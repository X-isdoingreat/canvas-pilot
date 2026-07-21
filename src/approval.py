# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic parser for scan-plan execution approval.

Execution approval only authorizes Canvas Pilot to *produce assignment work*.
It never authorizes a Canvas POST/PUT.  Live Canvas mutations require a
separate signed receipt from :mod:`src.authorization`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .run_state import RunStateError, load_json, validate_plan, write_plan


_VAGUE = re.compile(
    r"\b(?:important|best|priority|whatever|use your judgment|you decide)\b|"
    r"重要的|你看着办|你决定|优先的",
    re.IGNORECASE,
)
_SWAP = re.compile(
    r"\bswap\s+(\d+)\s+(?:to|->)\s+(canvas-[a-z0-9][a-z0-9-]*)\b",
    re.IGNORECASE,
)
_SWAP_ZH = re.compile(
    r"(?:第\s*)?(\d+)\s*(?:项)?\s*(?:用|改用)\s*"
    r"(canvas-[a-z0-9][a-z0-9-]*)",
    re.IGNORECASE,
)
_DEFER = re.compile(
    r"(?:\b(?:defer|skip)\b|跳过|暂缓)\s*([0-9][0-9,\s-]*)", re.IGNORECASE
)
_APPROVE = re.compile(
    r"(?:\b(?:approve|run|execute|do)\b|做|批准|执行)\s*([0-9][0-9,\s-]*)",
    re.IGNORECASE,
)
_ONLY_NUMBERS = re.compile(r"^\s*[0-9,\s-]+\s*$")


@dataclass(frozen=True)
class ApprovalParse:
    kind: str  # apply | cancel | clarify
    decisions: dict[int, str] = field(default_factory=dict)
    approved_indices: tuple[int, ...] = ()
    deferred_indices: tuple[int, ...] = ()
    clarification: str | None = None
    raw_text: str = ""
    scope: str = "execution_only"
    grants_canvas_mutation: bool = False

    @property
    def needs_clarification(self) -> bool:
        return self.kind == "clarify"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "scope": self.scope,
            "grants_canvas_mutation": self.grants_canvas_mutation,
            "decisions": {str(k): v for k, v in sorted(self.decisions.items())},
            "approved_indices": list(self.approved_indices),
            "deferred_indices": list(self.deferred_indices),
            "clarification": self.clarification,
            "raw_text": self.raw_text,
        }


