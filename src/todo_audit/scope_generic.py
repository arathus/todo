"""Best-effort code-scope resolution for brace languages (JS/TS and others).

Pure-Python structural parser: strips strings, comments, and regex literals,
tracks a brace-frame stack, and classifies each frame as a class, a function, or
a plain block from the header text preceding its ``{``. Exact for standard
function/class/method forms; documented as best-effort. A tree-sitter backend is
the natural future upgrade.
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Tuple

from .comments import (
    _TRAILING_WORD_RE,
    LangSyntax,
    _opener_scanner,
    _skip_delimited,
    regex_literal_end,
    starts_regex_literal,
)
from .models import Scope, ScopeInfo

_CLASS_RE = re.compile(r"\bclass\b")
_FUNC_KW_RE = re.compile(r"\b(function|func|fn)\b")
# method / bare function header: `name(args)` (with an optional `-> T` / `: T`
# return type) immediately before the brace.
_CALLABLE_HEADER_RE = re.compile(r"(?P<name>[\w$]+)\s*\([^;{}]*\)\s*(?:(?:->|:)[^;{}]*)?$")
# Control-flow headers look exactly like calls; they open blocks, not functions.
_CONTROL_KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "foreach",
        "while",
        "do",
        "switch",
        "case",
        "try",
        "catch",
        "finally",
        "with",
        "return",
        "throw",
        "using",
        "lock",
        "match",
        "unless",
        "elif",
        "when",
        "select",
        "defer",
        "go",
        "sizeof",
        "typeof",
        "await",
        "yield",
        "new",
        "delete",
    }
)


_CLASS_NAME_RE = re.compile(r"\bclass\s+(?P<name>[\w$]+)")
_FUNC_NAME_RE = re.compile(r"\b(?:function|func|fn)\s+(?P<name>[\w$]+)")
# `const run = (...) =>` / `run: function (...)` / `let run = function`
_ASSIGNED_FUNC_RE = re.compile(r"(?P<name>[\w$]+)\s*[=:]\s*(?:async\s+)?(?:function\b|\(|[\w$]+\s*=>)")


class _Frame(NamedTuple):
    kind: str  # "class" | "function" | "block"
    header_line: int  # first line of the header/statement
    open_line: int  # line of the opening brace
    close_line: int  # line of the matching closing brace
    symbol: Optional[str]  # dotted path built from the enclosing frames


def _blank(text: str) -> str:
    """``text`` with every character replaced by a space, newlines kept.

    Preserving both length and line breaks is what lets the frame stack report
    exact line numbers after a comment or string has been removed.
    """
    if "\n" not in text:
        return " " * len(text)
    return "\n".join(" " * len(piece) for piece in text.split("\n"))


def _strip(source: str, syntax: LangSyntax) -> str:
    """Replace string, comment, and regex-literal characters with spaces.

    Newlines are preserved so line numbers stay exact; braces and semicolons in
    real code are preserved so the frame stack stays correct.

    Plain code is copied a span at a time rather than a character at a time: the
    regex engine finds the next construct in C, and everything before it is code
    that passes through untouched.
    """
    out: List[str] = []
    i, n = 0, len(source)
    prev_char = ""
    last_word = ""
    scanner = _opener_scanner(syntax)
    block_open = syntax.block[0] if syntax.block else None
    block_close = syntax.block[1] if syntax.block else None
    track_tokens = syntax.regex_literals

    while i < n:
        match = scanner.search(source, i)
        if match is None:
            out.append(source[i:])
            break

        opener = match.start()
        if opener > i:
            span = source[i:opener]
            out.append(span)
            if track_tokens:
                trailing = span.rstrip()
                if trailing:
                    prev_char = trailing[-1]
                    word = _TRAILING_WORD_RE.search(trailing)
                    last_word = word.group() if word else ""
            i = opener

        token = match.group()

        if token == block_open:
            assert block_close is not None
            found = source.find(block_close, match.end())
            if found == -1:
                out.append(_blank(source[i:]))
                i = n
            else:
                out.append(_blank(source[i : found + len(block_close)]))
                i = found + len(block_close)
            prev_char, last_word = "/", ""
            continue

        if token == syntax.line:
            found = source.find("\n", match.end())
            stop = n if found == -1 else found
            out.append(_blank(source[i:stop]))
            i = stop
            continue

        if token == "/":  # only reachable where regex literals exist
            if starts_regex_literal(prev_char, last_word):
                end = regex_literal_end(source, i)
                if end is not None:
                    out.append(_blank(source[i:end]))
                    i = end
                    prev_char, last_word = "/", ""
                    continue
            out.append("/")  # division after all
            i += 1
            prev_char, last_word = "/", ""
            continue

        # a string literal: blank it, delimiters included
        end = _skip_delimited(source, match.end(), token)
        out.append(_blank(source[i:end]))
        i = end
        prev_char, last_word = token, ""

    return "".join(out)


def _classify(header: str) -> str:
    header = header.strip()
    if _CLASS_RE.search(header):
        return "class"
    if _FUNC_KW_RE.search(header) or "=>" in header:
        return "function"
    match = _CALLABLE_HEADER_RE.search(header)
    if match and match.group("name") not in _CONTROL_KEYWORDS:
        return "function"
    return "block"


def _header_name(header: str, kind: str) -> Optional[str]:
    """Best-effort declared name for a frame, or None for anonymous ones."""
    header = header.strip()
    if kind == "class":
        found = _CLASS_NAME_RE.search(header)
        return found.group("name") if found else None
    if kind != "function":
        return None
    for pattern in (_FUNC_NAME_RE, _ASSIGNED_FUNC_RE):
        found = pattern.search(header)
        if found:
            return found.group("name")
    if _FUNC_KW_RE.search(header) or "=>" in header:
        # An anonymous function passed to a call, as in `setTimeout(function () {`.
        # The identifier here names the callee, not this frame — reporting it
        # would attribute the body to the wrong symbol.
        return None
    found = _CALLABLE_HEADER_RE.search(header)
    if found and found.group("name") not in _CONTROL_KEYWORDS:
        return found.group("name")
    # Unreachable while _classify only calls a frame a function for one of the
    # reasons handled above; kept so the two cannot drift apart silently.
    return None  # pragma: no cover


class GenericScoper:
    """Resolve scopes for many lines after a single structural pass."""

    def __init__(self, source: str, syntax: LangSyntax):
        self._frames: List[_Frame] = []
        code = _strip(source, syntax)
        line_no = 1
        header_start = 1
        header_buf: List[str] = []
        # (kind, header_line, open_line, dotted symbol)
        stack: List[Tuple[str, int, int, Optional[str]]] = []

        for ch in code:
            if ch == "\n":
                line_no += 1
                continue
            if ch == "{":
                header = "".join(header_buf)
                kind = _classify(header)
                name = _header_name(header, kind)
                parent = next((frame[3] for frame in reversed(stack) if frame[3]), None)
                if name and parent:
                    symbol: Optional[str] = f"{parent}.{name}"
                else:
                    symbol = name or parent
                stack.append((kind, header_start, line_no, symbol))
                header_buf = []
                header_start = line_no
            elif ch == "}":
                if stack:
                    kind, hline, oline, symbol = stack.pop()
                    self._frames.append(_Frame(kind, hline, oline, line_no, symbol))
                header_buf = []
                header_start = line_no
            elif ch == ";":
                header_buf = []
                header_start = line_no
            elif ch.isspace():
                if header_buf:  # keep internal spacing, ignore leading whitespace
                    header_buf.append(ch)
            else:
                if not header_buf:
                    header_start = line_no
                header_buf.append(ch)

    def resolve(self, line: int) -> ScopeInfo:
        best: Optional[_Frame] = None
        best_span = None
        for f in self._frames:
            if f.kind == "block":
                continue
            if f.header_line - 1 <= line <= f.close_line:
                span = f.close_line - f.header_line
                if best_span is None or span < best_span:
                    best, best_span = f, span
        if best is None:
            return ScopeInfo(Scope.MODULE, None)
        if best.kind == "class":
            return ScopeInfo(Scope.CLASS, best.symbol)
        # function frame
        if line <= best.open_line:
            return ScopeInfo(Scope.FUNCTION, best.symbol)
        return ScopeInfo(Scope.FUNCTION_INNER, best.symbol)

    def scope_of(self, line: int) -> Scope:
        """Kind only, for callers that do not need the symbol name."""
        return self.resolve(line).scope
