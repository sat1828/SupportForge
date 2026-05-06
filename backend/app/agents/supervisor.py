"""
Supervisor Router — conditional edge function.
Routes to: kb_search | resolver | fraud_check | escalation | clarify.
Reads calibrated_confidence.routing_decision for routing, not raw LLM output.
"""
from __future__ import annotations

import logging

from app.agents.state import AgentState

logger = logging.getLogger(__name__)

# Intents that always need KB lookup
KB_REQUIRED_INTENTS = {
    "return_request", "payment_issue", "warranty_claim",
    "account_issue", "shipping_delay", "general_query",
}

# Intents that can be resolved directly with tools
DIRECT_RESOLVE_INTENTS = {
    "order_status", "refund_status", "invoice_download", "cod_query",
}


def supervisor_router(state: AgentState) -> str:
    """
    Conditional edge function — returns next node name.
    Called after budget_guard to determine routing.
    """
    if state["budget"]["force_escalated"]:
        return "escalation"

    # Fraud signals always route to fraud check first
    if state.get("fraud_signals"):
        return "fraud_check"

    intent = state.get("intent", "general_query")
    conf = state.get("calibrated_confidence") or {}
    routing = conf.get("routing_decision", "kb_retry")

    if routing == "escalate":
        state["escalation_reason"] = f"Low confidence routing for intent: {intent}"
        return "escalation"

    if intent in DIRECT_RESOLVE_INTENTS and routing == "resolve":
        return "resolver"

    if intent in KB_REQUIRED_INTENTS or routing == "kb_retry":
        kb_count = state["budget"]["kb_search_count"]
        if kb_count >= 3:  # Invariant 3
            logger.warning(f"supervisor_max_kb_retries_reached: {kb_count}")
            return "resolver"  # Proceed without more KB calls
        return "kb_search"

    return "resolver"
