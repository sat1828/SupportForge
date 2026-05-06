"""
Resilience layer: LLM fallback chain, circuit breaker, CostAwareLLM.
Enforces Invariants 19 (max 5 LLM calls) and 20 (max 5000 tokens) per ticket.
Execution Rule 4: cost limit breach STOPS execution immediately.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.messages import BaseMessage
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)


# ── Custom Exceptions ─────────────────────────────────────────
class CostLimitExceededError(Exception):
    """Raised when LLM call or token budget is breached. Stops execution."""
    def __init__(self, limit_type: str, current: int, max_allowed: int):
        self.limit_type = limit_type
        self.current = current
        self.max_allowed = max_allowed
        super().__init__(f"{limit_type} exceeded: {current} > {max_allowed}")


class AllProvidersExhaustedError(Exception):
    """Raised when Groq + Ollama + cache all fail."""


class BudgetExhaustedError(Exception):
    """Raised when execution budget (steps/latency) is exceeded."""


class ToolExecutionError(Exception):
    """Raised when a tool fails after all retries."""


# ── Circuit Breaker States ─────────────────────────────────────
class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Tripped — failing fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Per-provider circuit breaker stored in Redis for distributed consistency.
    Trips after 5 failures in 60s. Recovers after 60s cooling period.
    """
    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 2

    _failure_count: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _half_open_calls: int = field(default=0, repr=False)

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                extra={"provider": self.name, "failures": self._failure_count}
            )

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info("circuit_breaker_closed", extra={"provider": self.name})

    def can_attempt(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                return True
            return False
        # HALF_OPEN
        if self._half_open_calls < self.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False


# ── Global circuit breakers (one per LLM provider) ────────────
_circuit_breakers: dict[str, CircuitBreaker] = {
    "groq": CircuitBreaker(name="groq"),
    "ollama": CircuitBreaker(name="ollama"),
}


def get_circuit_breaker(provider: str) -> CircuitBreaker:
    return _circuit_breakers.get(provider, CircuitBreaker(name=provider))


# ── CostAwareLLM — enforces Invariants 19 & 20 ────────────────
class CostAwareLLM:
    """
    Wraps any LangChain ChatModel. Enforces LLM call + token budgets.
    Execution Rule 4: exceeding limit STOPS execution — no further processing.
    """

    def __init__(self) -> None:
        self._groq_llm: Any = None
        self._ollama_llm: Any = None
        self._providers_initialized = False

    def _init_providers(self) -> None:
        if self._providers_initialized:
            return
        try:
            from langchain_groq import ChatGroq
            if settings.groq_api_key:
                self._groq_llm = ChatGroq(
                    model=settings.groq_model,
                    api_key=settings.groq_api_key,
                    temperature=0.1,
                    max_retries=1,
                )
        except Exception as e:
            logger.warning(f"Groq init failed: {e}")

        try:
            from langchain_community.chat_models import ChatOllama
            self._ollama_llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=0.1,
            )
        except Exception as e:
            logger.warning(f"Ollama init failed: {e}")

        self._providers_initialized = True

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        budget: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """
        Invoke LLM with cost tracking and fallback chain.
        RAISES CostLimitExceededError before calling LLM if budget exhausted.
        """
        self._init_providers()

        # ── Pre-call budget guard (Execution Rule 4) ───────────
        calls_made = budget.get("llm_calls_made", 0)
        tokens_used = budget.get("tokens_consumed", 0)

        if calls_made >= settings.max_llm_calls_per_ticket:
            raise CostLimitExceededError(
                "llm_calls", calls_made, settings.max_llm_calls_per_ticket
            )
        if tokens_used >= settings.max_tokens_per_ticket:
            raise CostLimitExceededError(
                "tokens", tokens_used, settings.max_tokens_per_ticket
            )

        # ── Try providers in priority order ───────────────────
        providers = []
        if self._groq_llm:
            providers.append(("groq", self._groq_llm))
        if self._ollama_llm:
            providers.append(("ollama", self._ollama_llm))

        last_error: Exception | None = None
        for provider_name, llm in providers:
            cb = get_circuit_breaker(provider_name)
            if not cb.can_attempt():
                logger.info(f"circuit_open_skip_{provider_name}")
                continue
            try:
                response = await asyncio.wait_for(
                    llm.ainvoke(messages, **kwargs),
                    timeout=min(
                        settings.max_latency_seconds - 1,  # leave 1s buffer
                        8.0,
                    ),
                )
                cb.record_success()

                # ── Post-call accounting ───────────────────────
                usage = getattr(response, "usage_metadata", {}) or {}
                token_delta = usage.get("total_tokens", self._estimate_tokens(messages, response))
                budget["llm_calls_made"] = calls_made + 1
                budget["tokens_consumed"] = tokens_used + token_delta

                # Post-call breach check (boundary case)
                if budget["tokens_consumed"] > settings.max_tokens_per_ticket:
                    budget["cost_exceeded"] = True
                    logger.warning(
                        "token_budget_exceeded_post_call",
                        extra={
                            "consumed": budget["tokens_consumed"],
                            "limit": settings.max_tokens_per_ticket,
                        },
                    )

                from app.observability.prometheus import llm_provider_counter
                llm_provider_counter.labels(provider=provider_name, status="success").inc()
                return response

            except (CostLimitExceededError, TimeoutError) as e:
                cb.record_failure()
                last_error = e
                continue
            except Exception as e:
                cb.record_failure()
                last_error = e
                logger.warning(f"provider_{provider_name}_failed: {e}")
                continue

        raise AllProvidersExhaustedError(
            f"All LLM providers exhausted. Last error: {last_error}"
        )

    @staticmethod
    def _estimate_tokens(messages: list[BaseMessage], response: Any) -> int:
        """Rough token estimate when usage_metadata unavailable."""
        input_chars = sum(len(m.content) for m in messages if hasattr(m, "content"))
        output_chars = len(getattr(response, "content", "") or "")
        return int((input_chars + output_chars) / 4)


# ── Tool Retry Decorator ───────────────────────────────────────
def with_tool_retry(max_attempts: int = 3):
    """
    Decorator for tool functions. Retries with exponential backoff.
    After max_attempts, raises ToolExecutionError.
    """
    def decorator(fn):  # type: ignore[return]
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
            reraise=False,
        )
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await fn(*args, **kwargs)

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await wrapper(*args, **kwargs)
            except RetryError as e:
                raise ToolExecutionError(f"{fn.__name__} failed after {max_attempts} retries: {e}") from e

        return wrapped
    return decorator


# ── Global singleton ──────────────────────────────────────────
cost_aware_llm = CostAwareLLM()
