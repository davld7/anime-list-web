"""Deterministic unit tests for the frontend anime service.

All HTTP calls use httpx.MockTransport; no external network and no real
backend.
"""

import asyncio
import json

import httpx
import pytest

from app.services import anime
from app.services.anime import AnimeError, AnimeInput
from app.services.client import ApiClient


def _client(handler) -> ApiClient:
    return ApiClient(base_url="https://api.test", transport=httpx.MockTransport(handler))


def _anime_item(_id="642a63402537c1f25e5f20fd", name="Frieren: Beyond Journey's End"):
    return {
        "_id": _id,
        "name": name,
        "description": "An elf mage seeks the meaning of life.",
        "episodes": 28,
        "season": "Otoño 2023",
        "genres": ["Aventura", "Drama", "Fantasía"],
        "image_url": "https://example.com/frieren.jpg",
    }


def test_fetch_anime_page_parses_valid_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[_anime_item(), _anime_item(_id="abc", name="86 EIGHTY-SIX")],
        )

    items = asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert len(items) == 2
    assert items[0].id == "642a63402537c1f25e5f20fd"
    assert items[0].name == "Frieren: Beyond Journey's End"
    assert items[1].id == "abc"
    assert items[1].name == "86 EIGHTY-SIX"


def test_anime_response_id_maps_from_id_alias():
    items = asyncio.run(
        anime.fetch_anime_page(
            _client(lambda request: httpx.Response(200, json=[_anime_item()])), page=1
        )
    )

    assert items[0].id == "642a63402537c1f25e5f20fd"


def test_anime_response_parses_complete_fields():
    items = asyncio.run(
        anime.fetch_anime_page(
            _client(lambda request: httpx.Response(200, json=[_anime_item()])), page=1
        )
    )

    record = items[0]
    assert record.id == "642a63402537c1f25e5f20fd"
    assert record.name == "Frieren: Beyond Journey's End"
    assert record.description == "An elf mage seeks the meaning of life."
    assert record.episodes == 28
    assert record.season == "Otoño 2023"
    assert record.genres == ["Aventura", "Drama", "Fantasía"]
    assert record.image_url == "https://example.com/frieren.jpg"


def test_fetch_anime_page_empty_list_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    items = asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert items == []


def test_fetch_anime_page_uses_animes_page_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/animes/page"
        return httpx.Response(200, json=[])

    asyncio.run(anime.fetch_anime_page(_client(handler), page=1))


def test_fetch_anime_page_sends_requested_page_param():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/animes/page"
        assert request.url.params["page"] == "2"
        return httpx.Response(200, json=[])

    asyncio.run(anime.fetch_anime_page(_client(handler), page=2))


def test_fetch_anime_page_sends_no_authorization_header():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json=[])

    asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert seen == [""]


def test_fetch_anime_page_count_parses_counts():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/animes/pages"
        return httpx.Response(200, json={"total_animes": 123, "total_pages": 13})

    count = asyncio.run(anime.fetch_anime_page_count(_client(handler)))

    assert count.total_animes == 123
    assert count.total_pages == 13


def test_fetch_anime_page_count_empty_library_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_animes": 0, "total_pages": 0})

    count = asyncio.run(anime.fetch_anime_page_count(_client(handler)))

    assert count.total_animes == 0
    assert count.total_pages == 0


def test_fetch_anime_page_count_sends_no_authorization_header():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"total_animes": 0, "total_pages": 0})

    asyncio.run(anime.fetch_anime_page_count(_client(handler)))

    assert seen == [""]


def test_non_list_anime_response_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_animes": 1})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert excinfo.value.message == "Unexpected response from the anime service."


def test_malformed_anime_item_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"_id": "abc"}])

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert excinfo.value.message == "Unexpected response from the anime service."
    assert "AnimeResponse" not in excinfo.value.message


def test_malformed_page_count_response_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_animes": "many"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page_count(_client(handler)))

    assert excinfo.value.message == "Unexpected response from the anime service."


def test_422_maps_to_safe_anime_service_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": [{"loc": ["query", "page"], "msg": "greater than or equal to 1"}]},
        )

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=0))

    assert excinfo.value.message == "Anime service error."
    assert "greater than or equal to 1" not in excinfo.value.message


def test_500_maps_to_safe_anime_service_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "internal wiring"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert excinfo.value.message == "Anime service error."


def test_connect_error_maps_to_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert excinfo.value.message == "Unable to reach the anime service."


def test_error_message_never_contains_raw_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"secret": "supersecret-db-dump"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert "supersecret-db-dump" not in excinfo.value.message


def test_malformed_json_body_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy page</html>")

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(anime.fetch_anime_page(_client(handler), page=1))

    assert excinfo.value.message == "Unexpected response from the anime service."


def _anime_input(name="Frieren: Beyond Journey's End"):
    return AnimeInput(
        name=name,
        description="An elf mage seeks the meaning of life.",
        episodes=28,
        season="Otoño 2023",
        genres=["Aventura", "Drama", "Fantasía"],
        image_url="https://example.com/frieren.jpg",
    )


async def _refresh() -> str | None:
    return None


