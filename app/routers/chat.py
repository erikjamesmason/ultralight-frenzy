"""Chat endpoints — stateless (client history) and stateful (server sessions)."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

from agent.agent import run_chat_turn
from app.schemas import (
    ChatRequest,
    ChatResponse,
    SessionCreateResponse,
    SessionMessageRequest,
    SessionMessageResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))
_CLEANUP_INTERVAL = 300  # run cleanup every 5 minutes


@dataclass
class _SessionEntry:
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_access: float = field(default_factory=time.monotonic)


# In-memory session store: session_id → _SessionEntry.
# For production, swap this dict for Redis or another external store.
_sessions: dict[str, _SessionEntry] = {}
_cleanup_task: asyncio.Task | None = None


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        _purge_stale()


def _purge_stale() -> None:
    now = time.monotonic()
    stale = [sid for sid, entry in _sessions.items()
             if now - entry.last_access > SESSION_TTL_SECONDS]
    for sid in stale:
        del _sessions[sid]
    if stale:
        import logging
        logging.getLogger(__name__).info("Purged %d stale sessions", len(stale))


@router.post("", response_model=ChatResponse)
async def chat_stateless(req: ChatRequest) -> ChatResponse:
    """
    Stateless chat — the client owns the conversation history.

    On the first message send an empty `history` (or omit it). Each response
    includes an updated `history`; pass it back verbatim in the next request
    to continue the conversation. The history is an opaque JSON structure —
    don't modify it between calls.
    """
    history = list(req.history)
    response, updated = await run_chat_turn(req.message, history)
    return ChatResponse(response=response, history=updated)


@router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session() -> SessionCreateResponse:
    """
    Create a new server-managed session. Returns a `session_id` to use in
    subsequent `/chat/sessions/{session_id}` calls.
    """
    global _cleanup_task
    session_id = str(uuid.uuid4())
    _sessions[session_id] = _SessionEntry()
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())
    return SessionCreateResponse(session_id=session_id)


@router.post("/sessions/{session_id}", response_model=SessionMessageResponse)
async def session_message(
    session_id: str, req: SessionMessageRequest
) -> SessionMessageResponse:
    """
    Send a message in an existing session. History is stored server-side;
    the client only needs to track the `session_id`.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    entry = _sessions[session_id]
    entry.last_access = time.monotonic()
    response, entry.messages = await run_chat_turn(req.message, entry.messages)
    return SessionMessageResponse(response=response, session_id=session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Clear and remove a session."""
    _sessions.pop(session_id, None)
