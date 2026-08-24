"""Codebase traversal + orchestration: find TODOs and resolve their scope."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Protocol

from .comments import LangSyntax, find_markers, syntax_for
from .ignore import GitignoreIndex
from .models import Scope, ScopeInfo, Todo
from .scope_generic import GenericScoper
from .scope_python import PythonScoper


class _Scoper(Protocol):
    """Anything that can resolve a line number to a code scope."""

    def resolve(self, line: int) -> ScopeInfo: ...


# Directories holding third-party code. These are never scanned and never
# reported: an audit is about what the user wrote, not what they installed.
# Their presence anywhere in a path marks that path as dependency code.
VENDOR_DIRS = {
    # Python
    ".venv",
    "venv",
    "virtualenv",
    ".virtualenvs",
    ".direnv",
    ".tox",
    ".nox",
    ".eggs",
    "site-packages",
    "dist-packages",
    # JavaScript / TypeScript
    "node_modules",
    "bower_components",
    ".yarn",
    ".pnpm-store",
    # Go, PHP, Ruby
    "vendor",
    # Swift / Objective-C
    "Pods",
    "Carthage",
    # JVM, Rust, infrastructure
    ".m2",
    ".gradle",
    ".cargo",
    ".terraform",
    # vendored source trees
    "third_party",
}

# Directories holding generated output, caches, or tool metadata. Pruned during
# traversal, but harmless to name as an explicit scan root.
GENERATED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
    ".parcel-cache",
    ".turbo",
    "dist",
    "build",
    "_build",
    "deps",
    "target",
    "coverage",
    "htmlcov",
    ".nyc_output",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".astro",
    ".output",
    ".serverless",
    ".idea",
    ".vscode",
}

# Directory names never descended into, independent of .gitignore.
DEFAULT_DENYLIST = VENDOR_DIRS | GENERATED_DIRS

# Directory name suffixes never descended into (e.g. ``mypkg.egg-info``).
DENIED_DIR_SUFFIXES = (".egg-info",)

# A directory containing this file is a Python virtual environment, whatever it
# happens to be named — `env/`, `myenv/`, and `.venv/` are all caught by it.
VENV_MARKER = "pyvenv.cfg"

# Machine-generated files. Nobody wrote these by hand, so nobody can act on a
# TODO found inside one.
DENIED_FILE_SUFFIXES = (
    ".min.js",
    ".min.mjs",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    "_pb2.py",
    "_pb2_grpc.py",
    ".pb.go",
    ".pb.cc",
    ".pb.h",
    ".g.dart",
)

# Files larger than this are skipped: at that size it is a bundle, a generated
# artifact, or a data blob, and reading it costs far more than it can yield.
MAX_FILE_BYTES = 5 * 1024 * 1024

_PY_EXTS = {".py", ".pyi"}


def is_denied_dir(name: str) -> bool:
    """Whether a directory of this name should never be descended into."""
    return name in DEFAULT_DENYLIST or name.endswith(DENIED_DIR_SUFFIXES)


def is_denied_file(name: str) -> bool:
    """Whether this file is machine-generated and so not worth auditing."""
    return name.endswith(DENIED_FILE_SUFFIXES)


def is_virtualenv(path: Path) -> bool:
    """Whether ``path`` is the root of a Python virtual environment."""
    return (path / VENV_MARKER).is_file()


def is_dependency_path(path: Path) -> bool:
    """Whether ``path`` lies inside third-party code rather than the user's own.

    Used to refuse a scan root such as ``site-packages`` or ``.venv``. Only the
    unambiguous vendor markers count here: a project directory that happens to
    be named ``build`` is still the user's code and must remain scannable.
    """
    try:
        resolved = path.resolve()
    except OSError:  # pragma: no cover - resolve() is effectively total here
        return False
    if any(part in VENDOR_DIRS for part in resolved.parts):
        return True
    return any(is_virtualenv(ancestor) for ancestor in (resolved, *resolved.parents))


class _ModuleOnlyScoper:
    """Fallback used when no structural parser applies: everything is module-level."""

    def resolve(self, line: int) -> ScopeInfo:  # noqa: D401 - trivial
        return ScopeInfo(Scope.MODULE, None)


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
        if p.stat().st_size > MAX_FILE_BYTES:
            return []
        raw = p.read_bytes()
    except (OSError, ValueError):
        return []

    if b"\x00" in raw:
        # NUL bytes mean this is binary data wearing a source extension
        return []
    # Decode leniently: a single stray byte in a latin-1 file must not silently
    # discard every TODO in it.
    source = raw.decode("utf-8", errors="replace")

    hits = find_markers(source, syntax)
    if not hits:
        # Most files hold no markers at all; parsing them for scope is pure waste.
        return []

    rel = os.path.relpath(str(p), root) if root else str(p)
    scoper = _make_scoper(p.suffix, source, syntax)

    todos: List[Todo] = []
    for hit in hits:
        info = scoper.resolve(hit.line)
        todos.append(
            Todo(
                file=rel,
                line=hit.line,
                type=hit.type,
                scope=info.scope,
                description=hit.description,
                marker=hit.marker,
                symbol=info.symbol,
                assignee=hit.assignee,
            )
        )
    return todos


def _rel_dir(dirpath: str, root: Path) -> str:
    """POSIX path of ``dirpath`` relative to ``root``; ``""`` for the root itself."""
    rel = os.path.relpath(dirpath, root)
    return "" if rel == "." else Path(rel).as_posix()


def scan_path(root: str) -> List[Todo]:
    """Walk ``root`` recursively and return all TODOs, honoring ignore rules.

    ``.gitignore`` files are respected at every level, not just the root, with
    the closest file winning — the same precedence git itself applies.
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        # Reporting "0 TODOs, all good" for a mistyped path is a silent lie.
        raise FileNotFoundError(f"no such file or directory: {root}")
    if root_path.is_file():
        # Pointing at a single file is a reasonable thing to ask for.
        if is_dependency_path(root_path.parent):
            return []
        return scan_file(str(root_path), root=str(root_path.parent))
    if is_dependency_path(root_path):
        # Auditing installed packages is never the intent; see the CLI, which
        # explains the refusal rather than reporting an empty result.
        return []

    ignores = GitignoreIndex()
    todos: List[Todo] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        rel_dir = _rel_dir(dirpath, root_path)
        ignores.load_dir(rel_dir, Path(dirpath))

        # prune denylisted and ignored directories in place, in stable order
        kept: List[str] = []
        for name in sorted(dirnames):
            if is_denied_dir(name) or is_virtualenv(Path(dirpath) / name):
                continue
            if ignores.is_ignored(f"{rel_dir}/{name}" if rel_dir else name, is_dir=True):
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in sorted(filenames):
            if is_denied_file(name):
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if ignores.is_ignored(rel):
                continue
            todos.extend(scan_file(str(Path(dirpath) / name), root=str(root_path)))

    return todos
