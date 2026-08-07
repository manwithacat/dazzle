"""#1646 — detail money expanded keys + related-tab finger-scale budget.

Pilot (CyFuture): VIEW detail money fields ignored ``{name}_minor`` /
``{name}_currency``; related tabs hard-coded ``page_size=50``.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.dispatch_ctx import _one_detail_field_dict


def _money_field(name: str = "box5_net_vat", *, currency: str = "GBP") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        key=name,
        label=name.replace("_", " ").title(),
        type="money",
        widget=None,
        extra={"currency_code": currency},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )


def test_detail_money_prefers_minor_when_bare_empty() -> None:
    """Bare field empty → read ``{name}_minor`` (list/detail parity)."""
    item = {
        "id": "inv-1",
        "box5_net_vat_minor": 1250,
        "box5_net_vat_currency": "GBP",
    }
    out = _one_detail_field_dict(_money_field(), item)
    assert out["kind"] == "money"
    assert out["value"] == 1250
    assert out["currency_code"] == "GBP"


def test_detail_money_uses_item_currency_when_extra_missing() -> None:
    item = {
        "fee_minor": 9900,
        "fee_currency": "EUR",
    }
    f = SimpleNamespace(
        name="fee",
        key="fee",
        label="Fee",
        type="money",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    out = _one_detail_field_dict(f, item)
    assert out["value"] == 9900
    assert out["currency_code"] == "EUR"


def test_detail_money_bare_value_wins_when_present() -> None:
    item = {
        "box5_net_vat": 500,
        "box5_net_vat_minor": 99999,
        "box5_net_vat_currency": "GBP",
    }
    out = _one_detail_field_dict(_money_field(), item)
    assert out["value"] == 500


def test_detail_money_defaults_currency_gbp() -> None:
    f = SimpleNamespace(
        name="amount",
        key="amount",
        label="Amount",
        type="money",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    item = {"amount_minor": 100}
    out = _one_detail_field_dict(f, item)
    assert out["value"] == 100
    assert out["currency_code"] == "GBP"


def test_related_tab_page_size_default_is_finger_scale() -> None:
    """Source pins the related-tab budget (no warehouse 50 default)."""
    from pathlib import Path

    src = Path("src/dazzle/http/runtime/page_routes.py").read_text(encoding="utf-8")
    assert "page_size=50" not in src or "_related_page_size" in src
    assert "_related_page_size" in src
    assert "max(1, min(_related_page_size, 50))" in src
    # default 8 appears as budget when tab has no page_size/limit
    assert "if _tab_budget else 8" in src


def test_related_group_dsl_limit_parses() -> None:
    """related limit: / page_size: land on IR RelatedGroup (#1646 DSL budget)."""
    from pathlib import Path

    from dazzle.core.dsl_parser_impl import parse_dsl

    src = """module t
app t "T":
  security_profile: basic

entity Parent "Parent":
  id: uuid pk
  name: str(100)

entity Child "Child":
  id: uuid pk
  parent: ref Parent
  title: str(100)

surface parent_detail "Parent":
  uses entity Parent
  mode: view
  section main:
    field name "Name"
  related kids "Kids":
    display: queue
    show: Child
    columns: title
    limit: 5
"""
    _m, _a, _t, _c, _u, frag = parse_dsl(src, Path("t.dsl"))
    surface = next(s for s in frag.surfaces if s.name == "parent_detail")
    assert len(surface.related_groups) == 1
    rg = surface.related_groups[0]
    assert rg.name == "kids"
    assert rg.limit == 5


def test_related_group_dsl_page_size_alias() -> None:
    from pathlib import Path

    from dazzle.core.dsl_parser_impl import parse_dsl

    src = """module t
app t "T":
  security_profile: basic

entity Parent "Parent":
  id: uuid pk
  name: str(100)

entity Child "Child":
  id: uuid pk
  parent: ref Parent
  title: str(100)

surface parent_detail "Parent":
  uses entity Parent
  mode: view
  section main:
    field name "Name"
  related kids "Kids":
    display: table
    show: Child
    page_size: 3
"""
    _m, _a, _t, _c, _u, frag = parse_dsl(src, Path("t.dsl"))
    surface = next(s for s in frag.surfaces if s.name == "parent_detail")
    assert surface.related_groups[0].limit == 3


def test_related_tab_context_carries_budget() -> None:
    """RelatedTabContext accepts page_size/limit for page_routes honour path."""
    from dazzle.render.context import ColumnContext, RelatedTabContext

    tab = RelatedTabContext(
        tab_id="tab-child",
        label="Kids",
        entity_name="Child",
        api_endpoint="/children",
        filter_field="parent",
        columns=[ColumnContext(key="title", label="Title", type="text")],
        page_size=5,
        limit=5,
    )
    assert tab.page_size == 5
    assert tab.limit == 5
    # page_routes reads either attr
    budget = getattr(tab, "page_size", None) or getattr(tab, "limit", None)
    assert int(budget) == 5


def test_template_compiler_stamps_related_budget() -> None:
    """Group limit is copied onto RelatedTabContext tabs in the group."""
    from pathlib import Path

    src = Path("src/dazzle/page/converters/template_compiler.py").read_text(
        encoding="utf-8"
    )
    assert 'getattr(group, "limit", None)' in src
    assert '"page_size": _budget_i' in src
    assert '"limit": _budget_i' in src


def test_detail_money_non_money_unchanged() -> None:
    f = SimpleNamespace(
        name="title",
        key="title",
        label="Title",
        type="text",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    item = {"title": "Hello", "title_minor": 1}
    out = _one_detail_field_dict(f, item)
    assert out["value"] == "Hello"
    assert out["currency_code"] == ""
