"""A throughput guard, so a performance collapse fails the build.

Absolute MB/s would be flaky: CI runners vary by several times. Instead the scan
is measured against a fixed pure-Python loop timed in the same process, which
cancels out machine speed. The budget below is therefore a *ratio*, not a time.

This catches a collapse — the kind where a per-character call sneaks into the
hot loop — not a few percent of drift. Use ``uv run poe bench`` for that, and
compare against the figures recorded in README.md.
"""

import sys
import time
from pathlib import Path
from typing import Tuple

import pytest

from todo_audit.scanner import scan_path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from benchmark import JS_TEMPLATE, PY_TEMPLATE, build_corpus  # noqa: E402


def _coverage_is_tracing() -> bool:
    """Whether a line tracer is installed, which invalidates the measurement.

    Coverage costs far more per bytecode line than per reference-loop iteration,
    so a scan measured under it looks several times slower than it is. Rather
    than inflate the budget until it means nothing, the guard steps aside and
    runs as its own task (``uv run poe perf``).
    """
    if sys.gettrace() is not None:
        return True
    monitoring = getattr(sys, "monitoring", None)
    coverage_id = getattr(monitoring, "COVERAGE_ID", None)
    if monitoring is not None and coverage_id is not None:
        return monitoring.get_tool(coverage_id) is not None
    return False


pytestmark = pytest.mark.skipif(
    _coverage_is_tracing(),
    reason="coverage tracing distorts the timing; run `uv run poe perf` instead",
)

FILES = 300

# Reference units per megabyte of source, measured on the development machine at
# this corpus size: Python ≈ 6.5, JavaScript ≈ 10.2. The budgets allow ~2.5x
# headroom, which absorbs a slow or noisy runner while still failing on a real
# collapse. Re-measure with `uv run poe bench` before changing them.
BUDGETS = {"python": 17.0, "javascript": 26.0}


def _reference_seconds() -> float:
    """Time a fixed integer loop, as a proxy for this machine's Python speed."""
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        total = 0
        for i in range(1_000_000):
            total += i & 7
        best = min(best, time.perf_counter() - started)
    assert total >= 0, "the reference loop must actually run"
    return best


def _scan_cost(root: Path) -> Tuple[float, float]:
    """Best-of-three scan seconds, and the corpus size in megabytes."""
    megabytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) / 1_000_000
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        scan_path(str(root))
        best = min(best, time.perf_counter() - started)
    return best, megabytes


@pytest.mark.parametrize(
    ("corpus", "suffix", "template", "comment"),
    [
        ("python", ".py", PY_TEMPLATE, "    #"),
        ("javascript", ".js", JS_TEMPLATE, "  //"),
    ],
    ids=["python", "javascript"],  # the templates are multi-line; keep ids readable
)
def test_scan_throughput_stays_within_budget(
    tmp_path: Path, corpus: str, suffix: str, template: str, comment: str
) -> None:
    root = tmp_path / corpus
    build_corpus(root, suffix, template, comment, FILES)

    reference = _reference_seconds()
    seconds, megabytes = _scan_cost(root)
    cost = seconds / reference / megabytes
    budget = BUDGETS[corpus]

    assert cost <= budget, (
        f"{corpus} scanning costs {cost:.1f} reference units per MB, over the {budget} budget. "
        "Something in the character loop got more expensive per byte — a per-character function call "
        "or an isspace()/isalnum() check are the usual causes. Run `uv run poe bench` to compare."
    )
