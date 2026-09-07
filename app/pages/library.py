"""Read-only anime library page for the anime-list-web frontend."""

import reflex as rx

from app.components.shell import authenticated_shell
from app.state.library import LibraryState


def _genre_badge(genre: rx.Var) -> rx.Component:
    """Render a single anime genre as a small badge."""
    return rx.badge(genre, size="1", variant="soft", color_scheme="gray")


def _anime_card(anime: rx.Var) -> rx.Component:
    """Render a single anime as a compact card."""
    return rx.card(
        rx.vstack(
            rx.image(
                src=anime.image_url,
                width="100%",
                height="200px",
                style={"object_fit": "cover"},
            ),
            rx.vstack(
                rx.heading(anime.name, size="3"),
                rx.hstack(
                    rx.badge(anime.season, variant="soft", color_scheme="gray"),
                    rx.badge(f"{anime.episodes} episodes", variant="soft", color_scheme="gray"),
                    spacing="2",
                ),
                rx.hstack(
                    rx.foreach(anime.genres, _genre_badge),
                    spacing="1",
                ),
                rx.text(
                    anime.description,
                    size="2",
                    style={
                        "display": "-webkit-box",
                        "WebkitLineClamp": "3",
                        "WebkitBoxOrient": "vertical",
                        "overflow": "hidden",
                    },
                    color=rx.color("gray", 11),
                ),
                align="start",
                spacing="2",
                width="100%",
            ),
            spacing="0",
            width="100%",
        ),
        variant="surface",
        width="100%",
    )


def _loading_state() -> rx.Component:
    """Centered spinner shown during the initial load."""
    return rx.center(
        rx.spinner(size="3"),
        width="100%",
        padding="8",
    )


def _empty_state() -> rx.Component:
    """Empty-library message shown when there are no anime records."""
    return rx.card(
        rx.vstack(
            rx.icon(tag="library-big", size=20),
            rx.heading("No anime in the library yet.", size="4"),
            align="center",
            spacing="3",
            width="100%",
        ),
        variant="surface",
        width="100%",
    )


def _error_state() -> rx.Component:
    """Error card with a retry action."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(tag="circle-alert", size=20),
                rx.heading("Couldn't load the library", size="4"),
                align="center",
                spacing="2",
            ),
            rx.text(
                LibraryState.error_message,
                size="2",
                color=rx.color("gray", 11),
            ),
            rx.button(
                "Retry",
                on_click=LibraryState.load_page,
                color_scheme="gray",
                variant="soft",
            ),
            align="start",
            spacing="3",
            width="100%",
        ),
        variant="surface",
        width="100%",
    )


def _pagination_row() -> rx.Component:
    """Previous/Next navigation row for the anime grid."""
    return rx.hstack(
        rx.button(
            "Previous",
            on_click=LibraryState.prev_page,
            is_disabled=LibraryState.current_page <= 1,
            variant="surface",
            color_scheme="gray",
        ),
        rx.text(
            f"Page {LibraryState.current_page} of {LibraryState.total_pages}",
            size="2",
            color=rx.color("gray", 11),
        ),
        rx.button(
            "Next",
            on_click=LibraryState.next_page,
            is_disabled=LibraryState.current_page >= LibraryState.total_pages,
            variant="surface",
            color_scheme="gray",
        ),
        align="center",
        spacing="4",
    )


def _results_state() -> rx.Component:
    """The anime card grid together with its pagination."""
    return rx.vstack(
        rx.grid(
            rx.foreach(LibraryState.animes, _anime_card),
            columns={"initial": "1", "md": "2", "lg": "3"},
            spacing="4",
            width="100%",
        ),
        rx.cond(
            LibraryState.loading,
            rx.text("Loading…", size="1", color=rx.color("gray", 11)),
        ),
        rx.cond(LibraryState.total_pages > 1, _pagination_row()),
        width="100%",
        spacing="4",
    )


def library_page() -> rx.Component:
    """Authenticated read-only anime library page."""
    return authenticated_shell(
        rx.vstack(
            rx.heading("Library", size="5"),
            rx.text(
                f"{LibraryState.total_animes} anime in the library",
                size="2",
                color=rx.color("gray", 11),
            ),
            rx.cond(
                LibraryState.loading & (LibraryState.animes.length() == 0),
                _loading_state(),
                rx.cond(
                    LibraryState.error_message != "",
                    _error_state(),
                    rx.cond(
                        LibraryState.total_pages == 0,
                        _empty_state(),
                        _results_state(),
                    ),
                ),
            ),
            align="start",
            spacing="3",
            width="100%",
        )
    )
