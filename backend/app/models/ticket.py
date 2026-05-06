"""Ticket ORM model with SLA and priority tracking."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    P1 = "P1"   # Critical — breach in 1h
    P2 = "P2"   # High — breach in 4h
    P3 = "P3"   # Medium — breach in 24h
    P4 = "P4"   # Low — breach in 72h


SLA_HOURS = {
    TicketPriority.P1: 1,
    TicketPriority.P2: 4,
    TicketPriority.P3: 24,
    TicketPriority.P4: 72,
}


class Ticket(Base):
    __tablename__ = "tickets"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=TicketStatus.OPEN, nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(10), default=TicketPriority.P3, nullable=False, index=True
    )
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # SLA tracking
    sla_deadline: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # AI metadata
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Domain intelligence flags
    fraud_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    domain_signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Cost tracking (Invariant 19-20)
    llm_calls_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    customer: Mapped["User"] = relationship("User", back_populates="tickets", lazy="noload")  # type: ignore[name-defined]
    messages: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="ticket", lazy="noload")  # type: ignore[name-defined]
    agent_steps: Mapped[list["AgentStep"]] = relationship("AgentStep", back_populates="ticket", lazy="noload")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Ticket {self.id} status={self.status} priority={self.priority}>"
