"""
Tests for src/dazzle/core/ir/triples.py

Covers:
- WidgetKind enum values
- resolve_widget() mapping from FieldTypeKind to WidgetKind
- _id suffix convention: uuid field ending in _id → SEARCH_SELECT, plain 'id' → TEXT_INPUT
- has_source=True override → SEARCH_SELECT
- SurfaceFieldTriple construction (basic field and FK field)
- get_permitted_personas() permission helper
- resolve_surface_actions() action derivation
"""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.domain import (
    AccessSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition, TransitionTrigger
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.triples import (
    SurfaceActionTriple,
    SurfaceFieldTriple,
    WidgetKind,
    get_permitted_personas,
    resolve_surface_actions,
    resolve_widget,
)


def _make_field(
    name: str,
    kind: FieldTypeKind,
    *,
    modifiers: list[FieldModifier] | None = None,
    ref_entity: str | None = None,
    enum_values: list[str] | None = None,
) -> FieldSpec:
    """Helper: build a minimal FieldSpec."""
    return FieldSpec(
        name=name,
        type=FieldType(
            kind=kind,
            ref_entity=ref_entity,
            enum_values=enum_values,
        ),
        modifiers=modifiers or [],
    )


# ---------------------------------------------------------------------------
# WidgetKind values
# ---------------------------------------------------------------------------


class TestWidgetKindValues:
    def test_all_expected_values_present(self) -> None:
        expected = {
            "TEXT_INPUT",
            "TEXTAREA",
            "CHECKBOX",
            "DATE_PICKER",
            "DATETIME_PICKER",
            "NUMBER_INPUT",
            "EMAIL_INPUT",
            "ENUM_SELECT",
            "SEARCH_SELECT",
            "MONEY_INPUT",
            "FILE_UPLOAD",
        }
        actual = {member.name for member in WidgetKind}
        assert actual == expected

    def test_widget_kind_is_str(self) -> None:
        # WidgetKind inherits from StrEnum
        assert isinstance(WidgetKind.TEXT_INPUT, str)


# ---------------------------------------------------------------------------
# resolve_widget: basic type mappings
# ---------------------------------------------------------------------------


class TestResolveWidgetTypeMap:
    @pytest.mark.parametrize(
        "kind, expected_widget",
        [
            (FieldTypeKind.STR, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.TEXT, WidgetKind.TEXTAREA),
            (FieldTypeKind.INT, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.DECIMAL, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.FLOAT, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.BOOL, WidgetKind.CHECKBOX),
            (FieldTypeKind.DATE, WidgetKind.DATE_PICKER),
            (FieldTypeKind.DATETIME, WidgetKind.DATETIME_PICKER),
            (FieldTypeKind.UUID, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.ENUM, WidgetKind.ENUM_SELECT),
            (FieldTypeKind.REF, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.EMAIL, WidgetKind.EMAIL_INPUT),
            (FieldTypeKind.JSON, WidgetKind.TEXTAREA),
            (FieldTypeKind.MONEY, WidgetKind.MONEY_INPUT),
            (FieldTypeKind.FILE, WidgetKind.FILE_UPLOAD),
            (FieldTypeKind.URL, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.TIMEZONE, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.HAS_MANY, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.HAS_ONE, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.EMBEDS, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.BELONGS_TO, WidgetKind.SEARCH_SELECT),
        ],
    )
    def test_type_to_widget(self, kind: FieldTypeKind, expected_widget: WidgetKind) -> None:
        field = _make_field("some_field", kind)
        assert resolve_widget(field) == expected_widget


# ---------------------------------------------------------------------------
# resolve_widget: _id suffix convention
# ---------------------------------------------------------------------------


class TestResolveWidgetIdSuffix:
    def test_uuid_field_named_id_gives_text_input(self) -> None:
        """Plain 'id' primary-key field should stay TEXT_INPUT, not SEARCH_SELECT."""
        field = _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_uuid_field_ending_in_underscore_id_gives_search_select(self) -> None:
        """A uuid FK column like 'client_id' signals a foreign key → SEARCH_SELECT."""
        field = _make_field("client_id", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_uuid_field_ending_in_underscore_id_longer_name(self) -> None:
        field = _make_field("assessment_event_id", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_str_field_ending_in_id_not_affected(self) -> None:
        """The _id suffix rule only applies to UUID fields."""
        field = _make_field("some_id", FieldTypeKind.STR)
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_uuid_field_not_ending_in_underscore_id_gives_text_input(self) -> None:
        """A uuid field whose name doesn't end in _id stays TEXT_INPUT."""
        field = _make_field("record_uuid", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT


# ---------------------------------------------------------------------------
# resolve_widget: has_source override
# ---------------------------------------------------------------------------


class TestResolveWidgetHasSource:
    def test_has_source_overrides_str_to_search_select(self) -> None:
        field = _make_field("owner", FieldTypeKind.STR)
        assert resolve_widget(field, has_source=True) == WidgetKind.SEARCH_SELECT

    def test_has_source_overrides_uuid_id_to_search_select(self) -> None:
        """Even 'id' gets SEARCH_SELECT when has_source=True."""
        field = _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])
        assert resolve_widget(field, has_source=True) == WidgetKind.SEARCH_SELECT

    def test_has_source_false_leaves_default(self) -> None:
        field = _make_field("notes", FieldTypeKind.TEXT)
        assert resolve_widget(field, has_source=False) == WidgetKind.TEXTAREA


# ---------------------------------------------------------------------------
# SurfaceFieldTriple construction
# ---------------------------------------------------------------------------


class TestSurfaceFieldTriple:
    def test_basic_str_field(self) -> None:
        field = _make_field("title", FieldTypeKind.STR, modifiers=[FieldModifier.REQUIRED])
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=False,
            ref_entity=None,
        )
        assert triple.field_name == "title"
        assert triple.widget == WidgetKind.TEXT_INPUT
        assert triple.is_required is True
        assert triple.is_fk is False
        assert triple.ref_entity is None

    def test_fk_ref_field(self) -> None:
        field = _make_field(
            "client",
            FieldTypeKind.REF,
            ref_entity="Client",
            modifiers=[FieldModifier.REQUIRED],
        )
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=True,
            ref_entity=field.type.ref_entity,
        )
        assert triple.field_name == "client"
        assert triple.widget == WidgetKind.SEARCH_SELECT
        assert triple.is_fk is True
        assert triple.ref_entity == "Client"

    def test_uuid_fk_id_field(self) -> None:
        field = _make_field("client_id", FieldTypeKind.UUID)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=True,
            ref_entity="Client",
        )
        assert triple.widget == WidgetKind.SEARCH_SELECT
        assert triple.is_fk is True

    def test_triple_is_frozen(self) -> None:
        field = _make_field("name", FieldTypeKind.STR)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=False,
            is_fk=False,
            ref_entity=None,
        )
        with pytest.raises(ValidationError):
            triple.field_name = "other"  # type: ignore[misc]

    def test_optional_field(self) -> None:
        field = _make_field("notes", FieldTypeKind.TEXT)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=False,
            ref_entity=None,
        )
        assert triple.is_required is False
        assert triple.widget == WidgetKind.TEXTAREA


