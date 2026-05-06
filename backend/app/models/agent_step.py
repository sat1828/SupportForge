"""
AgentStep ORM model — stores full execution trace for replay system.
Tiered retention: 7 days full → compressed summary → 90 days → purged.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentStep(Base):
    __tablename__ = "agent_steps"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Full detail — nullified after REPLAY_FULL_RETENTION_DAYS (Invariant 8)
    input_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    llm_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Always retained
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Retention flags (Defect 5 fix)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    compressed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="agent_steps", lazy="noload")  # type: ignore[name-defined]
