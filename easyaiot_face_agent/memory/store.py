"""Explicit structured preferences; no free-text identity or biometric memory."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class MemoryItem:
    key: str
    value: str
    category: str
    source: str
    created_at: str
    expires_at: str | None = None


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("memory_timestamp_timezone_required")
    return result


def validate_preference(item: MemoryItem) -> None:
    if not isinstance(item.key, str) or not isinstance(item.value, str):
        raise ValueError("unsupported_preference")
    if item.category != "preference" or item.source != "user_confirmed":
        raise ValueError("only_confirmed_preferences_allowed")
    allowed = {"language": {"zh-CN", "en"}, "report_style": {"brief", "detailed"}}
    if item.key == "timezone":
        try:
            if not isinstance(item.value, str) or len(item.value) > 64:
                raise ValueError("invalid_timezone_preference")
            ZoneInfo(item.value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid_timezone_preference") from exc
    elif item.key not in allowed or item.value not in allowed[item.key]:
        raise ValueError("unsupported_preference")
    _time(item.created_at)
    if item.expires_at:
        _time(item.expires_at)


def _namespace(tenant_id: str, user_id: str) -> None:
    if not all(isinstance(v, str) and 0 < len(v) <= 100 for v in (tenant_id, user_id)):
        raise ValueError("memory_scope_required")


class AgentMemory(Protocol):
    def search(self, *, tenant_id: str, user_id: str, query: str, limit: int = 5) -> list[MemoryItem]: ...
    def save(self, *, tenant_id: str, user_id: str, item: MemoryItem) -> None: ...
    def delete(self, *, tenant_id: str, user_id: str, key: str) -> bool: ...


class InMemoryAgentMemory:
    """Development store for finite preferences, not semantic retrieval."""
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], MemoryItem] = {}
        self._lock = threading.RLock()

    def search(self, *, tenant_id, user_id, query, limit=5) -> list[MemoryItem]:
        _namespace(tenant_id, user_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            for key, item in list(self._items.items()):
                if item.expires_at and _time(item.expires_at) <= now:
                    del self._items[key]
            return [item for (tenant, user, _), item in sorted(self._items.items())
                    if tenant == tenant_id and user == user_id][:max(1, min(limit, 20))]

    def save(self, *, tenant_id, user_id, item: MemoryItem) -> None:
        _namespace(tenant_id, user_id)
        validate_preference(item)
        with self._lock:
            self._items[(tenant_id, user_id, item.key)] = item

    def delete(self, *, tenant_id, user_id, key) -> bool:
        _namespace(tenant_id, user_id)
        with self._lock:
            return self._items.pop((tenant_id, user_id, key), None) is not None


class SqliteAgentMemory:
    """Local durable preferences. Production may inject its own audited store."""
    def __init__(self, path: str) -> None:
        self.path = str(Path(path))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS agent_preferences (
                tenant TEXT NOT NULL, user_id TEXT NOT NULL, key TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY (tenant, user_id, key))""")

    def search(self, *, tenant_id, user_id, query, limit=5) -> list[MemoryItem]:
        _namespace(tenant_id, user_id)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            rows = conn.execute(
                "SELECT key, payload FROM agent_preferences WHERE tenant=? AND user_id=? ORDER BY key",
                (tenant_id, user_id),
            ).fetchall()
            result = []
            for key, payload in rows:
                item = MemoryItem(**json.loads(payload))
                if item.expires_at and _time(item.expires_at) <= datetime.now(timezone.utc):
                    conn.execute("DELETE FROM agent_preferences WHERE tenant=? AND user_id=? AND key=?",
                                 (tenant_id, user_id, key))
                else:
                    validate_preference(item)
                    result.append(item)
            return result[:max(1, min(limit, 20))]

    def save(self, *, tenant_id, user_id, item: MemoryItem) -> None:
        _namespace(tenant_id, user_id)
        validate_preference(item)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "INSERT INTO agent_preferences VALUES (?,?,?,?) "
                "ON CONFLICT(tenant,user_id,key) DO UPDATE SET payload=excluded.payload",
                (tenant_id, user_id, item.key, json.dumps(asdict(item))),
            )

    def delete(self, *, tenant_id, user_id, key) -> bool:
        _namespace(tenant_id, user_id)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            cursor = conn.execute("DELETE FROM agent_preferences WHERE tenant=? AND user_id=? AND key=?",
                                  (tenant_id, user_id, key))
            return cursor.rowcount > 0
