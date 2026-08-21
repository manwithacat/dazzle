"""Related salary history must title pay, not the reason enum (oral #141)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.page.converters.template_compiler import (
    _project_related_columns,
    _related_proj_index,
    compile_appspec_to_templates,
)
from dazzle.render.cell_chrome import related_queue_title_and_meta
from dazzle.render.context import ColumnContext
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer


def test_related_proj_index_maps_amount_to_minor() -> None:
    order = {"amount": 0, "effective_from": 1, "reason": 2}
    assert _related_proj_index("amount_minor", order) == 0
    assert _related_proj_index("effective_from", order) == 1
    assert _related_proj_index("reason", order) == 2
    assert _related_proj_index("amount_currency", order) is None
    assert _related_proj_index("zzz", order) is None


def test_related_proj_index_leftover_stays_put() -> None:
    order = {"amount": 0}
    assert _related_proj_index("ghost_minor", order) is None
    assert _related_proj_index("zzz", order) is None


def test_project_related_columns_keeps_money_minor() -> None:
    cols = [
        ColumnContext(key="effective_from", label="From", type="date"),
        ColumnContext(key="amount_minor", label="Amount", type="currency", currency_code="GBP"),
        ColumnContext(key="reason", label="Reason", type="badge"),
    ]
    out = _project_related_columns(cols, {"amount": 0, "effective_from": 1, "reason": 2})
    assert [c.key for c in out] == ["amount_minor", "effective_from", "reason"]


def test_related_queue_prefers_sterling_not_reason_enum() -> None:
    title, metas = related_queue_title_and_meta(
        ("£71,416.88", "1 Jun 2024", "", "Annual Review"),
        ("Amount", "Effective From", "Effective To", "Reason"),
    )
    assert title == "£71,416.88"
    assert ("Reason", "Annual Review") in metas
    assert title != "Annual Review"


def test_related_queue_leftover_amount_stays_put() -> None:
    title, metas = related_queue_title_and_meta(
        ("zzz", "1 Jun 2024", "ghost"),
        ("Amount", "Effective From", "Reason"),
    )
    assert title == "zzz"
    assert ("Reason", "ghost") in metas


def test_related_queue_html_titles_sterling() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="compensation",
            label="Salary history",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="compensation",
                    label="Salary history",
                    headers=("Amount", "Effective From", "Reason"),
                    rows=(("£71,416.88", "1 Jun 2024", "Annual Review"),),
                    row_drill=("/app/salary/s-1",),
                ),
            ),
        )
    )
    assert "£71,416.88" in html
    assert "dz-queue-row" in html or "data-dz-queue-row" in html
    assert "Reason: Annual Review" in html
    assert html.index("£71,416.88") < html.index("Annual Review")


def test_related_queue_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="compensation",
            label="Salary history",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="compensation",
                    label="Salary history",
                    headers=("Amount", "Reason"),
                    rows=(("zzz", "ghost"),),
                ),
            ),
        )
    )
    assert ">zzz<" in html or "zzz" in html
    assert "Reason: ghost" in html


def test_hr_records_compensation_columns_keep_amount_minor() -> None:
    spec = load_project(Path("examples/hr_records"))
    ctxs = compile_appspec_to_templates(spec)
    detail = ctxs["/person/{id}"].detail
    assert detail is not None
    group = next(g for g in detail.related_groups if g.group_id == "group-compensation")
    assert group.display == "queue"
    keys = [c.key for c in group.tabs[0].columns]
    assert keys[0] == "amount_minor"
    assert "reason" in keys
    by = {c.key: c for c in group.tabs[0].columns}
    assert by["amount_minor"].type == "currency"
    assert by["reason"].type == "badge"
