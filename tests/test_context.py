"""Facts the engine reports so the model does not have to open every file.

Symbol names, owners, continuation lines, and the stable id all exist to make an
audit possible from the payload alone.
"""

from pathlib import Path
from typing import Dict, List, Optional

import pytest

from todo_audit import scan_file
from todo_audit.comments import MAX_CONTINUATION_LINES, find_markers, syntax_for
from todo_audit.models import Scope, Todo, TodoType


def _write(path: Path, text: str) -> List[Todo]:
    path.write_text(text, encoding="utf-8")
    return scan_file(str(path), root=str(path.parent))


def _symbols(todos: List[Todo]) -> Dict[int, Optional[str]]:
    return {t.line: t.symbol for t in todos}


# --- enclosing symbol -----------------------------------------------------


def test_python_method_symbol_is_dotted(tmp_path: Path) -> None:
    todos = _write(
        tmp_path / "svc.py",
        "class PaymentService:\n    def refund(self):\n        # !TODO: partial refunds\n        return 1\n",
    )
    assert _symbols(todos) == {3: "PaymentService.refund"}, (
        "the payload must name the enclosing method, or two identical TODOs are indistinguishable"
    )


def test_python_nested_function_symbol(tmp_path: Path) -> None:
    todos = _write(
        tmp_path / "n.py",
        "def outer():\n    def inner():\n        # TODO: deep\n        return 1\n    return inner\n",
    )
    assert _symbols(todos) == {3: "outer.inner"}, "a nested function must report its full dotted path"


def test_python_class_body_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "c.py", "class Outer:\n    class Inner:\n        # TODO: here\n        pass\n")
    assert _symbols(todos) == {3: "Outer.Inner"}, "a nested class must report its full dotted path"


def test_python_module_level_has_no_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "m.py", "# TODO: module level\nimport os\n")
    assert _symbols(todos) == {1: None}, "module scope has no enclosing symbol to name"


def test_js_class_method_symbol(tmp_path: Path) -> None:
    todos = _write(
        tmp_path / "w.js",
        "class Widget {\n  render() {\n    // !TODO: memoize\n  }\n}\n",
    )
    assert _symbols(todos) == {3: "Widget.render"}, "the brace parser must name methods and their enclosing class"


def test_js_assigned_arrow_function_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "a.js", "const loadUser = async (id) => {\n  // TODO: cache this\n};\n")
    assert _symbols(todos) == {2: "loadUser"}, "an arrow function assigned to a name must report that name"


def test_js_anonymous_function_has_no_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "i.js", "setTimeout(function () {\n  // TODO: unnamed\n}, 10);\n")
    assert _symbols(todos) == {2: None}, "an anonymous function has no name to report, and must not invent one"


def test_go_function_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "h.go", "func Handle(a int) (int, error) {\n\t// TODO: retry\n}\n")
    assert _symbols(todos) == {2: "Handle"}, "the `func NAME` form must be named too"


def test_languages_without_a_parser_report_no_symbol(tmp_path: Path) -> None:
    todos = _write(tmp_path / "s.rb", "def wrapper\n  # TODO: ruby\nend\n")
    assert [(t.scope, t.symbol) for t in todos] == [(Scope.MODULE, None)], (
        "with no structural parser there is no symbol to report"
    )


# --- TODO(owner) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("comment", "assignee"),
    [
        ("# TODO(alice): ship it", "alice"),
        ("# !TODO(#412): ship it", "#412"),
        ("# FIXME(team-payments): ship it", "team-payments"),
        ("# TODO: ship it", None),
    ],
)
def test_assignee_is_captured(tmp_path: Path, comment: str, assignee: Optional[str]) -> None:
    todos = _write(tmp_path / "o.py", f"{comment}\n")
    assert todos[0].assignee == assignee, f"the owner in {comment!r} must be reported separately from the description"
    assert todos[0].description == "ship it", "the owner must not leak into the description"


def test_owner_form_keeps_its_type_and_marker(tmp_path: Path) -> None:
    todos = _write(tmp_path / "t.py", "# !TODO(bob): urgent with an owner\n")
    assert (todos[0].type, todos[0].marker) == (TodoType.URGENT, "TODO"), (
        "the parenthesised owner must not disturb sigil or keyword parsing"
    )


# --- continuation lines ---------------------------------------------------


def _descriptions(source: str, ext: str = ".py") -> List[str]:
    syntax = syntax_for(ext)
    assert syntax is not None, f"no comment syntax registered for {ext}"
    return [h.description for h in find_markers(source, syntax)]


def test_indented_continuation_is_appended() -> None:
    syntax = syntax_for(".py")
    assert syntax is not None, "no comment syntax registered for .py"
    hits = find_markers("# TODO: first part\n#   second part\n#   third part\n", syntax)
    assert [(h.line, h.description) for h in hits] == [(1, "first part second part third part")], (
        "an indented comment line below a marker continues it; dropping it truncates the description silently"
    )


def test_aligned_continuation_is_appended() -> None:
    # the commonest wrapped style of all: no extra indentation, just the next
    # comment line. Requiring an indent silently truncated these.
    assert _descriptions("# TODO: rework the retry path\n# because the gateway returns 202\n") == [
        "rework the retry path because the gateway returns 202"
    ], "a description wrapped at the same indentation is still one description"


def test_continuation_stops_at_a_blank_line() -> None:
    assert _descriptions("# TODO: mine\n\n# an unrelated remark\n") == ["mine"], (
        "a blank line ends the comment block, so what follows is a separate remark"
    )


def test_continuation_stops_at_code() -> None:
    assert _descriptions("# TODO: mine\nx = 1\n# a later remark\n") == ["mine"], (
        "a statement between the two comments means they are about different things"
    )


