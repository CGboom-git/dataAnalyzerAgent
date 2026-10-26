from unittest.mock import Mock

import pytest

from easyaiot_face_agent.adapters.video_client import VideoApiClient
from easyaiot_face_agent.analytics import build_analysis_report
from easyaiot_face_agent.config import AgentConfig
from easyaiot_face_agent.tools.service import FaceAnalysisTools, ToolExecutionError


def test_activity_argument_contract_and_known_fixture_total():
    tools = FaceAnalysisTools(AgentConfig())
    args = {"start_time": "2026-04-01T00:00:00Z", "end_time": "2026-06-01T00:00:00Z"}
    assert isinstance(tools._validate_arguments("summarize_face_activity", args), dict)
    result = tools.execute("summarize_face_activity", args)
    assert result["ok"] and result["data"]["total_records"] == 51


@pytest.mark.parametrize("name,args", [
    ("execute_sql", {"sql": "select 1"}),
    ("get_face_overview", {"url": "https://example.invalid"}),
    ("trace_person", {"person_id": True}),
    ("search_people", {"query": "demo", "limit": 10000}),
    ("summarize_face_activity", {"start_time": "2026-05-01", "end_time": "2026-04-01"}),
    ("compare_face_activity", {}),
])
def test_rejects_unknown_tools_unbounded_and_invalid_arguments(name, args):
    with pytest.raises(ToolExecutionError):
        FaceAnalysisTools(AgentConfig()).execute(name, args)


def test_wire_parameters_and_headers_are_explicit():
    session = Mock()
    response = Mock(status_code=200)
    response.json.return_value = {"code": 0, "data": {"total_records": 3}}
    session.get.return_value = response
    client = VideoApiClient(AgentConfig(video_base_url="http://video.example.invalid",
                                       video_api_token="test-token"), session=session)
    assert client.summarize_face_activity("2026-04-01", "2026-04-02") == {"total_records": 3}
    kwargs = session.get.call_args.kwargs
    assert kwargs["params"] == {"startTime": "2026-04-01", "endTime": "2026-04-02"}
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert session.get.call_args.args[0].endswith("/video/face/analysis/activity")


def test_failed_payload_is_not_reported_as_a_measured_zero():
    result = {"tool": "summarize_face_activity",
              "result": {"ok": False, "error": {"code": "video_timeout"}}}
    report = build_analysis_report([result], [{"tool": "summarize_face_activity", "status": "error"}])
    assert not report["metrics"]
    assert report["execution"]["failed_steps"]


def test_overview_known_counts_have_reproducible_identification_rate():
    result = {"tool": "get_face_overview", "result": {"ok": True, "data": {
        "people": 1, "face_records": 3, "identified_records": 2, "pending_review": 1,
    }}}
    report = build_analysis_report([result], [])
    assert report["metrics"]["get_face_overview"]["identification_rate"] == 0.6667
