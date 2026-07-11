"""Cross-boundary lock: the REAL Dazzle pipeline's emitted DOM must satisfy
the HM DOM contract. This is the gate that would have caught #1573 at the
contract layer: a hydrated badge row with producer-shaped filter_options is
rendered through build_data_table → render_data_table_rows and validated
against contracts/grid_edit.py's DOM_CONTRACT (fragment mode — the grid
root is page furniture, validated in HM's own exemplar tests)."""

import uuid

import pytest

from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.render.fragment.renderer._data_row import render_data_table_rows
from tests.unit.hm_contract_registry import REPO_ROOT, load_hm_module

pytestmark = pytest.mark.gate

_KIT = load_hm_module("contracts/_kit.py")

PRODUCER_SHAPES = [
    [{"value": "open", "label": "Open"}, {"value": "closed", "label": "Closed"}],
    [("open", "Open"), ("closed", "Closed")],
    ["open", "closed"],  # the #1573 crash shape
]


@pytest.mark.parametrize("options", PRODUCER_SHAPES)
def test_hydrated_badge_row_conforms_to_grid_edit_contract(options) -> None:
    pytest.importorskip("fastapi")
    grid_edit = load_hm_module("contracts/grid_edit.py")
    table = {
        "columns": [
            {"key": "title", "label": "Title", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge", "filter_options": options},
        ],
        "entity_name": "Ticket",
        "api_endpoint": "/tickets",
        "table_id": "t-conformance",
        "detail_url_template": "/app/ticket/{id}",
        "inline_editable": ["title", "status"],
    }
    row = {"id": str(uuid.uuid4()), "title": "x", "status": "open"}
    html = render_data_table_rows(build_data_table(table, [row]))
    violations = _KIT.validate_dom(html, grid_edit.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-grid-edit=" in html  # the seam actually rendered


def test_typed_path_is_sole_emitter() -> None:
    """HM contract attribute *assembly* is allowed ONLY in ingest.py.

    Families (#1577): ``data-dz-edit-``, ``data-dz-tags``, ``data-dz-combobox``,
    ``data-dz-money``. Docstrings and runtime readers (has_attr) are ignored;
    HTML f-string / quoted assembly outside ingest fails.
    """
    import re

    # Quoted/f-string assembly of contract markers (not bare identifier reads).
    assembly = re.compile(
        r"""(?x)
        (?:f['\"].{0,80}data-dz-(?:edit-|tags|combobox|money))
        | (?:['\"]data-dz-(?:edit-|tags|combobox|money))
        """
    )
    # Readers / docs that mention the attr without assembling HTML.
    allow_name = {
        "fidelity_scorer.py",  # has_attr reader
        "forms.py",  # primitive docstrings
        "form_field.py",  # routing comments
    }
    offenders: list[str] = []
    for p in (REPO_ROOT / "src" / "dazzle").rglob("*.py"):
        if p.name == "ingest.py" and p.parent.name == "fragment":
            continue
        if p.name in allow_name:
            continue
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if assembly.search(line):
                # has_attr / get_attr are readers, not emitters
                if "has_attr" in line or "get_attr" in line:
                    continue
                offenders.append(f"{p.relative_to(REPO_ROOT)}:{i}")
    assert not offenders, (
        f"HM contract attrs assembled outside ingest.py: {offenders} — "
        f"use the typed seam model + attr helper."
    )


def test_widget_combobox_conforms_to_combobox_contract() -> None:
    """Real Dazzle WidgetCombobox emission must satisfy contracts/combobox.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import WidgetCombobox
    from dazzle.render.fragment.renderer import FragmentRenderer

    combobox = load_hm_module("contracts/combobox.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = WidgetCombobox(
        name="priority",
        label="Priority",
        options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
        placeholder="Select…",
        initial_value="medium",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, combobox.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-combobox" in html
    assert 'name="priority"' in html


def test_tags_field_conforms_to_tags_contract() -> None:
    """Real Dazzle TagsField form primitive emission must satisfy contracts/tags.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import TagsField as FormTagsField
    from dazzle.render.fragment.renderer import FragmentRenderer

    tags_mod = load_hm_module("contracts/tags.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormTagsField(
        name="labels",
        label="Labels",
        placeholder="Add a label…",
        initial_value="urgent,backend",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, tags_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-tags" in html
    assert 'name="labels"' in html


def test_money_field_fixed_conforms_to_money_contract() -> None:
    """Fixed-currency MoneyField emission must satisfy contracts/money.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import MoneyField as FormMoneyField
    from dazzle.render.fragment.renderer import FragmentRenderer

    money_mod = load_hm_module("contracts/money.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormMoneyField(
        name="amount",
        label="Amount",
        currency_code="GBP",
        scale="2",
        symbol="£",
        currency_fixed=True,
        minor_initial="1250",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, money_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-money" in html
    assert 'data-dz-currency="GBP"' in html
    assert 'data-dz-scale="2"' in html


def test_money_field_selector_conforms_to_money_contract() -> None:
    """Selector-mode MoneyField root must still carry data-dz-currency (DOM_CONTRACT)."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import MoneyField as FormMoneyField
    from dazzle.render.fragment.renderer import FragmentRenderer

    money_mod = load_hm_module("contracts/money.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormMoneyField(
        name="fee",
        label="Fee",
        currency_code="USD",
        scale="2",
        symbol="$",
        currency_fixed=False,
        currency_options=(("USD", "2", "$"), ("GBP", "2", "£")),
        minor_initial="99",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, money_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-money" in html
    assert 'data-dz-currency="USD"' in html
    assert 'data-dz-scale="2"' in html
    assert 'name="fee_currency"' in html
