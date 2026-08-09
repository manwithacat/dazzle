"""Cycle 1806 — breadcrumb trail open-discovery stamps.

Agents attr-read parent list/detail crumbs without scraping labels.
Home / bare ``/app`` / non-app paths stay unstamped — parity with VIEW
ref-link path gate.
"""

from __future__ import annotations

from dazzle.render.fragment import Breadcrumb, BreadcrumbItem, FragmentRenderer
from dazzle.render.open_discovery import breadcrumb_open_attr_suffix, open_hop_label


def test_breadcrumb_open_attr_suffix_app_entity() -> None:
    attrs = breadcrumb_open_attr_suffix("/app/task")
    assert "data-dz-breadcrumb-drill" in attrs
    assert 'data-dz-open-entity="Task"' in attrs
    assert 'data-dz-open-via="id"' in attrs
    assert "Open Task" in attrs
    assert 'data-dz-open-chain="/app/task"' in attrs


def test_breadcrumb_open_attr_suffix_detail_path() -> None:
    attrs = breadcrumb_open_attr_suffix("/app/ticket/t-9")
    assert "data-dz-breadcrumb-drill" in attrs
    assert 'data-dz-open-entity="Ticket"' in attrs
    assert open_hop_label("Ticket") in attrs


def test_breadcrumb_open_attr_suffix_skips_home_and_non_app() -> None:
    assert breadcrumb_open_attr_suffix("/app") == ""
    assert breadcrumb_open_attr_suffix("/") == ""
    assert breadcrumb_open_attr_suffix("/projects") == ""
    assert breadcrumb_open_attr_suffix("#") == ""
    assert breadcrumb_open_attr_suffix("") == ""


def test_breadcrumb_emit_stamps_open_discovery_on_entity_crumbs() -> None:
    html = FragmentRenderer().render(
        Breadcrumb(
            items=(
                BreadcrumbItem(label="Home", href="/app"),
                BreadcrumbItem(label="Tasks", href="/app/task"),
                BreadcrumbItem(label="Fix login", href=None),
            )
        )
    )
    assert 'class="dz-breadcrumb"' in html
    # Home stays plain (no entity slug)
    home_idx = html.index('href="/app"')
    task_idx = html.index('href="/app/task"')
    assert "data-dz-breadcrumb-drill" not in html[home_idx:task_idx]
    # Entity list crumb stamps VIEW open discovery
    assert "data-dz-breadcrumb-drill" in html
    assert 'data-dz-open-entity="Task"' in html
    assert "Open Task" in html
    assert 'aria-current="page">Fix login</li>' in html
