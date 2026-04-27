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

    def test_template_emits_data_dz_state_attribute(self) -> None:
        """v0.61.70 (#906): pill + icon tints come from `dz-tones.css`
        keyed off `data-dz-state`, NOT from inline Tailwind arbitrary
        values built at IR-render time (those were JIT-invisible and
        shipped without rules). The template must still emit the
        attribute so the CSS can match it. Per-state branches pinned
        in `test_dz_tones_css.py::TestDzTonesCssRulesPresent`."""
        text = self._text()
        assert 'data-dz-state="' in text, (
            "status_list.html must emit data-dz-state — dz-tones.css keys off it"
        )

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


# ───────────────────────── runtime render contract ──────────────────────────


class TestStatusListRendersAuthoredEntries:
    """Regression for #908 — the runtime must forward `status_entries`
    to the template render call. Pre-fix the variable was never passed,
    so the template's `{% if status_entries and ... %}` gate fell
    through to the empty-state every time, regardless of what the IR
    held. AegisMark's sims_sync_settings_workspace shipped three
    status_list regions all rendering "No data available" before
    reporting it.

    The unit-tier template binding tests passed because they checked
    the template SOURCE for the right Jinja constructs but never
    actually rendered the template through `render_fragment` with a
    realistic kwargs payload."""

    def test_render_fragment_emits_entries_when_passed(self) -> None:
        from dazzle_ui.runtime.template_renderer import render_fragment

        html = render_fragment(
            "workspace/regions/status_list.html",
            title="Activation gates",
            empty_message="No data available.",
            status_entries=[
                {
                    "title": "DPA signed",
                    "caption": "Oakwood Academy / DPA v1.4",
                    "icon": "file-check",
                    "state": "positive",
                },
                {
                    "title": "Signatory verified",
                    "caption": "Rachel Morgan signed from school account",
                    "icon": "user-check",
                    "state": "positive",
                },
            ],
        )
        # Entries must render — the empty-state fallback must NOT fire.
        assert "DPA signed" in html
        assert "Signatory verified" in html
        assert "No data available" not in html
        # Each entry's data attributes flow through
        assert 'data-dz-state="positive"' in html
        assert "data-dz-entry-count=" in html

    def test_render_fragment_falls_back_to_empty_state_when_no_entries(self) -> None:
        """Defensive: with status_entries=[], the template SHOULD show
        the empty state. Pin the contract from the other direction."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        html = render_fragment(
            "workspace/regions/status_list.html",
            title="Empty",
            empty_message="No status entries.",
            status_entries=[],
        )
        assert "No status entries." in html
        assert "dz-status-list-entry" not in html

    def test_runtime_call_forwards_status_entries(self) -> None:
        """Defensive: the workspace_rendering.py render_fragment call
        must include `status_entries` in its kwargs. Pre-fix this was
        the missing line that caused #908. String-match on the source
        because the actual flow is hard to exercise without booting
        a full FastAPI app."""
        from pathlib import Path

        rendering_path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_back/runtime/workspace_rendering.py"
        )
        text = rendering_path.read_text()
        assert "status_entries=getattr(ctx.ctx_region" in text, (
            "workspace_rendering.py must forward status_entries to "
            "render_fragment — #908 regression"
        )
