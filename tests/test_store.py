"""Persistence, versioning, and snapshot isolation."""

import pytest

from mapping_engine import (
    ConnectorNotFoundError,
    RuleSetStore,
    transform_batch,
)


def rules_v1():
    return [
        {"target": "employee_id", "source": "id"},
        {"target": "first_name", "source": "fn"},
        {"target": "last_name", "source": "ln"},
        {"target": "email", "source": "em"},
        {"target": "status", "default": "active"},
    ]


def test_unknown_connector_raises(tmp_path):
    store = RuleSetStore(str(tmp_path / "r.db"))
    with pytest.raises(ConnectorNotFoundError):
        store.get_current("nope")
    store.close()


def test_versions_increment_and_persist(tmp_path):
    db = str(tmp_path / "r.db")
    store = RuleSetStore(db)
    assert store.save("acme", rules_v1()).version == 1
    v2 = rules_v1()
    v2[4] = {"target": "status", "default": "inactive"}
    assert store.save("acme", v2).version == 2
    # other connector versions independently
    assert store.save("other", rules_v1()).version == 1
    store.close()

    reopened = RuleSetStore(db)
    assert reopened.get_current("acme").version == 2
    assert reopened.get_current("other").version == 1
    reopened.close()


def test_snapshot_isolation_mid_batch_save(tmp_path):
    """A batch started on v1 finishes on v1 even after v2 is saved."""
    store = RuleSetStore(str(tmp_path / "r.db"))
    store.save("acme", rules_v1())
    snapshot = store.get_current("acme")  # batch "starts" here

    v2 = rules_v1()
    v2[4] = {"target": "status", "default": "terminated"}
    store.save("acme", v2)

    records = [{"id": str(i), "fn": "F", "ln": "L", "em": "e@x.co"} for i in range(50)]
    batch = transform_batch(snapshot, records)
    assert batch.succeeded == 50
    assert all(r.employee["status"] == "active" for r in batch.results)

    fresh = transform_batch(store.get_current("acme"), records)
    assert all(r.employee["status"] == "terminated" for r in fresh.results)
    store.close()


def test_failed_save_keeps_old_version(tmp_path):
    store = RuleSetStore(str(tmp_path / "r.db"))
    store.save("acme", rules_v1())
    with pytest.raises(Exception):
        store.save("acme", [{"target": "status", "transform": "nonsense"}])
    current = store.get_current("acme")
    assert current.version == 1
    rec = {"id": "1", "fn": "F", "ln": "L", "em": "e@x.co"}
    assert transform_batch(current, [rec]).results[0].employee["status"] == "active"
    store.close()
