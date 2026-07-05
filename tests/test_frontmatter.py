"""Validate SKILL.md frontmatter without requiring a YAML dependency."""

from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "todo-audit-skill" / "SKILL.md"
REQUIRED_KEYS = {"name", "description", "user-invocable", "disable-model-invocation"}


def _frontmatter(text: str) -> str:
    assert text.startswith("---"), "SKILL.md must open with a YAML frontmatter fence"
    end = text.index("\n---", 3)
    return text[3:end]


def test_skill_md_exists() -> None:
    assert SKILL.exists()


def test_frontmatter_has_required_keys() -> None:
    block = _frontmatter(SKILL.read_text(encoding="utf-8"))
    keys = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            keys.add(line.split(":", 1)[0].strip())
    missing = REQUIRED_KEYS - keys
    assert not missing, f"SKILL.md frontmatter missing keys: {missing}"