def test_create_anime_posts_full_body_without_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/animes/"
        assert request.headers["Authorization"] == "Bearer access-1"
        body = json.loads(request.read())
        assert body == {
            "name": "Frieren: Beyond Journey's End",
            "description": "An elf mage seeks the meaning of life.",
            "episodes": 28,
            "season": "Otoño 2023",
            "genres": ["Aventura", "Drama", "Fantasía"],
            "image_url": "https://example.com/frieren.jpg",
        }
        assert "_id" not in body
        assert "id" not in body
        return httpx.Response(201, json=_anime_item())

    created = asyncio.run(
        anime.create_anime(
            _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
        )
    )

    assert created.id == "642a63402537c1f25e5f20fd"
    assert created.name == "Frieren: Beyond Journey's End"


def test_create_anime_parses_created_anime_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_anime_item(name="86 EIGHTY-SIX"))

    created = asyncio.run(
        anime.create_anime(
            _client(handler),
            anime=_anime_input(name="86 EIGHTY-SIX"),
            token="access-1",
            refresh_handler=_refresh,
        )
    )

    assert created.name == "86 EIGHTY-SIX"


def test_create_anime_malformed_response_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert excinfo.value.message == "Unexpected response from the anime service."


def test_update_anime_puts_full_body_with_id_in_path_only():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/animes/642a63402537c1f25e5f20fd"
        assert request.headers["Authorization"] == "Bearer access-1"
        body = json.loads(request.read())
        assert body["name"] == "Frieren: Beyond Journey's End"
        assert "_id" not in body
        assert "id" not in body
        return httpx.Response(200, json=_anime_item())

    updated = asyncio.run(
        anime.update_anime(
            _client(handler),
            anime_id="642a63402537c1f25e5f20fd",
            anime=_anime_input(),
            token="access-1",
            refresh_handler=_refresh,
        )
    )

    assert updated.id == "642a63402537c1f25e5f20fd"


def test_update_anime_parses_updated_anime_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_anime_item(name="Renamed"))

    updated = asyncio.run(
        anime.update_anime(
            _client(handler),
            anime_id="642a63402537c1f25e5f20fd",
            anime=_anime_input(),
            token="access-1",
            refresh_handler=_refresh,
        )
    )

    assert updated.name == "Renamed"


def test_update_anime_malformed_response_returns_safe_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.update_anime(
                _client(handler),
                anime_id="642a63402537c1f25e5f20fd",
                anime=_anime_input(),
                token="access-1",
                refresh_handler=_refresh,
            )
        )

    assert excinfo.value.message == "Unexpected response from the anime service."


def test_delete_anime_returns_none_on_204_no_body_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/animes/642a63402537c1f25e5f20fd"
        assert request.headers["Authorization"] == "Bearer access-1"
        return httpx.Response(204)

    result = asyncio.run(
        anime.delete_anime(
            _client(handler),
            anime_id="642a63402537c1f25e5f20fd",
            token="access-1",
            refresh_handler=_refresh,
        )
    )

    assert result is None


def test_mutation_refresh_flow_retries_once_with_rotated_token():
    calls: list[str] = []
    refresh_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["Authorization"])
        if len(calls) == 1:
            return httpx.Response(401, json={"detail": "token expired"})
        return httpx.Response(201, json=_anime_item())

    async def refresh():
        refresh_calls.append("refresh")
        return "access-rotated"

    created = asyncio.run(
        anime.create_anime(
            _client(handler), anime=_anime_input(), token="access-1", refresh_handler=refresh
        )
    )

    assert created.name == "Frieren: Beyond Journey's End"
    assert calls == ["Bearer access-1", "Bearer access-rotated"]
    assert refresh_calls == ["refresh"]


def test_mutation_401_maps_to_session_expired_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "token expired"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert excinfo.value.message == "Your session has expired. Please log in again."


def test_mutation_403_maps_to_permission_denied_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Permission 'write' required"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert excinfo.value.message == "You do not have permission to perform this action."


def test_mutation_404_maps_to_not_found_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Anime not found."})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.delete_anime(
                _client(handler),
                anime_id="642a63402537c1f25e5f20fd",
                token="access-1",
                refresh_handler=_refresh,
            )
        )

    assert excinfo.value.message == "Anime not found."


def test_mutation_409_maps_to_already_exists_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Anime already exists."})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert excinfo.value.message == "Anime already exists."


def test_mutation_422_maps_to_generic_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"loc": ["body", "name"], "msg": "too short"}]})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.update_anime(
                _client(handler),
                anime_id="642a63402537c1f25e5f20fd",
                anime=_anime_input(name="x"),
                token="access-1",
                refresh_handler=_refresh,
            )
        )

    assert excinfo.value.message == "Anime service error."
    assert "too short" not in excinfo.value.message


def test_mutation_connect_error_maps_to_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert excinfo.value.message == "Unable to reach the anime service."


def test_mutation_error_never_leaks_raw_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"secret": "supersecret-role-rule"})

    with pytest.raises(AnimeError) as excinfo:
        asyncio.run(
            anime.create_anime(
                _client(handler), anime=_anime_input(), token="access-1", refresh_handler=_refresh
            )
        )

    assert "supersecret-role-rule" not in excinfo.value.message
