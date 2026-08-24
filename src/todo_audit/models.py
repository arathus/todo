"""Core data types for TODO records."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, NamedTuple, Optional


class TodoType(str, Enum):
    """The three recognized TODO marker types."""

    PLAIN = "plain"  # routine work
    QUESTION = "question"  # needs investigation
    URGENT = "urgent"  # imperative of what must be done


class Scope(str, Enum):
    """Where in the code structure a TODO sits."""

    MODULE = "module"  # standalone at module level
    CLASS = "class"  # top of / directly inside a class body
    FUNCTION = "function"  # immediately above or below a def
    FUNCTION_INNER = "function-inner"  # among statements within a function body


# Presentation intent — kept next to the type so reporting stays in one place.
COLOR_BY_TYPE: Dict[TodoType, str] = {
    TodoType.URGENT: "red",
    TodoType.QUESTION: "blue",
    TodoType.PLAIN: "orange",
}

# Sort weight: urgent first, then question, then plain.
SORT_WEIGHT: Dict[TodoType, int] = {
    TodoType.URGENT: 0,
    TodoType.QUESTION: 1,
    TodoType.PLAIN: 2,
}


class ScopeInfo(NamedTuple):
    """The tightest enclosing structure, and its name where one exists."""

    scope: Scope
    symbol: Optional[str]  # dotted path, e.g. "PaymentService.refund"


@dataclass(frozen=True)
class Todo:
    """One detected TODO comment."""

    file: str  # path relative to project root
    line: int  # 1-based line number
    type: TodoType
    scope: Scope
    description: str
    marker: str = "TODO"  # keyword that produced it: TODO / FIXME / HACK / XXX
    symbol: Optional[str] = None  # enclosing function/class, when resolvable
    assignee: Optional[str] = None  # owner from the `TODO(alice):` convention

    @property
    def color(self) -> str:
        return COLOR_BY_TYPE[self.type]

    @property
    def identity(self) -> str:
        """Stable id over content, not position.

        Deliberately excludes the line number so that editing the lines above a
        TODO does not make it look like a new one. This is what lets ``/todo:fix``
        deduplicate its managed ``CLAUDE.md`` section across runs. The enclosing
        symbol *is* included, so two identically worded TODOs in different
        methods stay distinguishable.
        """
        normalized = " ".join(self.description.lower().split())
        material = f"{self.file}\0{self.symbol or ''}\0{self.marker}\0{normalized}"
        return hashlib.sha256(material.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        data["scope"] = self.scope.value
        data["color"] = self.color
        data["id"] = self.identity
        return data
