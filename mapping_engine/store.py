"""SQLite-backed rule set storage, versioned per connector."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .errors import ConnectorNotFoundError, ValidationError
from .models import RuleSet, rule_from_dict, rule_to_dict
from .validate import validate_rules

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_sets (
    connector TEXT NOT NULL,
    version INTEGER NOT NULL,
    rules_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (connector, version)
);
"""


class RuleSetStore:
    """Persists rule sets per connector; keeps every saved version.

    A saved version is immutable once written. ``get_current`` returns a
    detached snapshot, so a batch that already started keeps transforming
    with the version it began with even if a new version is saved midway.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save(self, connector: str, rules: list[dict[str, Any]]) -> RuleSet:
        """Validate and save a new version; rejects invalid rule sets whole.

        On rejection nothing is written and the previous version stays active.
        """
        parsed = [rule_from_dict(r) for r in rules]
        issues = validate_rules(parsed)
        if issues:
            raise ValidationError(issues)
        rules_json = json.dumps(
            [rule_to_dict(r) for r in parsed], ensure_ascii=False
        )
        with self._conn:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM rule_sets WHERE connector = ?",
                (connector,),
            ).fetchone()
            version = row[0] + 1
            self._conn.execute(
                "INSERT INTO rule_sets (connector, version, rules_json, created_at)"
                " VALUES (?, ?, ?, ?)",
                (connector, version, rules_json, datetime.now(timezone.utc).isoformat()),
            )
        return RuleSet(connector=connector, version=version, rules=tuple(parsed))

    def get_current(self, connector: str) -> RuleSet:
        """Return the latest active rule set for a connector."""
        row = self._conn.execute(
            "SELECT version, rules_json FROM rule_sets"
            " WHERE connector = ? ORDER BY version DESC LIMIT 1",
            (connector,),
        ).fetchone()
        if row is None:
            raise ConnectorNotFoundError(
                f"no rule set stored for connector {connector!r}"
            )
        version, rules_json = row
        rules = tuple(rule_from_dict(r) for r in json.loads(rules_json))
        return RuleSet(connector=connector, version=version, rules=rules)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RuleSetStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
