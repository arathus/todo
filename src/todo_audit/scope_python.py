"""Exact code-scope resolution for Python via the stdlib ``ast`` module.

Maps a 1-based line number to the tightest enclosing structure. A comment
"immediately above" or "directly below" a ``def`` is attributed to that
function (``function``); a comment among a function's statements is
``function-inner``; comments in a class body outside any method are ``class``;
everything else is ``module``.
"""

from __future__ import annotations

import ast
from typing import List, Optional

from .models import Scope


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


class PythonScoper:
    """Resolve scopes for many lines after a single parse."""

    def __init__(self, source: str):
        self._ok = True
        self._funcs: List[ast.AST] = []
        self._classes: List[ast.AST] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self._ok = False
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._funcs.append(node)
            elif isinstance(node, ast.ClassDef):
                self._classes.append(node)

    @property
    def usable(self) -> bool:
        return self._ok

    def scope_of(self, line: int) -> Scope:
        best_kind: Optional[Scope] = None
        best_span = None
        for f in self._funcs:
            start = _effective_start(f)
            sig_end = _signature_end(f)
            end = f.end_lineno  # type: ignore[attr-defined]
            if line == start - 1 or (start <= line <= sig_end):
                kind = Scope.FUNCTION
            elif sig_end < line <= end:
                kind = Scope.FUNCTION_INNER
            else:
                continue
            span = end - start
            if best_span is None or span < best_span:
                best_kind, best_span = kind, span
        if best_kind is not None:
            return best_kind

        for c in self._classes:
            start = _effective_start(c)
            end = c.end_lineno  # type: ignore[attr-defined]
            if line == start - 1 or (start <= line <= end):
                span = end - start
                if best_span is None or span < best_span:
                    best_kind, best_span = Scope.CLASS, span
        if best_kind is not None:
            return best_kind

        return Scope.MODULE
