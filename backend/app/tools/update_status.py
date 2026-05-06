"""Tool: update_ticket_status — HITL-gated for sensitive transitions."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.resilience import with_tool_retry

HITL_REQUIRED_STATUSES = {"resolved", "closed"}


@with_tool_retry(max_attempts=3)
async def update_ticket_status(ticket_id: str, new_status: str, reason: str = "", **kwargs) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.ticket import Ticket, TicketStatus
    from app.observability.audit import write_audit

    if new_status in HITL_REQUIRED_STATUSES:
        # Return pending_approval — graph will interrupt before emailer
        return {
            "status": "pending_approval",
            "requires_hitl": True,
            "requested_status": new_status,
            "message": f"Status change to '{new_status}' requires admin approval.",
        }

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Ticket).where(Ticket.id == uuid.UUID(ticket_id)))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return {"error": "ticket_not_found"}

        old_status = ticket.status
        ticket.status = new_status
        ticket.updated_at = datetime.now(UTC)
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = datetime.now(UTC)

        await write_audit(
            action="ticket_status_updated",
            actor="agent",
            ticket_id=ticket_id,
            detail=f"{old_status} -> {new_status}: {reason}",
            db=db,
        )
        await db.commit()
        return {"status": "updated", "old_status": old_status, "new_status": new_status}
