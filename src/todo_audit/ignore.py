"""Nested ``.gitignore`` support.

Git applies a ``.gitignore`` to its own directory and everything below it, and
the closest file wins. This module mirrors that: every directory visited during
the walk contributes its own rules, and a path is judged against the deepest
``.gitignore`` that has an opinion about it.

Requires the optional ``pathspec`` extra; without it nothing is ignored here and
traversal falls back to the built-in directory denylist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, cast


def _load_spec(gitignore: Path) -> Optional[Any]:
    """Compile one ``.gitignore`` file, or return None if it cannot be used."""
    try:
        import pathspec  # optional dependency
    except ImportError:
        return None
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    # "gitignore" is the modern factory; fall back for older pathspec releases.
    try:
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except (KeyError, ValueError):
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _verdict(spec: Any, rel: str) -> Optional[bool]:
    """True = ignored, False = explicitly re-included, None = no rule matched."""
    check = getattr(spec, "check_file", None)
    if check is not None:
        return cast(Optional[bool], check(rel).include)
    # Older pathspec: a non-match and a negated match are indistinguishable, so
    # report "no opinion" and let a shallower .gitignore decide.
    return True if spec.match_file(rel) else None


def _ancestor_dirs(rel_path: str) -> List[str]:
    """Directories whose ``.gitignore`` can govern ``rel_path``, deepest first.

    ``"a/b/c.py"`` -> ``["a/b", "a", ""]`` (``""`` is the scan root).
    """
    parts = rel_path.split("/")[:-1]
    return ["/".join(parts[:depth]) for depth in range(len(parts), -1, -1)]


class GitignoreIndex:
    """Accumulates ``.gitignore`` rules as a top-down walk descends."""

    def __init__(self) -> None:
        self._specs: Dict[str, Any] = {}  # directory relative to root ("" = root)

    def load_dir(self, rel_dir: str, abs_dir: Path) -> None:
        """Register the ``.gitignore`` in ``abs_dir``, if there is one."""
        gitignore = abs_dir / ".gitignore"
        if not gitignore.is_file():
            return
        spec = _load_spec(gitignore)
        if spec is not None:
            self._specs[rel_dir] = spec

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Whether ``rel_path`` (POSIX, relative to the scan root) is ignored."""
        if not self._specs:
            return False
        target = rel_path + "/" if is_dir else rel_path
        for rel_dir in _ancestor_dirs(rel_path):
            spec = self._specs.get(rel_dir)
            if spec is None:
                continue
            sub = target[len(rel_dir) + 1 :] if rel_dir else target
            verdict = _verdict(spec, sub)
            if verdict is not None:
                return verdict
        return False
