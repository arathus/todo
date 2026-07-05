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


def _t(line: int, ttype: TodoType) -> Todo:
    return Todo(file="a.py", line=line, type=ttype, scope=Scope.MODULE, description="x")


def test_sort_order_urgent_question_plain() -> None:
    todos = [
        _t(1, TodoType.PLAIN),
        _t(2, TodoType.URGENT),
        _t(3, TodoType.QUESTION),
    ]
    ordered = [t.type for t in sort_todos(todos)]
    assert ordered == [TodoType.URGENT, TodoType.QUESTION, TodoType.PLAIN]


def test_sort_stable_by_file_then_line() -> None:
    todos = [_t(9, TodoType.URGENT), _t(2, TodoType.URGENT)]
    assert [t.line for t in sort_todos(todos)] == [2, 9]


def test_color_mapping() -> None:
    assert color_of(_t(1, TodoType.URGENT)) == "red"
    assert color_of(_t(1, TodoType.QUESTION)) == "blue"
    assert color_of(_t(1, TodoType.PLAIN)) == "orange"


def test_group_by_severity_keys_in_order() -> None:
    groups = group_by_severity([_t(1, TodoType.PLAIN)])
    assert list(groups.keys()) == [TodoType.URGENT, TodoType.QUESTION, TodoType.PLAIN]


def test_render_severity_list_orders_sections() -> None:
    md = render_severity_list([_t(1, TodoType.PLAIN), _t(2, TodoType.URGENT)])
    # urgent (red) section must precede the plain (orange) section
    assert md.index("red") < md.index("orange")
    assert md.index("urgent") < md.index("color: orange")


def test_validate_difficulty() -> None:
    assert validate_difficulty(3) == 3
    with pytest.raises(ValueError):
        validate_difficulty(0)
    with pytest.raises(ValueError):
        validate_difficulty(6)


def test_validate_fix_kind() -> None:
    assert validate_fix_kind("system") == "system"
    assert validate_fix_kind("temporary") == "temporary"
    with pytest.raises(ValueError):
        validate_fix_kind("permanent")
