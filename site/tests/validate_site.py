from __future__ import annotations

import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


SITE_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://canvas-pilot.likelyou.com"
ROUTE_ALIASES = {
    "/install": SITE_ROOT / "index.html",
    "/zh/install": SITE_ROOT / "zh" / "index.html",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang = ""
        self.ids: list[str] = []
        self.labels: list[str] = []
        self.links: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self.canonical = ""
        self.alternates: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.textareas: dict[str, str] = {}
        self.text: list[str] = []
        self.start_tags: list[tuple[str, dict[str, str]]] = []
        self._json_buffer: list[str] | None = None
        self._textarea_id: str | None = None
        self._textarea_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.start_tags.append((tag, values))
        element_id = values.get("id")
        if element_id:
            self.ids.append(element_id)

        if tag == "html":
            self.html_lang = values.get("lang", "")
        elif tag == "label" and values.get("for"):
            self.labels.append(values["for"])
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])
            self.anchors.append(values)
        elif tag == "link":
            rel = values.get("rel", "")
            if rel == "canonical":
                self.canonical = values.get("href", "")
            elif rel == "alternate" and values.get("hreflang"):
                self.alternates[values["hreflang"]] = values.get("href", "")
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._json_buffer = []
        elif tag == "textarea" and element_id:
            self._textarea_id = element_id
            self._textarea_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_buffer is not None:
            self.json_ld.append("".join(self._json_buffer).strip())
            self._json_buffer = None
        elif tag == "textarea" and self._textarea_id is not None:
            self.textareas[self._textarea_id] = "".join(self._textarea_buffer or [])
            self._textarea_id = None
            self._textarea_buffer = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._json_buffer is not None:
            self._json_buffer.append(data)
        if self._textarea_buffer is not None:
            self._textarea_buffer.append(data)


def route_for(path: Path) -> str:
    relative = path.relative_to(SITE_ROOT)
    if relative == Path("index.html"):
        return "/"
    if relative.name == "index.html":
        return "/" + relative.parent.as_posix()
    return "/" + relative.as_posix()


def resolve_internal_path(href: str) -> tuple[Path | None, str]:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None, ""
    path = parsed.path
    fragment = parsed.fragment
    if not path:
        return None, fragment
    if path in ROUTE_ALIASES:
        return ROUTE_ALIASES[path], fragment
    relative = path.lstrip("/")
    candidate = SITE_ROOT / relative
    if candidate.is_file():
        return candidate, fragment
    return candidate / "index.html", fragment


def load_pages() -> tuple[dict[Path, PageParser], list[str]]:
    pages: dict[Path, PageParser] = {}
    errors: list[str] = []
    for path in sorted(SITE_ROOT.rglob("*.html")):
        parser = PageParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except Exception as exc:
            errors.append(f"{path.relative_to(SITE_ROOT)}: HTML parse failed: {exc}")
            continue
        pages[path.resolve()] = parser

        duplicates = [key for key, count in Counter(parser.ids).items() if count > 1]
        if duplicates:
            errors.append(f"{path.relative_to(SITE_ROOT)}: duplicate ids: {duplicates}")
        for target in parser.labels:
            if target not in parser.ids:
                errors.append(f"{path.relative_to(SITE_ROOT)}: label target #{target} is missing")
        for index, block in enumerate(parser.json_ld, start=1):
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.relative_to(SITE_ROOT)}: JSON-LD block {index} is invalid: {exc}")
    return pages, errors


def validate_links(pages: dict[Path, PageParser], errors: list[str]) -> None:
    for path, parser in pages.items():
        for href in parser.links:
            target, fragment = resolve_internal_path(href)
            if target is None:
                if fragment and fragment not in parser.ids:
                    errors.append(f"{path.relative_to(SITE_ROOT)}: missing fragment #{fragment}")
                continue
            target = target.resolve()
            if not target.exists():
                errors.append(f"{path.relative_to(SITE_ROOT)}: broken internal link {href}")
                continue
            if fragment and target.suffix == ".html":
                target_page = pages.get(target)
                if target_page is None or fragment not in target_page.ids:
                    errors.append(f"{path.relative_to(SITE_ROOT)}: missing target fragment {href}")


