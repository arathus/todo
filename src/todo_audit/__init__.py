"""todo_audit: scan a codebase for TODO comments, classify and locate them."""

from .models import Scope, Todo, TodoType
from .scanner import scan_file, scan_path

__all__ = ["Todo", "TodoType", "Scope", "scan_path", "scan_file"]
__version__ = "0.1.0"
