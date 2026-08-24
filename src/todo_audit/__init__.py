"""todo_audit: scan a codebase for TODO comments, classify and locate them."""

from .comments import DEFAULT_TYPE_BY_MARKER, MARKER_KEYWORDS
from .models import Scope, Todo, TodoType
from .scanner import scan_file, scan_path

# Single source of truth for the version: pyproject.toml reads it from here, and
# `poe sync-version` propagates it to package.json and .claude-plugin/plugin.json.
__version__ = "0.1.0"

__all__ = [
    "Todo",
    "TodoType",
    "Scope",
    "scan_path",
    "scan_file",
    "MARKER_KEYWORDS",
    "DEFAULT_TYPE_BY_MARKER",
    "__version__",
]
