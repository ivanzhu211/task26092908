"""规则集保存校验与 SQLite 持久化测试。"""

import time

import pytest

from field_mapper import Engine, RuleSetNotFoundError, RuleSetStore, RuleSetValidationError


@pytest.fixture
def store(tmp_path):
    return RuleSetStore(str(tmp_path / "rules.db"))


GOOD = [
    {"target": "employee_id", "source": "id", "convert": "id"},
    {"target": "first_name", "source": "fn"},
    {"target": "last_name", "source": "ln"},
    {"target": "email", "source": "em"},
    {"target": "status", "source": "st", "conditions": [{"equals": "A", "value": "active"}]},
]


class TestSaveRejection:
    def test_too_many_rules(self, store):
        data = [{"target": f"f{i}", "source": "s"} for i in range(501)]
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", data)
        assert any("exceeds limit" in i.message for i in exc.value.issues)

    def test_exactly_500_allowed(self, store):
        data = [*GOOD, *[{"target": f"f{i}", "source": "s"} for i in range(495)]]
        assert store.save("c", data) == 1

    def test_duplicate_target(self, store):
        data = [{"target": "a", "source": "x"}, {"target": "a", "source": "y"}]
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", data)
        assert any("duplicate target" in i.message for i in exc.value.issues)

    def test_undefined_reference(self, store):
        data = [{"target": "a", "source": "@ghost"}]
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", data)
        assert any("undefined field" in i.message for i in exc.value.issues)

    def test_circular_reference(self, store):
        data = [
            {"target": "a", "source": "@b"},
            {"target": "b", "source": "@c"},
            {"target": "c", "source": "@a"},
        ]
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", data)
        assert any("circular reference" in i.message for i in exc.value.issues)

    def test_self_reference(self, store):
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", [{"target": "a", "source": "@a"}])
        assert any("references itself" in i.message for i in exc.value.issues)

    def test_unknown_convert(self, store):
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", [{"target": "a", "source": "x", "convert": "magic"}])
        assert any("unknown convert type" in i.message for i in exc.value.issues)

    @pytest.mark.parametrize("rule", [
        {"target": "weekly_hours", "source": "h", "default": "40"},        # 默认值应是整数
        {"target": "is_contractor", "source": "c", "default": "yes"},      # 默认值应是布尔
        {"target": "start_date", "source": "d", "default": "2/3/2024"},    # 默认值应是 YYYY-MM-DD
        {"target": "status", "conditions": [{"equals": "A", "value": "ACTIVE"}]},  # 条件结果非法
        {"target": "status", "conditions": [{"equals": "A", "value": "active"}],
         "otherwise": "quit"},                                             # 兜底结果非法
    ])
    def test_literal_type_mismatch(self, store, rule):
        with pytest.raises(RuleSetValidationError):
            store.save("c", [rule])

    def test_all_issues_listed_with_positions(self, store):
        data = [
            {"target": "a", "source": "@ghost"},                       # 引用未定义
            {"target": "b", "source": "x", "convert": "magic"},        # 未知转换
            {"target": "a", "source": "y"},                            # 重复
        ]
        with pytest.raises(RuleSetValidationError) as exc:
            store.save("c", data)
        issues = exc.value.issues
        assert len(issues) >= 3
        assert all(i.rule_index is not None for i in issues)
        assert {i.rule_index for i in issues} == {0, 1, 2}

    def test_rejection_keeps_old_version(self, store):
        store.save("c", GOOD)
        assert store.version("c") == 1
        with pytest.raises(RuleSetValidationError):
            store.save("c", [{"target": "a", "source": "@ghost"}])
        assert store.version("c") == 1  # 旧版本继续生效
        rules = store.load("c")
        assert [r.target for r in rules] == [r["target"] for r in GOOD]

    def test_structural_errors_rejected(self, store):
        with pytest.raises(RuleSetValidationError):
            store.save("c", "not-a-list")
        with pytest.raises(RuleSetValidationError):
            store.save("c", [{"no_target": 1}])
        with pytest.raises(RuleSetValidationError):
            store.save("c", [{"target": "a", "conditions": [{"equals": 1, "value": "x"}]}])


class TestLoad:
    def test_not_found(self, store):
        with pytest.raises(RuleSetNotFoundError):
            store.load("nobody")

    def test_version_increments(self, store):
        assert store.save("c", GOOD) == 1
        assert store.save("c", GOOD) == 2
        assert store.version("c") == 2

    def test_connectors_isolated(self, store):
        store.save("a", GOOD)
        with pytest.raises(RuleSetNotFoundError):
            store.load("b")


class TestVersionIsolation:
    def test_running_batch_uses_start_version(self, store):
        """转换进行中保存了新规则集，正在跑的批仍按开始时的版本。"""
        store.save("c", GOOD)
        engine = Engine(store.load("c"))  # 批次开始：锁定当时版本
        record = {"id": "1", "fn": "A", "ln": "B", "em": "a@b.c", "st": "A"}

        # 中途有人保存了语义不同的新规则集
        new_rules = [dict(r) for r in GOOD]
        new_rules[4] = {"target": "status", "source": "st",
                        "conditions": [{"equals": "A", "value": "on_leave"}]}
        store.save("c", new_rules)

        results = engine.transform_batch([record, record])
        assert all(r.ok for r in results)
        assert all(r.employee["status"] == "active" for r in results)  # 仍按旧版本

        fresh = Engine(store.load("c"))  # 下一批用新版本
        assert fresh.transform_record(record).employee["status"] == "on_leave"


class TestPerformance:
    def test_500_rules_1000_records_under_5s(self, store):
        rules = [*GOOD]
        for i in range(495):
            rules.append({"target": f"tmp_{i}", "source": f"extra.f{i}",
                          "convert": "string", "default": f"d{i}"})
        store.save("c", rules)
        engine = Engine(store.load("c"))
        record = {"id": "1", "fn": "A", "ln": "B", "em": "a@b.c", "st": "A",
                  "extra": {f"f{i}": f"v{i}" for i in range(495)}}
        started = time.monotonic()
        results = engine.transform_batch([record] * 1000)
        elapsed = time.monotonic() - started
        assert all(r.ok for r in results)
        assert elapsed < 5, f"took {elapsed:.2f}s"
