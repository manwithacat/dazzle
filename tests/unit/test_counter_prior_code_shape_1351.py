"""#1351: counter_prior code_shape= must match prose descriptions, not just code regexes.

CLAUDE.md instructs agents to call `knowledge counter_prior code_shape="<one-sentence
description>"` before emitting user-app code. A description is prose, so the handler
must fall back to triggers_text when the triggers_code regexes don't hit — otherwise
the documented call silently returns 0 matches and the agent proceeds unwarned.
"""

import json

import dazzle.mcp.server.handlers.knowledge as kn
from dazzle.mcp.semantics_kb.counter_priors import CounterPrior


def _entry(entry_id: str, triggers_text: list[str], triggers_code: list[str]) -> CounterPrior:
    return CounterPrior(
        id=entry_id,
        name=entry_id,
        layer="inference",
        summary="s",
        triggers_text=triggers_text,
        triggers_code=triggers_code,
        file_path="x",
        body="...",
    )


def _matches(out: str) -> list[str]:
    return [m["id"] for m in json.loads(out)["matches"]]


def test_code_shape_prose_description_hits_text_triggers(monkeypatch):
    # The regression: a textbook N+1 description must match via code_shape.
    cp = _entry(
        "n_plus_one",
        triggers_text=["for each parent, fetch children", "fetch related"],
        triggers_code=[r"for\s+\w+\s+in\s+\w+:\s*\n\s+\w+_repo\.list\("],
    )
    monkeypatch.setattr(kn, "load_all_counter_priors", lambda: [cp])

    out = kn.counter_prior_handler(
        {"code_shape": "loop that will, for each parent, fetch children to compute totals"}
    )
    assert _matches(out) == ["n_plus_one"]


def test_code_shape_literal_code_still_hits_regexes(monkeypatch):
    cp = _entry(
        "n_plus_one",
        triggers_text=["fetch related"],
        triggers_code=[r"for\s+\w+\s+in\s+\w+:\s*\n\s+\w+_repo\.list\("],
    )
    monkeypatch.setattr(kn, "load_all_counter_priors", lambda: [cp])

    out = kn.counter_prior_handler(
        {"code_shape": "for inv in invoices:\n    client_repo.list(inv.client)"}
    )
    assert _matches(out) == ["n_plus_one"]


def test_code_shape_dedupes_entries_matching_both_channels(monkeypatch):
    cp = _entry(
        "both_channels",
        triggers_text=["loop over the rows"],
        triggers_code=[r"for\s+\w+\s+in\s+\w+:"],
    )
    monkeypatch.setattr(kn, "load_all_counter_priors", lambda: [cp])

    # Sample hits the code regex AND contains the text trigger.
    out = kn.counter_prior_handler({"code_shape": "loop over the rows: for r in rows:"})
    assert _matches(out) == ["both_channels"]


def test_code_shape_code_hits_rank_before_text_fallback(monkeypatch):
    code_cp = _entry("code_hit", triggers_text=[], triggers_code=[r"for\s+\w+\s+in\s+\w+:"])
    text_cp = _entry("text_hit", triggers_text=["loop over the rows"], triggers_code=[])
    monkeypatch.setattr(kn, "load_all_counter_priors", lambda: [text_cp, code_cp])

    out = kn.counter_prior_handler({"code_shape": "loop over the rows: for r in rows:"})
    assert _matches(out) == ["code_hit", "text_hit"]
