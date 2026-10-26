"""Host persistence adapter without coupling the public component to platform models."""
from __future__ import annotations

from typing import Callable

from ..domain.run_record import AgentRunRecord


class PlatformRunRecorderAdapter:
    """Wrap a host-owned persistence callback (for example, Flask-SQLAlchemy)."""

    def __init__(self, persist: Callable[[AgentRunRecord], None]) -> None:
        self.persist = persist

    def record(self, run: AgentRunRecord) -> None:
        self.persist(run)
