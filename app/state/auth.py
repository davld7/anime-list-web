"""Per-session authentication state for the anime-list-web frontend.

Tokens are held in backend-only state variables (leading underscore) and are
never synchronized to the browser. Only safe session metadata is exposed.
"""

import reflex as rx
from reflex.event import EventSpec

from app.services import auth as auth_service
from app.services.auth import AuthError
from app.services.client import ApiClient

LOGIN_ROUTE = "/login"
DASHBOARD_ROUTE = "/"


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
    user_id: str | None = None
    permissions: list[str] = []
    active: bool = False
    username_input: str = ""
    password_input: str = ""
    submitting: bool = False

    @classmethod
    def _make_client(cls) -> ApiClient:
        """Build the API client used by the authentication handlers."""
        return ApiClient()

    @rx.event
    async def login(self, username: str, password: str) -> EventSpec | None:
        """Authenticate against the backend and load the current user.

        The token pair is stored first, then identity/permissions are fetched
        from `/auth/me`. On any failure the session is left (or returned to)
        unauthenticated and a safe error message is recorded; a partially
        initialized session is never left active.

        Returns:
            A redirect to the authenticated home on success, otherwise ``None``.
        """
        self._clear_session()
        try:
            tokens = await auth_service.login(
                self._make_client(), username=username, password=password
            )
        except AuthError as exc:
            self.error_message = exc.message
            return None
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        success = await self.load_user()
        if success:
            return rx.redirect(DASHBOARD_ROUTE)
        return None

    async def load_user(self) -> bool:
        """Fetch the authenticated user's identity and permissions.

        Uses the stored access token through the authenticated client path, so
        the existing refresh-once/retry-once behavior applies. On failure the
        session is cleared via the existing lifecycle and ``False`` is returned.

        Returns:
            ``True`` if the identity was loaded successfully, ``False`` otherwise.
        """
        token = self._access_token
        if not token:
            self._clear_session()
            return False
        try:
            user = await auth_service.fetch_me(
                self._make_client(), token=token, refresh_handler=self._refresh
            )
        except AuthError as exc:
            self._clear_session()
            self.error_message = exc.message
            return False
        self.user_id = user.id
        self.username = user.username
        self.permissions = list(user.permissions)
        self.active = user.active
        self.is_authenticated = True
        self.error_message = ""
        return True

    @rx.event
    def set_username_input(self, value: str) -> None:
        """Update the username input field."""
        self.username_input = value

    @rx.event
    def set_password_input(self, value: str) -> None:
        """Update the password input field."""
        self.password_input = value

    @rx.event
    async def submit_login(self, form_data: dict | None = None) -> EventSpec | None:
        """Submit the login form using the current input values.

        Reads the username/password inputs, forwards to :meth:`login`, and
        passes through the redirect on success. The password field and the
        submitting flag are always reset, so a failed attempt leaves the
        username in place but never retains the entered password.

        Args:
            form_data: Submitted form values (unused; inputs are controlled).

        Returns:
            The redirect produced by :meth:`login` on success, otherwise ``None``.
        """
        self.submitting = True
        try:
            return await self.login(self.username_input.strip(), self.password_input)
        finally:
            self.submitting = False
            self.password_input = ""

    @rx.event
    def guard_authenticated(self) -> EventSpec | None:
        """UX guard for the authenticated area: send anonymous users to login."""
        if not self.is_authenticated:
            return rx.redirect(LOGIN_ROUTE)
        return None

    @rx.event
    def guard_login(self) -> EventSpec | None:
        """UX guard for the login page: send authenticated users home."""
        if self.is_authenticated:
            return rx.redirect(DASHBOARD_ROUTE)
        return None

    @rx.event
    async def logout(self) -> EventSpec:
        """Clear the local session and best-effort revoke the refresh token.

        The local session always clears; a failed server-side revocation is
        not surfaced because the session is already gone.

        Returns:
            A redirect to the login page.
        """
        refresh_token = self._refresh_token
        self._clear_session()
        self.password_input = ""
        if refresh_token:
            try:
                await auth_service.logout(self._make_client(), refresh_token=refresh_token)
            except AuthError:
                pass
        return rx.redirect(LOGIN_ROUTE)

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
        self.user_id = None
        self.permissions = []
        self.active = False
