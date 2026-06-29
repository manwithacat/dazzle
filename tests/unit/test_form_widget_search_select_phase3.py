"""ADR-0049 Phase 3a — substrate `SearchSelect` parity with the legacy
`form_renderer._render_search_select` (`source:` typeahead).

The legacy renderer is the only `search_select` implementation today and is
exercised by ~21 fleet DSL files; its DOM contract is also enforced by the
fidelity scorer (`fidelity_scorer._check_*_interaction`). This pins the
substrate `SearchSelect` to the same mount-attribute contract so the 3b flip
keeps fidelity green and the widget keeps working.

The fidelity scorer requires (per surface with a `source=` field):
  - `search-input-{name}` id (MISSING_SOURCE_WIDGET — critical)
  - `search-results-` presence
  - `hx-indicator` (loading)
  - `delay:` debounce in `hx-trigger`
  - an empty-state phrase ("type at least" / "no results")
  - `aria-invalid` / `text-error` / `destructive` error wiring (only on error)
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import FragmentRenderer, SearchSelect


def _render(field_dict: dict) -> str:
    prim = _field_to_primitive(field_dict)
    assert isinstance(prim, SearchSelect), f"expected SearchSelect, got {type(prim).__name__}"
    return FragmentRenderer().render(prim)


_BASE = {
    "name": "company",
    "label": "Company",
    "required": True,
    "source": {
        "endpoint": "/_dazzle/fragments/search?source=companieshouse",
        "debounce_ms": 400,
        "min_chars": 3,
    },
}


def test_source_field_maps_to_search_select() -> None:
    prim = _field_to_primitive(_BASE)
    assert isinstance(prim, SearchSelect)
    assert prim.endpoint.value == "/_dazzle/fragments/search?source=companieshouse"
    assert prim.debounce_ms == 400
    assert prim.min_chars == 3
    assert prim.required is True


def test_fidelity_contract_tokens_present() -> None:
    html = _render(_BASE)
    # Critical: the id the fidelity scorer checks for MISSING_SOURCE_WIDGET.
    assert 'id="search-input-company"' in html
    assert 'id="search-results-company"' in html
    # Loading indicator + debounce + empty-state phrase.
    assert "hx-indicator=" in html
    assert "delay:400ms" in html
    assert "Type at least 3 characters" in html


def test_hidden_input_holds_selected_id() -> None:
    html = _render(_BASE)
    # The form posts the hidden input (the FK), not the visible search text.
    assert '<input type="hidden" name="company" id="field-company"' in html
    assert 'data-dazzle-field="company"' in html


def test_endpoint_and_typeahead_wiring() -> None:
    html = _render(_BASE)
    assert 'hx-get="/_dazzle/fragments/search?source=companieshouse"' in html
    assert 'hx-trigger="keyup changed delay:400ms"' in html
    assert 'hx-target="#search-results-company"' in html
    assert 'hx-params="q"' in html
    # min_chars>0 → hx-vals carries the floor.
    assert "hx-vals='{\"min_chars\": 3}'" in html
    # Self-contained Alpine open/close (no external controller).
    assert 'x-data="{ open: false }"' in html
    assert 'data-dz-widget="search_select"' in html


def test_required_emits_aria_required() -> None:
    html = _render(_BASE)
    assert 'required aria-required="true"' in html


def test_edit_mode_prefills_visible_and_hidden() -> None:
    edited = {
        **_BASE,
        "value": "abc-123",
        "initial_label": "Acme Ltd",
    }
    html = _render(edited)
    # Hidden input carries the FK id; visible input shows the display label.
    assert 'name="company" id="field-company" data-dazzle-field="company" value="abc-123"' in html
    assert 'value="Acme Ltd"' in html


def test_min_chars_zero_omits_hx_vals() -> None:
    field = {
        "name": "owner",
        "label": "Owner",
        "source": {"endpoint": "/search?source=users", "debounce_ms": 300, "min_chars": 0},
    }
    html = _render(field)
    assert "hx-vals=" not in html
    assert "delay:300ms" in html


def test_parity_with_legacy_search_select() -> None:
    """Direct attribute-parity check vs the legacy renderer for the
    contract attrs the client JS + fidelity scorer depend on."""
    from types import SimpleNamespace

    from dazzle.page.runtime.form_renderer import _render_search_select

    legacy_field = SimpleNamespace(
        name="company",
        label="Company",
        required=True,
        placeholder="",
        source=SimpleNamespace(
            endpoint="/_dazzle/fragments/search?source=companieshouse",
            debounce_ms=400,
            min_chars=3,
        ),
    )
    legacy = _render_search_select(legacy_field, None, {})
    substrate = _render(_BASE)
    # The load-bearing contract tokens must appear in BOTH.
    for token in (
        'id="search-input-company"',
        'id="search-results-company"',
        'id="field-company"',
        'hx-get="/_dazzle/fragments/search?source=companieshouse"',
        'hx-trigger="keyup changed delay:400ms"',
        'hx-target="#search-results-company"',
        'hx-indicator="#search-spinner-company"',
        'hx-params="q"',
        'data-dz-widget="search_select"',
        'role="combobox"',
        'aria-controls="search-results-company"',
        "Type at least 3 characters",
    ):
        assert token in legacy, f"legacy missing {token!r} (test assumption stale)"
        assert token in substrate, f"substrate missing {token!r} — parity break"
