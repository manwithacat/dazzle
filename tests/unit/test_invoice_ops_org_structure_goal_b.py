"""Post-5.8 Goal B org_structure — invoice_ops Team + Suppliers desk hierarchy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
USER_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/User.jsonl"
SUPPLIER_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/Supplier.jsonl"


def _team_desk_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace team_desk "Team":')
    end = text.index('workspace payments_trail "Payments":', start)
    return text[start:end]


def _suppliers_desk_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace suppliers_desk "Suppliers":')
    end = text.index('workspace team_desk "Team":', start)
    return text[start:end]


def test_user_entity_declares_department_and_job_title() -> None:
    text = ENTITIES.read_text()
    start = text.index('entity User "User":')
    end = text.index('entity Supplier "Supplier":', start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "job_title: str(80)" in block


def test_team_desk_declares_title_board_and_dept_before_load() -> None:
    """Peer AP tools show title/dept org shape before open invoice dumps."""
    block = _team_desk_block()
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_department:" in block
    # Region markers (avoid team_pulse aggregate keys people:/open_invoices:)
    roster = "\n  people:\n    source: User"
    open_load = "\n  open_invoices:\n    source: Invoice"
    assert roster in block
    assert open_load in block
    # Order: pulse → title board → department queue → flat roster → open load
    assert block.index("team_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_department:")
    assert block.index("by_department:") < block.index(roster)
    assert block.index(roster) < block.index(open_load)


def test_team_desk_ux_focus_org_before_load() -> None:
    block = _team_desk_block()
    assert "focus: team_pulse, by_title, by_department, people" in block
    assert "org structure" in block.lower() or "title and department" in block.lower()
    # Prefer kanban org boards over under-fold tenant/invoice bar theater
    assert "tenant_mix:" not in block
    assert "invoice_trail:" not in block
    assert "display: bar_chart" not in block
    assert "as tenant_admin:" in block
    assert "as finance_admin:" in block
    assert "as auditor:" in block


def test_suppliers_desk_declares_region_board_and_supplier_load() -> None:
    """Peer AP tools show vendor geography + multi-invoice load before flat roster."""
    block = _suppliers_desk_block()
    assert "by_region:" in block
    assert "group_by: region" in block
    assert "by_supplier:" in block
    assert "group_by: supplier" in block
    roster = "\n  roster:\n    source: Supplier"
    assert roster in block
    assert block.index("vendor_pulse:") < block.index("by_region:")
    assert block.index("by_region:") < block.index("by_supplier:")
    assert block.index("by_supplier:") < block.index(roster)
    # Prune under-fold status bar / twin invoice timeline theater
    assert "invoice_status_mix:" not in block
    assert "invoice_trail:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_suppliers_desk_ux_focus_org_before_roster() -> None:
    block = _suppliers_desk_block()
    assert "focus: vendor_pulse, by_region, by_supplier, roster" in block
    assert "region" in block.lower()
    assert "as finance:" in block
    assert "as finance_admin:" in block


def test_user_list_exposes_org_fields() -> None:
    text = SURFACES.read_text()
    start = text.index('surface user_list "Users":')
    end = text.index('surface user_detail "User":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block
    assert "filter: department, job_title" in block


def test_supplier_list_exposes_region_filter() -> None:
    text = SURFACES.read_text()
    start = text.index('surface supplier_list "Suppliers":')
    end = text.index('surface supplier_detail "Supplier":', start)
    block = text[start:end]
    assert "filter: region" in block
    assert "search: name, contact_email, region" in block


def test_user_seeds_span_departments_and_titles() -> None:
    """Buyer-true AP org needs multi-dept staff, not a 4-row persona monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    depts = {str(r.get("department") or "") for r in rows}
    titles = {str(r.get("job_title") or "") for r in rows}
    assert "Accounts Payable" in depts
    assert "Treasury" in depts
    assert "Controllership" in depts
    assert "Audit" in depts
    assert len(depts) >= 4
    assert "Requester" in titles
    assert "Approver" in titles
    assert "Finance Operator" in titles
    assert "Auditor" in titles
    # Extra IC rows use non-STABLE UUIDs (a100… reserved for personas)
    non_stable = [r for r in rows if str(r.get("id", "")).startswith("b2000000")]
    assert len(non_stable) >= 4
    counts = Counter(str(r.get("department") or "") for r in rows)
    multi = [d for d, n in counts.items() if n >= 2]
    assert len(multi) >= 3, f"expected multi-person depts, got {counts}"
    for row in rows:
        assert row.get("name")
        assert row.get("department")
        assert row.get("job_title")


def test_supplier_seeds_span_regions() -> None:
    """Vendor book needs multi-region placement for region kanban columns."""
    rows = [json.loads(line) for line in SUPPLIER_SEEDS.read_text().splitlines() if line.strip()]
    regions = {str(r.get("region") or "") for r in rows}
    assert "emea" in regions
    assert "amer" in regions
    assert "apac" in regions
    assert len(regions) >= 3
