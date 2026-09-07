"""Per-session anime library state for the anime-list-web frontend."""

import asyncio

import reflex as rx

from app.services import anime as anime_service
from app.services.anime import AnimeError, AnimeResponse
from app.services.client import ApiClient


class LibraryState(rx.State):
    """Authenticated anime library state.

    Holds the current page of anime records and its pagination metadata. The
    anime read endpoints are public on the backend, so no authentication
    concerns live here; route protection is handled by
    ``AuthState.guard_authenticated``.
    """

    animes: list[AnimeResponse] = []
    current_page: int = 1
    total_pages: int = 0
    total_animes: int = 0
    loading: bool = False
    error_message: str = ""

    @classmethod
    def _make_client(cls) -> ApiClient:
        """Build the API client used by the library handlers."""
        return ApiClient()

    @rx.event
    async def load_page(self) -> None:
        """Load the current page of anime and refresh pagination metadata.

        On failure a safe error message is recorded and the previously loaded
        data is kept rather than destroyed.
        """
        self.loading = True
        self.error_message = ""
        try:
            client = self._make_client()
            count, page = await asyncio.gather(
                anime_service.fetch_anime_page_count(client),
                anime_service.fetch_anime_page(client, page=self.current_page),
            )
        except AnimeError as exc:
            self.error_message = exc.message
            return
        finally:
            self.loading = False
        self.animes = page
        self.total_animes = count.total_animes
        self.total_pages = count.total_pages

    @rx.event
    async def next_page(self) -> None:
        """Move to the next page, if any, and load it."""
        if self.current_page >= self.total_pages:
            return
        self.current_page += 1
        await self.load_page()

    @rx.event
    async def prev_page(self) -> None:
        """Move to the previous page, if any, and load it."""
        if self.current_page <= 1:
            return
        self.current_page -= 1
        await self.load_page()
