import pytest

from todo_audit.models import Scope, Todo, TodoType
from todo_audit.report import (
    color_of,
    group_by_severity,
    render_severity_list,
    sort_todos,
    validate_difficulty,
    validate_fix_kind,
)


def _t(line: int, ttype: TodoType, marker: str = "TODO") -> Todo:
    return Todo(file="a.py", line=line, type=ttype, scope=Scope.MODULE, description="x", marker=marker)


def test_sort_order_urgent_question_plain() -> None:
    todos = [
        _t(1, TodoType.PLAIN),
        _t(2, TodoType.URGENT),
        _t(3, TodoType.QUESTION),
    ]
    ordered = [t.type for t in sort_todos(todos)]
    assert ordered == [TodoType.URGENT, TodoType.QUESTION, TodoType.PLAIN], (
        "severity must outrank input order: urgent, then question, then plain"
    )


def test_sort_stable_by_file_then_line() -> None:
    todos = [_t(9, TodoType.URGENT), _t(2, TodoType.URGENT)]
    assert [t.line for t in sort_todos(todos)] == [2, 9], (
        "within one severity, ties must break by file and then by line number"
    )


@pytest.mark.parametrize(
    ("todo_type", "expected"),
    [(TodoType.URGENT, "red"), (TodoType.QUESTION, "blue"), (TodoType.PLAIN, "orange")],
)
def test_color_mapping(todo_type: TodoType, expected: str) -> None:
    assert color_of(_t(1, todo_type)) == expected, f"{todo_type.value} TODOs must render as {expected}"


def test_group_by_severity_keys_in_order() -> None:
    groups = group_by_severity([_t(1, TodoType.PLAIN)])
    assert list(groups.keys()) == [TodoType.URGENT, TodoType.QUESTION, TodoType.PLAIN], (
        "every severity group must be present in the fixed display order, even when empty"
    )


def test_render_severity_list_orders_sections() -> None:
    md = render_severity_list([_t(1, TodoType.PLAIN), _t(2, TodoType.URGENT)])
    assert md.index("red") < md.index("orange"), (
        "the urgent (red) section must be rendered before the plain (orange) one"
    )
    assert md.index("urgent") < md.index("color: orange"), "section headings must follow the same severity order"


def test_render_names_a_non_default_marker_only() -> None:
    md = render_severity_list([_t(1, TodoType.URGENT, marker="FIXME"), _t(2, TodoType.PLAIN)])
    assert "`FIXME`" in md, "a non-default keyword must be named, so FIXME is not shown as an anonymous urgent TODO"
    assert "`a.py:2` [module] — x" in md, "a plain TODO must render without a redundant keyword annotation"


def test_marker_defaults_to_todo() -> None:
    todo = Todo(file="a.py", line=1, type=TodoType.PLAIN, scope=Scope.MODULE, description="x")
    assert todo.marker == "TODO", "the marker field must default to TODO so existing callers keep working"


def test_to_dict_exposes_the_marker() -> None:
    payload = _t(1, TodoType.URGENT, marker="XXX").to_dict()
    assert payload["marker"] == "XXX", "the serialized record must carry the keyword that produced it"
    assert payload["type"] == "urgent", "enums must serialize to their string values, not repr"
    assert payload["color"] == "red", "the derived color must be included in the payload"


def test_validate_difficulty() -> None:
    assert validate_difficulty(3) == 3, "a level inside the 1-5 scale must pass through unchanged"
    for level in (0, 6):
        with pytest.raises(ValueError):
            validate_difficulty(level)


def test_validate_fix_kind() -> None:
    assert validate_fix_kind("system") == "system", "'system' is a valid fix kind and must pass through unchanged"
    assert validate_fix_kind("temporary") == "temporary", "'temporary' is a valid fix kind and must pass through"
    with pytest.raises(ValueError):
        validate_fix_kind("permanent")
