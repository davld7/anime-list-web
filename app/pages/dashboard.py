"""Authenticated home page (dashboard) for the anime-list-web frontend."""

import reflex as rx

from app.components.shell import authenticated_shell
from app.state.auth import AuthState


def dashboard_page() -> rx.Component:
    """Authenticated entry page after login."""
    return authenticated_shell(
        rx.card(
            rx.vstack(
                rx.heading(f"Welcome, {AuthState.username}!", size="5"),
                rx.text(
                    "Your anime library and tracking features are coming soon. "
                    "Use the navigation above to get started.",
                    size="2",
                    color=rx.color("gray", 11),
                ),
                align="start",
                spacing="3",
                width="100%",
            ),
            variant="surface",
            width="100%",
        )
    )
