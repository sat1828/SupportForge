"""Models package — export all ORM models for Alembic autogenerate."""
from app.models.agent_step import AgentStep
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation, MessageRole
from app.models.human_correction import AgentPerformanceLog, HumanCorrection
from app.models.knowledge_base import EMBEDDING_DIM, KnowledgeBaseChunk
from app.models.ticket import SLA_HOURS, Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole

__all__ = [
    "User", "UserRole",
    "Ticket", "TicketStatus", "TicketPriority", "SLA_HOURS",
    "Conversation", "MessageRole",
    "AuditLog",
    "KnowledgeBaseChunk", "EMBEDDING_DIM",
    "AgentStep",
    "HumanCorrection", "AgentPerformanceLog",
]
