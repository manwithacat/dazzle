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
from dazzle.rbac.matrix import generate_access_matrix
from dazzle.ui.converters.nav_builder import build_persona_nav

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
    assert group_labels == ["Contacts", "Browse"]

    # "Contacts" group → the Contact entity's list surface.
    contacts_group = next(g for g in model.groups if g.label == "Contacts")
    contact_link = next(link for link in contacts_group.links if link.entity == "Contact")
    assert contact_link.route == "/list/Contact"
    assert contact_link.label == "Contact List"

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
