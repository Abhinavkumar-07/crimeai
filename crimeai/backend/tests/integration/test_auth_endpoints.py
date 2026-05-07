"""Integration tests for /api/v1/auth endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # Register
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "SecurePass1",
            "full_name": "New User",
            "badge_number": "T999",
        },
    )
    assert register_resp.status_code == 201
    assert "user_id" in register_resp.json()

    # Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@test.com", "password": "SecurePass1"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user2@test.com", "password": "SecurePass1", "full_name": "User 2"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user2@test.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/users/")
    assert resp.status_code == 401
