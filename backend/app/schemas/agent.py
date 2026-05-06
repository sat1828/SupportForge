"""
Pydantic v2 schemas for Agent API.
response_meta is MANDATORY on every AgentResponse (Execution Rule 3).
Missing response_meta = system broken.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ResponseMeta(BaseModel):
    """
    Mandatory metadata attached to every agent response.
    Execution Rule 3: No endpoint returns response without this.
    """
    confidence: float = Field(ge=0.0, le=1.0)
    action: Literal["resolve", "clarify", "escalate", "fast_path", "pending_approval"]
    reason: str = Field(min_length=1)
    step_count: int = Field(ge=0)
    fast_path_used: bool
    tool_calls_summary: list[str] = Field(default_factory=list)
    escalation_reason: str | None = None
    confidence_breakdown: dict[str, float] | None = None

    @field_validator("reason")
    @classmethod
    def reason_must_be_human_readable(cls, v: str) -> str:
        """Ensure reason is human-readable, not a raw code."""
        if v.startswith("_") or v == "":
            raise ValueError("reason must be a human-readable string")
        return v


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class ChatResponse(BaseModel):
    """Returned immediately from POST /chat — job enqueued."""
    job_id: str
    status: Literal["queued", "fast_path_resolved"]
    ticket_id: uuid.UUID
    response_meta: ResponseMeta | None = None   # populated for fast-path
    message: str | None = None                  # populated for fast-path


class SSEChunk(BaseModel):
    """Individual SSE event chunk during streaming."""
    event: Literal["meta", "chunk", "tool_call", "done", "error"]
    data: dict[str, Any]


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "in_progress", "complete", "failed"]
    result: dict[str, Any] | None = None


class ToolApprovalRequest(BaseModel):
    job_id: str
    ticket_id: uuid.UUID
    approved: bool
    modified_response: str | None = None  # admin can modify before approving


class AgentMetrics(BaseModel):
    total_tickets: int
    resolved_today: int
    avg_resolution_rate: float
    avg_confidence: float
    avg_latency_ms: float
    fast_path_rate: float
    escalation_rate: float
    cost_exceeded_count: int
