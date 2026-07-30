"""P0/P1 agent domain priors: lifecycle attach, arrow tokens, process candidates."""

from __future__ import annotations

from dazzle.domain_brief import lifecycles as sl
from dazzle.domain_brief.extract import extract_from_text
from dazzle.domain_brief.lifecycles import identify_lifecycles


class TestArrowChains:
    def test_underscore_states_stay_atomic(self) -> None:
        chains = sl.parse_arrow_chains("Tickets move open -> in_progress -> resolved -> closed.")
        assert chains
        _sentence, states = chains[0]
        assert states == ["open", "in_progress", "resolved", "closed"]

    def test_in_progress_not_split_in_identify(self) -> None:
        result = identify_lifecycles(
            "A Ticket is open -> in_progress -> closed.",
            ["Ticket"],
        )
        chains = [lc for lc in result["lifecycles"] if lc.get("source") == "arrow_chain"]
        assert chains
        assert chains[0]["states"] == ["open", "in_progress", "closed"]


class TestFuzzyEntityMatch:
    def test_support_ticket_matches_ticket_pattern(self) -> None:
        matched = sl.match_pattern_lifecycle("SupportTicket")
        assert matched is not None
        states, source = matched
        assert source == "pattern_match"
        assert "open" in states
        assert "closed" in states

    def test_invoice_matches_invoice_pattern(self) -> None:
        matched = sl.match_pattern_lifecycle("Invoice")
        assert matched is not None
        states, _ = matched
        assert "draft" in states
        assert "paid" in states or "approved" in states

    def test_persona_like_names_skip_lifecycle(self) -> None:
        assert sl.match_pattern_lifecycle("Approver") is None
        assert sl.match_pattern_lifecycle("Requester") is None

    def test_resolve_lifecycle_fuzzy(self) -> None:
        life = {"Ticket": ["open", "closed"]}
        assert sl.resolve_lifecycle_for_name("SupportTicket", life) == ["open", "closed"]
        assert sl.resolve_lifecycle_for_name("Comment", life) == []


class TestIdentifyLifecycles:
    def test_support_ticket_entity_gets_lifecycle(self) -> None:
        result = identify_lifecycles(
            "Support tickets are filed by customers and resolved by agents.",
            ["SupportTicket", "Comment"],
        )
        by_ent = {lc["entity"]: lc for lc in result["lifecycles"] if "states" in lc}
        assert "SupportTicket" in by_ent
        assert "open" in by_ent["SupportTicket"]["states"]

    def test_invoice_entity_gets_lifecycle(self) -> None:
        result = identify_lifecycles(
            "Invoices are submitted for approval then paid by finance.",
            ["Invoice", "Supplier"],
        )
        by_ent = {lc["entity"]: lc for lc in result["lifecycles"] if "states" in lc}
        assert "Invoice" in by_ent

    def test_arrow_chain_beats_pattern(self) -> None:
        result = identify_lifecycles(
            "Orders move quoted->packed->shipped.",
            ["Order"],
        )
        order_lcs = [lc for lc in result["lifecycles"] if lc["entity"] == "Order"]
        assert len(order_lcs) == 1
        assert order_lcs[0]["source"] == "arrow_chain"
        assert order_lcs[0]["states"] == ["quoted", "packed", "shipped"]

    def test_process_candidates_for_approval_domain(self) -> None:
        result = identify_lifecycles(
            (
                "Requesters submit invoices. Approvers approve or reject. "
                "Finance pays after approval."
            ),
            ["Invoice"],
        )
        ids = {c["id_hint"] for c in result.get("process_candidates") or []}
        assert "approval_flow" in ids or "settlement" in ids


class TestDomainExtractLifecyclePriors:
    INVOICE_BRIEF = """
# Invoice Ops

A multi-tenant supplier invoice system.

## Personas

- Requester submits invoices for approval
- Approver reviews and approves or rejects
- Finance processes payment after approval
- Auditor reviews paid invoices read-only

## Entities

An Invoice is a supplier bill moving through draft, submitted, approved, and paid.
A Supplier is a vendor that bills a tenant.
A Tenant is a customer company.

Requesters submit invoices. Approvers approve. Finance pays settled invoices.
"""

    SUPPORT_BRIEF = """
# Support Tickets

A SupportTicket is a customer issue from open to resolved.
A Comment is a note on a ticket.

Agents work the queue. Managers handle escalations. Customers submit tickets and follow their own.
"""

    def test_invoice_noun_gets_lifecycle_hint(self) -> None:
        ad = extract_from_text(self.INVOICE_BRIEF, source_path="inline")
        by_name = {n.name: n for n in ad.nouns}
        assert "Invoice" in by_name
        assert by_name["Invoice"].lifecycle_hint

    def test_support_ticket_gets_ticket_lifecycle(self) -> None:
        ad = extract_from_text(self.SUPPORT_BRIEF, source_path="inline")
        by_name = {n.name: n for n in ad.nouns}
        assert "SupportTicket" in by_name
        life = by_name["SupportTicket"].lifecycle_hint
        assert life
        assert "open" in life

    def test_process_candidates_present_for_invoice(self) -> None:
        ad = extract_from_text(self.INVOICE_BRIEF, source_path="inline")
        ids = {p.id_hint for p in ad.process_candidates}
        assert ids & {"approval_flow", "settlement", "escalation"}

    def test_generic_user_persona_filtered_without_job(self) -> None:
        brief = """
# Widget App

A Widget is a thing users look at in the product marketing page.

A Manager assigns Widgets. A Member completes assigned Widgets.
Manager can assign. Member can complete.
"""
        ad = extract_from_text(brief, source_path="inline")
        ids = {p.id_hint for p in ad.personas}
        assert "user" not in ids
        assert "manager" in ids or "member" in ids
