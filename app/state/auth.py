"""Per-session authentication state for the anime-list-web frontend.

Tokens are held in backend-only state variables (leading underscore) and are
never synchronized to the browser. Only safe session metadata is exposed.
"""

import reflex as rx

from app.services import auth as auth_service
from app.services.auth import AuthError
from app.services.client import ApiClient


class AuthState(rx.State):
    """Server-side session state for authentication.

    Tokens stay in backend-only vars (`_access_token`, `_refresh_token`), so
    they are never sent to the frontend. `username` and `is_authenticated`
    are safe, non-sensitive session metadata for UX decisions.
    """

    _access_token: str = ""
    _refresh_token: str = ""
    username: str = ""
    is_authenticated: bool = False
    error_message: str = ""

    @classmethod
    def _make_client(cls) -> ApiClient:
        """Build the API client used by the authentication handlers."""
        return ApiClient()

    @rx.event
    async def login(self, username: str, password: str) -> None:
        """Authenticate against the backend and store the session.

        On any failure the session is left (or returned to) unauthenticated
        and a safe error message is recorded.
        """
        self._clear_session()
        try:
            tokens = await auth_service.login(
                self._make_client(), username=username, password=password
            )
        except AuthError as exc:
            self.error_message = exc.message
            return
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        self.username = username
        self.is_authenticated = True

    @rx.event
    async def logout(self) -> None:
        """Clear the local session and best-effort revoke the refresh token.

        The local session always clears; a failed server-side revocation is
        not surfaced because the session is already gone.
        """
        refresh_token = self._refresh_token
        self._clear_session()
        if refresh_token:
            try:
                await auth_service.logout(self._make_client(), refresh_token=refresh_token)
            except AuthError:
                pass

    async def _refresh(self) -> str | None:
        """Exchange the current refresh token for a rotated token pair.

        On success both stored tokens are replaced together and the new access
        token is returned so the caller can retry the original request. On any
        failure the local session is cleared and ``None`` is returned; the
        original request must not be retried.

        This is used internally by ``ApiClient``'s refresh/retry path. It uses a
        bare client (no refresh handler) so a refresh never re-enters itself.
        """
        refresh_token = self._refresh_token
        if not refresh_token:
            self._clear_session()
            return None
        try:
            tokens = await auth_service.refresh(self._make_client(), refresh_token=refresh_token)
        except AuthError as exc:
            self._clear_session()
            self.error_message = exc.message
            return None
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        return tokens.access_token

    def _clear_session(self) -> None:
        """Reset all session information to the logged-out default."""
        self._access_token = ""
        self._refresh_token = ""
        self.username = ""
        self.is_authenticated = False
        self.error_message = ""
