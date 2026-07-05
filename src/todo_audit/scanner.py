"""Codebase traversal + orchestration: find TODOs and resolve their scope."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Protocol

from .comments import LangSyntax, find_markers, syntax_for
from .models import Scope, Todo
from .scope_generic import GenericScoper
from .scope_python import PythonScoper


class _Scoper(Protocol):
    """Anything that can resolve a line number to a code scope."""

    def scope_of(self, line: int) -> Scope: ...


# Directory names never descended into, independent of .gitignore.
DEFAULT_DENYLIST = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".egg-info",
    ".tox",
    ".idea",
    ".vscode",
}

_PY_EXTS = {".py", ".pyi"}


class _ModuleOnlyScoper:
    """Fallback used when no structural parser applies: everything is module-level."""

    def scope_of(self, line: int) -> Scope:  # noqa: D401 - trivial
        return Scope.MODULE


def _make_scoper(ext: str, source: str, syntax: LangSyntax) -> _Scoper:
    if ext.lower() in _PY_EXTS:
        scoper = PythonScoper(source)
        return scoper if scoper.usable else _ModuleOnlyScoper()
    if syntax.block == ("/*", "*/"):  # C-family / JS / TS
        return GenericScoper(source, syntax)
    return _ModuleOnlyScoper()


def scan_file(path: str, root: Optional[str] = None) -> List[Todo]:
    """Scan one file. ``root`` sets the base for the reported relative path."""
    p = Path(path)
    syntax = syntax_for(p.suffix)
    if syntax is None:
        return []
    try:
        source = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    rel = os.path.relpath(str(p), root) if root else str(p)
    scoper = _make_scoper(p.suffix, source, syntax)

    todos: List[Todo] = []
    for line_no, todo_type, desc in find_markers(source, syntax):
        todos.append(
            Todo(
                file=rel,
                line=line_no,
                type=todo_type,
                scope=scoper.scope_of(line_no),
                description=desc,
            )
        )
    return todos


def _load_gitignore_spec(root: Path) -> Optional[Any]:
    """Return a pathspec matcher for the root .gitignore, or None if unavailable."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return None
    try:
        import pathspec  # optional dependency
    except ImportError:
        return None
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    # "gitignore" is the modern factory; fall back for older pathspec releases.
    try:
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except (KeyError, ValueError):
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def scan_path(root: str) -> List[Todo]:
    """Walk ``root`` recursively and return all TODOs, honoring ignore rules."""
    root_path = Path(root).resolve()
    spec = _load_gitignore_spec(root_path)
    todos: List[Todo] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # prune denylisted directories in place
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_DENYLIST]
        if spec is not None:
            dirnames[:] = [
                d for d in dirnames if not spec.match_file(os.path.relpath(os.path.join(dirpath, d), root_path) + "/")
            ]
        for name in filenames:
            full = Path(dirpath) / name
            rel = os.path.relpath(str(full), root_path)
            if spec is not None and spec.match_file(rel):
                continue
            todos.extend(scan_file(str(full), root=str(root_path)))

    return todos
