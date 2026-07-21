# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".agents" / "skills"
ALLOWED_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "argument-hint",
}
PRIVATE_MARKERS = [
    "U" + "CI",
    "xian" + "zh",
    "tao" + ".for",
    "@u" + "ci",
    "gmail" + ".com",
    "proton" + ".me",
]


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def frontmatter_lines(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return [], [f"{path.parent.name}: frontmatter is missing"]

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end = index
            break
    if end is None:
        errors.append(f"{path.parent.name}: frontmatter is not closed")
        return [], errors
    return lines[1:end], errors


def check_skill(path: Path) -> list[str]:
    skill = path.parent.name
    frontmatter, errors = frontmatter_lines(path)
    if errors:
        return errors

    values: dict[str, str] = {}
    for line_number, line in enumerate(frontmatter, start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            errors.append(f"{skill}: frontmatter line {line_number} is missing ':'")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in ALLOWED_KEYS:
            errors.append(f"{skill}: frontmatter key '{key}' is not allowed")
        if key in values:
            errors.append(f"{skill}: frontmatter key '{key}' is duplicated")
        values[key] = value.strip()

    name = unquote(values.get("name", ""))
    if not name:
        errors.append(f"{skill}: name is missing")
    elif name != skill:
        errors.append(f"{skill}: name '{name}' does not match directory '{skill}'")

    if "description" not in values:
        errors.append(f"{skill}: description is missing")
        return errors

    raw_description = values["description"]
    if not raw_description:
        errors.append(f"{skill}: description is empty")
        return errors
    block_scalar_header = raw_description.split("#", 1)[0].strip()
    if block_scalar_header in {"|", ">", "|-", ">-", "|+", ">+"}:
        errors.append(f"{skill}: description must be a one-line string")
        return errors

    description = unquote(raw_description)
    if "\n" in description or "\r" in description:
        errors.append(f"{skill}: description must be one line")
    if len(description) > 320:
        errors.append(f"{skill}: description is {len(description)} characters, max is 320")
    if "<" in description or ">" in description:
        errors.append(f"{skill}: description contains '<' or '>'")

    description_lower = description.lower()
    for marker in PRIVATE_MARKERS:
        if marker.lower() in description_lower:
            errors.append(f"{skill}: description contains private marker '{marker}'")

    return errors


def main() -> int:
    if not SKILLS_DIR.exists():
        print("Skill frontmatter tests FAIL")
        print(f"- .agents/skills directory not found at {SKILLS_DIR}")
        return 1

    errors: list[str] = []
    skill_paths: list[Path] = []
    for directory in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        skill_path = directory / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"{directory.name}: SKILL.md is missing")
            continue
        skill_paths.append(skill_path)
        errors.extend(check_skill(skill_path))

    if errors:
        print("Skill frontmatter tests FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Skill frontmatter tests PASS ({len(skill_paths)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
