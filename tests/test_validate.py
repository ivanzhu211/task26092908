"""Save-time validation: every rejection category."""

import pytest

from mapping_engine import Condition, Rule, RuleSetStore, ValidationError
from mapping_engine.validate import validate_rules


def base_rules():
    return [
        {"target": "employee_id", "source": "id"},
        {"target": "first_name", "source": "fn"},
        {"target": "last_name", "source": "ln"},
        {"target": "email", "source": "em"},
        {"target": "status", "default": "active"},
    ]


class TestRejections:
    def test_too_many_rules(self):
        rules = [Rule(target=f"f{i}") for i in range(501)]
        issues = validate_rules(rules)
        assert any("500" in i for i in issues)
        assert validate_rules([Rule(target=f"f{i}") for i in range(500)]) == []

    def test_duplicate_target(self):
        issues = validate_rules([Rule(target="email"), Rule(target="email")])
        assert any("more than once" in i for i in issues)

    def test_undefined_reference(self):
        issues = validate_rules([Rule(target="email", source_path="$ghost")])
        assert any("undefined field 'ghost'" in i for i in issues)

    def test_direct_cycle(self):
        rules = [
            Rule(target="a", source_path="$b"),
            Rule(target="b", source_path="$a"),
        ]
        assert any("circular" in i for i in validate_rules(rules))

    def test_indirect_cycle(self):
        rules = [
            Rule(target="a", source_path="$b"),
            Rule(target="b", source_path="$c"),
            Rule(target="c", source_path="$a"),
        ]
        assert any("circular" in i for i in validate_rules(rules))

    def test_self_cycle(self):
        assert any("circular" in i for i in validate_rules([Rule(target="a", source_path="$a")]))

    def test_unknown_transform(self):
        issues = validate_rules([Rule(target="email", transform="teleport")])
        assert any("unknown transform" in i for i in issues)

    def test_bad_default_type(self):
        issues = validate_rules(
            [Rule(target="weekly_hours", has_default=True, default="3.5")]
        )
        assert any("default" in i for i in issues)

    def test_bad_condition_value_type(self):
        rules = [Rule(target="status", conditions=(Condition("s", "A", "bogus"),))]
        issues = validate_rules(rules)
        assert any("condition[0]" in i for i in issues)

    def test_bad_bool_default(self):
        rules = [Rule(target="is_contractor", has_default=True, default="maybe")]
        assert validate_rules(rules)

    def test_all_issues_listed_at_once(self):
        rules = [
            Rule(target="email"),
            Rule(target="email"),
            Rule(target="x", source_path="$ghost"),
            Rule(target="weekly_hours", has_default=True, default="3.5"),
        ]
        issues = validate_rules(rules)
        assert len(issues) >= 3

    def test_valid_set_passes(self):
        rules = [
            Rule(target="full_name", source_path="name"),
            Rule(target="first_name", source_path="$full_name"),
            Rule(
                target="status",
                conditions=(Condition("s", "A", "active"),),
                has_default=True,
                default="inactive",
            ),
        ]
        assert validate_rules(rules) == []


class TestStoreRejection:
    def test_invalid_save_rejected_old_version_active(self, tmp_path):
        store = RuleSetStore(str(tmp_path / "r.db"))
        store.save("acme", base_rules())
        with pytest.raises(ValidationError) as exc:
            store.save("acme", base_rules() + [{"target": "email", "source": "em2"}])
        assert exc.value.issues
        assert store.get_current("acme").version == 1
        store.close()

    def test_cycle_rejected_at_save(self, tmp_path):
        store = RuleSetStore(str(tmp_path / "r.db"))
        with pytest.raises(ValidationError):
            store.save("acme", [
                {"target": "a", "source": "$b"},
                {"target": "b", "source": "$a"},
            ])
        store.close()
