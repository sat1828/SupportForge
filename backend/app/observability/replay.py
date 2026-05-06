"""
Replay system — stores AgentStep rows and handles tiered retention.
Invariant 8: steps > 7 days → compressed (input_state/llm_prompt nullified)
Invariant 9: steps > 90 days → deleted
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_step import AgentStep

logger = logging.getLogger(__name__)


async def emit_step(
    db: AsyncSession,
    ticket_id: str,
    thread_id: str,
    step_number: int,
    node_name: str,
    input_state: dict[str, Any],
    output_state: dict[str, Any],
    tool_calls: list[dict] | None,
    llm_prompt: str | None,
    llm_response: str | None,
    confidence_score: float | None,
    latency_ms: int,
) -> None:
    """Emit one agent execution step. Called from each graph node."""
    now = datetime.now(UTC)
    step = AgentStep(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(ticket_id),
        thread_id=thread_id,
        step_number=step_number,
        node_name=node_name,
        input_state=_sanitize_state(input_state),
        output_state=_sanitize_state(output_state),
        tool_calls=tool_calls,
        llm_prompt=llm_prompt,
        llm_response=llm_response,
        confidence_score=confidence_score,
        latency_ms=latency_ms,
        is_compressed=False,
        raw_expires_at=now + timedelta(days=settings.replay_full_retention_days),
        created_at=now,
        updated_at=now,
    )
    db.add(step)
    try:
        await db.flush()
    except Exception as e:
        logger.warning(f"emit_step_flush_failed: {e}")


def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Remove non-serializable objects and truncate large fields."""
    safe = {}
    for k, v in state.items():
        try:
            if k == "messages":
                safe[k] = [{"type": type(m).__name__, "content": getattr(m, "content", "")[:200]}
                            for m in (v or [])]
            elif isinstance(v, (str, int, float, bool)) or v is None:
                safe[k] = v
            elif isinstance(v, dict):
                safe[k] = {kk: str(vv)[:200] for kk, vv in v.items()}
            elif isinstance(v, list):
                safe[k] = [str(item)[:100] for item in v[:5]]
            else:
                safe[k] = str(v)[:200]
        except Exception:
            safe[k] = "[unserializable]"
    return safe


async def compress_old_steps(db: AsyncSession) -> int:
    """
    Invariant 8: Compress steps older than REPLAY_FULL_RETENTION_DAYS.
    Nullifies: input_state, output_state, llm_prompt, llm_response.
    Writes: compressed_summary.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.replay_full_retention_days)
    result = await db.execute(
        select(AgentStep).where(
            AgentStep.raw_expires_at < cutoff,
            AgentStep.is_compressed == False,  # noqa: E712
        )
    )
    steps = result.scalars().all()

    compressed_count = 0
    for step in steps:
        step.compressed_summary = _make_summary(step)
        step.input_state = None
        step.output_state = None
        step.llm_prompt = None
        step.llm_response = None
        step.is_compressed = True
        compressed_count += 1

    if compressed_count:
        await db.commit()
        logger.info(f"replay_compressed: {compressed_count} steps")

    return compressed_count


async def purge_expired_steps(db: AsyncSession) -> int:
    """Invariant 9: Delete compressed steps older than REPLAY_SUMMARY_RETENTION_DAYS."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.replay_summary_retention_days)
    result = await db.execute(
        delete(AgentStep).where(
            AgentStep.is_compressed == True,  # noqa: E712
            AgentStep.created_at < cutoff,
        ).returning(AgentStep.id)
    )
    deleted_count = len(result.fetchall())
    if deleted_count:
        await db.commit()
        logger.info(f"replay_purged: {deleted_count} steps")
    return deleted_count


def _make_summary(step: AgentStep) -> str:
    parts = [f"node={step.node_name}"]
    if step.confidence_score is not None:
        parts.append(f"confidence={step.confidence_score:.2f}")
    parts.append(f"latency={step.latency_ms}ms")
    if step.tool_calls:
        tool_names = [t.get("name", "") for t in (step.tool_calls or [])]
        parts.append(f"tools={','.join(tool_names)}")
    return " | ".join(parts)
