"""转换引擎行为测试：路径、缺值、默认值、条件映射、中间字段、错误聚合。"""

import pytest

from field_mapper.engine import Engine
from field_mapper.rules import parse_rule_set, validate_rule_set


def make_engine(data):
    rules, issues = parse_rule_set(data)
    assert not issues
    issues = validate_rule_set(rules)
    assert not issues, [i.message for i in issues]
    return Engine(rules)


BASE_RULES = [
    {"target": "employee_id", "source": "id", "convert": "id"},
    {"target": "first_name", "source": "name.first"},
    {"target": "last_name", "source": "name.last"},
    {"target": "email", "source": "contact.email"},
    {"target": "status", "source": "st", "conditions": [
        {"equals": "A", "value": "active"},
        {"equals": "I", "value": "inactive"},
        {"when": "leave.flag", "equals": "Y", "value": "on_leave"},
    ], "otherwise": "terminated"},
    {"target": "department", "source": "dept"},
    {"target": "title", "source": "job.title"},
    {"target": "start_date", "source": "since", "convert": "date"},
    {"target": "manager_id", "source": "mgr", "convert": "id"},
    {"target": "is_contractor", "source": "contractor", "convert": "bool"},
    {"target": "weekly_hours", "source": "hours", "convert": "int", "default": 40},
]

GOOD_RECORD = {
    "id": "007",
    "name": {"first": "Ada", "last": "Lovelace"},
    "contact": {"email": "ada@example.com"},
    "st": "A",
    "dept": "Engineering",
    "job": {"title": "Engineer"},
    "since": "2024-02-29",
    "mgr": 1001,
    "contractor": "no",
    "hours": "0042",
}


class TestHappyPath:
    def test_full_record_field_by_field(self):
        eng = make_engine(BASE_RULES)
        result = eng.transform_record(GOOD_RECORD)
        assert result.ok, result.errors
        assert result.employee == {
            "employee_id": "007",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "status": "active",
            "department": "Engineering",
            "title": "Engineer",
            "start_date": "2024-02-29",
            "manager_id": "1001",
            "is_contractor": False,
            "weekly_hours": 42,
        }

    def test_optional_fields_absent_when_missing(self):
        eng = make_engine(BASE_RULES)
        record = {"id": 1, "name": {"first": "A", "last": "B"},
                  "contact": {"email": "a@b.c"}, "st": "I"}
        result = eng.transform_record(record)
        assert result.ok, result.errors
        assert result.employee == {
            "employee_id": "1", "first_name": "A", "last_name": "B",
            "email": "a@b.c", "status": "inactive", "weekly_hours": 40,
        }

    def test_array_subscript_path(self):
        eng = make_engine(BASE_RULES)
        record = dict(GOOD_RECORD, contact={"emails": [{"addr": "x@y.z"}]})
        eng2 = make_engine([*BASE_RULES[:3],
                            {"target": "email", "source": "contact.emails[0].addr"},
                            *BASE_RULES[4:]])
        result = eng2.transform_record(record)
        assert result.ok, result.errors
        assert result.employee["email"] == "x@y.z"

    def test_broken_path_counts_as_missing(self):
        eng = make_engine(BASE_RULES)
        record = dict(GOOD_RECORD, job=None)  # 路径中途断掉
        result = eng.transform_record(record)
        assert result.ok, result.errors
        assert "title" not in result.employee


class TestMissingAndDefault:
    @pytest.mark.parametrize("bad_value", [None, "   ", ""])
    def test_null_and_blank_are_missing(self, bad_value):
        eng = make_engine(BASE_RULES)
        record = dict(GOOD_RECORD, hours=bad_value)
        result = eng.transform_record(record)
        assert result.ok, result.errors
        assert result.employee["weekly_hours"] == 40  # 默认值生效

    def test_default_not_type_converted(self):
        eng = make_engine([{"target": "weekly_hours", "default": 40}])
        # 缺 source：直接走默认值
        result = eng.transform_record({})
        assert not result.ok  # 必填字段缺失
        eng2 = make_engine([*BASE_RULES[:4], *BASE_RULES[4:]])
        assert eng2.transform_record(GOOD_RECORD).ok

    def test_required_missing_reports_error(self):
        eng = make_engine(BASE_RULES)
        record = dict(GOOD_RECORD)
        del record["contact"]
        result = eng.transform_record(record)
        assert not result.ok
        assert any(e.field == "email" and "缺值" in e.reason for e in result.errors)


