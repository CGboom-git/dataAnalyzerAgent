"""Reproducible synthetic component demonstration; no model, VIDEO or biometric data."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.config import AgentConfig


def compact(result: dict) -> dict:
    return {key: result[key] for key in (
        "status", "assistant_reply", "analysis_report", "pending_interrupt",
    )}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/demo.json")
    args = parser.parse_args()
    queries = [
        "overview",
        "统计2026-04-20 到2026-05-07的抓拍活动",
        "demo-subject-a",
        "人员1001的跨摄像头轨迹",
        "对比2026-04-20 到2026-04-26 和2026-05-01 到2026-05-07的抓拍活动",
    ]
    output = {"provenance": "synthetic fixtures + deterministic demo model",
              "real_model_evaluation": False, "queries": []}
    with AgentRuntime(AgentConfig()) as runtime:
        for query in queries:
            result = runtime.chat(message=query)
            if result["status"] != "completed":
                raise RuntimeError(f"synthetic_demo_failed:{result['status']}")
            output["queries"].append({"question": query, **compact(result)})
    with tempfile.TemporaryDirectory() as folder:
        config = AgentConfig(require_tool_approval=True,
                             checkpoint_db=str(Path(folder) / "checkpoints.sqlite3"))
        with AgentRuntime(config) as runtime:
            pending = runtime.chat(message="overview", conversation_id="demo-durable")
            digest = pending["pending_interrupt"][0]["proposal_digest"]
        # New runtime, new SQLite connection, same durable thread.
        with AgentRuntime(config) as runtime:
            resumed = runtime.resume("demo-durable", approved=True, proposal_digest=digest)
            output["restart_resume"] = {"before": pending["status"], "after": resumed["status"],
                                        "same_trace": pending["trace_id"] == resumed["trace_id"]}
            pending = runtime.chat(message="overview", conversation_id="demo-denied")
            denied = runtime.resume("demo-denied", approved=False,
                                    proposal_digest=pending["pending_interrupt"][0]["proposal_digest"])
            output["rejection"] = {"status": denied["status"], "results": denied["analysis_results"]}
            history = runtime.checkpoints("demo-durable")
            target = next(row for row in history if row["next"] == ["tools"])
            replay = runtime.rollback("demo-durable", target["checkpoint_id"])
            output["replay"] = {"status": replay["status"],
                                "new_approval": replay["pending_interrupt"][0]["proposal_digest"] != digest}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"synthetic demo: {len(queries)} queries, restart/resume/reject/replay -> {path}")


if __name__ == "__main__":
    main()
