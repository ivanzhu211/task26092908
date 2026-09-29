"""Record and batch transformation tests with exact expected outputs."""

import pytest

from mapping_engine import (
    Condition,
    Rule,
    RuleSet,
    transform_batch,
    transform_record,
)


def make_ruleset():
    return RuleSet(
        connector="acme",
        version=1,
        rules=(
            Rule(target="employee_id", source_path="emp.id", transform="id_string"),
            Rule(target="first_name", source_path="name.first"),
            Rule(target="last_name", source_path="name.last"),
            Rule(target="email", source_path="contact.email"),
            Rule(
                target="status",
                conditions=(
                    Condition("state", "A", "active"),
                    Condition("state", "T", "terminated"),
                    Condition("state", "L", "on_leave"),
                ),
                has_default=True,
                default="inactive",
            ),
            Rule(target="department", source_path="dept"),
            Rule(target="title", source_path="job.title"),
            Rule(target="start_date", source_path="hired", transform="date"),
            Rule(target="manager_id", source_path="mgr", transform="id_string"),
            Rule(target="is_contractor", source_path="contractor", transform="bool"),
            Rule(
                target="weekly_hours",
                source_path="hours",
                transform="int",
                has_default=True,
                default=40,
            ),
        ),
    )


GOOD_RECORD = {
    "emp": {"id": "0076"},
    "name": {"first": "Ada", "last": "Lovelace"},
    "contact": {"email": "ada@example.com"},
    "state": "A",
    "dept": "Engineering",
    "job": {"title": "Analyst"},
    "hired": "2/29/2024",
    "mgr": 1001,
    "contractor": "no",
    "hours": "0042",
}

GOOD_EMPLOYEE = {
    "employee_id": "0076",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "status": "active",
    "department": "Engineering",
    "title": "Analyst",
    "start_date": "2024-02-29",
    "manager_id": "1001",
    "is_contractor": False,
    "weekly_hours": 42,
}


def test_good_record_exact_output():
    result = transform_record(make_ruleset(), GOOD_RECORD)
    assert result.ok, result.errors
    assert result.employee == GOOD_EMPLOYEE


def test_optional_fields_absent_when_missing():
    record = {
        "emp": {"id": 7},
        "name": {"first": "Grace", "last": "Hopper"},
        "contact": {"email": "g@example.com"},
        "state": "T",
    }
    result = transform_record(make_ruleset(), record)
    assert result.ok, result.errors
    assert result.employee == {
        "employee_id": "7",
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "g@example.com",
        "status": "terminated",
        "weekly_hours": 40,
    }


def test_default_only_applies_when_missing():
    rs = make_ruleset()
    # hours present but blank string -> missing -> default
    rec = dict(GOOD_RECORD, hours="   ")
    assert transform_record(rs, rec).employee["weekly_hours"] == 40
    # hours present -> default not used
    rec = dict(GOOD_RECORD, hours="35")
    assert transform_record(rs, rec).employee["weekly_hours"] == 35


def test_condition_first_match_wins_and_case_sensitive():
    rules = (
        Rule(target="employee_id", source_path="id"),
        Rule(target="first_name", source_path="id"),
        Rule(target="last_name", source_path="id"),
        Rule(target="email", source_path="id"),
        Rule(
            target="status",
            conditions=(
                Condition("s", "A", "active"),
                Condition("s", "A", "terminated"),
            ),
        ),
    )
    rs = RuleSet("c", 1, rules)
    rec = {"id": "x", "s": "A"}
    assert transform_record(rs, rec).employee["status"] == "active"
    # case-sensitive: "a" does not match "A"
    rec = {"id": "x", "s": "a"}
    assert not transform_record(rs, rec).ok
    # trimmed text comparison
    rec = {"id": "x", "s": "  A  "}
    assert transform_record(rs, rec).employee["status"] == "active"


def test_condition_no_match_no_default_is_error_not_passthrough():
    rules = (
        Rule(target="employee_id", source_path="id"),
        Rule(target="first_name", source_path="id"),
        Rule(target="last_name", source_path="id"),
        Rule(target="email", source_path="id"),
        Rule(target="status", conditions=(Condition("s", "A", "active"),)),
    )
    rs = RuleSet("c", 1, rules)
    result = transform_record(rs, {"id": "x", "s": "UNKNOWN"})
    assert not result.ok
    err = next(e for e in result.errors if e.field == "status")
    assert "no condition matched" in err.reason
    assert "status" not in result.employee  # never passed through raw


def test_condition_on_other_source_field():
    rules = (
        Rule(target="employee_id", source_path="id"),
        Rule(target="first_name", source_path="id"),
        Rule(target="last_name", source_path="id"),
        Rule(target="email", source_path="id"),
        Rule(target="status", has_default=True, default="active"),
        Rule(
            target="is_contractor",
            source_path="pay.type",
            conditions=(Condition("pay.kind", "contract", "true"),),
            has_default=True,
            default="false",
        ),
    )
    rs = RuleSet("c", 1, rules)
    rec = {"id": "x", "pay": {"kind": "contract", "type": "ignored"}}
    assert transform_record(rs, rec).employee["is_contractor"] is True
    rec = {"id": "x", "pay": {"kind": "salary", "type": "true"}}
    assert transform_record(rs, rec).employee["is_contractor"] is False


