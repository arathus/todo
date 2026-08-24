from pathlib import Path
from typing import Dict, List

import pytest

from todo_audit import scan_file
from todo_audit.models import Scope, Todo, TodoType

FIXTURES = Path(__file__).parent / "fixtures"


def _index(todos: List[Todo]) -> Dict[int, Todo]:
    return {t.line: t for t in todos}


def test_python_scope_and_type() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    by_line = _index(todos)

    assert 22 not in by_line, "the marker on line 22 lives in a string literal and must not be reported"
    assert len(todos) == 6, "py_sample.py holds exactly six real markers"

    expected = {
        1: (TodoType.URGENT, Scope.MODULE),
        4: (TodoType.QUESTION, Scope.CLASS),
        7: (TodoType.PLAIN, Scope.CLASS),
        10: (TodoType.URGENT, Scope.FUNCTION),
        12: (TodoType.QUESTION, Scope.FUNCTION_INNER),
        18: (TodoType.PLAIN, Scope.FUNCTION_INNER),
    }
    for line, (todo_type, scope) in expected.items():
        assert (by_line[line].type, by_line[line].scope) == (todo_type, scope), (
            f"py_sample.py:{line} must resolve to {todo_type.value}/{scope.value}"
        )


def test_python_relative_path() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    assert all(t.file == "py_sample.py" for t in todos), (
        "paths must be reported relative to the given root, not as absolute paths"
    )


def test_python_descriptions_trimmed() -> None:
    todos = scan_file(str(FIXTURES / "py_sample.py"), root=str(FIXTURES))
    by_line = _index(todos)
    assert by_line[1].description == "module urgent", "the description must drop the marker and surrounding whitespace"
    assert by_line[12].description == "inside method", "indented comments must yield the same trimmed description"


def test_js_scope_and_type() -> None:
    todos = scan_file(str(FIXTURES / "js_sample.js"), root=str(FIXTURES))
    by_line = _index(todos)

    assert 1 not in by_line, "the marker on line 1 lives in a string literal and must not be reported"
    assert len(todos) == 5, "js_sample.js holds exactly five real markers"

    expected = {
        2: (TodoType.QUESTION, Scope.CLASS),
        4: (TodoType.PLAIN, Scope.CLASS),
        7: (TodoType.URGENT, Scope.FUNCTION_INNER),
        11: (TodoType.PLAIN, Scope.FUNCTION),
        13: (TodoType.URGENT, Scope.FUNCTION_INNER),
    }
    for line, (todo_type, scope) in expected.items():
        assert (by_line[line].type, by_line[line].scope) == (todo_type, scope), (
            f"js_sample.js:{line} must resolve to {todo_type.value}/{scope.value}"
        )


def test_unsupported_extension_skipped(tmp_path: Path) -> None:
    f = tmp_path / "notes.unknownext"
    f.write_text("TODO: should not be scanned\n")
    assert scan_file(str(f)) == [], "a file whose extension has no comment syntax must yield nothing"


@pytest.mark.parametrize(("name", "comment"), [("app.rb", "# !TODO: ruby"), ("ci.yml", "# ?TODO: yaml")])
def test_languages_without_a_structural_parser_report_module_scope(tmp_path: Path, name: str, comment: str) -> None:
    f = tmp_path / name
    f.write_text(f"def wrapper\n  {comment}\nend\n", encoding="utf-8")
    todos = scan_file(str(f), root=str(tmp_path))
    assert [t.scope for t in todos] == [Scope.MODULE], (
        f"{name} has no structural parser, so every TODO must fall back to module scope"
    )


def test_supported_file_without_markers_yields_nothing(tmp_path: Path) -> None:
    # the scope parser is skipped entirely for such files, which is most of them
    f = tmp_path / "quiet.py"
    f.write_text("class A:\n    def run(self):\n        return 1\n", encoding="utf-8")
    assert scan_file(str(f), root=str(tmp_path)) == [], "a file with no markers must produce no records"


def test_markers_survive_the_scan(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("# FIXME: broken\n# HACK: patch\n", encoding="utf-8")
    todos = scan_file(str(f), root=str(tmp_path))
    assert [(t.marker, t.type) for t in todos] == [("FIXME", TodoType.URGENT), ("HACK", TodoType.PLAIN)], (
        "the keyword and its default type must both reach the Todo record"
    )


def test_python_with_a_syntax_error_falls_back_to_module_scope(tmp_path: Path) -> None:
    f = tmp_path / "broken.py"
    f.write_text("def oops(:\n    # TODO: unparseable\n", encoding="utf-8")
    todos = scan_file(str(f), root=str(tmp_path))
    assert [t.scope for t in todos] == [Scope.MODULE], (
        "unparseable Python must still report its TODOs, degraded to module scope"
    )
