"""
Structured audit log writer.
Execution Rule 2: every fallback, breach, and escalation writes here.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)
_fallback_logger = logging.getLogger("audit.fallback")


async def write_audit(
    action: str,
    actor: str,
    ticket_id: str | None = None,
    user_id: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
    db: Any = None,
) -> None:
    """Async audit log write — preferred path."""
    try:
        if db is not None:
            from app.models.audit_log import AuditLog
            log = AuditLog(
                id=uuid.uuid4(),
                ticket_id=uuid.UUID(ticket_id) if ticket_id else None,
                user_id=uuid.UUID(user_id) if user_id else None,
                action=action,
                actor=actor,
                detail=detail,
                metadata_=metadata,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(log)
            await db.flush()

        # Always log to structured logger regardless of DB availability
        logger.info(
            action,
            actor=actor,
            ticket_id=ticket_id,
            detail=detail,
            **(metadata or {}),
        )
    except Exception as e:
        _fallback_logger.error(f"audit_write_failed action={action} error={e}")


def write_audit_sync(
    action: str,
    actor: str,
    ticket_id: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Synchronous fallback for budget_guard node (which runs in sync context).
    Writes to structured logger only — DB write skipped.
    """
    try:
        logger.info(
            action,
            actor=actor,
            ticket_id=ticket_id,
            detail=detail,
            **(metadata or {}),
        )
    except Exception as e:
        _fallback_logger.error(f"audit_sync_write_failed: {e}")
