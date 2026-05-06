"""Admin API — metrics, audit logs, replay, corrections, eval results."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.database import get_db
from app.models.agent_step import AgentStep
from app.models.audit_log import AuditLog
from app.models.ticket import Ticket, TicketStatus

router = APIRouter(prefix="/admin", tags=["admin"])


class CorrectionRequest(BaseModel):
    original_intent: str
    original_response: str
    corrected_response: str
    correction_type: str
    category: str | None = None
    priority: str | None = None


class EvalResultsResponse(BaseModel):
    baseline_resolution_rate: float
    full_resolution_rate: float
    baseline_hallucination_rate: float
    full_hallucination_rate: float
    baseline_avg_latency_ms: float
    full_avg_latency_ms: float
    improvement_pct: float
    run_at: datetime | None


@router.get("/metrics")
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> dict:
    """System-wide metrics for admin dashboard."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total = await db.scalar(select(func.count(Ticket.id)))
    resolved_today = await db.scalar(
        select(func.count(Ticket.id))
        .where(Ticket.resolved_at >= today_start)
    )
    escalated = await db.scalar(
        select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.ESCALATED)
    )
    avg_confidence = await db.scalar(
        select(func.avg(Ticket.confidence_score))
        .where(Ticket.confidence_score.isnot(None))
    )
    avg_llm_calls = await db.scalar(
        select(func.avg(Ticket.llm_calls_made))
    )
    avg_tokens = await db.scalar(
        select(func.avg(Ticket.tokens_consumed))
    )

    total_safe = total or 0
    return {
        "total_tickets": total_safe,
        "resolved_today": resolved_today or 0,
        "escalated_count": escalated or 0,
        "resolution_rate": round((resolved_today or 0) / max(total_safe, 1), 3),
        "escalation_rate": round((escalated or 0) / max(total_safe, 1), 3),
        "avg_confidence": round(float(avg_confidence or 0), 3),
        "avg_llm_calls_per_ticket": round(float(avg_llm_calls or 0), 2),
        "avg_tokens_per_ticket": round(float(avg_tokens or 0), 0),
    }


@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> list[dict]:
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "action": log.action,
            "actor": log.actor,
            "ticket_id": str(log.ticket_id) if log.ticket_id else None,
            "detail": log.detail,
            "metadata": log.metadata_,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/tickets/{ticket_id}/replay")
async def get_replay(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> list[dict]:
    """Return agent execution steps for replay viewer."""
    result = await db.execute(
        select(AgentStep)
        .where(AgentStep.ticket_id == ticket_id)
        .order_by(AgentStep.step_number)
    )
    steps = result.scalars().all()
    return [
        {
            "step_number": s.step_number,
            "node_name": s.node_name,
            "confidence_score": s.confidence_score,
            "latency_ms": s.latency_ms,
            "is_compressed": s.is_compressed,
            "compressed_summary": s.compressed_summary,
            # Full data only available within retention window (Invariant 8)
            "input_state": s.input_state if not s.is_compressed else None,
            "output_state": s.output_state if not s.is_compressed else None,
            "tool_calls": s.tool_calls if not s.is_compressed else None,
            "llm_prompt": s.llm_prompt if not s.is_compressed else None,
        }
        for s in steps
    ]


@router.post("/tickets/{ticket_id}/correction")
async def submit_correction(
    ticket_id: uuid.UUID,
    body: CorrectionRequest,
    db: AsyncSession = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> dict:
    """
    Admin correction → immediately indexed into KB with boost_score=1.5.
    Invariants 16 + 17 + 18.
    """
    from app.rag.feedback_indexer import feedback_indexer
    from app.models.human_correction import HumanCorrection, AgentPerformanceLog
    from app.observability.audit import write_audit

    chunk_id = await feedback_indexer.index_correction(
        ticket_id=str(ticket_id),
        original_intent=body.original_intent,
        original_response=body.original_response,
        corrected_response=body.corrected_response,
        correction_type=body.correction_type,
        category=body.category,
        admin_id=admin_id,
        db=db,
    )

    # Record correction model (Invariant 18)
    correction = HumanCorrection(
        ticket_id=ticket_id,
        admin_id=uuid.UUID(admin_id),
        original_intent=body.original_intent,
        original_response=body.original_response,
        corrected_response=body.corrected_response,
        correction_type=body.correction_type,
        kb_chunk_id=uuid.UUID(chunk_id) if chunk_id else None,
        correction_metadata={"priority": body.priority, "category": body.category},
    )
    db.add(correction)

    # Mark performance log as failure (feeds historical_accuracy)
    perf = AgentPerformanceLog(
        ticket_id=ticket_id,
        intent=body.original_intent,
        tool_used=None,
        success=False,
        correction_id=correction.id,
    )
    db.add(perf)

    await write_audit(
        action="admin_correction_submitted",
        actor="admin",
        ticket_id=str(ticket_id),
        user_id=admin_id,
        detail=f"intent={body.original_intent} type={body.correction_type}",
        db=db,
    )

    return {
        "status": "correction_indexed",
        "chunk_id": chunk_id,
        "boost_score": 1.5,
    }


@router.get("/eval/results", response_model=EvalResultsResponse)
async def get_eval_results(
    admin_id: str = Depends(require_admin),
) -> EvalResultsResponse:
    """Return latest A/B evaluation results."""
    # Results stored in Redis after eval run
    try:
        import redis as sync_redis
        import json
        from app.config import settings
        r = sync_redis.from_url(settings.redis_url, decode_responses=True)
        raw = r.get("eval:latest_results")
        if raw:
            data = json.loads(raw)
            return EvalResultsResponse(**data)
    except Exception:
        pass
    return EvalResultsResponse(
        baseline_resolution_rate=0.0,
        full_resolution_rate=0.0,
        baseline_hallucination_rate=0.0,
        full_hallucination_rate=0.0,
        baseline_avg_latency_ms=0.0,
        full_avg_latency_ms=0.0,
        improvement_pct=0.0,
        run_at=None,
    )
