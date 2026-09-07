"""Anime library operations for the anime-list-api backend."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.client import ApiClient, ApiError

ANIME_PAGE_PATH = "/animes/page"
ANIME_PAGES_PATH = "/animes/pages"

_UNAVAILABLE = "Unable to reach the anime service."
_GENERIC_ERROR = "Anime service error."
_UNEXPECTED_RESPONSE = "Unexpected response from the anime service."


class AnimeResponse(BaseModel):
    """Response record for a single anime from the backend.

    Mirrors the backend ``Anime`` schema. The wire key for the identifier is
    ``_id``, matching the existing ``UserResponse`` convention.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    name: str
    description: str
    episodes: int
    season: str
    genres: list[str] = []
    image_url: str


class AnimePageCount(BaseModel):
    """Response body for GET /animes/pages."""

    total_animes: int
    total_pages: int


class AnimeError(Exception):
    """A safe, user-facing anime service failure.

    The message never contains raw backend error bodies or credentials.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def fetch_anime_page(client: ApiClient, *, page: int) -> list[AnimeResponse]:
    """Fetch one 1-based page of anime records from the backend.

    The pagination endpoints are public, so no token or refresh handler is
    attached to the request.

    Args:
        client: The API client to use.
        page: The 1-based page number to fetch.

    Raises:
        AnimeError: If the backend is unreachable, returns a non-success
            status, or the response does not match the expected contract.
    """
    try:
        response = await client.get(ANIME_PAGE_PATH, params={"page": page})
    except ApiError as exc:
        raise _translate_api_error(exc) from exc
    return _parse_anime_page(response)


async def fetch_anime_page_count(client: ApiClient) -> AnimePageCount:
    """Fetch the total anime and total page counts from the backend.

    The pagination endpoints are public, so no token or refresh handler is
    attached to the request.

    Raises:
        AnimeError: If the backend is unreachable, returns a non-success
            status, or the response does not match the expected contract.
    """
    try:
        response = await client.get(ANIME_PAGES_PATH)
    except ApiError as exc:
        raise _translate_api_error(exc) from exc
    return _parse_anime_page_count(response)


def _translate_api_error(error: ApiError) -> AnimeError:
    if error.status_code is None:
        return AnimeError(_UNAVAILABLE)
    return AnimeError(_GENERIC_ERROR)


def _read_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise AnimeError(_UNEXPECTED_RESPONSE) from exc


def _parse_anime_page(response: httpx.Response) -> list[AnimeResponse]:
    data = _read_json(response)
    if not isinstance(data, list):
        raise AnimeError(_UNEXPECTED_RESPONSE)
    try:
        return [AnimeResponse.model_validate(item) for item in data]
    except ValidationError as exc:
        raise AnimeError(_UNEXPECTED_RESPONSE) from exc


def _parse_anime_page_count(response: httpx.Response) -> AnimePageCount:
    data = _read_json(response)
    try:
        return AnimePageCount.model_validate(data)
    except ValidationError as exc:
        raise AnimeError(_UNEXPECTED_RESPONSE) from exc
