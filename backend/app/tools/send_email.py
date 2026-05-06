"""Tool: send_email — mocked (logged to DB, no SMTP)."""
from __future__ import annotations

import uuid

from app.core.resilience import with_tool_retry


@with_tool_retry(max_attempts=2)
async def send_email(ticket_id: str, to_email: str, subject: str, body: str, **kwargs) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.conversation import Conversation
    from app.observability.audit import write_audit

    async with AsyncSessionLocal() as db:
        msg = Conversation(
            ticket_id=uuid.UUID(ticket_id),
            role="system",
            content=f"[EMAIL SENT] To: {to_email} | Subject: {subject} | Body: {body[:500]}",
        )
        db.add(msg)
        await write_audit(
            action="email_sent", actor="agent", ticket_id=ticket_id,
            detail=f"to={to_email} subject={subject[:50]}", db=db,
        )
        await db.commit()
    return {"status": "sent", "to": to_email, "subject": subject}
