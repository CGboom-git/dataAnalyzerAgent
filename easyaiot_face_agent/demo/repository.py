"""Offline repository that mirrors the VIDEO response shapes with synthetic people only."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "events.json"


class SyntheticFaceRepository:
    """Development adapter. It must never be populated with production face records."""

    def __init__(self, data_path: Path = DATA_PATH) -> None:
        self.data_path = data_path

    def _events(self) -> list[dict[str, Any]]:
        with self.data_path.open(encoding="utf-8") as stream:
            return json.load(stream)["events"]

    def face_overview(self) -> dict[str, Any]:
        events = self._events()
        people = {str(event["person_ref"]) for event in events if event.get("person_ref")}
        identified = sum(bool(event.get("person_ref")) for event in events)
        return {
            "people": len(people),
            "face_records": len(events),
            "identified_records": identified,
            "pending_review": 0,
            "image_search_ready": False,
            "source": "synthetic_demo",
        }

    def search_people(self, query: str, is_blacklist: bool | None = None, limit: int = 20) -> dict[str, Any]:
        events = self._events()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            grouped.setdefault(str(event["person_ref"]), []).append(event)
        query_lower = query.casefold().strip()
        people = []
        for person_ref, rows in grouped.items():
            suffix = person_ref.removeprefix("demo-subject-").upper()
            person_id = _person_id(person_ref)
            label = f"演示主体 {suffix}"
            blacklist = suffix == "B"
            searchable = f"{person_ref} DEMO-{suffix} {label}".casefold()
            if query_lower and query_lower not in searchable:
                continue
            if is_blacklist is not None and blacklist != is_blacklist:
                continue
            people.append({
                "id": person_id,
                "person_code": f"DEMO-{suffix}",
                "name": label,
                "tags": ["synthetic", "demo"],
                "description": "仅用于接口演示的虚构档案；不对应真实身份。",
                "is_blacklist": blacklist,
                "capture_count": len(rows),
                "profile_photo": None,
            })
        return {"items": people[:min(max(int(limit), 1), 50)], "total": len(people), "source": "synthetic_demo"}

    def summarize_face_activity(self, start_time: str | None = None, end_time: str | None = None) -> dict[str, Any]:
        events = self._filter_time(self._events(), start_time, end_time)
        frame = pd.DataFrame(events)
        if frame.empty:
            return {"total_records": 0, "records_analyzed": 0, "truncated": False, "identified_records": 0, "unique_people": 0, "by_day": [], "by_camera": [], "source": "synthetic_demo"}
        frame["day"] = pd.to_datetime(frame["occurred_at"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
        by_day = frame.dropna(subset=["day"]).groupby("day").size().sort_index().rename("count").reset_index().to_dict(orient="records")
        by_camera = frame.groupby("camera_id").size().sort_values(ascending=False).head(20).rename("count").reset_index().to_dict(orient="records")
        return {
            "total_records": len(frame),
            "records_analyzed": len(frame),
            "truncated": False,
            "identified_records": int(frame["person_ref"].notna().sum()),
            "unique_people": int(frame["person_ref"].nunique()),
            "by_day": [{"day": str(row["day"]), "count": int(row["count"])} for row in by_day[-31:]],
            "by_camera": [{"device_id": row["camera_id"], "camera_name": row["camera_id"], "count": int(row["count"])} for row in by_camera],
            "source": "synthetic_demo",
        }

    def trace_person(self, person_id: int, start_time: str | None = None, end_time: str | None = None, limit: int = 200) -> dict[str, Any] | None:
        events = [item for item in self._filter_time(self._events(), start_time, end_time) if _person_id(str(item["person_ref"])) == person_id]
        if not events:
            return None
        events = sorted(events, key=lambda item: item["occurred_at"])[:min(max(int(limit), 1), 200)]
        suffix = str(events[0]["person_ref"]).removeprefix("demo-subject-").upper()
        return {
            "person": {"id": person_id, "person_code": f"DEMO-{suffix}", "name": f"演示主体 {suffix}", "is_blacklist": suffix == "B"},
            "total_records": len(events),
            "events": [
                {"face_id": item["event_id"], "face_code": item["event_id"], "device_id": item["camera_id"], "camera_name": item["camera_id"], "captured_at": item["occurred_at"], "confidence": 0.91, "match_score": 0.87, "status": "synthetic_demo", "image_object": None}
                for item in events
            ],
            "source": "synthetic_demo",
        }

    @staticmethod
    def _filter_time(events: list[dict[str, Any]], start_time: str | None, end_time: str | None) -> list[dict[str, Any]]:
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        if start and end and start > end:
            raise ValueError("start_time must be earlier than or equal to end_time")
        rows = []
        for event in events:
            captured = _parse_time(str(event["occurred_at"]))
            if start and captured < start:
                continue
            if end and captured > end:
                continue
            rows.append(event)
        return rows


def _person_id(person_ref: str) -> int:
    suffix = person_ref.removeprefix("demo-subject-").lower()
    if len(suffix) == 1 and suffix.isalpha():
        return 1001 + ord(suffix) - ord("a")
    return 1999


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("time must be ISO 8601") from exc
