"""Environment-backed configuration for platform integration and local demos."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    model_base_url: str = ""
    model_name: str = ""
    model_api_key: str = ""
    model_timeout_seconds: int = 90
    video_base_url: str = ""
    video_api_token: str = ""
    video_timeout_seconds: int = 20
    max_tool_rounds: int = 4
    max_tools_per_round: int = 3
    max_history_messages: int = 8
    max_image_bytes: int = 10 * 1024 * 1024
    max_images: int = 3
    require_tool_approval: bool = False
    checkpoint_db: str = ""
    memory_db: str = ""

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            model_base_url=os.getenv("AGENT_MODEL_BASE_URL", "").strip(),
            model_name=os.getenv("AGENT_MODEL_NAME", "").strip(),
            model_api_key=os.getenv("AGENT_MODEL_API_KEY", ""),
            model_timeout_seconds=_bounded_int("AGENT_MODEL_TIMEOUT", 90, 10, 180),
            video_base_url=os.getenv("FACE_ANALYTICS_BASE_URL", "").rstrip("/"),
            video_api_token=os.getenv("FACE_ANALYTICS_API_TOKEN", ""),
            video_timeout_seconds=_bounded_int("FACE_ANALYTICS_TIMEOUT", 20, 3, 60),
            max_tool_rounds=_bounded_int("AGENT_MAX_TOOL_ROUNDS", 4, 1, 6),
            max_tools_per_round=_bounded_int("AGENT_MAX_TOOLS_PER_ROUND", 3, 1, 5),
            max_history_messages=_bounded_int("AGENT_MAX_HISTORY_MESSAGES", 8, 0, 20),
            max_image_bytes=_bounded_int("AGENT_MAX_IMAGE_BYTES", 10 * 1024 * 1024, 1024, 20 * 1024 * 1024),
            max_images=_bounded_int("AGENT_MAX_IMAGES", 3, 0, 3),
            require_tool_approval=os.getenv("AGENT_REQUIRE_TOOL_APPROVAL", "false").casefold() in {"1", "true", "yes"},
            checkpoint_db=os.getenv("AGENT_CHECKPOINT_DB", "").strip(),
            memory_db=os.getenv("AGENT_MEMORY_DB", "").strip(),
        )

    @property
    def model_enabled(self) -> bool:
        return bool(self.model_base_url and self.model_name)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)
