from pathlib import Path
from typing import Dict, List

from todo_audit import scan_file
from todo_audit.models import Scope, Todo, TodoType

FIXTURES = Path(__file__).parent / "fixtures"


def _index(todos: List[Todo]) -> Dict[int, Todo]:
    return {t.line: t for t in todos}


def test_python_scope_and_type() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    by_line = _index(todos)

    # decoy string literal is not detected
    assert 22 not in by_line
    assert len(todos) == 6

    assert (by_line[1].type, by_line[1].scope) == (TodoType.URGENT, Scope.MODULE)
    assert (by_line[4].type, by_line[4].scope) == (TodoType.QUESTION, Scope.CLASS)
    assert (by_line[7].type, by_line[7].scope) == (TodoType.PLAIN, Scope.CLASS)
    assert (by_line[10].type, by_line[10].scope) == (TodoType.URGENT, Scope.FUNCTION)
    assert (by_line[12].type, by_line[12].scope) == (TodoType.QUESTION, Scope.FUNCTION_INNER)
    assert (by_line[18].type, by_line[18].scope) == (TodoType.PLAIN, Scope.FUNCTION_INNER)


def test_python_relative_path() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    assert all(t.file == "py_sample.py" for t in todos)


def test_python_descriptions_trimmed() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    by_line = _index(todos)
    assert by_line[1].description == "module urgent"
    assert by_line[12].description == "inside method"


def test_js_scope_and_type() -> None:
    todos = scan_file(str(FIXTURES / "js_sample.js"), root=str(FIXTURES))
    by_line = _index(todos)

    assert 1 not in by_line  # decoy inside string
    assert len(todos) == 5

    assert (by_line[2].type, by_line[2].scope) == (TodoType.QUESTION, Scope.CLASS)
    assert (by_line[4].type, by_line[4].scope) == (TodoType.PLAIN, Scope.CLASS)
    assert (by_line[7].type, by_line[7].scope) == (TodoType.URGENT, Scope.FUNCTION_INNER)
    assert (by_line[11].type, by_line[11].scope) == (TodoType.PLAIN, Scope.FUNCTION)
    assert (by_line[13].type, by_line[13].scope) == (TodoType.URGENT, Scope.FUNCTION_INNER)


def test_unsupported_extension_skipped(tmp_path: Path) -> None:
    f = tmp_path / "notes.unknownext"
    f.write_text("TODO: should not be scanned\n")
    assert scan_file(str(f)) == []
