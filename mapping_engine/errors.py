"""Exception types for the mapping engine."""

from __future__ import annotations


class MappingEngineError(Exception):
    """Base class for all mapping engine errors."""


class ValidationError(MappingEngineError):
    """Raised when a rule set fails validation and is rejected."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = list(issues)
        super().__init__("; ".join(self.issues))


class ConnectorNotFoundError(MappingEngineError):
    """Raised when no rule set exists for a connector."""
