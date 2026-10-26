from flask import request

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.api.flask_app import create_app
from easyaiot_face_agent.config import AgentConfig


def test_chat_resume_and_rollback_share_one_response_contract():
    with AgentRuntime(AgentConfig(require_tool_approval=True)) as runtime:
        client = create_app(runtime).test_client()
        first = client.post("/v1/chat", json={"message": "overview", "conversation_id": "api"}).get_json()
        assert first["status"] == "awaiting_approval"
        response = client.post("/v1/runs/api/resume", json={
            "approved": True, "proposal_digest": first["pending_interrupt"][0]["proposal_digest"],
        })
        assert response.status_code == 200
        result = response.get_json()
        assert result["status"] == "completed"
        assert "assistant_reply" in result and "reply" not in result
        checkpoints = client.get("/v1/runs/api/checkpoints").get_json()["checkpoints"]
        target = next(c for c in checkpoints if c["next"] == ["tools"])
        branch = client.post("/v1/runs/api/rollback", json={
            "checkpoint_id": target["checkpoint_id"],
        }).get_json()
        assert branch["status"] == "awaiting_approval"
        assert client.post("/v1/runs/api/cancel").get_json()["status"] == "cancelled"


def test_api_identity_comes_from_host_not_json():
    def identity():
        # Test-only resolver; production must use its validated session, not raw headers.
        return {"tenant_id": "demo", "user_id": request.headers.get("X-Test-User", "alice")}
    with AgentRuntime(AgentConfig()) as runtime:
        client = create_app(runtime, identity_resolver=identity).test_client()
        assert client.post("/v1/chat", json={"message": "overview", "conversation_id": "scope",
                                           "user_id": "bob"}).status_code == 200
        assert client.get("/v1/runs/scope", headers={"X-Test-User": "bob"}).status_code == 404
        assert client.get("/v1/runs/scope").status_code == 200


def test_platform_data_requires_trusted_identity_resolver():
    with AgentRuntime(AgentConfig(video_base_url="http://video.example.invalid")) as runtime:
        client = create_app(runtime).test_client()
        assert client.post("/v1/chat", json={"message": "overview"}).status_code == 401


def test_empty_host_identity_never_falls_back_to_demo_identity():
    with AgentRuntime(AgentConfig()) as runtime:
        client = create_app(runtime, identity_resolver=lambda: {}).test_client()
        assert client.post("/v1/chat", json={"message": "overview"}).status_code == 401


def test_api_rejects_invalid_payload_and_stale_approval():
    with AgentRuntime(AgentConfig(require_tool_approval=True)) as runtime:
        client = create_app(runtime).test_client()
        assert client.post("/v1/chat", json=[]).status_code == 400
        assert client.post("/v1/chat", json={"message": 5}).status_code == 400
        assert client.post("/v1/chat", json={"message": "a", "history": 5}).status_code == 400
        assert client.post("/v1/chat", data="{", content_type="application/json").status_code == 400
        assert client.get("/v1/runs/missing").status_code == 404
        client.post("/v1/chat", json={"message": "overview", "conversation_id": "stale"})
        assert client.post("/v1/runs/stale/resume", json={
            "approved": True, "proposal_digest": "wrong",
        }).status_code == 409
