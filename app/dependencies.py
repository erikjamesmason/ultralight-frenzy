"""FastAPI dependencies shared across routers."""
from __future__ import annotations
import os
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Validate the X-API-Key header against the API_KEY env var.
    If API_KEY is not set, the check is skipped (dev mode).
    Raises HTTP 401 if the key is set but doesn't match.
    """
    required = os.environ.get("API_KEY")
    if required and x_api_key != required:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