def test_a_trailing_marker_owns_nothing_below_it() -> None:
    assert _descriptions("x = 1  # TODO: fix\n# an unrelated note\n") == ["fix"], (
        "a marker trailing a statement is a remark about that statement; the line below is not its continuation"
    )


def test_a_trailing_comment_is_not_absorbed_as_a_continuation() -> None:
    assert _descriptions("# TODO: fix the parser\ny = 2  # unrelated note about y\n") == ["fix the parser"], (
        "a comment trailing a later statement describes that statement, not the TODO above it"
    )


@pytest.mark.parametrize(
    "directive",
    [
        "# noqa: E501",
        "# type: ignore",
        "# pylint: disable=all",
        "# fmt: off",
        "# Copyright 2020 Acme",
        "# SPDX-License-Identifier: MIT",
    ],
)
def test_continuation_stops_at_tool_directives_and_licence_headers(directive: str) -> None:
    assert _descriptions(f"# TODO: fix the parser\n{directive}\n") == ["fix the parser"], (
        f"{directive!r} is machinery, not prose, so it must not become part of the description"
    )


def test_one_block_comment_is_one_description() -> None:
    assert _descriptions("/* TODO: fix the parser\n   because of the grammar */\n", ".js") == [
        "fix the parser because of the grammar"
    ], "the lines of a single `/* ... */` are literally one comment"


def test_a_block_comment_continues_even_when_it_trails_a_statement() -> None:
    # the own-line rule does not apply within a block: the wrapped line is part
    # of the same lexical comment, not a remark about a different statement
    assert _descriptions("const x = 1; /* TODO: fix\n   wrapped here */\n", ".js") == ["fix wrapped here"], (
        "a wrapped block comment is one comment however it started"
    )


def test_a_closed_block_does_not_absorb_the_next_block() -> None:
    assert _descriptions("/* TODO: first */\n/* an unrelated second */\n", ".js") == ["first"], (
        "the closing delimiter ends the comment, so the block below it is a new one"
    )


def test_a_line_comment_does_not_absorb_a_following_block() -> None:
    assert _descriptions("// TODO: first\n/* an unrelated block */\n", ".js") == ["first"], (
        "a `//` comment and a `/* */` below it are two different comments"
    )


def test_continuation_is_capped() -> None:
    source = "# TODO: a\n" + "".join(f"# line{i}\n" for i in range(8))
    words = _descriptions(source)[0].split()
    assert len(words) == 1 + MAX_CONTINUATION_LINES, (
        f"an unbounded continuation would swallow a whole comment block; the cap is {MAX_CONTINUATION_LINES} lines"
    )


def test_a_second_marker_ends_the_continuation() -> None:
    syntax = syntax_for(".py")
    assert syntax is not None, "no comment syntax registered for .py"
    hits = find_markers("# TODO: first\n#   detail\n#   !TODO: second\n", syntax)
    assert [(h.line, h.description) for h in hits] == [(1, "first detail"), (3, "second")], (
        "a marker of its own always starts a new record, however indented"
    )


def test_blank_decorated_line_ends_the_continuation() -> None:
    syntax = syntax_for(".js")
    assert syntax is not None, "no comment syntax registered for .js"
    hits = find_markers("/**\n * !TODO: rework this\n *\n *   a separate paragraph\n */\n", syntax)
    assert [h.description for h in hits] == ["rework this"], (
        "a bare `*` line is a paragraph break, so the text after it is not part of the marker"
    )


def test_jsdoc_decoration_is_stripped() -> None:
    syntax = syntax_for(".js")
    assert syntax is not None, "no comment syntax registered for .js"
    hits = find_markers("/**\n * !TODO: rework this\n *   because of the retry bug\n */\n", syntax)
    assert [h.description for h in hits] == ["rework this because of the retry bug"], (
        "JSDoc's leading asterisk is decoration and must not appear in the description"
    )


# --- stable identity ------------------------------------------------------


def test_identity_survives_edits_above_the_todo(tmp_path: Path) -> None:
    before = _write(tmp_path / "s.py", "def run():\n    # TODO: same work\n    return 1\n")
    after = _write(
        tmp_path / "s.py",
        'import os\n\nHEADER = "new lines above"\n\n\ndef run():\n    # TODO: same work\n    return 1\n',
    )
    assert before[0].line != after[0].line, "the fixture must actually move the TODO for this test to mean anything"
    assert before[0].identity == after[0].identity, (
        "the id must ignore position, or every edit above a TODO makes it look new and CLAUDE.md accumulates duplicates"
    )


def test_identity_distinguishes_same_wording_in_different_methods(tmp_path: Path) -> None:
    todos = _write(
        tmp_path / "d.py",
        "class A:\n"
        "    def refund(self):\n"
        "        # !TODO: handle partial\n"
        "        return 1\n"
        "\n"
        "    def capture(self):\n"
        "        # !TODO: handle partial\n"
        "        return 2\n",
    )
    ids = {t.identity for t in todos}
    assert len(ids) == 2, "identically worded TODOs in different methods are different work and need different ids"


def test_identity_ignores_whitespace_and_case(tmp_path: Path) -> None:
    a = _write(tmp_path / "w.py", "# TODO: Handle   Partial Refunds\n")
    b = _write(tmp_path / "w.py", "# TODO: handle partial refunds\n")
    assert a[0].identity == b[0].identity, "reflowing or recasing a description must not create a new identity"


def test_identity_is_exposed_in_the_payload(tmp_path: Path) -> None:
    todos = _write(tmp_path / "p.py", "# TODO: one\n")
    payload = todos[0].to_dict()
    assert payload["id"] == todos[0].identity, "the id must reach the JSON the model reads"
    assert len(payload["id"]) == 12, "a 12-hex-character id is short enough to paste into a CLAUDE.md bullet"
