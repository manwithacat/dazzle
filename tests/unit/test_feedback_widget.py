"""
Tests for feedback_widget DSL keyword — IR model, parser, and auto-entity generation.

TDD: These tests are written BEFORE the implementation.
"""

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# 1. IR Model Tests — FeedbackWidgetSpec
# ---------------------------------------------------------------------------


class TestFeedbackWidgetSpec:
    """FeedbackWidgetSpec Pydantic model."""

    def test_defaults(self) -> None:
        """All fields have sensible defaults when only enabled=True is set."""
        from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec

        spec = FeedbackWidgetSpec(enabled=True)
        assert spec.enabled is True
        assert spec.position == "bottom-right"
        assert spec.shortcut == "backtick"
        assert spec.categories == [
            "bug",
            "ux",
            "visual",
            "behaviour",
            "enhancement",
            "other",
        ]
        assert spec.severities == ["blocker", "annoying", "minor"]
        assert spec.capture == [
            "url",
            "persona",
            "viewport",
            "user_agent",
            "console_errors",
            "nav_history",
            "page_snapshot",
        ]

    def test_custom_values(self) -> None:
        """Custom sub-keys override defaults."""
        from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec

        spec = FeedbackWidgetSpec(
            enabled=True,
            position="top-left",
            shortcut="f1",
            categories=["bug", "other"],
            severities=["critical"],
            capture=["url"],
        )
        assert spec.position == "top-left"
        assert spec.shortcut == "f1"
        assert spec.categories == ["bug", "other"]
        assert spec.severities == ["critical"]
        assert spec.capture == ["url"]

    def test_disabled(self) -> None:
        """Spec with enabled=False."""
        from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec

        spec = FeedbackWidgetSpec(enabled=False)
        assert spec.enabled is False

    def test_frozen(self) -> None:
        """FeedbackWidgetSpec is immutable (frozen)."""
        from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec

        spec = FeedbackWidgetSpec(enabled=True)
        with pytest.raises(ValidationError):
            spec.enabled = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. FEEDBACK_REPORT_FIELDS constant
# ---------------------------------------------------------------------------


class TestFeedbackReportFields:
    """FEEDBACK_REPORT_FIELDS constant for auto-entity generation."""

    def test_fields_defined(self) -> None:
        """FEEDBACK_REPORT_FIELDS is a non-empty tuple of field definitions."""
        from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS

        assert len(FEEDBACK_REPORT_FIELDS) > 0
        # Each entry is (name, type_str, modifiers, default)
        for entry in FEEDBACK_REPORT_FIELDS:
            assert len(entry) == 4
            name, type_str, modifiers, default = entry
            assert isinstance(name, str)
            assert isinstance(type_str, str)
            assert isinstance(modifiers, tuple)

    def test_has_required_fields(self) -> None:
        """Must include the core human-input and auto-captured fields."""
        from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS

        field_names = {f[0] for f in FEEDBACK_REPORT_FIELDS}
        # Human input
        assert "category" in field_names
        assert "severity" in field_names
        assert "description" in field_names
        # Auto-captured context
        assert "page_url" in field_names
        assert "console_errors" in field_names
        assert "nav_history" in field_names
        # Status lifecycle
        assert "status" in field_names
        # Notification tracking (#721)
        assert "notification_sent" in field_names
        # Audit
        assert "reported_by" in field_names
        assert "created_at" in field_names

    def test_id_field_is_first(self) -> None:
        """id: uuid pk must be the first field."""
        from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS

        name, type_str, modifiers, _ = FEEDBACK_REPORT_FIELDS[0]
        assert name == "id"
        assert type_str == "uuid"
        assert "pk" in modifiers


# ---------------------------------------------------------------------------
# 3. Lexer token
# ---------------------------------------------------------------------------


