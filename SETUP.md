# SupportForge Setup Guide

Complete local and Docker deployment guide.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Node.js | 18+ | `node --version` |
| Python | 3.11+ | `python --version` |
| Git | 2.40+ | `git --version` |

---

## Quick Start (Docker — Recommended)

### 1. Clone and Configure

```bash
git clone https://github.com/sat1828/Support2.git
cd Support2/supportforge
cp .env.example .env
```

### 2. Edit `.env` — Fill in Required Values

Open `.env` and update these fields:

```env
# Required: Generate a secure key
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">

# Required: Your Groq API key (free at https://console.groq.com)
GROQ_API_KEY=gsk_your_key_here

# Optional: LangSmith tracing (https://smith.langchain.com)
LANGSMITH_API_KEY=lsv2_your_key_here
```

> **Note:** `DATABASE_URL` and `REDIS_URL` are pre-configured for Docker networking. Do not change them unless running outside Docker.

### 3. Start All Services

```bash
docker compose up -d --build
```

This starts:
- PostgreSQL 16 + pgvector
- Redis 7
- FastAPI backend (port 8000)
- ARQ agent workers (2 replicas)
- Next.js frontend (port 3000)
- Prometheus (port 9090)
- Grafana (port 3001)
- LibreTranslate Hindi/English (port 5000)

### 4. Seed Database

```bash
# Wait ~30 seconds for services to be healthy, then:
docker compose exec backend python scripts/seed_admin.py
docker compose exec backend python scripts/seed_kb.py
```

### 5. Access the Application

| Service | URL | Credentials |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | admin@supportforge.dev / admin123 |
| **API Docs** | http://localhost:8000/docs | — |
| **Prometheus** | http://localhost:9090 | — |
| **Grafana** | http://localhost:3001 | admin / admin |

---

## Local Development (No Docker)

### Backend

```bash
cd supportforge/backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set environment variables (Windows PowerShell)
$env:DATABASE_URL = "postgresql+asyncpg://supportforge:password@localhost:5432/supportforge"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:SECRET_KEY = "your_secret_key_minimum_32_characters_long"
$env:GROQ_API_KEY = "your_groq_key"

# Start the backend
uvicorn app.main:app --reload --port 8000
```

### ARQ Worker (separate terminal)

```bash
cd supportforge/backend
python -m arq app.workers.agent_worker.WorkerSettings
```

### Frontend

```bash
cd supportforge/frontend
npm install
npm run dev
# Open http://localhost:3000
```

---

## Seeding Knowledge Base

The KB seeder processes 5 policy documents:
- `refund_policy.txt` — Return and refund rules
- `gst_invoice_policy.txt` — GST compliance and invoice generation
- `cod_policy.txt` — Cash on delivery remittance rules
- `fraud_detection_rules.txt` — 9 domain fraud detection rules
- `shipping_policy.txt` — Delivery SLA and NDR handling

```bash
docker compose exec backend python scripts/seed_kb.py
# Or locally:
python backend/scripts/seed_kb.py
```

---

## Running Tests

```bash
cd supportforge/backend

# Unit tests only (no external services needed)
pytest tests/unit/ -v

# Integration tests (requires running Postgres + Redis)
pytest tests/integration/ -v -m integration

# Full 130-case robustness dataset
pytest tests/evaluation/robustness_dataset.py -v -m robustness

# All tests with coverage
pytest --cov=app --cov-report=html
```

---

## Verifying System Invariants

The system enforces 21 invariants at runtime. Check them via:

```bash
# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=sf_budget_breach_total

# Check API health
curl http://localhost:8000/health

# Check admin metrics (requires auth token)
curl -b "access_token=YOUR_TOKEN" http://localhost:8000/api/admin/metrics
```

Visit `http://localhost:3000/dashboard/analytics` for the live invariant compliance dashboard.

---

## Stopping Services

```bash
docker compose down          # Stop but keep data
docker compose down -v       # Stop and delete all volumes (fresh start)
```

---

## Troubleshooting

### Backend won't start

```
ValidationError: DATABASE_URL field required
```
**Fix:** Add `DATABASE_URL` to your `.env` file:
```
DATABASE_URL=postgresql+asyncpg://supportforge:password@postgres:5432/supportforge
```

### pgvector extension missing

```
ProgrammingError: could not open extension control file
```
**Fix:** Use the `pgvector/pgvector:pg16` image (already in docker-compose.yml). Do not use plain `postgres:16`.

### LangGraph checkpointer fails

```
ModuleNotFoundError: No module named 'psycopg'
```
**Fix:** `pip install psycopg[binary]` — the sync psycopg3 driver is required by `langgraph-checkpoint-postgres`.

### Frontend build fails

```
Cannot find module 'framer-motion'
```
**Fix:** `cd frontend && npm install`

### Push to GitHub fails

Use a Personal Access Token (PAT), not your password:
1. Go to https://github.com/settings/tokens/new
2. Select scope: **repo** (full control of private repositories)
3. Copy the token
4. When git prompts for password, paste the token

Or use the credential manager:
```bash
git config --global credential.helper manager
git push -u origin main
# When prompted: username=your_github_username, password=YOUR_PAT_TOKEN
```
