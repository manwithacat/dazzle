"""Tests for the v0.61.72 confirm_action_panel display mode (#6).

The AegisMark UX patterns roadmap (item #6) — irreversible-action
consent primitive. The SIMS-sync-opt-in prototype's "Final
authorisation" panel: a checklist of obligations, a primary commit
button gated on all required checkboxes being ticked, an optional
draft button, and a revoke action shown only in the live state.

The panel binds to an entity field via `state_field:` so the same
DSL declaration handles all visual modes (off / pending / live /
revoked) — the runtime resolves the field value from the fetched
item and the template branches on it.

Audit footer auto-renders when the source entity has an `audit:`
block. Multi-stage consent (wizard-style flows) is composed via
the existing `experience` / `step` primitives — each step renders
a confirm_action_panel surface — rather than baking a multi-stage
mode into the panel itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ConfirmationItemSpec, DisplayMode
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"

entity Integration:
  id: uuid pk
  status: enum[off,pending,live,revoked]

workspace dash "Dash":
  panel:
    source: Integration
    display: confirm_action_panel
    state_field: status
    confirmations:
      - title: "I confirm DPA signed"
      - title: "I authorise write-backs"
      - title: "Audit will record this"
        required: false
    primary_action: enable_sync
    secondary_action: save_draft
    revoke: disable_sync
"""


# ───────────────────────── parser ──────────────────────────


