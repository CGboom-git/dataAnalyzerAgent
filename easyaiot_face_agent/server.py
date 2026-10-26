"""Compatibility entry point for the local Flask development host."""
from .api.server import main
from .api.flask_app import create_app

__all__ = ["create_app", "main"]
