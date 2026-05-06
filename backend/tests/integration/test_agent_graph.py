"""
Integration tests for the LangGraph agent graph.
Tests: budget invariants, context compression, fraud detection, confidence routing.
All LLM calls mocked — pure graph logic tested.
"""
from __future__ import annotations

import time
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.state import initial_state, fresh_budget, AgentState
from app.agents.budget_guard import budget_guard, route_after_guard
from app.agents.context_manager import context_manager
from app.agents.fraud_check import domain_rules
from app.config import settings


# ── Budget Guard Integration ──────────────────────────────────
class TestBudgetGuardIntegration:
    def test_budget_stops_at_step_limit(self):
        """No execution path can exceed 10 steps — Invariant 1."""
        state = initial_state(str(uuid.uuid4()), "test")

        # Simulate 11 steps through budget_guard
        breach_detected = False
        for _ in range(12):
            state = budget_guard(state)
            if state["budget"]["force_escalated"]:
                breach_detected = True
                break

        assert breach_detected, "Budget guard must breach before step 12"
        assert state["budget"]["steps_taken"] <= settings.max_steps_per_ticket + 1

    def test_budget_stops_on_latency(self):
        """Elapsed > 10s → force escalation — Invariant 2."""
        state = initial_state(str(uuid.uuid4()), "test")
        # Backdate start time by 15 seconds
        state["budget"]["start_time_utc"] = time.monotonic() - 15.0
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "latency" in result["budget"]["escalation_trigger"]

    def test_force_escalated_sets_response_meta(self):
        """Execution Rule 2: response_meta must always be populated on breach."""
        state = initial_state(str(uuid.uuid4()), "test")
        state["budget"]["steps_taken"] = 999  # force breach
        result = budget_guard(state)
        assert result["response_meta"] is not None
        assert result["response_meta"]["action"] == "escalate"
        assert result["response_meta"]["reason"] != ""

    def test_route_after_guard_escalation(self):
        """force_escalated → route always returns 'escalation'."""
        state = initial_state(str(uuid.uuid4()), "test")
        state["budget"]["force_escalated"] = True
        state["budget"]["escalation_trigger"] = "test_trigger"
        route = route_after_guard(state)
        assert route == "escalation"

    def test_route_after_guard_normal(self):
        """Normal state → routes to next_node."""
        state = initial_state(str(uuid.uuid4()), "test")
        state["next_node"] = "triage"
        route = route_after_guard(state)
        assert route == "triage"


# ── Context Manager Integration ───────────────────────────────
class TestContextManagerIntegration:
    def test_trims_messages_over_limit(self):
        """Invariant 4: messages capped at MAX_CONTEXT_MESSAGES (6)."""
        from langchain_core.messages import HumanMessage, AIMessage
        state = initial_state(str(uuid.uuid4()), "start")

        # Add 12 messages
        for i in range(12):
            msg = HumanMessage(content=f"msg {i}") if i % 2 == 0 else AIMessage(content=f"reply {i}")
            state["messages"].append(msg)

        result = context_manager.compress(state)
        assert len(result["messages"]) <= settings.max_context_messages + 1  # +1 for summary SystemMessage

    def test_kb_results_compressed_to_3(self):
        """Invariant 5: kb_results limited to 3 top results."""
        state = initial_state(str(uuid.uuid4()), "test")
        state["kb_results"] = [
            {"source": f"doc_{i}", "text": "x" * 500, "score": float(i) / 10}
            for i in range(10)
        ]
        result = context_manager.compress(state)
        assert len(result["kb_results"]) <= settings.max_kb_results_per_cycle

    def test_tool_log_capped_at_5(self):
        """Tool call log never exceeds 5 entries."""
        state = initial_state(str(uuid.uuid4()), "test")
        state["tool_calls_log"] = [{"name": f"tool_{i}"} for i in range(10)]
        result = context_manager.compress(state)
        assert len(result["tool_calls_log"]) <= 5


# ── Domain Rules Integration ──────────────────────────────────
class TestDomainRulesIntegration:
    def test_invalid_gstin_flagged(self):
        ticket_data = {"gstin": "INVALID_GSTIN"}
        result = domain_rules.apply_all_rules(ticket_data, {})
        rule_names = [s.rule_name for s in result.fraud_signals]
        assert "gst_invalid_gstin" in rule_names

    def test_refund_exceeds_invoice_blocked(self):
        ticket_data = {"refund_amount": 10000, "invoice_amount": 5000}
        result = domain_rules.apply_all_rules(ticket_data, {})
        blocking = [s for s in result.fraud_signals if s.severity == "block"]
        assert any(s.rule_name == "gst_refund_exceeds_invoice" for s in blocking)
        assert "deny_refund" in result.auto_actions

    def test_excessive_cod_failures_suspended(self):
        customer_history = {"cod_failures_30d": 5}
        result = domain_rules.apply_all_rules({}, customer_history)
        rule_names = [s.rule_name for s in result.fraud_signals]
        assert "cod_excessive_failures" in rule_names
        assert "suspend_cod" in result.auto_actions

    def test_excessive_refunds_flagged(self):
        customer_history = {"refunds_30d": 4}
        result = domain_rules.apply_all_rules({}, customer_history)
        rule_names = [s.rule_name for s in result.fraud_signals]
        assert "refund_excessive_requests" in rule_names

    def test_clean_data_passes(self):
        """No signals on clean, normal data."""
        ticket_data = {
            "gstin": "29ABCDE1234F1Z5",
            "refund_amount": 500,
            "invoice_amount": 1000,
        }
        result = domain_rules.apply_all_rules(ticket_data, {})
        assert result.clean is True
        assert len(result.fraud_signals) == 0

    def test_no_crash_on_empty_data(self):
        """Invariant 21: no crash on empty/None data."""
        result = domain_rules.apply_all_rules({}, {})
        assert result is not None  # must not raise


# ── Supervisor Routing Integration ────────────────────────────
class TestSupervisorRouting:
    def test_high_confidence_routes_to_resolver(self):
        from app.agents.supervisor import supervisor_router
        state = initial_state(str(uuid.uuid4()), "track my order")
        state["intent"] = "order_status"
        state["calibrated_confidence"] = {
            "final_score": 0.92, "routing_decision": "resolve",
            "llm_confidence": 0.92, "rag_relevance_score": 0.8,
            "tool_execution_success": 1.0, "historical_accuracy": 0.7,
        }
        result = supervisor_router(state)
        assert result == "resolver"

    def test_low_confidence_routes_to_kb_search(self):
        from app.agents.supervisor import supervisor_router
        state = initial_state(str(uuid.uuid4()), "complex warranty claim")
        state["intent"] = "warranty_claim"
        state["calibrated_confidence"] = {
            "final_score": 0.50, "routing_decision": "kb_retry",
            "llm_confidence": 0.50, "rag_relevance_score": 0.3,
            "tool_execution_success": 1.0, "historical_accuracy": 0.5,
        }
        result = supervisor_router(state)
        assert result == "kb_search"

    def test_very_low_confidence_escalates(self):
        from app.agents.supervisor import supervisor_router
        state = initial_state(str(uuid.uuid4()), "something unclear")
        state["intent"] = "general_query"
        state["calibrated_confidence"] = {
            "final_score": 0.30, "routing_decision": "escalate",
            "llm_confidence": 0.30, "rag_relevance_score": 0.1,
            "tool_execution_success": 0.0, "historical_accuracy": 0.3,
        }
        result = supervisor_router(state)
        assert result == "escalation"
