"""Structural scope resolution for brace languages."""

from typing import List

import pytest

from todo_audit.comments import syntax_for
from todo_audit.models import Scope
from todo_audit.scope_generic import GenericScoper


def _scope(source: str, line: int, ext: str = ".js") -> Scope:
    syntax = syntax_for(ext)
    assert syntax is not None, f"no comment syntax is registered for {ext}, so this test cannot run"
    return GenericScoper(source, syntax).scope_of(line)


@pytest.mark.parametrize(
    "header",
    [
        "if (ready)",
        "for (const item of items)",
        "while (running)",
        "switch (kind)",
        "do",
        "else",
    ],
)
def test_top_level_control_flow_is_module_scope(header: str) -> None:
    source = f"{header} {{\n  // TODO: not in a function\n}}\n"
    assert _scope(source, 2) == Scope.MODULE, (
        f"`{header}` looks like a call but opens a plain block, so a TODO inside it is module-level"
    )


def test_catch_block_at_top_level_is_module_scope() -> None:
    source = "try {\n  run();\n} catch (err) {\n  // TODO: handle it\n}\n"
    assert _scope(source, 4) == Scope.MODULE, "`catch (err)` is a control-flow header, not a function declaration"


def test_else_if_chain_is_module_scope() -> None:
    source = "if (a) {\n  x();\n} else if (b) {\n  // TODO: branch two\n}\n"
    assert _scope(source, 4) == Scope.MODULE, (
        "the header after a closing brace is `else if (b)`, which must classify as a block"
    )


def test_control_flow_inside_function_still_reports_function_inner() -> None:
    source = "function run() {\n  if (ready) {\n    // TODO: inner\n  }\n}\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, (
        "a block frame is transparent: the enclosing function must still be found"
    )


def test_arrow_function_body() -> None:
    source = "const run = () => {\n  // TODO: in arrow\n};\n"
    assert _scope(source, 2) == Scope.FUNCTION_INNER, "an `=>` header must be recognized as a function"


def test_method_with_typescript_return_type() -> None:
    source = "class A {\n  run(): void {\n    // TODO: typed method\n  }\n}\n"
    assert _scope(source, 3, ext=".ts") == Scope.FUNCTION_INNER, (
        "a `: T` return type must not stop a method header from being recognized"
    )


def test_go_func_with_multiple_return_values() -> None:
    source = "func Handle(a int) (int, error) {\n\t// TODO: go body\n}\n"
    assert _scope(source, 2, ext=".go") == Scope.FUNCTION_INNER, (
        "Go's multi-value return puts a second paren group before the brace; the `func` keyword must still win"
    )


def test_rust_fn_with_return_type() -> None:
    source = "fn parse(input: &str) -> usize {\n    // TODO: rust body\n}\n"
    assert _scope(source, 2, ext=".rs") == Scope.FUNCTION_INNER, (
        "the `fn` keyword must be recognized so Rust bodies resolve to a function, not a bare block"
    )


def test_regex_literal_braces_do_not_corrupt_the_frame_stack() -> None:
    source = "function run() {\n  const re = /[{}]/;\n  // TODO: after regex\n}\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, (
        "the `}` inside the regex literal would close the function frame early if the literal were not blanked out"
    )


def test_escaped_newline_in_string_does_not_shift_scope_lines() -> None:
    source = 'const s = "a\\\nb";\nfunction run() {\n  // TODO: inside\n}\n'
    assert _scope(source, 4) == Scope.FUNCTION_INNER, (
        "an escaped newline inside a string must still advance the line counter, or every later frame shifts by one"
    )


def test_class_body_outside_any_method() -> None:
    source = "class A {\n  // TODO: class body\n  field = 1;\n}\n"
    assert _scope(source, 2) == Scope.CLASS, "a comment in a class body but outside any method belongs to the class"


def test_line_above_function_header_is_function_scope() -> None:
    source = "// TODO: above\nfunction run() {\n  return 1;\n}\n"
    assert _scope(source, 1) == Scope.FUNCTION, (
        "a comment immediately above a declaration documents it, so it belongs to the function"
    )


def test_object_literal_is_not_a_function() -> None:
    source = "const config = {\n  // TODO: in an object literal\n};\n"
    assert _scope(source, 2) == Scope.MODULE, "`const config =` opens an object literal, not a callable"


def test_block_comment_braces_do_not_corrupt_the_frame_stack() -> None:
    source = "function run() {\n  /* } not real */\n  // TODO: after block comment\n}\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, (
        "the `}` lives inside a block comment, so the function frame must stay open"
    )


def test_multiline_block_comment_braces_do_not_corrupt_the_frame_stack() -> None:
    source = "function run() {\n  /* line one\n     } still a comment\n     line three */\n  // TODO: after\n}\n"
    assert _scope(source, 5) == Scope.FUNCTION_INNER, (
        "a block comment spanning several lines must be blanked without losing any of those lines"
    )


def test_unterminated_block_comment_does_not_break_scoping() -> None:
    source = "function run() {\n  // TODO: before\n}\n/* never closed\n"
    assert _scope(source, 2) == Scope.FUNCTION_INNER, (
        "a block comment left open at the end of the file must not disturb the frames before it"
    )


def test_unterminated_regex_candidate_in_a_function_body() -> None:
    source = "function run() {\n  const x = /abc;\n  // TODO: after a bare slash\n}\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, (
        "`= /abc` opens what looks like a regex but never closes on the line; the scan must give up cleanly"
    )


def test_trailing_backslash_inside_a_string_is_tolerated() -> None:
    source = 'function run() {\n  // TODO: before\n}\nconst s = "x\\'
    assert _scope(source, 2) == Scope.FUNCTION_INNER, (
        "a backslash as the final byte must not read past the end of the source"
    )


def test_unbalanced_closing_brace_is_tolerated() -> None:
    lines: List[str] = ["}", "// TODO: after a stray brace"]
    assert _scope("\n".join(lines) + "\n", 2) == Scope.MODULE, (
        "a closing brace with no matching frame must be dropped rather than corrupting the stack"
    )
