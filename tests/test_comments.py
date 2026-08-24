from typing import List, Tuple

from todo_audit.comments import MARKER_KEYWORDS, find_markers, syntax_for
from todo_audit.models import TodoType


def _hits(source: str, ext: str) -> List[Tuple[TodoType, str]]:
    syntax = syntax_for(ext)
    assert syntax is not None, f"no comment syntax is registered for {ext}, so this test cannot run"
    return [(hit.type, hit.description) for hit in find_markers(source, syntax)]


def _lines(source: str, ext: str) -> List[int]:
    syntax = syntax_for(ext)
    assert syntax is not None, f"no comment syntax is registered for {ext}, so this test cannot run"
    return [hit.line for hit in find_markers(source, syntax)]


def test_block_comment_marker_detected() -> None:
    found = _hits("/* !TODO: block urgent */\n", ".js")
    assert found == [(TodoType.URGENT, "block urgent")], "a marker inside a `/* */` comment must be detected"


def test_marker_in_python_triple_string_ignored() -> None:
    source = '"""\nTODO: inside a docstring string literal\n"""\n# ?TODO: real one\n'
    found = _hits(source, ".py")
    assert found == [(TodoType.QUESTION, "real one")], (
        "a docstring is a string literal, not a comment, so markers inside it must not be reported"
    )


def test_escaped_quote_does_not_break_string_tracking() -> None:
    source = 'x = "a \\" TODO: still string"\n// TODO: the real one\n'
    found = _hits(source, ".js")
    assert found == [(TodoType.PLAIN, "the real one")], (
        "an escaped quote keeps the string open, so the marker inside it must stay hidden"
    )


def test_multiline_block_comment_marker() -> None:
    source = "/*\n line one\n !TODO: deep in block\n*/\n"
    found = _hits(source, ".c")
    assert found == [(TodoType.URGENT, "deep in block")], (
        "block comment state must persist across newlines so markers on later lines are still seen"
    )


def test_unterminated_block_comment_still_yields_its_markers() -> None:
    source = "code();\n/*\n !TODO: never closed\n"
    assert _hits(source, ".js") == [(TodoType.URGENT, "never closed")], (
        "a block comment running to the end of the file must still be scanned, not discarded"
    )


def test_empty_line_comment_is_harmless() -> None:
    source = "x = 1  #\n# TODO: after an empty comment\n"
    assert _lines(source, ".py") == [2], "a comment prefix with nothing after it must not disturb the walk"


def test_unknown_extension_has_no_syntax() -> None:
    assert syntax_for(".unknownext") is None, "an unregistered extension must report no syntax so the file is skipped"


# --- marker vocabulary -----------------------------------------------------


def test_embedded_keyword_is_not_a_marker() -> None:
    source = "# NOTODO: not a marker\n# METODO: spanish for method\n# XXXX: redacted\n"
    assert _hits(source, ".py") == [], "detection is word-anchored: a keyword embedded in a longer word must not match"


def test_lowercase_marker_ignored() -> None:
    assert _hits("# todo: lower case\n# fixme: lower case\n", ".py") == [], (
        "markers are upper-case by convention; matching lower-case prose would flood the results"
    )


def test_fixme_and_xxx_default_to_urgent() -> None:
    found = _hits("# FIXME: broken now\n# XXX: dangerous\n# HACK: workaround\n", ".py")
    assert found == [
        (TodoType.URGENT, "broken now"),
        (TodoType.URGENT, "dangerous"),
        (TodoType.PLAIN, "workaround"),
    ], "FIXME and XXX assert something is wrong now (urgent); HACK marks routine debt (plain)"


def test_sigil_overrides_keyword_default() -> None:
    found = _hits("# ?FIXME: is this still broken\n# !HACK: must go before release\n", ".py")
    assert found == [
        (TodoType.QUESTION, "is this still broken"),
        (TodoType.URGENT, "must go before release"),
    ], "an explicit sigil must win over the keyword's default type"


def test_marker_keyword_is_reported() -> None:
    syntax = syntax_for(".py")
    assert syntax is not None, "no comment syntax is registered for .py, so this test cannot run"
    hits = find_markers("# FIXME: a\n# TODO: b\n", syntax)
    assert [hit.marker for hit in hits] == ["FIXME", "TODO"], (
        "the originating keyword must be preserved so a FIXME is not reported as an anonymous urgent TODO"
    )


