"""
Authentication — simple API key check.
"""

from fastapi import Request

from app.config import API_KEY


def check_api_key(request: Request) -> bool:
    """
    Simple API key check.
    If the API_KEY env var is empty, auth is disabled.
    Supports both Bearer token and query param.
    """
    if not API_KEY:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == API_KEY
    key = request.query_params.get("api_key", "")
    return key == API_KEY
