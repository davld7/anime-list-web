"""Per-session anime library state for the anime-list-web frontend."""

import asyncio

import reflex as rx

from app.services import anime as anime_service
from app.services.anime import AnimeError, AnimeInput, AnimeResponse
from app.services.client import ApiClient
from app.state.auth import AuthState


class LibraryState(rx.State):
    """Authenticated anime library state.

    Holds the current page of anime records, its pagination metadata, and the
    create/edit/delete form state. The anime read endpoints are public on the
    backend, so no authentication concerns live there; mutations use the
    access token and refresh handler from ``AuthState`` (server-side only).
    Route protection is handled by ``AuthState.guard_authenticated``.
    """

    animes: list[AnimeResponse] = []
    current_page: int = 1
    total_pages: int = 0
    total_animes: int = 0
    loading: bool = False
    error_message: str = ""

    form_open: bool = False
    editing_anime_id: str | None = None
    name_input: str = ""
    description_input: str = ""
    episodes_input: str = ""
    season_input: str = ""
    genres_input: str = ""
    image_url_input: str = ""
    form_submitting: bool = False
    form_error_message: str = ""

    delete_confirmation_open: bool = False
    deleting_anime_id: str | None = None
    deleting_anime_name: str = ""
    delete_submitting: bool = False
    delete_error_message: str = ""

    @classmethod
    def _make_client(cls) -> ApiClient:
        """Build the API client used by the library handlers."""
        return ApiClient()

    def _get_auth_state(self) -> AuthState:
        """Return the session's AuthState instance for token/refresh access."""
        return self._get_root_state().get_substate([AuthState.get_name()])

    # ------------------------------------------------------------------
    # Read / pagination
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Form state
    # ------------------------------------------------------------------

    @rx.event
    def set_name_input(self, value: str) -> None:
        """Update the name form field."""
        self.name_input = value

    @rx.event
    def set_description_input(self, value: str) -> None:
        """Update the description form field."""
        self.description_input = value

    @rx.event
    def set_episodes_input(self, value: str) -> None:
        """Update the episodes form field."""
        self.episodes_input = value

    @rx.event
    def set_season_input(self, value: str) -> None:
        """Update the season form field."""
        self.season_input = value

    @rx.event
    def set_genres_input(self, value: str) -> None:
        """Update the genres form field (comma-separated text)."""
        self.genres_input = value

    @rx.event
    def set_image_url_input(self, value: str) -> None:
        """Update the image URL form field."""
        self.image_url_input = value

    @rx.event
    def open_create_form(self) -> None:
        """Open the empty create form dialog."""
        self._reset_form()
        self.form_open = True

    @rx.event
    def open_edit_form(self, anime_id: str) -> None:
        """Open the edit form dialog pre-populated from the selected anime."""
        anime = next((a for a in self.animes if a.id == anime_id), None)
        if anime is None:
            return
        self.editing_anime_id = anime_id
        self.name_input = anime.name
        self.description_input = anime.description
        self.episodes_input = str(anime.episodes)
        self.season_input = anime.season
        self.genres_input = ", ".join(anime.genres)
        self.image_url_input = anime.image_url
        self.form_error_message = ""
        self.form_open = True

    @rx.event
    def set_form_open(self, value: bool) -> None:
        """Honour dialog close requests (X, overlay, Escape)."""
        self.form_open = value
        if not value:
            self._reset_form()

    @rx.event
    def close_form(self) -> None:
        """Close and reset the form dialog."""
        self.form_open = False
        self._reset_form()

    # ------------------------------------------------------------------
    # Delete confirmation state
    # ------------------------------------------------------------------

    @rx.event
    def request_delete(self, anime_id: str) -> None:
        """Open the delete confirmation dialog for the given anime."""
        anime = next((a for a in self.animes if a.id == anime_id), None)
        if anime is None:
            return
        self.deleting_anime_id = anime_id
        self.deleting_anime_name = anime.name
        self.delete_error_message = ""
        self.delete_confirmation_open = True

    @rx.event
    def set_delete_confirmation_open(self, value: bool) -> None:
        """Honour dialog close requests for the delete confirmation."""
        self.delete_confirmation_open = value
        if not value:
            self._reset_delete()

    @rx.event
    def cancel_delete(self) -> None:
        """Cancel the pending delete operation."""
        self.delete_confirmation_open = False
        self._reset_delete()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @rx.event
    async def create_anime(self) -> None:
        """Submit the form as a new anime via POST /animes/.

        On success the form closes and the library reloads. On failure the
        dialog stays open with a safe error message.
        """
        anime = self._build_anime_input()
        if anime is None:
            return
        self.form_submitting = True
        self.form_error_message = ""
        try:
            auth = self._get_auth_state()
            await anime_service.create_anime(
                self._make_client(),
                anime=anime,
                token=auth._access_token,
                refresh_handler=auth._refresh,
            )
        except AnimeError as exc:
            self.form_error_message = exc.message
            return
        finally:
            self.form_submitting = False
        self._close_form_after_success()
        await self.load_page()

    @rx.event
    async def update_anime(self) -> None:
        """Replace the edited anime via PUT /animes/{id}.

        ``PUT`` is a full replacement, so every ``AnimeInput`` field is sent;
        the id is used only as the path parameter.
        """
        if self.editing_anime_id is None:
            return
        anime = self._build_anime_input()
        if anime is None:
            return
        self.form_submitting = True
        self.form_error_message = ""
        try:
            auth = self._get_auth_state()
            await anime_service.update_anime(
                self._make_client(),
                anime_id=self.editing_anime_id,
                anime=anime,
                token=auth._access_token,
                refresh_handler=auth._refresh,
            )
        except AnimeError as exc:
            self.form_error_message = exc.message
            return
        finally:
            self.form_submitting = False
        self._close_form_after_success()
        await self.load_page()

    @rx.event
    async def delete_anime(self, anime_id: str) -> None:
        """Confirm and execute the pending deletion via DELETE /animes/{id}.

        On success the confirmation closes and the library reloads, clamping
        the current page if it went out of range. On failure the confirmation
        stays open with a safe error and the library data is untouched.
        """
        self.delete_submitting = True
        self.delete_error_message = ""
        try:
            auth = self._get_auth_state()
            await anime_service.delete_anime(
                self._make_client(),
                anime_id=anime_id,
                token=auth._access_token,
                refresh_handler=auth._refresh,
            )
        except AnimeError as exc:
            self.delete_error_message = exc.message
            return
        finally:
            self.delete_submitting = False
        self.delete_confirmation_open = False
        self._reset_delete()
        await self._refresh_after_delete()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_anime_input(self) -> AnimeInput | None:
        """Build an ``AnimeInput`` from the current form values.

        Only the numeric episodes field is validated frontend-side (text input);
        the backend remains the authority for the rest.
        """
        try:
            episodes = int(self.episodes_input.strip())
        except ValueError:
            self.form_error_message = "Please enter a valid number of episodes."
            return None
        genres = [genre.strip() for genre in self.genres_input.split(",") if genre.strip()]
        return AnimeInput(
            name=self.name_input,
            description=self.description_input,
            episodes=episodes,
            season=self.season_input,
            genres=genres,
            image_url=self.image_url_input,
        )

    def _close_form_after_success(self) -> None:
        """Close and fully reset the form after a successful mutation."""
        self.form_open = False
        self._reset_form()

    def _reset_form(self) -> None:
        """Reset all form fields to their empty defaults."""
        self.editing_anime_id = None
        self.name_input = ""
        self.description_input = ""
        self.episodes_input = ""
        self.season_input = ""
        self.genres_input = ""
        self.image_url_input = ""
        self.form_error_message = ""

    def _reset_delete(self) -> None:
        """Reset all delete confirmation state to its empty defaults."""
        self.deleting_anime_id = None
        self.deleting_anime_name = ""
        self.delete_submitting = False
        self.delete_error_message = ""

    async def _refresh_after_delete(self) -> None:
        """Reload the library, correcting an out-of-range current page.

        Deleting the last item on the last page can shrink the page count, so
        after the reload the page is reconciled against the new total: an
        empty library resets to page 1 and an out-of-range page is clamped and
        reloaded once more.
        """
        self.current_page = max(1, min(self.current_page, self.total_pages))
        await self.load_page()
        if self.total_pages == 0:
            self.current_page = 1
        elif self.current_page > self.total_pages:
            self.current_page = self.total_pages
            await self.load_page()
