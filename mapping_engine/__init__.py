"""Field mapping engine library for the integration gateway."""

from .engine import transform_batch, transform_record
from .errors import ConnectorNotFoundError, MappingEngineError, ValidationError
from .models import (
    BatchResult,
    FieldError,
    RecordResult,
    Rule,
    RuleSet,
    Condition,
)
from .store import RuleSetStore

__all__ = [
    "BatchResult",
    "Condition",
    "ConnectorNotFoundError",
    "FieldError",
    "MappingEngineError",
    "RecordResult",
    "Rule",
    "RuleSet",
    "RuleSetStore",
    "ValidationError",
    "transform_batch",
    "transform_record",
]
