"""Trusted package resources; workflow guidance never grants tool privileges."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    description: str
    allowed_tools: tuple[str, ...]
    instructions: str


class SkillRegistry:
    def __init__(self) -> None:
        definitions = (
            ("face_overview", "人脸数据总览", ("get_face_overview",)),
            ("person_lookup", "人员档案检索", ("search_people",)),
            ("person_trace", "先解析人员，再查询授权轨迹", ("search_people", "trace_person")),
            ("face_activity", "活动统计与两期对比",
             ("get_face_overview", "summarize_face_activity", "compare_face_activity")),
            ("face_analysis", "组合分析",
             ("get_face_overview", "search_people", "trace_person",
              "summarize_face_activity", "compare_face_activity")),
        )
        self._skills = {
            name: Skill(name, "1.0.0", description, tools,
                        files(__package__).joinpath("prompts", f"{name}.md").read_text("utf-8"))
            for name, description, tools in definitions
        }

    def get(self, name: str | None) -> Skill | None:
        return self._skills.get(name or "")

    def list(self) -> list[dict]:
        return [
            {"name": s.name, "version": s.version, "description": s.description,
             "allowed_tools": list(s.allowed_tools)}
            for s in self._skills.values()
        ]

    def select(self, message: str) -> str:
        text = message.casefold()
        trace = any(w in text for w in ("轨迹", "跨摄像头", "去哪", "trajectory"))
        activity = any(w in text for w in ("活动", "抓拍", "趋势", "统计", "对比", "比较",
                                          "环比", "同比", "activity", "compare", "count"))
        overview = any(w in text for w in ("总览", "概览", "概况", "总数", "overview"))
        if sum((trace, activity, overview)) > 1:
            return "face_analysis"
        if trace:
            return "person_trace"
        if activity:
            return "face_activity"
        if overview:
            return "face_overview"
        return "face_analysis"
