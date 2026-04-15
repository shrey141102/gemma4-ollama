"""
Backwards compatibility — the app has moved to app/main.py.

This file allows `uvicorn server:app` to still work,
but the canonical entry point is `uvicorn app.main:app`.
"""

from app.main import app  # noqa: F401
