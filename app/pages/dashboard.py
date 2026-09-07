"""Authenticated home page (dashboard) for the anime-list-web frontend."""

import reflex as rx

from app.state.auth import AuthState


def dashboard_page() -> rx.Component:
    """Authenticated entry page after login."""
    content = rx.vstack(
        rx.hstack(
            rx.heading("Anime List", size="5"),
            rx.spacer(),
            rx.badge(
                f"Signed in as {AuthState.username}",
                variant="soft",
                color_scheme="gray",
            ),
            rx.button(
                "Log out",
                on_click=AuthState.logout,
                variant="outline",
                color_scheme="gray",
            ),
            align="center",
            width="100%",
        ),
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon(tag="library-big", size=20),
                    rx.heading("Library", size="4"),
                    align="center",
                    spacing="2",
                ),
                rx.text(
                    "Your anime library will appear here. "
                    "Library and tracking features are coming soon.",
                    size="2",
                    color=rx.color("gray", 11),
                ),
                align="start",
                spacing="3",
                width="100%",
            ),
            variant="surface",
            width="100%",
        ),
        width="100%",
        spacing="6",
    )
    return rx.container(
        rx.cond(
            AuthState.is_authenticated,
            content,
            rx.spinner(size="3"),
        ),
        max_width="1100px",
        padding="4",
    )