class TestConfirmActionPanelParser:
    def test_minimal_panel(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.CONFIRM_ACTION_PANEL
        assert region.state_field == "status"
        assert len(region.confirmations) == 3
        assert region.primary_action == "enable_sync"
        assert region.secondary_action == "save_draft"
        assert region.revoke == "disable_sync"

    def test_required_default_true(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.confirmations[0].required is True
        assert region.confirmations[1].required is True

    def test_required_false_explicit(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.confirmations[2].required is False

    def test_confirmation_with_caption(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: confirm_action_panel
    confirmations:
      - title: "I confirm"
        caption: "Recorded with my account, IP, timestamp"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.confirmations[0].caption == ("Recorded with my account, IP, timestamp")

    def test_no_state_field_is_allowed(self) -> None:
        """Authors can omit `state_field:` for low-friction flows
        (no state machine, panel is the whole flow). The runtime
        defaults state_value to empty → off mode."""
        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: confirm_action_panel
    confirmations:
      - title: "I agree"
    primary_action: do_thing
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.state_field is None
        assert region.primary_action == "do_thing"

    def test_invalid_required_value_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: confirm_action_panel
    confirmations:
      - title: "X"
        required: maybe
"""
        with pytest.raises(ParseError, match="required must be"):
            _parse(src)

    def test_unknown_confirmation_key_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: confirm_action_panel
    confirmations:
      - title: "X"
        bogus: yes
"""
        with pytest.raises(ParseError, match="Unknown confirmations"):
            _parse(src)


# ───────────────────────── bodyless exemption ──────────────────────────


class TestConfirmActionPanelBodyless:
    """Panels can declare without a `source:` (low-friction flows
    where the panel itself is the entire UI). Joins action_grid /
    pipeline_steps / status_list in the bodyless exemption."""

    def test_no_source_required(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  panel:
    display: confirm_action_panel
    confirmations:
      - title: "I agree"
    primary_action: do_thing
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.source is None
        assert region.aggregates == {}
        assert len(region.confirmations) == 1


# ───────────────────────── ConfirmationItemSpec ──────────────────────────


class TestConfirmationItemSpec:
    def test_construct_minimal(self) -> None:
        c = ConfirmationItemSpec(title="X")
        assert c.title == "X"
        assert c.caption == ""
        assert c.required is True

    def test_construct_full(self) -> None:
        c = ConfirmationItemSpec(title="T", caption="C", required=False)
        assert c.required is False


# ───────────────────────── primary_action / secondary_action keys ──────────


class TestActionKeysDontClashWithProfileCard:
    """`primary:` and `secondary:` are profile_card keys (entity field
    names there). The confirm_action_panel uses `primary_action:` /
    `secondary_action:` instead — same DSL file, different keys, no
    parser ambiguity."""

    def test_primary_action_distinct_from_profile_card_primary(self) -> None:
        src = """module t
app t "Test"
entity Person:
  id: uuid pk
  name: str(100)
workspace dash "Dash":
  card:
    source: Person
    display: profile_card
    primary: name
"""
        region = _parse(src).workspaces[0].regions[0]
        # Profile card's primary is still parsed correctly
        assert region.primary == "name"
        # confirm_action_panel-specific fields stay None on a non-panel region
        assert region.primary_action is None


# ───────────────────────── runtime + template wiring ──────────────────────────


class TestConfirmActionPanelRuntimeWiring:
    def test_display_template_map_includes_confirm_action_panel(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "CONFIRM_ACTION_PANEL" in DISPLAY_TEMPLATE_MAP
        assert (
            DISPLAY_TEMPLATE_MAP["CONFIRM_ACTION_PANEL"]
            == "workspace/regions/confirm_action_panel.html"
        )

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/confirm_action_panel.html"
        )
        assert path.is_file()

    def test_region_context_default_empty(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.confirmations == []
        assert ctx.state_field == ""
        assert ctx.state_value == ""
        assert ctx.primary_action_url == ""
        assert ctx.secondary_action_url == ""
        assert ctx.revoke_url == ""
        assert ctx.audit_enabled is False

    def test_region_context_carries_fields(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            confirmations=[{"title": "X", "caption": "", "required": True}],
            state_field="status",
            state_value="off",
            primary_action_url="/app/integration_enable",
            audit_enabled=True,
        )
        assert ctx.state_value == "off"
        assert ctx.audit_enabled is True
        assert len(ctx.confirmations) == 1


class TestConfirmActionPanelTemplateBranches:
    """Template-source invariants for the off/live/revoked mode
    branching. The static template must contain at least one branch
    per state class so the runtime can route into them."""

    def _text(self) -> str:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/confirm_action_panel.html"
        )
        return path.read_text()

    def test_branches_on_state_value(self) -> None:
        text = self._text()
        assert "state_value" in text
        # The three render modes
        assert "_is_live" in text
        assert "_is_revoked" in text

    def test_renders_confirmations(self) -> None:
        text = self._text()
        assert "for item in confirmations" in text

    def test_renders_dual_button(self) -> None:
        text = self._text()
        assert "primary_action_url" in text
        assert "secondary_action_url" in text

    def test_renders_revoke_in_live_mode(self) -> None:
        text = self._text()
        # The revoke button must live inside the _is_live branch
        live_idx = text.find("_is_live")
        revoke_idx = text.find("revoke_url")
        assert live_idx > 0 and revoke_idx > live_idx, (
            "revoke action must render inside the _is_live branch"
        )

    def test_audit_footer_gated_on_audit_enabled(self) -> None:
        text = self._text()
        assert "if audit_enabled" in text
        assert "audit log" in text.lower()

    def test_uses_alpine_gate(self) -> None:
        """The required-checkbox gate uses an Alpine component named
        `dzConfirmGate` (registered in dz-alpine.js). Pin the
        contract: template binds, JS provides."""
        text = self._text()
        assert "dzConfirmGate" in text
        # And the JS component must be registered
        js_path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/js/dz-alpine.js"
        )
        js_text = js_path.read_text()
        assert 'Alpine.data("dzConfirmGate"' in js_text


# ───────────────────────── audit auto-detect ──────────────────────────


class TestConfirmActionPanelAuditAutoDetect:
    """The audit footer auto-renders when the source entity has an
    `audit:` block. Authors don't need to write the disclosure copy
    by hand. Driven by `audit_enabled` on the RegionContext, set
    upstream during build_workspace_context.

    This test exercises the IR path — runtime auto-detection happens
    inside build_workspace_context which the unit test infra doesn't
    boot. A separate integration test would cover the full flow."""

    def test_entity_with_audit_block_parses(self) -> None:
        src = """module t
app t "Test"
entity Integration:
  id: uuid pk
  status: enum[off,live]
  audit: all
workspace dash "Dash":
  panel:
    source: Integration
    display: confirm_action_panel
    state_field: status
    confirmations:
      - title: "I agree"
    primary_action: do_thing
"""
        fragment = _parse(src)
        entity = fragment.entities[0]
        assert entity.audit is not None, "audit:all must produce an AuditConfig"
        # Region binds to this entity by source name; the renderer
        # looks up audit on the entity at context-build time.
        region = fragment.workspaces[0].regions[0]
        assert region.source == "Integration"


# ───────────────────────── invariants ──────────────────────────


class TestConfirmActionPanelExampleApp:
    """ops_dashboard exercises confirm_action_panel via the
    `integration_authorise` region against the Integration entity.
    Authors who copy from examples need a working reference."""

    def test_ops_dashboard_has_panel_region(self) -> None:
        path = Path(__file__).resolve().parents[2] / "examples/ops_dashboard/dsl/app.dsl"
        text = path.read_text()
        assert "display: confirm_action_panel" in text, (
            "ops_dashboard missing confirm_action_panel demo — #6 example anchor lost"
        )
        assert "integration_authorise" in text
