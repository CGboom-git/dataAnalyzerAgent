# Offline examples

## Reproduce the demonstration

Install with dev and persistence extras, then run:

~~~bash
python examples/demo.py --output artifacts/demo.json
~~~

The script explicitly uses synthetic configuration. It executes all five text query
types, closes/reopens the SQLite runtime, resumes an approval, rejects another run,
and forks a historical checkpoint which requires a fresh approval.
See DEMO_OUTPUT.md for the checked example summary and docs/VERIFICATION.md for checks.

Real endpoint verification is separate:

~~~bash
python examples/smoke_live.py
~~~

It requires explicit model/VIDEO settings and authenticated smoke identity; it does
not automatically approve a real tool request or print raw production data.

The local fixtures are synthetic only. They cover multiple people, cameras, days and two separated reporting windows to make deterministic summaries and comparisons inspectable.

Try these prompts against the local host:

- `给我人脸数据总览` — platform-equivalent overview using the synthetic adapter.
- `统计 2026-04-20 到 2026-04-26 的抓拍活动` — activity totals and distributions.
- `对比 2026-04-20T00:00:00Z 到 2026-04-26T23:59:59Z 与 2026-05-01T00:00:00Z 到 2026-05-07T23:59:59Z 的抓拍活动` — two bounded periods. Both start/end pairs are explicit.
- `查询 DEMO-A` — search a synthetic person profile.
- `查看人员编号 1001 在 2026-04-20T00:00:00Z 到 2026-05-07T23:59:59Z 的跨摄像头轨迹` — synthetic trajectory summary.

The main response includes both the human-readable answer and a machine-readable `analysis_report`. Compare-period activity is normalized by the requested time span; totals remain visible so callers can inspect the denominator and source data.
# 真实模型的分层检查

配置模型后运行 `python examples/smoke_model.py`，验证真实模型工具调用、审批恢复及合成数据报告。
它不会连接真实 VIDEO。两端真实接入使用 smoke_live.py，并遵守宿主身份和审批要求。
具体结果和环境限制见 ../docs/LIVE_INTEGRATION.md。
