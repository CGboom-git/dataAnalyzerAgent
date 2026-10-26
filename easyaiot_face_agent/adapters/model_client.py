"""Configured OpenAI-compatible model adapter and deterministic graph demo client."""
from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib.parse import urlparse

import requests

from ..config import AgentConfig


class ModelProviderError(RuntimeError):
    """Raised when the configured model endpoint fails or returns invalid data."""


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]], allow_tools: bool) -> dict[str, Any]: ...


class OpenAICompatibleModelClient:
    def __init__(self, config: AgentConfig, session: requests.Session | None = None) -> None:
        if not config.model_enabled:
            raise ValueError("AGENT_MODEL_BASE_URL and AGENT_MODEL_NAME are required")
        self.config = config
        self.session = session or requests.Session()

    def complete(self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]], allow_tools: bool) -> dict[str, Any]:
        endpoint = _chat_completions_url(self.config.model_base_url)
        headers = {"Content-Type": "application/json"}
        if self.config.model_api_key:
            headers["Authorization"] = f"Bearer {self.config.model_api_key}"
        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2000,
        }
        if allow_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            response = self.session.post(endpoint, headers=headers, json=payload, timeout=self.config.model_timeout_seconds)
            response.raise_for_status()
            body = response.json()
        except requests.Timeout as exc:
            raise ModelProviderError("model_timeout") from exc
        except requests.RequestException as exc:
            raise ModelProviderError("model_unavailable") from exc
        except ValueError as exc:
            raise ModelProviderError("model_invalid_json") from exc
        choices = body.get("choices") if isinstance(body, dict) else None
        message = (choices[0].get("message")
                   if isinstance(choices, list) and choices and isinstance(choices[0], dict)
                   else None)
        if not isinstance(message, dict):
            raise ModelProviderError("model_invalid_response")
        return message


def _chat_completions_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("model endpoint must be an http(s) URL")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


class OfflineDemoModelClient:
    """Local deterministic client that exercises the same tool-call graph without a model."""

    def complete(self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]], allow_tools: bool) -> dict[str, Any]:
        if not allow_tools:
            return {"role": "assistant", "content": "本地演示流程已完成。结果仅来自合成数据或模拟 VIDEO 接口。"}
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        if tool_messages:
            summaries = []
            for item in tool_messages[-3:]:
                try:
                    result = json.loads(item.get("content") or "{}")
                except (TypeError, ValueError):
                    result = {}
                summaries.append(f"{item.get('name')}: {json.dumps(result, ensure_ascii=False)[:1200]}")
            return {"role": "assistant", "content": "本地演示查询完成。\n" + "\n".join(summaries)}

        question = _last_user_text(messages)
        tool_name, arguments = _offline_route(question)
        call = {
            "id": "offline-call-1",
            "type": "function",
            "function": {"name": tool_name, "arguments": json.dumps(arguments, ensure_ascii=False)},
        }
        return {"role": "assistant", "content": "", "tool_calls": [call]}


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
    return ""


def _offline_route(question: str) -> tuple[str, dict[str, Any]]:
    lower = question.casefold()
    person_id_match = re.search(r"(?:person(?:_id)?\s*[:=#]?\s*|人员(?:编号|ID)?\s*[:=#]?\s*)(\d+)", question, re.IGNORECASE)
    demo_match = re.search(r"demo[-_ ]?(?:person|subject)[-_ ]?([a-z0-9]+)", question, re.IGNORECASE)
    if any(word in question for word in ("总览", "概览", "概况", "总数", "整体情况")) or "overview" in lower:
        return "get_face_overview", {}
    ranges = re.findall(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?", question)
    ranges = [_date_bound(value, index) for index, value in enumerate(ranges)]
    if any(word in question for word in ("对比", "环比", "同比")) or "compare" in lower:
        if len(ranges) >= 4:
            return "compare_face_activity", {"period_a_start": ranges[0], "period_a_end": ranges[1], "period_b_start": ranges[2], "period_b_end": ranges[3]}
    if any(word in question for word in ("轨迹", "跨摄像头", "经过哪些摄像头", "去哪")) or "trajectory" in lower:
        if not person_id_match and not demo_match:
            return "search_people", {"query": question[:120], "limit": 20}
        person_id = int(person_id_match.group(1)) if person_id_match else _demo_person_id(demo_match.group(1) if demo_match else "a")
        args = {"person_id": person_id, "limit": 200}
        if len(ranges) >= 2:
            args.update({"start_time": ranges[0], "end_time": ranges[1]})
        return "trace_person", args
    if any(word in question for word in ("抓拍", "活动", "趋势", "统计", "分布", "多少")) or any(word in lower for word in ("activity", "capture", "summary", "count")):
        args = {"start_time": ranges[0], "end_time": ranges[1]} if len(ranges) >= 2 else {}
        return "summarize_face_activity", args
    demo_code = re.search(r"\bDEMO-[ABC]\b", question, re.IGNORECASE)
    query = (demo_match.group(0) if demo_match else demo_code.group(0) if demo_code
             else re.sub(r"^(?:查询|查找|搜索)\s*", "", question).strip()[:120])
    return "search_people", {"query": query, "limit": 20}


def _date_bound(value: str, index: int) -> str:
    if "T" in value or " " in value:
        return value
    # Date-only user windows are interpreted inclusively in the offline demo.
    suffix = "T00:00:00Z" if index % 2 == 0 else "T23:59:59Z"
    return value + suffix


def _demo_person_id(value: str) -> int:
    normalized = str(value or "a").lower()
    return ord(normalized[0]) - ord("a") + 1001 if normalized[0].isalpha() else 1001
