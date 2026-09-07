"""Reusable authenticated application shell for anime-list-web pages."""

import reflex as rx

from app.state.auth import AuthState


def nav_link(href: str, label: str) -> rx.Component:
    """Navigation link with an active-state indicator for the current page."""
    is_active = AuthState.router.url.path == href
    return rx.link(
        rx.text(
            label,
            size="2",
            weight=rx.cond(is_active, "bold", "regular"),
            color=rx.cond(is_active, rx.color("accent", 11), rx.color("gray", 11)),
        ),
        href=href,
    )


def app_header() -> rx.Component:
    """Application header with branding, navigation, and session actions."""
    return rx.hstack(
        rx.hstack(
            rx.hstack(
                rx.icon(tag="film", size=24),
                rx.heading("Anime List", size="4"),
                align="center",
                spacing="2",
            ),
            rx.hstack(
                nav_link("/", "Dashboard"),
                nav_link("/library", "Library"),
                spacing="4",
            ),
            align="center",
            spacing="6",
        ),
        rx.hstack(
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
            spacing="3",
        ),
        justify="between",
        align="center",
        width="100%",
    )


def authenticated_shell(content: rx.Component) -> rx.Component:
    """Wrap authenticated page content in the shared application shell.

    While an anonymous visitor is being redirected to the login page, only a
    spinner is rendered instead of the shell + content.
    """
    return rx.container(
        rx.cond(
            AuthState.is_authenticated,
            rx.vstack(
                app_header(),
                rx.box(content, width="100%"),
                width="100%",
                spacing="6",
            ),
            rx.spinner(size="3"),
        ),
        max_width="1100px",
        padding="4",
    )
