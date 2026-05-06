"""
Budget guard node — inserted on every edge in the StateGraph.
Enforces all execution invariants: 1 (steps), 2 (latency), 3 (KB), 19 (LLM calls), 20 (tokens).
If any limit is breached, routes to FORCE_ESCALATE in one step.
Execution Rule 2: every fallback sets explicit state flags + audit log.
"""
from __future__ import annotations

import logging
import time

from app.agents.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)


def budget_guard(state: AgentState) -> AgentState:
    """
    Runs BEFORE every node transition.
    Checks all 5 execution invariants.
    Returns state unchanged if budget OK, or sets force_escalated=True if breached.
    """
    b = state["budget"]

    if b["force_escalated"]:
        # Already breached — pass through to escalation node immediately
        return state

    elapsed = time.monotonic() - b["start_time_utc"]
    b["steps_taken"] += 1

    breach_reason: str | None = None

    # Invariant 1: max steps
    if b["steps_taken"] > settings.max_steps_per_ticket:
        breach_reason = f"max_steps_exceeded:{b['steps_taken']}/{settings.max_steps_per_ticket}"

    # Invariant 2: max latency
    elif elapsed > settings.max_latency_seconds:
        breach_reason = f"max_latency_exceeded:{elapsed:.2f}s/{settings.max_latency_seconds}s"

    # Invariant 3: max KB retries
    elif b["kb_search_count"] > settings.max_kb_retries:
        breach_reason = f"max_kb_retries_exceeded:{b['kb_search_count']}/{settings.max_kb_retries}"

    # Invariant 19: max LLM calls
    elif b["llm_calls_made"] >= settings.max_llm_calls_per_ticket:
        breach_reason = f"max_llm_calls_exceeded:{b['llm_calls_made']}/{settings.max_llm_calls_per_ticket}"

    # Invariant 20: max tokens
    elif b["tokens_consumed"] >= settings.max_tokens_per_ticket:
        breach_reason = f"max_tokens_exceeded:{b['tokens_consumed']}/{settings.max_tokens_per_ticket}"

    if breach_reason:
        return _force_escalate(state, breach_reason)

    return state


def _force_escalate(state: AgentState, reason: str) -> AgentState:
    """
    Execution Rule 2: NEVER silent. Sets flags, logs audit event.
    Terminal — routes to escalation in next step.
    """
    state["budget"]["force_escalated"] = True
    state["budget"]["escalation_trigger"] = reason
    state["escalation_reason"] = f"[AUTO] Budget exceeded: {reason}"

    # Execution Rule 2: build response_meta so UX always knows why
    state["response_meta"] = {
        "confidence": 0.0,
        "action": "escalate",
        "reason": "Request complexity exceeded system limits. A human agent will assist you shortly.",
        "step_count": state["budget"]["steps_taken"],
        "fast_path_used": False,
        "tool_calls_summary": [t["name"] for t in state.get("tool_calls_log", [])],
        "escalation_reason": reason,
    }

    logger.warning(
        "budget_guard_forced_escalation",
        extra={
            "ticket_id": state.get("ticket_id"),
            "reason": reason,
            "steps": state["budget"]["steps_taken"],
            "llm_calls": state["budget"]["llm_calls_made"],
            "tokens": state["budget"]["tokens_consumed"],
        },
    )

    # Async audit log scheduled via background task (can't await in sync node)
    _schedule_audit(state["ticket_id"], reason, state["budget"])

    return state


def _schedule_audit(ticket_id: str, reason: str, budget: dict) -> None:
    """Non-blocking audit log write."""
    try:
        from app.observability.audit import write_audit_sync
        write_audit_sync(
            ticket_id=ticket_id,
            action="budget_exceeded",
            actor="system",
            detail=reason,
            metadata=dict(budget),
        )
    except Exception as e:
        logger.error(f"audit_write_failed: {e}")


def route_after_guard(state: AgentState) -> str:
    """
    Conditional edge function — called after budget_guard.
    If budget breached -> always route to 'escalation'.
    Otherwise -> route to state["next_node"].
    Invariant: force_escalated=True ALWAYS terminates at escalation within 1 step.
    """
    if state["budget"]["force_escalated"]:
        return "escalation"
    return state.get("next_node") or "supervisor"
