"""Deterministic structural tests for the read-only library page.

These tests build the page component and introspect its rendered component
tree. No network, no real backend, no browser.
"""

from app.pages.library import library_page
from app.state.library import LibraryState


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


def _foreach_iterables(component) -> list[str]:
    """The js expressions of all Foreach iterables in the component tree."""
    iterables: list[str] = []
    for node in _walk(component):
        if type(node).__name__ != "Foreach":
            continue
        iterables.append(getattr(node.iterable, "_js_expr", ""))
    return iterables


def _text_contents(component) -> list[str]:
    """All literal or var-bound text expressions found in the component tree.

    Reflex renders text/heading children as ``Bare`` components whose
    ``contents`` attribute carries the literal string or state Var expression.
    Browsing must also descend into list-valued children (foreground cond
    branches) so every branch is covered.
    """

    def descend(node) -> list[str]:
        found: list[str] = []
        if not hasattr(node, "render"):
            return found
        for child in getattr(node, "children", []) or []:
            if isinstance(child, list):
                for nested in child:
                    found.extend(descend(nested))
            elif isinstance(child, dict) and "contents" in child:
                found.append(child["contents"])
            elif hasattr(child, "contents"):
                expr = getattr(child.contents, "_js_expr", "") or ""
                if expr:
                    found.append(expr)
            elif hasattr(child, "render"):
                found.extend(descend(child))
        return found

    return descend(component)


def test_library_page_uses_the_authenticated_shell():
    page = library_page()

    assert 'to:"/"' in _nav_targets(page)
    assert 'to:"/library"' in _nav_targets(page)
    assert "LucideFilm" in _icon_tags(page)


def test_library_page_renders_anime_collection_from_state():
    page = library_page()

    assert LibraryState.animes._js_expr in _foreach_iterables(page)


def test_library_page_wires_previous_and_next_pagination():
    handlers = _event_handler_names(library_page())

    assert "prev_page" in handlers
    assert "next_page" in handlers


def test_library_page_wires_retry_to_load_page():
    handlers = _event_handler_names(library_page())

    assert "load_page" in handlers


def test_library_page_contains_empty_state_text():
    contents = _text_contents(library_page())

    assert any(
        content.strip().strip('"') == "No anime in the library yet."
        for content in contents
    )


def test_library_page_binds_error_message():
    contents = _text_contents(library_page())

    assert any("error_message" in content for content in contents)


def test_library_page_binds_page_count_display():
    contents = _text_contents(library_page())

    assert any("current_page" in content and "total_pages" in content for content in contents)


def test_library_page_uses_expected_icons():
    tags = _icon_tags(library_page())

    assert "LucideLibraryBig" in tags
    assert "LucideCircleAlert" in tags
