"""
FastAPI application factory — lifespan, middleware, routers.
"""
from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import settings
from app.database import create_all_tables

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger.info("supportforge_starting", environment=settings.environment)

    # 1. Create DB tables + pgvector extension
    await create_all_tables()

    # 2. Build BM25 index from existing KB chunks
    try:
        from app.rag.bm25_index import bm25_index
        await bm25_index.rebuild_from_db()
    except Exception as e:
        logger.warning(f"bm25_rebuild_failed_startup: {e}")

    # 3. Initialize Redis connection for agent API
    try:
        from app.api.agent import init_redis
        await init_redis()
    except Exception as e:
        logger.warning(f"redis_init_failed: {e}")

    # 4. Start APScheduler for replay retention jobs
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from app.database import AsyncSessionLocal
        from app.observability.replay import compress_old_steps, purge_expired_steps

        scheduler = AsyncIOScheduler()

        async def _compress_job() -> None:
            async with AsyncSessionLocal() as db:
                await compress_old_steps(db)

        async def _purge_job() -> None:
            async with AsyncSessionLocal() as db:
                await purge_expired_steps(db)

        scheduler.add_job(_compress_job, "cron", hour=2, minute=0)
        scheduler.add_job(_purge_job, "cron", hour=3, minute=0)
        scheduler.start()
        app.state.scheduler = scheduler
    except Exception as e:
        logger.warning(f"scheduler_init_failed: {e}")

    # 5. Configure LangSmith (optional — graceful degradation)
    if settings.langsmith_enabled:
        try:
            import os
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
            logger.info("langsmith_enabled")
        except Exception as e:
            logger.warning(f"langsmith_init_failed: {e}")

    logger.info("supportforge_ready")
    yield

    # Shutdown
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()
    logger.info("supportforge_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SupportForge API",
        description="Production-grade AI Agent for Automated Customer Support",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # -- CORS --------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Request logging middleware -----------------------------
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.monotonic()
        response: Response = await call_next(request)
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=elapsed,
        )
        return response

    # -- Routes ------------------------------------------------
    from app.api.admin import router as admin_router
    from app.api.agent import router as agent_router
    from app.api.auth import router as auth_router
    from app.api.tickets import router as tickets_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(tickets_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    # -- Prometheus metrics endpoint ---------------------------
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # -- Health check ------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    # -- Global exception handler ------------------------------
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "response_meta": {
                    "confidence": 0.0,
                    "action": "escalate",
                    "reason": "An unexpected error occurred. Please try again.",
                    "step_count": 0,
                    "fast_path_used": False,
                    "tool_calls_summary": [],
                    "escalation_reason": "internal_error",
                },
            },
        )

    return app


app = create_app()
