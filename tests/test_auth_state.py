"""Deterministic unit tests for the authentication session State.

The base AuthState is instantiated directly (allowed under pytest) with
``_make_client`` patched to a MockTransport-backed client. No network, no real
backend, no real credentials.
"""

import asyncio
import json
from unittest.mock import patch

import httpx

from app.services.client import ApiClient
from app.state.auth import AuthState


def _client(handler) -> ApiClient:
    return ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))


def _token_response():
    return httpx.Response(
        200,
        json={"access_token": "access-1", "refresh_token": "refresh-1", "token_type": "bearer"},
    )


async def _login(state: AuthState, handler, username="alice", password="password"):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        await state.login(username, password)


async def _logout(state: AuthState, handler):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        await state.logout()


def test_successful_login_stores_session():
    state = AuthState()
    asyncio.run(_login(state, lambda request: _token_response()))

    assert state.is_authenticated is True
    assert state.username == "alice"
    assert state.error_message == ""
    assert state._access_token == "access-1"
    assert state._refresh_token == "refresh-1"


def test_invalid_credentials_leave_state_unauthenticated():
    state = AuthState()
    asyncio.run(
        _login(
            state,
            lambda request: httpx.Response(401, json={"detail": "Invalid username or password"}),
            password="wrong",
        )
    )

    assert state.is_authenticated is False
    assert state.username == ""
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.error_message == "Invalid username or password."


def test_backend_error_does_not_leave_partial_session():
    state = AuthState()
    asyncio.run(_login(state, lambda request: httpx.Response(503, json={"detail": "boom"})))

    assert state.is_authenticated is False
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.error_message == "Authentication service error."


def test_transport_failure_does_not_leave_partial_session():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    state = AuthState()
    asyncio.run(_login(state, handler))

    assert state.is_authenticated is False
    assert state._refresh_token == ""
    assert state.error_message == "Unable to reach the authentication service."


def test_logout_clears_session_and_tokens():
    state = AuthState()
    asyncio.run(_login(state, lambda request: _token_response()))
    assert state.is_authenticated is True

    asyncio.run(_logout(state, lambda request: httpx.Response(204)))

    assert state.is_authenticated is False
    assert state.username == ""
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.error_message == ""


def test_logout_revokes_refresh_token_serverside():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        assert request.url.path == "/auth/logout"
        assert json.loads(request.content) == {"refresh_token": "refresh-1"}
        return httpx.Response(204)

    state = AuthState()
    asyncio.run(_login(state, handler))

    asyncio.run(_logout(state, handler))

    assert state._refresh_token == ""


def test_logout_after_failed_login_sends_no_revoke():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/auth/login"):
            return httpx.Response(401, json={"detail": "nope"})
        raise AssertionError("logout should not reach the backend")

    state = AuthState()
    asyncio.run(_login(state, handler, password="wrong"))

    asyncio.run(_logout(state, handler))

    assert state._refresh_token == ""


def test_logout_surfaces_revocation_failure_without_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        return httpx.Response(500, json={"detail": "downstream down"})

    state = AuthState()
    asyncio.run(_login(state, handler))

    asyncio.run(_logout(state, handler))

    assert state.is_authenticated is False
    assert state._refresh_token == ""


def test_tokens_not_exposed_through_public_state():
    state = AuthState()
    asyncio.run(_login(state, lambda request: _token_response()))

    assert "_access_token" not in state.vars
    assert "_refresh_token" not in state.vars
    snapshot = state.dict()
    assert not any("access-1" in str(v) or "refresh-1" in str(v) for v in snapshot.values())
