"""Opt-in read-only smoke against host-configured Qwen-compatible and VIDEO endpoints."""
import json
import os
from datetime import datetime, timezone

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.config import AgentConfig


def main():
    config = AgentConfig.from_env()
    tenant, user = os.getenv("AGENT_SMOKE_TENANT"), os.getenv("AGENT_SMOKE_USER")
    if not config.model_enabled or not config.video_base_url or not tenant or not user:
        print("Missing live model/VIDEO configuration or authenticated smoke identity.")
        return 2
    # VIDEO must independently enforce the service credential's authorized scope.
    with AgentRuntime(config) as runtime:
        result = runtime.chat(
            message="请仅使用 get_face_overview 查询人脸概况，不查询人员与轨迹。",
            tenant_id=tenant, user_id=user,
        )
        if result["status"] == "awaiting_approval":
            print("Live run paused. Use the host approval UI/API; no auto-approval was issued.")
            return 2
        good = (result["status"] == "completed" and
                any(row["tool"] == "get_face_overview" and row["result"].get("ok")
                    for row in result["analysis_results"]))
        # Receipt contains no endpoint, credential, person ID or raw production result.
        print(json.dumps({"passed": good, "status": result["status"],
                          "verified_at": datetime.now(timezone.utc).isoformat(),
                          "contract_version": result["contract_version"],
                          "check": "live_read_only_overview"}, ensure_ascii=False))
        return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
