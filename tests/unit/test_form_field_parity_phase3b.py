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

import pytest

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import FragmentRenderer

_R = FragmentRenderer()


def _render(field_dict: dict) -> str:
    return _R.render(_field_to_primitive(field_dict))


_ENUM = [("low", "Low"), ("high", "High")]


@pytest.mark.parametrize(
    ("field", "present", "absent"),
    [
        # 1. required enum placeholder (data correctness)
        pytest.param(
            {"name": "priority", "label": "Priority", "required": True, "options": _ENUM},
            ['<option value="" disabled selected>'],
            ['<option value="low" selected>'],
            id="required_enum_starts_on_disabled_placeholder",
        ),
        pytest.param(
            {"name": "p", "label": "P", "value": "high", "options": _ENUM},
            ['<option value="" disabled>', '<option value="high" selected>'],
            ['<option value="" disabled selected>'],
            id="enum_with_value_selects_value_not_placeholder",
        ),
        # 2. CREATE default values
        pytest.param(
            {"name": "qty", "label": "Qty", "kind": "number", "default": "5"},
            ['value="5"'],
            [],
            id="number_default_seeds_value_on_create",
        ),
        pytest.param(
            {"name": "st", "label": "St", "default": "high", "options": _ENUM},
            ['<option value="high" selected>'],
            ['<option value="low" selected>'],
            id="enum_default_selects_option_on_create",
        ),
        pytest.param(
            {"name": "qty", "label": "Qty", "kind": "number", "default": "5", "value": "12"},
            ['value="12"'],
            ['value="5"'],
            id="edit_value_wins_over_default",
        ),
        # 3 + 4. data-dazzle-field + a11y on plain fields
        pytest.param(
            {"name": "title", "label": "Title", "kind": "text", "required": True},
            [
                'id="field-title"',
                'data-dazzle-field="title"',
                'class="dz-form-input"',
                'required aria-required="true"',
                '<label for="field-title" class="dz-form-label">',
                'class="dz-form-required"',
                "(required)",
            ],
            [],
            id="plain_input_harness_and_a11y_attrs",
        ),
        pytest.param(
            {"name": "desc", "label": "Desc", "kind": "textarea"},
            [
                '<textarea id="field-desc" name="desc" data-dazzle-field="desc"',
                'class="dz-form-input dz-form-textarea"',
                'rows="4"',
            ],
            [],
            id="textarea",
        ),
        pytest.param(
            {"name": "done", "label": "Done", "kind": "checkbox", "value": "true"},
            [
                'type="checkbox"',
                'id="field-done"',
                'data-dazzle-field="done"',
                'class="dz-form-checkbox"',
                " checked",
            ],
            [],
            id="checkbox",
        ),
        pytest.param(
            {"name": "due", "label": "Due", "kind": "date", "placeholder": "ignored"},
            ['type="date"'],
            ["ignored"],
            id="native_date_input_drops_placeholder",
        ),
        # 5. help text
        pytest.param(
            {"name": "email", "label": "Email", "kind": "email", "help": "We never share it"},
            [
                '<p id="hint-email" class="dz-form-hint">We never share it</p>',
                'aria-describedby="hint-email"',
            ],
            [],
            id="help_renders_hint_paragraph_and_describedby",
        ),
        pytest.param(
            {"name": "x", "label": "X", "kind": "text"},
            [],
            ["aria-describedby", "dz-form-hint"],
            id="no_help_no_describedby",
        ),
    ],
)
def test_plain_field_render(field: dict, present: list[str], absent: list[str]) -> None:
    html = _render(field)
    for fragment in present:
        assert fragment in html
    for fragment in absent:
        assert fragment not in html


@pytest.mark.parametrize(
    ("kind", "value", "group", "companion", "companion_label"),
    [
        pytest.param(
            "number",
            "12",
            "data-dz-number-group",
            "data-dz-number-value",
            "Number value",
            id="number_cycle_2149",
        ),
        pytest.param(
            "date",
            "2026-06-01",
            "data-dz-date-group",
            "data-dz-date-iso",
            "ISO date",
            id="date_cycle_2145",
        ),
        pytest.param(
            "time",
            "14:30",
            "data-dz-time-group",
            "data-dz-time-iso",
            "ISO time",
            id="time_cycle_2144",
        ),
        pytest.param(
            "datetime-local",
            "2026-06-01T14:30",
            "data-dz-time-group",
            "data-dz-time-iso",
            "ISO datetime",
            id="datetime_local",
        ),
    ],
)
def test_typed_input_emits_unsubmitted_companion(
    kind: str, value: str, group: str, companion: str, companion_label: str
) -> None:
    """Leftover junk must not invent a number/date/time: the typed input gets a
    companion read-out that has no `name`, so only the real input is submitted."""
    html = _render(
        {"name": "f", "label": "F", "kind": kind, "value": value, "placeholder": "ignored"}
    )
    assert f'type="{kind}"' in html
    assert group in html
    assert companion in html
    assert f'aria-label="{companion_label}"' in html
    assert f'value="{value}"' in html
    assert 'name="f"' in html
    assert html.count("name=") == 1
    if kind != "number":  # native date/time inputs drop the placeholder (legacy parity)
        assert "ignored" not in html


# NOTE: the `def test_field_wrapper_matches_legacy` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
