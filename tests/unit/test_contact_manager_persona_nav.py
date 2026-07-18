"""Worked per-persona nav example, end-to-end against ``examples/contact_manager`` (#1324 slice 4).

contact_manager is the canonical two-persona example. The ``user`` persona
binds a curated sidebar via ``uses nav contact_nav``; the ``admin`` persona
has no binding and falls back to auto-discovery. This test exercises the
author-facing ``uses nav`` path on real committed DSL using the REAL RBAC
matrix (``generate_access_matrix``), so it's a true end-to-end check — not a
stubbed-matrix unit test.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.page.converters.nav_builder import build_persona_nav
from dazzle.rbac.matrix import generate_access_matrix

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "contact_manager"


def test_contact_manager_user_persona_has_curated_nav() -> None:
    """The committed ``user`` persona resolves ``uses nav contact_nav`` to the
    hand-ordered curated sidebar (auto_discovered=False), with both real
    targets resolving to routes through the REAL access matrix."""
    appspec = load_project_appspec(EXAMPLE_ROOT)
    matrix = generate_access_matrix(appspec)

    user = next(p for p in appspec.personas if p.id == "user")
    assert user.nav_ref == "contact_nav"

    model = build_persona_nav(appspec, user, matrix)

    # Curated path — NOT auto-discovered.
    assert model.auto_discovered is False

    group_labels = [g.label for g in model.groups]
    # TR-2: Home first so the sidebar matches the post-login landing.
    assert group_labels == ["Home", "Contacts", "Browse"]

    # "Home" group → the `home` workspace page.
    home_group = next(g for g in model.groups if g.label == "Home")
    home_link = next(link for link in home_group.links if link.entity == "home")
    assert home_link.route == "/workspaces/home"

    # "Contacts" group → the Contact entity's list surface.
    # Label comes from the LIST surface title (`surface contact_list "Contacts"`),
    # not the legacy "{entity} List" fallback — product nav copy (#1626).
    contacts_group = next(g for g in model.groups if g.label == "Contacts")
    contact_link = next(link for link in contacts_group.links if link.entity == "Contact")
    assert contact_link.route == "/list/Contact"
    assert contact_link.label == "Contacts"

    # "Browse" group → the `contacts` workspace page.
    browse_group = next(g for g in model.groups if g.label == "Browse")
    workspace_link = next(link for link in browse_group.links if link.entity == "contacts")
    assert workspace_link.route == "/workspaces/contacts"


def test_contact_manager_admin_persona_auto_discovers() -> None:
    """The committed ``admin`` persona has no ``uses nav`` binding, so it falls
    back to auto-discovery — demonstrating both nav paths in one app."""
    appspec = load_project_appspec(EXAMPLE_ROOT)
    matrix = generate_access_matrix(appspec)

    admin = next(p for p in appspec.personas if p.id == "admin")
    assert admin.nav_ref is None

    model = build_persona_nav(appspec, admin, matrix)
    assert model.auto_discovered is True


def test_contact_manager_browse_group_gated_by_tenant_config() -> None:
    """#1324 FR-4 worked example: the committed ``Browse`` group declares
    ``when: tenant_config.show_browse = true``. It carries the model_dump'd
    condition through the NavModel, and the render-time sidebar filter hides it
    when the tenant flag is false and shows it when true — visibility only, the
    ``contacts`` workspace stays reachable (RBAC unchanged)."""
    from dazzle.render.context import PageContext
    from dazzle.render.dispatch import _sidebar_from_nav_model

    appspec = load_project_appspec(EXAMPLE_ROOT)
    matrix = generate_access_matrix(appspec)
    user = next(p for p in appspec.personas if p.id == "user")
    model = build_persona_nav(appspec, user, matrix)

    # The condition is carried onto the Browse NavGroup (model_dump'd dict).
    browse = next(g for g in model.groups if g.label == "Browse")
    assert isinstance(browse.when, dict)
    assert browse.when["comparison"]["field"] == "tenant_config.show_browse"

    # Tenant with the flag OFF → "Browse" group hidden from the sidebar.
    off = _sidebar_from_nav_model(
        model, PageContext(page_title="x", tenant_config={"show_browse": False})
    )
    assert "Browse" not in {g.label for g in off.groups}
    assert "Contacts" in {g.label for g in off.groups}

    # Tenant with the flag ON → "Browse" group present.
    on = _sidebar_from_nav_model(
        model, PageContext(page_title="x", tenant_config={"show_browse": True})
    )
    assert "Browse" in {g.label for g in on.groups}
