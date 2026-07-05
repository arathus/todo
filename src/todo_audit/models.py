"""Core data types for TODO records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict


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


@dataclass(frozen=True)
class Todo:
    """One detected TODO comment."""

    file: str  # path relative to project root
    line: int  # 1-based line number
    type: TodoType
    scope: Scope
    description: str

    @property
    def color(self) -> str:
        return COLOR_BY_TYPE[self.type]

    @property
    def sort_weight(self) -> int:
        return SORT_WEIGHT[self.type]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        data["scope"] = self.scope.value
        data["color"] = self.color
        return data
