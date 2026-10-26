import base64
import json

import pytest

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.adapters.model_client import ModelProviderError
from easyaiot_face_agent.config import AgentConfig
from easyaiot_face_agent.domain.run_record import InMemoryRunRecorder
from easyaiot_face_agent.tools.service import FaceAnalysisTools


class ObservedTools(FaceAnalysisTools):
    def __init__(self, config):
        super().__init__(config)
        self.calls = []
        self.image_calls = 0

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return super().execute(name, arguments)

    def image_search(self, image):
        self.image_calls += 1
        return {"available": True, "source": "synthetic_stub", "matches": [{"id": "DEMO-CANDIDATE"}]}


def approve(runtime, response, decision=True):
    return runtime.resume(
        response["thread_id"], approved=decision,
        proposal_digest=response["pending_interrupt"][0]["proposal_digest"],
    )


@pytest.mark.parametrize("message,tool", [
    ("概况", "get_face_overview"),
    ("统计2026-04-20 到2026-05-07的活动", "summarize_face_activity"),
    ("人员1001的轨迹", "trace_person"),
    ("demo-subject-a", "search_people"),
    ("查询 DEMO-A", "search_people"),
    ("对比2026-04-20 到2026-04-26 和2026-05-01 到2026-05-07", "compare_face_activity"),
])
def test_offline_graph_reports_real_synthetic_metrics(message, tool):
    with AgentRuntime(AgentConfig()) as runtime:
        result = runtime.chat(message=message)
        assert result["status"] == "completed"
        assert result["analysis_report"]["metrics"][tool]
        assert {s.get("role") for s in result["agent_steps"]} >= {
            "planner", "data_access", "analyst", "reviewer", "reporter",
        }
        assert "合成数据" in result["assistant_reply"]


def test_approval_is_bound_and_rejection_never_executes_tool():
    config = AgentConfig(require_tool_approval=True)
    tools, recorder = ObservedTools(config), InMemoryRunRecorder()
    with AgentRuntime(config, tools=tools, run_recorder=recorder) as runtime:
        first = runtime.chat(message="overview", conversation_id="approval")
        assert first["status"] == "awaiting_approval"
        assert not tools.calls
        record = recorder.recent()[0]
        assert record["human_review_required"] and record["finished_at"] is None
        with pytest.raises(ValueError, match="approval_proposal_mismatch"):
            runtime.resume("approval", approved=True, proposal_digest="wrong")
        with pytest.raises(ValueError, match="previous_run_incomplete"):
            runtime.chat(message="overview", conversation_id="approval")
        rejected = approve(runtime, first, False)
        assert rejected["status"] == "cancelled"
        assert not tools.calls
        assert recorder.recent()[0]["status"] == "cancelled"
        with pytest.raises(ValueError, match="run_not_interrupted"):
            approve(runtime, first)


def test_sqlite_checkpoint_survives_runtime_recreation(tmp_path):
    config = AgentConfig(require_tool_approval=True, checkpoint_db=str(tmp_path / "runs.db"))
    first_runtime = AgentRuntime(config)
    first = first_runtime.chat(message="overview", conversation_id="durable")
    first_runtime.close()
    with AgentRuntime(config) as second_runtime:
        resumed = approve(second_runtime, first)
        assert resumed["status"] == "completed"
        assert resumed["trace_id"] == first["trace_id"]
        state = second_runtime.graph.get_state(second_runtime._config("durable")).values
        assert len(state["dialogue"]) == 2


def test_history_persists_without_client_resubmission_and_zero_disables_it(tmp_path):
    config = AgentConfig(checkpoint_db=str(tmp_path / "history.db"))
    with AgentRuntime(config) as runtime:
        runtime.chat(message="overview", conversation_id="history")
    with AgentRuntime(config) as runtime:
        runtime.chat(message="overview", conversation_id="history")
        state = runtime.graph.get_state(runtime._config("history")).values
        assert len(state["dialogue"]) == 4
    with AgentRuntime(AgentConfig(max_history_messages=0)) as runtime:
        runtime.chat(message="overview", conversation_id="zero")
        assert runtime.graph.get_state(runtime._config("zero")).values["dialogue"] == []


def test_threads_are_scoped_by_authenticated_tenant_and_user():
    with AgentRuntime(AgentConfig()) as runtime:
        runtime.chat(message="overview", conversation_id="same",
                     tenant_id="tenant-a", user_id="alice")
        for tenant, user in [("tenant-b", "alice"), ("tenant-a", "bob")]:
            with pytest.raises(ValueError, match="run_not_found"):
                runtime.status("same", tenant_id=tenant, user_id=user)