def _items(plan_or_items: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(plan_or_items, Mapping):
        return validate_plan(plan_or_items, require_current=True)["items"]
    plan = validate_plan({"items": list(plan_or_items)}, require_timestamps=False)
    return plan["items"]


def _expand_indices(expr: str) -> set[int]:
    out: set[int] = set()
    compact = re.sub(r"\s*-\s*", "-", expr.strip())
    for token in re.split(r"[\s,]+", compact):
        if not token:
            continue
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise ValueError(f"invalid range {token!r}")
            lo, hi = (int(part) for part in parts)
            if lo <= 0 or hi < lo:
                raise ValueError(f"invalid range {token!r}")
            out.update(range(lo, hi + 1))
        elif token.isdigit() and int(token) > 0:
            out.add(int(token))
        else:
            raise ValueError(f"invalid index {token!r}")
    if not out:
        raise ValueError("no indices found")
    return out


def _clarify(raw: str, reason: str) -> ApprovalParse:
    return ApprovalParse(kind="clarify", clarification=reason, raw_text=raw)


def parse_approval(
    text: str,
    plan_or_items: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> ApprovalParse:
    """Parse the documented approval language without guessing intent."""

    raw = text or ""
    normalized = (
        raw.strip()
        .lower()
        .replace("–", "-")
        .replace("—", "-")
        .replace("，", ",")
        .replace("；", ";")
    )
    normalized = re.sub(r"(?<=\d)\s*(?:到|至)\s*(?=\d)", "-", normalized)
    items = _items(plan_or_items)
    indices = {int(item["index"]) for item in items}
    if not normalized:
        return _clarify(raw, "No approval selection was provided.")
    if _VAGUE.search(normalized):
        return _clarify(raw, "Selection is qualitative; name exact indices, a range, all, or urgent only.")

    exact_cancel = normalized in {
        "cancel", "skip", "cancel all", "skip all", "取消", "算了", "全部取消", "都不做"
    }
    if exact_cancel:
        decisions = {index: "defer" for index in indices}
        return ApprovalParse(
            kind="cancel",
            decisions=decisions,
            deferred_indices=tuple(sorted(indices)),
            raw_text=raw,
        )

    urgent_only = bool(
        re.fullmatch(r"(?:approve\s+)?urgent(?:\s+only)?", normalized)
        or normalized in {"只做紧急", "仅紧急", "只批准紧急", "只做 urgent", "仅做 urgent"}
    )
    if urgent_only:
        urgent = {int(item["index"]) for item in items if str(item.get("bucket", "")).lower() == "urgent"}
        decisions = {index: ("approve" if index in urgent else "defer") for index in indices}
        return ApprovalParse(
            kind="apply",
            decisions=decisions,
            approved_indices=tuple(sorted(urgent)),
            deferred_indices=tuple(sorted(indices - urgent)),
            raw_text=raw,
        )

    approved: set[int] = set()
    deferred: set[int] = set()
    swaps: dict[int, str] = {}
    broad_selector = False
    explicit_approved: set[int] = set()
    clauses = [clause.strip() for clause in normalized.split(";")]
    if any(not clause for clause in clauses):
        return _clarify(raw, "Approval clauses must not be empty.")

    try:
        for position, clause in enumerate(clauses):
            if clause in {"all", "全部", "都做", "全部做", "全部批准", "全部执行"} or re.fullmatch(
                r"(?:approve|execute|run|do)\s+all", clause
            ):
                if position != 0:
                    return _clarify(raw, "A broad approval selector must be the first clause.")
                approved.update(indices)
                broad_selector = True
                continue
            if clause in {"urgent", "urgent only", "只做紧急", "仅紧急", "只批准紧急", "只做 urgent", "仅做 urgent"}:
                if position != 0:
                    return _clarify(raw, "The urgent selector must be the first clause.")
                selected = {
                    int(item["index"])
                    for item in items
                    if str(item.get("bucket", "")).lower() == "urgent"
                }
                approved.update(selected)
                broad_selector = True
                continue
            if position == 0 and len(clauses) == 1 and _ONLY_NUMBERS.fullmatch(clause):
                selected = _expand_indices(clause)
                approved.update(selected)
                explicit_approved.update(selected)
                continue
            match = _APPROVE.fullmatch(clause)
            if match:
                selected = _expand_indices(match.group(1))
                approved.update(selected)
                explicit_approved.update(selected)
                continue
            match = _DEFER.fullmatch(clause)
            if match:
                deferred.update(_expand_indices(match.group(1)))
                continue
            match = _SWAP.fullmatch(clause) or _SWAP_ZH.fullmatch(clause)
            if match:
                index = int(match.group(1))
                swaps[index] = f"swap:{match.group(2).lower()}"
                approved.add(index)
                explicit_approved.add(index)
                continue
            return _clarify(
                raw,
                f"Unrecognized approval clause {clause!r}; use only the documented exact forms.",
            )
    except ValueError as exc:
        return _clarify(raw, str(exc))

    mentioned = approved | deferred | set(swaps)
    unknown = mentioned - indices
    if unknown:
        return _clarify(raw, f"Plan has no item index/indices: {sorted(unknown)}.")
    # Targeted defer may narrow a broad selector.  It conflicts with an exact
    # approve/swap for the same item; unknown residual prose never reaches here.
    contradictions = explicit_approved & deferred
    if contradictions:
        return _clarify(raw, f"Items have both approve and defer instructions: {sorted(contradictions)}.")
    approved -= deferred
    if not broad_selector and not approved and not deferred and not swaps:
        return _clarify(raw, "Use exact indices, a range, all, urgent only, defer N, or swap N to canvas-x.")

    decisions = {index: "defer" for index in indices}
    for index in approved:
        decisions[index] = "approve"
    decisions.update(swaps)
    deferred_final = indices - approved
    return ApprovalParse(
        kind="apply",
        decisions=decisions,
        approved_indices=tuple(sorted(approved)),
        deferred_indices=tuple(sorted(deferred_final)),
        raw_text=raw,
    )


def apply_approval_to_plan(plan: Mapping[str, Any], parsed: ApprovalParse) -> dict[str, Any]:
    if parsed.needs_clarification:
        raise RunStateError("cannot update plan from an ambiguous approval")
    updated = validate_plan(plan, require_current=True)
    for item in updated["items"]:
        item["user_decision"] = parsed.decisions.get(int(item["index"]), "defer")
    return validate_plan(updated, require_current=True)


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse/apply Canvas execution approval")
    parser.add_argument("command", choices=("parse", "apply"))
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--text", help="approval text; omit to read stdin")
    args = parser.parse_args(argv)
    raw = args.text if args.text is not None else sys.stdin.read()
    try:
        plan = validate_plan(load_json(args.plan), require_current=True)
        parsed = parse_approval(raw, plan)
    except (OSError, ValueError, RunStateError) as exc:
        print(json.dumps({"kind": "error", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(parsed.as_dict(), ensure_ascii=False, indent=2))
    if parsed.needs_clarification:
        return 2
    if args.command == "apply":
        write_plan(args.plan, apply_approval_to_plan(plan, parsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
