"""Post-5.8 Goal B empty_region_honesty — acme_billing desks (cycle 1828 + 1853)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_billing_omits_membership_mix_under_fold() -> None:
    """Admin home: dual attention + composition + notes — not role-mix chart void."""
    block = _workspace_block("billing")
    assert "portfolio_metrics:" in block
    assert "open_invoices:" in block
    assert "sensitive_flags:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "membership_mix:" not in block
    # Focus spine stays chart-free; bar_chart coverage may sit under fold.
    # Goal B media invoice_packets leads the fold (cycle 1885).
    assert (
        "focus: invoice_packets, portfolio_metrics, open_invoices, "
        "sensitive_flags, dunning_board, composition, live_conversation" in block
    )
    assert "invoice_by_project" not in block.split("focus:")[1].split("\n")[0]
    assert "sensitive_share" not in block.split("focus:")[1].split("\n")[0]


def test_my_work_omits_chart_and_membership_timeline() -> None:
    """Member desk: assigned projects + invoices only — not status chart / roster dump."""
    block = _workspace_block("my_work")
    assert "my_pulse:" in block
    assert "assigned_projects:" in block
    assert "my_invoices:" in block
    assert "team_context:" not in block
    assert "my_invoice_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_projects_home_omits_load_chart_and_twin_trail() -> None:
    """Projects desk: kanban + recent invoices — not invoice-by-project bar / trail."""
    block = _workspace_block("projects_home")
    assert "project_pulse:" in block
    assert "project_queue:" in block
    assert "recent_invoices:" in block
    assert "invoice_by_project:" not in block
    assert "project_trail:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_invoices_home_omits_status_mix_and_bill_timeline() -> None:
    """Invoice desk: conversation + board + projects — not status chart / twin timeline."""
    block = _workspace_block("invoices_home")
    assert "live_conversation:" in block
    assert "invoice_pulse:" in block
    assert "open_bills:" in block
    assert "projects_context:" in block
    assert "bill_timeline:" not in block
    assert "invoice_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "focus: live_conversation, invoice_pulse, open_bills" in block


def test_team_home_omits_role_chart_and_roster_timeline() -> None:
    """Team desk: people + membership queues — not role bar / twin roster timeline."""
    block = _workspace_block("team_home")
    assert "membership_pulse:" in block
    assert "people:" in block
    assert "membership_queue:" in block
    assert "roster:" not in block or "org_roster:" in _workspace_block("orgs_home")
    # Explicit twin removed from this desk (not org_roster elsewhere).
    assert "\n  roster:" not in block
    assert "membership_chart:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_orgs_home_omits_project_trail_and_load_chart() -> None:
    """Orgs desk: roster + open bills — not project timeline / invoice-load bar."""
    block = _workspace_block("orgs_home")
    assert "org_pulse:" in block
    assert "org_roster:" in block
    assert "open_bills:" in block
    assert "project_context:" not in block
    assert "org_invoice_load:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_sensitive_review_omits_trail_and_load_bar() -> None:
    """Sensitivity desk: pulse + queue + project cards — not trail/bar thrash."""
    block = _workspace_block("sensitive_review")
    assert "sensitivity_pulse:" in block
    assert "sensitive_queue:" in block
    assert "project_cards:" in block
    assert "invoice_trail:" not in block
    assert "project_invoice_load:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_public_billing_omits_trail_and_load_bar() -> None:
    """Public desk: pulse + queue + project cards — not trail/bar thrash."""
    block = _workspace_block("public_billing")
    assert "public_pulse:" in block
    assert "public_queue:" in block
    assert "project_cards:" in block
    assert "public_trail:" not in block
    assert "project_load:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_org_pulse_omits_people_trail_and_project_mix() -> None:
    """Org pulse: metrics + org/project queues — not people timeline / mix bar."""
    block = _workspace_block("org_pulse")
    assert "pulse_metrics:" in block
    assert "org_queue:" in block
    assert "project_cards:" in block
    assert "people_trail:" not in block
    assert "project_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_acme_billing_hosts_bar_chart_coverage_under_billing() -> None:
    """Secondary prune must not leave display: bar_chart uncovered in this app."""
    block = _workspace_block("billing")
    assert "invoice_by_project:" in block
    assert "sensitive_share:" in block
    assert block.count("display: bar_chart") >= 2
    text = SURFACES.read_text()
    assert text.count("display: bar_chart") >= 2
