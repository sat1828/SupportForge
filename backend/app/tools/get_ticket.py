"""Tool: get_ticket_details — safe DB fetch, no raw SQL."""
from __future__ import annotations

import uuid

from app.core.resilience import with_tool_retry


@with_tool_retry(max_attempts=3)
async def get_ticket_details(ticket_id: str, **kwargs) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.ticket import Ticket
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Ticket, User)
            .join(User, Ticket.customer_id == User.id)
            .where(Ticket.id == uuid.UUID(ticket_id))
        )
        row = result.one_or_none()
        if not row:
            return {"error": "ticket_not_found", "ticket_id": ticket_id}
        ticket, user = row
        return {
            "ticket_id": str(ticket.id),
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "intent": ticket.intent,
            "customer_name": user.full_name,
            "customer_email": user.email,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
            "created_at": ticket.created_at.isoformat(),
            "fraud_flags": ticket.fraud_flags,
        }
