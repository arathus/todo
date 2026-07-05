"""Best-effort code-scope resolution for brace languages (JS/TS and others).

Pure-Python structural parser: strips strings/comments, tracks a brace-frame
stack, and classifies each frame as a class or function from the header text
preceding its ``{``. Exact for standard function/class/method forms; documented
as best-effort. A tree-sitter backend is the natural future upgrade.
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Tuple

from .comments import LangSyntax
from .models import Scope

_CLASS_RE = re.compile(r"\bclass\b")
_FUNC_KW_RE = re.compile(r"\bfunction\b")
# method / bare function header:  name(args)  immediately before the brace
_METHOD_RE = re.compile(r"[\w$]\s*\([^;{}]*\)\s*$")


class _Frame(NamedTuple):
    kind: str  # "class" | "function" | "block"
    header_line: int  # first line of the header/statement
    open_line: int  # line of the opening brace
    close_line: int  # line of the matching closing brace


def _strip(source: str, syntax: LangSyntax) -> str:
    """Replace string and comment characters with spaces; keep newlines/braces."""
    out: List[str] = []
    i, n = 0, len(source)
    in_block = False
    in_string: Optional[str] = None

    while i < n:
        ch = source[i]
        if ch == "\n":
            out.append("\n")
            i += 1
            continue
        if in_block:
            close = syntax.block[1]  # type: ignore[index]
            if source.startswith(close, i):
                in_block = False
                out.append(" " * len(close))
                i += len(close)
            else:
                out.append(" ")
                i += 1
            continue
        if in_string is not None:
            if ch == "\\":
                out.append("  ")
                i += 2
                continue
            if ch == in_string:
                in_string = None
            out.append(" ")
            i += 1
            continue
        if syntax.block and source.startswith(syntax.block[0], i):
            in_block = True
            out.append(" " * len(syntax.block[0]))
            i += len(syntax.block[0])
            continue
        if syntax.line and source.startswith(syntax.line, i):
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch in syntax.quotes:
            in_string = ch
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _classify(header: str) -> str:
    if _CLASS_RE.search(header):
        return "class"
    if _FUNC_KW_RE.search(header) or "=>" in header or _METHOD_RE.search(header.strip()):
        return "function"
    return "block"


class GenericScoper:
    """Resolve scopes for many lines after a single structural pass."""

    def __init__(self, source: str, syntax: LangSyntax):
        self._frames: List[_Frame] = []
        code = _strip(source, syntax)
        line_no = 1
        header_start = 1
        header_buf: List[str] = []
        stack: List[Tuple[str, int, int]] = []  # (kind, header_line, open_line)

        for ch in code:
            if ch == "\n":
                line_no += 1
                continue
            if ch == "{":
                kind = _classify("".join(header_buf))
                stack.append((kind, header_start, line_no))
                header_buf = []
                header_start = line_no
            elif ch == "}":
                if stack:
                    kind, hline, oline = stack.pop()
                    self._frames.append(_Frame(kind, hline, oline, line_no))
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

    def scope_of(self, line: int) -> Scope:
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
            return Scope.MODULE
        if best.kind == "class":
            return Scope.CLASS
        # function frame
        if line <= best.open_line:
            return Scope.FUNCTION
        return Scope.FUNCTION_INNER
