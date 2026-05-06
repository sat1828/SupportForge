"""
ARQ Worker — runs agent jobs in background.
Invariant 14: POST /chat returns 202 immediately; processing is async.
max_jobs=20 enforced at WorkerSettings level.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.agents.state import initial_state
from app.config import settings

logger = logging.getLogger(__name__)

# Semaphore for concurrency control (Invariant 14)
_agent_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    global _agent_semaphore
    if _agent_semaphore is None:
        _agent_semaphore = asyncio.Semaphore(settings.max_concurrent_agent_executions)
    return _agent_semaphore


async def run_agent_job(
    ctx: dict[str, Any],
    ticket_id: str,
    message: str,
    thread_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    ARQ task — executes LangGraph agent for a ticket.
    Bounded by ExecutionBudget: max 10 steps, 10s latency, 5 LLM calls, 5000 tokens.
    """
    t0 = time.monotonic()
    redis: aioredis.Redis = ctx["redis"]

    async with get_semaphore():
        try:
            await _publish_event(redis, ticket_id, "status", {"status": "processing"})

            from app.agents.graph import get_graph
            graph = await get_graph()

            state = initial_state(ticket_id, message)
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": settings.max_steps_per_ticket + 2,  # safety margin
            }

            result_state: dict[str, Any] = {}
            async for event in graph.astream(state, config):
                # Stream each node output as SSE chunk
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue
                    if isinstance(node_output, dict):
                        # Stream response_meta update
                        meta = node_output.get("response_meta")
                        if meta:
                            await _publish_event(redis, ticket_id, "meta", meta)
                        # Stream any new AI messages
                        msgs = node_output.get("messages", [])
                        for msg in msgs[-1:]:  # only last new message
                            content = getattr(msg, "content", "")
                            if content and hasattr(msg, "__class__") and "AI" in msg.__class__.__name__:
                                await _publish_chunk(redis, ticket_id, content)
                        result_state = node_output

            final_meta = result_state.get("response_meta") or {}
            final_meta["fast_path_used"] = False

            # Persist to DB
            await _persist_result(ticket_id, user_id, result_state)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await _publish_event(redis, ticket_id, "done", {
                "ticket_id": ticket_id,
                "elapsed_ms": elapsed_ms,
                "response_meta": final_meta,
            })

            logger.info(
                "agent_job_complete",
                extra={"ticket_id": ticket_id, "elapsed_ms": elapsed_ms},
            )
            return {"status": "complete", "ticket_id": ticket_id, "elapsed_ms": elapsed_ms}

        except TimeoutError:
            # Hard timeout (ARQ job_timeout=15s)
            await _publish_event(redis, ticket_id, "error", {
                "message": "Request timed out. A human agent will assist you.",
                "response_meta": {
                    "confidence": 0.0, "action": "escalate",
                    "reason": "System timeout — human agent assigned.",
                    "step_count": 0, "fast_path_used": False,
                    "tool_calls_summary": [], "escalation_reason": "worker_timeout",
                },
            })
            return {"status": "timeout", "ticket_id": ticket_id}

        except Exception as e:
            logger.error(f"agent_job_failed ticket={ticket_id}: {e}", exc_info=True)
            await _publish_event(redis, ticket_id, "error", {
                "message": "An error occurred. A human agent will assist you.",
                "response_meta": {
                    "confidence": 0.0, "action": "escalate",
                    "reason": "Unexpected error — human agent assigned.",
                    "step_count": 0, "fast_path_used": False,
                    "tool_calls_summary": [], "escalation_reason": str(e),
                },
            })
            return {"status": "failed", "ticket_id": ticket_id, "error": str(e)}


async def _publish_event(redis: aioredis.Redis, ticket_id: str, event: str, data: dict) -> None:
    channel = f"ticket:{ticket_id}:stream"
    payload = json.dumps({"event": event, "data": data})
    await redis.publish(channel, payload)


async def _publish_chunk(redis: aioredis.Redis, ticket_id: str, text: str) -> None:
    await _publish_event(redis, ticket_id, "chunk", {"text": text})


async def _persist_result(ticket_id: str, user_id: str, state: dict[str, Any]) -> None:
    """Persist final state to DB: ticket update + conversation + performance log."""
    try:
        from app.database import AsyncSessionLocal
        from app.models.human_correction import AgentPerformanceLog
        from app.models.ticket import Ticket, TicketStatus
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            # Update ticket
            result = await db.execute(
                select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
            )
            ticket = result.scalar_one_or_none()
            if ticket:
                meta = state.get("response_meta") or {}
                if meta.get("action") == "resolve":
                    ticket.status = TicketStatus.RESOLVED
                    ticket.resolved_at = datetime.now(UTC)
                elif meta.get("action") == "escalate":
                    ticket.status = TicketStatus.ESCALATED
                ticket.confidence_score = (state.get("calibrated_confidence") or {}).get("final_score")
                ticket.llm_calls_made = state.get("budget", {}).get("llm_calls_made", 0)
                ticket.tokens_consumed = state.get("budget", {}).get("tokens_consumed", 0)
                ticket.escalation_reason = state.get("escalation_reason")

            # Write performance log (powers Invariant 18: historical_accuracy)
            perf = AgentPerformanceLog(
                ticket_id=uuid.UUID(ticket_id),
                intent=state.get("intent", "general_query"),
                tool_used=(state.get("tool_calls_log") or [{}])[-1].get("name") if state.get("tool_calls_log") else None,
                success=(state.get("response_meta") or {}).get("action") == "resolve",
                final_confidence=(state.get("calibrated_confidence") or {}).get("final_score"),
                steps_taken=state.get("budget", {}).get("steps_taken", 0),
                total_latency_ms=0,
            )
            db.add(perf)
            await db.commit()

            # Update Prometheus
            from app.observability.prometheus import (
                cost_per_ticket_histogram, llm_calls_per_ticket_histogram,
                confidence_score_histogram
            )
            budget = state.get("budget", {})
            cost_per_ticket_histogram.observe(budget.get("tokens_consumed", 0))
            llm_calls_per_ticket_histogram.observe(budget.get("llm_calls_made", 0))
            if ticket and ticket.confidence_score:
                confidence_score_histogram.observe(ticket.confidence_score)

    except Exception as e:
        logger.error(f"persist_result_failed: {e}", exc_info=True)


class WorkerSettings:
    """ARQ worker configuration — Invariant 14 enforced via max_jobs."""
    from arq.connections import RedisSettings
    import os as _os
    redis_settings = RedisSettings.from_dsn(_os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    functions = [run_agent_job]
    max_jobs = 20           # Invariant 14: max 20 concurrent
    job_timeout = 15        # Hard kill: budget=10s + 5s buffer
    keep_result = 3600      # Job result kept 1h for polling
    queue_name = "supportforge:jobs"

    @classmethod
    def get_redis_settings(cls):
        from arq.connections import RedisSettings as RS
        return RS.from_dsn(settings.redis_url)
