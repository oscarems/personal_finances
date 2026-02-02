"""Backward-compatible ASGI entrypoint.

Allows legacy commands like: uvicorn backend.app:app
"""
from finance_app.app import app

__all__ = ["app"]
