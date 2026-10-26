"""Agent run audit contracts inspired by the platform's persisted run/result records."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentRunRecord:
    trace_id: str
    conversation_id: str | None
    agent_role: str
    stage: str
    contract_version: str
    status: str
    started_at: str
    finished_at: str | None
    tool_steps: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    risk_flags: list[str]
    human_review_required: bool
    analysis_report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentRunRecorder(Protocol):
    def record(self, run: AgentRunRecord) -> None: ...


class InMemoryRunRecorder:
    """Small local observer for development; production persistence belongs to the host app."""

    def __init__(self, max_records: int = 100) -> None:
        self.max_records = max(1, min(int(max_records), 1000))
        self._records: list[AgentRunRecord] = []

    def record(self, run: AgentRunRecord) -> None:
        self._records.append(run)
        del self._records[:-self.max_records]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        count = min(max(int(limit), 1), 100)
        return [item.to_dict() for item in self._records[-count:]][::-1]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
