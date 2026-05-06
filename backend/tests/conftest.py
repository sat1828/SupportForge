"""
Pytest fixtures — shared across all test modules.
Provides: async DB session, test app, test client, seeded user, seeded ticket.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Force test environment before any app imports ─────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test_user:test_pass@localhost:5432/supportforge_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_pytest_minimum_32_chars")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("MAX_STEPS_PER_TICKET", "10")
os.environ.setdefault("MAX_LATENCY_SECONDS", "10")
os.environ.setdefault("MAX_KB_RETRIES", "3")
os.environ.setdefault("MAX_LLM_CALLS_PER_TICKET", "5")
os.environ.setdefault("MAX_TOKENS_PER_TICKET", "5000")
os.environ.setdefault("LIBRETRANSLATE_URL", "http://localhost:5000")


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for entire session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    from app.database import engine, Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test DB session — rolled back after each test."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with DB override."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """Seeded customer user."""
    from app.models.user import User
    from app.core.security import hash_password
    from datetime import datetime, timezone

    user = User(
        id=uuid.uuid4(),
        email=f"test_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Test Customer",
        hashed_password=hash_password("test_password_123"),
        role="customer",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession):
    """Seeded admin user."""
    from app.models.user import User
    from app.core.security import hash_password
    from datetime import datetime, timezone

    user = User(
        id=uuid.uuid4(),
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Test Admin",
        hashed_password=hash_password("admin_password_123"),
        role="admin",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_ticket(db: AsyncSession, test_user):
    """Seeded open ticket."""
    from app.models.ticket import Ticket, TicketStatus, TicketPriority
    from datetime import datetime, timezone, timedelta

    ticket = Ticket(
        id=uuid.uuid4(),
        customer_id=test_user.id,
        title="Test: Where is my order?",
        description="I ordered 3 days ago and haven't received tracking info.",
        status=TicketStatus.OPEN,
        priority=TicketPriority.P3,
        sla_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ticket)
    await db.flush()
    return ticket


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user):
    """Login and return auth headers (Bearer token)."""
    resp = await client.post("/api/auth/login", json={
        "email": test_user.email,
        "password": "test_password_123",
    })
    assert resp.status_code == 200
    token = resp.cookies.get("access_token")
    return {"Cookie": f"access_token={token}"} if token else {}
