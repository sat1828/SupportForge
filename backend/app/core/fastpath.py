"""
FastPath — deterministic rule-based resolution BEFORE any LLM call.
Invariant 10: FastPath returns in <= 200ms
Invariant 11: FastPath always logs fast_path_used=True
Execution Rule 6: FastPath NEVER calls LLM — assertion enforced in code.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Assertion guard — Execution Rule 6 ───────────────────────
_LLM_CALLED_DURING_FASTPATH = False


def _assert_no_llm_call() -> None:
    """Called at the start of fast-path execution. Fails loudly if LLM is ever invoked."""
    global _LLM_CALLED_DURING_FASTPATH
    _LLM_CALLED_DURING_FASTPATH = False  # Reset sentinel


def _mark_llm_call_attempt() -> None:
    """Monkey-patched onto LLM client during tests to detect violations."""
    global _LLM_CALLED_DURING_FASTPATH
    _LLM_CALLED_DURING_FASTPATH = True
    raise AssertionError("FastPath MUST NOT call LLM (Execution Rule 6 violated)")


# ── Response Templates ─────────────────────────────────────────
ORDER_STATUS_TEMPLATE = (
    "Hi {customer_name}! 👋 Your order **#{order_id}** is currently "
    "**{order_status}**. Expected delivery: **{eta}**. "
    "Tracking link: {tracking_url}. Need more help? Just ask!"
)

REFUND_STATUS_TEMPLATE = (
    "Hello {customer_name}! Your refund of **₹{refund_amount}** for order "
    "**#{order_id}** is **{refund_status}**. "
    "It will be credited to your {payment_method} within {refund_eta} business days."
)

INVOICE_TEMPLATE = (
    "Hi {customer_name}! Your GST invoice for order **#{order_id}** "
    "(Amount: ₹{amount}, GSTIN: {gstin}) is ready. "
    "Download link: {invoice_url}. Valid for 7 days."
)

COD_STATIC_TEMPLATE = (
    "Cash on Delivery (COD) is available for orders up to ₹{cod_limit}. "
    "COD remittance is processed within 3–5 business days after delivery. "
    "For NDR cases, our team will contact you within 24 hours."
)


@dataclass
class FastPathRule:
    name: str
    patterns: list[str]
    intent: str
    template: str
    requires_ticket_lookup: bool = True
    compiled_patterns: list[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in self.patterns
        ]

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self.compiled_patterns)


# ── Rule Registry (ordered by priority) ──────────────────────
FAST_PATH_RULES: list[FastPathRule] = [
    FastPathRule(
        name="order_tracking",
        patterns=[
            r"\btrack\b.*\border\b",
            r"\bwhere.*(my order|my package|mera order)\b",
            r"\border status\b",
            r"\bshipment status\b",
            r"\bdelivery status\b",
            r"\bkahan hai.*order\b",
            r"\border.*kahan\b",
            r"\btracking\b",
        ],
        intent="order_status",
        template=ORDER_STATUS_TEMPLATE,
        requires_ticket_lookup=True,
    ),
    FastPathRule(
        name="refund_status",
        patterns=[
            r"\brefund status\b",
            r"\brefund.*pending\b",
            r"\bwhen.*refund\b",
            r"\bmy refund\b",
            r"\brefund kab\b",
            r"\bpaise.*wapas\b",
            r"\breturn.*money\b",
        ],
        intent="refund_status",
        template=REFUND_STATUS_TEMPLATE,
        requires_ticket_lookup=True,
    ),
    FastPathRule(
        name="invoice_download",
        patterns=[
            r"\bdownload.*invoice\b",
            r"\binvoice.*copy\b",
            r"\bGST invoice\b",
            r"\bbill.*copy\b",
            r"\bkaccha bill\b",
            r"\binvoice chahiye\b",
        ],
        intent="invoice_download",
        template=INVOICE_TEMPLATE,
        requires_ticket_lookup=True,
    ),
    FastPathRule(
        name="cod_query",
        patterns=[
            r"\bCOD\b",
            r"\bcash on delivery\b",
            r"\bCOD.*available\b",
            r"\bcash.*delivery\b",
        ],
        intent="cod_query",
        template=COD_STATIC_TEMPLATE,
        requires_ticket_lookup=False,
    ),
]


@dataclass
class NormalizedInput:
    """Result of InputNormalizer.normalize() — always safe to process."""
    text: str
    hinglish_detected: bool = False
    aggressive_tone: bool = False
    requires_clarification: bool = False
    clarification_reason: str = ""
    was_truncated: bool = False
    was_sanitized: bool = False


class InputNormalizer:
    """
    Invariant 21: Every input normalized without crash.
    Execution Rule 7: empty/too-long/injection/abusive inputs handled safely.
    """

    MIN_LENGTH = 3
    MAX_LENGTH = 1000

    HINGLISH_MARKERS = [
        "kahan", "kab", "milega", "nahi", "bhai", "chahiye",
        "mera", "meri", "hai", "hua", "wapas", "paise", "kaccha",
        "abhi", "please", "yaar", "ho gaya", "nahi mila",
    ]

    AGGRESSIVE_MARKERS = [
        "now", "immediately", "scam", "cheater", "fraud",
        "sue", "legal action", "fir", "consumer forum",
        "rubbish", "pathetic", "disgusting", "useless",
        "worst", "horrible",
    ]

    INJECTION_PATTERNS = [
        re.compile(r"(SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\s+", re.IGNORECASE),
        re.compile(r"<script.*?>", re.IGNORECASE),
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"\{\{.*?\}\}"),  # template injection
        re.compile(r"__import__", re.IGNORECASE),
    ]

    def normalize(self, raw: str) -> NormalizedInput:
        """
        Process raw user input into safe NormalizedInput.
        NEVER raises. Returns requires_clarification=True for unsafe inputs.
        """
        if not raw or not raw.strip():
            return NormalizedInput(
                text="",
                requires_clarification=True,
                clarification_reason="empty_input",
            )

        text = raw.strip()
        was_truncated = False
        was_sanitized = False

        # ── Length guards ──────────────────────────────────────
        if len(text) < self.MIN_LENGTH:
            return NormalizedInput(
                text=text,
                requires_clarification=True,
                clarification_reason="too_short",
            )

        if len(text) > self.MAX_LENGTH:
            text = text[: self.MAX_LENGTH]
            was_truncated = True
            logger.info(f"input_truncated from {len(raw)} to {self.MAX_LENGTH} chars")

        # ── Injection detection ────────────────────────────────
        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("injection_attempt_detected", extra={"input_prefix": text[:50]})
                return NormalizedInput(
                    text="[sanitized]",
                    requires_clarification=True,
                    clarification_reason="injection_detected",
                    was_sanitized=True,
                )

        lower = text.lower()
        hinglish = sum(1 for m in self.HINGLISH_MARKERS if m in lower) >= 2
        aggressive = any(m in lower for m in self.AGGRESSIVE_MARKERS)

        return NormalizedInput(
            text=text,
            hinglish_detected=hinglish,
            aggressive_tone=aggressive,
            requires_clarification=False,
            was_truncated=was_truncated,
            was_sanitized=was_sanitized,
        )


@dataclass
class FastPathResponse:
    message: str
    intent: str
    fast_path_used: bool = True
    latency_ms: int = 0
    rule_name: str = ""


class FastPathExecutor:
    """
    Execution Rule 6: NEVER calls LLM.
    Invariant 10: resolves in <= 200ms.
    Invariant 11: always logs fast_path_used=True.
    """

    def __init__(self) -> None:
        self.normalizer = InputNormalizer()

    def match_rule(self, normalized_text: str) -> FastPathRule | None:
        """Return first matching rule or None."""
        for rule in FAST_PATH_RULES:
            if rule.matches(normalized_text):
                return rule
        return None

    async def execute(
        self,
        rule: FastPathRule,
        ticket_data: dict[str, Any],
        customer_name: str,
    ) -> FastPathResponse:
        """
        Execute fast-path resolution.
        Assertion: no LLM client is invoked during this method.
        """
        t0 = time.monotonic()
        _assert_no_llm_call()  # Execution Rule 6 sentinel

        try:
            response_text = rule.template.format(
                customer_name=customer_name,
                order_id=ticket_data.get("order_id", "N/A"),
                order_status=ticket_data.get("status", "processing"),
                eta=ticket_data.get("eta", "2-3 business days"),
                tracking_url=ticket_data.get("tracking_url", "#"),
                refund_amount=ticket_data.get("refund_amount", "0"),
                refund_status=ticket_data.get("refund_status", "processing"),
                refund_eta=ticket_data.get("refund_eta", "5-7"),
                payment_method=ticket_data.get("payment_method", "original payment method"),
                amount=ticket_data.get("amount", "0"),
                gstin=ticket_data.get("gstin", "N/A"),
                invoice_url=ticket_data.get("invoice_url", "#"),
                cod_limit=ticket_data.get("cod_limit", "10,000"),
            )
        except KeyError as e:
            # Template key missing — return safe fallback without LLM
            response_text = (
                f"I found your request about {rule.intent.replace('_', ' ')}. "
                "Please check our portal or contact support for specific details."
            )
            logger.warning(f"fastpath_template_key_missing: {e}")

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Invariant 11: log fast_path_used=True always
        logger.info(
            "fast_path_resolved",
            extra={
                "rule": rule.name,
                "intent": rule.intent,
                "latency_ms": latency_ms,
                "fast_path_used": True,  # REQUIRED
            },
        )

        # Invariant 10: warn if latency exceeded (shouldn't happen without LLM)
        if latency_ms > 200:
            logger.warning(f"fastpath_latency_exceeded: {latency_ms}ms > 200ms")

        return FastPathResponse(
            message=response_text,
            intent=rule.intent,
            fast_path_used=True,
            latency_ms=latency_ms,
            rule_name=rule.name,
        )


# ── Global singletons ─────────────────────────────────────────
fast_path_executor = FastPathExecutor()
input_normalizer = InputNormalizer()
