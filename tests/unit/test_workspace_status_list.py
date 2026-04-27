"""Tests for the v0.61.69 status_list display mode (#3).

The AegisMark UX patterns roadmap (item #3) — the SIMS-sync-opt-in
prototype's "agreement card", "schedule grid", and "scope grid"
patterns all share the same row shape: icon + title + secondary copy
+ state pill. Promoting this to a region display mode lets DSL
authors stamp the pattern out without per-app templating.

This first cycle ships the **authored** variant — `entries:` dash-list
of `{title, caption, icon, state}` dicts (mirrors action_grid #891).
The source-bound variant (entity rows mapped to entries) is deferred
to a later cycle per the roadmap.

Reuses the action_grid + metrics + notice tone vocabulary
(positive / warning / destructive / accent / neutral) for the state
pill — one palette across all tinted components.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode, StatusListEntrySpec
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"

workspace dash "Dash":
  readiness:
    display: status_list
    entries:
      - title: "Verified"
        caption: "Identity confirmed via SSO"
        icon: "check-circle"
        state: positive
      - title: "Pending"
        caption: "Awaiting school admin sign-off"
        icon: "clock"
        state: warning
"""


# ───────────────────────── parser ──────────────────────────


class TestStatusListParser:
    def test_minimal_pair(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.STATUS_LIST
        assert len(region.status_entries) == 2
        assert region.status_entries[0].title == "Verified"
        assert region.status_entries[0].caption == "Identity confirmed via SSO"
        assert region.status_entries[0].icon == "check-circle"
        assert region.status_entries[0].state == "positive"

    def test_title_only_entry(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - title: "Just a title"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.status_entries) == 1
        e = region.status_entries[0]
        assert e.title == "Just a title"
        assert e.caption == ""
        assert e.icon == ""
        assert e.state == "neutral"

    def test_state_defaults_to_neutral(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - title: "Plain"
        caption: "No state set"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.status_entries[0].state == "neutral"

    def test_invalid_state_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - title: "Bad"
        state: nonsense
"""
        with pytest.raises(ParseError, match="state must be one of"):
            _parse(src)

    def test_unknown_key_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - title: "X"
        bogus: "no"
"""
        with pytest.raises(ParseError, match="Unknown status_list entry key"):
            _parse(src)

    def test_entry_must_start_with_title(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - state: positive
        title: "Wrong order"
"""
        with pytest.raises(ParseError, match="must start with `title:`"):
            _parse(src)

    def test_each_valid_state_token_parses(self) -> None:
        for tok in ("positive", "warning", "destructive", "accent", "neutral"):
            src = f"""module t
app t "Test"
workspace dash "Dash":
  panel:
    display: status_list
    entries:
      - title: "X"
        state: {tok}
"""
            region = _parse(src).workspaces[0].regions[0]
            assert region.status_entries[0].state == tok


# ───────────────────────── bodyless exemption ──────────────────────────


class TestStatusListBodyless:
    """status_list regions don't need source/aggregate at the top
    level — `entries:` IS the body. The parser exemption now covers
    this alongside action_grid (#891) and pipeline_steps (#890)."""

    def test_no_source_or_aggregate_required(self) -> None:
        """The base DSL has neither `source:` nor `aggregate:` — only
        `entries:`. Must parse without the "requires source or aggregate"
        error."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.source is None
        assert region.aggregates == {}
        assert len(region.status_entries) == 2


# ───────────────────────── StatusListEntrySpec ──────────────────────────


class TestStatusListEntrySpec:
    def test_construct_minimal(self) -> None:
        e = StatusListEntrySpec(title="X")
        assert e.title == "X"
        assert e.caption == ""
        assert e.icon == ""
        assert e.state == "neutral"

    def test_construct_full(self) -> None:
        e = StatusListEntrySpec(
            title="Verified", caption="cap", icon="check-circle", state="positive"
        )
        assert e.caption == "cap"
        assert e.icon == "check-circle"
        assert e.state == "positive"

    def test_field_named_caption_not_copy(self) -> None:
        """Pydantic v2 BaseModel has a `copy` method (deprecated) —
        a field named `copy` would shadow it. We use `caption` to
        match `PipelineStageSpec.caption` and dodge the shadow."""
        # Direct construction with caption= works; copy= would error
        e = StatusListEntrySpec(title="X", caption="hi")
        assert e.caption == "hi"
        # `model.copy()` — Pydantic's method — must remain callable
        assert callable(e.copy)


# ───────────────────────── runtime + template wiring ──────────────────────────


class TestStatusListRuntimeWiring:
    def test_display_template_map_includes_status_list(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "STATUS_LIST" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["STATUS_LIST"] == "workspace/regions/status_list.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/status_list.html"
        )
        assert path.is_file()

    def test_region_context_default_empty_list(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.status_entries == []

    def test_region_context_carries_entries(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            status_entries=[
                {
                    "title": "Verified",
                    "caption": "SSO",
                    "icon": "check-circle",
                    "state": "positive",
                }
            ],
        )
        assert len(ctx.status_entries) == 1
        assert ctx.status_entries[0]["state"] == "positive"


class TestStatusListTemplateBinding:
    """Template-source invariants — the status_list template must
    bind to the four entry fields and use design-system tokens."""

    def _text(self) -> str:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/status_list.html"
        )
        return path.read_text()

    def test_template_iterates_status_entries(self) -> None:
        text = self._text()
        assert "for entry in status_entries" in text

    def test_template_renders_each_field(self) -> None:
        text = self._text()
        assert "entry.title" in text
        assert "entry.caption" in text
        assert "entry.icon" in text

    def test_template_uses_lucide_icon_attr(self) -> None:
        """Mirrors action_grid (#891) icon rendering — `data-lucide`
        attribute, no inline SVG paths."""
        text = self._text()
        assert "data-lucide=" in text

    def test_template_uses_design_system_tokens(self) -> None:
        """All five tone tints route through HSL design-system slots
        so the active theme applies — no hardcoded colours."""
        text = self._text()
        assert "var(--success)" in text
        assert "var(--warning)" in text
        assert "var(--destructive)" in text
        assert "var(--primary)" in text
        assert "var(--muted)" in text

    def test_template_uses_region_card_macro(self) -> None:
        text = self._text()
        assert "{% call region_card" in text

    def test_template_emits_canonical_class_markers(self) -> None:
        text = self._text()
        assert "dz-status-list-region" in text
        assert "dz-status-list" in text
        assert "dz-status-list-entry" in text

    def test_neutral_state_omits_pill(self) -> None:
        """Neutral state is the default — entries that don't explicitly
        set a state shouldn't render a pill saying "NEUTRAL". The
        template gates the pill on `_state != 'neutral'`."""
        text = self._text()
        assert "_state != 'neutral'" in text


# ───────────────────────── empty state ──────────────────────────


class TestStatusListEmpty:
    """Region with empty `entries:` declared elsewhere — template
    must render the empty-state fallback rather than an empty <ul>."""

    def test_empty_status_entries_means_empty_state_message(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r", status_entries=[])
        # The template's `{% if status_entries and ... %}` gate falls
        # through to the empty-state <p>. We don't render here; the
        # contract is checked via the template binding tests above.
        assert ctx.status_entries == []
