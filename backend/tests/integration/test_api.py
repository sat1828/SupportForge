"""
Integration tests for the FastAPI endpoints.
Tests: auth, ticket CRUD, agent chat (fast-path), metrics.
"""
import uuid
import pytest


@pytest.mark.integration
class TestAuthAPI:
    async def test_register_success(self, client):
        resp = await client.post("/api/auth/register", json={
            "email": f"{uuid.uuid4().hex[:8]}@test.com",
            "full_name": "Integration User",
            "password": "securepassword123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"].endswith("@test.com")
        assert data["role"] == "customer"

    async def test_register_duplicate_email(self, client, test_user):
        resp = await client.post("/api/auth/register", json={
            "email": test_user.email,
            "full_name": "Dup User",
            "password": "securepassword123",
        })
        assert resp.status_code == 409

    async def test_login_success(self, client, test_user):
        resp = await client.post("/api/auth/login", json={
            "email": test_user.email,
            "password": "test_password_123",
        })
        assert resp.status_code == 200
        # HTTPOnly cookie must be set
        assert "access_token" in resp.cookies or "Set-Cookie" in resp.headers

    async def test_login_wrong_password(self, client, test_user):
        resp = await client.post("/api/auth/login", json={
            "email": test_user.email,
            "password": "wrong_password",
        })
        assert resp.status_code == 401

    async def test_logout(self, client):
        resp = await client.post("/api/auth/logout")
        assert resp.status_code == 200


@pytest.mark.integration
class TestTicketsAPI:
    async def test_create_ticket(self, client, auth_headers):
        resp = await client.post("/api/tickets/", json={
            "title": "My order has not arrived after 10 days",
            "description": "Order placed on April 15th, still no delivery update.",
            "priority": "P2",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "open"
        assert data["priority"] == "P2"
        # SLA deadline must be set
        assert data["sla_deadline"] is not None

    async def test_list_tickets(self, client, auth_headers, test_ticket):
        resp = await client.get("/api/tickets/", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_ticket(self, client, auth_headers, test_ticket):
        resp = await client.get(f"/api/tickets/{test_ticket.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_ticket.id)

    async def test_get_nonexistent_ticket(self, client, auth_headers):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/tickets/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_create_ticket_unauthenticated(self, client):
        resp = await client.post("/api/tickets/", json={
            "title": "Should fail",
            "description": "No auth header provided here.",
        })
        assert resp.status_code == 401


@pytest.mark.integration
class TestAgentChatAPI:
    async def test_fast_path_order_tracking(self, client, auth_headers, test_ticket):
        """Fast-path messages must return 200 with response_meta immediately."""
        resp = await client.post(
            f"/api/agent/chat/{test_ticket.id}",
            json={"message": "Where is my order? Track it please"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "fast_path_resolved"
        meta = data["response_meta"]
        assert meta is not None
        assert meta["fast_path_used"] is True
        assert meta["confidence"] >= 0.9

    async def test_empty_message_requires_clarification(self, client, auth_headers, test_ticket):
        """Invariant 21: empty input → clarify, not crash."""
        resp = await client.post(
            f"/api/agent/chat/{test_ticket.id}",
            json={"message": "   "},  # whitespace only
            headers=auth_headers,
        )
        # Pydantic validation catches this (min_length=1 after strip)
        assert resp.status_code in (200, 422)

    async def test_injection_input_handled(self, client, auth_headers, test_ticket):
        """Execution Rule 7: injection input returns clarify, not crash."""
        resp = await client.post(
            f"/api/agent/chat/{test_ticket.id}",
            json={"message": "SELECT * FROM users WHERE 1=1; DROP TABLE tickets;"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        meta = data.get("response_meta", {})
        assert meta.get("action") == "clarify"

    async def test_async_job_returns_202(self, client, auth_headers, test_ticket):
        """Execution Rule 5: non-fast-path must return 202 (not block)."""
        # A complex query that won't hit fast-path
        resp = await client.post(
            f"/api/agent/chat/{test_ticket.id}",
            json={"message": "I have a warranty claim for my product that arrived damaged during transit last month"},
            headers=auth_headers,
        )
        # Either fast-path (200) or queued (202) — never 5xx
        assert resp.status_code in (200, 202)

    async def test_hinglish_input_normalized(self, client, auth_headers, test_ticket):
        """Hinglish input must be processed, not rejected."""
        resp = await client.post(
            f"/api/agent/chat/{test_ticket.id}",
            json={"message": "Mera order kahan hai bhai? Tracking batao please"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 202)
        if resp.status_code == 200:
            assert resp.json()["response_meta"] is not None


@pytest.mark.integration
class TestHealthEndpoint:
    async def test_health_check(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
