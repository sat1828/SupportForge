"""
Agent API router — SSE streaming, job enqueueing, tool approval.
Execution Rule 5: POST /chat MUST return within 50ms (never blocks on LLM).
Execution Rule 3: every response includes response_meta.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.fastpath import fast_path_executor, input_normalizer
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.ticket import Ticket
from app.schemas.agent import (
    ChatRequest, ChatResponse, ResponseMeta, ToolApprovalRequest,
)

router = APIRouter(prefix="/agent", tags=["agent"])

# Shared Redis pool (set at startup)
_redis_pool: aioredis.Redis | None = None
_limiter = None


def get_redis() -> aioredis.Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    return _redis_pool


async def init_redis() -> None:
    global _redis_pool
    _redis_pool = await aioredis.from_url(settings.redis_url, decode_responses=True)

    # Initialize rate limiter if available
    global _limiter
    try:
        from fastapi_limiter import FastAPILimiter
        from redis.asyncio import from_url
        redis_client = await from_url(settings.redis_url, encoding="utf-8")
        _limiter = FastAPILimiter(
            key_func=get_current_user_id,
            storage_uri=settings.redis_url,
        )
    except ImportError:
        pass  # Graceful degradation


@router.post("/chat/{ticket_id}", response_model=ChatResponse)
async def chat(
    ticket_id: uuid.UUID,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse | JSONResponse:
    """
    Execution Rule 5: returns 202 + job_id within 50ms.
    Fast-path cases return 200 with immediate response_meta.
    NEVER blocks waiting for LLM.
    """
    # Rate limit check
    if _limiter is not None:
        try:
            await _limiter.check("5/minute", user_id)
        except Exception:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 5 requests per minute.")

    # Fetch ticket
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # ── Normalize input (Execution Rule 7 — Invariant 21) ─────
    normalized = input_normalizer.normalize(body.message)

    if normalized.requires_clarification:
        # Execution Rule 2: explicit, not silent
        from app.observability.prometheus import noisy_input_counter
        noisy_input_counter.labels(type=normalized.clarification_reason).inc()

        clarify_meta = ResponseMeta(
            confidence=0.0,
            action="clarify",
            reason=_clarification_reason_text(normalized.clarification_reason),
            step_count=0,
            fast_path_used=False,
            tool_calls_summary=[],
        )
        return JSONResponse(
            status_code=200,
            content={
                "job_id": "",
                "status": "fast_path_resolved",
                "ticket_id": str(ticket_id),
                "response_meta": clarify_meta.model_dump(),
                "message": clarify_meta.reason,
            },
        )

    # ── Fast-path check (Execution Rule 6 — Invariant 10/11) ──
    rule = fast_path_executor.match_rule(normalized.text)
    if rule:
        ticket_data = {
            "order_id": str(ticket.id)[:8].upper(),
            "status": ticket.status,
            "customer_name": "Customer",
        }
        from app.models.user import User
        user_res = await db.execute(select(User).where(User.id == ticket.customer_id))
        customer = user_res.scalar_one_or_none()
        if customer:
            ticket_data["customer_name"] = customer.full_name

        fp_result = await fast_path_executor.execute(rule, ticket_data, ticket_data["customer_name"])

        # Track Prometheus (Invariant 11 — fast_path_used logged)
        from app.observability.prometheus import fast_path_resolutions_counter
        fast_path_resolutions_counter.labels(rule=rule.name).inc()

        meta = ResponseMeta(
            confidence=0.99,
            action="fast_path",
            reason=fp_result.message,
            step_count=0,
            fast_path_used=True,   # Execution Rule 6 — LOGGED
            tool_calls_summary=[],
            escalation_reason=None,
        )
        # Save to conversation
        await _save_message(db, ticket_id, "assistant", fp_result.message,
                            action="fast_path", confidence=0.99, fast_path_used=True)
        return JSONResponse(
            content={
                "job_id": "",
                "status": "fast_path_resolved",
                "ticket_id": str(ticket_id),
                "response_meta": meta.model_dump(),
                "message": fp_result.message,
            }
        )

    # ── Enqueue async job (Execution Rule 5) ──────────────────
    from arq import create_pool
    from arq.connections import RedisSettings
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    job = await arq_pool.enqueue_job(
        "run_agent_job",
        str(ticket_id),
        normalized.text,
        str(ticket_id),  # thread_id = ticket_id for stateful memory
        user_id,
        _job_id=f"ticket:{ticket_id}:{uuid.uuid4()}",
    )

    # Save user message to conversation
    await _save_message(db, ticket_id, "user", normalized.text)

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.job_id,
            "status": "queued",
            "ticket_id": str(ticket_id),
            "response_meta": None,
            "message": None,
        },
    )


@router.get("/chat/{ticket_id}/stream")
async def stream_result(
    ticket_id: uuid.UUID,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """SSE endpoint — client subscribes after receiving job_id."""
    redis = get_redis()

    async def event_generator() -> AsyncGenerator[str, None]:
        if redis is None:
            yield f"event: error\ndata: {{\"error\": \"Redis not available\"}}\n\n"
            return

        channel = f"ticket:{ticket_id}:stream"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    data = message["data"]
                    try:
                        parsed = json.loads(data)
                        event_type = parsed.get("event", "chunk")
                        event_data = json.dumps(parsed.get("data", {}))
                        yield f"event: {event_type}\ndata: {event_data}\n\n"
                        if event_type in ("done", "error"):
                            break
                    except json.JSONDecodeError:
                        yield f"data: {data}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/approve")
async def approve_tool_action(
    body: ToolApprovalRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """HITL approval endpoint — admin approves or rejects pending tool actions."""
    from app.models.ticket import Ticket, TicketStatus
    from sqlalchemy import select

    result = await db.execute(select(Ticket).where(Ticket.id == body.ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    from app.observability.audit import write_audit
    await write_audit(
        action="tool_approval_decision",
        actor="admin",
        ticket_id=str(body.ticket_id),
        user_id=user_id,
        detail=f"approved={body.approved}",
        metadata={"job_id": body.job_id, "modified": bool(body.modified_response)},
        db=db,
    )

    if body.approved:
        ticket.status = TicketStatus.RESOLVED
    else:
        ticket.status = TicketStatus.ESCALATED

    return {"status": "processed", "approved": body.approved}


def _clarification_reason_text(reason: str) -> str:
    messages = {
        "empty_input": "Please describe what you need help with.",
        "too_short": "Could you provide more details about your issue?",
        "injection_detected": "I couldn't understand your request. Please describe your issue in plain text.",
    }
    return messages.get(reason, "Could you please provide more details?")


async def _save_message(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    role: str,
    content: str,
    action: str | None = None,
    confidence: float | None = None,
    fast_path_used: bool = False,
) -> None:
    from app.models.conversation import Conversation
    msg = Conversation(
        ticket_id=ticket_id,
        role=role,
        content=content,
        action=action,
        confidence=confidence,
        fast_path_used=fast_path_used,
    )
    db.add(msg)
