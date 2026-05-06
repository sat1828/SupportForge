-- PostgreSQL 16 init script
-- Run by Docker on first startup

-- pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram index for LIKE queries
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- LangGraph checkpointer schema (created by langgraph-checkpoint-postgres)
-- Tables created automatically by checkpointer.setup()
