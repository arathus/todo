#!/usr/bin/env python3
"""Scan-throughput benchmark over generated Python and JavaScript corpora.

The corpora are synthesised rather than borrowed from a virtual environment: the
scanner refuses dependency directories outright, so measuring against installed
packages would time something the tool is never asked to do.

    uv run poe bench            # human-readable report
    uv run poe bench -- --json  # machine-readable, for the guard test

Throughput is reported in MB/s of source scanned, which is stable across
machines in a way that wall-clock totals are not.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from todo_audit.scanner import scan_path  # noqa: E402

# One file in five carries a marker, matching what real trees look like.
MARKED_EVERY = 5

PY_TEMPLATE = '''"""Module {n}: generated benchmark fixture."""

import os
import re

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BANNER = "a string with a / slash and a # hash inside it"


class Widget{n}:
    """A docstring that mentions nothing in particular."""

    def __init__(self, options=None):
        self.options = options or {{}}
        self.count = 0
{marker}
    def validate(self, keys):
        for key in keys:
            if not SLUG_RE.match(key):
                raise ValueError(f"bad key {{key}}")
        return True

    def render(self, parts) -> str:
        ratio = len(parts) / max(self.count, 1)
        return os.path.join(*parts) + str(ratio)


def build{n}(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None
'''

JS_TEMPLATE = """import {{ helper }} from './helper';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const URL_RE = /https:\\/\\/[^\\s]+/g;

export class Widget{n} {{
{marker}
  count = 0;

  constructor(options) {{
    this.options = options || {{}};
    if (this.options.strict) {{
      this.validate();
    }}
  }}

  validate() {{
    for (const key of Object.keys(this.options)) {{
      if (!SLUG_RE.test(key)) {{
        throw new Error(`bad key ${{key}}`);
      }}
    }}
  }}

  render(input) {{
    const parts = input.split('/').filter(Boolean);
    const ratio = parts.length / this.count;
    return parts.map((p) => p.replace(URL_RE, '')).join('/') + ratio;
  }}
}}

export function build{n}(a, b) {{
  try {{
    return helper(a) / helper(b);
  }} catch (err) {{
    return null;
  }}
}}
"""

CORPORA: Tuple[Tuple[str, str, str, str], ...] = (
    ("python", ".py", PY_TEMPLATE, "    #"),
    ("javascript", ".js", JS_TEMPLATE, "  //"),
)


def build_corpus(root: Path, suffix: str, template: str, comment: str, count: int) -> int:
    """Write ``count`` files and return the total byte size."""
    root.mkdir(parents=True, exist_ok=True)
    total = 0
    for n in range(count):
        marker = f"{comment} !TODO: widget {n} needs a default count" if n % MARKED_EVERY == 0 else ""
        body = template.format(n=n, marker=marker)
        (root / f"mod{n}{suffix}").write_text(body, encoding="utf-8")
        total += len(body.encode("utf-8"))
    return total


def measure(root: Path, runs: int) -> Tuple[float, int]:
    """Best-of-``runs`` wall time, plus the marker count for a sanity check."""
    best = float("inf")
    found = 0
    for _ in range(runs):
        started = time.perf_counter()
        todos = scan_path(str(root))
        best = min(best, time.perf_counter() - started)
        found = len(todos)
    return best, found


def run(files: int, runs: int) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    workspace = Path(tempfile.mkdtemp(prefix="todo-audit-bench-"))
    try:
        for name, suffix, template, comment in CORPORA:
            root = workspace / name
            size = build_corpus(root, suffix, template, comment, files)
            seconds, found = measure(root, runs)
            results.append(
                {
                    "corpus": name,
                    "files": files,
                    "megabytes": round(size / 1_000_000, 2),
                    "seconds": round(seconds, 3),
                    "mb_per_second": round(size / 1_000_000 / seconds, 1),
                    "markers": found,
                }
            )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return results


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=2000, help="files per corpus (default: 2000)")
    parser.add_argument("--runs", type=int, default=2, help="timed runs; the best is reported (default: 2)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    results = run(args.files, args.runs)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print(f"{'corpus':<12}{'files':>7}{'MB':>8}{'seconds':>10}{'MB/s':>9}{'markers':>9}")
    for row in results:
        print(
            f"{row['corpus']:<12}{row['files']:>7}{row['megabytes']:>8}"
            f"{row['seconds']:>10}{row['mb_per_second']:>9}{row['markers']:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
