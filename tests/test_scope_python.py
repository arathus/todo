"""Exact Python scope resolution via ``ast``."""

from todo_audit.comments import syntax_for
from todo_audit.models import Scope
from todo_audit.scope_python import PythonScoper


def _scope(source: str, line: int) -> Scope:
    return PythonScoper(source).scope_of(line)


def test_comment_above_a_decorator_belongs_to_the_function() -> None:
    source = "# TODO: above the decorator\n@cache\ndef run():\n    return 1\n"
    assert _scope(source, 1) == Scope.FUNCTION, (
        "a decorated function starts at its first decorator, so the line above that is still its documentation"
    )


def test_comment_between_decorator_and_def_belongs_to_the_function() -> None:
    source = "@cache\n# TODO: between\ndef run():\n    return 1\n"
    assert _scope(source, 2) == Scope.FUNCTION, "a line between a decorator and its `def` is inside the declaration"


def test_multiline_signature_is_function_not_function_inner() -> None:
    source = "def run(\n    a,\n    # TODO: in the signature\n    b,\n):\n    return a + b\n"
    assert _scope(source, 3) == Scope.FUNCTION, (
        "lines within the argument list are part of the declaration, not the body"
    )


def test_return_annotation_extends_the_signature() -> None:
    source = "def run(\n    a,\n) -> (\n    # TODO: in the return annotation\n    int\n):\n    return a\n"
    assert _scope(source, 4) == Scope.FUNCTION, (
        "the signature does not end at the closing paren of the arguments; the return annotation is part of it"
    )


def test_body_after_the_signature_is_function_inner() -> None:
    source = "def run(\n    a,\n) -> int:\n    # TODO: in the body\n    return a\n"
    assert _scope(source, 4) == Scope.FUNCTION_INNER, (
        "once the signature ends, statements belong to the body and must read as function-inner"
    )


def test_argument_free_def_body() -> None:
    source = "def run():\n    # TODO: no args at all\n    return 1\n"
    assert _scope(source, 2) == Scope.FUNCTION_INNER, "a def with no arguments must still separate signature from body"


def test_nested_function_wins_over_the_outer_one() -> None:
    source = "def outer():\n    def inner():\n        # TODO: innermost\n        return 1\n    return inner\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, "the tightest enclosing structure wins when frames overlap"


def test_async_def_is_recognized() -> None:
    source = "async def run():\n    # TODO: async body\n    return 1\n"
    assert _scope(source, 2) == Scope.FUNCTION_INNER, "`async def` must be treated exactly like `def`"


def test_method_wins_over_the_enclosing_class() -> None:
    source = "class A:\n    def run(self):\n        # TODO: in the method\n        return 1\n"
    assert _scope(source, 3) == Scope.FUNCTION_INNER, (
        "a method body is tighter than its class, so the function scope must win"
    )


def test_class_body_outside_any_method() -> None:
    source = "class A:\n    # TODO: class body\n    field = 1\n"
    assert _scope(source, 2) == Scope.CLASS, "with no method enclosing it, a class-body comment belongs to the class"


def test_nested_class_wins_over_the_outer_one() -> None:
    source = "class Outer:\n    class Inner:\n        # TODO: inner class\n        pass\n    field = 1\n"
    assert _scope(source, 3) == Scope.CLASS, "the tightest class must win, the same way the tightest function does"


def test_module_level_line() -> None:
    source = "# TODO: module level\nimport os\n"
    assert _scope(source, 1) == Scope.MODULE, "a line inside no function or class is module-level"


def test_syntax_error_makes_the_scoper_unusable() -> None:
    scoper = PythonScoper("def oops(:\n")
    assert scoper.usable is False, (
        "unparseable source must report itself unusable so the caller can fall back to module scope"
    )


def test_valid_source_is_usable() -> None:
    assert PythonScoper("x = 1\n").usable is True, "source that parses cleanly must report itself usable"


def test_python_syntax_has_triple_quote_delimiters() -> None:
    syntax = syntax_for(".py")
    assert syntax is not None, "no comment syntax is registered for .py, so nothing would be scanned"
    assert syntax.triples == ('"""', "'''"), "docstrings must be tracked, or markers inside them would be reported"
    assert syntax.regex_literals is False, "Python has no regex literals; enabling the heuristic would misread `/`"
