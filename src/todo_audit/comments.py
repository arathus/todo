"""Comment-syntax table and comment-aware marker detection.

Markers are only matched inside *real* comments. A tiny per-language tokenizer
walks the source tracking string and block-comment state so that a marker inside
a string literal (e.g. ``x = "TODO: not real"``) is never reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import TodoType

# ``!TODO:`` / ``?TODO:`` / ``TODO:`` — the optional sigil decides the type.
MARKER_RE = re.compile(r"(?P<sigil>[!?])?TODO:\s?(?P<desc>.*)")

_SIGIL_TO_TYPE = {
    "!": TodoType.URGENT,
    "?": TodoType.QUESTION,
    None: TodoType.PLAIN,
}


@dataclass(frozen=True)
class LangSyntax:
    line: Optional[str]  # line-comment prefix, e.g. "#" or "//"
    block: Optional[Tuple[str, str]]  # (open, close), e.g. ("/*", "*/")
    quotes: Tuple[str, ...]  # string delimiters
    triples: Tuple[str, ...] = ()  # triple-quote string delimiters (Python)


_C_FAMILY = LangSyntax(line="//", block=("/*", "*/"), quotes=('"', "'", "`"))
_HASH = LangSyntax(line="#", block=None, quotes=('"', "'"))
_PYTHON = LangSyntax(line="#", block=None, quotes=('"', "'"), triples=('"""', "'''"))

# Extension -> syntax. Extend freely; unknown extensions are skipped.
SYNTAX_BY_EXT: Dict[str, LangSyntax] = {
    ".py": _PYTHON,
    ".pyi": _PYTHON,
    ".js": _C_FAMILY,
    ".jsx": _C_FAMILY,
    ".ts": _C_FAMILY,
    ".tsx": _C_FAMILY,
    ".mjs": _C_FAMILY,
    ".cjs": _C_FAMILY,
    ".java": _C_FAMILY,
    ".c": _C_FAMILY,
    ".h": _C_FAMILY,
    ".cpp": _C_FAMILY,
    ".cc": _C_FAMILY,
    ".hpp": _C_FAMILY,
    ".go": _C_FAMILY,
    ".rs": _C_FAMILY,
    ".swift": _C_FAMILY,
    ".kt": _C_FAMILY,
    ".rb": _HASH,
    ".sh": _HASH,
    ".bash": _HASH,
    ".zsh": _HASH,
    ".yaml": _HASH,
    ".yml": _HASH,
    ".toml": _HASH,
}


def syntax_for(ext: str) -> Optional[LangSyntax]:
    return SYNTAX_BY_EXT.get(ext.lower())


def comment_text_by_line(source: str, syntax: LangSyntax) -> Dict[int, str]:
    """Return {1-based line number: concatenated comment text on that line}.

    Only characters that are inside comments are returned; string and code
    characters are dropped, so downstream marker matching never sees a marker
    that lives inside a string literal.
    """
    out: Dict[int, List[str]] = {}
    line_no = 1
    i = 0
    n = len(source)
    in_block = False
    in_string: Optional[str] = None  # active single-line string delimiter
    in_triple: Optional[str] = None  # active triple-quote delimiter

    def emit(ch: str) -> None:
        out.setdefault(line_no, []).append(ch)

    while i < n:
        ch = source[i]

        if ch == "\n":
            line_no += 1
            i += 1
            # a line comment ends at newline; block/triple/string may continue
            continue

        if in_block:
            close = syntax.block[1]  # type: ignore[index]
            if source.startswith(close, i):
                in_block = False
                i += len(close)
            else:
                emit(ch)
                i += 1
            continue

        if in_triple is not None:
            if source.startswith(in_triple, i):
                i += len(in_triple)
                in_triple = None
            else:
                i += 1
            continue

        if in_string is not None:
            if ch == "\\":
                i += 2  # skip escaped char
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue

        # --- not currently inside string/comment ---
        # triple-quoted strings (Python) take priority over single quotes
        matched_triple = False
        for t in syntax.triples:
            if source.startswith(t, i):
                in_triple = t
                i += len(t)
                matched_triple = True
                break
        if matched_triple:
            continue

        if syntax.block and source.startswith(syntax.block[0], i):
            in_block = True
            i += len(syntax.block[0])
            continue

        if syntax.line and source.startswith(syntax.line, i):
            i += len(syntax.line)
            # rest of physical line is a comment
            while i < n and source[i] != "\n":
                emit(source[i])
                i += 1
            continue

        if ch in syntax.quotes:
            in_string = ch
            i += 1
            continue

        i += 1

    return {ln: "".join(frags) for ln, frags in out.items()}


def find_markers(source: str, syntax: LangSyntax) -> List[Tuple[int, TodoType, str]]:
    """Return (line_no, type, description) for each TODO marker in comments."""
    results: List[Tuple[int, TodoType, str]] = []
    for line_no, text in comment_text_by_line(source, syntax).items():
        for m in MARKER_RE.finditer(text):
            todo_type = _SIGIL_TO_TYPE[m.group("sigil")]
            results.append((line_no, todo_type, m.group("desc").strip()))
    return results
