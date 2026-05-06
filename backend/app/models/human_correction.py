"""Human correction and agent performance ORM models — power the learning loop."""
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HumanCorrection(Base):
    """
    Stored when admin overrides AI decision.
    Immediately indexed into KB with boost_score=1.5.
    """
    __tablename__ = "human_corrections"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_intent: Mapped[str] = mapped_column(String(100), nullable=False)
    original_response: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_response: Mapped[str] = mapped_column(Text, nullable=False)
    correction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "resolution" | "escalation" | "tool_choice"
    kb_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_base_chunks.id", ondelete="SET NULL"), nullable=True
    )
    correction_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class AgentPerformanceLog(Base):
    """
    Written after every ticket resolution.
    Powers historical_accuracy in ConfidenceScorer.
    """
    __tablename__ = "agent_performance_logs"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intent: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("human_corrections.id", ondelete="SET NULL"), nullable=True
    )
    final_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps_taken: Mapped[int] = mapped_column(nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)
