"""ADR-0049 Phase 3b — substrate plain-field parity with the legacy
`form_renderer.render_form_field` standard-field contract.

The pre-flip adversarial review found the substrate's *common-case* field
emitters (`_emit_field`/`_emit_combobox`) had regressed against legacy while the
rich widgets were ported at parity. This pins the five fixes so they can't
silently regress again:
  1. required enums get a leading disabled placeholder option (else `required`
     is a no-op → silent wrong-default writes);
  2. CREATE-mode `default:` values seed plain fields + enums;
  3. `data-dazzle-field` on every plain input (QA-harness / a11y selectors);
  4. `aria-required` + required indicator + `for`/`id` label association;
  5. `help:` text renders as a hint paragraph with `aria-describedby`.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import FragmentRenderer

_R = FragmentRenderer()


def _render(field_dict: dict) -> str:
    return _R.render(_field_to_primitive(field_dict))


# ── 1. required enum placeholder (data correctness) ──────────────────────────


def test_required_enum_has_disabled_placeholder_selected() -> None:
    html = _render(
        {
            "name": "priority",
            "label": "Priority",
            "required": True,
            "options": [("low", "Low"), ("high", "High")],
        }
    )
    # Leading disabled+selected empty option so a required select starts blank.
    assert '<option value="" disabled selected>' in html
    # The first real option must NOT be auto-selected.
    assert '<option value="low" selected>' not in html


def test_enum_with_value_does_not_select_placeholder() -> None:
    html = _render(
        {"name": "p", "label": "P", "value": "high", "options": [("low", "Low"), ("high", "High")]}
    )
    assert '<option value="" disabled>' in html  # present but not selected
    assert '<option value="high" selected>' in html


# ── 2. CREATE default values ─────────────────────────────────────────────────


def test_number_default_seeds_value_on_create() -> None:
    html = _render({"name": "qty", "label": "Qty", "kind": "number", "default": "5"})
    assert 'value="5"' in html


def test_enum_default_selects_option_on_create() -> None:
    html = _render(
        {
            "name": "st",
            "label": "St",
            "default": "high",
            "options": [("low", "Low"), ("high", "High")],
        }
    )
    assert '<option value="high" selected>' in html


def test_edit_value_wins_over_default() -> None:
    html = _render({"name": "qty", "label": "Qty", "kind": "number", "default": "5", "value": "12"})
    assert 'value="12"' in html
    assert 'value="5"' not in html


# ── 3 + 4. data-dazzle-field + a11y on plain fields ──────────────────────────


def test_plain_input_carries_harness_and_a11y_attrs() -> None:
    html = _render({"name": "title", "label": "Title", "kind": "text", "required": True})
    assert 'id="field-title"' in html
    assert 'data-dazzle-field="title"' in html
    assert 'class="dz-form-input"' in html
    assert 'required aria-required="true"' in html
    # label association + required indicator.
    assert '<label for="field-title" class="dz-form-label">' in html
    assert 'class="dz-form-required"' in html
    assert "(required)" in html


def test_textarea_parity() -> None:
    html = _render({"name": "desc", "label": "Desc", "kind": "textarea"})
    assert '<textarea id="field-desc" name="desc" data-dazzle-field="desc"' in html
    assert 'class="dz-form-input dz-form-textarea"' in html
    assert 'rows="4"' in html


def test_checkbox_parity() -> None:
    html = _render({"name": "done", "label": "Done", "kind": "checkbox", "value": "true"})
    assert 'type="checkbox"' in html
    assert 'id="field-done"' in html
    assert 'data-dazzle-field="done"' in html
    assert 'class="dz-form-checkbox"' in html
    assert " checked" in html


def test_date_input_suppresses_placeholder() -> None:
    html = _render({"name": "due", "label": "Due", "kind": "date", "placeholder": "ignored"})
    assert 'type="date"' in html
    assert "ignored" not in html  # native date inputs drop the placeholder (legacy parity)


# ── 5. help text ─────────────────────────────────────────────────────────────


def test_help_renders_hint_paragraph_and_describedby() -> None:
    html = _render(
        {"name": "email", "label": "Email", "kind": "email", "help": "We never share it"}
    )
    assert '<p id="hint-email" class="dz-form-hint">We never share it</p>' in html
    assert 'aria-describedby="hint-email"' in html


def test_no_help_no_describedby() -> None:
    html = _render({"name": "x", "label": "X", "kind": "text"})
    assert "aria-describedby" not in html
    assert "dz-form-hint" not in html


# NOTE: the `def test_field_wrapper_matches_legacy` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