def validate_github_link_behavior(pages: dict[Path, PageParser], errors: list[str]) -> None:
    for path, parser in pages.items():
        for anchor in parser.anchors:
            href = anchor["href"]
            hostname = (urlsplit(href).hostname or "").lower()
            if hostname not in {"github.com", "www.github.com"}:
                continue
            if anchor.get("target") != "_blank":
                errors.append(
                    f"{path.relative_to(SITE_ROOT)}: GitHub link must open a new window: {href}"
                )
            rel_tokens = set(anchor.get("rel", "").lower().split())
            missing_rel = {"noopener", "noreferrer"} - rel_tokens
            if missing_rel:
                errors.append(
                    f"{path.relative_to(SITE_ROOT)}: GitHub link is missing rel tokens "
                    f"{sorted(missing_rel)}: {href}"
                )


def validate_setup_contracts(pages: dict[Path, PageParser], errors: list[str]) -> None:
    expected = {
        SITE_ROOT / "setup" / "index.html": {
            "lang": "en",
            "canonical": f"{BASE_URL}/setup",
            "page_phrases": [
                "Download. Name your school. Log in. Choose a skill.",
                "Four steps, in this order.",
                "Name your school",
                "Run Opportunity",
                "Strong fit after course setup",
                "Conditional fit",
                "Manual handoff",
                "Copied. Paste the prompt into your local agent.",
                "Copy failed. The prompt is selected so you can copy it manually.",
            ],
            "required_phrases": [
                ".agents/skills/canvas-setup/SKILL.md",
                ".agents/skills/canvas-skill-opportunity/SKILL.md",
                'ask me exactly: "Which school do you use Canvas through?"',
                "official Canvas login URL",
                "If it is ambiguous, ask me for the URL; never guess.",
                "Open an interactive browser so I can log in to Canvas.",
                "Immediately after login, run canvas-skill-opportunity read-only.",
                "stop and ask me to choose a number",
                "Until I choose: do not run canvas-bootstrap",
                "scan pending work",
                "commit, push, deploy, or modify .claude",
                "keep the full report local",
            ],
            "max_prompt_chars": 1500,
            "max_prompt_lines": 18,
        },
        SITE_ROOT / "zh" / "setup" / "index.html": {
            "lang": "zh-CN",
            "canonical": f"{BASE_URL}/zh/setup",
            "page_phrases": [
                "下载、选学校、登录，再选第一个 Skill。",
                "严格按照这四步进行。",
                "告诉它学校",
                "运行 Opportunity",
                "完成课程配置后，尤其适合",
                "有条件支持",
                "需要人工接手",
                "已复制。现在可以把提示词粘贴到本地 Agent。",
                "复制失败。提示词已经选中，请手动复制。",
            ],
            "required_phrases": [
                ".agents/skills/canvas-setup/SKILL.md",
                ".agents/skills/canvas-skill-opportunity/SKILL.md",
                "下载完成后先问我：“你在哪所学校使用 Canvas？”",
                "学校官方 Canvas 登录地址",
                "如果不明确，再问我网址，不要猜",
                "打开交互式浏览器让我登录 Canvas。",
                "登录后立即只读运行 canvas-skill-opportunity。",
                "停下来让我选号",
                "我选号前，不要运行 canvas-bootstrap",
                "扫描待办",
                "commit、push、deploy，也不要修改 .claude",
                "完整报告留在本机",
            ],
            "max_prompt_chars": 800,
            "max_prompt_lines": 18,
        },
    }
    alternates = {
        "en": f"{BASE_URL}/setup",
        "zh-CN": f"{BASE_URL}/zh/setup",
        "x-default": f"{BASE_URL}/setup",
    }

    for path, contract in expected.items():
        parser = pages.get(path.resolve())
        relative = path.relative_to(SITE_ROOT)
        if parser is None:
            errors.append(f"{relative}: setup guide is missing")
            continue
        if parser.html_lang != contract["lang"]:
            errors.append(f"{relative}: expected lang={contract['lang']}, got {parser.html_lang!r}")
        if parser.canonical != contract["canonical"]:
            errors.append(f"{relative}: incorrect canonical {parser.canonical!r}")
        if parser.alternates != alternates:
            errors.append(f"{relative}: incorrect hreflang map {parser.alternates!r}")
        prompt = parser.textareas.get("setup-prompt-text", "")
        if not prompt:
            errors.append(f"{relative}: setup prompt textarea is missing or empty")
        for phrase in contract["required_phrases"]:
            if phrase not in prompt:
                errors.append(f"{relative}: setup prompt lost required contract text: {phrase!r}")
        if len(prompt) > contract["max_prompt_chars"]:
            errors.append(
                f"{relative}: setup prompt is too verbose "
                f"({len(prompt)} > {contract['max_prompt_chars']} characters)"
            )
        prompt_lines = len(prompt.splitlines())
        if prompt_lines > contract["max_prompt_lines"]:
            errors.append(
                f"{relative}: setup prompt has too many lines "
                f"({prompt_lines} > {contract['max_prompt_lines']})"
            )
        visible_text = " ".join(parser.text)
        for phrase in contract["page_phrases"]:
            if phrase not in visible_text:
                errors.append(f"{relative}: localized page copy is missing: {phrase!r}")
        if "—" in visible_text or "–" in visible_text:
            errors.append(f"{relative}: visible copy contains a disallowed long dash")

    english = pages.get((SITE_ROOT / "setup" / "index.html").resolve())
    chinese = pages.get((SITE_ROOT / "zh" / "setup" / "index.html").resolve())
    if english is not None and chinese is not None:
        english_prompt = english.textareas.get("setup-prompt-text", "")
        chinese_prompt = chinese.textareas.get("setup-prompt-text", "")
        required_literals = (
            "https://github.com/X-isdoingreat/canvas-pilot.git",
            "AGENTS.md",
            ".agents/skills/canvas-setup/SKILL.md",
            ".agents/skills/canvas-skill-opportunity/SKILL.md",
            "canvas-bootstrap",
            ".claude",
        )
        for literal in required_literals:
            if literal not in english_prompt or literal not in chinese_prompt:
                errors.append(f"localized setup prompts lost technical literal: {literal!r}")


