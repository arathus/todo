"""Command-line entrypoint. Emits scanner facts as JSON for the skill to consume.

The skill (SKILL.md) shells out to ``todo-audit scan`` and interprets the JSON:
difficulty ranking, fix suggestions, consolidation, and clarifying questions are
all done by the model, not here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Todo
from .report import DIFFICULTY_LABELS, FIX_KINDS, SEVERITY_ORDER, sort_todos
from .scanner import is_dependency_path, scan_path

# Exit codes: 0 success, 1 reserved for future use, 2 refused/unusable input.
EXIT_OK = 0
EXIT_REFUSED = 2

_NO_PATHSPEC_WARNING = (
    "note: .gitignore rules were NOT applied — the optional 'pathspec' package "
    "is missing for this interpreter. Install it with: "
    "python3 -m pip install pathspec"
)

_DEPENDENCY_ROOT_ERROR = (
    "error: {root} is third-party code (a virtual environment, site-packages, "
    "node_modules, vendor, or similar). This tool audits only code written by "
    "the user. Point it at your project root instead."
)


def _warn_if_gitignore_unenforced(root: str) -> None:
    """Say so on stderr when a .gitignore exists but cannot be honored.

    Without this the scan silently reports TODOs from ignored directories, which
    reads as a scanner bug rather than a missing optional dependency.
    """
    if importlib.util.find_spec("pathspec") is not None:
        return
    if not (Path(root) / ".gitignore").is_file():
        return
    print(_NO_PATHSPEC_WARNING, file=sys.stderr)


def _summary(todos: List[Todo]) -> Dict[str, Any]:
    """Counts the model can prioritize from without walking the whole array."""
    return {
        "by_type": {t.value: sum(1 for todo in todos if todo.type is t) for t in SEVERITY_ORDER},
        "by_scope": dict(Counter(todo.scope.value for todo in todos)),
        "by_marker": dict(Counter(todo.marker for todo in todos)),
        "files": len({todo.file for todo in todos}),
    }


def _vocabulary() -> Dict[str, Any]:
    """The grading vocabulary, so prose copies cannot drift from the code."""
    return {
        "difficulty": {str(level): label for level, label in DIFFICULTY_LABELS.items()},
        "fix_kinds": list(FIX_KINDS),
        "severity_order": [t.value for t in SEVERITY_ORDER],
    }


def _cmd_scan(args: argparse.Namespace) -> int:
    if is_dependency_path(Path(args.root)):
        print(_DEPENDENCY_ROOT_ERROR.format(root=args.root), file=sys.stderr)
        return EXIT_REFUSED
    _warn_if_gitignore_unenforced(args.root)
    try:
        todos = sort_todos(scan_path(args.root))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    payload = {
        "root": args.root,
        "count": len(todos),
        "summary": _summary(todos),
        "vocabulary": _vocabulary(),
        "todos": [t.to_dict() for t in todos],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo-audit", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a codebase and print TODO facts as JSON.")
    scan.add_argument("root", nargs="?", default=".", help="Project root (default: .)")
    scan.set_defaults(func=_cmd_scan)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
