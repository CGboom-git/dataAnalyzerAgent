"""Validated Agent tool execution and bounded multimodal preflight."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from ..adapters.video_client import VideoApiClient, VideoApiError
from ..config import AgentConfig
from ..demo.repository import SyntheticFaceRepository
from .schemas import TOOL_SCHEMAS

_ALLOWED_ARGUMENTS = {
    "get_face_overview": set(),
    "search_people": {"query", "is_blacklist", "limit"},
    "compare_face_activity": {"period_a_start", "period_a_end", "period_b_start", "period_b_end"},
    "summarize_face_activity": {"start_time", "end_time"},
    "trace_person": {"person_id", "start_time", "end_time", "limit"},
}
TOOL_CATALOG = [
    {"name": item["function"]["name"], "description": item["function"]["description"], "read_only": True, "execution_mode": "model_selected"}
    for item in TOOL_SCHEMAS
] + [{
    "name": "image_similarity_search",
    "description": "当请求包含图片时，由图中的固定预检节点自动调用 VIDEO；模型不能自行触发。",
    "read_only": True,
    "execution_mode": "image_preflight",
}]


@dataclass(frozen=True)
class UploadedImage:
    data_url: str
    data: bytes
    media_type: str


class ToolExecutionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FaceAnalysisTools:
    def __init__(self, config: AgentConfig, *, video_client: VideoApiClient | None = None, demo_repository: SyntheticFaceRepository | None = None) -> None:
        self.config = config
        self.video_client = video_client
        self.demo_repository = demo_repository or SyntheticFaceRepository()

    @property
    def source_name(self) -> str:
        return "easyaiot_video_api" if self.video_client else "synthetic_demo"

    def execute(self, name: str, raw_arguments: Any) -> dict[str, Any]:
        args = self._validate_arguments(name, raw_arguments)
        try:
            if self.video_client:
                value = self._execute_video(name, args)
            else:
                value = self._execute_demo(name, args)
            return {"ok": True, "data": value, "source": self.source_name}
        except VideoApiError as exc:
            return {"ok": False, "error": {"code": exc.code, "status_code": exc.status_code}}
        except ValueError as exc:
            return {"ok": False, "error": {"code": "invalid_tool_arguments", "detail": str(exc)[:160]}}

    def image_search(self, image: UploadedImage) -> dict[str, Any]:
        if not self.video_client:
            return {"available": False, "source": "synthetic_demo", "message": "本地演示没有真实人脸索引，图片相似检索未执行。"}
        try:
            result = self.video_client.image_search(image.data, image.media_type)
            return {"available": True, "source": self.source_name, "matches": result}
        except VideoApiError as exc:
            return {"available": False, "source": self.source_name, "error": {"code": exc.code}}

    @staticmethod
    def _validate_arguments(name: str, arguments: Any) -> dict[str, Any]:
        if name not in _ALLOWED_ARGUMENTS:
            raise ToolExecutionError("tool_not_allowlisted")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except ValueError as exc:
                raise ToolExecutionError("tool_arguments_invalid_json") from exc
        if not isinstance(arguments, dict) or set(arguments) - _ALLOWED_ARGUMENTS[name]:
            raise ToolExecutionError("tool_arguments_invalid_shape")
        if name == "get_face_overview":
            return {}
        if name == "compare_face_activity":
            result = {}
            for period in ("a", "b"):
                start, end = _bounded_time_range(arguments.get(f"period_{period}_start"), arguments.get(f"period_{period}_end"))
                if not start or not end:
                    raise ToolExecutionError("comparison_period_bounds_required")
                result[f"period_{period}"] = {"start_time": start, "end_time": end}
            return result
        if name == "search_people":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ToolExecutionError("query_required")
            if len(query) > 120:
                raise ToolExecutionError("query_too_long")
            is_blacklist = arguments.get("is_blacklist")
            if is_blacklist is not None and not isinstance(is_blacklist, bool):
                raise ToolExecutionError("is_blacklist_must_be_boolean")
            return {"query": query.strip(), "is_blacklist": is_blacklist, "limit": _bounded_int(arguments.get("limit", 20), 1, 50)}
        if name == "summarize_face_activity":
            start_time, end_time = _bounded_time_range(
                arguments.get("start_time"), arguments.get("end_time")
            )
            return {"start_time": start_time, "end_time": end_time}
        person_id = _bounded_int(arguments.get("person_id"), 1, 2**31 - 1)
        start_time, end_time = _bounded_time_range(arguments.get("start_time"), arguments.get("end_time"))
        return {"person_id": person_id, "start_time": start_time, "end_time": end_time, "limit": _bounded_int(arguments.get("limit", 200), 1, 200)}

    def _execute_video(self, name: str, args: dict[str, Any]) -> Any:
        assert self.video_client is not None
        if name == "get_face_overview":
            return self.video_client.face_overview()
        if name == "compare_face_activity":
            return {
                "period_a": {**args["period_a"], "activity": self.video_client.summarize_face_activity(args["period_a"]["start_time"], args["period_a"]["end_time"])},
                "period_b": {**args["period_b"], "activity": self.video_client.summarize_face_activity(args["period_b"]["start_time"], args["period_b"]["end_time"])},
            }
        if name == "search_people":
            return self.video_client.search_people(args["query"], args["is_blacklist"], args["limit"])
        if name == "summarize_face_activity":
            return self.video_client.summarize_face_activity(args["start_time"], args["end_time"])
        return self.video_client.trace_person(args["person_id"], args["start_time"], args["end_time"], args["limit"])

    def _execute_demo(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_face_overview":
            return self.demo_repository.face_overview()
        if name == "compare_face_activity":
            return {
                "period_a": {**args["period_a"], "activity": self.demo_repository.summarize_face_activity(args["period_a"]["start_time"], args["period_a"]["end_time"])},
                "period_b": {**args["period_b"], "activity": self.demo_repository.summarize_face_activity(args["period_b"]["start_time"], args["period_b"]["end_time"])},
            }
        if name == "search_people":
            return self.demo_repository.search_people(args["query"], args["is_blacklist"], args["limit"])
        if name == "summarize_face_activity":
            return self.demo_repository.summarize_face_activity(args["start_time"], args["end_time"])
        return self.demo_repository.trace_person(args["person_id"], args["start_time"], args["end_time"], args["limit"])


def _bounded_time_range(start_value: Any, end_value: Any) -> tuple[str | None, str | None]:
    start_text, end_text = _time_arg(start_value), _time_arg(end_value)
    if start_text and end_text:
        from datetime import datetime, timezone

        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_text.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if start > end:
            raise ToolExecutionError("time_range_invalid")
    return start_text, end_text


def normalize_uploaded_image(value: Any, max_bytes: int) -> UploadedImage:
    if not isinstance(value, str) or not value:
        raise ToolExecutionError("image_invalid")
    media_type = "image/jpeg"
    encoded = value
    if value.startswith("data:"):
        header, sep, encoded = value.partition(",")
        if not sep:
            raise ToolExecutionError("image_data_url_invalid")
        media_type = header[5:].split(";", 1)[0].lower()
    if media_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ToolExecutionError("image_type_not_allowed")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ToolExecutionError("image_base64_invalid") from exc
    if not image_bytes or len(image_bytes) > max_bytes:
        raise ToolExecutionError("image_size_out_of_range")
    if not _matches_image_signature(image_bytes, media_type):
        raise ToolExecutionError("image_signature_mismatch")
    canonical = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return UploadedImage(canonical, image_bytes, media_type)


def _matches_image_signature(data: bytes, media_type: str) -> bool:
    return {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }[media_type]


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ToolExecutionError("integer_expected")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError("integer_expected") from exc
    if str(number) != str(value).strip() and not isinstance(value, int):
        raise ToolExecutionError("integer_expected")
    if number < minimum or number > maximum:
        raise ToolExecutionError("integer_out_of_range")
    return number


def _time_arg(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ToolExecutionError("time_invalid")
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolExecutionError("time_invalid") from exc
    return value
