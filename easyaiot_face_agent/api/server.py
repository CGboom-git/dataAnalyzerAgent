"""Local development entry point for the EasyAIoT Face Analysis Agent component."""
from __future__ import annotations

from .flask_app import create_app


def main() -> None:
    app = create_app()
    try:
        app.run(host="127.0.0.1", port=8765, debug=False)
    finally:
        app.extensions["face_analysis_agent"].close()


if __name__ == "__main__":
    main()
