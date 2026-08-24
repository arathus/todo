"""Comment-syntax table and comment-aware marker detection.

Markers are only matched inside *real* comments. A tiny per-language tokenizer
walks the source tracking string, block-comment, and (for JS/TS) regex-literal
state so that a marker inside a string literal (e.g. ``x = "TODO: not real"``)
is never reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Pattern, Tuple

from .models import TodoType

# Marker keywords the scanner recognizes. Extend this tuple (and
# ``DEFAULT_TYPE_BY_MARKER``) to teach it new ones.
MARKER_KEYWORDS: Tuple[str, ...] = ("TODO", "FIXME", "HACK", "XXX")

# Type applied when a marker carries no ``!``/``?`` sigil. FIXME and XXX are
# treated as urgent by convention: both assert something is wrong right now.
DEFAULT_TYPE_BY_MARKER: Dict[str, TodoType] = {
    "TODO": TodoType.PLAIN,
    "FIXME": TodoType.URGENT,
    "HACK": TodoType.PLAIN,
    "XXX": TodoType.URGENT,
}

# An explicit sigil always wins over the keyword's default type.
_SIGIL_TO_TYPE: Dict[str, TodoType] = {
    "!": TodoType.URGENT,
    "?": TodoType.QUESTION,
}


def build_marker_re(keywords: Tuple[str, ...]) -> Pattern[str]:
    """Compile the marker pattern for ``keywords``.

    The leading lookbehind is what keeps ``NOTODO:`` / ``METODO:`` from being
    reported as a ``TODO``. The optional parenthesised group captures the
    widespread ``TODO(alice):`` / ``TODO(#412):`` owner convention.

    The sigil is accepted on either side of the keyword, so ``TODO!:`` reads
    exactly like ``!TODO:``. Both positions occur in the wild, and a marker
    written the other way round used to match nothing at all — an urgent item
    would vanish from the audit entirely rather than merely lose its severity.
    """
    alternation = "|".join(sorted(keywords, key=len, reverse=True))
    return re.compile(
        rf"(?<![A-Za-z0-9_])(?P<sigil>[!?])?(?P<marker>{alternation})"
        rf"(?:\((?P<assignee>[^)\n]{{1,64}})\))?(?P<trailing_sigil>[!?])?:\s?(?P<desc>.*)"
    )


MARKER_RE = build_marker_re(MARKER_KEYWORDS)

# A comment line continues the marker above it when it stands on its own line
# and carries no marker of its own. Leading decoration (JSDoc's ``*``) is dropped.
_CONTINUATION_TRIM = " \t*"

# How many following lines a single marker may absorb. Bounds the damage when a
# genuinely unrelated comment block sits directly beneath a TODO.
MAX_CONTINUATION_LINES = 5

# Comment lines that are machinery rather than prose. These end a continuation:
# a tool directive or a licence header is never part of a TODO's description.
_DIRECTIVE_RE = re.compile(
    r"^(?:!"  # shebang
    r"|-\*-"  # editor mode line
    r"|coding[:=]"
    r"|noqa\b|type:\s|pragma\b|pylint:|mypy:|ruff:|flake8:|isort:|fmt:\s*(?:on|off)"
    r"|eslint|prettier|@ts-|c8 |istanbul "
    r"|copyright\b|spdx-|licen[cs]e\b"
    r")",
    re.IGNORECASE,
)


class CommentLine(NamedTuple):
    """The comment text on one line, and whether it starts that line.

    ``own_line`` is what separates a wrapped description from an unrelated
    trailing comment: ``x = 1  # TODO: fix`` followed by ``y = 2  # note`` is two
    remarks about two statements, not one wrapped sentence.
    """

    text: str
    own_line: bool
    block_id: int = 0  # nonzero: lines sharing a value are one `/* ... */` comment


class MarkerHit(NamedTuple):
    """One marker found inside a comment."""

    line: int
    type: TodoType
    description: str
    marker: str
    assignee: Optional[str] = None


@dataclass(frozen=True)
class LangSyntax:
    line: Optional[str]  # line-comment prefix, e.g. "#" or "//"
    block: Optional[Tuple[str, str]]  # (open, close), e.g. ("/*", "*/")
    quotes: Tuple[str, ...]  # string delimiters
    triples: Tuple[str, ...] = ()  # triple-quote string delimiters (Python)
    regex_literals: bool = False  # language has /regex/ literals (JS/TS)


_JS_FAMILY = LangSyntax(line="//", block=("/*", "*/"), quotes=('"', "'", "`"), regex_literals=True)
_C_FAMILY = LangSyntax(line="//", block=("/*", "*/"), quotes=('"', "'", "`"))
_HASH = LangSyntax(line="#", block=None, quotes=('"', "'"))
_PYTHON = LangSyntax(line="#", block=None, quotes=('"', "'"), triples=('"""', "'''"))

# Extension -> syntax. Extend freely; unknown extensions are skipped.
SYNTAX_BY_EXT: Dict[str, LangSyntax] = {
    ".py": _PYTHON,
    ".pyi": _PYTHON,
    ".js": _JS_FAMILY,
    ".jsx": _JS_FAMILY,
    ".ts": _JS_FAMILY,
    ".tsx": _JS_FAMILY,
    ".mjs": _JS_FAMILY,
    ".cjs": _JS_FAMILY,
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

# Characters after which a `/` opens a regex literal rather than dividing.
_REGEX_PREV_CHARS = frozenset("(,=:[!&|?{};+-*%<>~^")
# Keywords after which the same is true.
_REGEX_PREV_WORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "case",
        "do",
        "else",
        "yield",
        "await",
        "throw",
    }
)