class TestFeedbackWidgetToken:
    """FEEDBACK_WIDGET token type exists in lexer."""

    def test_token_exists(self) -> None:
        """TokenType.FEEDBACK_WIDGET is registered."""
        from dazzle.core.lexer import TokenType

        assert hasattr(TokenType, "FEEDBACK_WIDGET")

    def test_tokenize_keyword(self) -> None:
        """Lexer recognises 'feedback_widget' as a keyword token."""
        from dazzle.core.lexer import TokenType, tokenize

        tokens = tokenize("feedback_widget: enabled\n", file="test.dsl")
        fw_tokens = [t for t in tokens if t.type == TokenType.FEEDBACK_WIDGET]
        assert len(fw_tokens) == 1


# ---------------------------------------------------------------------------
# 4. ModuleFragment / AppSpec integration
# ---------------------------------------------------------------------------


class TestModuleFragmentAppSpec:
    """feedback_widget field on ModuleFragment and AppSpec."""

    def test_module_fragment_field_default_none(self) -> None:
        """ModuleFragment.feedback_widget defaults to None."""
        from dazzle.core.ir import ModuleFragment

        frag = ModuleFragment()
        assert frag.feedback_widget is None

    def test_module_fragment_field_accepts_spec(self) -> None:
        """ModuleFragment.feedback_widget accepts a FeedbackWidgetSpec."""
        from dazzle.core.ir import ModuleFragment
        from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec

        spec = FeedbackWidgetSpec(enabled=True)
        frag = ModuleFragment(feedback_widget=spec)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.enabled is True

    def test_appspec_field_default_none(self) -> None:
        """AppSpec.feedback_widget defaults to None."""
        from dazzle.core.ir import AppSpec, DomainSpec

        app = AppSpec(name="test", domain=DomainSpec(entities=[]))
        assert app.feedback_widget is None

    def test_ir_exports_feedback_widget_spec(self) -> None:
        """FeedbackWidgetSpec is re-exported from ir package."""
        from dazzle.core import ir

        assert hasattr(ir, "FeedbackWidgetSpec")


# ---------------------------------------------------------------------------
# 5. Parser mixin tests
# ---------------------------------------------------------------------------


