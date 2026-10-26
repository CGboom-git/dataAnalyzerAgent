"""OpenAI-compatible function schemas exposed to Qwen or another configured model."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_people",
            "description": "按姓名、人员编号、描述或标签查询当前用户有权访问的人脸档案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "姓名、人员编号或关键词，最多120字符"},
                    "is_blacklist": {"type": "boolean", "description": "可选：是否仅查重点关注人员"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_face_activity",
            "description": "统计指定时间范围内的人脸抓拍量、人员数、按日期与摄像头的分布。时间使用ISO 8601。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_time": {"type": "string", "description": "可选的ISO 8601起始时间"},
                    "end_time": {"type": "string", "description": "可选的ISO 8601结束时间"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_person",
            "description": "查看已知人员在指定时间范围内的跨摄像头抓拍轨迹。",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {"type": "integer", "minimum": 1},
                    "start_time": {"type": "string", "description": "可选的ISO 8601起始时间"},
                    "end_time": {"type": "string", "description": "可选的ISO 8601结束时间"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["person_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_face_overview",
            "description": "读取平台人脸档案、抓拍记录、待复核数量和图片检索就绪状态。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_face_activity",
            "description": "对比两个明确给出的时间段的人脸抓拍量和人员分布；两个时间段都必须提供起止时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_a_start": {"type": "string", "description": "对比期 A 的 ISO 8601 起始时间"},
                    "period_a_end": {"type": "string", "description": "对比期 A 的 ISO 8601 结束时间"},
                    "period_b_start": {"type": "string", "description": "对比期 B 的 ISO 8601 起始时间"},
                    "period_b_end": {"type": "string", "description": "对比期 B 的 ISO 8601 结束时间"},
                },
                "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"],
                "additionalProperties": False,
            },
        },
    },
]