def validate_home_contracts(pages: dict[Path, PageParser], errors: list[str]) -> None:
    root_alternates = {
        "en": f"{BASE_URL}/install",
        "zh-CN": f"{BASE_URL}/zh/install",
        "x-default": f"{BASE_URL}/install",
    }
    expected = {
        SITE_ROOT / "index.html": {
            "lang": "en",
            "canonical": f"{BASE_URL}/install",
            "prompt_source": SITE_ROOT / "setup" / "index.html",
            "phrases": [
                "Kill repetitive homework.",
                "Everyone uses AI for homework.",
                "Copy this to your Agent to get started",
                "Expand",
                "Copy for your Agent",
                "4 manual steps, every week",
                "Find Canvas files",
                "Read requirements",
                "One Agent Skill",
                "runs it all.",
                "Reusable Agent Skill",
                "Reads Canvas files",
                "Does the work",
                "Ready for Canvas",
                "How it works",
                "Quiz",
                "First attempt. Canvas feedback. A corrected second attempt.",
                "Code assignments",
                "Documents",
                "Inside Canvas",
                "Built for work AI can finish and check.",
            ],
            "success": "Copied. Paste it into your Agent.",
            "failure": "Copy failed. Open the install page to copy it manually.",
        },
        SITE_ROOT / "zh" / "index.html": {
            "lang": "zh-CN",
            "canonical": f"{BASE_URL}/zh/install",
            "prompt_source": SITE_ROOT / "zh" / "setup" / "index.html",
            "phrases": [
                "重复作业杀手",
                "大家都在用 AI 写作业",
                "复制这段话给你的agent，开始使用吧",
                "展开",
                "复制给 Agent",
                "每周都要手动做 4 步",
                "查找课程文件",
                "查看作业要求",
                "完成作业答案",
                "提交作业结果",
                "一个 Agent Skill",
                "自动完成整套流程",
                "可复用 Agent Skill",
                "读取 Canvas 文件",
                "完成作业",
                "准备好交回 Canvas",
                "How it works",
                "Quiz",
                "完成第一遍，读取 Canvas 成绩和反馈，再修正第二遍。",
                "代码作业",
                "文档作业",
                "Canvas 内作业",
                "适合作业，比作业长短更重要。",
            ],
            "success": "已复制。现在把它粘贴给你的 Agent。",
            "failure": "复制失败。请打开安装页手动复制。",
        },
    }

    for path, contract in expected.items():
        relative = path.relative_to(SITE_ROOT)
        parser = pages.get(path.resolve())
        if parser is None:
            errors.append(f"{relative}: localized home page is missing")
            continue
        if parser.html_lang != contract["lang"]:
            errors.append(f"{relative}: expected lang={contract['lang']}, got {parser.html_lang!r}")
        if parser.canonical != contract["canonical"]:
            errors.append(f"{relative}: incorrect canonical {parser.canonical!r}")
        if parser.alternates != root_alternates:
            errors.append(f"{relative}: incorrect root hreflang map {parser.alternates!r}")

        visible_text = " ".join(parser.text)
        for phrase in contract["phrases"]:
            if phrase not in visible_text:
                errors.append(f"{relative}: landing copy is missing: {phrase!r}")
        if "—" in visible_text or "–" in visible_text:
            errors.append(f"{relative}: visible copy contains a disallowed long dash")

        transitions = [
            attrs
            for _tag, attrs in parser.start_tags
            if attrs.get("data-automation-transition") == "4-to-1"
        ]
        if len(transitions) != 1:
            errors.append(f"{relative}: expected exactly one 4-to-1 workflow transition")

        agent_skills = [
            attrs
            for _tag, attrs in parser.start_tags
            if "data-agent-skill" in attrs
        ]
        if len(agent_skills) != 1:
            errors.append(f"{relative}: expected exactly one Agent Skill component")

        automation_workflows = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "ol" and "data-automation-workflow" in attrs
        ]
        if len(automation_workflows) != 1:
            errors.append(f"{relative}: expected exactly one automated workflow list")

        workflow_steps = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "li" and "data-workflow-step" in attrs
        ]
        if len(workflow_steps) != 4:
            errors.append(f"{relative}: expected exactly four automated workflow steps")

        home_prompt = parser.textareas.get("home-setup-prompt", "")
        setup_parser = pages.get(contract["prompt_source"].resolve())
        setup_prompt = (
            setup_parser.textareas.get("setup-prompt-text", "") if setup_parser else ""
        )
        if not home_prompt:
            errors.append(f"{relative}: hidden Agent prompt is missing")
        elif home_prompt != setup_prompt:
            errors.append(f"{relative}: Agent prompt drifted from the localized setup guide")

        buttons = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "button" and attrs.get("id") == "copy-agent-prompt"
        ]
        if len(buttons) != 1:
            errors.append(f"{relative}: expected exactly one copy-to-Agent button")

        toggles = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "button" and attrs.get("id") == "toggle-agent-prompt"
        ]
        if len(toggles) != 1:
            errors.append(f"{relative}: expected exactly one Agent-prompt expand control")
        elif (
            toggles[0].get("aria-expanded") != "false"
            or toggles[0].get("aria-controls") != "home-prompt-preview-text"
            or not toggles[0].get("data-expand-label")
            or not toggles[0].get("data-collapse-label")
        ):
            errors.append(f"{relative}: Agent-prompt expand control lost its state contract")

        previews = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "pre" and attrs.get("id") == "home-prompt-preview-text"
        ]
        if len(previews) != 1 or previews[0].get("tabindex") != "0":
            errors.append(f"{relative}: visible Agent-prompt preview is missing or not focusable")

        prompt_sources = [
            attrs
            for tag, attrs in parser.start_tags
            if tag == "textarea" and attrs.get("id") == "home-setup-prompt"
        ]
        if len(prompt_sources) != 1 or "hidden" not in prompt_sources[0]:
            errors.append(f"{relative}: long Agent prompt must remain hidden on the landing page")

        statuses = [
            attrs
            for _tag, attrs in parser.start_tags
            if attrs.get("id") == "home-copy-status"
        ]
        if len(statuses) != 1:
            errors.append(f"{relative}: copy status region is missing")
        else:
            if statuses[0].get("data-success") != contract["success"]:
                errors.append(f"{relative}: localized copy success text is incorrect")
            if statuses[0].get("data-failure") != contract["failure"]:
                errors.append(f"{relative}: localized copy failure text is incorrect")

        empty_slots = [
            attrs
            for _tag, attrs in parser.start_tags
            if attrs.get("data-video-state") == "empty"
        ]
        if len(empty_slots) != 4:
            errors.append(f"{relative}: expected four explicitly empty walkthrough video slots")
        media_tags = {"video", "iframe", "source", "track"}
        if any(tag in media_tags for tag, _attrs in parser.start_tags):
            errors.append(f"{relative}: empty walkthrough slots must not claim playable media")

        try:
            how_index = parser.ids.index("how-it-works")
            video_index = parser.ids.index("video-series")
        except ValueError:
            errors.append(f"{relative}: fold teaser or video-series anchor is missing")
        else:
            if how_index >= video_index:
                errors.append(f"{relative}: How it works teaser must precede all video slots")

        scripts = [
            attrs.get("src", "")
            for tag, attrs in parser.start_tags
            if tag == "script" and attrs.get("src")
        ]
        if "/landing.js" not in scripts:
            errors.append(f"{relative}: shared landing copy behavior is missing")


