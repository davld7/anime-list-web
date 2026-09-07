"""Login page for the anime-list-web frontend."""

import reflex as rx

from app.state.auth import AuthState


def login_form() -> rx.Component:
    """Username/password form bound to ``AuthState``."""
    return rx.form(
        rx.vstack(
            rx.text("Username", size="2", weight="medium"),
            rx.input(
                placeholder="Enter your username",
                name="username",
                type="text",
                value=AuthState.username_input,
                on_change=AuthState.set_username_input,
                width="100%",
            ),
            rx.text("Password", size="2", weight="medium"),
            rx.input(
                placeholder="Enter your password",
                name="password",
                type="password",
                value=AuthState.password_input,
                on_change=AuthState.set_password_input,
                width="100%",
            ),
            rx.cond(
                AuthState.error_message != "",
                rx.callout(
                    text=AuthState.error_message,
                    icon="triangle_alert",
                    color_scheme="red",
                    variant="soft",
                    role="alert",
                    width="100%",
                ),
            ),
            rx.button(
                "Sign in",
                type="submit",
                loading=AuthState.submitting,
                disabled=AuthState.submitting,
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        on_submit=AuthState.submit_login,
        width="100%",
    )


def login_page() -> rx.Component:
    """Page shown to unauthenticated users."""
    return rx.center(
        rx.cond(
            AuthState.is_authenticated,
            rx.spinner(size="3"),
            rx.card(
                rx.vstack(
                    rx.heading("Anime List", size="6"),
                    rx.text(
                        "Sign in to access your library.",
                        size="2",
                        color=rx.color("gray", 11),
                    ),
                    login_form(),
                    align="stretch",
                    spacing="4",
                    width="100%",
                ),
                variant="surface",
                max_width="400px",
                width="100%",
            ),
        ),
        rx.color_mode.button(position="top-right"),
        min_height="100vh",
        padding="4",
        width="100%",
    )
