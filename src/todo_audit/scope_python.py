"""Exact code-scope resolution for Python via the stdlib ``ast`` module.

Maps a 1-based line number to the tightest enclosing structure, and names it. A
comment "immediately above" or "directly below" a ``def`` is attributed to that
function (``function``); a comment among a function's statements is
``function-inner``; comments in a class body outside any method are ``class``;
everything else is ``module``.
"""

from __future__ import annotations

import ast
from typing import List, NamedTuple, Optional, Tuple

from .models import Scope, ScopeInfo


def _effective_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", []) or []
    if decorators:
        return min(int(d.lineno) for d in decorators)
    return int(node.lineno)  # type: ignore[attr-defined]


def _signature_end(node: ast.AST) -> int:
    """Last line of a def's signature (its `):` region), used to separate the
    declaration from the body. Lines after this inside the def are body lines."""
    end = int(node.lineno)  # type: ignore[attr-defined]
    args = getattr(node, "args", None)
    if args is not None:
        for child in ast.walk(args):
            ln = getattr(child, "lineno", None)
            if ln is not None:
                end = max(end, int(ln))
    returns = getattr(node, "returns", None)
    if returns is not None:
        end = max(end, int(getattr(returns, "end_lineno", returns.lineno)))
    return end


class _FuncSpan(NamedTuple):
    start: int  # first line of the declaration, decorators included
    sig_end: int  # last line of the signature; the body starts after it
    end: int  # last line of the whole def
    path: Tuple[str, ...]  # ("PaymentService", "refund"); joined only when resolved


class _ClassSpan(NamedTuple):
    start: int  # first line of the declaration, decorators included
    end: int  # last line of the whole class body
    path: Tuple[str, ...]  # ("Outer", "Inner"); joined only when resolved


class PythonScoper:
    """Resolve scopes for many lines after a single parse.

    Line spans and symbol names are resolved once here rather than per lookup:
    ``_signature_end`` walks a function's argument AST, which is far too costly
    to repeat for every marker in the file.
    """

    def __init__(self, source: str):
        self._ok = True
        self._funcs: List[_FuncSpan] = []
        self._classes: List[_ClassSpan] = []
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            # ValueError covers sources containing NUL bytes
            self._ok = False
            return
        # Explicit stack rather than recursion: deeply nested modules would
        # otherwise risk a RecursionError.
        pending: List[Tuple[ast.AST, Tuple[str, ...]]] = [(tree, ())]
        while pending:
            node, prefix = pending.pop()
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    path = (*prefix, child.name)
                    self._funcs.append(
                        _FuncSpan(
                            _effective_start(child),
                            _signature_end(child),
                            int(child.end_lineno or 0),
                            path,
                        )
                    )
                    pending.append((child, path))
                elif isinstance(child, ast.ClassDef):
                    path = (*prefix, child.name)
                    self._classes.append(_ClassSpan(_effective_start(child), int(child.end_lineno or 0), path))
                    pending.append((child, path))
                else:
                    pending.append((child, prefix))

    @property
    def usable(self) -> bool:
        return self._ok

    def resolve(self, line: int) -> ScopeInfo:
        best_kind: Optional[Scope] = None
        best_path: Tuple[str, ...] = ()
        best_span = None
        for f in self._funcs:
            if line == f.start - 1 or (f.start <= line <= f.sig_end):
                kind = Scope.FUNCTION
            elif f.sig_end < line <= f.end:
                kind = Scope.FUNCTION_INNER
            else:
                continue
            span = f.end - f.start
            if best_span is None or span < best_span:
                best_kind, best_path, best_span = kind, f.path, span
        if best_kind is None:
            for c in self._classes:
                if line == c.start - 1 or (c.start <= line <= c.end):
                    span = c.end - c.start
                    if best_span is None or span < best_span:
                        best_kind, best_path, best_span = Scope.CLASS, c.path, span
        if best_kind is None:
            return ScopeInfo(Scope.MODULE, None)
        # joined here, once per resolved marker, rather than once per definition
        return ScopeInfo(best_kind, ".".join(best_path) or None)

    def scope_of(self, line: int) -> Scope:
        """Kind only, for callers that do not need the symbol name."""
        return self.resolve(line).scope