def test_all_errors_collected_not_just_first():
    record = {
        "emp": {"id": "1"},
        "state": "BOGUS_STATE_NO_MATCH_NO_DEFAULT",
        "hours": "3.5",
        "contractor": 7,
        "hired": "2023-02-29",
        # first_name, last_name, email missing
    }
    rules = RuleSet(
        "c",
        1,
        (
            Rule(target="employee_id", source_path="emp.id", transform="id_string"),
            Rule(target="first_name", source_path="name.first"),
            Rule(target="last_name", source_path="name.last"),
            Rule(target="email", source_path="contact.email"),
            Rule(target="status", conditions=(Condition("state", "A", "active"),)),
            Rule(target="start_date", source_path="hired", transform="date"),
            Rule(target="is_contractor", source_path="contractor", transform="bool"),
            Rule(target="weekly_hours", source_path="hours", transform="int"),
        ),
    )
    result = transform_record(rules, record)
    assert not result.ok
    fields = {e.field for e in result.errors}
    assert fields == {
        "first_name",
        "last_name",
        "email",
        "status",
        "start_date",
        "is_contractor",
        "weekly_hours",
    }
    for e in result.errors:
        assert e.rule_index is not None and e.reason


def test_upstream_failure_propagates():
    rules = RuleSet(
        "c",
        1,
        (
            Rule(target="employee_id", source_path="id"),
            Rule(target="first_name", source_path="id"),
            Rule(target="last_name", source_path="id"),
            Rule(target="email", source_path="id"),
            Rule(target="status", has_default=True, default="active"),
            Rule(target="dept_code", source_path="dept", transform="int"),
            Rule(target="department", source_path="$dept_code"),
            Rule(target="dept_label", source_path="$dept_code"),
            Rule(target="title", source_path="$dept_label"),
        ),
    )
    result = transform_record(rules, {"id": "e1", "dept": "not-a-number"})
    assert not result.ok
    by_field = {e.field: e for e in result.errors}
    assert "not-a-number" in by_field["dept_code"].reason or "integer" in by_field["dept_code"].reason
    assert "upstream failed" in by_field["department"].reason
    assert "upstream failed" in by_field["dept_label"].reason
    assert "upstream failed" in by_field["title"].reason


def test_intermediate_fields_not_in_output():
    rules = RuleSet(
        "c",
        1,
        (
            Rule(target="employee_id", source_path="id"),
            Rule(target="first_name", source_path="id"),
            Rule(target="last_name", source_path="id"),
            Rule(target="email", source_path="id"),
            Rule(target="status", has_default=True, default="active"),
            Rule(target="raw_dept", source_path="dept"),
            Rule(target="department", source_path="$raw_dept"),
        ),
    )
    result = transform_record(rules, {"id": "e1", "dept": "Eng"})
    assert result.ok
    assert result.employee["department"] == "Eng"
    assert "raw_dept" not in result.employee


def test_manager_cannot_be_self():
    result = transform_record(make_ruleset(), dict(GOOD_RECORD, mgr="0076"))
    assert not result.ok
    err = next(e for e in result.errors if e.field == "manager_id")
    assert "own employee_id" in err.reason


def test_mixed_batch_exact_results():
    rs = make_ruleset()
    good2 = dict(GOOD_RECORD)
    good2["emp"] = {"id": 2002}
    good2["state"] = "L"
    good2["hired"] = 20240115
    bad = {"emp": {"id": "3"}, "hours": "3.5", "contractor": "maybe", "state": "?"}

    batch = transform_batch(rs, [GOOD_RECORD, bad, good2])
    assert batch.succeeded == 2 and batch.failed == 1

    assert batch.results[0].ok
    assert batch.results[0].employee == GOOD_EMPLOYEE

    bad_result = batch.results[1]
    assert not bad_result.ok
    assert {e.field for e in bad_result.errors} >= {
        "first_name", "last_name", "email", "weekly_hours", "is_contractor",
    }
    # "state": "?" matches no condition but falls back to the default
    assert bad_result.employee["status"] == "inactive"

    assert batch.results[2].ok
    assert batch.results[2].employee == dict(
        GOOD_EMPLOYEE,
        employee_id="2002",
        status="on_leave",
        start_date="2024-01-15",
    )


def test_batch_size_limit():
    rs = make_ruleset()
    with pytest.raises(ValueError):
        transform_batch(rs, [dict(GOOD_RECORD)] * 1001)
    batch = transform_batch(rs, [dict(GOOD_RECORD)] * 1000)
    assert batch.succeeded == 1000


def test_missing_required_field_without_rule():
    rules = RuleSet(
        "c",
        1,
        (
            Rule(target="employee_id", source_path="id"),
            Rule(target="status", has_default=True, default="active"),
        ),
    )
    result = transform_record(rules, {"id": "e1"})
    assert not result.ok
    missing = {e.field for e in result.errors}
    assert {"first_name", "last_name", "email"} <= missing
