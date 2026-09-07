"""Application entrypoint for the anime-list-web frontend."""

import reflex as rx

from app.pages.dashboard import dashboard_page
from app.pages.login import login_page
from app.state.auth import AuthState

app = rx.App()

app.add_page(
    dashboard_page,
    route="/",
    title="Anime List",
    description="Your personal anime library.",
    on_load=AuthState.guard_dashboard,
)

app.add_page(
    login_page,
    route="/login",
    title="Sign in | Anime List",
    description="Sign in to access your anime library.",
    on_load=AuthState.guard_login,
)