def _parse(text: str) -> object:
    """Helper to parse DSL text and return the ModuleFragment."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    result = parse_dsl(text, "test.dsl")
    return result[-1]  # ModuleFragment is last element


class TestFeedbackWidgetParser:
    """Parser mixin for feedback_widget keyword."""

    def test_enabled_defaults(self) -> None:
        """feedback_widget: enabled with no sub-keys produces defaults."""
        frag = _parse('module test\napp test "Test"\n\nfeedback_widget: enabled\n')
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.enabled is True
        assert frag.feedback_widget.position == "bottom-right"

    def test_disabled(self) -> None:
        """feedback_widget: disabled sets enabled=False."""
        frag = _parse('module test\napp test "Test"\n\nfeedback_widget: disabled\n')
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.enabled is False

    def test_custom_position(self) -> None:
        """Custom position sub-key."""
        dsl = 'module test\napp test "Test"\n\nfeedback_widget: enabled\n  position: top-left\n'
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.position == "top-left"

    def test_custom_categories_list(self) -> None:
        """Custom categories as bracket list."""
        dsl = (
            'module test\napp test "Test"\n\nfeedback_widget: enabled\n  categories: [bug, other]\n'
        )
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.categories == ["bug", "other"]

    def test_custom_severities(self) -> None:
        """Custom severities."""
        dsl = (
            'module test\napp test "Test"\n\n'
            "feedback_widget: enabled\n"
            "  severities: [critical, minor]\n"
        )
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.severities == ["critical", "minor"]

    def test_custom_capture(self) -> None:
        """Custom capture list."""
        dsl = (
            'module test\napp test "Test"\n\nfeedback_widget: enabled\n  capture: [url, persona]\n'
        )
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.capture == ["url", "persona"]

    def test_custom_shortcut(self) -> None:
        """Custom shortcut."""
        dsl = 'module test\napp test "Test"\n\nfeedback_widget: enabled\n  shortcut: f1\n'
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.shortcut == "f1"

    def test_partial_subkeys_use_defaults(self) -> None:
        """Partial sub-keys fill remaining with defaults."""
        dsl = 'module test\napp test "Test"\n\nfeedback_widget: enabled\n  position: bottom-left\n'
        frag = _parse(dsl)
        assert frag.feedback_widget is not None
        assert frag.feedback_widget.position == "bottom-left"
        # Defaults remain
        assert frag.feedback_widget.shortcut == "backtick"
        assert len(frag.feedback_widget.categories) == 6


# ---------------------------------------------------------------------------
# 6. Auto-entity generation in linker
# ---------------------------------------------------------------------------


class TestFeedbackReportAutoEntity:
    """Auto-generation of FeedbackReport entity when feedback_widget is enabled."""

    def _link(self, dsl: str) -> object:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec

        mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
        module = ModuleIR(
            name=mod_name or "test",
            file=Path("test.dsl"),
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=fragment,
        )
        return build_appspec([module], module.name)

    def test_auto_entity_created_when_enabled(self) -> None:
        """FeedbackReport entity is auto-generated when feedback_widget: enabled."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: enabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        assert entity.name == "FeedbackReport"

    def test_auto_entity_has_required_fields(self) -> None:
        """Auto-generated FeedbackReport has the expected fields."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: enabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        field_names = {f.name for f in entity.fields}
        assert "id" in field_names
        assert "category" in field_names
        assert "description" in field_names
        assert "status" in field_names
        assert "reported_by" in field_names

    def test_no_auto_entity_when_disabled(self) -> None:
        """FeedbackReport is NOT generated when feedback_widget: disabled."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: disabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is None

    def test_no_auto_entity_when_absent(self) -> None:
        """No FeedbackReport when feedback_widget keyword is absent."""
        dsl = (
            'module test\napp test "Test"\n\nentity User "User":\n  id: uuid pk\n  name: str(100)\n'
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is None

    def test_explicit_entity_not_overwritten(self) -> None:
        """If app declares its own FeedbackReport entity, auto-generation is skipped."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            'entity FeedbackReport "Custom Feedback":\n'
            "  id: uuid pk\n"
            "  title: str(200)\n\n"
            "feedback_widget: enabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        # Should be the explicit one (has 'title' field, not 'category')
        field_names = {f.name for f in entity.fields}
        assert "title" in field_names

    def test_auto_entity_has_state_machine(self) -> None:
        """Auto-generated FeedbackReport has lifecycle transitions."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: enabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        assert entity.state_machine is not None
        transition_strs = {
            f"{t.from_state} -> {t.to_state}" for t in entity.state_machine.transitions
        }
        assert "new -> triaged" in transition_strs
        assert "triaged -> in_progress" in transition_strs
        assert "in_progress -> resolved" in transition_strs

    def test_triaged_to_resolved_shortcut(self) -> None:
        """State machine allows triaged → resolved (agent shortcut)."""
        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: enabled\n"
        )
        app = self._link(dsl)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        assert entity.state_machine is not None
        transition_strs = {
            f"{t.from_state} -> {t.to_state}" for t in entity.state_machine.transitions
        }
        assert "triaged -> resolved" in transition_strs


# ---------------------------------------------------------------------------
# 7. Synthetic surface generation in linker (#685)
# ---------------------------------------------------------------------------


