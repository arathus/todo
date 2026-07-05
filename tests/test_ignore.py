"""Traversal honors the built-in denylist and .gitignore (when pathspec is present)."""

import importlib.util
from pathlib import Path

import pytest

from todo_audit import scan_path

_HAS_PATHSPEC = importlib.util.find_spec("pathspec") is not None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_denylisted_dir_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "node_modules" / "dep.py", "# TODO: ignore me\n")
    files = {t.file for t in scan_path(str(tmp_path))}
    assert "keep.py" in files
    assert not any("node_modules" in f for f in files)


@pytest.mark.skipif(not _HAS_PATHSPEC, reason="pathspec not installed")
def test_gitignore_skipped(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "secret/\n")
    _write(tmp_path / "keep.py", "# TODO: keep me\n")
    _write(tmp_path / "secret" / "hidden.py", "# TODO: hidden\n")
    files = {t.file for t in scan_path(str(tmp_path))}
    assert "keep.py" in files
    assert not any("secret" in f for f in files)