_WORD_EXTRA = "_$"


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch in _WORD_EXTRA


def starts_regex_literal(prev_char: str, last_word: str) -> bool:
    """Whether a ``/`` following ``prev_char`` opens a regex literal.

    Standard prev-token heuristic: after an operator, an opening bracket, or a
    keyword such as ``return``, a ``/`` starts a regex; after a value (an
    identifier, a literal, or a closing bracket) it is division.
    """
    if not prev_char:
        return True  # start of file
    if prev_char in _REGEX_PREV_CHARS:
        return True
    return _is_word_char(prev_char) and last_word in _REGEX_PREV_WORDS


def regex_literal_end(source: str, start: int) -> Optional[int]:
    """Index just past the closing ``/`` of the literal at ``start``, else None.

    Returns None when no closing delimiter is found on the same line, which
    means the ``/`` was not a regex literal after all.
    """
    i = start + 1
    n = len(source)
    in_class = False
    while i < n:
        ch = source[i]
        if ch == "\n":
            return None
        if ch == "\\":
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "/":
            return i + 1
        i += 1
    return None


def syntax_for(ext: str) -> Optional[LangSyntax]:
    return SYNTAX_BY_EXT.get(ext.lower())


def _openers(syntax: LangSyntax) -> FrozenSet[str]:
    """First characters of every construct that interrupts plain code.

    The source walkers test this before attempting any multi-character match, so
    an ordinary code character costs one set lookup instead of several
    ``str.startswith`` calls.
    """
    chars = set(syntax.quotes)
    chars.update(t[0] for t in syntax.triples)
    if syntax.block:
        chars.add(syntax.block[0][0])
    if syntax.line:
        chars.add(syntax.line[0])
    if syntax.regex_literals:
        chars.add("/")
    return frozenset(chars)


def _starts_line(source: str, index: int) -> bool:
    """Whether only whitespace precedes ``index`` on its line.

    Computed at comment boundaries rather than tracked per character: comments
    are a small fraction of a source file, and a per-character check showed up
    plainly in the scan benchmark.
    """
    return not source[source.rfind("\n", 0, index) + 1 : index].strip()


