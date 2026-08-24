"""The Node installer must put each asset where Claude Code actually reads it."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

import pytest

REPO = Path(__file__).parent.parent
INSTALLER = REPO / "bin" / "installer.js"

_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _install(home: Path) -> Tuple[subprocess.CompletedProcess[str], Path, Path]:
    result = subprocess.run(
        ["node", str(INSTALLER)],
        cwd=str(REPO),
        env={"HOME": str(home), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    return result, home / ".claude" / "skills" / "todo-audit-skill", home / ".claude" / "commands" / "todo"


@_needs_node
def test_installer_places_the_skill_and_the_engine(tmp_path: Path) -> None:
    result, skill_dir, _ = _install(tmp_path)
    assert result.returncode == 0, f"the installer must exit 0 so `npm install` is never failed by it\n{result.stderr}"
    assert (skill_dir / "SKILL.md").is_file(), "without SKILL.md Claude Code cannot load the skill at all"
    assert (skill_dir / "src" / "todo_audit" / "scanner.py").is_file(), (
        "the engine must ship alongside the skill; the documented PYTHONPATH fallback points at this src/ tree"
    )


@_needs_node
def test_commands_are_installed_where_they_are_discovered(tmp_path: Path) -> None:
    _, skill_dir, command_dir = _install(tmp_path)
    for name in ("audit.md", "fix.md", "analyze.md"):
        assert (command_dir / name).is_file(), (
            f"{name} must land in ~/.claude/commands/todo/ to register as /todo:{name[:-3]}"
        )
    assert not (skill_dir / "commands").exists(), (
        "command files nested inside a skill directory are not discovered as slash commands, "
        "so installing them there would silently provide no commands at all"
    )


@_needs_node
def test_installer_does_not_ship_python_build_artifacts(tmp_path: Path) -> None:
    _, skill_dir, _ = _install(tmp_path)
    stowaways = [
        p.relative_to(skill_dir)
        for p in skill_dir.rglob("*")
        if p.suffix == ".pyc" or "__pycache__" in p.parts or p.name.endswith(".egg-info")
    ]
    assert stowaways == [], f"build artifacts must not reach an installed skill; found {stowaways}"


@_needs_node
def test_reinstall_removes_files_dropped_by_an_earlier_release(tmp_path: Path) -> None:
    _, skill_dir, command_dir = _install(tmp_path)
    stale_module = skill_dir / "src" / "todo_audit" / "removed_in_a_later_release.py"
    stale_command = command_dir / "retired.md"
    stale_module.write_text("# leftover\n", encoding="utf-8")
    stale_command.write_text("# leftover\n", encoding="utf-8")

    _install(tmp_path)
    assert not stale_module.exists(), "a module removed upstream must not survive an upgrade"
    assert not stale_command.exists(), "a command removed upstream must not keep answering /todo:retired"


@_needs_node
def test_installer_reports_on_the_python_interpreter(tmp_path: Path) -> None:
    result, _, _ = _install(tmp_path)
    combined = result.stdout + result.stderr
    assert "python" in combined.lower(), (
        "the engine needs python3 at audit time, so its absence or version must surface at install time"
    )
