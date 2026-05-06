"""
Unit tests for confidence scorer.
Invariant 12: deterministic given same inputs.
Invariant 13: tool_fail → score <= 0.60.
"""
import pytest
from app.core.confidence import ConfidenceInputs, ConfidenceScorer, TOOL_FAIL_SCORE_CAP, LOW_RAG_SCORE_CAP


@pytest.fixture
def scorer():
    return ConfidenceScorer()


def test_determinism(scorer):
    """Invariant 12: identical inputs → identical output."""
    inputs = ConfidenceInputs(
        llm_confidence=0.8,
        rag_relevance_score=0.7,
        tool_execution_success=1.0,
        historical_accuracy=0.6,
    )
    r1 = scorer.compute(inputs)
    r2 = scorer.compute(inputs)
    assert r1.score == r2.score
    assert r1.routing_decision == r2.routing_decision


def test_tool_fail_hard_floor(scorer):
    """Invariant 13: tool_execution_success=0.0 → score <= 0.60."""
    inputs = ConfidenceInputs(
        llm_confidence=0.95,
        rag_relevance_score=0.90,
        tool_execution_success=0.0,  # tool failed
        historical_accuracy=0.90,
    )
    result = scorer.compute(inputs)
    assert result.score <= TOOL_FAIL_SCORE_CAP, f"Expected <= {TOOL_FAIL_SCORE_CAP}, got {result.score}"
    assert result.hard_floor_applied == "tool_fail_cap"


def test_low_rag_cap(scorer):
    """RAG relevance < 0.40 → score <= 0.65."""
    inputs = ConfidenceInputs(
        llm_confidence=0.90,
        rag_relevance_score=0.30,  # low RAG
        tool_execution_success=1.0,
        historical_accuracy=0.80,
    )
    result = scorer.compute(inputs)
    assert result.score <= LOW_RAG_SCORE_CAP


def test_resolve_routing(scorer):
    """score >= 0.80 → routing_decision = 'resolve'."""
    inputs = ConfidenceInputs(0.9, 0.9, 1.0, 0.9)
    result = scorer.compute(inputs)
    assert result.routing_decision == "resolve"


def test_escalate_routing(scorer):
    """score < 0.65 → routing_decision = 'escalate'."""
    inputs = ConfidenceInputs(0.3, 0.2, 0.0, 0.3)
    result = scorer.compute(inputs)
    assert result.routing_decision == "escalate"


def test_kb_retry_routing(scorer):
    """0.65 <= score < 0.80 → routing_decision = 'kb_retry'."""
    inputs = ConfidenceInputs(0.7, 0.6, 1.0, 0.5)
    result = scorer.compute(inputs)
    assert result.routing_decision == "kb_retry"


def test_breakdown_returned(scorer):
    """Breakdown includes all 4 components."""
    inputs = ConfidenceInputs(0.7, 0.6, 1.0, 0.5)
    result = scorer.compute(inputs)
    assert "llm" in result.breakdown
    assert "rag" in result.breakdown
    assert "tool" in result.breakdown
    assert "historical" in result.breakdown


def test_clamps_inputs(scorer):
    """Values outside [0,1] are clamped."""
    inputs = ConfidenceInputs(
        llm_confidence=1.5,   # >1
        rag_relevance_score=-0.1,  # <0
        tool_execution_success=2.0,
        historical_accuracy=0.5,
    )
    result = scorer.compute(inputs)
    assert 0.0 <= result.score <= 1.0