def comment_text_by_line(source: str, syntax: LangSyntax) -> Dict[int, CommentLine]:
    """Return {1-based line number: the comment on that line}.

    Only characters that are inside comments are returned; string and code
    characters are dropped, so downstream marker matching never sees a marker
    that lives inside a string literal. Each entry also records whether the
    comment starts its line, which is what lets a wrapped description be told
    apart from an unrelated comment trailing a different statement.
    """
    out: Dict[int, List[str]] = {}
    starts_line: Dict[int, bool] = {}
    block_ids: Dict[int, int] = {}
    line_no = 1
    i = 0
    n = len(source)
    in_block = False
    in_string: Optional[str] = None  # active single-line string delimiter
    in_triple: Optional[str] = None  # active triple-quote delimiter
    prev_char = ""  # last significant *code* character seen
    word_buf = ""  # word currently being accumulated
    last_word = ""  # most recent code word
    block_own_line = False  # did the open `/*` start its line?
    block_first_piece = False  # the next block piece is on the opening line
    block_seq = 0  # identifies which block comment a body line came from

    def add(text: str, own_line: bool, block_id: int = 0) -> None:
        out.setdefault(line_no, []).append(text)
        starts_line.setdefault(line_no, own_line)
        block_ids.setdefault(line_no, block_id)

    # Only these characters can open a string, a comment, or a regex literal.
    # Every other code character is skipped after one set lookup.
    openers = _openers(syntax)
    # prev_char/last_word feed the regex heuristic and nothing else, so tracking
    # them is dead weight in languages without regex literals.
    track_tokens = syntax.regex_literals

    while i < n:
        ch = source[i]

        if ch == "\n":
            line_no += 1
            i += 1
            # a line comment ends at newline; block/triple/string may continue
            continue

        if in_block:
            close = syntax.block[1]  # type: ignore[index]
            found = source.find(close, i)
            stop = n if found == -1 else found
            for offset, piece in enumerate(source[i:stop].split("\n")):
                if offset:
                    line_no += 1
                if piece:
                    add(piece, block_own_line if block_first_piece else True, block_seq)
                    block_first_piece = False
            if found == -1:
                i = n
            else:
                in_block = False
                i = found + len(close)
            continue

        if in_triple is not None:
            if ch == "\\":
                # an escaped newline still advances the line counter
                if source.startswith("\n", i + 1):
                    line_no += 1
                i += 2
                continue
            if source.startswith(in_triple, i):
                i += len(in_triple)
                in_triple = None
                prev_char, word_buf = '"', ""
            else:
                i += 1
            continue

        if in_string is not None:
            if ch == "\\":
                if source.startswith("\n", i + 1):
                    line_no += 1
                i += 2
                continue
            if ch == in_string:
                in_string = None
                prev_char, word_buf = ch, ""
            i += 1
            continue

        # --- not currently inside string/comment ---
        if ch in openers:
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
                block_seq += 1
                block_own_line = _starts_line(source, i)
                block_first_piece = True
                i += len(syntax.block[0])
                continue

            if syntax.line and source.startswith(syntax.line, i):
                own_line = _starts_line(source, i)
                i += len(syntax.line)
                # rest of the physical line is a comment
                found = source.find("\n", i)
                stop = n if found == -1 else found
                if stop > i:
                    add(source[i:stop], own_line)
                i = stop
                continue

            # A regex literal may contain `//` or `/*`; skip it before those can
            # be mistaken for a comment opener.
            if syntax.regex_literals and ch == "/" and starts_regex_literal(prev_char, last_word):
                end = regex_literal_end(source, i)
                if end is not None:
                    i = end
                    prev_char, word_buf = "/", ""
                    continue

            if ch in syntax.quotes:
                in_string = ch
                i += 1
                continue

        if track_tokens:
            if _is_word_char(ch):
                word_buf += ch
                last_word = word_buf
            else:
                word_buf = ""
            if not ch.isspace():
                prev_char = ch
        i += 1

    return {ln: CommentLine("".join(frags), starts_line[ln], block_ids[ln]) for ln, frags in out.items()}


def _continuation(by_line: Dict[int, CommentLine], line_no: int) -> str:
    """Text of the comment lines that continue the marker on ``line_no``.

    A description wrapped over several comment lines is one description, however
    the author aligned it — requiring extra indentation would silently truncate
    the commonest style of all:

    .. code-block:: python

        # TODO: rework the retry path
        # because the gateway returns 202

    The discriminator is therefore *own-line*, not indentation. A marker trailing
    a statement owns nothing below it, and a comment trailing a later statement
    is a remark about that statement rather than a continuation. Scanning also
    stops at a blank line, at real code, at another marker, and at tool
    directives or licence headers, which are machinery rather than prose.
    """
    head = by_line[line_no]
    parts: List[str] = []
    probe = line_no + 1
    while len(parts) < MAX_CONTINUATION_LINES:
        entry = by_line.get(probe)
        if entry is None:
            break
        if head.block_id:
            # Inside a `/* ... */` the lines are literally one comment, so they
            # continue it even when the opener trailed a statement — but the
            # closing delimiter ends it, so a following block is a new comment.
            if entry.block_id != head.block_id:
                break
        elif entry.block_id or not (head.own_line and entry.own_line):
            break
        if MARKER_RE.search(entry.text):
            break
        stripped = entry.text.strip(_CONTINUATION_TRIM).strip()
        if not stripped or _DIRECTIVE_RE.match(stripped):
            break
        parts.append(stripped)
        probe += 1
    return " ".join(parts)


def find_markers(source: str, syntax: LangSyntax) -> List[MarkerHit]:
    """Return one :class:`MarkerHit` per marker found in a real comment."""
    by_line = comment_text_by_line(source, syntax)
    results: List[MarkerHit] = []
    for line_no, entry in by_line.items():
        text = entry.text
        matches = list(MARKER_RE.finditer(text))
        for index, m in enumerate(matches):
            marker = m.group("marker")
            # `!TODO:` and `TODO!:` mean the same thing; a leading sigil wins if
            # both are somehow given, being the documented canonical position.
            sigil = m.group("sigil") or m.group("trailing_sigil")
            todo_type = _SIGIL_TO_TYPE[sigil] if sigil else DEFAULT_TYPE_BY_MARKER[marker]
            description = m.group("desc").strip()
            # only the last marker on a line can own the lines below it
            if index == len(matches) - 1:
                extra = _continuation(by_line, line_no)
                if extra:
                    description = f"{description} {extra}".strip()
            assignee = m.group("assignee")
            results.append(MarkerHit(line_no, todo_type, description, marker, assignee.strip() if assignee else None))
    return results
