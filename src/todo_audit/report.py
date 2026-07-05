"""Presentation contract: sort order, color mapping, and fix classification.

Kept in one place so color/sort rules are testable and decoupled from whatever
renders them. Difficulty and fix suggestions are supplied by the model driving
the skill; this module only defines the vocabulary and ordering.
"""

from __future__ import annotations

from typing import Dict, List

from .models import COLOR_BY_TYPE, SORT_WEIGHT, Todo, TodoType

# 5-level difficulty scale (assigned by the model during /todo:audit).
DIFFICULTY_LABELS: Dict[int, str] = {
    1: "immediate fix",
    2: "refactor / reordering",
    3: "minor local rewrite",
    4: "module or system-level rewrite",
    5: "solution requiring complete redesign",
}

# A suggested fix is one of these; only "system" fixes are written to CLAUDE.md.
FIX_KINDS = ("system", "temporary")

# Display order of the type groups.
SEVERITY_ORDER: List[TodoType] = [TodoType.URGENT, TodoType.QUESTION, TodoType.PLAIN]

_TYPE_LABEL = {
    TodoType.URGENT: "!TODO (urgent)",
    TodoType.QUESTION: "?TODO (question)",
    TodoType.PLAIN: "TODO",
}


def sort_todos(todos: List[Todo]) -> List[Todo]:
    """Sort urgent -> question -> plain, then by file, then by line."""
    return sorted(todos, key=lambda t: (SORT_WEIGHT[t.type], t.file, t.line))


def group_by_severity(todos: List[Todo]) -> Dict[TodoType, List[Todo]]:
    groups: Dict[TodoType, List[Todo]] = {t: [] for t in SEVERITY_ORDER}
    for todo in sort_todos(todos):
        groups[todo.type].append(todo)
    return groups


def color_of(todo: Todo) -> str:
    return COLOR_BY_TYPE[todo.type]


def render_severity_list(todos: List[Todo]) -> str:
    """Markdown list grouped by severity, in the enforced order."""
    lines: List[str] = []
    groups = group_by_severity(todos)
    for todo_type in SEVERITY_ORDER:
        items = groups[todo_type]
        if not items:
            continue
        lines.append(f"### {_TYPE_LABEL[todo_type]}  _(color: {COLOR_BY_TYPE[todo_type]})_")
        for t in items:
            lines.append(f"- `{t.file}:{t.line}` [{t.scope.value}] — {t.description}")
        lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def validate_difficulty(level: int) -> int:
    if level not in DIFFICULTY_LABELS:
        raise ValueError(f"difficulty must be 1-5, got {level!r}")
    return level


def validate_fix_kind(kind: str) -> str:
    if kind not in FIX_KINDS:
        raise ValueError(f"fix_kind must be one of {FIX_KINDS}, got {kind!r}")
    return kind
