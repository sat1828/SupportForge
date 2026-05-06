"""
Unit tests for execution budget / resilience.
Invariants 1 (steps), 2 (latency), 3 (KB retries), 19 (LLM calls), 20 (tokens).
"""
import time
import pytest
from unittest.mock import patch

from app.agents.state import fresh_budget, AgentState, initial_state
from app.agents.budget_guard import budget_guard, route_after_guard, _force_escalate
from app.core.resilience import CostLimitExceededError, CostAwareLLM
from app.config import settings


def make_state(**overrides) -> AgentState:
    state = initial_state("test-ticket-123", "test message")
    state["budget"].update(overrides)
    return state


class TestBudgetGuard:
    def test_clean_state_passes(self):
        """No breach → state unchanged, force_escalated=False."""
        state = make_state()
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is False

    def test_max_steps_exceeded(self):
        """Invariant 1: steps > 10 → force_escalated=True."""
        state = make_state(steps_taken=settings.max_steps_per_ticket + 1)
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "max_steps_exceeded" in result["budget"]["escalation_trigger"]

    def test_max_latency_exceeded(self):
        """Invariant 2: elapsed > 10s → force_escalated=True."""
        state = make_state(start_time_utc=time.monotonic() - 15.0)  # 15s ago
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "max_latency_exceeded" in result["budget"]["escalation_trigger"]

    def test_max_kb_retries_exceeded(self):
        """Invariant 3: kb_search_count > 3 → force_escalated=True."""
        state = make_state(kb_search_count=settings.max_kb_retries + 1)
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "max_kb_retries_exceeded" in result["budget"]["escalation_trigger"]

    def test_max_llm_calls_exceeded(self):
        """Invariant 19: llm_calls_made >= 5 → force_escalated=True."""
        state = make_state(llm_calls_made=settings.max_llm_calls_per_ticket)
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "max_llm_calls_exceeded" in result["budget"]["escalation_trigger"]

    def test_max_tokens_exceeded(self):
        """Invariant 20: tokens_consumed >= 5000 → force_escalated=True."""
        state = make_state(tokens_consumed=settings.max_tokens_per_ticket)
        result = budget_guard(state)
        assert result["budget"]["force_escalated"] is True
        assert "max_tokens_exceeded" in result["budget"]["escalation_trigger"]

    def test_force_escalated_routes_to_escalation(self):
        """Already force_escalated → route_after_guard returns 'escalation'."""
        state = make_state(force_escalated=True)
        result = route_after_guard(state)
        assert result == "escalation"

    def test_response_meta_set_on_breach(self):
        """Execution Rule 2: response_meta populated on budget breach."""
        state = make_state(steps_taken=999)
        result = budget_guard(state)
        assert result["response_meta"] is not None
        assert result["response_meta"]["action"] == "escalate"
        assert result["response_meta"]["escalation_reason"] is not None

    def test_steps_incremented(self):
        """budget_guard increments steps_taken on every call."""
        state = make_state(steps_taken=0)
        result = budget_guard(state)
        assert result["budget"]["steps_taken"] == 1


class TestCostAwareLLM:
    @pytest.mark.asyncio
    async def test_raises_on_llm_call_limit(self):
        """Invariant 19: 6th LLM call raises CostLimitExceededError."""
        llm = CostAwareLLM()
        budget = {
            "llm_calls_made": settings.max_llm_calls_per_ticket,  # already at limit
            "tokens_consumed": 0,
            "cost_exceeded": False,
        }
        with pytest.raises(CostLimitExceededError) as exc_info:
            await llm.ainvoke([], budget=budget)
        assert exc_info.value.limit_type == "llm_calls"

    @pytest.mark.asyncio
    async def test_raises_on_token_limit(self):
        """Invariant 20: tokens exceeded raises CostLimitExceededError."""
        llm = CostAwareLLM()
        budget = {
            "llm_calls_made": 0,
            "tokens_consumed": settings.max_tokens_per_ticket,  # already at limit
            "cost_exceeded": False,
        }
        with pytest.raises(CostLimitExceededError) as exc_info:
            await llm.ainvoke([], budget=budget)
        assert exc_info.value.limit_type == "tokens"