def test_all_declared_keywords_are_detected() -> None:
    source = "".join(f"# {kw}: item\n" for kw in MARKER_KEYWORDS)
    assert len(_hits(source, ".py")) == len(MARKER_KEYWORDS), (
        f"every keyword in MARKER_KEYWORDS must be detectable; declared: {MARKER_KEYWORDS}"
    )


# --- line accounting -------------------------------------------------------


def test_escaped_newline_in_string_does_not_shift_lines_py() -> None:
    source = 'x = "abc\\\n def"\n# TODO: after continuation\n'
    assert _lines(source, ".py") == [3], (
        "the escaped newline must advance the line counter, or every marker after it is reported one line early"
    )


def test_escaped_newline_in_string_does_not_shift_lines_js() -> None:
    source = 'const s = "abc\\\n def";\n// TODO: after continuation\n'
    assert _lines(source, ".js") == [3], "string continuations must not shift reported line numbers in JS either"


def test_escaped_newline_in_triple_quoted_string_does_not_shift_lines() -> None:
    source = '"""abc\\\ndef"""\n# TODO: after docstring\n'
    assert _lines(source, ".py") == [3], "escapes inside a triple-quoted string must also keep the line count honest"


def test_crlf_source_reports_clean_descriptions() -> None:
    source = "# !TODO: windows line ending\r\nx = 1\r\n"
    assert _hits(source, ".py") == [(TodoType.URGENT, "windows line ending")], (
        "a CRLF file must not leave a stray carriage return on the end of the description"
    )


# --- JS/TS regex literals --------------------------------------------------


def test_regex_literal_containing_double_slash_is_not_a_comment() -> None:
    source = "const re = /\\/\\/ TODO: decoy/;\n// TODO: real one\n"
    syntax = syntax_for(".js")
    assert syntax is not None, "no comment syntax is registered for .js, so this test cannot run"
    hits = find_markers(source, syntax)
    assert [(hit.line, hit.description) for hit in hits] == [(2, "real one")], (
        "an escaped `//` inside a regex literal must not open a line comment"
    )


def test_regex_literal_does_not_swallow_a_trailing_comment() -> None:
    source = "const re = /a\\/b/; // TODO: after a regex\n"
    assert _hits(source, ".js") == [(TodoType.PLAIN, "after a regex")], (
        "the literal must end at its closing delimiter so the real comment after it is still scanned"
    )


def test_division_is_not_mistaken_for_a_regex() -> None:
    source = "const half = total / 2; // TODO: after a division\n"
    assert _hits(source, ".js") == [(TodoType.PLAIN, "after a division")], (
        "a `/` after a value is division; treating it as a regex would swallow the rest of the line"
    )


def test_unterminated_regex_candidate_falls_back_to_division() -> None:
    source = "const x = a /b\n// TODO: still found\n"
    assert _lines(source, ".js") == [2], "a `/` with no closing delimiter on the line was division after all"


def test_regex_heuristic_is_off_for_non_js_c_family() -> None:
    source = "int x = a / b; // TODO: c division\n"
    assert _hits(source, ".c") == [(TodoType.PLAIN, "c division")], (
        "C has no regex literals, so the heuristic must stay off there"
    )


def test_regex_literal_at_the_start_of_a_file() -> None:
    source = "/a\\/b/.test(s);\n// TODO: after a leading regex\n"
    assert _lines(source, ".js") == [2], "with no preceding token, a leading `/` can only be a regex literal"


def test_regex_candidate_without_a_closing_slash_is_not_a_regex() -> None:
    source = "const x = /abc\n// TODO: still found\n"
    assert _lines(source, ".js") == [2], (
        "regex literals cannot span lines, so an unclosed candidate must be abandoned rather than eating the next line"
    )


def test_regex_candidate_at_end_of_file_is_not_a_regex() -> None:
    assert _hits("// TODO: found\nconst x = /abc", ".js") == [(TodoType.PLAIN, "found")], (
        "a candidate that runs to the end of the file must be abandoned without reading past the end"
    )


def test_escaped_non_newline_inside_a_triple_quoted_string() -> None:
    source = '"""a \\" TODO: decoy"""\n# TODO: real one\n'
    syntax = syntax_for(".py")
    assert syntax is not None, "no comment syntax is registered for .py, so this test cannot run"
    hits = find_markers(source, syntax)
    assert [(hit.line, hit.description) for hit in hits] == [(2, "real one")], (
        "an escaped quote inside a docstring must not end it early and expose the decoy marker"
    )
