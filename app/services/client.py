"""Centralized async HTTP client for the anime-list-api backend."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_api_base_url

DEFAULT_TIMEOUT = 10.0

RefreshHandler = Callable[[], Awaitable[str | None]]
"""An async callback that performs a token refresh.

Returns the new access token on success, or ``None`` if refresh failed.
"""


class ApiError(Exception):
    """An error raised by the API client."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
        url: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.url = url


class ApiClient:
    """Minimal async HTTP client for the backend API."""

    def __init__(
        self,
        *,
        base_url: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or get_api_base_url()
        self.timeout = timeout
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        token: str | None = None,
        refresh_handler: RefreshHandler | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request to the backend and return the response.

        Args:
            token: Optional bearer token used to authenticate the request.
                When provided it is sent as ``Authorization: Bearer <token>``.
            refresh_handler: Optional async callable (``() -> str | None``) that
                performs a token refresh and returns the new access token, or
                ``None`` if refresh failed. When provided together with ``token``,
                a ``401`` from an authenticated request triggers at most one refresh
                followed by at most one retry with the new token.

        Raises:
            ApiError: If the request could not be sent or the backend returned
                a non-success HTTP status.
        """
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        base_headers = dict(kwargs.pop("headers", {}))
        attempt = 0
        while True:
            headers = dict(base_headers)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                return await self._send(
                    method, path, params=params, json=json, headers=headers, url=url, **kwargs
                )
            except ApiError as exc:
                if (
                    exc.status_code == 401
                    and token
                    and refresh_handler is not None
                    and attempt == 0
                ):
                    attempt = 1
                    new_token = await refresh_handler()
                    if new_token is None:
                        raise exc
                    token = new_token
                    continue
                raise

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: Any,
        headers: dict[str, str],
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform a single HTTP request, translating failures to ``ApiError``."""
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=headers,
                    **kwargs,
                )
        except httpx.TransportError as exc:
            raise ApiError(
                f"Could not reach the backend at {url}: {exc}",
                url=url,
            ) from exc

        if not response.is_success:
            raise ApiError(
                f"Backend request failed with status {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
                url=str(response.url),
            )
        return response

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        token: str | None = None,
        refresh_handler: RefreshHandler | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a GET request to the backend."""
        return await self.request(
            "GET", path, params=params, token=token, refresh_handler=refresh_handler, **kwargs
        )

    async def post(
        self,
        path: str,
        *,
        json: Any = None,
        token: str | None = None,
        refresh_handler: RefreshHandler | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a POST request to the backend."""
        return await self.request(
            "POST", path, json=json, token=token, refresh_handler=refresh_handler, **kwargs
        )

    async def put(
        self,
        path: str,
        *,
        json: Any = None,
        token: str | None = None,
        refresh_handler: RefreshHandler | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a PUT request to the backend."""
        return await self.request(
            "PUT", path, json=json, token=token, refresh_handler=refresh_handler, **kwargs
        )

    async def delete(
        self,
        path: str,
        *,
        token: str | None = None,
        refresh_handler: RefreshHandler | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a DELETE request to the backend.

        The backend responds ``204 No Content``; the response body is left for
        the caller to handle (it is never JSON-parsed here).
        """
        return await self.request(
            "DELETE", path, token=token, refresh_handler=refresh_handler, **kwargs
        )