class TestFeedbackWidgetSurfaces:
    """Synthetic CREATE + LIST surfaces generated alongside FeedbackReport entity."""

    _DSL_ENABLED = (
        'module test\napp test "Test"\n\n'
        'entity User "User":\n'
        "  id: uuid pk\n"
        "  name: str(100)\n\n"
        "feedback_widget: enabled\n"
    )

    _DSL_DISABLED = (
        'module test\napp test "Test"\n\n'
        'entity User "User":\n'
        "  id: uuid pk\n"
        "  name: str(100)\n\n"
        "feedback_widget: disabled\n"
    )

    def _link(self, dsl: str) -> object:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec

        mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
        module = ModuleIR(
            name=mod_name or "test",
            file=Path("test.dsl"),
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=fragment,
        )
        return build_appspec([module], module.name)

    def test_generates_entity_and_surfaces(self) -> None:
        """feedback_widget: enabled produces 1 entity + 3 surfaces."""
        app = self._link(self._DSL_ENABLED)
        assert app.get_entity("FeedbackReport") is not None
        surface_names = {s.name for s in app.surfaces}
        assert "feedback_create" in surface_names
        assert "feedback_admin" in surface_names
        assert "feedback_edit" in surface_names

    def test_disabled_no_surfaces(self) -> None:
        """feedback_widget: disabled produces no FeedbackReport surfaces."""
        app = self._link(self._DSL_DISABLED)
        assert app.get_entity("FeedbackReport") is None
        surface_names = {s.name for s in app.surfaces}
        assert "feedback_create" not in surface_names
        assert "feedback_admin" not in surface_names

    def test_create_surface_mode_and_entity(self) -> None:
        """feedback_create surface is mode=create referencing FeedbackReport."""
        from dazzle.core.ir.surfaces import SurfaceMode

        app = self._link(self._DSL_ENABLED)
        create = next(s for s in app.surfaces if s.name == "feedback_create")
        assert create.mode == SurfaceMode.CREATE
        assert create.entity_ref == "FeedbackReport"
        assert create.sections == []  # headless — widget JS is the UI

    def test_create_surface_requires_auth(self) -> None:
        """feedback_create surface requires authentication (any role)."""
        app = self._link(self._DSL_ENABLED)
        create = next(s for s in app.surfaces if s.name == "feedback_create")
        assert create.access is not None
        assert create.access.require_auth is True
        assert create.access.allow_personas == []  # any authenticated user

    def test_admin_surface_mode_and_entity(self) -> None:
        """feedback_admin surface is mode=list referencing FeedbackReport."""
        from dazzle.core.ir.surfaces import SurfaceMode

        app = self._link(self._DSL_ENABLED)
        admin = next(s for s in app.surfaces if s.name == "feedback_admin")
        assert admin.mode == SurfaceMode.LIST
        assert admin.entity_ref == "FeedbackReport"

    def test_admin_surface_has_triage_fields(self) -> None:
        """feedback_admin surface has sections with expected fields."""
        app = self._link(self._DSL_ENABLED)
        admin = next(s for s in app.surfaces if s.name == "feedback_admin")
        assert len(admin.sections) == 1
        field_names = {e.field_name for e in admin.sections[0].elements}
        assert "category" in field_names
        assert "severity" in field_names
        assert "description" in field_names
        assert "status" in field_names
        assert "reported_by" in field_names
        assert "page_url" in field_names
        assert "created_at" in field_names

    def test_admin_surface_restricts_to_admin_personas(self) -> None:
        """feedback_admin surface restricted to admin/super_admin."""
        app = self._link(self._DSL_ENABLED)
        admin = next(s for s in app.surfaces if s.name == "feedback_admin")
        assert admin.access is not None
        assert admin.access.require_auth is True
        assert "admin" in admin.access.allow_personas
        assert "super_admin" in admin.access.allow_personas

    def test_edit_surface_generated(self) -> None:
        """feedback_widget: enabled produces a feedback_edit surface."""
        app = self._link(self._DSL_ENABLED)
        surface_names = {s.name for s in app.surfaces}
        assert "feedback_edit" in surface_names

    def test_edit_surface_mode_and_entity(self) -> None:
        """feedback_edit surface is mode=edit referencing FeedbackReport."""
        from dazzle.core.ir.surfaces import SurfaceMode

        app = self._link(self._DSL_ENABLED)
        edit = next(s for s in app.surfaces if s.name == "feedback_edit")
        assert edit.mode == SurfaceMode.EDIT
        assert edit.entity_ref == "FeedbackReport"

    def test_edit_surface_has_editable_fields(self) -> None:
        """feedback_edit surface has triage/resolution fields across three sections."""
        app = self._link(self._DSL_ENABLED)
        edit = next(s for s in app.surfaces if s.name == "feedback_edit")
        assert len(edit.sections) == 3
        field_names = {e.field_name for section in edit.sections for e in section.elements}
        assert "status" in field_names
        assert "assigned_to" in field_names
        assert "agent_notes" in field_names

    def test_edit_surface_has_admin_access(self) -> None:
        """feedback_edit surface restricted to admin/super_admin."""
        app = self._link(self._DSL_ENABLED)
        edit = next(s for s in app.surfaces if s.name == "feedback_edit")
        assert edit.access is not None
        assert edit.access.require_auth is True
        assert "admin" in edit.access.allow_personas


