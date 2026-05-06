# SupportForge AI

> A stateful multi-agent customer support system built with LangGraph, FastAPI, and Next.js.
> This is a portfolio project demonstrating production-grade agentic AI patterns.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B35)](https://github.com/langchain-ai/langgraph)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Current Status

**Production-ready core implemented.** Some features are in progress — see [Limitations](#limitations) below.

---

## Architecture

```
User Message
     │
     ├──> [InputNormalizer] ── injection guard, length check, Hinglish detection
     │
     ├──> [Fast-Path Match?] ── YES ──> [FastPathExecutor] ── 0 LLM calls, <200ms
     │                                        (regex rules for order tracking, refunds, invoices)
     NO
     │
     ├──> [ARQ Queue] ── POST /chat returns 202 in <50ms
     │
     ├──> [LangGraph StateGraph]
     │     ├──> [triage]      ── structured output: intent, priority, language
     │     ├──> [supervisor]    ── confidence-based routing
     │     ├──> [kb_search]     ── hybrid RAG: BM25 + vector + RRF + reranker
     │     ├──> [fraud_check]   ── 9 deterministic domain rules (GST, COD, refund)
     │     ├──> [resolver]      ── tool-calling + multi-factor confidence
     │     ├──> [emailer]       ── HITL gate for refunds >₹5000
     │     └──> [escalation]    ── human handoff
     │
     └──> [SSE Stream] ── Frontend receives real-time updates with response_meta
```

---

## Implemented Features

### LangGraph Multi-Agent System
- `StateGraph` with `AsyncPostgresSaver` checkpointer for stateful, resumable execution
- Budget guards on every edge enforcing: max 10 steps, 10s latency, 5 LLM calls, 5000 tokens
- `interrupt_before=["emailer"]` for human-in-the-loop approval

### Hybrid RAG Pipeline
- **BM25** keyword search (`rank-bm25`)
- **Vector** search (pgvector + `all-MiniLM-L6-v2`)
- **Reciprocal Rank Fusion** merging
- **Cross-encoder** reranking (`ms-marco-MiniLM-L-6-v2`)
- Redis-cached embeddings (24h TTL)

### Fast-Path Rule Engine
- 4 regex rules for common queries (order tracking, refunds, invoices, COD)
- Executes in <200ms with **zero LLM calls**
- Covers ~30% of test queries (benchmark pending)

### Domain Intelligence
- 9 deterministic fraud detection rules for Indian SME context
- GSTIN validation, refund fraud detection, COD failure tracking
- Results injected into `AgentState.fraud_signals`

### Multi-Factor Confidence Scoring
```
score = 0.4 × llm_confidence
      + 0.3 × rag_relevance
      + 0.2 × tool_execution_success
      + 0.1 × historical_accuracy
```
- Hard floors: tool failure → score ≤ 0.60
- Routing: ≥0.80 resolve, ≥0.65 retry KB, else escalate

### Observability
- **Prometheus** metrics for latency, cost, confidence, tools
- **Structlog** structured logging
- **Replay system**: 7-day full state retention, 90-day summary retention
- **Audit logs**: all escalations, corrections, budget breaches

---

## Tech Stack

| Layer | Technology |
|-------|-------------|
| LLM | Groq Llama-3.1-8b (primary), Ollama (fallback) |
| Agent Framework | LangGraph 0.2 + Postgres checkpointer |
| Backend | FastAPI 0.115 + Uvicorn |
| Task Queue | ARQ + Redis |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Frontend | Next.js 15 + React 19 + Framer Motion |
| Observability | Prometheus + structlog |

---

## Quick Start

### Prerequisites
- Docker Desktop 24+
- Python 3.11+
- Node.js 18+
- Groq API key (free at https://console.groq.com)

### Setup

```bash
git clone https://github.com/sat1828/SupportForge.git
cd SupportForge

# Copy environment files
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Start all services
docker compose up -d --build

# Seed database
docker compose exec backend python scripts/seed_kb.py

# Access
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:8000/docs
# Admin:     admin@supportforge.dev / admin123
```

### Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

---

## Running Tests

```bash
cd backend

# Unit tests (no external services)
pytest tests/unit/ -v

# Integration tests (requires Postgres + Redis)
pytest tests/integration/ -v -m integration

# Coverage
pytest --cov=app --cov-report=html
```

---

## Limitations (Honest Disclaimer)

1. **Hinglish support is incomplete** — Input normalization detects Hinglish but there's no translation pipeline yet. The LLM receives raw Hinglish text.
2. **Metrics are not benchmarked** — The "~30% fast-path" and "80% resolution rate" claims are estimates, not tested results. Actual benchmarks are pending.
3. **Frontend SSE has known issues** — `EventSource` doesn't send cookies. Authentication for streaming needs replacement with `fetch()`-based reader. **[FIXED in latest commit]**
4. **Grafana is unconfigured** — The service runs but has no pre-built dashboards.
5. **Rate limiting is not implemented** — `fastapi-limiter` is installed but not wired up yet.
6. **Only 5 KB documents** — The knowledge base has only refund, GST, COD, shipping, and SLA policies. Real deployment needs 100+ documents.
7. **LibreTranslate integration is incomplete** — The Docker service runs but the translation tool isn't called in main flow.

---

## Project Structure

```
supportforge/
├── backend/
│   ├── app/
│   │   ├── agents/         # LangGraph nodes + StateGraph
│   │   ├── api/            # FastAPI routers
│   │   ├── core/           # fastpath, confidence, resilience
│   │   ├── rag/            # BM25 + Vector + RRF + Reranker
│   │   ├── tools/          # 6 agent tools
│   │   ├── workers/        # ARQ background workers
│   │   ├── models/         # SQLAlchemy ORM
│   │   └── observability/  # Prometheus, audit, replay
│   ├── tests/
│   │   ├── unit/          # fastpath, confidence, resilience
│   │   ├── integration/   # graph, API
│   │   └── conftest.py
│   ├── scripts/           # seed_kb.py, seed_admin.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── login/
│   │   ├── dashboard/
│   │   └── page.tsx      # Landing page
│   └── package.json
├── docker-compose.yml
├── README.md
└── LICENSE
```

---

## License

MIT License — see [LICENSE](LICENSE)

---

<div align="center">
Built for learning LangGraph, hybrid RAG, and production AI agent patterns.
</div>
