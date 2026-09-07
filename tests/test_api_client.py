"""Deterministic unit tests for the API client.

All HTTP calls are mocked with httpx.MockTransport; no external network
requests are made and no production services are contacted.
"""

import asyncio

import httpx
import pytest

from app.config import DEFAULT_API_BASE_URL, get_api_base_url
from app.services.client import ApiClient, ApiError


def test_successful_request_returns_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/items"
        return httpx.Response(200, json={"items": []})

    client = ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))

    response = asyncio.run(client.get("/api/v1/items"))

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_http_error_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Item not found"})

    client = ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))

    with pytest.raises(ApiError) as excinfo:
        asyncio.run(client.get("/api/v1/items/1"))

    error = excinfo.value
    assert error.status_code == 404
    assert "Item not found" in error.response_body


def test_transport_failure_raises_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))

    with pytest.raises(ApiError, match="Could not reach the backend"):
        asyncio.run(client.get("/api/v1/items"))


def test_base_url_env_default(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    assert get_api_base_url() == DEFAULT_API_BASE_URL


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://api.staging.test")
    assert get_api_base_url() == "https://api.staging.test"


def test_client_uses_configured_base_url(monkeypatch):
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={})

    monkeypatch.setenv("API_BASE_URL", "https://env-config.test")
    client = ApiClient(transport=httpx.MockTransport(handler))

    asyncio.run(client.get("/api/v1/items"))

    assert client.base_url == "https://env-config.test"
    assert seen_urls == ["https://env-config.test/api/v1/items"]


def test_client_explicit_base_url_overrides_environment(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://env-config.test")
    client = ApiClient(
        base_url="https://explicit.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    assert client.base_url == "https://explicit.test"


def test_request_with_token_sets_authorization_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token123"
        return httpx.Response(200, json={})

    client = ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))

    asyncio.run(client.get("/api/v1/items", token="token123"))


def test_request_without_token_has_no_authorization_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={})

    client = ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))

    asyncio.run(client.get("/api/v1/items"))
