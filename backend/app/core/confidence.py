"""
Multi-factor confidence scorer — Defect 2 fix.
Formula: 0.4×llm + 0.3×rag + 0.2×tool_success + 0.1×historical_accuracy
Invariant 12: deterministic given same inputs.
Invariant 13: tool_failed → final_score <= 0.60
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

WEIGHTS = {"llm": 0.4, "rag": 0.3, "tool": 0.2, "historical": 0.1}

# Hard floors (Invariant 13)
TOOL_FAIL_SCORE_CAP = 0.60
LOW_RAG_SCORE_CAP = 0.65
RAG_LOW_THRESHOLD = 0.40

# Routing thresholds
RESOLVE_THRESHOLD = 0.80
KB_RETRY_THRESHOLD = 0.65


@dataclass(frozen=True)
class ConfidenceInputs:
    llm_confidence: float           # [0,1] from LLM structured output
    rag_relevance_score: float      # [0,1] top chunk cosine similarity
    tool_execution_success: float   # 1.0 = all tools succeeded, 0.0 = any failed
    historical_accuracy: float      # [0,1] from AgentPerformanceCache


@dataclass(frozen=True)
class CalibratedConfidence:
    score: float
    routing_decision: str           # "resolve" | "kb_retry" | "escalate"
    breakdown: dict[str, float]
    hard_floor_applied: str | None  # which floor was applied, if any


class ConfidenceScorer:
    """
    Invariant 12: given identical inputs, always returns identical output.
    All operations are deterministic (no randomness, no time dependency).
    """

    def compute(self, inputs: ConfidenceInputs) -> CalibratedConfidence:
        """Compute calibrated confidence from multi-factor inputs."""
        # Clamp all inputs to [0, 1]
        llm = max(0.0, min(1.0, inputs.llm_confidence))
        rag = max(0.0, min(1.0, inputs.rag_relevance_score))
        tool = max(0.0, min(1.0, inputs.tool_execution_success))
        hist = max(0.0, min(1.0, inputs.historical_accuracy))

        raw = (
            WEIGHTS["llm"] * llm
            + WEIGHTS["rag"] * rag
            + WEIGHTS["tool"] * tool
            + WEIGHTS["historical"] * hist
        )

        hard_floor_applied: str | None = None

        # Invariant 13: tool failure hard cap
        if inputs.tool_execution_success == 0.0 and raw > TOOL_FAIL_SCORE_CAP:
            raw = TOOL_FAIL_SCORE_CAP
            hard_floor_applied = "tool_fail_cap"

        # RAG relevance hard cap
        if inputs.rag_relevance_score < RAG_LOW_THRESHOLD and raw > LOW_RAG_SCORE_CAP:
            raw = LOW_RAG_SCORE_CAP
            hard_floor_applied = hard_floor_applied or "low_rag_cap"

        score = round(raw, 4)
        routing = self._route(score)

        logger.debug(
            "confidence_computed",
            extra={
                "score": score,
                "routing": routing,
                "llm": llm,
                "rag": rag,
                "tool": tool,
                "hist": hist,
                "floor": hard_floor_applied,
            },
        )

        return CalibratedConfidence(
            score=score,
            routing_decision=routing,
            breakdown={"llm": llm, "rag": rag, "tool": tool, "historical": hist, "raw": raw},
            hard_floor_applied=hard_floor_applied,
        )

    @staticmethod
    def _route(score: float) -> str:
        if score >= RESOLVE_THRESHOLD:
            return "resolve"
        if score >= KB_RETRY_THRESHOLD:
            return "kb_retry"
        return "escalate"


class AgentPerformanceCache:
    """
    Reads historical success rate for (intent, tool_used) pairs.
    Cached in Redis, refreshed every 10 minutes.
    Falls back to 0.5 (neutral) if no history available.
    """

    CACHE_TTL = 600  # 10 minutes
    DEFAULT_ACCURACY = 0.5

    async def get(self, intent: str, tool_used: str | None) -> float:
        try:
            from app.core.cache import cache_manager
            cache_key = f"perf:{intent}:{tool_used or 'none'}"
            cached = await cache_manager.get(cache_key)
            if cached is not None:
                return float(cached)

            rate = await self._query_db(intent, tool_used)
            await cache_manager.set(cache_key, str(rate), ttl=self.CACHE_TTL)
            return rate
        except Exception as e:
            logger.warning(f"performance_cache_get_failed: {e}")
            return self.DEFAULT_ACCURACY

    async def _query_db(self, intent: str, tool_used: str | None) -> float:
        try:
            from sqlalchemy import select, func
            from sqlalchemy.types import Float as SAFloat
            from app.database import AsyncSessionLocal
            from app.models.human_correction import AgentPerformanceLog

            async with AsyncSessionLocal() as db:
                stmt = (
                    select(func.avg(AgentPerformanceLog.success.cast(SAFloat)))
                    .where(AgentPerformanceLog.intent == intent)
                    .order_by(AgentPerformanceLog.created_at.desc())
                    .limit(500)
                )
                if tool_used:
                    stmt = stmt.where(AgentPerformanceLog.tool_used == tool_used)
                result = await db.scalar(stmt)
                return float(result) if result is not None else self.DEFAULT_ACCURACY
        except Exception as e:
            logger.warning(f"performance_db_query_failed: {e}")
            return self.DEFAULT_ACCURACY


# ── Global singletons ─────────────────────────────────────────
confidence_scorer = ConfidenceScorer()
performance_cache = AgentPerformanceCache()
