"""规则集模型与保存前整体校验。

规则 JSON 结构（list，顺序即执行顺序）：
    {
      "target": "employee_id",        # 标准字段名或自定义中间字段名
      "source": "emp.id",             # 源路径；以 @ 开头表示引用其他规则的输出
      "convert": "id",                # 可选：date/bool/int/id/status/string
      "default": ...                  # 可选：缺值时兜底，本身须符合目标类型
    }
条件映射规则：
    {
      "target": "status",
      "source": "emp.status_code",    # 可选；condition 省略 when 时用它
      "conditions": [
        {"when": "emp.status_code", "equals": "A", "value": "active"}
      ],
      "otherwise": "inactive"         # 可选兜底；都没有则转换时报错
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ValidationIssue
from .types import CONVERTERS, STATUSES, to_date, to_id_string

# 标准字段名 -> 转换类型
STANDARD_FIELDS: dict[str, str] = {
    "employee_id": "id",
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "status": "status",
    "department": "string",
    "title": "string",
    "start_date": "date",
    "manager_id": "id",
    "is_contractor": "bool",
    "weekly_hours": "int",
}

REQUIRED_FIELDS = ("employee_id", "first_name", "last_name", "email", "status")

MAX_RULES = 500


@dataclass
class Condition:
    """条件映射的一条分支：when 路径的值等于 equals（去空白、区分大小写）时输出 value。"""

    source_path: str | None  # None 表示用所属规则的 source
    equals: str
    value: object


@dataclass
class Rule:
    """单条映射规则。"""

    target: str
    source_path: str | None = None
    convert: str | None = None
    default: object = None
    has_default: bool = False
    conditions: list[Condition] = field(default_factory=list)
    condition_default: object = None
    has_condition_default: bool = False
    index: int = 0  # 在规则集中的位置，用于错误定位

    @property
    def is_standard(self) -> bool:
        return self.target in STANDARD_FIELDS

    @property
    def effective_convert(self) -> str | None:
        """实际生效的转换类型：标准字段固定为其类型，中间字段用规则声明的 convert。"""
        if self.is_standard:
            return STANDARD_FIELDS[self.target]
        return self.convert


def _check_literal(convert: str, value: object) -> str | None:
    """校验默认值/条件结果本身是否符合目标类型的规范形态；返回问题描述或 None。"""
    if convert == "string":
        return None if isinstance(value, str) else "must be a string"
    if convert == "int":
        return None if isinstance(value, int) and not isinstance(value, bool) else "must be an integer"
    if convert == "bool":
        return None if isinstance(value, bool) else "must be a boolean"
    if convert == "status":
        return None if isinstance(value, str) and value in STATUSES else f"must be one of {STATUSES}"
    if convert == "date":
        if not isinstance(value, str):
            return "must be a 'YYYY-MM-DD' string"
        try:
            if to_date(value) != value:
                return "must be in 'YYYY-MM-DD' form"
        except ValueError as exc:
            return str(exc)
        return None
    if convert == "id":
        if not isinstance(value, str):
            return "must be a string"
        return None if to_id_string(value) == value else "must not have surrounding whitespace"
    return None


def parse_rule_set(data: object) -> tuple[list[Rule], list[ValidationIssue]]:
    """把 JSON 规则列表解析为 Rule 对象列表，并收集结构性问题。"""
    issues: list[ValidationIssue] = []
    rules: list[Rule] = []
    if not isinstance(data, list):
        return [], [ValidationIssue(None, None, "rule set must be a JSON array")]
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            issues.append(ValidationIssue(index, None, "rule must be an object"))
            continue
        target = item.get("target")
        if not isinstance(target, str) or not target.strip():
            issues.append(ValidationIssue(index, None, "'target' must be a non-empty string"))
            continue
        target = target.strip()
        rule = Rule(target=target, index=index)
        source = item.get("source")
        if source is not None:
            if not isinstance(source, str) or not source.strip():
                issues.append(ValidationIssue(index, target, "'source' must be a non-empty string"))
            else:
                rule.source_path = source.strip()
        convert = item.get("convert")
        if convert is not None:
            if not isinstance(convert, str):
                issues.append(ValidationIssue(index, target, "'convert' must be a string"))
            else:
                rule.convert = convert
        if "default" in item:
            rule.has_default = True
            rule.default = item["default"]
        raw_conditions = item.get("conditions")
        if raw_conditions is not None:
            if not isinstance(raw_conditions, list) or not raw_conditions:
                issues.append(ValidationIssue(index, target, "'conditions' must be a non-empty array"))
            else:
                for cond_index, raw in enumerate(raw_conditions):
                    if not isinstance(raw, dict):
                        issues.append(ValidationIssue(index, target, f"conditions[{cond_index}] must be an object"))
                        continue
                    when = raw.get("when")
                    if when is not None and (not isinstance(when, str) or not when.strip()):
                        issues.append(ValidationIssue(index, target, f"conditions[{cond_index}].when must be a non-empty string"))
                        continue
                    equals = raw.get("equals")
                    if not isinstance(equals, str):
                        issues.append(ValidationIssue(index, target, f"conditions[{cond_index}].equals must be a string"))
                        continue
                    if "value" not in raw:
                        issues.append(ValidationIssue(index, target, f"conditions[{cond_index}] missing 'value'"))
                        continue
                    rule.conditions.append(Condition(
                        source_path=when.strip() if isinstance(when, str) else None,
                        equals=equals,
                        value=raw["value"],
                    ))
        if "otherwise" in item:
            rule.has_condition_default = True
            rule.condition_default = item["otherwise"]
        rules.append(rule)
    return rules, issues


def _references(rule: Rule) -> list[str]:
    """规则里以 @ 开头的引用（@字段 或 @字段.子路径）。"""
    refs: list[str] = []
    paths: list[str] = []
    if rule.source_path:
        paths.append(rule.source_path)
    paths.extend(c.source_path for c in rule.conditions if c.source_path)
    for path in paths:
        if path.startswith("@"):
            name = path[1:].split(".", 1)[0].split("[", 1)[0]
            if name:
                refs.append(name)
    return refs


def validate_rule_set(rules: list[Rule]) -> list[ValidationIssue]:
    """整体校验，返回全部问题（空列表表示通过）。"""
    issues: list[ValidationIssue] = []

    if len(rules) > MAX_RULES:
        issues.append(ValidationIssue(None, None, f"rule count {len(rules)} exceeds limit {MAX_RULES}"))

    targets: dict[str, int] = {}
    for rule in rules:
        if rule.target in targets:
            issues.append(ValidationIssue(rule.index, rule.target,
                                          f"duplicate target (first defined at rule {targets[rule.target]})"))
        else:
            targets[rule.target] = rule.index

    for rule in rules:
        convert = rule.effective_convert
        if rule.convert is not None and rule.convert not in CONVERTERS:
            issues.append(ValidationIssue(rule.index, rule.target, f"unknown convert type: {rule.convert!r}"))
        if rule.is_standard and rule.convert is not None and rule.convert != STANDARD_FIELDS[rule.target]:
            issues.append(ValidationIssue(rule.index, rule.target,
                                          f"convert {rule.convert!r} does not match standard field type "
                                          f"{STANDARD_FIELDS[rule.target]!r}"))
        if rule.conditions:
            if rule.has_default:
                issues.append(ValidationIssue(rule.index, rule.target,
                                              "'default' cannot be combined with 'conditions' (use 'otherwise')"))
            if rule.convert is not None and not rule.is_standard:
                issues.append(ValidationIssue(rule.index, rule.target,
                                              "'convert' cannot be combined with 'conditions'"))
            for cond in rule.conditions:
                if cond.source_path is None and rule.source_path is None:
                    issues.append(ValidationIssue(rule.index, rule.target,
                                                  "condition without 'when' requires the rule to have 'source'"))
            if convert in CONVERTERS:
                for cond in rule.conditions:
                    problem = _check_literal(convert, cond.value)
                    if problem:
                        issues.append(ValidationIssue(rule.index, rule.target,
                                                      f"condition value {cond.value!r}: {problem}"))
                if rule.has_condition_default:
                    problem = _check_literal(convert, rule.condition_default)
                    if problem:
                        issues.append(ValidationIssue(rule.index, rule.target,
                                                      f"'otherwise' value {rule.condition_default!r}: {problem}"))
        else:
            if rule.source_path is None and not rule.has_default:
                issues.append(ValidationIssue(rule.index, rule.target,
                                              "rule needs 'source', 'default' or 'conditions'"))
            if rule.has_condition_default:
                issues.append(ValidationIssue(rule.index, rule.target,
                                              "'otherwise' requires 'conditions'"))
            if rule.has_default and convert in CONVERTERS:
                problem = _check_literal(convert, rule.default)
                if problem:
                    issues.append(ValidationIssue(rule.index, rule.target,
                                                  f"default value {rule.default!r}: {problem}"))

    # 引用必须指向已定义的字段
    graph: dict[str, list[str]] = {}
    for rule in rules:
        refs = _references(rule)
        graph.setdefault(rule.target, [])
        for ref in refs:
            if ref not in targets:
                issues.append(ValidationIssue(rule.index, rule.target, f"reference to undefined field: @{ref}"))
            elif ref != rule.target:
                graph[rule.target].append(ref)
            else:
                issues.append(ValidationIssue(rule.index, rule.target, f"field references itself: @{ref}"))

    # 引用成环检测（DFS 三色标记）
    color: dict[str, int] = {}  # 0=未访问 1=访问中 2=完成
    reported: set[tuple[str, ...]] = set()

    def visit(node: str, stack: list[str]) -> None:
        color[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if color.get(nxt, 0) == 0:
                visit(nxt, stack)
            elif color.get(nxt) == 1:
                cycle = tuple(stack[stack.index(nxt):] + [nxt])
                if cycle not in reported:
                    reported.add(cycle)
                    issues.append(ValidationIssue(targets.get(nxt), nxt,
                                                  "circular reference: " + " -> ".join(cycle)))
        stack.pop()
        color[node] = 2

    for name in graph:
        if color.get(name, 0) == 0:
            visit(name, [])

    return issues