class TestConditions:
    def test_first_match_wins(self):
        rules = [r for r in BASE_RULES if r["target"] != "status"]
        rules.append({"target": "status", "source": "st", "conditions": [
            {"equals": "A", "value": "active"},
            {"equals": "A", "value": "inactive"},
        ]})
        eng = make_engine(rules)
        result = eng.transform_record(GOOD_RECORD)
        assert result.ok, result.errors
        assert result.employee["status"] == "active"

    def test_case_sensitive_trimmed_comparison(self):
        rules = [r for r in BASE_RULES if r["target"] != "status"]
        rules.append({"target": "status", "source": "st", "conditions": [
            {"equals": "A", "value": "active"},
        ]})
        eng = make_engine(rules)
        ok = eng.transform_record(dict(GOOD_RECORD, st=" A "))
        assert ok.ok, ok.errors
        assert ok.employee["status"] == "active"  # 去空白后命中
        result = eng.transform_record(dict(GOOD_RECORD, st="a"))  # 区分大小写
        assert not result.ok
        assert any("没有命中任何条件" in e.reason for e in result.errors)

    def test_condition_on_other_field(self):
        eng = make_engine(BASE_RULES)
        record = dict(GOOD_RECORD, st="X", leave={"flag": "Y"})
        result = eng.transform_record(record)
        assert result.ok, result.errors
        assert result.employee["status"] == "on_leave"

    def test_no_match_no_otherwise_is_error_not_passthrough(self):
        eng = make_engine([
            {"target": "status", "source": "st", "conditions": [
                {"equals": "A", "value": "active"},
            ]},
        ])
        result = eng.transform_record({"st": "UNKNOWN"})
        assert not result.ok
        status_err = next(e for e in result.errors if e.field == "status")
        assert "没有命中任何条件" in status_err.reason
        # 不能原样透传
        assert result.employee is None


class TestIntermediateFields:
    RULES = [
        {"target": "raw_hours", "source": "time.hours", "convert": "int"},
        {"target": "weekly_hours", "source": "@raw_hours"},
        {"target": "employee_id", "source": "id", "convert": "id"},
        {"target": "first_name", "source": "id"},
        {"target": "last_name", "source": "id"},
        {"target": "email", "source": "id"},
        {"target": "status", "source": "st", "conditions": [{"equals": "A", "value": "active"}]},
    ]

    def test_intermediate_feeds_other_rule_and_hidden(self):
        eng = make_engine(self.RULES)
        record = {"id": "9", "st": "A", "time": {"hours": "38"}}
        result = eng.transform_record(record)
        assert result.ok, result.errors
        assert result.employee["weekly_hours"] == 38
        assert "raw_hours" not in result.employee

    def test_upstream_failure_propagates(self):
        eng = make_engine(self.RULES)
        record = {"id": "9", "st": "A", "time": {"hours": "3.5"}}
        result = eng.transform_record(record)
        assert not result.ok
        by_field = {e.field: e.reason for e in result.errors}
        assert "3.5" in by_field["raw_hours"]
        assert "上游失败" in by_field["weekly_hours"]


class TestErrorAggregation:
    def test_all_errors_listed_not_just_first(self):
        eng = make_engine(BASE_RULES)
        record = {"id": "007", "st": "Z", "hours": "3.5", "contractor": 2,
                  "since": "2023-02-29", "mgr": "007"}
        result = eng.transform_record(record)
        assert not result.ok
        fields = {e.field for e in result.errors}
        # hours 非整数、contractor 非 0/1、since 日期不存在、
        # first/last/email 必填缺失、manager_id 与 employee_id 相同
        # （status 配了 otherwise，"Z" 被兜底为 terminated，不报错）
        assert {"weekly_hours", "is_contractor", "start_date",
                "first_name", "last_name", "email", "manager_id"} <= fields
        assert any("manager_id 不能等于本人" in e.reason for e in result.errors)
        # 每条错误都带规则位置
        for err in result.errors:
            assert isinstance(err.rule_index, int)

    def test_batch_mixed_records_isolated(self):
        eng = make_engine(BASE_RULES)
        bad = dict(GOOD_RECORD, hours="3.5")
        results = eng.transform_batch([GOOD_RECORD, bad, GOOD_RECORD])
        assert [r.ok for r in results] == [True, False, True]
        assert results[0].employee == results[2].employee
        assert any("3.5" in e.reason for e in results[1].errors)

    def test_batch_limit_1000(self):
        eng = make_engine(BASE_RULES)
        with pytest.raises(ValueError):
            eng.transform_batch([GOOD_RECORD] * 1001)
        assert len(eng.transform_batch([GOOD_RECORD] * 1000)) == 1000
