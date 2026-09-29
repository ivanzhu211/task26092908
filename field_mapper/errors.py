"""错误类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldError:
    """单条记录转换时某个字段的错误。"""

    field: str
    rule_index: int
    reason: str


@dataclass
class RecordResult:
    """单条记录的转换结果：成功时 employee 为标准员工结构，否则 errors 列出全部错误。"""

    ok: bool
    employee: dict | None = None
    errors: list[FieldError] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """规则集保存前校验发现的问题。"""

    rule_index: int | None
    field: str | None
    message: str


class RuleSetValidationError(Exception):
    """规则集校验失败，整份拒收。"""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__(f"rule set rejected with {len(issues)} issue(s)")


class RuleSetNotFoundError(Exception):
    """连接器没有已保存的规则集。"""
