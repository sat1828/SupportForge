"""
AgentState TypedDict — the single source of truth flowing through LangGraph.
ExecutionBudget enforces all invariants 1–5, 19–20.
"""
from __future__ import annotations

import time
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage


class ExecutionBudget(TypedDict):
    """
    Tracks ALL execution limits. Every invariant is enforced here.
    Invariant 1: steps_taken <= MAX_STEPS_PER_TICKET (10)
    Invariant 2: (time.monotonic() - start_time_utc) <= MAX_LATENCY_SECONDS (10s)
    Invariant 3: kb_search_count <= MAX_KB_RETRIES (3)
    Invariant 19: llm_calls_made <= MAX_LLM_CALLS_PER_TICKET (5)
    Invariant 20: tokens_consumed <= MAX_TOKENS_PER_TICKET (5000)
    """
    steps_taken: int
    kb_search_count: int
    start_time_utc: float       # time.monotonic() — wall clock start
    force_escalated: bool
    escalation_trigger: str     # which limit was breached
    llm_calls_made: int
    tokens_consumed: int
    cost_exceeded: bool


class ConfidenceBreakdown(TypedDict):
    """Multi-factor confidence score — Defect 2 fix."""
    llm_confidence: float
    rag_relevance_score: float
    tool_execution_success: float
    historical_accuracy: float
    final_score: float
    routing_decision: str       # "resolve" | "clarify" | "escalate" | "kb_retry"


class AgentState(TypedDict):
    """
    Complete state flowing through every LangGraph node.
    ContextManager compresses this to stay within token budget (Invariant 4-5).
    """
    # Core
    messages: list[BaseMessage]
    ticket_id: str
    thread_id: str

    # Triage output
    intent: str | None
    priority: str | None
    language: str              # "en" | "hi" | "hinglish"
    hinglish_detected: bool
    aggressive_tone: bool

    # Routing
    next_node: str | None
    retry_count: int

    # Budget (all invariants enforced here)
    budget: ExecutionBudget

    # Confidence (multi-factor)
    calibrated_confidence: ConfidenceBreakdown | None

    # KB results (compressed to top-3 after each cycle)
    kb_results: list[dict[str, Any]]

    # Tool tracking
    tool_calls_log: list[dict[str, Any]]   # max 5 entries (rolling)

    # Domain intelligence
    fraud_signals: list[dict[str, Any]]
    domain_check_result: dict[str, Any] | None

    # Escalation
    escalation_reason: str | None
    requires_approval: bool
    approval_status: str | None     # "pending" | "approved" | "rejected"

    # Memory (rolling summary replaces old messages)
    conversation_summary: str | None

    # Response metadata (Execution Rule 3 — MANDATORY on every response)
    response_meta: dict[str, Any] | None

    # Fast path flag (Execution Rule 6 — logged explicitly)
    fast_path_used: bool


def fresh_budget() -> ExecutionBudget:
    """Create a new ExecutionBudget at graph entry point."""
    return ExecutionBudget(
        steps_taken=0,
        kb_search_count=0,
        start_time_utc=time.monotonic(),
        force_escalated=False,
        escalation_trigger="",
        llm_calls_made=0,
        tokens_consumed=0,
        cost_exceeded=False,
    )


def initial_state(ticket_id: str, message: str) -> AgentState:
    """Create a fresh AgentState for a new ticket invocation."""
    from langchain_core.messages import HumanMessage

    return AgentState(
        messages=[HumanMessage(content=message)],
        ticket_id=ticket_id,
        thread_id=ticket_id,
        intent=None,
        priority=None,
        language="en",
        hinglish_detected=False,
        aggressive_tone=False,
        next_node=None,
        retry_count=0,
        budget=fresh_budget(),
        calibrated_confidence=None,
        kb_results=[],
        tool_calls_log=[],
        fraud_signals=[],
        domain_check_result=None,
        escalation_reason=None,
        requires_approval=False,
        approval_status=None,
        conversation_summary=None,
        response_meta=None,
        fast_path_used=False,
    )
