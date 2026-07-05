"""Verify the Node installer copies assets into HOME/.claude/skills/."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
INSTALLER = REPO / "bin" / "installer.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_installer_copies_skill(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"]}
    result = subprocess.run(
        ["node", str(INSTALLER)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    target = tmp_path / ".claude" / "skills" / "todo-audit-skill"
    assert (target / "SKILL.md").exists()
    assert (target / "src" / "todo_audit" / "scanner.py").exists()
    assert (target / "commands" / "todo" / "audit.md").exists()
