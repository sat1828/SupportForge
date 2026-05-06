#!/usr/bin/env bash
# SupportForge — one-command deploy
# Usage: ./start.sh [--seed] [--with-eval]
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }

SEED=false
WITH_EVAL=false
for arg in "$@"; do
  case $arg in --seed) SEED=true ;; --with-eval) WITH_EVAL=true ;; esac
done

info "Starting SupportForge..."

# Copy .env if not present
if [ ! -f .env ]; then
  warn ".env not found — copying from .env.example"
  cp .env.example .env
  warn "Please fill in GROQ_API_KEY in .env before first run"
fi

# Build and start all services
info "Building and starting Docker services..."
docker compose up -d --build

# Wait for backend health
info "Waiting for backend to be ready..."
for i in {1..30}; do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    success "Backend is ready"
    break
  fi
  echo -n "."
  sleep 3
done

# Seed KB (optional)
if [ "$SEED" = true ]; then
  info "Seeding knowledge base..."
  docker compose exec backend python scripts/seed_kb.py
  success "KB seeded"
fi

echo ""
echo -e "${GREEN}🚀 SupportForge is running!${NC}"
echo ""
echo "  Frontend:    http://localhost:3000"
echo "  API Docs:    http://localhost:8000/docs"
echo "  Grafana:     http://localhost:3001  (admin / admin)"
echo "  Prometheus:  http://localhost:9090"
echo ""
echo "  Default login: admin@supportforge.dev / admin123"
echo ""
