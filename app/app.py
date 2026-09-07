"""Application entrypoint for the anime-list-web frontend."""

import reflex as rx

from app.pages.dashboard import dashboard_page
from app.pages.library import library_page
from app.pages.login import login_page
from app.state.auth import AuthState
from app.state.library import LibraryState

app = rx.App()

app.add_page(
    dashboard_page,
    route="/",
    title="Anime List",
    description="Your personal anime library.",
    on_load=AuthState.guard_authenticated,
)

app.add_page(
    library_page,
    route="/library",
    title="Library | Anime List",
    description="Your anime library.",
    on_load=[
        AuthState.guard_authenticated,
        LibraryState.load_page,
    ],
)

app.add_page(
    login_page,
    route="/login",
    title="Sign in | Anime List",
    description="Sign in to access your anime library.",
    on_load=AuthState.guard_login,
)
