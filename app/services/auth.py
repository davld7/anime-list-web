"""Authentication operations for the anime-list-api backend."""

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.client import ApiClient, ApiError, RefreshHandler

LOGIN_PATH = "/auth/login"
LOGOUT_PATH = "/auth/logout"
REFRESH_PATH = "/auth/refresh"
ME_PATH = "/auth/me"

_INVALID_CREDENTIALS = "Invalid username or password."
_SESSION_EXPIRED = "Your session has expired. Please log in again."
_GENERIC_ERROR = "Authentication service error."
_UNAVAILABLE = "Unable to reach the authentication service."
_UNEXPECTED_RESPONSE = "Unexpected response from the authentication service."


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    username: str
    password: str


class AuthTokenResponse(BaseModel):
    """Response body for POST /auth/login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response body for GET /auth/me.

    Mirrors the backend ``UserResponse`` schema. Identity and permissions are
    the backend's source of truth; the frontend never decodes JWTs to obtain
    them.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    username: str
    permissions: list[str] = []
    active: bool = True


class AuthError(Exception):
    """A safe, user-facing authentication failure.

    The message never contains raw backend error bodies or credentials.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def login(client: ApiClient, *, username: str, password: str) -> AuthTokenResponse:
    """Authenticate with the backend and return the token pair.

    Raises:
        AuthError: If the credentials are rejected, the backend is unreachable,
            or the response is unexpected.
    """
    payload = LoginRequest(username=username, password=password).model_dump()
    try:
        response = await client.post(LOGIN_PATH, json=payload)
    except ApiError as exc:
        raise _translate_api_error(exc, invalid_credentials_message=_INVALID_CREDENTIALS) from exc
    return _parse_token_response(response)


async def logout(client: ApiClient, *, refresh_token: str) -> None:
    """Revoke the refresh token server-side.

    Raises:
        AuthError: If the backend rejected the request or was unreachable.
    """
    try:
        await client.post(LOGOUT_PATH, json={"refresh_token": refresh_token})
    except ApiError as exc:
        raise _translate_api_error(exc) from exc


async def fetch_me(
    client: ApiClient,
    *,
    token: str | None = None,
    refresh_handler: RefreshHandler | None = None,
) -> UserResponse:
    """Fetch the authenticated user's identity and permissions.

    Sends ``Authorization: Bearer <token>`` unless ``token`` is ``None``. When a
    ``refresh_handler`` is supplied, the underlying client performs the usual
    refresh-once/retry-once flow on an authenticated ``401``.

    Raises:
        AuthError: If the session is no longer valid, the backend is unreachable,
            or the response is unexpected.
    """
    try:
        response = await client.get(ME_PATH, token=token, refresh_handler=refresh_handler)
    except ApiError as exc:
        raise _translate_api_error(exc, invalid_credentials_message=_SESSION_EXPIRED) from exc
    return _parse_user_response(response)


async def refresh(client: ApiClient, *, refresh_token: str) -> AuthTokenResponse:
    """Exchange a refresh token for a rotated token pair.

    The backend always issues a new access token and a new refresh token while
    revoking the provided one, so the caller must replace BOTH stored tokens.

    Raises:
        AuthError: If the token is invalid/expired/revoked, the backend is
            unreachable, or the response is unexpected.
    """
    try:
        response = await client.post(REFRESH_PATH, json={"refresh_token": refresh_token})
    except ApiError as exc:
        raise _translate_api_error(exc, invalid_credentials_message=_SESSION_EXPIRED) from exc
    return _parse_token_response(response)


def _translate_api_error(
    error: ApiError,
    *,
    invalid_credentials_message: str | None = None,
) -> AuthError:
    if error.status_code is None:
        return AuthError(_UNAVAILABLE)
    if error.status_code == 401 and invalid_credentials_message is not None:
        return AuthError(invalid_credentials_message)
    return AuthError(_GENERIC_ERROR)


def _parse_token_response(response: httpx.Response) -> AuthTokenResponse:
    try:
        data = response.json()
    except ValueError as exc:
        raise AuthError(_UNEXPECTED_RESPONSE) from exc
    try:
        return AuthTokenResponse.model_validate(data)
    except ValidationError as exc:
        raise AuthError(_UNEXPECTED_RESPONSE) from exc


def _parse_user_response(response: httpx.Response) -> UserResponse:
    try:
        data = response.json()
    except ValueError as exc:
        raise AuthError(_UNEXPECTED_RESPONSE) from exc
    try:
        return UserResponse.model_validate(data)
    except ValidationError as exc:
        raise AuthError(_UNEXPECTED_RESPONSE) from exc
