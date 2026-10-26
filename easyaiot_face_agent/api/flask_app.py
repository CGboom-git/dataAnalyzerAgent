"""Embeddable Flask routes; authenticated identity is supplied by the host."""
from __future__ import annotations

import logging
import re
from functools import wraps
from typing import Callable

from flask import Blueprint, Flask, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, UnsupportedMediaType

from ..adapters.model_client import ModelProviderError
from ..core.runtime import AgentRuntime
from ..domain.contracts import AGENT_CONTRACT_VERSION

MAX_REQUEST_BYTES = 44 * 1024 * 1024
logger = logging.getLogger(__name__)
IdentityResolver = Callable[[], dict[str, str]]


def create_agent_blueprint(runtime: AgentRuntime, *, name: str = "face_analysis_agent",
                           identity_resolver: IdentityResolver | None = None) -> Blueprint:
    blueprint = Blueprint(name, __name__)

    def identity() -> dict:
        if identity_resolver is None:
            if runtime.config.video_base_url:
                raise ValueError("authenticated_identity_required")
            return {"tenant_id": "local-demo", "user_id": "local-user"}
        value = identity_resolver()
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) and value[key] for key in ("tenant_id", "user_id")
        ):
            raise ValueError("authenticated_identity_required")
        tenant, user = runtime._scope(value.get("tenant_id"), value.get("user_id"))
        return {"tenant_id": tenant, "user_id": user}

    def payload() -> dict:
        value = request.get_json()
        if not isinstance(value, dict):
            raise ValueError("request_object_required")
        return value

    def safe(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (BadRequest, UnsupportedMediaType):
                return jsonify({"error": {"code": "invalid_json_or_content_type"}}), 400
            except RequestEntityTooLarge:
                return jsonify({"error": {"code": "request_size_out_of_range"}}), 413
            except ValueError as exc:
                code = str(exc)
                if not re.fullmatch(r"[a-z_]{1,80}", code):
                    code = "invalid_request"
                status = 400
                if code in {"run_not_found", "checkpoint_not_found"}:
                    status = 404
                elif code in {"previous_run_incomplete", "run_not_interrupted",
                              "approval_proposal_mismatch", "checkpoint_not_resumable"}:
                    status = 409
                elif code == "authenticated_identity_required":
                    status = 401
                return jsonify({"error": {"code": code}}), status
            except ModelProviderError as exc:
                return jsonify({"error": {"code": str(exc)}}), 502
            except Exception:
                logger.exception("face agent request failed")
                return jsonify({"error": {"code": "agent_internal_error"}}), 500
        return wrapped

    @blueprint.get("/health")
    def health():
        return jsonify({
            "status": "ok", "component": "easyaiot-face-analysis-agent",
            "mode": "platform" if runtime.config.video_base_url else "synthetic-data",
            "model": "configured" if runtime.config.model_enabled else "offline-demo",
            "data_source": runtime.tools.source_name,
            "checkpoint": type(runtime.checkpointer).__name__,
        })

    @blueprint.get("/skills")
    @safe
    def skills():
        identity()
        return jsonify({"skills": runtime.skills.list()})

    @blueprint.get("/tools")
    @safe
    def tools():
        identity()
        return jsonify({"contract_version": AGENT_CONTRACT_VERSION, "tools": runtime.list_tools()})

    @blueprint.post("/chat")
    @safe
    def chat():
        scope = identity()
        body = payload()
        return jsonify(runtime.chat(
            message=body.get("message", ""), history=body.get("history", []),
            images=body.get("images", []), conversation_id=body.get("conversation_id"),
            **scope,
        ))

    @blueprint.get("/runs/<thread_id>")
    @safe
    def status(thread_id):
        return jsonify(runtime.status(thread_id, **identity()))

    @blueprint.get("/runs/<thread_id>/checkpoints")
    @safe
    def checkpoints(thread_id):
        return jsonify({"thread_id": thread_id,
                        "checkpoints": runtime.checkpoints(thread_id, **identity())})

    @blueprint.post("/runs/<thread_id>/resume")
    @safe
    def resume(thread_id):
        scope, body = identity(), payload()
        return jsonify(runtime.resume(
            thread_id, approved=body.get("approved"),
            proposal_digest=body.get("proposal_digest"), **scope,
        ))

    @blueprint.post("/runs/<thread_id>/rollback")
    @safe
    def rollback(thread_id):
        scope, body = identity(), payload()
        checkpoint_id = body.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("checkpoint_id_required")
        return jsonify(runtime.rollback(thread_id, checkpoint_id, **scope))

    @blueprint.post("/runs/<thread_id>/cancel")
    @safe
    def cancel(thread_id):
        return jsonify(runtime.cancel(thread_id, **identity()))

    return blueprint


def register_agent_routes(app: Flask, runtime: AgentRuntime | None = None, *,
                          url_prefix: str = "/api/agent/face",
                          identity_resolver: IdentityResolver | None = None) -> AgentRuntime:
    selected = runtime or AgentRuntime()
    if app.config.get("MAX_CONTENT_LENGTH") is None:
        app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.register_blueprint(create_agent_blueprint(
        selected, identity_resolver=identity_resolver,
    ), url_prefix=url_prefix.rstrip("/"))
    app.extensions["face_analysis_agent"] = selected
    return selected


def create_app(runtime: AgentRuntime | None = None, *,
               identity_resolver: IdentityResolver | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    register_agent_routes(app, runtime, url_prefix="/v1", identity_resolver=identity_resolver)
    return app
