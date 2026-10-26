"""Stable, platform-facing result and trace contracts."""
from __future__ import annotations

from typing import Any

AGENT_CONTRACT_VERSION = "easyaiot.face-agent.v1"


def result_envelope(
    *, trace_id: str, assistant_reply: str, steps: list[dict[str, Any]],
    results: list[dict[str, Any]], conversation_id: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    analysis_report: dict[str, Any] | None = None,
    run_record_status: str = "not_configured",
) -> dict[str, Any]:
    return {
        "contract_version": AGENT_CONTRACT_VERSION,
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "assistant_reply": assistant_reply,
        "agent_steps": steps,
        "analysis_results": results,
        "evidence_refs": evidence_refs or [],
        "analysis_report": analysis_report or {},
        "run_record_status": run_record_status,
        "limitations": [
            "分析结果来自当前配置的数据服务；数据范围、授权和识别质量由平台 VIDEO 服务决定。"
        ],
    }
