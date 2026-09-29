"""端到端验收：保存规则集 -> 加载 -> 一批混有好坏记录 -> 逐字段核对期望。"""

import pytest

from field_mapper import Engine, RuleSetStore


@pytest.fixture
def engine(tmp_path):
    store = RuleSetStore(str(tmp_path / "rules.db"))
    store.save("workday", [
        {"target": "employee_id", "source": "worker.id", "convert": "id"},
        {"target": "first_name", "source": "worker.name.given"},
        {"target": "last_name", "source": "worker.name.family"},
        {"target": "email", "source": "worker.contacts[0].email"},
        {"target": "status", "source": "worker.status_code", "conditions": [
            {"equals": "A", "value": "active"},
            {"equals": "T", "value": "terminated"},
            {"when": "worker.leave", "equals": "Y", "value": "on_leave"},
        ], "otherwise": "inactive"},
        {"target": "department", "source": "worker.org.dept"},
        {"target": "title", "source": "worker.job.title"},
        {"target": "start_date", "source": "worker.hired", "convert": "date"},
        {"target": "manager_id", "source": "worker.mgr_id", "convert": "id"},
        {"target": "is_contractor", "source": "worker.flags.contractor", "convert": "bool"},
        {"target": "weekly_hours", "source": "worker.schedule.hours", "convert": "int",
         "default": 40},
    ])
    return Engine(store.load("workday"))


def test_mixed_batch_exact_expectations(engine):
    records = [
        # 0: 完整好记录（含闰年、前导零、跨日时区、数字 id）
        {"worker": {
            "id": "0042",
            "name": {"given": "Ada", "family": "Lovelace"},
            "contacts": [{"email": "ada@example.com"}],
            "status_code": "A",
            "org": {"dept": "Engineering"},
            "job": {"title": "Engineer"},
            "hired": "2024-03-01T00:30:00+08:00",  # UTC 仍是 2024-02-29
            "mgr_id": 1001,
            "flags": {"contractor": "no"},
            "schedule": {"hours": "0040"},
        }},
        # 1: 多处错误的坏记录
        {"worker": {
            "id": "0043",
            "status_code": "UNKNOWN_BUT_FALLBACK",
            "hired": "2023-02-29",       # 不存在的日期
            "mgr_id": "0043",            # 等于本人
            "flags": {"contractor": 2},  # 非 0 非 1
            "schedule": {"hours": "3.5"},
        }},
        # 2: 只带必填项 + 条件判断其他字段命中 on_leave
        {"worker": {
            "id": 7,
            "name": {"given": "Grace", "family": "Hopper"},
            "contacts": [{"email": "grace@example.com"}],
            "status_code": "X",
            "leave": "Y",
        }},
    ]

    results = engine.transform_batch(records)
    assert [r.ok for r in results] == [True, False, True]

    assert results[0].employee == {
        "employee_id": "0042",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "status": "active",
        "department": "Engineering",
        "title": "Engineer",
        "start_date": "2024-02-29",
        "manager_id": "1001",
        "is_contractor": False,
        "weekly_hours": 40,
    }

    errors = {e.field: e.reason for e in results[1].errors}
    assert "不存在" in errors["start_date"] or "does not exist" in errors["start_date"]
    assert "manager_id 不能等于本人" in errors["manager_id"]
    assert "0 or 1" in errors["is_contractor"]
    assert "3.5" in errors["weekly_hours"]
    assert "必填" in errors["first_name"]
    assert "必填" in errors["last_name"]
    assert "必填" in errors["email"]
    assert "status" not in errors  # otherwise 兜底为 inactive

    assert results[2].employee == {
        "employee_id": "7",
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace@example.com",
        "status": "on_leave",
        "weekly_hours": 40,
    }
