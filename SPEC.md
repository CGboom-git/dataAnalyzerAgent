# Product specification — EasyAIoT Face Analysis Agent

## Purpose

Provide a modular LangGraph implementation of the EasyAIoT face-data Agent component. It should demonstrate real Agent responsibilities—query planning, constrained service access, multi-step orchestration, deterministic analytics, evidence linking, quality reporting and platform run integration—while remaining a component that depends on EasyAIoT for production behavior.

## User workflows

1. Ask for a face-data system overview and receive platform record, identification and review-queue counts.
2. Search for a person by profile fields and inspect returned profile summaries.
3. Ask for activity in a time window; receive totals, daily and camera distributions, identification coverage, peak day/camera and daily movement where data supports it.
4. Compare two explicitly bounded periods; receive raw totals and per-day normalized rates so unequal windows are not compared as if they had equal length.
5. Inspect a known person's trajectory; receive record coverage, camera sequence, first/last sightings, elapsed record span, gaps and available score summaries.
6. Submit an image for a VIDEO similarity search; receive candidate count and references with a clear human-review limitation.

## Response requirements

- Preserve platform-facing `assistant_reply`, `agent_steps`, and `analysis_results` fields.
- Include a contract version and generated `trace_id`.
- Provide a structured `analysis_report` with metrics, findings, data lineage, quality status, method, limitations and follow-up suggestions.
- Distinguish successful, rejected, failed, unavailable and truncated tool steps.
- Link findings to evidence identifiers when the platform API supplies them.
- Do not state that a similarity candidate is a verified identity or that time gaps establish physical travel.

## Platform responsibilities

AI/WEB own conversation auth, user scope, persistence and UI. VIDEO owns PostgreSQL/ORM access, person and face records, camera metadata, face detection/embedding, Faiss and MinIO. The component calls the existing AI model and VIDEO APIs over HTTP and may pass a run record to a host-owned persistence callback.

## Local development

Version 0.2 adds a unified lifecycle for chat/resume/replay/cancel, identity-scoped
checkpoint threads, bounded checkpoint-backed dialogue and optional SQLite storage.
Approval binds the concrete proposal; image approval happens before image I/O.
The only built-in long-term memory is confirmed structured preferences. Five trusted
skills and a schema-validating host MCP bridge are included. See AGENT_RUNTIME.md.

The deterministic offline client and synthetic Pandas repository use the same graph, tool catalog and report builder. The sample events support filtering, trend summaries, person trajectories, and period comparisons. This mode is for inspection and development; it is not a face-recognition simulation or production performance test.

## Non-goals and safety boundaries

- Rebuild the EasyAIoT platform, web console, device ingestion, face-model hosting, identity store or camera controls.
- Execute arbitrary SQL, arbitrary HTTP, code from the model, or state-changing operations.
- Make decisions about access, discipline, safety action or a person's identity from generated analysis alone.
- Publish real biometric data, endpoints, credentials or platform-derived code without clearance.
