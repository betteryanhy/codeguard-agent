"""Abstract base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any


class ToolResult:
    """Standard result container for all tool executions."""

    def __init__(self, success: bool, data: Any = None, error: str = ""):
        self.success = success
        self.data = data
        self.error = error

    @classmethod
    def ok(cls, data: Any = None) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, error=error)

    def __repr__(self) -> str:
        if self.success:
            return f"ToolResult(ok, data={self.data!r})"
        return f"ToolResult(fail, error={self.error!r})"


class BaseTool(ABC):
    """Abstract base for all Agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier used by the planner."""
        ...

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """Execute the tool with given parameters."""
        ...
