"""
Prometheus metrics registry — all custom metrics for SupportForge.
Covers invariants visibility, cost tracking, and system health.
"""
from prometheus_client import Counter, Gauge, Histogram

# ── Resolution & Routing ──────────────────────────────────────
resolution_rate_gauge = Gauge(
    "sf_resolution_rate",
    "Current session AI resolution rate (0-1)",
)

escalation_rate_gauge = Gauge(
    "sf_escalation_rate",
    "Current session escalation rate (0-1)",
)

fast_path_resolutions_counter = Counter(
    "sf_fast_path_resolutions_total",
    "Total tickets resolved via fast-path (0 LLM calls)",
    labelnames=["rule"],
)

agent_resolutions_counter = Counter(
    "sf_agent_resolutions_total",
    "Total tickets resolved via LangGraph agent",
    labelnames=["action"],  # resolve | escalate | clarify
)

# ── Latency ───────────────────────────────────────────────────
agent_latency_histogram = Histogram(
    "sf_agent_latency_ms",
    "End-to-end agent execution latency in milliseconds",
    labelnames=["node"],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000, 10000],
)

rag_retrieval_latency = Histogram(
    "sf_rag_retrieval_latency_ms",
    "RAG retrieval latency",
    labelnames=["path"],  # "fast" | "full"
    buckets=[10, 25, 50, 100, 200, 500, 1000],
)

# ── Cost (Invariants 19-20) ────────────────────────────────────
cost_per_ticket_histogram = Histogram(
    "sf_cost_tokens_per_ticket",
    "Total tokens consumed per ticket",
    buckets=[100, 500, 1000, 2000, 3500, 5000],
)

llm_calls_per_ticket_histogram = Histogram(
    "sf_llm_calls_per_ticket",
    "LLM API calls per ticket",
    buckets=[1, 2, 3, 4, 5],
)

cost_exceeded_counter = Counter(
    "sf_cost_exceeded_total",
    "Cost limit breach events",
    labelnames=["reason"],  # max_llm_calls | max_tokens
)

# ── LLM Provider ──────────────────────────────────────────────
llm_provider_counter = Counter(
    "sf_llm_provider_calls_total",
    "LLM calls by provider and status",
    labelnames=["provider", "status"],  # groq/ollama/cache × success/fail
)

# ── Tool Calls ────────────────────────────────────────────────
tool_call_counter = Counter(
    "sf_tool_calls_total",
    "Tool invocations by name and outcome",
    labelnames=["tool_name", "status"],  # success | fail | hitl_pending
)

# ── Confidence ────────────────────────────────────────────────
confidence_score_histogram = Histogram(
    "sf_confidence_score",
    "Distribution of calibrated confidence scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],
)

# ── Circuit Breaker ───────────────────────────────────────────
circuit_breaker_state_gauge = Gauge(
    "sf_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    labelnames=["provider"],
)

# ── Budget Guard (Invariants 1-3, 19-20) ─────────────────────
budget_breach_counter = Counter(
    "sf_budget_breach_total",
    "Execution budget breaches by type",
    labelnames=["breach_type"],  # steps | latency | kb_retries | llm_calls | tokens
)

# ── Queue ─────────────────────────────────────────────────────
queue_depth_gauge = Gauge(
    "sf_worker_queue_depth",
    "Current number of jobs in ARQ queue",
)

active_jobs_gauge = Gauge(
    "sf_worker_active_jobs",
    "Currently executing agent jobs",
)

# ── Robustness ────────────────────────────────────────────────
noisy_input_counter = Counter(
    "sf_noisy_input_total",
    "Inputs requiring normalization by type",
    labelnames=["type"],  # hinglish | aggressive | truncated | injection | empty
)
