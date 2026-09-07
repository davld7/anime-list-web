"""Anime library operations for the anime-list-api backend."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.client import ApiClient, ApiError, RefreshHandler

ANIME_PAGE_PATH = "/animes/page"
ANIME_PAGES_PATH = "/animes/pages"
ANIMES_PATH = "/animes/"
ANIME_ITEM_PATH = "/animes/{anime_id}"

_UNAVAILABLE = "Unable to reach the anime service."
_GENERIC_ERROR = "Anime service error."
_UNEXPECTED_RESPONSE = "Unexpected response from the anime service."
_SESSION_EXPIRED = "Your session has expired. Please log in again."
_PERMISSION_DENIED = "You do not have permission to perform this action."
_NOT_FOUND = "Anime not found."
_ALREADY_EXISTS = "Anime already exists."


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


class AnimeInput(BaseModel):
    """Request body for POST /animes/ and PUT /animes/{id}.

    Mirrors the backend ``AnimeBase`` schema. The identifier is never part of
    the request body; it is conveyed only through the URL for update/delete.
    """

    name: str
    description: str
    episodes: int
    season: str
    genres: list[str] = []
    image_url: str


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


async def create_anime(
    client: ApiClient,
    *,
    anime: AnimeInput,
    token: str,
    refresh_handler: RefreshHandler,
) -> AnimeResponse:
    """Create an anime via POST /animes/.

    Requires an authenticated session with the ``write`` permission. The
    access token and refresh handler come from ``AuthState``; a ``401``
    triggers the existing refresh-once/retry-once flow.

    Raises:
        AnimeError: If the backend is unreachable, rejects the request, or the
            response does not match the expected contract.
    """
    try:
        response = await client.post(
            ANIMES_PATH,
            json=anime.model_dump(),
            token=token,
            refresh_handler=refresh_handler,
        )
    except ApiError as exc:
        raise _translate_mutation_api_error(exc) from exc
    return _parse_anime_item(response)


async def update_anime(
    client: ApiClient,
    *,
    anime_id: str,
    anime: AnimeInput,
    token: str,
    refresh_handler: RefreshHandler,
) -> AnimeResponse:
    """Replace an anime via PUT /animes/{anime_id}.

    ``PUT`` is a full replacement; ``anime`` must contain every field. The
    identifier is used only as the path parameter and is never part of the
    request body.

    Requires an authenticated session with the ``write`` permission.

    Raises:
        AnimeError: If the backend is unreachable, rejects the request, or the
            response does not match the expected contract.
    """
    try:
        response = await client.put(
            ANIME_ITEM_PATH.format(anime_id=anime_id),
            json=anime.model_dump(),
            token=token,
            refresh_handler=refresh_handler,
        )
    except ApiError as exc:
        raise _translate_mutation_api_error(exc) from exc
    return _parse_anime_item(response)


async def delete_anime(
    client: ApiClient,
    *,
    anime_id: str,
    token: str,
    refresh_handler: RefreshHandler,
) -> None:
    """Delete an anime via DELETE /animes/{anime_id}.

    Requires an authenticated session with the ``admin`` permission. Returns
    ``None`` on a successful ``204 No Content``; the response body is never
    parsed.

    Raises:
        AnimeError: If the backend is unreachable, rejects the request, or the
            deletion could not be confirmed.
    """
    try:
        await client.delete(
            ANIME_ITEM_PATH.format(anime_id=anime_id),
            token=token,
            refresh_handler=refresh_handler,
        )
    except ApiError as exc:
        raise _translate_mutation_api_error(exc) from exc


def _translate_api_error(error: ApiError) -> AnimeError:
    if error.status_code is None:
        return AnimeError(_UNAVAILABLE)
    return AnimeError(_GENERIC_ERROR)


def _translate_mutation_api_error(error: ApiError) -> AnimeError:
    if error.status_code is None:
        return AnimeError(_UNAVAILABLE)
    if error.status_code == 401:
        return AnimeError(_SESSION_EXPIRED)
    if error.status_code == 403:
        return AnimeError(_PERMISSION_DENIED)
    if error.status_code == 404:
        return AnimeError(_NOT_FOUND)
    if error.status_code == 409:
        return AnimeError(_ALREADY_EXISTS)
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


def _parse_anime_item(response: httpx.Response) -> AnimeResponse:
    data = _read_json(response)
    try:
        return AnimeResponse.model_validate(data)
    except ValidationError as exc:
        raise AnimeError(_UNEXPECTED_RESPONSE) from exc


def _parse_anime_page_count(response: httpx.Response) -> AnimePageCount:
    data = _read_json(response)
    try:
        return AnimePageCount.model_validate(data)
    except ValidationError as exc:
        raise AnimeError(_UNEXPECTED_RESPONSE) from exc
