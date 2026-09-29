"""Data models: rules, rule sets, and transform results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Standard employee fields
REQUIRED_FIELDS = ("employee_id", "first_name", "last_name", "email", "status")
OPTIONAL_FIELDS = (
    "department",
    "title",
    "start_date",
    "manager_id",
    "is_contractor",
    "weekly_hours",
)
STANDARD_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

# Target type per standard field
FIELD_TYPES: dict[str, str] = {
    "employee_id": "id_string",
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "status": "status",
    "department": "string",
    "title": "string",
    "start_date": "date",
    "manager_id": "id_string",
    "is_contractor": "bool",
    "weekly_hours": "int",
}

STATUS_VALUES = ("active", "inactive", "terminated", "on_leave")

MAX_RULES = 500
MAX_BATCH_SIZE = 1000


@dataclass(frozen=True)
class Condition:
    """One conditional mapping branch.

    Compares a source-record field (or another rule output) against ``equals``
    using trimmed, case-sensitive text comparison; on match, outputs ``value``.
    """

    source_path: str
    equals: Any
    value: Any


@dataclass(frozen=True)
class Rule:
    """A single mapping rule.

    - target: standard field name or a custom intermediate field name.
    - source_path: path into the source record (None if rule only uses
      conditions/default).
    - transform: optional type conversion name.
    - default: value used when the extracted value is missing.
    - conditions: ordered conditional branches; first match wins.
    """

    target: str
    source_path: Optional[str] = None
    transform: Optional[str] = None
    default: Any = None
    has_default: bool = False
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class RuleSet:
    """An immutable, validated set of rules for one connector."""

    connector: str
    version: int
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class FieldError:
    """One field-level error during record transformation."""

    field: str
    rule_index: Optional[int]
    reason: str


@dataclass
class RecordResult:
    """Transform result for a single source record."""

    ok: bool
    employee: dict[str, Any] = field(default_factory=dict)
    errors: list[FieldError] = field(default_factory=list)


@dataclass
class BatchResult:
    """Transform result for a batch of records."""

    results: list[RecordResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def rule_from_dict(data: dict[str, Any]) -> "Rule":
    """Parse a rule from its JSON dict form."""
    conditions = tuple(
        Condition(
            source_path=c["source"],
            equals=c.get("equals"),
            value=c.get("value"),
        )
        for c in data.get("conditions", [])
    )
    return Rule(
        target=data["target"],
        source_path=data.get("source"),
        transform=data.get("transform"),
        default=data.get("default"),
        has_default="default" in data,
        conditions=conditions,
    )


def rule_to_dict(rule: "Rule") -> dict[str, Any]:
    """Serialize a rule to its JSON dict form."""
    data: dict[str, Any] = {"target": rule.target}
    if rule.source_path is not None:
        data["source"] = rule.source_path
    if rule.transform is not None:
        data["transform"] = rule.transform
    if rule.has_default:
        data["default"] = rule.default
    if rule.conditions:
        data["conditions"] = [
            {"source": c.source_path, "equals": c.equals, "value": c.value}
            for c in rule.conditions
        ]
    return data
