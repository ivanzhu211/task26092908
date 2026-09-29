"""转换引擎：按规则集把源记录转为标准员工结构。"""

from __future__ import annotations

from .errors import FieldError, RecordResult
from .paths import MISSING, extract, parse_path
from .rules import REQUIRED_FIELDS, STANDARD_FIELDS, Rule
from .types import CONVERTERS

MAX_BATCH = 1000


class _UpstreamFailed(Exception):
    """内部信号：引用的上游字段转换失败。"""

    def __init__(self, upstream: str) -> None:
        self.upstream = upstream
        super().__init__(upstream)


class Engine:
    """对一份已校验的规则集做逐条转换。批次内规则集版本固定。"""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = list(rules)

    def transform_record(self, record: dict) -> RecordResult:
        """转换单条记录，失败时列出全部错误，依赖失败字段的字段报"上游失败"。"""
        values: dict[str, object] = {}   # 所有已产出的字段（含中间字段）
        failed: set[str] = set()
        errors: list[FieldError] = []

        def resolve(path: str):
            """解析路径：@ 开头引用其他规则输出，否则从源记录取值。"""
            if path.startswith("@"):
                segments = parse_path(path[1:])
                name = segments[0]
                if name in failed:
                    raise _UpstreamFailed(str(name))
                if name not in values:
                    return MISSING
                current: object = values[name]
                rest = segments[1:]
            else:
                segments = parse_path(path)
                current = record
                rest = segments
            for segment in rest:
                if isinstance(segment, int):
                    if not isinstance(current, list) or segment >= len(current):
                        return MISSING
                    current = current[segment]
                else:
                    if not isinstance(current, dict) or segment not in current:
                        return MISSING
                    current = current[segment]
            if current is None or (isinstance(current, str) and not current.strip()):
                return MISSING
            return current

        for rule in self._rules:
            try:
                result = self._apply_rule(rule, resolve)
            except _UpstreamFailed as exc:
                failed.add(rule.target)
                errors.append(FieldError(rule.target, rule.index,
                                         f"上游失败：依赖字段 {exc.upstream} 转换失败"))
                continue
            except ValueError as exc:
                failed.add(rule.target)
                errors.append(FieldError(rule.target, rule.index, str(exc)))
                continue
            if result is not MISSING:
                values[rule.target] = result

        for name in REQUIRED_FIELDS:
            if name not in values and name not in failed:
                errors.append(FieldError(name, -1, "必填字段最终缺值"))

        employee = {name: values[name] for name in STANDARD_FIELDS if name in values}
        if ("manager_id" in employee and "employee_id" in employee
                and employee["manager_id"] == employee["employee_id"]):
            errors.append(FieldError("manager_id", -1, "manager_id 不能等于本人的 employee_id"))

        if errors:
            return RecordResult(ok=False, errors=errors)
        return RecordResult(ok=True, employee=employee)

    def _apply_rule(self, rule: Rule, resolve) -> object:
        """执行单条规则，返回输出值；MISSING 表示该规则无输出（可选字段缺值）。"""
        if rule.conditions:
            for cond in rule.conditions:
                path = cond.source_path or rule.source_path
                value = resolve(path)
                if value is MISSING:
                    continue
                text = value.strip() if isinstance(value, str) else str(value)
                if text == cond.equals:
                    return cond.value
            if rule.has_condition_default:
                return rule.condition_default
            raise ValueError("没有命中任何条件，且未配置 otherwise 兜底")

        value = resolve(rule.source_path) if rule.source_path else MISSING
        if value is MISSING:
            if rule.has_default:
                return rule.default
            if rule.target in REQUIRED_FIELDS:
                raise ValueError("必填字段缺值，且未配置默认值")
            return MISSING
        convert = rule.effective_convert
        if convert is None:
            return value
        try:
            return CONVERTERS[convert](value)
        except ValueError as exc:
            raise ValueError(f"类型转换失败（{convert}）：{exc}")

    def transform_batch(self, records: list[dict]) -> list[RecordResult]:
        """逐条转换，最多 1000 条；单条失败不影响其他记录。"""
        if len(records) > MAX_BATCH:
            raise ValueError(f"batch size {len(records)} exceeds limit {MAX_BATCH}")
        return [self.transform_record(record) for record in records]
