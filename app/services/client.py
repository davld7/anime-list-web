"""Centralized async HTTP client for the anime-list-api backend."""

from typing import Any

import httpx

from app.config import get_api_base_url

DEFAULT_TIMEOUT = 10.0


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
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request to the backend and return the response.

        Raises:
            ApiError: If the request could not be sent or the backend returned
                a non-success HTTP status.
        """
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method, path, params=params, json=json, **kwargs
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
        self, path: str, *, params: dict[str, Any] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a GET request to the backend."""
        return await self.request("GET", path, params=params, **kwargs)

    async def post(
        self, path: str, *, json: Any = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a POST request to the backend."""
        return await self.request("POST", path, json=json, **kwargs)
