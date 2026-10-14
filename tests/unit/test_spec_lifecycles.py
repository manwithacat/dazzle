"""spec_analyze lifecycle priors: lifecycle attach, arrow tokens, process candidates."""

from __future__ import annotations

from dazzle.mcp.server.handlers import spec_lifecycles as sl
from dazzle.mcp.server.handlers.spec_lifecycles import identify_lifecycles


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
