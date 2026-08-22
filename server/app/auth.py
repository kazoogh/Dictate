"""API key authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app import config


def require_api_key(x_api_key: str | None = Header(default=None, alias="x-api-key")) -> None:
    expected = config.API_KEY
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
