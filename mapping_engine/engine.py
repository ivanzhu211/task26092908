"""Per-record transform engine."""

from __future__ import annotations

from typing import Any

from .convert import convert
from .models import (
    FIELD_TYPES,
    MAX_BATCH_SIZE,
    REQUIRED_FIELDS,
    STANDARD_FIELDS,
    BatchResult,
    FieldError,
    RecordResult,
    Rule,
    RuleSet,
)
from .paths import MISSING, extract, is_missing
from .validate import REF_PREFIX


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).strip()


class _RecordContext:
    """Evaluates rules for one record with memoized dependency resolution."""

    def __init__(self, ruleset: RuleSet, record: dict[str, Any]) -> None:
        self.ruleset = ruleset
        self.record = record
        self.by_target = {rule.target: i for i, rule in enumerate(ruleset.rules)}
        self.status: dict[str, str] = {}  # target -> ok | missing | failed
        self.values: dict[str, Any] = {}
        self.errors: list[FieldError] = []

    def run(self) -> RecordResult:
        for idx in range(len(self.ruleset.rules)):
            self.resolve(idx)
        for req in REQUIRED_FIELDS:
            if req not in self.values:
                if self.status.get(req) != "failed":
                    self.errors.append(
                        FieldError(req, self.by_target.get(req), "required field missing")
                    )
                    self.status[req] = "failed"
        self._check_manager_not_self()
        employee = {
            t: v for t, v in self.values.items() if t in STANDARD_FIELDS
        }
        return RecordResult(ok=not self.errors, employee=employee, errors=self.errors)

    def resolve(self, idx: int) -> None:
        rule = self.ruleset.rules[idx]
        if rule.target in self.status:
            return
        self.status[rule.target] = "failed"  # guard; overwritten on success
        try:
            value = self.evaluate(rule, idx)
        except _UpstreamFailed as exc:
            self.errors.append(
                FieldError(rule.target, idx, f"upstream failed: {exc}")
            )
            return
        except _RuleFailed as exc:
            self.errors.append(FieldError(rule.target, idx, str(exc)))
            return
        if is_missing(value):
            if rule.target in REQUIRED_FIELDS:
                self.errors.append(
                    FieldError(rule.target, idx, "required field missing")
                )
                return
            self.status[rule.target] = "missing"
            return
        self.values[rule.target] = value
        self.status[rule.target] = "ok"

    def evaluate(self, rule: Rule, idx: int) -> Any:
        type_name = rule.transform or FIELD_TYPES.get(rule.target)
        if rule.conditions:
            for cond in rule.conditions:
                actual = self.extract_value(cond.source_path, idx)
                if is_missing(actual):
                    continue
                if _as_text(actual) == _as_text(cond.equals):
                    return self.convert_value(cond.value, type_name)
            if rule.has_default:
                return self.convert_value(rule.default, type_name)
            raise _RuleFailed("no condition matched and no default provided")
        raw = self.extract_value(rule.source_path, idx) if rule.source_path else MISSING
        if is_missing(raw):
            if rule.has_default:
                return self.convert_value(rule.default, type_name)
            return MISSING
        return self.convert_value(raw, type_name)

    def extract_value(self, source_path: str | None, idx: int) -> Any:
        if source_path is None:
            return MISSING
        if source_path.startswith(REF_PREFIX):
            name = source_path[len(REF_PREFIX):]
            dep_idx = self.by_target.get(name)
            if dep_idx is None:
                raise _RuleFailed(f"references undefined field {name!r}")
            self.resolve(dep_idx)
            dep_status = self.status.get(name)
            if dep_status == "failed":
                raise _UpstreamFailed(name)
            if dep_status == "ok":
                return self.values[name]
            return MISSING
        return extract(self.record, source_path)

    def convert_value(self, value: Any, type_name: str | None) -> Any:
        if type_name is None:
            return value
        try:
            return convert(value, type_name)
        except ValueError as exc:
            raise _RuleFailed(str(exc)) from exc

    def _check_manager_not_self(self) -> None:
        mgr = self.values.get("manager_id")
        emp = self.values.get("employee_id")
        if mgr is not None and emp is not None and mgr == emp:
            idx = self.by_target.get("manager_id")
            self.errors.append(
                FieldError("manager_id", idx, "manager_id equals own employee_id")
            )
            self.status["manager_id"] = "failed"


class _RuleFailed(Exception):
    pass


class _UpstreamFailed(Exception):
    pass


def transform_record(ruleset: RuleSet, record: dict[str, Any]) -> RecordResult:
    """Transform one source record; collects all field errors."""
    return _RecordContext(ruleset, record).run()


def transform_batch(ruleset: RuleSet, records: list[dict[str, Any]]) -> BatchResult:
    """Transform a batch; one bad record does not affect others."""
    if len(records) > MAX_BATCH_SIZE:
        raise ValueError(
            f"batch has {len(records)} records, max is {MAX_BATCH_SIZE}"
        )
    return BatchResult(results=[transform_record(ruleset, r) for r in records])
