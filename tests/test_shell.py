"""Deterministic tests for the authenticated application shell and pages.

These tests build the page components directly and introspect their rendered
component tree. No network, no real backend, no browser.
"""

from app.pages.dashboard import dashboard_page
from app.pages.library import library_page


def _walk(node):
    """Walk a component tree, yielding every renderable node."""
    if not hasattr(node, "render"):
        return
    yield node
    for child in getattr(node, "children", []) or []:
        yield from _walk(child)


def _nav_targets(component) -> list[str]:
    """All router link targets found in the component tree."""
    targets: list[str] = []
    for node in _walk(component):
        rendered = node.render()
        if rendered.get("name") != "ReactRouterLink":
            continue
        for prop in rendered.get("props", []):
            if prop.startswith("to:"):
                targets.append(prop)
    return targets


def _event_handler_names(component) -> list[str]:
    """All event handler function names wired up in the component tree."""
    names: list[str] = []
    for node in _walk(component):
        for chain in getattr(node, "event_triggers", {}).values():
            for event in getattr(chain, "events", []) or []:
                fn = getattr(getattr(event, "handler", None), "fn", None)
                name = getattr(fn, "__name__", None)
                if name and name not in names:
                    names.append(name)
    return names


def _icon_tags(component) -> list[str]:
    """All lucide icon component names found in the rendered tree."""
    return [
        node.render().get("name")
        for node in _walk(component)
        if (node.render().get("name") or "").startswith("Lucide")
    ]


def test_dashboard_page_includes_dashboard_and_library_navigation():
    targets = _nav_targets(dashboard_page())

    assert 'to:"/"' in targets
    assert 'to:"/library"' in targets
    assert len(targets) == 2


def test_library_page_includes_dashboard_and_library_navigation():
    targets = _nav_targets(library_page())

    assert 'to:"/"' in targets
    assert 'to:"/library"' in targets
    assert len(targets) == 2


def test_shell_logout_button_wires_to_auth_logout():
    handler_names = _event_handler_names(dashboard_page())

    assert "logout" in handler_names


def test_pages_use_the_shared_shell_header():
    for page in (dashboard_page(), library_page()):
        tags = _icon_tags(page)
        assert "LucideFilm" in tags

    assert "LucideLibraryBig" in _icon_tags(library_page())
    assert "LucideLibraryBig" not in _icon_tags(dashboard_page())
