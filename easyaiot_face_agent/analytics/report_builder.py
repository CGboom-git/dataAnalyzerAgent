"""Build auditable, deterministic findings from VIDEO API results."""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

REPORT_VERSION = "easyaiot.face-analysis-report.v1"


def build_analysis_report(results: list[dict[str, Any]], steps: list[dict[str, Any]], evidence_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Create derived metrics without asking an LLM to do arithmetic."""
    metrics: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    limitations = [
        "报告中的统计由 Agent 对 VIDEO 返回字段进行确定性计算；原始查询结果仍保留在 analysis_results。",
        "人脸相似度、匹配分数和轨迹记录不能单独证明真实身份、意图或行为因果。",
    ]

    for row in results:
        if not isinstance(row, dict):
            continue
        tool = str(row.get("tool") or "unknown")
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        if not result.get("ok") or result.get("truncated"):
            # Missing/failed results are not measured zeroes.
            continue
        payload = result.get("data") if isinstance(result.get("data"), (dict, list)) else result
        if tool == "summarize_face_activity":
            detail, issues = _activity(payload)
            metrics[tool] = detail
            findings.extend(issues)
        elif tool == "trace_person":
            detail, issues = _trajectory(payload)
            metrics[tool] = detail
            findings.extend(issues)
        elif tool == "search_people":
            detail, issues = _people(payload)
            metrics[tool] = detail
            findings.extend(issues)
        elif tool == "get_face_overview":
            detail, issues = _overview(payload)
            metrics[tool] = detail
            findings.extend(issues)
        elif tool == "compare_face_activity":
            detail, issues = _compare_activity(payload)
            metrics[tool] = detail
            findings.extend(issues)
        elif tool == "image_similarity_search":
            detail, issues = _image_search(payload)
            metrics[tool] = detail
            findings.extend(issues)

    failed_steps = [
        {"tool": step.get("tool", "unknown"), "status": step.get("status"), "error_code": step.get("error_code")}
        for step in steps
        if step.get("status") in {"error", "rejected", "unavailable"}
    ]
    truncated_tools = [
        name for name, value in metrics.items()
        if isinstance(value, dict) and (value.get("truncated") or value.get("camera_distribution_limited"))
    ]
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
            continue
        if row["result"].get("truncated") and row.get("tool") not in truncated_tools:
            truncated_tools.append(str(row.get("tool") or "unknown"))
    if failed_steps:
        findings.append({
            "code": "partial_execution",
            "severity": "warning",
            "title": "部分数据源或工具未完成",
            "detail": f"{len(failed_steps)} 个步骤失败、被拒绝或不可用。",
            "source_tools": [item["tool"] for item in failed_steps],
        })
    if truncated_tools:
        findings.append({
            "code": "result_truncated",
            "severity": "warning",
            "title": "部分指标覆盖不完整",
            "detail": "部分记录或摄像头分布受到 VIDEO 返回上限影响，报告已标出对应分析项。",
            "source_tools": truncated_tools,
        })

    completed = len(steps) - len(failed_steps)
    status = "no_data" if not metrics else ("partial" if failed_steps or truncated_tools else "complete")
    summary = "本次没有可用于统计的结构化结果。" if not metrics else f"基于 {len(metrics)} 类分析结果生成 {len(findings)} 条可核查发现。"
    refs = evidence_refs or []
    for finding in findings:
        sources = set(finding.get("source_tools", []))
        finding["evidence_refs"] = [ref for ref in refs if ref.get("source_tool") in sources][:20]
    next_steps = []
    if truncated_tools:
        next_steps.append("缩小时间范围或降低查询结果量，再核查被截断的数据。")
    if failed_steps:
        next_steps.append("检查对应 VIDEO 接口状态和当前用户的数据授权后重试。")
    if any(f.get("code") == "image_search_unavailable" for f in findings):
        next_steps.append("配置并确认 VIDEO detector、embedding model 与 FAISS matcher 后再启用图片相似检索。")
    if not next_steps:
        next_steps.append("需要更多背景时，可指定时间范围、人员编号或比较周期继续分析。")
    return {
        "schema_version": REPORT_VERSION,
        "status": status,
        "summary": summary,
        "metrics": metrics,
        "findings": findings,
        "data_lineage": sorted({str(row.get("result", {}).get("source")) for row in results if isinstance(row, dict) and isinstance(row.get("result"), dict) and row.get("result", {}).get("source")}),
        "data_quality": {"status": status, "truncated_tools": truncated_tools, "failed_step_count": len(failed_steps)},
        "follow_up_suggestions": next_steps,
        "execution": {"completed_steps": max(completed, 0), "failed_steps": failed_steps},
        "methodology": [
            "仅对当前请求返回的数据进行确定性汇总，不跨请求推断或补齐缺失值。",
            "每日变化率仅在相邻两个返回日期均有记录且前一日非零时计算。",
            "跨期日均按两个给定时间戳之间的时长折算，短于一天的窗口按一天展示。",
            "轨迹间隔按相邻抓拍时间差计算；没有摄像头坐标时不推断距离、速度或方向。",
        ],
        "limitations": limitations,
    }


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"items": payload, "total": len(payload)}
    return {}



def _overview(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    face_records = _number(data.get("face_records"))
    identified = _number(data.get("identified_records"))
    pending = _number(data.get("pending_review"))
    rate = round(identified / face_records, 4) if face_records else None
    findings = []
    if pending:
        findings.append({"code": "pending_review", "severity": "info", "title": "待复核记录", "detail": f"平台当前报告 {pending} 条待复核记录。", "source_tools": ["get_face_overview"]})
    if data.get("image_search_ready") is False:
        findings.append({"code": "image_search_unavailable", "severity": "warning", "title": "图片检索未就绪", "detail": "VIDEO 当前未配置可用的人脸检测、特征提取和向量匹配链路。", "source_tools": ["get_face_overview"]})
    return ({
        "people": _number(data.get("people")),
        "face_records": face_records,
        "identified_records": identified,
        "pending_review": pending,
        "identification_rate": rate,
        "image_search_ready": data.get("image_search_ready"),
    }, findings)


def _compare_activity(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    periods = {}
    for key in ("period_a", "period_b"):
        period = data.get(key) if isinstance(data.get(key), dict) else {}
        activity, _ = _activity(period.get("activity"))
        start = _parse_datetime(period.get("start_time"))
        end = _parse_datetime(period.get("end_time"))
        days = max((end - start).total_seconds() / 86400, 1) if start and end else None
        periods[key] = {"start_time": period.get("start_time"), "end_time": period.get("end_time"), "days": round(days, 2) if days else None, "activity": activity}
    a, b = periods["period_a"], periods["period_b"]
    total_a = a["activity"]["total_records"]
    total_b = b["activity"]["total_records"]
    rate_a = round(total_a / a["days"], 2) if a["days"] else None
    rate_b = round(total_b / b["days"], 2) if b["days"] else None
    normalized_change = round((rate_b - rate_a) / rate_a, 4) if rate_a else None
    identification_a = a["activity"]["identification_rate"]
    identification_b = b["activity"]["identification_rate"]
    camera_a = {str(row.get("device_id") or row.get("camera_name") or "unknown"): row["count"] for row in a["activity"]["by_camera"]}
    camera_b = {str(row.get("device_id") or row.get("camera_name") or "unknown"): row["count"] for row in b["activity"]["by_camera"]}
    camera_deltas = sorted(({
        "camera": camera,
        "period_a_count": camera_a.get(camera, 0),
        "period_b_count": camera_b.get(camera, 0),
        "period_a_per_day": round(camera_a.get(camera, 0) / a["days"], 2) if a["days"] else None,
        "period_b_per_day": round(camera_b.get(camera, 0) / b["days"], 2) if b["days"] else None,
        "count_delta": camera_b.get(camera, 0)-camera_a.get(camera, 0),
        "per_day_delta": round(camera_b.get(camera, 0) / b["days"] - camera_a.get(camera, 0) / a["days"], 2) if a["days"] and b["days"] else None,
    } for camera in set(camera_a) | set(camera_b)), key=lambda row: abs(row["per_day_delta"] or 0), reverse=True)[:10]
    findings = []
    if rate_a is not None and rate_b is not None:
        change_text = f"{normalized_change:+.1%}" if normalized_change is not None else "无法计算（对比期 A 日均为零）"
        findings.append({"code": "period_activity_comparison", "severity": "info", "title": "两期活动对比", "detail": f"日均抓拍量由 {rate_a} 条/日变为 {rate_b} 条/日，变化 {change_text}。", "source_tools": ["compare_face_activity"]})
    if identification_a is not None and identification_b is not None:
        findings.append({"code": "identification_rate_comparison", "severity": "info", "title": "人员关联率对比", "detail": f"人员关联率从 {identification_a:.1%} 变为 {identification_b:.1%}，变化 {(identification_b-identification_a):+.1%}。", "source_tools": ["compare_face_activity"]})
    if a["activity"]["camera_distribution_limited"] or b["activity"]["camera_distribution_limited"]:
        findings.append({"code": "comparison_camera_distribution_limited", "severity": "warning", "title": "部分摄像头未进入对比", "detail": "至少一个周期的摄像头分布未覆盖全部抓拍记录。", "source_tools": ["compare_face_activity"]})
    if a["activity"]["truncated"] or b["activity"]["truncated"]:
        findings.append({"code": "comparison_truncated", "severity": "warning", "title": "对比数据不完整", "detail": "至少一个时间段的活动记录被接口结果上限截断。", "source_tools": ["compare_face_activity"]})
    return ({"period_a": a, "period_b": b, "metrics": {"capture_count_delta": total_b-total_a, "capture_count_change_ratio": round((total_b-total_a)/total_a, 4) if total_a else None, "daily_rate_a": rate_a, "daily_rate_b": rate_b, "daily_rate_change_ratio": normalized_change, "identification_rate_delta": round(identification_b-identification_a, 4) if identification_a is not None and identification_b is not None else None, "camera_deltas": camera_deltas}}, findings)

def _activity(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    total = _number(data.get("total_records", data.get("total", data.get("records_analyzed", 0))))
    analyzed = _number(data.get("records_analyzed", total))
    identified = _number(data.get("identified_records", 0))
    by_day = _rows(data.get("by_day"))
    by_camera = _rows(data.get("by_camera"))
    findings: list[dict[str, Any]] = []
    identification_rate = round(identified / analyzed, 4) if analyzed else None
    if data.get("truncated") or (total > analyzed):
        findings.append({"code": "activity_truncated", "severity": "warning", "title": "活动记录不完整", "detail": f"统计覆盖 {analyzed} 条记录，接口报告总量为 {total} 条。", "source_tools": ["summarize_face_activity"]})
    if by_day:
        daily = sorted((str(row.get("day", "")), _number(row.get("count"))) for row in by_day)
        busiest = max(daily, key=lambda item: item[1])
        findings.append({"code": "busiest_day", "severity": "info", "title": "抓拍最多的日期", "detail": f"{busiest[0]} 共 {busiest[1]} 条记录。", "source_tools": ["summarize_face_activity"]})
        if len(daily) > 1 and daily[-2][1] > 0:
            change = round((daily[-1][1] - daily[-2][1]) / daily[-2][1], 4)
            findings.append({"code": "daily_change", "severity": "info", "title": "最近日期抓拍变化", "detail": f"{daily[-1][0]} 相比 {daily[-2][0]} 变化 {change:+.1%}（{daily[-2][1]} → {daily[-1][1]}）。", "source_tools": ["summarize_face_activity"]})
    if by_day and len(by_day) >= 4:
        ordered_counts = sorted(value for _, value in daily)
        q1 = ordered_counts[int(0.25 * (len(ordered_counts) - 1))]
        q3 = ordered_counts[int(0.75 * (len(ordered_counts) - 1))]
        upper_fence = q3 + 1.5 * (q3 - q1)
        outliers = [(day, value) for day, value in daily if value > upper_fence]
        for day, value in outliers[:5]:
            findings.append({"code": "high_activity_outlier", "severity": "info", "title": "高于近期分布的日期", "detail": f"{day} 有 {value} 条记录，高于当前窗口的 Tukey 上界 {upper_fence:g}。这是探索性异常提示，应结合业务背景复核。", "source_tools": ["summarize_face_activity"]})
    camera_total = sum(_number(row.get("count")) for row in by_camera)
    camera_distribution_limited = bool(analyzed and camera_total < analyzed)
    if by_camera:
        camera_key = lambda row: _number(row.get("count"))
        top = max(by_camera, key=camera_key)
        count = camera_key(top)
        findings.append({"code": "top_camera", "severity": "info", "title": "抓拍量最高的摄像头", "detail": f"{top.get('camera_name') or top.get('device_id') or 'unknown'} 共 {count} 条记录。", "source_tools": ["summarize_face_activity"]})
        if camera_distribution_limited:
            findings.append({"code": "camera_distribution_limited", "severity": "warning", "title": "摄像头分布仅覆盖部分记录", "detail": f"已返回摄像头分布覆盖 {camera_total}/{analyzed} 条统计记录；平台仅返回部分高频摄像头或存在未归属摄像头。", "source_tools": ["summarize_face_activity"]})
    if analyzed and identified < analyzed:
        findings.append({"code": "unidentified_records", "severity": "info", "title": "未关联人员档案的记录", "detail": f"{analyzed - identified} 条记录未关联到人员档案（{1 - identification_rate:.1%}）。", "source_tools": ["summarize_face_activity"]})
    return ({
        "total_records": total,
        "records_analyzed": analyzed,
        "identified_records": identified,
        "unidentified_records": max(analyzed - identified, 0),
        "identification_rate": identification_rate,
        "unique_people": _number(data.get("unique_people")),
        "truncated": bool(data.get("truncated")) or total > analyzed,
        "camera_distribution_limited": camera_distribution_limited,
        "by_day": daily if by_day else [],
        "by_camera": sorted(({"device_id": row.get("device_id"), "camera_name": row.get("camera_name"), "count": _number(row.get("count")), "share_of_reported_camera_counts": round(_number(row.get("count")) / camera_total, 4) if by_camera and camera_total else None} for row in by_camera), key=lambda item: item["count"], reverse=True),
        "reported_camera_count_sum": sum(_number(row.get("count")) for row in by_camera),
    }, findings)


def _trajectory(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    person = data.get("person") if isinstance(data.get("person"), dict) else {}
    events = _rows(data.get("events", data.get("items")))
    events = sorted(events, key=lambda row: _parse_datetime(row.get("captured_at")) or datetime.min.replace(tzinfo=timezone.utc))
    cameras = [str(row.get("camera_name") or row.get("device_id") or "unknown") for row in events]
    unique_cameras = list(dict.fromkeys(cameras))
    times = [(row, _parse_datetime(row.get("captured_at"))) for row in events]
    missing_timestamps = sum(ts is None for _, ts in times)
    times = [(row, ts) for row, ts in times if ts is not None]
    gaps = [(times[index][1] - times[index - 1][1]).total_seconds() for index in range(1, len(times))]
    confidence = [_number_or_none(row.get("confidence")) for row in events]
    confidence = [value for value in confidence if value is not None]
    match_scores = [_number_or_none(row.get("match_score")) for row in events]
    match_scores = [value for value in match_scores if value is not None]
    total = _number(data.get("total_records", len(events)))
    findings: list[dict[str, Any]] = []
    if events:
        findings.append({"code": "trajectory_coverage", "severity": "info", "title": "轨迹覆盖", "detail": f"返回 {len(events)} 条抓拍，涉及 {len(unique_cameras)} 个摄像头。", "source_tools": ["trace_person"]})
    if gaps:
        largest = max(gaps)
        findings.append({"code": "largest_capture_gap", "severity": "info", "title": "最长相邻抓拍间隔", "detail": f"相邻记录的最长间隔为 {_duration(largest)}。这只描述记录间隔，不代表人员移动时间。", "source_tools": ["trace_person"]})
    if missing_timestamps:
        findings.append({"code": "trajectory_missing_timestamps", "severity": "warning", "title": "轨迹存在缺失时间", "detail": f"{missing_timestamps} 条记录没有可解析的抓拍时间，未纳入间隔计算。", "source_tools": ["trace_person"]})
    if total > len(events):
        findings.append({"code": "trajectory_truncated", "severity": "warning", "title": "轨迹结果被限制", "detail": f"返回 {len(events)} 条，共有 {total} 条符合条件记录。", "source_tools": ["trace_person"]})
    return ({
        "person_id": person.get("id"),
        "person_code": person.get("person_code"),
        "returned_events": len(events),
        "timestamped_events": len(times),
        "missing_timestamps": missing_timestamps,
        "total_events": total,
        "truncated": total > len(events),
        "unique_camera_count": len(unique_cameras),
        "camera_sequence": unique_cameras,
        "first_seen": times[0][1].isoformat() if times else None,
        "last_seen": times[-1][1].isoformat() if times else None,
        "elapsed_seconds": int((times[-1][1] - times[0][1]).total_seconds()) if len(times) > 1 else 0,
        "median_capture_gap_seconds": round(median(gaps), 1) if gaps else None,
        "max_capture_gap_seconds": round(max(gaps), 1) if gaps else None,
        "average_confidence": round(mean(confidence), 4) if confidence else None,
        "average_match_score": round(mean(match_scores), 4) if match_scores else None,
    }, findings)


def _people(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    people = _rows(data.get("items", data.get("people", data.get("results"))))
    total = _number(data.get("total", len(people)))
    focus = [person for person in people if person.get("is_blacklist") is True]
    captures = [_number(person.get("capture_count")) for person in people]
    findings: list[dict[str, Any]] = []
    if total > len(people):
        findings.append({"code": "people_list_limited", "severity": "warning", "title": "人员列表受结果上限影响", "detail": f"当前返回 {len(people)} 条，服务报告匹配总数 {total} 条。", "source_tools": ["search_people"]})
    return ({
        "returned_people": len(people),
        "total_matches": total,
        "focus_list_count": len(focus),
        "capture_count_sum_for_returned_people": sum(captures),
        "mean_capture_count": round(mean(captures), 2) if captures else 0,
        "top_capture_people": [
            {"person_id": person.get("id"), "person_code": person.get("person_code"), "capture_count": _number(person.get("capture_count"))}
            for person in sorted(people, key=lambda item: _number(item.get("capture_count")), reverse=True)[:5]
        ],
    }, findings)


def _image_search(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = _payload_dict(payload)
    matches = _rows(data.get("matches", data.get("items", data.get("results"))))
    scores = [_number_or_none(item.get("similarity", item.get("score", item.get("match_score")))) for item in matches]
    scores = [value for value in scores if value is not None]
    findings = []
    if matches:
        findings.append({"code": "image_candidates", "severity": "info", "title": "图片检索候选", "detail": f"VIDEO 返回 {len(matches)} 个候选；候选仅供人工复核，不构成身份确认。", "source_tools": ["image_similarity_search"]})
    return ({"available": bool(data.get("available", True)), "candidate_count": len(matches), "top_candidate_score": max(scores) if scores else None}, findings)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _number(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _number_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    if minutes:
        return f"{minutes} 分钟 {seconds} 秒"
    return f"{seconds} 秒"
