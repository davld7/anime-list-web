"""Deterministic unit tests for the frontend authentication service.

All HTTP calls use httpx.MockTransport; no external network, no real backend,
and no real credentials.
"""

import asyncio
import json

import httpx
import pytest

from app.services import auth
from app.services.auth import AuthError
from app.services.client import ApiClient


def _client(handler) -> ApiClient:
    return ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))


def test_login_success_returns_token_pair():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/login"
        assert json.loads(request.content) == {"username": "alice", "password": "hunter2"}
        return httpx.Response(
            200,
            json={"access_token": "access-1", "refresh_token": "refresh-1", "token_type": "bearer"},
        )

    tokens = asyncio.run(auth.login(_client(handler), username="alice", password="hunter2"))

    assert tokens.access_token == "access-1"
    assert tokens.refresh_token == "refresh-1"
    assert tokens.token_type == "bearer"


def test_login_token_type_defaults_to_bearer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})

    tokens = asyncio.run(auth.login(_client(handler), username="u", password="p"))

    assert tokens.token_type == "bearer"


def test_login_invalid_credentials_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid username or password"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="wrong"))

    assert excinfo.value.message == "Invalid username or password."


def test_login_backend_error_returns_generic_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "internal wiring"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="x"))

    assert excinfo.value.message == "Authentication service error."


def test_login_transport_failure_returns_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="x"))

    assert excinfo.value.message == "Unable to reach the authentication service."


def test_login_malformed_response_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy page</html>")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="x"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


def test_login_missing_token_field_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"refresh_token": "r"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="x"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


def test_login_error_message_never_contains_raw_body_or_credentials():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(500, json={"secret": "supersecret-sysinfo"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.login(_client(handler), username="alice", password="hunter2"))

    message = excinfo.value.message
    assert "supersecret-sysinfo" not in message
    assert "hunter2" not in message
    assert captured["payload"]["password"] == "hunter2"


def test_login_never_submits_auth_header():
    captures: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captures.append(request)
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})

    asyncio.run(auth.login(_client(handler), username="alice", password="pw"))

    assert "Authorization" not in captures[0].headers


def test_logout_sends_refresh_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/logout"
        assert json.loads(request.content) == {"refresh_token": "refresh-1"}
        return httpx.Response(204)

    result = asyncio.run(auth.logout(_client(handler), refresh_token="refresh-1"))

    assert result is None


def test_logout_surfaces_transport_error_as_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(AuthError):
        asyncio.run(auth.logout(_client(handler), refresh_token="refresh-1"))


def test_refresh_sends_correct_request():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/refresh"
        assert json.loads(request.content) == {"refresh_token": "refresh-1"}
        return httpx.Response(
            200,
            json={"access_token": "access-2", "refresh_token": "refresh-2", "token_type": "bearer"},
        )

    tokens = asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert tokens.access_token == "access-2"
    assert tokens.refresh_token == "refresh-2"
    assert tokens.token_type == "bearer"


def test_refresh_never_submits_auth_header():
    captures: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captures.append(request)
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})

    asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert "Authorization" not in captures[0].headers


def test_refresh_invalid_token_returns_session_expired_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.refresh(_client(handler), refresh_token="stale"))

    assert excinfo.value.message == "Your session has expired. Please log in again."


def test_refresh_backend_error_returns_generic_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "downstream"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert excinfo.value.message == "Authentication service error."


def test_refresh_transport_failure_returns_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert excinfo.value.message == "Unable to reach the authentication service."


def test_refresh_malformed_response_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy page</html>")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


def test_refresh_missing_token_field_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "a"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.refresh(_client(handler), refresh_token="refresh-1"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


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


def test_fetch_me_success_returns_typed_user():
    user = asyncio.run(
        auth.fetch_me(_client(lambda request: _me_response()), token="access-1")
    )

    assert user.id == "507f1f77bcf86cd799439011"
    assert user.username == "alice"
    assert user.permissions == ["read", "write"]
    assert user.active is True


def test_fetch_me_is_correct_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/me"
        return _me_response()

    asyncio.run(auth.fetch_me(_client(handler), token="access-1"))


def test_fetch_me_accepts_id_key_via_populate_by_name():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "abc", "username": "alice", "permissions": ["read"], "active": True},
        )

    user = asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert user.id == "abc"


def test_fetch_me_sends_bearer_token():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return _me_response()

    asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert seen == ["Bearer access-1"]


def test_fetch_me_without_token_sends_no_auth_header():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return _me_response()

    asyncio.run(auth.fetch_me(_client(handler)))

    assert seen == [""]


def test_fetch_me_inactive_user_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"_id": "abc", "username": "bob", "permissions": [], "active": False},
        )

    user = asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert user.active is False
    assert user.permissions == []


def test_fetch_me_permissions_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "_id": "abc",
                "username": "admin",
                "permissions": ["read", "write", "admin"],
                "active": True,
            },
        )

    user = asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert user.permissions == ["read", "write", "admin"]


def test_fetch_me_defaults_for_missing_optional_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"username": "alice"})

    user = asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert user.id is None
    assert user.permissions == []
    assert user.active is True


def test_fetch_me_401_returns_session_expired_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Not authenticated"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert excinfo.value.message == "Your session has expired. Please log in again."


def test_fetch_me_backend_error_returns_generic_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "downstream"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert excinfo.value.message == "Authentication service error."


def test_fetch_me_transport_failure_returns_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert excinfo.value.message == "Unable to reach the authentication service."


def test_fetch_me_malformed_response_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy page</html>")

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


def test_fetch_me_missing_username_field_returns_unexpected_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"_id": "abc", "permissions": []})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert excinfo.value.message == "Unexpected response from the authentication service."


def test_fetch_me_error_message_never_contains_raw_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"secret": "supersecret-sysinfo"})

    with pytest.raises(AuthError) as excinfo:
        asyncio.run(auth.fetch_me(_client(handler), token="access-1"))

    assert "supersecret-sysinfo" not in excinfo.value.message


def test_fetch_me_forwards_refresh_handler_on_401_retry():
    refresh_calls = 0
    me_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        me_calls.append(request.headers.get("Authorization", ""))
        if len(me_calls) == 1:
            return httpx.Response(401, json={"detail": "token expired"})
        return _me_response()

    async def refresh_handler():
        nonlocal refresh_calls
        refresh_calls += 1
        return "access-2"

    user = asyncio.run(
        auth.fetch_me(_client(handler), token="access-1", refresh_handler=refresh_handler)
    )

    assert user.username == "alice"
    assert me_calls == ["Bearer access-1", "Bearer access-2"]
    assert refresh_calls == 1
