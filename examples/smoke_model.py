"""Real configured model + synthetic data. Never proof of real VIDEO integration."""
import json
from dataclasses import replace
from datetime import datetime, timezone

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.config import AgentConfig


def main():
    config = AgentConfig.from_env()
    if not config.model_enabled:
        print("Missing configured model; offline fallback is not accepted.")
        return 2
    # Explicit synthetic source; do not open a production data connection or persistent store.
    config = replace(config, video_base_url="", video_api_token="",
                     checkpoint_db="", memory_db="", require_tool_approval=True)
    with AgentRuntime(config) as runtime:
        result = runtime.chat(message="请调用 get_face_overview 查询人脸概况并基于工具证据报告。")
        paused = result["status"] == "awaiting_approval"
        if paused:
            proposal = result["pending_interrupt"][0]
            result = runtime.resume(result["thread_id"], approved=True,
                                    proposal_digest=proposal["proposal_digest"])
        metrics = result.get("analysis_report", {}).get("metrics", {}).get("get_face_overview", {})
        names = [row["tool"] for row in result.get("analysis_results", [])]
        passed = (paused and result["status"] == "completed" and
                  "get_face_overview" in names and metrics.get("face_records") == 51)
        print(json.dumps({"check": "live_model_synthetic_video", "passed": passed,
                          "model": config.model_name, "source": "synthetic",
                          "approval_resumed": paused, "status": result["status"],
                          "tools": names, "verified_at": datetime.now(timezone.utc).isoformat()},
                         ensure_ascii=False))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
