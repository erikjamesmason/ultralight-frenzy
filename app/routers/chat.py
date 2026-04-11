"""Chat endpoints — stateless (client history) and stateful (server sessions)."""

from __future__ import annotations

import uuid
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

# In-memory session store: session_id → Anthropic messages list.
# For production, swap this dict for Redis or another external store.
_sessions: dict[str, list[dict[str, Any]]] = {}


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
def create_session() -> SessionCreateResponse:
    """
    Create a new server-managed session. Returns a `session_id` to use in
    subsequent `/chat/sessions/{session_id}` calls.
    """
    session_id = str(uuid.uuid4())
    _sessions[session_id] = []
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
    response, _sessions[session_id] = await run_chat_turn(
        req.message, _sessions[session_id]
    )
    return SessionMessageResponse(response=response, session_id=session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Clear and remove a session."""
    _sessions.pop(session_id, None)