# ---------------------------------------------------------------------------
# 8. PUT endpoint generation (#720)
# ---------------------------------------------------------------------------


class TestFeedbackReportPutEndpoint:
    """Verify that feedback_edit surface generates a PUT endpoint via surface converter."""

    _DSL_ENABLED = (
        'module test\napp test "Test"\n\n'
        'entity User "User":\n'
        "  id: uuid pk\n"
        "  name: str(100)\n\n"
        "feedback_widget: enabled\n"
    )

    def _build_app(self) -> object:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec

        mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
            self._DSL_ENABLED, Path("test.dsl")
        )
        module = ModuleIR(
            name=mod_name or "test",
            file=Path("test.dsl"),
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=fragment,
        )
        return build_appspec([module], module.name)

    def test_put_endpoint_registered(self) -> None:
        """feedback_edit surface produces a PUT endpoint at /feedbackreports/{id}."""
        from dazzle_back.converters.surface_converter import (
            convert_surfaces_to_services,
        )

        app = self._build_app()
        _services, endpoints = convert_surfaces_to_services(app.surfaces, app.domain)
        put_endpoints = [
            ep
            for ep in endpoints
            if ep.method.value == "PUT" and "feedbackreport" in ep.path.lower()
        ]
        assert len(put_endpoints) == 1
        assert "{id}" in put_endpoints[0].path

    def test_update_service_created(self) -> None:
        """feedback_edit surface produces an UPDATE service for FeedbackReport."""
        from dazzle_back.converters.surface_converter import (
            convert_surfaces_to_services,
        )

        app = self._build_app()
        services, _endpoints = convert_surfaces_to_services(app.surfaces, app.domain)
        update_services = [
            s
            for s in services
            if s.domain_operation
            and s.domain_operation.entity == "FeedbackReport"
            and s.domain_operation.kind.value == "update"
        ]
        assert len(update_services) == 1


# ---------------------------------------------------------------------------
# 9. Notification tracking field (#721)
# ---------------------------------------------------------------------------


class TestFeedbackReportNotificationField:
    """notification_sent field for resolved-report notifications."""

    def test_notification_sent_field_exists(self) -> None:
        """FEEDBACK_REPORT_FIELDS includes notification_sent."""
        from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS

        field_names = {f[0] for f in FEEDBACK_REPORT_FIELDS}
        assert "notification_sent" in field_names

    def test_notification_sent_is_bool_default_false(self) -> None:
        """notification_sent is a bool field defaulting to false."""
        from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS

        field = next(f for f in FEEDBACK_REPORT_FIELDS if f[0] == "notification_sent")
        name, type_str, modifiers, default = field
        assert type_str == "bool"
        assert default == "false"

    def test_auto_entity_has_notification_sent(self) -> None:
        """Auto-generated FeedbackReport entity includes notification_sent."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec

        dsl = (
            'module test\napp test "Test"\n\n'
            'entity User "User":\n'
            "  id: uuid pk\n"
            "  name: str(100)\n\n"
            "feedback_widget: enabled\n"
        )
        mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
        module = ModuleIR(
            name=mod_name or "test",
            file=Path("test.dsl"),
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=fragment,
        )
        app = build_appspec([module], module.name)
        entity = app.get_entity("FeedbackReport")
        assert entity is not None
        field_names = {f.name for f in entity.fields}
        assert "notification_sent" in field_names
