"""Deterministic unit tests for the authentication session State.

The base AuthState is instantiated directly (allowed under pytest) with
``_make_client`` patched to a MockTransport-backed client. No network, no real
backend, no real credentials.
"""

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from app.services.client import ApiClient, ApiError
from app.state.auth import AuthState


def _client(handler) -> ApiClient:
    return ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))


def _token_response():
    return httpx.Response(
        200,
        json={"access_token": "access-1", "refresh_token": "refresh-1", "token_type": "bearer"},
    )


def _me_response():
    return httpx.Response(
        200,
        json={
            "_id": "507f1f77bcf86cd799439011",
            "username": "alice",
            "permissions": ["read", "write"],
            "active": True,
        },
    )


def _session_handler():
    """Handler that serves a successful login followed by a successful /auth/me."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        if request.url.path == "/auth/me":
            return _me_response()
        raise AssertionError(f"unexpected request: {request.url.path}")

    return handler


async def _login(state: AuthState, handler, username="alice", password="password"):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        return await state.login(username, password)


async def _logout(state: AuthState, handler):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        return await state.logout()


async def _submit_login(state: AuthState, handler):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        return await state.submit_login()


def _redirect_path(result) -> str | None:
    """Extract the redirect path from an event handler result, if any."""
    specs = result if isinstance(result, list) else [result] if result else []
    for spec in specs:
        for arg, value in getattr(spec, "args", []) or []:
            if getattr(arg, "_js_expr", None) == "path":
                return getattr(value, "_var_value", None)
    return None


def test_successful_login_returns_redirect_to_dashboard():
    state = AuthState()
    result = asyncio.run(_login(state, _session_handler()))

    assert _redirect_path(result) == "/"
    assert state.is_authenticated is True


def test_invalid_credentials_return_no_redirect():
    state = AuthState()
    result = asyncio.run(
        _login(
            state,
            lambda request: httpx.Response(401, json={"detail": "Invalid username or password"}),
            password="wrong",
        )
    )

    assert result is None
    assert state.is_authenticated is False


def test_successful_login_stores_session():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    assert state.is_authenticated is True
    assert state.username == "alice"
    assert state.error_message == ""
    assert state._access_token == "access-1"
    assert state._refresh_token == "refresh-1"
    assert state.user_id == "507f1f77bcf86cd799439011"
    assert state.permissions == ["read", "write"]
    assert state.active is True


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
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
    assert state.error_message == "Invalid username or password."


def test_backend_error_does_not_leave_partial_session():
    state = AuthState()
    asyncio.run(_login(state, lambda request: httpx.Response(503, json={"detail": "boom"})))

    assert state.is_authenticated is False
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
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
    asyncio.run(_login(state, _session_handler()))
    assert state.is_authenticated is True

    result = asyncio.run(_logout(state, lambda request: httpx.Response(204)))

    assert _redirect_path(result) == "/login"
    assert state.is_authenticated is False
    assert state.username == ""
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
    assert state.error_message == ""


def test_logout_returns_redirect_when_nothing_to_revoke():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/auth/login"):
            return httpx.Response(401, json={"detail": "nope"})
        raise AssertionError("logout should not reach the backend")

    state = AuthState()

    result = asyncio.run(_logout(state, handler))

    assert _redirect_path(result) == "/login"
    assert state._refresh_token == ""


def test_guard_authenticated_redirects_anonymous_to_login():
    state = AuthState()

    result = state.guard_authenticated()

    assert _redirect_path(result) == "/login"


def test_guard_authenticated_allows_authenticated():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    result = state.guard_authenticated()

    assert result is None


def test_guard_login_redirects_authenticated_to_dashboard():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    result = state.guard_login()

    assert _redirect_path(result) == "/"


def test_guard_login_allows_anonymous():
    state = AuthState()

    result = state.guard_login()

    assert result is None


def test_submit_login_success_redirects_and_clears_password():
    state = AuthState()
    state.username_input = "  alice  "
    state.password_input = "password"

    result = asyncio.run(_submit_login(state, _session_handler()))

    assert _redirect_path(result) == "/"
    assert state.is_authenticated is True
    assert state.username == "alice"
    assert state.password_input == ""
    assert state.submitting is False


def test_submit_login_failure_keeps_username_and_clears_password():
    state = AuthState()
    state.username_input = "alice"
    state.password_input = "wrong"

    result = asyncio.run(
        _submit_login(
            state,
            lambda request: httpx.Response(401, json={"detail": "Invalid username or password"}),
        )
    )

    assert result is None
    assert state.is_authenticated is False
    assert state.username_input == "alice"
    assert state.password_input == ""
    assert state.submitting is False
    assert state.error_message == "Invalid username or password."


def test_logout_revokes_refresh_token_serverside():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        if request.url.path == "/auth/me":
            return _me_response()
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
        if request.url.path == "/auth/me":
            return _me_response()
        return httpx.Response(500, json={"detail": "downstream down"})

    state = AuthState()
    asyncio.run(_login(state, handler))

    asyncio.run(_logout(state, handler))

    assert state.is_authenticated is False
    assert state._refresh_token == ""


def test_tokens_not_exposed_through_public_state():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    assert "_access_token" not in state.vars
    assert "_refresh_token" not in state.vars
    snapshot = state.dict()
    assert not any("access-1" in str(v) or "refresh-1" in str(v) for v in snapshot.values())


def _refresh_response():
    return httpx.Response(
        200,
        json={"access_token": "access-2", "refresh_token": "refresh-2", "token_type": "bearer"},
    )


async def _do_refresh(state: AuthState, handler):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        return await state._refresh()


def test_refresh_success_replaces_both_tokens():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))
    assert state._access_token == "access-1"
    assert state._refresh_token == "refresh-1"

    result = asyncio.run(_do_refresh(state, lambda request: _refresh_response()))

    assert result == "access-2"
    assert state._access_token == "access-2"
    assert state._refresh_token == "refresh-2"
    assert state.is_authenticated is True
    assert state.error_message == ""


def test_refresh_uses_stored_refresh_token():
    seen_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/refresh"
        seen_body.update(json.loads(request.content))
        return _refresh_response()

    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    asyncio.run(_do_refresh(state, handler))

    assert seen_body == {"refresh_token": "refresh-1"}


def test_refresh_failure_clears_session_and_returns_None():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})

    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    result = asyncio.run(_do_refresh(state, handler))

    assert result is None
    assert state.is_authenticated is False
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.username == ""
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
    assert state.error_message == "Your session has expired. Please log in again."


def test_refresh_transport_failure_clears_session():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    result = asyncio.run(_do_refresh(state, handler))

    assert result is None
    assert state.is_authenticated is False
    assert state._refresh_token == ""


def test_refresh_without_stored_token_clears_and_returns_None():
    state = AuthState()

    result = asyncio.run(_do_refresh(state, lambda request: httpx.Response(200)))

    assert result is None
    assert state.is_authenticated is False


def test_client_401_triggers_refresh_once_and_retries_with_new_token():
    business_calls: list[dict] = []
    refresh_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_calls
        if request.url.path == "/auth/refresh":
            refresh_calls += 1
            assert json.loads(request.content) == {"refresh_token": "refresh-1"}
            return _refresh_response()
        if request.url.path.startswith("/auth/login"):
            return _token_response()
        if request.url.path == "/auth/me":
            return _me_response()
        business_calls.append({"auth": request.headers.get("Authorization", "")})
        if len(business_calls) == 1:
            return httpx.Response(401, json={"detail": "token expired"})
        return httpx.Response(200, json={"ok": True})

    state = AuthState()
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        asyncio.run(state.login("alice", "password"))
        client = state._make_client()
        response = asyncio.run(
            client.get("/api/v1/items", token=state._access_token, refresh_handler=state._refresh)
        )

    assert response.status_code == 200
    assert business_calls[0]["auth"] == "Bearer access-1"
    assert business_calls[1]["auth"] == "Bearer access-2"
    assert refresh_calls == 1
    assert state._access_token == "access-2"
    assert state._refresh_token == "refresh-2"


def test_client_refresh_failure_clears_session_and_does_not_retry_business_request():
    business_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/refresh":
            return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})
        if request.url.path.startswith("/auth/login"):
            return _token_response()
        if request.url.path == "/auth/me":
            return _me_response()
        business_calls.append(request.headers.get("Authorization", ""))
        return httpx.Response(401, json={"detail": "token expired"})

    state = AuthState()
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        asyncio.run(state.login("alice", "password"))
        client = state._make_client()
        with pytest.raises(ApiError):
            asyncio.run(
                client.get(
                    "/api/v1/items", token=state._access_token, refresh_handler=state._refresh
                )
            )

    assert business_calls == ["Bearer access-1"]
    assert state.is_authenticated is False
    assert state._access_token == ""
    assert state._refresh_token == ""
    assert state.error_message == "Your session has expired. Please log in again."


async def _load_user(state: AuthState, handler):
    with patch.object(AuthState, "_make_client", return_value=_client(handler)):
        return await state.load_user()


def test_load_user_populates_identity():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))
    assert state.user_id == "507f1f77bcf86cd799439011"
    assert state.username == "alice"
    assert state.permissions == ["read", "write"]
    assert state.active is True


def test_load_user_populates_inactive_value():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        return httpx.Response(
            200,
            json={"_id": "abc", "username": "alice", "permissions": ["read"], "active": False},
        )

    state = AuthState()
    asyncio.run(_login(state, handler))

    assert state.active is False
    assert state.is_authenticated is True
    assert state.permissions == ["read"]


def test_load_user_uses_authenticated_client_and_returns_true():
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return _token_response()
        if request.url.path == "/auth/me":
            seen_auth.append(request.headers.get("Authorization", ""))
            return _me_response()
        raise AssertionError(f"unexpected request: {request.url.path}")

    state = AuthState()
    asyncio.run(_login(state, handler))

    result = asyncio.run(_load_user(state, handler))

    assert result is True
    assert seen_auth == ["Bearer access-1", "Bearer access-1"]


def test_load_user_without_access_token_returns_false_and_clears():
    state = AuthState()
    result = asyncio.run(_load_user(state, lambda request: httpx.Response(200)))

    assert result is False
    assert state.is_authenticated is False


def test_load_user_401_clears_session_and_returns_false():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))
    assert state.is_authenticated is True

    result = asyncio.run(_load_user(state, lambda request: httpx.Response(401)))

    assert result is False
    assert state.is_authenticated is False
    assert state.username == ""
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
    assert state.error_message == "Your session has expired. Please log in again."


def test_load_user_transport_failure_clears_session_and_returns_false():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    state = AuthState()
    asyncio.run(_login(state, _session_handler()))
    assert state.is_authenticated is True

    result = asyncio.run(_load_user(state, handler))

    assert result is False
    assert state.is_authenticated is False
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False


def test_load_user_failure_does_not_leave_stale_identity():
    me_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal me_calls
        if request.url.path == "/auth/login":
            return _token_response()
        if request.url.path == "/auth/me":
            me_calls += 1
            if me_calls == 2:
                return httpx.Response(401, json={"detail": "token expired"})
            return _me_response()
        if request.url.path == "/auth/refresh":
            return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    state = AuthState()
    asyncio.run(_login(state, handler))
    assert state.permissions == ["read", "write"]

    result = asyncio.run(_load_user(state, handler))

    assert result is False
    assert state.is_authenticated is False
    assert state.username == ""
    assert state.permissions == []
    assert state.user_id is None
    assert state.active is False


def test_clear_session_clears_identity_and_permissions():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))
    assert state.is_authenticated is True

    state._clear_session()

    assert state.is_authenticated is False
    assert state.username == ""
    assert state.user_id is None
    assert state.permissions == []
    assert state.active is False
    assert state._access_token == ""
    assert state._refresh_token == ""


def test_permissions_are_loadable_and_present_in_public_state():
    state = AuthState()
    asyncio.run(_login(state, _session_handler()))

    assert "permissions" in state.vars
    assert state.permissions == ["read", "write"]
