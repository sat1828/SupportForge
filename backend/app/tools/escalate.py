"""Tool: escalate_to_human — HITL gate, always requires approval."""
from __future__ import annotations

from app.core.resilience import with_tool_retry


@with_tool_retry(max_attempts=2)
async def escalate_to_human(ticket_id: str, reason: str, priority: str = "P2", **kwargs) -> dict:
    import uuid

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.ticket import Ticket, TicketStatus
    from app.observability.audit import write_audit

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Ticket).where(Ticket.id == uuid.UUID(ticket_id)))
        ticket = result.scalar_one_or_none()
        if ticket:
            ticket.status = TicketStatus.ESCALATED
            ticket.escalation_reason = reason
        await write_audit(
            action="ticket_escalated", actor="agent", ticket_id=ticket_id,
            detail=reason, metadata={"priority": priority}, db=db,
        )
        await db.commit()
    return {"status": "escalated", "reason": reason, "requires_human": True}


@with_tool_retry(max_attempts=2)
async def translate_text(text: str, source_lang: str = "auto", target_lang: str = "en", **kwargs) -> dict:
    """Tool: translate Hindi <-> English via LibreTranslate."""
    import httpx

    from app.config import settings

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.libretranslate_url}/translate",
                json={"q": text, "source": source_lang, "target": target_lang},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"translated": data.get("translatedText", text), "source": source_lang, "target": target_lang}
    except Exception:
        pass
    return {"translated": text, "source": source_lang, "target": target_lang, "fallback": True}
