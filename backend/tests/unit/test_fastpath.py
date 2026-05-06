"""
Unit tests for FastPathExecutor.
Invariant 10: fast-path latency <= 200ms.
Invariant 11: fast_path_used=True always logged.
Execution Rule 6: NEVER calls LLM.
"""
import pytest
import time
from unittest.mock import patch, AsyncMock

from app.core.fastpath import (
    FastPathExecutor, InputNormalizer, FAST_PATH_RULES,
    fast_path_executor, input_normalizer,
)


# ── InputNormalizer tests (Invariant 21 / Execution Rule 7) ──
class TestInputNormalizer:
    def test_empty_input_requires_clarification(self):
        result = input_normalizer.normalize("")
        assert result.requires_clarification is True
        assert result.clarification_reason == "empty_input"

    def test_whitespace_only(self):
        result = input_normalizer.normalize("   ")
        assert result.requires_clarification is True

    def test_too_short_requires_clarification(self):
        result = input_normalizer.normalize("hi")
        assert result.requires_clarification is True
        assert result.clarification_reason == "too_short"

    def test_injection_detected(self):
        result = input_normalizer.normalize("SELECT * FROM users WHERE 1=1")
        assert result.requires_clarification is True
        assert result.was_sanitized is True

    def test_script_injection_detected(self):
        result = input_normalizer.normalize("<script>alert('xss')</script>")
        assert result.requires_clarification is True

    def test_truncation_over_1000_chars(self):
        long_input = "a" * 1500
        result = input_normalizer.normalize(long_input)
        assert len(result.text) == 1000
        assert result.was_truncated is True
        assert result.requires_clarification is False  # truncated but valid

    def test_hinglish_detected(self):
        result = input_normalizer.normalize("Mera order kahan hai bhai?")
        assert result.hinglish_detected is True

    def test_aggressive_tone_detected(self):
        result = input_normalizer.normalize("This is a scam, I will take legal action NOW")
        assert result.aggressive_tone is True

    def test_normal_english_passes(self):
        result = input_normalizer.normalize("Where is my order #12345?")
        assert result.requires_clarification is False
        assert result.hinglish_detected is False

    def test_no_crash_on_any_input(self):
        """Invariant 21: crash_rate = 0%."""
        test_inputs = [
            "", " ", "a", "a" * 5000, "SELECT DROP TABLE",
            "<script>", "{{config}}", "__import__('os')",
            "Mera order kahan hai?", "URGENT!!! FRAUD!!!",
            "normal support query",
        ]
        for inp in test_inputs:
            result = input_normalizer.normalize(inp)  # Must not raise
            assert result is not None


# ── FastPathExecutor tests (Invariants 10, 11, Rule 6) ────────
class TestFastPathExecutor:
    def test_order_tracking_rule_matches(self):
        rule = fast_path_executor.match_rule("where is my order?")
        assert rule is not None
        assert rule.name == "order_tracking"

    def test_hinglish_order_tracking_matches(self):
        rule = fast_path_executor.match_rule("mera order kahan hai")
        assert rule is not None
        assert rule.name == "order_tracking"

    def test_refund_status_matches(self):
        rule = fast_path_executor.match_rule("when will I get my refund?")
        assert rule is not None
        assert rule.name == "refund_status"

    def test_invoice_matches(self):
        rule = fast_path_executor.match_rule("I need GST invoice download")
        assert rule is not None
        assert rule.name == "invoice_download"

    def test_no_match_returns_none(self):
        rule = fast_path_executor.match_rule("my product has a defect and warranty issue")
        assert rule is None

    @pytest.mark.asyncio
    async def test_fast_path_latency_under_200ms(self):
        """Invariant 10: execution must complete in <= 200ms."""
        rule = fast_path_executor.match_rule("track my order")
        assert rule is not None

        t0 = time.monotonic()
        result = await fast_path_executor.execute(rule, {}, "Test User")
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert elapsed_ms <= 200, f"Fast-path took {elapsed_ms:.1f}ms > 200ms"

    @pytest.mark.asyncio
    async def test_fast_path_used_true(self):
        """Invariant 11: fast_path_used=True always."""
        rule = fast_path_executor.match_rule("where is my order?")
        result = await fast_path_executor.execute(rule, {}, "Customer")
        assert result.fast_path_used is True

    @pytest.mark.asyncio
    async def test_no_llm_call_during_fastpath(self):
        """Execution Rule 6: fast-path MUST NOT call LLM."""
        rule = fast_path_executor.match_rule("track my order")
        llm_called = False

        # Patch the cost_aware_llm to detect any invocation
        with patch("app.core.resilience.cost_aware_llm.ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = AssertionError("LLM called during fast-path! Rule 6 violated.")
            result = await fast_path_executor.execute(rule, {}, "Customer")
            # If we get here without exception, LLM was NOT called
            assert mock_llm.call_count == 0, "LLM was called during fast-path execution"

    @pytest.mark.asyncio
    async def test_template_error_returns_safe_fallback(self):
        """Template key missing → safe fallback without crashing or calling LLM."""
        from app.core.fastpath import FastPathRule
        rule = FastPathRule(
            name="test_rule",
            patterns=[r"\btest\b"],
            intent="test",
            template="{missing_key} something",
        )
        result = await fast_path_executor.execute(rule, {}, "Customer")
        assert result.fast_path_used is True
        assert len(result.message) > 0  # has fallback text
