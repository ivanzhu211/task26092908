"""SQLite 持久化：规则集按连接器保存，校验通过才替换旧版本。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .errors import RuleSetNotFoundError, RuleSetValidationError
from .rules import Rule, parse_rule_set, validate_rule_set

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_sets (
    connector  TEXT PRIMARY KEY,
    version    INTEGER NOT NULL,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class RuleSetStore:
    """按连接器存取规则集；保存前整体校验，失败则拒收、旧版本继续生效。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def save(self, connector: str, data: list[dict]) -> int:
        """校验并保存规则集，返回新版本号；有任何问题则整份拒收并抛 RuleSetValidationError。"""
        rules, issues = parse_rule_set(data)
        issues.extend(validate_rule_set(rules))
        if issues:
            raise RuleSetValidationError(issues)
        payload = json.dumps(data, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT version FROM rule_sets WHERE connector = ?",
                               (connector,)).fetchone()
            version = (row[0] + 1) if row else 1
            conn.execute(
                "INSERT INTO rule_sets (connector, version, data, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(connector) DO UPDATE SET version = excluded.version, "
                "data = excluded.data, updated_at = excluded.updated_at",
                (connector, version, payload, now),
            )
        return version

    def load(self, connector: str) -> list[Rule]:
        """读取连接器当前生效的规则集；不存在抛 RuleSetNotFoundError。"""
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM rule_sets WHERE connector = ?",
                               (connector,)).fetchone()
        if row is None:
            raise RuleSetNotFoundError(f"no rule set for connector {connector!r}")
        rules, issues = parse_rule_set(json.loads(row[0]))
        issues.extend(validate_rule_set(rules))
        if issues:  # 保存时已校验，正常不会走到这里
            raise RuleSetValidationError(issues)
        return rules

    def version(self, connector: str) -> int | None:
        """当前生效版本号；不存在返回 None。"""
        with self._connect() as conn:
            row = conn.execute("SELECT version FROM rule_sets WHERE connector = ?",
                               (connector,)).fetchone()
        return row[0] if row else None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)