# ---------------------------------------------------------------------------
# Helpers for permission + action tests
# ---------------------------------------------------------------------------


def _make_entity(
    name: str,
    permissions: list[tuple[PermissionKind, list[str]]] | None = None,
    state_machine: StateMachineSpec | None = None,
) -> EntitySpec:
    """Build a minimal EntitySpec with optional permissions and state machine."""
    access: AccessSpec | None = None
    if permissions is not None:
        rules = [
            PermissionRule(
                operation=op,
                personas=personas,
                effect=PolicyEffect.PERMIT,
            )
            for op, personas in permissions
        ]
        access = AccessSpec(permissions=rules)
    return EntitySpec(
        name=name,
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            )
        ],
        access=access,
        state_machine=state_machine,
    )


def _make_surface(name: str, entity_ref: str, mode: SurfaceMode) -> SurfaceSpec:
    """Build a minimal SurfaceSpec."""
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=mode)


def _make_personas(*ids: str) -> list[PersonaSpec]:
    """Build a list of PersonaSpec from IDs."""
    return [PersonaSpec(id=pid, label=pid.capitalize()) for pid in ids]


# ---------------------------------------------------------------------------
# TestGetPermittedPersonas
# ---------------------------------------------------------------------------


class TestGetPermittedPersonas:
    def test_open_permissions_all_personas(self) -> None:
        """A permit rule with no personas list returns all personas."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, [])],
        )
        personas = _make_personas("admin", "viewer", "editor")
        result = get_permitted_personas([entity], personas, "Task", PermissionKind.READ)
        assert set(result) == {"admin", "viewer", "editor"}

    def test_restricted_to_named_personas_only(self) -> None:
        """A permit rule naming specific personas returns only those IDs."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.UPDATE, ["editor", "admin"])],
        )
        personas = _make_personas("admin", "viewer", "editor")
        result = get_permitted_personas([entity], personas, "Task", PermissionKind.UPDATE)
        assert set(result) == {"editor", "admin"}

    def test_no_access_spec_defaults_to_all_personas(self) -> None:
        """Entity with no access spec at all defaults to all personas."""
        entity = _make_entity("Task")  # no permissions
        personas = _make_personas("admin", "viewer")
        result = get_permitted_personas([entity], personas, "Task", PermissionKind.READ)
        assert set(result) == {"admin", "viewer"}

    def test_entity_not_found_returns_all_personas(self) -> None:
        """Requesting an unknown entity name returns all personas (safe default)."""
        entity = _make_entity("Task", permissions=[(PermissionKind.READ, ["admin"])])
        personas = _make_personas("admin", "viewer")
        result = get_permitted_personas([entity], personas, "Other", PermissionKind.READ)
        assert set(result) == {"admin", "viewer"}

    def test_operation_without_rule_returns_empty(self) -> None:
        """If the entity has access spec but no rule for the operation, returns empty."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, ["admin"])],
        )
        personas = _make_personas("admin", "viewer")
        # DELETE has no rule, so permitted set is empty
        result = get_permitted_personas([entity], personas, "Task", PermissionKind.DELETE)
        assert result == []

    def test_multiple_rules_same_operation_union(self) -> None:
        """Multiple permit rules for the same operation produce a union."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, ["admin"]),
                (PermissionKind.READ, ["viewer"]),
            ],
        )
        personas = _make_personas("admin", "viewer", "editor")
        result = get_permitted_personas([entity], personas, "Task", PermissionKind.READ)
        assert set(result) == {"admin", "viewer"}


