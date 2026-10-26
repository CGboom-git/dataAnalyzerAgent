# EasyAIoT face Agent context

## Platform implementation reviewed

The WSL platform places `run_face_analysis_agent` in `AI/app/services/face_analysis_agent.py`. It uses LangGraph with an OpenAI-compatible model, restricts model-selected operations to read-only tools, and calls VIDEO face-analysis APIs over HTTP. The corresponding VIDEO blueprint exposes `/overview`, `/people`, `/activity`, `/people/{id}/trajectory`, `/image-search`, and `/image-search/base64`. VIDEO owns face records, query logic, face models, vector matching and images.

The public component mirrors this boundary while adding explicit local modules for API hosting, domain contracts, model/VIDEO adapters, validated tools, deterministic report generation and optional run persistence. It adds no new production VIDEO route: a two-period comparison simply calls the existing activity API twice.

## Current Agent functions

- Overview of people, face records, identified records, pending review and image-search readiness.
- Profile search with bounded filters and result count.
- Activity distribution with identification rate, peak camera/day, daily change and exploratory Tukey outlier prompts when there are enough daily observations.
- Two-period activity comparison with total delta, per-day rates, identification-rate change and per-camera changes.
- Person trajectory with temporal span, camera sequence, capture-gap statistics and available confidence/match-score summaries.
- Optional image similarity preflight that returns candidates for review.

## Stack and contract boundary

The component uses the WSL AI stack boundary: Flask 2.3, LangGraph 1.x, `requests`, and Pandas-backed synthetic offline analysis. It calls Qwen through an OpenAI-compatible chat-completions interface. Production SQLAlchemy/PostgreSQL, face inference, Faiss and MinIO remain in VIDEO. The existing Vue 3 WEB remains the platform UI.

The Agent can be mounted as a Flask Blueprint, and host-owned `AgentRunRecorder` callbacks can persist trace ID, role/stage, contract version, tool outcomes, evidence references, risk flags and the computed report. The platform remains responsible for authentication, data scope, user history and UI. A shared VIDEO API token alone does not prove per-user authorization; deployment must define host/gateway enforcement or trusted scope propagation.

## Interpretation rules

The deterministic report separates source counts from derived metrics, tags failures and truncation, and attaches evidence refs when available. Daily/camera distributions are limited to the VIDEO response. Time between two sightings is a record gap, not travel duration. Face similarity is a candidate score, not identity proof. Outlier prompts are exploratory and need operational context.

All local data is synthetic. Rights to publish platform-derived code/contracts remain subject to review; see `LICENSE_STATUS.md`.
