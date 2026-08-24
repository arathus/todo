#!/usr/bin/env python3
"""Propagate ``todo_audit.__version__`` to the JSON manifests.

The Python package version is the single source of truth: ``pyproject.toml``
reads it dynamically, and this script rewrites the two manifests that cannot.
Run with ``--check`` to verify instead of write (used by the test suite and CI).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
INIT = REPO / "src" / "todo_audit" / "__init__.py"
MANIFESTS = (REPO / "package.json", REPO / ".claude-plugin" / "plugin.json")

_VERSION_RE = re.compile(r'^__version__\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)


def source_version() -> str:
    """Read ``__version__`` textually, so no import of the package is needed."""
    match = _VERSION_RE.search(INIT.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"no __version__ found in {INIT}")
    return match.group("version")


def manifest_versions() -> List[Tuple[Path, str]]:
    return [(path, str(json.loads(path.read_text(encoding="utf-8")).get("version", ""))) for path in MANIFESTS]


def write(path: Path, version: str) -> None:
    """Rewrite only the version line, preserving the file's own formatting."""
    text = path.read_text(encoding="utf-8")
    updated = re.sub(r'("version"\s*:\s*)"[^"]*"', rf'\1"{version}"', text, count=1)
    path.write_text(updated, encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only; do not write")
    args = parser.parse_args(argv)

    version = source_version()
    stale = [(path, found) for path, found in manifest_versions() if found != version]

    if not stale:
        print(f"version {version} is in sync")
        return 0
    if args.check:
        for path, found in stale:
            print(f"{path.relative_to(REPO)}: {found or '<missing>'} != {version}", file=sys.stderr)
        print("run `uv run poe sync-version` to fix", file=sys.stderr)
        return 1
    for path, _ in stale:
        write(path, version)
        print(f"updated {path.relative_to(REPO)} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
