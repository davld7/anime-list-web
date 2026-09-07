"""Deterministic unit tests for the anime library State.

The LibraryState is instantiated directly (allowed under pytest) with
``_make_client`` patched to a MockTransport-backed client. No network, no real
backend.
"""

import asyncio
from unittest.mock import patch

import httpx
import reflex as rx

from app.services.client import ApiClient
from app.state.auth import AuthState
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


def _make_session():
    """Create a wired state tree so LibraryState can reach the live AuthState.

    The LibraryState event handlers cross states via the root for the access
    token and refresh handler, mirroring how the app wires the session.
    """
    root = rx.State()
    auth = root.get_substate([AuthState.get_name()])
    lib = root.get_substate([LibraryState.get_name()])
    return lib, auth


def _rotating_refresh(rotated="access-rotated"):
    """Bound-style AuthState._refresh replacement for deterministic tests."""

    async def fake_refresh(self):
        self._access_token = rotated
        self._refresh_token = "refresh-rotated"
        return rotated

    return fake_refresh


def _edit_handler(seen=None):
    """Handler serving mutation operations plus the post-mutation reload."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/animes/":
            return httpx.Response(201, json=_anime_item())
        if request.method == "PUT" and request.url.path.endswith(
            "/animes/642a63402537c1f25e5f20fd"
        ):
            return httpx.Response(200, json=_anime_item(name="Renamed"))
        if request.method == "DELETE" and request.url.path == "/animes/642a63402537c1f25e5f20fd":
            return httpx.Response(204)
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        assert request.url.path == "/animes/page"
        if seen is not None:
            seen.append(request.url.params.get("page"))
        return httpx.Response(200, json=[_anime_item()])

    return handler


def _wrap_handler(handler):
    return patch.object(LibraryState, "_make_client", return_value=_client(handler))


def _fill_create_form(lib: LibraryState) -> None:
    lib.name_input = "Frieren: Beyond Journey's End"
    lib.description_input = "An elf mage seeks the meaning of life."
    lib.episodes_input = "28"
    lib.season_input = "Otoño 2023"
    lib.genres_input = "Aventura, Drama, Fantasía"
    lib.image_url_input = "https://example.com/frieren.jpg"


def test_create_anime_posts_form_and_reloads_library():
    lib, auth = _make_session()
    auth._access_token = "access-1"
    _fill_create_form(lib)

    with _wrap_handler(_edit_handler()):
        asyncio.run(lib.create_anime())

    assert lib.form_open is False
    assert lib.editing_anime_id is None
    assert lib.name_input == ""
    assert lib.form_error_message == ""
    assert len(lib.animes) == 1
    assert lib.animes[0].name == "Frieren: Beyond Journey's End"


def test_create_anime_sends_authorization_header():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        if request.url.path == "/animes/page":
            return httpx.Response(200, json=[])
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(201, json=_anime_item())

    lib, auth = _make_session()
    auth._access_token = "access-1"
    _fill_create_form(lib)

    with _wrap_handler(handler):
        asyncio.run(lib.create_anime())

    assert "Bearer access-1" in seen


def test_create_anime_failure_keeps_form_open_with_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Permission 'write' required"})

    lib, auth = _make_session()
    auth._access_token = "access-1"
    lib.open_create_form()
    _fill_create_form(lib)

    with _wrap_handler(handler):
        asyncio.run(lib.create_anime())

    assert lib.form_open is True
    assert lib.form_error_message == "You do not have permission to perform this action."
    assert lib.name_input == "Frieren: Beyond Journey's End"
    assert lib.form_submitting is False
    assert lib.animes == []


def test_create_anime_rejects_invalid_episodes_without_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    lib, auth = _make_session()
    auth._access_token = "access-1"
    lib.open_create_form()
    _fill_create_form(lib)
    lib.episodes_input = "many"

    with _wrap_handler(handler):
        asyncio.run(lib.create_anime())

    assert lib.form_open is True
    assert lib.form_error_message == "Please enter a valid number of episodes."
    assert lib.animes == []


def test_open_edit_form_populates_fields_from_library():
    lib, auth = _make_session()
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())

    lib.open_edit_form("642a63402537c1f25e5f20fd")

    assert lib.editing_anime_id == "642a63402537c1f25e5f20fd"
    assert lib.name_input == "Frieren: Beyond Journey's End"
    assert lib.episodes_input == "28"
    assert lib.season_input == "Otoño 2023"
    assert lib.genres_input == "Aventura, Drama, Fantasía"
    assert lib.form_open is True
    assert lib.form_error_message == ""


def test_open_edit_form_unknown_id_is_noop():
    lib, auth = _make_session()

    lib.open_edit_form("does-not-exist")

    assert lib.form_open is False
    assert lib.editing_anime_id is None


def test_update_anime_puts_form_and_reloads():
    lib, auth = _make_session()
    auth._access_token = "access-1"
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())
    lib.open_edit_form("642a63402537c1f25e5f20fd")
    lib.name_input = "Renamed"

    with _wrap_handler(_edit_handler()):
        asyncio.run(lib.update_anime())

    assert lib.form_open is False
    assert lib.editing_anime_id is None
    assert lib.form_error_message == ""
    assert len(lib.animes) == 1


def test_update_anime_without_open_edit_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url.path}")

    lib, auth = _make_session()
    auth._access_token = "access-1"

    with _wrap_handler(handler):
        asyncio.run(lib.update_anime())

    assert lib.editing_anime_id is None


def test_update_anime_failure_keeps_form_values():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Anime already exists."})

    lib, auth = _make_session()
    auth._access_token = "access-1"
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())
    lib.open_edit_form("642a63402537c1f25e5f20fd")
    lib.name_input = "Duplicate"

    with _wrap_handler(handler):
        asyncio.run(lib.update_anime())

    assert lib.form_open is True
    assert lib.editing_anime_id == "642a63402537c1f25e5f20fd"
    assert lib.name_input == "Duplicate"
    assert lib.form_error_message == "Anime already exists."
    assert lib.form_submitting is False


def test_mutation_401_triggers_single_refresh_retry_and_stores_rotated_token():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls.append(request.headers["Authorization"])
            if len(calls) == 1:
                return httpx.Response(401, json={"detail": "token expired"})
            return httpx.Response(201, json=_anime_item())
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        return httpx.Response(200, json=[_anime_item()])

    lib, auth = _make_session()
    auth._access_token = "access-1"
    auth._refresh_token = "refresh-1"
    lib.open_create_form()
    _fill_create_form(lib)

    with _wrap_handler(handler), patch.object(AuthState, "_refresh", new=_rotating_refresh()):
        asyncio.run(lib.create_anime())

    assert calls == ["Bearer access-1", "Bearer access-rotated"]
    assert auth._access_token == "access-rotated"
    assert auth._refresh_token == "refresh-rotated"
    assert len(lib.animes) == 1


def test_request_delete_opens_confirmation_with_name():
    lib, auth = _make_session()
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())

    lib.request_delete("642a63402537c1f25e5f20fd")

    assert lib.delete_confirmation_open is True
    assert lib.deleting_anime_id == "642a63402537c1f25e5f20fd"
    assert lib.deleting_anime_name == "Frieren: Beyond Journey's End"


def test_request_delete_unknown_id_is_noop():
    lib, auth = _make_session()

    lib.request_delete("does-not-exist")

    assert lib.delete_confirmation_open is False


def test_cancel_delete_resets_confirmation_state():
    lib, auth = _make_session()
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())
    lib.request_delete("642a63402537c1f25e5f20fd")

    lib.cancel_delete()

    assert lib.delete_confirmation_open is False
    assert lib.deleting_anime_id is None
    assert lib.deleting_anime_name == ""


def test_delete_anime_removes_and_reloads_library():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 20, "total_pages": 2})
        return httpx.Response(200, json=[_anime_item()])

    lib, auth = _make_session()
    auth._access_token = "access-1"
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())
    lib.request_delete("642a63402537c1f25e5f20fd")

    with _wrap_handler(handler):
        asyncio.run(lib.delete_anime("642a63402537c1f25e5f20fd"))

    assert lib.delete_confirmation_open is False
    assert lib.deleting_anime_id is None
    assert lib.delete_error_message == ""
    assert len(lib.animes) == 1


def test_delete_anime_failure_keeps_confirmation_open():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Permission 'admin' required"})

    lib, auth = _make_session()
    auth._access_token = "access-1"
    with _wrap_handler(_success_handler()):
        asyncio.run(lib.load_page())
    lib.request_delete("642a63402537c1f25e5f20fd")

    with _wrap_handler(handler):
        asyncio.run(lib.delete_anime("642a63402537c1f25e5f20fd"))

    assert lib.delete_confirmation_open is True
    assert lib.deleting_anime_id == "642a63402537c1f25e5f20fd"
    assert lib.delete_error_message == "You do not have permission to perform this action."
    assert lib.delete_submitting is False
    assert len(lib.animes) == 1


def test_delete_last_item_on_last_page_resets_to_empty_library():
    pages_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 0, "total_pages": 0})
        pages_seen.append(request.url.params.get("page"))
        return httpx.Response(200, json=[])

    lib, auth = _make_session()
    auth._access_token = "access-1"
    lib.total_pages = 1

    with _wrap_handler(handler):
        asyncio.run(lib.delete_anime("642a63402537c1f25e5f20fd"))

    assert pages_seen == ["1"]
    assert lib.current_page == 1
    assert lib.total_pages == 0
    assert lib.total_animes == 0
    assert lib.animes == []
    assert lib.delete_confirmation_open is False


def test_delete_collapses_count_clamps_and_reloads_out_of_range_page():
    pages_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/animes/pages":
            return httpx.Response(200, json={"total_animes": 10, "total_pages": 1})
        pages_seen.append(request.url.params.get("page"))
        return httpx.Response(200, json=[_anime_item()])

    lib, auth = _make_session()
    auth._access_token = "access-1"
    lib.current_page = 2
    lib.total_pages = 2
    lib.delete_confirmation_open = True

    with _wrap_handler(handler):
        asyncio.run(lib.delete_anime("642a63402537c1f25e5f20fd"))

    assert lib.delete_confirmation_open is False
    assert pages_seen == ["2", "1"]
    assert lib.current_page == 1
    assert lib.total_pages == 1


def test_set_form_open_false_resets_form():
    lib, auth = _make_session()
    lib.form_open = True
    lib.name_input = "unsubmitted"

    lib.set_form_open(False)

    assert lib.form_open is False
    assert lib.name_input == ""
    assert lib.editing_anime_id is None
