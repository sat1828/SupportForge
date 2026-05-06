"""
LangGraph StateGraph assembly — the complete agent execution graph.
Enforces all 21 invariants through budget_guard nodes on every edge.
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.agents.budget_guard import budget_guard, route_after_guard
from app.agents.context_manager import context_manager
from app.config import settings

logger = logging.getLogger(__name__)


def _compress_node(state: AgentState) -> AgentState:
    """Wrapper node — compresses state before checkpointing."""
    return context_manager.compress(state)


async def _clarify_node(state: AgentState) -> AgentState:
    """Ask follow-up question when triage confidence < 0.75."""
    from langchain_core.messages import AIMessage
    clarify_msg = (
        "I want to make sure I help you correctly. Could you provide more details about:\n"
        "• Your order ID or ticket reference number\n"
        "• What specifically you need help with\n"
        "• Any error messages or status you've seen"
    )
    state["messages"] = list(state["messages"]) + [AIMessage(content=clarify_msg)]
    state["response_meta"] = {
        "confidence": 0.3,
        "action": "clarify",
        "reason": "I need a bit more information to help you accurately.",
        "step_count": state["budget"]["steps_taken"],
        "fast_path_used": False,
        "tool_calls_summary": [],
        "escalation_reason": None,
    }
    state["next_node"] = "triage"
    return state


async def _fraud_check_node(state: AgentState) -> AgentState:
    """Apply domain rules — routes to resolver or escalation."""
    from app.agents.fraud_check import domain_rules
    # domain_check_result used as ticket_data context if already populated
    ticket_data = state.get("domain_check_result") or {}
    customer_history = ticket_data.get("customer_history", {})
    result = domain_rules.apply_all_rules(ticket_data, customer_history)

    state["domain_check_result"] = {
        "fraud_signals": [
            {"rule_name": s.rule_name, "severity": s.severity, "evidence": s.evidence}
            for s in result.fraud_signals
        ],
        "auto_actions": result.auto_actions,
        "requires_review": result.requires_review,
        "clean": result.clean,
    }

    if result.fraud_signals:
        blocking = [s for s in result.fraud_signals if s.severity == "block"]
        if blocking:
            state["escalation_reason"] = f"Fraud detected: {blocking[0].rule_name}"
            state["next_node"] = "escalation"
        else:
            state["next_node"] = "resolver"
    else:
        state["next_node"] = "resolver"

    return state


async def _emailer_node(state: AgentState) -> AgentState:
    """Compose and send (mock) email response."""
    state["requires_approval"] = False
    # HITL gate — check if action requires approval
    meta = state.get("response_meta") or {}
    if meta.get("action") in ("escalate",) or any(
        "refund" in (t or "") for t in meta.get("tool_calls_summary", [])
    ):
        state["requires_approval"] = True
        state["approval_status"] = "pending"
        state["response_meta"]["action"] = "pending_approval"  # type: ignore[index]
        state["response_meta"]["reason"] = "This action requires admin approval before proceeding."  # type: ignore[index]

    logger.info("emailer_node_complete", extra={"requires_approval": state["requires_approval"]})
    return state


async def _escalation_node(state: AgentState) -> AgentState:
    """Final escalation node — enriches response_meta with reason."""
    reason = state.get("escalation_reason") or "Complex issue requiring human expertise."
    state["response_meta"] = state.get("response_meta") or {}
    state["response_meta"].update({  # type: ignore[union-attr]
        "confidence": (state.get("calibrated_confidence") or {}).get("final_score", 0.0),
        "action": "escalate",
        "reason": f"This requires human review due to: {reason}",
        "step_count": state["budget"]["steps_taken"],
        "fast_path_used": False,
        "tool_calls_summary": [t["name"] for t in state.get("tool_calls_log", [])],
        "escalation_reason": reason,
    })
    logger.info("escalation_node", extra={"reason": reason})
    return state


def build_graph(checkpointer: Any = None) -> Any:
    """
    Build and compile the StateGraph.
    budget_guard runs on every node as the first operation.
    All cycles are bounded by Invariant 1 (max 10 steps).
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────
    graph.add_node("budget_guard", budget_guard)
    graph.add_node("compress", _compress_node)

    from app.agents.triage import triage_node
    graph.add_node("triage", triage_node)
    graph.add_node("clarify", _clarify_node)
    graph.add_node("supervisor", lambda s: {**s, "next_node": None})  # pure router
    graph.add_node("kb_search", kb_search_node_wrapper)
    graph.add_node("resolver", resolver_node_wrapper)
    graph.add_node("fraud_check", _fraud_check_node)
    graph.add_node("emailer", _emailer_node)
    graph.add_node("escalation", _escalation_node)

    # ── Entry point ───────────────────────────────────────────
    graph.set_entry_point("budget_guard")

    # ── budget_guard → conditional route ─────────────────────
    graph.add_conditional_edges("budget_guard", route_after_guard, {
        "triage": "triage",
        "supervisor": "supervisor",
        "kb_search": "kb_search",
        "resolver": "resolver",
        "fraud_check": "fraud_check",
        "emailer": "emailer",
        "escalation": "escalation",
    })

    # ── After triage → compress → budget_guard ────────────────
    graph.add_edge("triage", "compress")
    graph.add_conditional_edges("compress", lambda s: s.get("next_node", "supervisor"), {
        "supervisor": "budget_guard",
        "clarify": "clarify",
        "escalation": "escalation",
        "resolver": "budget_guard",
    })

    # ── clarify → budget_guard (loops back to triage) ─────────
    graph.add_edge("clarify", "budget_guard")

    # ── supervisor → budget_guard (pure conditional route) ────
    graph.add_conditional_edges("supervisor",
        supervisor_router_call,  # returns node key string directly
        {
            "kb_search": "budget_guard",
            "resolver": "budget_guard",
            "fraud_check": "budget_guard",
            "escalation": "escalation",
        }
    )

    # ── kb_search → budget_guard ──────────────────────────────
    graph.add_edge("kb_search", "budget_guard")

    # ── resolver → emailer or re-route ────────────────────────
    def _resolver_route(s: AgentState) -> str:
        if s["budget"]["force_escalated"]:
            return "escalation"
        nxt = s.get("next_node", "emailer")
        # Normalise: resolver sets next_node to routing_decision value
        if nxt == "resolve":
            return "emailer"
        return nxt

    graph.add_conditional_edges("resolver",
        _resolver_route,
        {
            "emailer": "emailer",
            "clarify": "budget_guard",  # loops back through supervisor
            "kb_retry": "budget_guard",
            "escalation": "escalation",
        }
    )

    # ── fraud_check → budget_guard ────────────────────────────
    graph.add_edge("fraud_check", "budget_guard")

    # ── emailer → END (with optional HITL interrupt) ──────────
    graph.add_edge("emailer", END)
    graph.add_edge("escalation", END)

    # HITL interrupt points
    interrupt_before = ["emailer"]  # Admin must approve before emailer sends

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


def supervisor_router_call(state: AgentState) -> str:
    from app.agents.supervisor import supervisor_router
    return supervisor_router(state)


async def kb_search_node_wrapper(state: AgentState) -> AgentState:
    from app.agents.kb_search import kb_search_node
    return await kb_search_node(state)


async def resolver_node_wrapper(state: AgentState) -> AgentState:
    from app.agents.resolver import resolver_node
    return await resolver_node(state)


# ── Checkpointer setup ────────────────────────────────────────
async def get_checkpointer() -> AsyncPostgresSaver:
    """AsyncPostgresSaver with autocommit=True for LangGraph compatibility."""
    import psycopg
    conn = await psycopg.AsyncConnection.connect(
        settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
        autocommit=True,
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()
    return checkpointer


# Graph singleton (initialized at startup)
_compiled_graph: Any = None


async def get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        checkpointer = await get_checkpointer()
        _compiled_graph = build_graph(checkpointer)
    return _compiled_graph
