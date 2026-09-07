"""Anime library page with create/edit/delete management for the anime-list-web frontend."""

import reflex as rx

from app.components.shell import authenticated_shell
from app.state.auth import AuthState
from app.state.library import LibraryState


def _genre_badge(genre: rx.Var) -> rx.Component:
    """Render a single anime genre as a small badge."""
    return rx.badge(genre, size="1", variant="soft", color_scheme="gray")


def _card_actions(anime: rx.Var) -> rx.Component:
    """Edit/Delete actions for one anime card, gated by permission.

    Permission checks drive UI visibility only; the backend remains the
    authority for authorization.
    """
    return rx.hstack(
        rx.cond(
            AuthState.permissions.contains("write"),
            rx.button(
                "Edit",
                on_click=LibraryState.open_edit_form(anime.id),
                size="2",
                variant="soft",
                color_scheme="gray",
            ),
        ),
        rx.cond(
            AuthState.permissions.contains("admin"),
            rx.button(
                "Delete",
                on_click=LibraryState.request_delete(anime.id),
                size="2",
                variant="soft",
                color_scheme="red",
            ),
        ),
        spacing="2",
        justify="end",
        width="100%",
    )


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
            _card_actions(anime),
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


def _empty_state(has_write: rx.Var) -> rx.Component:
    """Empty-library message shown when there are no anime records."""
    return rx.card(
        rx.vstack(
            rx.icon(tag="library-big", size=20),
            rx.heading("No anime in the library yet.", size="4"),
            rx.cond(
                has_write,
                rx.text("Create the first anime.", size="2", color=rx.color("gray", 11)),
                rx.text("There is nothing to show yet.", size="2", color=rx.color("gray", 11)),
            ),
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


def _form_field(label: str, field: rx.Component) -> rx.Component:
    """Label + input field for the anime form dialog."""
    return rx.vstack(
        rx.text(label, size="2", color=rx.color("gray", 11)),
        field,
        align="start",
        spacing="1",
        width="100%",
    )


def _anime_form_dialog() -> rx.Component:
    """Create/Edit dialog for one anime record."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(
                    LibraryState.editing_anime_id != None,  # noqa: E711
                    "Edit Anime",
                    "Create Anime",
                )
            ),
            rx.dialog.description(
                "The backend validates the submitted values.",
                size="2",
                color=rx.color("gray", 11),
            ),
            rx.vstack(
                _form_field(
                    "Name",
                    rx.input(
                        value=LibraryState.name_input,
                        on_change=LibraryState.set_name_input,
                        placeholder="Anime name",
                        width="100%",
                    ),
                ),
                _form_field(
                    "Description",
                    rx.text_area(
                        value=LibraryState.description_input,
                        on_change=LibraryState.set_description_input,
                        placeholder="Short summary",
                        width="100%",
                    ),
                ),
                _form_field(
                    "Episodes",
                    rx.input(
                        value=LibraryState.episodes_input,
                        on_change=LibraryState.set_episodes_input,
                        placeholder="e.g. 12",
                        width="100%",
                    ),
                ),
                _form_field(
                    "Season",
                    rx.input(
                        value=LibraryState.season_input,
                        on_change=LibraryState.set_season_input,
                        placeholder="e.g. Fall 2025",
                        width="100%",
                    ),
                ),
                _form_field(
                    "Genres",
                    rx.input(
                        value=LibraryState.genres_input,
                        on_change=LibraryState.set_genres_input,
                        placeholder="Comma-separated, e.g. Action, Comedy",
                        width="100%",
                    ),
                ),
                _form_field(
                    "Image URL",
                    rx.input(
                        value=LibraryState.image_url_input,
                        on_change=LibraryState.set_image_url_input,
                        placeholder="https://…",
                        width="100%",
                    ),
                ),
                width="100%",
                spacing="3",
            ),
            rx.cond(
                LibraryState.form_error_message != "",
                rx.text(
                    LibraryState.form_error_message,
                    size="2",
                    color=rx.color("red", 11),
                ),
            ),
            rx.hstack(
                rx.button(
                    "Cancel",
                    on_click=LibraryState.close_form,
                    variant="soft",
                    color_scheme="gray",
                ),
                rx.cond(
                    LibraryState.editing_anime_id != None,  # noqa: E711
                    rx.button(
                        "Save Changes",
                        on_click=LibraryState.update_anime,
                        is_disabled=LibraryState.form_submitting,
                    ),
                    rx.button(
                        "Create",
                        on_click=LibraryState.create_anime,
                        is_disabled=LibraryState.form_submitting,
                    ),
                ),
                align="center",
                justify="end",
                width="100%",
                spacing="3",
            ),
            align="start",
            max_width="480px",
        ),
        open=LibraryState.form_open,
        on_open_change=LibraryState.set_form_open,
    )


def _delete_dialog() -> rx.Component:
    """Delete confirmation dialog for one anime record."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Anime"),
            rx.text(
                f'Delete "{LibraryState.deleting_anime_name}"? This cannot be undone.',
                size="2",
                color=rx.color("gray", 11),
            ),
            rx.cond(
                LibraryState.delete_error_message != "",
                rx.text(
                    LibraryState.delete_error_message,
                    size="2",
                    color=rx.color("red", 11),
                ),
            ),
            rx.hstack(
                rx.button(
                    "Cancel",
                    on_click=LibraryState.cancel_delete,
                    variant="soft",
                    color_scheme="gray",
                ),
                rx.button(
                    "Delete",
                    on_click=LibraryState.delete_anime(LibraryState.deleting_anime_id),
                    is_disabled=LibraryState.delete_submitting,
                    color_scheme="red",
                ),
                align="center",
                justify="end",
                width="100%",
                spacing="3",
            ),
            align="start",
            max_width="420px",
        ),
        open=LibraryState.delete_confirmation_open,
        on_open_change=LibraryState.set_delete_confirmation_open,
    )


def _page_header() -> rx.Component:
    """Page title and the permission-gated Create action."""
    return rx.hstack(
        rx.vstack(
            rx.heading("Library", size="5"),
            rx.text(
                f"{LibraryState.total_animes} anime in the library",
                size="2",
                color=rx.color("gray", 11),
            ),
            align="start",
            spacing="1",
        ),
        rx.spacer(),
        rx.cond(
            AuthState.permissions.contains("write"),
            rx.button(
                "Create Anime",
                on_click=LibraryState.open_create_form,
                color_scheme="iris",
            ),
        ),
        align="center",
        width="100%",
    )


def library_page() -> rx.Component:
    """Authenticated anime library page with management actions."""
    return authenticated_shell(
        rx.vstack(
            _page_header(),
            rx.cond(
                LibraryState.loading & (LibraryState.animes.length() == 0),
                _loading_state(),
                rx.cond(
                    LibraryState.error_message != "",
                    _error_state(),
                    rx.cond(
                        LibraryState.total_pages == 0,
                        _empty_state(AuthState.permissions.contains("write")),
                        _results_state(),
                    ),
                ),
            ),
            _anime_form_dialog(),
            _delete_dialog(),
            align="start",
            spacing="3",
            width="100%",
        )
    )