def validate_vercel_routes(errors: list[str]) -> None:
    config_path = SITE_ROOT / "vercel.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"vercel.json: parse failed: {exc}")
        return

    actual = {
        (rewrite.get("source"), rewrite.get("destination"))
        for rewrite in config.get("rewrites", [])
        if isinstance(rewrite, dict)
    }
    expected = {
        ("/install", "/index.html"),
        ("/zh/install", "/zh/index.html"),
    }
    if not expected.issubset(actual):
        errors.append(f"vercel.json: missing canonical install rewrites: {sorted(expected - actual)}")

    shadowing_files = (
        SITE_ROOT / "install" / "index.html",
        SITE_ROOT / "zh" / "install" / "index.html",
    )
    for path in shadowing_files:
        if path.exists():
            errors.append(
                f"{path.relative_to(SITE_ROOT)}: static file shadows the canonical install rewrite"
            )


def validate_discovery_files(errors: list[str]) -> None:
    sitemap_path = SITE_ROOT / "sitemap.xml"
    try:
        root = ET.parse(sitemap_path).getroot()
    except (OSError, ET.ParseError) as exc:
        errors.append(f"sitemap.xml: parse failed: {exc}")
        return

    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "xhtml": "http://www.w3.org/1999/xhtml",
    }
    localized_urls = {
        f"{BASE_URL}/install",
        f"{BASE_URL}/zh/install",
        f"{BASE_URL}/setup",
        f"{BASE_URL}/zh/setup",
    }
    found: dict[str, dict[str, str]] = {}
    for url in root.findall("sm:url", ns):
        loc = url.findtext("sm:loc", default="", namespaces=ns)
        if loc in localized_urls:
            found[loc] = {
                link.attrib.get("hreflang", ""): link.attrib.get("href", "")
                for link in url.findall("xhtml:link", ns)
            }
    expected_install_alternates = {
        "en": f"{BASE_URL}/install",
        "zh-CN": f"{BASE_URL}/zh/install",
        "x-default": f"{BASE_URL}/install",
    }
    expected_setup_alternates = {
        "en": f"{BASE_URL}/setup",
        "zh-CN": f"{BASE_URL}/zh/setup",
        "x-default": f"{BASE_URL}/setup",
    }
    if set(found) != localized_urls:
        errors.append(f"sitemap.xml: missing localized URLs: {sorted(localized_urls - set(found))}")
    for loc in (f"{BASE_URL}/install", f"{BASE_URL}/zh/install"):
        if found.get(loc) != expected_install_alternates:
            errors.append(
                f"sitemap.xml: incorrect install alternates for {loc}: {found.get(loc)!r}"
            )
    for loc in (f"{BASE_URL}/setup", f"{BASE_URL}/zh/setup"):
        if found.get(loc) != expected_setup_alternates:
            errors.append(
                f"sitemap.xml: incorrect setup alternates for {loc}: {found.get(loc)!r}"
            )

    llms_text = (SITE_ROOT / "llms.txt").read_text(encoding="utf-8")
    if f"{BASE_URL}/zh/install" not in llms_text:
        errors.append("llms.txt: localized install URL is missing")
    if f"{BASE_URL}/zh/setup" not in llms_text:
        errors.append("llms.txt: localized setup guide URL is missing")


def main() -> int:
    pages, errors = load_pages()
    validate_links(pages, errors)
    validate_github_link_behavior(pages, errors)
    validate_setup_contracts(pages, errors)
    validate_home_contracts(pages, errors)
    validate_vercel_routes(errors)
    validate_discovery_files(errors)

    if errors:
        print("Static site validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Validated {len(pages)} HTML pages, localized landing/setup contracts, "
        "Vercel routes, links, GitHub new-window behavior, JSON-LD, and sitemap entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
