"""Swap / identity contract (ADR-0054, decision 0012)."""

from __future__ import annotations

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

from contracts.swap_identity import (  # noqa: E402
    bare_region_id_for_card_body,
    find_duplicate_ids,
    find_nested_region_hooks,
    validate_fragment_identity,
    validate_inner_swap_response,
)


def test_duplicate_ids() -> None:
    html = '<div id="a"></div><span id="a"></span><i id="b"></i>'
    assert find_duplicate_ids(html) == ["a"]


def test_nested_region_same_name() -> None:
    html = (
        '<div data-dz-region data-dz-region-name="device_attention" id="region-device_attention">'
        '<div data-dz-region data-dz-region-name="device_attention" id="region-device_attention">'
        "<p>x</p></div></div>"
    )
    v = find_nested_region_hooks(html)
    assert v, "expected nested region violation"
    assert any("device_attention" in x for x in v)


def test_flat_region_ok() -> None:
    html = (
        '<div id="region-device_attention-card-0" data-dz-region data-dz-region-name="device_attention">'
        '<div class="dz-queue-region"><span>row</span></div></div>'
    )
    assert find_nested_region_hooks(html) == []


def test_bare_region_from_card_body() -> None:
    assert (
        bare_region_id_for_card_body("region-device_attention-card-0") == "region-device_attention"
    )
    assert bare_region_id_for_card_body("region-open_task_queue") is None


def test_inner_swap_rejects_rewrap_chrome() -> None:
    response = (
        '<div data-dz-region data-dz-region-name="device_attention" '
        'id="region-device_attention"><p>body</p></div>'
    )
    v = validate_inner_swap_response(response, "region-device_attention-card-0")
    assert v
    assert any("re-declares bare id" in x or "data-dz-region chrome" in x for x in v)


def test_inner_swap_accepts_body_only() -> None:
    response = '<div class="dz-queue-region"><div class="dz-queue-row">ok</div></div>'
    assert validate_inner_swap_response(response, "region-device_attention-card-0") == []


def test_inner_swap_rejects_redeclaring_target_id() -> None:
    response = '<div id="region-x-card-1">oops</div>'
    v = validate_inner_swap_response(response, "region-x-card-1")
    assert any("re-declares id" in x for x in v)


def test_validate_fragment_identity_aggregates() -> None:
    html = (
        '<div data-dz-region data-dz-region-name="a">'
        '<div data-dz-region data-dz-region-name="a"></div></div>'
        '<i id="z"></i><b id="z"></b>'
    )
    v = validate_fragment_identity(html)
    assert any("duplicate id" in x for x in v)
    assert any("nested" in x for x in v)


def test_lint_fragment_flags_nested_region() -> None:
    sys.path.insert(0, str(PKG / "tools"))
    from template_lint import lint_fragment

    html = (
        '<div data-dz-region data-dz-region-name="q">'
        '<div data-dz-region data-dz-region-name="q"></div></div>'
    )
    issues = lint_fragment(html, location="t")
    assert any(i.code == "nested-region" for i in issues)


def test_exchange_envelope_inferred_and_explicit() -> None:
    sys.path.insert(0, str(PKG / "site"))
    from build_site import _exchange_envelope
    from registry import Exchange

    inferred = Exchange(
        "GET",
        "/x",
        "t",
        "rows only",
        "innerMorph of the region's body (`#{region}-body`)",
    )
    assert _exchange_envelope(inferred) == "body_only"
    explicit = Exchange(
        "GET",
        "/x",
        "t",
        "full element",
        "outerHTML of #panel",
        envelope="outer",
    )
    assert _exchange_envelope(explicit) == "outer"
    assert _exchange_envelope(Exchange("PUT", "/e", "t", "json", "none (raw fetch)")) == "none"
    assert (
        _exchange_envelope(
            Exchange("DELETE", "/e", "t", "row gone", "per the button's hx-target/hx-swap")
        )
        == "host_owned"
    )


def test_every_hyperpart_has_agent_visible_swap_contract() -> None:
    """Confidence gate: every Hyperpart ships an agent-visible Swap contract.

    Presentation-only parts declare envelope n/a; exchange parts resolve every
    Exchange to a known envelope (never unspecified).
    """
    sys.path.insert(0, str(PKG / "site"))
    from build_site import _ENVELOPE_VALUES, _exchange_envelope, _morph_swap_section
    from registry import HYPERPARTS

    agents = PKG / "site" / "agents"
    missing_section: list[str] = []
    unspecified: list[str] = []
    for h in HYPERPARTS:
        md_path = agents / f"{h.id}.md"
        assert md_path.is_file(), f"missing agent pack for {h.id}"
        md = md_path.read_text(encoding="utf-8")
        if "## Swap contract" not in md:
            missing_section.append(h.id)
        section = "\n".join(_morph_swap_section(h))
        assert "## Swap contract" in section, h.id
        assert "Exchange envelope" in section or "exchange envelope" in section.lower(), h.id
        if not h.exchanges:
            assert "n/a" in section or "No host HTMX exchange" in section, h.id
        for e in h.exchanges or ():
            env = _exchange_envelope(e)
            if env not in _ENVELOPE_VALUES:
                unspecified.append(f"{h.id}: {e.method} {e.endpoint} → {env!r}")
    assert not missing_section, f"agent packs missing ## Swap contract: {missing_section}"
    assert not unspecified, f"exchanges with unspecified envelope: {unspecified}"
