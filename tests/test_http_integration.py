"""Real localhost HTTP with synthetic VIDEO and model endpoints, no GPU."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.adapters.video_client import VideoApiClient
from easyaiot_face_agent.config import AgentConfig


@contextmanager
def endpoint(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_configured_model_and_video_protocols_execute_end_to_end():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_GET(self):
            requests.append(("video", self.path))
            assert self.path == "/video/face/analysis/overview"
            self.respond({"code": 0, "data": {
                "people": 1, "face_records": 3, "identified_records": 2,
                "pending_review": 1, "image_search_ready": False,
            }})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(("model", body))
            assert self.path == "/v1/chat/completions"
            assert body["model"] == "synthetic-protocol-stub"
            assert "test-only-secret" not in json.dumps(body)
            if body.get("tools") and not any(m["role"] == "tool" for m in body["messages"]):
                message = {"role": "assistant", "content": "", "tool_calls": [{
                    "id": "http-call", "type": "function",
                    "function": {"name": "get_face_overview", "arguments": "{}"},
                }]}
            else:
                message = {"role": "assistant", "content": "合成接口桩报告：3 条记录，身份仍需复核。"}
            self.respond({"choices": [{"message": message}]})

    with endpoint(Handler) as base:
        config = AgentConfig(model_base_url=base, model_name="synthetic-protocol-stub",
                             model_api_key="test-only-secret", video_base_url=base)
        with AgentRuntime(config) as runtime:
            result = runtime.chat(message="overview", tenant_id="test", user_id="u")
            assert result["status"] == "completed"
            assert result["analysis_report"]["metrics"]["get_face_overview"]["identification_rate"] == 0.6667
            assert sum(kind == "video" for kind, _ in requests) == 1
            assert sum(kind == "model" for kind, _ in requests) == 4


def test_delegated_video_auth_is_resolved_for_each_call():
    from unittest.mock import Mock
    session = Mock()
    response = Mock(status_code=200)
    response.json.return_value = {"code": 0, "data": {}}
    session.get.return_value = response
    delegated = {"Authorization": "Bearer delegated-a"}
    client = VideoApiClient(
        AgentConfig(video_base_url="http://video.example.invalid"),
        session=session, scope_headers_provider=lambda: dict(delegated),
    )
    client.face_overview()
    assert session.get.call_args.kwargs["headers"]["Authorization"] == "Bearer delegated-a"
    delegated["Authorization"] = "Bearer delegated-b"
    client.face_overview()
    assert session.get.call_args.kwargs["headers"]["Authorization"] == "Bearer delegated-b"
