"""Local integration host using actual platform VIDEO code and a read-only DB snapshot.

This is a restricted integration fixture, not the platform's production entry point.
It does not import run.py, create tables, start background jobs, or implement tenant RLS.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import sys
from dataclasses import replace

from flask import Flask, jsonify, request
from sqlalchemy import URL, text

from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.api.flask_app import register_agent_routes
from easyaiot_face_agent.config import AgentConfig


def create_probe_app(platform_root: Path, db_config: Path, token: str, port: int):
    if len(token) < 32:
        raise ValueError("a private integration token of at least 32 characters is required")
    video_root = (platform_root / "VIDEO").resolve()
    if not (video_root / "app/blueprints/face_analysis.py").is_file():
        raise ValueError("platform face_analysis blueprint is missing")
    connection = json.loads(db_config.read_text())
    url = URL.create("postgresql+psycopg", username=connection["user"],
                     password=connection["password"], host=connection["host"],
                     port=int(connection["port"]), database=connection["dbname"])
    sys.path.insert(0, str(video_root))
    from models import db
    import models
    if Path(models.__file__).resolve() != video_root / "models.py":
        raise ValueError("unexpected platform models import")
    from app.blueprints.face_analysis import face_analysis_bp

    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {
                          "connect_timeout": 5,
                          "options": "-c default_transaction_read_only=on -c statement_timeout=10000",
                      }}, FACE_SERVICE_MODE="off", MAX_CONTENT_LENGTH=64 * 1024)
    db.init_app(app)
    with app.app_context():
        with db.engine.connect() as handle:
            if handle.execute(text("SHOW transaction_read_only")).scalar() != "on":
                raise RuntimeError("read-only database connection required")

    @app.before_request
    def restrict_probe():
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return jsonify({"error": {"code": "integration_identity_required"}}), 401
        if request.path.startswith("/video/"):
            if request.path not in {"/video/face/analysis/overview", "/video/face/analysis/activity"}:
                return jsonify({"error": {"code": "route_disabled_in_readonly_probe"}}), 403
            if request.method != "GET":
                return jsonify({"error": {"code": "read_only_method_required"}}), 405
        if request.path == "/v1/chat":
            body = request.get_json(silent=True)
            if isinstance(body, dict) and body.get("images"):
                return jsonify({"error": {"code": "images_disabled_in_readonly_probe"}}), 400

    app.register_blueprint(face_analysis_bp, url_prefix="/video/face/analysis")
    config = replace(AgentConfig.from_env(), video_base_url=f"http://127.0.0.1:{port}",
                     video_api_token=token, require_tool_approval=True)
    runtime = AgentRuntime(config)
    # This fixed scope belongs to a trusted local integration operator. It is not RLS.
    register_agent_routes(app, runtime, url_prefix="/v1", identity_resolver=lambda: {
        "tenant_id": "readonly-integration", "user_id": "authorized-operator",
    })
    return app, runtime, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--db-config", type=Path, required=True,
                        help="private JSON with host/port/user/password/dbname; never commit")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    app, runtime, db = create_probe_app(args.platform_root, args.db_config,
                                      os.environ.get("AGENT_INTEGRATION_TOKEN", ""), args.port)
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=True)
    finally:
        runtime.close()
        with app.app_context():
            db.engine.dispose()


if __name__ == "__main__":
    main()
