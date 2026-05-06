# ─────────────────────────────────────────────────────────────
# SupportForge Backend — Multi-stage Dockerfile
# Stage 1: base     — system deps + poetry
# Stage 2: deps     — install Python packages
# Stage 3: test     — test environment
# Stage 4: production — minimal production image
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# System deps: curl (healthcheck), gcc (native extensions), libpq (asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

WORKDIR /app

# ── Dependency Installation Stage ─────────────────────────────
FROM base AS deps

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --only main

# ── Test Stage ────────────────────────────────────────────────
FROM deps AS test

# Install dev + lint deps for test environment
RUN poetry install --no-root --with dev,lint

COPY . .
RUN poetry install --only-root

# ── Production Stage ──────────────────────────────────────────
FROM deps AS production

# Create non-root user (security best practice)
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .
RUN poetry install --only-root

# Download NLTK data at build time (avoids runtime download)
RUN python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True)"

# Pre-download sentence-transformer model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
