"""Deterministic unit tests for the anime library State.

The LibraryState is instantiated directly (allowed under pytest) with
``_make_client`` patched to a MockTransport-backed client. No network, no real
backend.
"""

import asyncio
from unittest.mock import patch

import httpx

from app.services.client import ApiClient
from app.state.library import LibraryState


def _client(handler) -> ApiClient:
    return ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))


def _anime_item(name="Frieren: Beyond Journey's End"):
    return {
        "_id": "642a63402537c1f25e5f20fd",
        "name": name,
        "description": "An elf mage seeks the meaning of life.",
        "episodes": 28,
        "season": "Otoño 2023",
        "genres": ["Aventura", "Drama", "Fantasía"],
        "image_url": "https://example.com/frieren.jpg",
    }


def _success_handler(seen=None):
    """Handler serving a two-page library with one anime per page."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        assert request.url.path == "/animes/page"
        if seen is not None:
            seen.append(request.url.params.get("page"))
        return httpx.Response(200, json=[_anime_item()])

    return handler


def _empty_handler():
    """Handler serving an empty library (0 total, 0 pages)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 0, "total_pages": 0})
        assert request.url.path == "/animes/page"
        return httpx.Response(200, json=[])

    return handler


async def _load(state: LibraryState, handler):
    with patch.object(LibraryState, "_make_client", return_value=_client(handler)):
        return await state.load_page()


async def _next(state: LibraryState, handler):
    with patch.object(LibraryState, "_make_client", return_value=_client(handler)):
        return await state.next_page()


async def _prev(state: LibraryState, handler):
    with patch.object(LibraryState, "_make_client", return_value=_client(handler)):
        return await state.prev_page()


def test_successful_load_populates_library():
    state = LibraryState()
    asyncio.run(_load(state, _success_handler()))

    assert len(state.animes) == 1
    assert state.animes[0].name == "Frieren: Beyond Journey's End"
    assert state.animes[0].genres == ["Aventura", "Drama", "Fantasía"]
    assert state.total_animes == 20
    assert state.total_pages == 2
    assert state.current_page == 1
    assert state.loading is False
    assert state.error_message == ""


def test_empty_library_loads_cleanly():
    state = LibraryState()
    asyncio.run(_load(state, _empty_handler()))

    assert state.animes == []
    assert state.total_animes == 0
    assert state.total_pages == 0
    assert state.current_page == 1
    assert state.loading is False
    assert state.error_message == ""


def test_api_failure_sets_safe_error_and_keeps_data():
    state = LibraryState()
    asyncio.run(_load(state, _success_handler()))
    assert len(state.animes) == 1

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "internal wiring"})

    asyncio.run(_load(state, failing_handler))

    assert state.error_message == "Anime service error."
    assert state.loading is False
    assert len(state.animes) == 1
    assert state.animes[0].name == "Frieren: Beyond Journey's End"


def test_failure_then_retry_clears_error_and_populates():
    fail = True

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500, json={"detail": "boom"})
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        return httpx.Response(200, json=[_anime_item()])

    state = LibraryState()
    asyncio.run(_load(state, handler))
    assert state.error_message == "Anime service error."
    assert state.animes == []

    fail = False
    asyncio.run(_load(state, handler))

    assert state.error_message == ""
    assert len(state.animes) == 1
    assert state.current_page == 1
    assert state.loading is False


def test_next_page_moves_forward_and_fetches_page_two():
    seen: list[str] = []
    state = LibraryState()
    asyncio.run(_load(state, _success_handler(seen=seen)))
    assert seen == ["1"]

    asyncio.run(_next(state, _success_handler(seen=seen)))

    assert state.current_page == 2
    assert seen == ["1", "2"]
    assert len(state.animes) == 1
    assert state.loading is False


def test_prev_page_moves_back_and_fetches_page_one():
    seen: list[str] = []
    state = LibraryState()
    asyncio.run(_load(state, _success_handler(seen=seen)))
    asyncio.run(_next(state, _success_handler(seen=seen)))
    assert state.current_page == 2

    asyncio.run(_prev(state, _success_handler(seen=seen)))

    assert state.current_page == 1
    assert seen == ["1", "2", "1"]


def test_prev_at_first_page_does_nothing_and_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url.path}")

    state = LibraryState()
    asyncio.run(_prev(state, handler))

    assert state.current_page == 1


def test_next_at_last_page_does_nothing_and_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url.path}")

    state = LibraryState()
    state.current_page = 2
    state.total_pages = 2

    asyncio.run(_next(state, handler))

    assert state.current_page == 2


def test_pagination_is_noop_with_zero_total_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url.path}")

    state = LibraryState()
    state.total_pages = 0

    asyncio.run(_next(state, handler))
    asyncio.run(_prev(state, handler))

    assert state.current_page == 1


def test_loading_resets_to_false_after_success():
    state = LibraryState()
    asyncio.run(_load(state, _success_handler()))

    assert state.loading is False


def test_loading_resets_to_false_after_failure():
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    state = LibraryState()
    asyncio.run(_load(state, failing_handler))

    assert state.loading is False
    assert state.error_message == "Unable to reach the anime service."


def test_transport_failure_keeps_existing_data():
    state = LibraryState()
    asyncio.run(_load(state, _success_handler()))

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    asyncio.run(_load(state, failing_handler))

    assert state.error_message == "Unable to reach the anime service."
    assert len(state.animes) == 1
    assert state.loading is False
