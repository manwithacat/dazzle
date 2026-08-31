"""#1668 — invoice_ops steal: PO spoken exception, needs-you home, copy."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = (ROOT / "examples/invoice_ops/dsl/surfaces.dsl").read_text()
ENTITIES = (ROOT / "examples/invoice_ops/dsl/entities.dsl").read_text()
STORIES = (ROOT / "examples/invoice_ops/dsl/stories.dsl").read_text()
STEM = (ROOT / "examples/invoice_ops/stems/story-driven-jobs.md").read_text()


def _ws(name: str) -> str:
    marker = f'workspace {name} "'
    return SURFACES[SURFACES.index(marker) :]


def test_approve_requires_spoken_exception() -> None:
    assert "approval_exception: text optional" in ENTITIES
    assert "submitted -> approved: role(approver) requires approval_exception" in ENTITIES
    assert "released for settlement" in _ws("approval_desk").lower()
    assert "entity NeedsYou" not in ENTITIES
    assert "po_match: enum[matched, partial, unmatched, not_applicable]" in ENTITIES


def test_requester_home_is_needs_you() -> None:
    desk = _ws("my_invoices")
    assert "filter: status = rejected" in desk
    assert "filter: status = disputed" in desk
    assert "filter: status = approved" in desk.split("awaiting_settle:", 1)[1]
    assert (
        "status = paid" not in desk.split("my_status_board:", 1)[1].split("suppliers_nearby:", 1)[0]
    )
    focus = desk.split("as requester:", 1)[1]
    assert "drafts" in focus and "composition" not in focus.split("focus:", 1)[1].split("\n", 1)[0]
    assert "lines live on the slip" in desk.lower() or "notepad" in STORIES.lower()


def test_pay_desk_failed_rail_copy() -> None:
    desk = _ws("pay_desk")
    assert "failed rail" in desk.lower()
    assert "does not" in desk.lower()


def test_audit_today_attempts() -> None:
    desk = _ws("audit_review")
    attempts = desk.split("payment_attempts:", 1)[1].split("settled_invoices:", 1)[0]
    assert "created_at >= today" in attempts
    assert "earlier tries live on the invoice" in attempts.lower()


def test_stories_and_stem_name_the_steal() -> None:
    assert "approval_exception" in STORIES
    assert "still needs her" in STORIES
    assert "today's payment attempts" in STORIES.lower()
    assert "needs-you" in STEM.lower() or "still needs" in STEM.lower()
    assert "approval_exception" in STEM