def test_replay_uses_historical_position_and_new_trace():
    config = AgentConfig()
    tools = ObservedTools(config)
    with AgentRuntime(config, tools=tools) as runtime:
        original = runtime.chat(message="overview", conversation_id="replay")
        before_tools = next(c for c in runtime.checkpoints("replay") if c["next"] == ["tools"])
        replay = runtime.rollback("replay", before_tools["checkpoint_id"])
        assert replay["status"] == "completed"
        assert replay["trace_id"] != original["trace_id"]
        assert replay["replayed_from"] == before_tools["checkpoint_id"]
        assert len(tools.calls) == 2
        final = next(c for c in runtime.checkpoints("replay") if not c["next"])
        with pytest.raises(ValueError, match="checkpoint_not_resumable"):
            runtime.rollback("replay", final["checkpoint_id"])


def test_replay_requires_new_approval_and_cancel_closes_pending_run():
    config = AgentConfig(require_tool_approval=True)
    with AgentRuntime(config) as runtime:
        first = runtime.chat(message="overview", conversation_id="branch")
        approve(runtime, first)
        target = next(c for c in runtime.checkpoints("branch") if c["next"] == ["tools"])
        replay = runtime.rollback("branch", target["checkpoint_id"])
        assert replay["status"] == "awaiting_approval"
        assert replay["pending_interrupt"][0]["proposal_digest"] != first["pending_interrupt"][0]["proposal_digest"]
        assert runtime.cancel("branch")["status"] == "cancelled"


class RepeatingModel:
    def complete(self, messages, *, tools, allow_tools):
        return {"role": "assistant", "content": "", "tool_calls": [{
            "id": "repeat", "function": {"name": "get_face_overview", "arguments": "{}"},
        }]}


def test_tool_budget_counts_executed_rounds():
    config = AgentConfig(max_tool_rounds=2)
    tools = ObservedTools(config)
    with AgentRuntime(config, model_client=RepeatingModel(), tools=tools) as runtime:
        result = runtime.chat(message="overview")
        assert len(tools.calls) == 2
        assert result["status"] == "completed_with_errors"
        assert any(s.get("error_code") == "agent_tool_round_limit" for s in result["agent_steps"])


def test_model_failure_is_a_failed_run_not_a_false_success():
    class BrokenModel:
        def complete(self, *args, **kwargs):
            raise ModelProviderError("model_timeout")
    recorder = InMemoryRunRecorder()
    with AgentRuntime(AgentConfig(), model_client=BrokenModel(), run_recorder=recorder) as runtime:
        with pytest.raises(ModelProviderError):
            runtime.chat(message="overview", conversation_id="broken")
        assert runtime.status("broken")["status"] == "failed"
        assert recorder.recent()[0]["status"] == "failed"


def test_images_are_approved_before_io_and_absent_from_checkpoint():
    config = AgentConfig(require_tool_approval=True)
    tools = ObservedTools(config)
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    with AgentRuntime(config, tools=tools) as runtime:
        first = runtime.chat(message="overview", images=["data:image/png;base64," + png],
                             conversation_id="image")
        assert first["pending_interrupt"][0]["kind"] == "image_approval"
        assert tools.image_calls == 0
        state = runtime.graph.get_state(runtime._config("image")).values
        assert png not in json.dumps(state, default=str)
        second = approve(runtime, first)
        assert second["status"] == "awaiting_approval"  # Tool approval follows image approval.
        assert tools.image_calls == 1
        assert approve(runtime, second)["status"] == "completed"


def test_status_reads_do_not_emit_duplicate_audit_events():
    recorder = InMemoryRunRecorder()
    with AgentRuntime(AgentConfig(), run_recorder=recorder) as runtime:
        runtime.chat(message="overview", conversation_id="audit")
        runtime.status("audit")
        runtime.status("audit")
        assert len(recorder.recent()) == 1


def test_image_payload_lost_after_restart_fails_explicitly_without_raw_checkpoint(tmp_path):
    config = AgentConfig(require_tool_approval=True, checkpoint_db=str(tmp_path / "image.db"))
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    with AgentRuntime(config) as runtime:
        pending = runtime.chat(message="overview", images=["data:image/png;base64," + png],
                               conversation_id="expired")
    with AgentRuntime(config) as runtime:
        second = approve(runtime, pending)
        assert second["status"] == "awaiting_approval"
        done = approve(runtime, second)
        assert done["status"] == "completed_with_errors"
        assert done["analysis_results"][0]["result"]["error"]["code"] == "image_payload_expired"
