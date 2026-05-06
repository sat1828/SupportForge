"""Tickets CRUD router."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database import get_db
from app.models.ticket import SLA_HOURS, Ticket, TicketPriority, TicketStatus

router = APIRouter(prefix="/tickets", tags=["tickets"])


class CreateTicketRequest(BaseModel):
    title: str = Field(min_length=5, max_length=500)
    description: str = Field(min_length=10, max_length=5000)
    priority: str = TicketPriority.P3


class TicketResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    intent: str | None
    confidence_score: float | None
    sla_deadline: datetime | None
    created_at: datetime
    llm_calls_made: int
    tokens_consumed: int


@router.post("/", response_model=TicketResponse, status_code=201)
async def create_ticket(
    body: CreateTicketRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> TicketResponse:
    priority = body.priority if body.priority in TicketPriority.__members__.values() else TicketPriority.P3
    sla_hours = SLA_HOURS.get(TicketPriority(priority), 24)
    now = datetime.now(UTC)

    ticket = Ticket(
        id=uuid.uuid4(),
        customer_id=uuid.UUID(user_id),
        title=body.title,
        description=body.description,
        status=TicketStatus.OPEN,
        priority=priority,
        sla_deadline=now + timedelta(hours=sla_hours),
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    await db.flush()
    return _to_response(ticket)


@router.get("/", response_model=list[TicketResponse])
async def list_tickets(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> list[TicketResponse]:
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    result = await db.execute(stmt)
    return [_to_response(t) for t in result.scalars().all()]


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> TicketResponse:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _to_response(ticket)


def _to_response(ticket: Ticket) -> TicketResponse:
    return TicketResponse(
        id=str(ticket.id),
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        intent=ticket.intent,
        confidence_score=ticket.confidence_score,
        sla_deadline=ticket.sla_deadline,
        created_at=ticket.created_at,
        llm_calls_made=ticket.llm_calls_made,
        tokens_consumed=ticket.tokens_consumed,
    )
