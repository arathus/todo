"""Command-line entrypoint. Emits scanner facts as JSON for the skill to consume.

The skill (SKILL.md) shells out to ``todo-audit scan`` and interprets the JSON:
difficulty ranking, fix suggestions, consolidation, and clarifying questions are
all done by the model, not here.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .report import sort_todos
from .scanner import scan_path


def _cmd_scan(args: argparse.Namespace) -> int:
    todos = sort_todos(scan_path(args.root))
    payload = {
        "root": args.root,
        "count": len(todos),
        "todos": [t.to_dict() for t in todos],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


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