# ---------------------------------------------------------------------------
# TestResolveSurfaceActions
# ---------------------------------------------------------------------------


class TestResolveSurfaceActions:
    def test_list_mode_basic_actions(self) -> None:
        """List mode always has list and detail_link actions."""
        entity = _make_entity("Task", permissions=[(PermissionKind.READ, [])])
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "list" in action_names
        assert "detail_link" in action_names

    def test_list_mode_create_link_when_create_permitted(self) -> None:
        """List mode includes create_link when CREATE is permitted to any persona."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, []),
                (PermissionKind.CREATE, ["admin"]),
            ],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin", "viewer")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "create_link" in action_names

    def test_list_mode_no_create_link_when_create_not_permitted(self) -> None:
        """List mode omits create_link when there is no CREATE rule."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, [])],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "create_link" not in action_names

    def test_view_mode_no_edit_surface(self) -> None:
        """View mode without a sibling edit surface has no edit_link action."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, []),
                (PermissionKind.UPDATE, ["admin"]),
            ],
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, view_surface, [view_surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "edit_link" not in action_names

    def test_view_mode_with_edit_surface(self) -> None:
        """View mode includes edit_link when an edit surface for the entity exists."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, []),
                (PermissionKind.UPDATE, ["admin"]),
            ],
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        edit_surface = _make_surface("task_edit", "Task", SurfaceMode.EDIT)
        personas = _make_personas("admin")
        all_surfaces = [view_surface, edit_surface]
        result = resolve_surface_actions(entity, view_surface, all_surfaces, personas, [entity])
        action_names = [t.action for t in result]
        assert "edit_link" in action_names

    def test_view_mode_with_delete_permission(self) -> None:
        """View mode includes delete_button when DELETE is permitted."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, []),
                (PermissionKind.DELETE, ["admin"]),
            ],
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, view_surface, [view_surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "delete_button" in action_names

    def test_view_mode_no_delete_when_not_permitted(self) -> None:
        """View mode omits delete_button when there is no DELETE rule."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, [])],
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, view_surface, [view_surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "delete_button" not in action_names

    def test_view_mode_with_transitions(self) -> None:
        """View mode emits transition:{name} actions for manual state transitions."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "closed"],
            transitions=[
                StateTransition(
                    from_state="open",
                    to_state="closed",
                    trigger=TransitionTrigger.MANUAL,
                ),
            ],
        )
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, [])],
            state_machine=sm,
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, view_surface, [view_surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "transition:open->closed" in action_names

    def test_view_mode_auto_transitions_excluded(self) -> None:
        """Auto transitions are NOT surfaced as user-facing actions."""
        sm = StateMachineSpec(
            status_field="status",
            states=["pending", "done"],
            transitions=[
                StateTransition(
                    from_state="pending",
                    to_state="done",
                    trigger=TransitionTrigger.AUTO,
                ),
            ],
        )
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.READ, [])],
            state_machine=sm,
        )
        view_surface = _make_surface("task_view", "Task", SurfaceMode.VIEW)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, view_surface, [view_surface], personas, [entity])
        action_names = [t.action for t in result]
        assert "transition:pending->done" not in action_names

    def test_create_mode_gives_create_submit(self) -> None:
        """Create mode gives only create_submit action."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.CREATE, [])],
        )
        surface = _make_surface("task_create", "Task", SurfaceMode.CREATE)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        action_names = [t.action for t in result]
        assert action_names == ["create_submit"]

    def test_edit_mode_gives_edit_submit(self) -> None:
        """Edit mode gives only edit_submit action."""
        entity = _make_entity(
            "Task",
            permissions=[(PermissionKind.UPDATE, [])],
        )
        surface = _make_surface("task_edit", "Task", SurfaceMode.EDIT)
        personas = _make_personas("admin")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        action_names = [t.action for t in result]
        assert action_names == ["edit_submit"]

    def test_surface_action_triple_is_frozen(self) -> None:
        """SurfaceActionTriple must be immutable."""
        triple = SurfaceActionTriple(
            action="list",
            requires_permission=PermissionKind.READ,
            visible_to=["admin"],
        )
        with pytest.raises(ValidationError):
            triple.action = "other"  # type: ignore[misc]

    def test_visible_to_reflects_permitted_personas(self) -> None:
        """visible_to on action triples reflects which personas are permitted."""
        entity = _make_entity(
            "Task",
            permissions=[
                (PermissionKind.READ, ["admin", "viewer"]),
                (PermissionKind.CREATE, ["admin"]),
            ],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin", "viewer", "editor")
        result = resolve_surface_actions(entity, surface, [surface], personas, [entity])
        by_action = {t.action: t for t in result}
        assert set(by_action["list"].visible_to) == {"admin", "viewer"}
        assert set(by_action["create_link"].visible_to) == {"admin"}


# ---------------------------------------------------------------------------
# TestDeriveTriples
# ---------------------------------------------------------------------------


class TestDeriveTriples:
    """Tests for derive_triples() and supporting helpers."""

    def _entity_with_fields(
        self,
        name: str,
        extra_fields: list[FieldSpec] | None = None,
        permissions: list[tuple[PermissionKind, list[str]]] | None = None,
    ) -> EntitySpec:
        """Build an entity with a PK field plus optional extra fields."""
        fields = [
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            )
        ]
        if extra_fields:
            fields.extend(extra_fields)
        access: AccessSpec | None = None
        if permissions is not None:
            rules = [
                PermissionRule(
                    operation=op,
                    personas=personas,
                    effect=PolicyEffect.PERMIT,
                )
                for op, personas in permissions
            ]
            access = AccessSpec(permissions=rules)
        return EntitySpec(name=name, fields=fields, access=access)

    def test_basic_triple_count(self) -> None:
        """derive_triples produces one triple per (entity × surface × persona)
        where the persona has at least one permitted action."""
        from dazzle.core.ir.triples import derive_triples

        entity = self._entity_with_fields(
            "Task",
            permissions=[(PermissionKind.READ, [])],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin", "viewer")

        triples = derive_triples([entity], [surface], personas)
        # Both personas can READ → both should appear
        assert len(triples) == 2
        persona_ids = {t.persona for t in triples}
        assert persona_ids == {"admin", "viewer"}

    def test_triple_fields_populated(self) -> None:
        """Triple records entity name, surface name, persona, mode, actions and fields."""
        from dazzle.core.ir.triples import VerifiableTriple, derive_triples

        title_field = FieldSpec(
            name="title",
            type=FieldType(kind=FieldTypeKind.STR),
            modifiers=[FieldModifier.REQUIRED],
        )
        entity = self._entity_with_fields(
            "Task",
            extra_fields=[title_field],
            permissions=[(PermissionKind.READ, [])],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")

        triples = derive_triples([entity], [surface], personas)
        assert len(triples) == 1
        t: VerifiableTriple = triples[0]
        assert t.entity == "Task"
        assert t.surface == "task_list"
        assert t.persona == "admin"
        assert t.surface_mode == SurfaceMode.LIST
        # At minimum the list action should be present
        assert any("list" in a for a in t.action_names)
        # title field should appear in fields (PK id excluded)
        field_names = {f.field_name for f in t.fields}
        assert "title" in field_names
        assert "id" not in field_names

    def test_framework_entities_excluded(self) -> None:
        """Framework entities (AIJob, FeedbackReport, etc.) are skipped."""
        from dazzle.core.ir.triples import derive_triples

        framework_names = [
            "AIJob",
            "FeedbackReport",
            "SystemHealth",
            "SystemMetric",
            "DeployHistory",
        ]
        entities = [self._entity_with_fields(name) for name in framework_names]
        task = self._entity_with_fields("Task", permissions=[(PermissionKind.READ, [])])
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")

        triples = derive_triples(entities + [task], [surface], personas)
        entity_names = {t.entity for t in triples}
        for fw in framework_names:
            assert fw not in entity_names
        assert "Task" in entity_names

    def test_entity_without_surfaces_produces_no_triples(self) -> None:
        """If an entity has no surfaces, no triples are emitted."""
        from dazzle.core.ir.triples import derive_triples

        entity = self._entity_with_fields("Task", permissions=[(PermissionKind.READ, [])])
        personas = _make_personas("admin")

        triples = derive_triples([entity], [], personas)
        assert triples == []

    def test_persona_actions_filtered_by_permission(self) -> None:
        """Admin sees create_link; viewer doesn't."""
        from dazzle.core.ir.triples import derive_triples

        entity = self._entity_with_fields(
            "Task",
            permissions=[
                (PermissionKind.READ, []),
                (PermissionKind.CREATE, ["admin"]),
            ],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin", "viewer")

        triples = derive_triples([entity], [surface], personas)
        by_persona = {t.persona: t for t in triples}

        assert "admin" in by_persona
        assert "viewer" in by_persona
        # Admin should see create_link; viewer should not
        assert "create_link" in by_persona["admin"].action_names
        assert "create_link" not in by_persona["viewer"].action_names

    def test_fields_exclude_pk_and_auto(self) -> None:
        """PK and auto_add/auto_update fields are excluded from field triples."""
        from dazzle.core.ir.triples import derive_triples

        auto_add_field = FieldSpec(
            name="created_at",
            type=FieldType(kind=FieldTypeKind.DATETIME),
            modifiers=[FieldModifier.AUTO_ADD],
        )
        auto_update_field = FieldSpec(
            name="updated_at",
            type=FieldType(kind=FieldTypeKind.DATETIME),
            modifiers=[FieldModifier.AUTO_UPDATE],
        )
        title_field = FieldSpec(
            name="title",
            type=FieldType(kind=FieldTypeKind.STR),
            modifiers=[FieldModifier.REQUIRED],
        )
        entity = self._entity_with_fields(
            "Task",
            extra_fields=[auto_add_field, auto_update_field, title_field],
            permissions=[(PermissionKind.READ, [])],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")

        triples = derive_triples([entity], [surface], personas)
        assert len(triples) == 1
        field_names = {f.field_name for f in triples[0].fields}
        assert "id" not in field_names
        assert "created_at" not in field_names
        assert "updated_at" not in field_names
        assert "title" in field_names

    def test_fk_fields_not_required_in_triple(self) -> None:
        """FK fields that are required in the entity carry is_required=False in the triple."""
        from dazzle.core.ir.triples import derive_triples

        fk_field = FieldSpec(
            name="project",
            type=FieldType(kind=FieldTypeKind.REF, ref_entity="Project"),
            modifiers=[FieldModifier.REQUIRED],
        )
        entity = self._entity_with_fields(
            "Task",
            extra_fields=[fk_field],
            permissions=[(PermissionKind.READ, [])],
        )
        surface = _make_surface("task_list", "Task", SurfaceMode.LIST)
        personas = _make_personas("admin")

        triples = derive_triples([entity], [surface], personas)
        assert len(triples) == 1
        field_triples = {f.field_name: f for f in triples[0].fields}
        assert "project" in field_triples
        # FK field should be is_required=False in the triple
        assert field_triples["project"].is_required is False

    def test_surface_sections_used_when_present(self) -> None:
        """When the surface declares sections, only those fields appear in the triple."""
        from dazzle.core.ir.surfaces import SurfaceElement, SurfaceSection
        from dazzle.core.ir.triples import derive_triples

        title_field = FieldSpec(
            name="title",
            type=FieldType(kind=FieldTypeKind.STR),
            modifiers=[FieldModifier.REQUIRED],
        )
        notes_field = FieldSpec(
            name="notes",
            type=FieldType(kind=FieldTypeKind.TEXT),
        )
        entity = self._entity_with_fields(
            "Task",
            extra_fields=[title_field, notes_field],
            permissions=[(PermissionKind.READ, [])],
        )
        # Surface only declares title, not notes
        section = SurfaceSection(
            name="main",
            elements=[SurfaceElement(field_name="title")],
        )
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[section],
        )
        personas = _make_personas("admin")

        triples = derive_triples([entity], [surface], personas)
        assert len(triples) == 1
        field_names = {f.field_name for f in triples[0].fields}
        assert "title" in field_names
        assert "notes" not in field_names


# ---------------------------------------------------------------------------
# TestLinkerIntegration
# ---------------------------------------------------------------------------


class TestLinkerIntegration:
    """Integration tests: derive_triples wired into the linker pipeline."""

    def test_simple_task_has_triples(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(Path("examples/simple_task"))
        assert len(appspec.triples) > 0

    def test_fieldtest_hub_has_triples(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(Path("examples/fieldtest_hub"))
        assert len(appspec.triples) > 0

    def test_get_triple_getter(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(Path("examples/simple_task"))
        if appspec.triples:
            t = appspec.triples[0]
            found = appspec.get_triple(t.entity, t.surface, t.persona)
            assert found is not None
            assert found.entity == t.entity

    def test_get_triples_for_entity(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(Path("examples/simple_task"))
        if appspec.triples:
            entity_name = appspec.triples[0].entity
            results = appspec.get_triples_for_entity(entity_name)
            assert all(t.entity == entity_name for t in results)

    def test_get_triples_for_persona(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(Path("examples/simple_task"))
        if appspec.triples:
            persona = appspec.triples[0].persona
            results = appspec.get_triples_for_persona(persona)
            assert all(t.persona == persona for t in results)


# ---------------------------------------------------------------------------
# TestContractParity — ensure generate_contracts produces expected output
# ---------------------------------------------------------------------------


class TestContractParity:
    def test_fieldtest_hub_produces_contracts(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.ux.contracts import generate_contracts

        appspec = load_project_appspec(Path("examples/fieldtest_hub"))
        contracts = generate_contracts(appspec)
        assert len(contracts) > 0
        kinds = {str(c.kind) for c in contracts}
        assert "list_page" in kinds
        assert "rbac" in kinds

    def test_simple_task_produces_contracts(self) -> None:
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.ux.contracts import generate_contracts

        appspec = load_project_appspec(Path("examples/simple_task"))
        contracts = generate_contracts(appspec)
        assert len(contracts) > 0
