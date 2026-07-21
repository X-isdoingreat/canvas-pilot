"""Option C paragraph-balanced constraint solver for canvas-awkward-syntax.

Given segments with roles, assigns ONE transformation per segment such that:
- Each transformation ∈ role's allowlist (rubric-safe)
- Per-paragraph max-frequency-1 (≤4 sents), max-2 (5-7 sents), ceil(N/4) (≥8)
- Doc-wide opener-category cap ≤30% (fronted-* / pseudo-cleft / gerund-subject)
- Fallback chain if infeasible: relax para-cap → relax doc-cap → any-legal

Greedy: per-paragraph in document order, per-sentence pick rarest transformation
(by doc-wide category count, then paragraph-internal use count).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Banned phrase guard (cross-skill sync with canvas-humanizer-surgical)
# ─────────────────────────────────────────────────────────────────────────────

# Conservative fallback list — kept in sync with canvas-humanizer-surgical-app.md
# `banned_words_post_surgical:` section. The runtime loader (below) reads from
# the overlay when available, so this fallback is the safety net for environments
# without the overlay (e.g., fork users running canvas-awkward-syntax standalone).
_BANNED_FALLBACK: list[str] = [
    "Moreover", "Furthermore", "In conclusion", "In summary",
    "It's worth noting", "It is worth noting", "It is important to note",
    "delve", "leverage", "multifaceted", "plethora", "paradigm",
    "In today's world", "As we navigate", "Embark on",
    "The journey of", "The landscape of",
]


def load_banned_phrases() -> list[str]:
    """Load banned phrase patterns from canvas-humanizer-surgical app overlay.

    Source of truth: `_private/canvas-humanizer-surgical-app.md` `banned_words_post_surgical:`
    YAML section. Falls back to `_BANNED_FALLBACK` (kept in rough sync) if overlay missing
    or unparseable.

    Note: adds "It is worth noting" alongside the overlay's "It's worth noting" because
    canvas-awkward-syntax's extraposed_copula previously generated the full "It is" form
    which the overlay's literal string match missed. Belt-and-suspenders.
    """
    overlay = Path("_private/canvas-humanizer-surgical-app.md")
    extra = {"It is worth noting"}  # full-form variant for the apostrophe contraction
    if overlay.exists():
        try:
            text = overlay.read_text(encoding="utf-8")
            m = re.search(r"banned_words_post_surgical:\s*\n((?:\s*-\s*.+\n?)+)", text)
            if m:
                phrases = []
                for line in m.group(1).strip().split("\n"):
                    p = line.strip().lstrip("-").strip()
                    if p:
                        phrases.append(p)
                # Add the full-form "It is worth noting" alongside overlay's apostrophe variant
                for v in extra:
                    if v not in phrases:
                        phrases.append(v)
                return phrases
        except Exception:
            pass
    return list(_BANNED_FALLBACK)


def contains_banned(text: str, banned: list[str] | None = None) -> str | None:
    """Return the first banned phrase found in text (case-insensitive), or None.

    Used as the post-rewrite output gate (see SKILL.md §8.3). Caller re-invokes
    the sub-agent on hit with an explicit "DO NOT use {hit}" instruction.
    """
    if banned is None:
        banned = load_banned_phrases()
    low = text.lower()
    for phrase in banned:
        if phrase.lower() in low:
            return phrase
    return None


_PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|been|being|be)\s+\w+ed\b", re.I)
_NOMINAL_RE = re.compile(
    r"\b(?:the|a)\s+\w+(?:tion|ment|ity|sion|ance|ence)\b", re.I
)
_LEADING_SUBORDINATE_RE = re.compile(
    r"^(?:When|While|Although|Because|If|Since|After|Before|Until|Through|Across|Among)\b"
    r"|^[A-Z]\w+ing\b"
)
_FRONTED_PP_RE = re.compile(
    r"^(?:In|On|At|By|With|From|For|Through|Across|Among|Between|Under|Over|After|Before)\b[^,]+,\s+"
)
_FORMULAIC_RE = re.compile(
    r"\b(?:play|have|exert)\b\s+(?:a|an)\b\s+\w+\s+"
    r"(?:role|part|impact|effect|influence)\b\s+(?:in|on)\b",
    re.I,
)
_EXTRAPOSED_RE = re.compile(
    r"\bIt is (?:undeniable|clear|certain|remarkable|generally accepted|"
    r"no exaggeration|abundantly clear|hard to overstate|beyond question|"
    r"self-evident|without doubt|patently clear)\b.*\bthat\b",
    re.I,
)
_FOLK_RE = re.compile(
    r"^(?:As we all know|As is known to all|It is generally accepted|"
    r"It goes without saying|It is universally acknowledged)\b",
    re.I,
)
_DISCOURSE_RE = re.compile(
    r"^(?:Last but not least|All in all|What's more|Generally speaking|"
    r"In a nutshell|On top of that)\b",
    re.I,
)
_SLANG_RE = re.compile(
    r"^(?:Honestly|Like|And yeah|Real talk|I'll be real|Not gonna lie|"
    r"Kinda wild|What's wild|Honestly though)\b"
    r"|\b(?:don't|can't|isn't|it's|that's|you'd|she'd|he'd|won't|hasn't|haven't)\b",
    re.I,
)
_REFLECTION_RE = re.compile(
    r"^(?:Reading (?:this|her|it)|What stays with me|What I keep coming back|"
    r"For me, the picture|From where I sit|Looking at (?:her|his|the) data|"
    r"To me, the honest|I keep asking|I find myself coming back)\b",
    re.I,
)
_SVA_SLIP_RE = re.compile(
    r"\b(?:he|she|it|[A-Z][a-z]+)\s+"
    r"(?:show|take|send|run|come|go|find|make|do|have|reach|get|treat|pay|"
    r"teach|sell|need|cover|reverse)\b"
)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _article_count(text: str) -> int:
    return len(re.findall(r"\b(?:the|a|an)\b", text, re.I))


def _topic_comment_marker_count(original: str, candidate: str) -> int:
    article_drops = max(0, _article_count(original) - _article_count(candidate))
    plural_drops = len(
        re.findall(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+[A-Za-z]+\b", candidate)
    )
    return article_drops + plural_drops + len(_SVA_SLIP_RE.findall(candidate))


def validate_transformation(
    original: str,
    candidate: str,
    transformation: str,
) -> dict[str, object]:
    """Deterministically verify the visible shape required by a transformation.

    This validator deliberately does not decide semantic equivalence.  The
    calling skill must run lock/source/rubric checks and an independent meaning
    review in addition to this structural gate.
    """

    reasons: list[str] = []
    if not candidate.strip():
        reasons.append("empty candidate")
    if any(mark in candidate for mark in ("—", "–", ":")):
        reasons.append("forbidden punctuation")

    original_wc = _word_count(original)
    candidate_wc = _word_count(candidate)
    rule_ok = True

    if transformation == "voice_flip":
        rule_ok = abs(len(_PASSIVE_RE.findall(candidate)) - len(_PASSIVE_RE.findall(original))) >= 1
        if original_wc < 8 and candidate.strip() == original.strip():
            rule_ok = True
    elif transformation == "clause_reorder":
        rule_ok = bool(_LEADING_SUBORDINATE_RE.search(candidate))
    elif transformation == "nominalize_flip":
        rule_ok = len(_NOMINAL_RE.findall(candidate)) != len(_NOMINAL_RE.findall(original))
    elif transformation == "pseudo_cleft":
        rule_ok = bool(re.search(r"^(?:What|It is)\b|\b(?:is what|are what)\b", candidate))
    elif transformation == "fronted_pp":
        rule_ok = bool(_FRONTED_PP_RE.search(candidate))
    elif transformation == "fronted_when":
        rule_ok = bool(re.match(r"^When\b", candidate))
    elif transformation == "fronted_while":
        rule_ok = bool(re.match(r"^While\b", candidate))
    elif transformation == "fronted_participle_post_author":
        rule_ok = bool(
            re.search(r'^In\s+"[^"]+"\s*\([^)]+\),\s*[A-Z]\w+', candidate)
            and re.search(r",\s+\w+ing\b[^,]*,", candidate)
        )
    elif transformation == "gerund_subject":
        rule_ok = bool(re.match(r"^[A-Z][a-z]+ing\b\s+\w+", candidate))
    elif transformation == "right_branching_extension":
        rule_ok = (
            original.split()[:3] == candidate.split()[:3]
            and candidate_wc >= original_wc + 8
        )
    elif transformation == "topic_comment_chinese":
        opener_ok = bool(
            re.match(r"^About\b", candidate)
            or re.search(r"\b\w+,\s+(?:it|this|he|she|they)\s+", candidate, re.I)
            or re.search(r",\s+this\s+is\s+\w+\.?$", candidate, re.I)
        )
        required = 0 if candidate_wc <= 20 else (candidate_wc + 11) // 12
        rule_ok = opener_ok and _topic_comment_marker_count(original, candidate) >= required
    elif transformation == "article_omission_esl":
        rule_ok = _article_count(candidate) < _article_count(original) or bool(
            _SVA_SLIP_RE.search(candidate)
        )
    elif transformation == "extraposed_copula":
        rule_ok = bool(_EXTRAPOSED_RE.search(candidate)) and not re.search(
            r"\b(?:worth noting|important to note)\b", candidate, re.I
        )
    elif transformation == "fact_noun_complement":
        rule_ok = bool(re.search(r"\bthe fact that\b", candidate, re.I))
    elif transformation == "formulaic_verb_noun":
        rule_ok = bool(_FORMULAIC_RE.search(candidate))
    elif transformation == "folk_wisdom_opener":
        rule_ok = bool(_FOLK_RE.search(candidate))
    elif transformation == "discourse_pleonasm":
        rule_ok = bool(_DISCOURSE_RE.search(candidate))
    elif transformation == "dual_connective_chinese":
        rule_ok = bool(
            re.search(r"\b(?:Although|Even though|Because|Since)\b.+\b(?:but|so)\b", candidate)
        )
    elif transformation == "slang_break":
        rule_ok = bool(_SLANG_RE.search(candidate)) and 5 <= candidate_wc <= 18
    elif transformation == "first_person_reflection":
        first_50 = candidate[:50]
        rule_ok = (
            bool(_REFLECTION_RE.search(candidate))
            and bool(re.search(r"\b(?:I|me|my)\b", first_50, re.I))
            and 10 <= candidate_wc <= 30
            and not re.search(r"\b(?:gonna|kinda|gotta|lowkey|honestly|real talk)\b", candidate, re.I)
        )
    elif transformation == "minimal_lexical":
        similarity = SequenceMatcher(None, original, candidate).ratio()
        rule_ok = similarity <= 0.90 and original.split()[:3] == candidate.split()[:3]
    else:
        rule_ok = False
        reasons.append(f"unknown transformation: {transformation}")

    if not rule_ok:
        reasons.append("transformation shape not detected")
    return {
        "ok": not reasons,
        "transformation": transformation,
        "original_word_count": original_wc,
        "candidate_word_count": candidate_wc,
        "reasons": reasons,
    }


# Role × transformation allowlist (per plan §Role allowlist matrix).
# Body roles get 3 new ESL-Chinese transformations (§5.12-§5.14 in SKILL.md):
# topic_comment_chinese, article_omission_esl, dual_connective_chinese.
# Conclusion_structural tightened: voice_flip removed after smoketest run 1
# showed voice_flip produced fluent passive English that GPTZero flagged.
ROLE_ALLOWLIST: dict[str, list[str]] = {
    "intro_opener": ["fronted_participle_post_author", "minimal_lexical"],
    "intro_thesis": ["pseudo_cleft", "nominalize_flip"],
    "intro_setup": ["voice_flip", "clause_reorder", "fronted_when"],
    "body_TS": ["fronted_when", "fronted_while", "fronted_participle_post_author", "voice_flip"],
    "body_quote_lead_in": ["pseudo_cleft", "nominalize_flip"],
    "body_quote_follow_up": ["voice_flip", "clause_reorder"],
    "body_elaboration": [
        # 5 MANDATORY Chinese-student-formal cringe patterns (§5.15-§5.19)
        "extraposed_copula", "fact_noun_complement", "formulaic_verb_noun",
        "folk_wisdom_opener", "discourse_pleonasm",
        # ESL supplements
        "topic_comment_chinese", "article_omission_esl", "dual_connective_chinese",
        "right_branching_extension",
    ],
    "body_anecdote": ["topic_comment_chinese", "article_omission_esl", "right_branching_extension"],
    "body_closing": [
        # 3 of the 5 cringe patterns (skip openers — closing position)
        "extraposed_copula", "fact_noun_complement", "discourse_pleonasm",
        # supplements
        "gerund_subject", "article_omission_esl",
    ],
    "conclusion_thesis_restate": ["fronted_participle_post_author", "pseudo_cleft", "first_person_reflection"],
    "conclusion_structural": ["clause_reorder", "fronted_pp", "gerund_subject", "first_person_reflection"],
    "conclusion_closing": ["voice_flip", "gerund_subject", "fronted_pp", "first_person_reflection"],
}

# Opener-category grouping for doc-wide cadence-uniformity cap.
# Doc-wide cap of 30% applies to each category; transformations not in this map
# count as "other" (no cap).
OPENER_CATEGORY: dict[str, str] = {
    "fronted_pp": "fronted",
    "fronted_when": "fronted",
    "fronted_while": "fronted",
    "fronted_participle_post_author": "fronted",
    "pseudo_cleft": "pseudo_cleft",
    "gerund_subject": "gerund_subject",
}

CAPPED_CATEGORIES = {"fronted", "pseudo_cleft", "gerund_subject"}


def _max_per_para(n_sents: int, relaxation: int) -> int:
    if relaxation >= 2:
        return n_sents  # no limit
    if relaxation == 1:
        return 2
    # strict (relaxation == 0)
    if n_sents <= 4:
        return 1
    if n_sents <= 7:
        return 2
    return (n_sents + 3) // 4


def _doc_cap_ratio(relaxation: int) -> float:
    if relaxation == 0:
        return 0.30
    if relaxation == 1:
        return 0.40
    return 1.0


def _inject_slang_quota(segments: list[dict], target_ratio: float = 0.14) -> None:
    """Force selected body sentences to be slang_break (continuity breaker per §5.20).

    GPTZero is span-continuity-based: long unbroken academic-register runs trigger
    high AI scores. slang_break breaks the register every few sentences.

    Priority placement (run 3 diagnosis):
    1. **Post-anecdote slot**: the sentence immediately AFTER a body_anecdote
       (which is content-bearing and can't be slang-replaced). Anecdote → next
       sentence is the dead-zone where register continuity rebuilds. Highest
       priority slot for slang_break.
    2. Step-based fill: every-N-th body sentence (body_elaboration / body_closing)
       to reach target count.

    Skips body_anecdote (content-bearing) and body_TS (gate-sensitive).
    """
    BODY_RUNNABLE_ROLES = {"body_elaboration", "body_closing"}
    target_count = max(2, round(len(segments) * target_ratio))

    # Document-ordered segment list
    ordered = sorted(segments, key=lambda x: (x["doc_paragraph_index"], x["intra_para_index"]))

    # Priority 1: post-anecdote slots
    selected_ids = set()
    for i, s in enumerate(ordered):
        if s["role"] == "body_anecdote" and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            # Only post-anecdote slot if next is in body_elaboration / body_closing
            # AND same paragraph (don't slang-break across paragraph boundary)
            if (
                nxt["role"] in BODY_RUNNABLE_ROLES
                and nxt["doc_paragraph_index"] == s["doc_paragraph_index"]
                and nxt["seg_id"] not in selected_ids
            ):
                selected_ids.add(nxt["seg_id"])

    # Priority 2: step-based fill for remaining quota
    body_ordered = [s for s in ordered if s["role"] in BODY_RUNNABLE_ROLES and s["seg_id"] not in selected_ids]
    remaining = max(0, target_count - len(selected_ids))
    if remaining > 0 and len(body_ordered) >= 3:
        step = max(1, len(body_ordered) // max(1, remaining))
        start = max(1, step // 2)
        idx = start
        while idx < len(body_ordered) and remaining > 0:
            selected_ids.add(body_ordered[idx]["seg_id"])
            remaining -= 1
            idx += step

    for s in segments:
        if s["seg_id"] in selected_ids:
            s["transformation"] = "slang_break"


def _inject_conclusion_register_shift(segments: list[dict]) -> None:
    """Force ≥1 conclusion sentence per conclusion paragraph to use first_person_reflection.

    Empirical (2026-05-23 run 7): conclusion paragraphs assigned only cadence transformations
    (fronted_*, pseudo_cleft, gerund_subject, voice_flip) preserved third-person academic
    register continuity and scored 90% on GPTZero. first_person_reflection (§5.21) breaks
    the register without slang, recovering detector score AND grade.

    Strategy: for each conclusion paragraph (≥1 segment with role starting "conclusion_"),
    if NO segment already has transformation=first_person_reflection, promote the middle
    structural sentence (priority: conclusion_structural > conclusion_thesis_restate >
    conclusion_closing). The closing sentence is left alone if possible — it's the punch line.
    """
    CONCLUSION_ROLES = {"conclusion_thesis_restate", "conclusion_structural", "conclusion_closing"}
    PROMOTION_PRIORITY = ["conclusion_structural", "conclusion_thesis_restate", "conclusion_closing"]

    # Group conclusion segments by paragraph
    by_para: dict[int, list[dict]] = defaultdict(list)
    for s in segments:
        if s["role"] in CONCLUSION_ROLES:
            by_para[s["doc_paragraph_index"]].append(s)

    for p_idx, p_segs in by_para.items():
        if any(s.get("transformation") == "first_person_reflection" for s in p_segs):
            continue  # already has one
        # Pick promotion target by priority
        promoted = None
        for target_role in PROMOTION_PRIORITY:
            for s in p_segs:
                if s["role"] == target_role:
                    promoted = s
                    break
            if promoted:
                break
        if promoted:
            promoted["transformation"] = "first_person_reflection"


def assign_transformations(segments: list[dict]) -> list[dict]:
    """Assign one transformation per segment.

    Each segment must have: seg_id, doc_paragraph_index, intra_para_index, role, v0_text.
    Returns the same list with 'transformation' + 'relaxation_level' fields added.

    After greedy assignment, runs _inject_slang_quota to force ~18% of body
    sentences to slang_break (continuity-breaker per §5.20).
    """
    n = len(segments)
    if n == 0:
        return segments

    by_para: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        by_para[seg["doc_paragraph_index"]].append(seg)

    for relaxation in (0, 1, 2):
        assignments: dict[str, str] = {}
        category_count: Counter[str] = Counter()
        doc_cap = _doc_cap_ratio(relaxation) * n
        infeasible = False

        for p_idx in sorted(by_para):
            p_segs = sorted(by_para[p_idx], key=lambda s: s["intra_para_index"])
            cap = _max_per_para(len(p_segs), relaxation)
            para_used: Counter[str] = Counter()

            for seg in p_segs:
                allowed = list(ROLE_ALLOWLIST.get(seg["role"], ["minimal_lexical"]))
                # Fallback rule 1: short sentences (<10 words) → minimal_lexical only
                wc = len(str(seg.get("v0_text", "")).split())
                if wc < 10:
                    allowed = ["minimal_lexical"]

                # Filter by para-cap and doc-cap
                def passes_caps(t: str) -> bool:
                    if para_used[t] >= cap:
                        return False
                    cat = OPENER_CATEGORY.get(t)
                    if cat in CAPPED_CATEGORIES and category_count[cat] >= doc_cap:
                        return False
                    return True

                candidates = [t for t in allowed if passes_caps(t)]
                # Soft relaxation if no candidates: try ignoring doc-cap
                if not candidates:
                    candidates = [t for t in allowed if para_used[t] < cap]
                # Hard relaxation: any allowed
                if not candidates:
                    candidates = list(allowed)
                if not candidates:
                    candidates = ["minimal_lexical"]

                chosen = min(
                    candidates,
                    key=lambda t: (
                        category_count[OPENER_CATEGORY.get(t, "other")],
                        para_used[t],
                    ),
                )
                assignments[seg["seg_id"]] = chosen
                para_used[chosen] += 1
                cat = OPENER_CATEGORY.get(chosen, "other")
                category_count[cat] += 1

            if len(assignments) < sum(len(by_para[q]) for q in by_para if q <= p_idx):
                infeasible = True
                break

        if not infeasible and len(assignments) == n:
            for seg in segments:
                seg["transformation"] = assignments[seg["seg_id"]]
                seg["relaxation_level"] = relaxation
            # Post-pass: inject slang_break quota (§5.20)
            _inject_slang_quota(segments, target_ratio=0.18)
            # Post-pass: inject conclusion register shift (§5.21)
            _inject_conclusion_register_shift(segments)
            return segments

    # Last resort: assign minimal_lexical to anything unset
    for seg in segments:
        seg.setdefault("transformation", "minimal_lexical")
        seg["relaxation_level"] = "last_resort"
    _inject_slang_quota(segments, target_ratio=0.18)
    _inject_conclusion_register_shift(segments)
    return segments


def write_assignment_report(segments: list[dict], out_path: str | Path) -> None:
    """Write a JSON report of the assignment, including category distribution."""
    cat_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    trans_counts: Counter[str] = Counter()
    for seg in segments:
        t = seg.get("transformation", "?")
        trans_counts[t] += 1
        cat_counts[OPENER_CATEGORY.get(t, "other")] += 1
        role_counts[seg.get("role", "?")] += 1

    n = max(len(segments), 1)
    report = {
        "total_segments": len(segments),
        "relaxation_level": segments[0].get("relaxation_level") if segments else None,
        "transformation_distribution": dict(trans_counts),
        "category_distribution": {
            cat: {"count": cnt, "ratio": round(cnt / n, 3)}
            for cat, cnt in cat_counts.items()
        },
        "role_distribution": dict(role_counts),
        "assignments": [
            {"seg_id": s["seg_id"], "role": s["role"], "transformation": s.get("transformation")}
            for s in segments
        ],
    }
    Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
