from typing import List, Tuple

from todo_audit.comments import find_markers, syntax_for
from todo_audit.models import TodoType


def _types(source: str, ext: str) -> List[Tuple[TodoType, str]]:
    syntax = syntax_for(ext)
    assert syntax is not None
    return [(t, desc) for _, t, desc in find_markers(source, syntax)]


def test_block_comment_marker_detected() -> None:
    found = _types("/* !TODO: block urgent */\n", ".js")
    assert found == [(TodoType.URGENT, "block urgent")]


def test_marker_in_python_triple_string_ignored() -> None:
    source = '"""\nTODO: inside a docstring string literal\n"""\n# ?TODO: real one\n'
    found = _types(source, ".py")
    assert found == [(TodoType.QUESTION, "real one")]


def test_escaped_quote_does_not_break_string_tracking() -> None:
    # the escaped quote keeps us inside the string, so the marker stays hidden
    source = 'x = "a \\" TODO: still string"\n// TODO: the real one\n'
    found = _types(source, ".js")
    assert found == [(TodoType.PLAIN, "the real one")]


def test_multiline_block_comment_marker() -> None:
    source = "/*\n line one\n !TODO: deep in block\n*/\n"
    found = _types(source, ".c")
    assert found == [(TodoType.URGENT, "deep in block")]


def test_unknown_extension_has_no_syntax() -> None:
    assert syntax_for(".unknownext") is None
