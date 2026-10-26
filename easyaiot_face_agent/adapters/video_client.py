"""HTTP adapter to the platform VIDEO face-analysis API."""
from __future__ import annotations

from typing import Any
from collections.abc import Callable

import requests

from ..config import AgentConfig


class VideoApiError(RuntimeError):
    def __init__(self, code: str, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class VideoApiClient:
    """Only calls the narrow face-analysis API; it never opens a database connection."""

    def __init__(self, config: AgentConfig, session: requests.Session | None = None,
                 *, scope_headers_provider: Callable[[], dict[str, str]] | None = None) -> None:
        if not config.video_base_url:
            raise ValueError("FACE_ANALYTICS_BASE_URL is required")
        self.config = config
        self.session = session or requests.Session()
        self.scope_headers_provider = scope_headers_provider

    def face_overview(self) -> Any:
        return self._get("/video/face/analysis/overview", {})

    def search_people(self, query: str, is_blacklist: bool | None, limit: int) -> Any:
        params: dict[str, Any] = {"q": query[:120], "limit": min(max(limit, 1), 50)}
        if is_blacklist is not None:
            params["isBlacklist"] = str(is_blacklist).lower()
        return self._get("/video/face/analysis/people", params)

    def summarize_face_activity(self, start_time: str | None, end_time: str | None) -> Any:
        params = {wire_key: value[:40] for wire_key, value in (("startTime", start_time), ("endTime", end_time)) if value}
        return self._get("/video/face/analysis/activity", params)

    def trace_person(self, person_id: int, start_time: str | None, end_time: str | None, limit: int) -> Any:
        params = {wire_key: value[:40] for wire_key, value in (("startTime", start_time), ("endTime", end_time)) if value}
        params["limit"] = min(max(limit, 1), 200)
        return self._get(f"/video/face/analysis/people/{int(person_id)}/trajectory", params)

    def image_search(self, image_bytes: bytes, media_type: str, top_k: int = 5) -> Any:
        headers = self._headers()
        try:
            response = self.session.post(
                f"{self.config.video_base_url}/video/face/analysis/image-search",
                headers=headers,
                files={"image": ("query-image", image_bytes, media_type)},
                data={"topK": min(max(int(top_k), 1), 10)},
                timeout=min(max(self.config.video_timeout_seconds, 10), 60),
            )
            return self._unwrap(response)
        except requests.Timeout as exc:
            raise VideoApiError("video_timeout") from exc
        except requests.RequestException as exc:
            raise VideoApiError("video_unavailable") from exc

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = self.session.get(
                f"{self.config.video_base_url}{path}",
                headers=self._headers(),
                params=params,
                timeout=self.config.video_timeout_seconds,
            )
            return self._unwrap(response)
        except requests.Timeout as exc:
            raise VideoApiError("video_timeout") from exc
        except requests.RequestException as exc:
            raise VideoApiError("video_unavailable") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.video_api_token:
            headers["Authorization"] = f"Bearer {self.config.video_api_token}"
        if self.scope_headers_provider is not None:
            delegated = self.scope_headers_provider()
            if not isinstance(delegated, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and "\n" not in k + v
                and "\r" not in k + v for k, v in delegated.items()
            ):
                raise VideoApiError("invalid_delegated_headers")
            headers.update(delegated)
        return headers

    @staticmethod
    def _unwrap(response: requests.Response) -> Any:
        if response.status_code >= 400:
            raise VideoApiError("video_http_error", response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise VideoApiError("video_invalid_json", response.status_code) from exc
        if isinstance(payload, dict):
            if payload.get("code") not in (None, 0):
                raise VideoApiError("video_application_error", response.status_code)
            return payload.get("data", payload)
        return payload
