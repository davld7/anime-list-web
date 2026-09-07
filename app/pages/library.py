"""Placeholder page for the future anime library."""

import reflex as rx

from app.components.shell import authenticated_shell


def library_page() -> rx.Component:
    """Placeholder for the anime library (not implemented in this milestone)."""
    return authenticated_shell(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon(tag="library-big", size=20),
                    rx.heading("Library", size="4"),
                    align="center",
                    spacing="2",
                ),
                rx.text(
                    "Your saved anime will appear here. "
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
        )
    )
