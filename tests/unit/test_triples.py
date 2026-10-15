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
    def test_uuid_id_suffix_widget_resolution(self) -> None:
        """Combined: pk-named-id stays TEXT_INPUT, uuid _id suffix → SEARCH_SELECT,
        str _id NOT affected, uuid without _id stays TEXT_INPUT."""
        # Plain 'id' primary key → TEXT_INPUT
        field = _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

        # uuid FK column 'client_id' → SEARCH_SELECT
        assert (
            resolve_widget(_make_field("client_id", FieldTypeKind.UUID)) == WidgetKind.SEARCH_SELECT
        )

        # longer name 'assessment_event_id' → SEARCH_SELECT
        assert (
            resolve_widget(_make_field("assessment_event_id", FieldTypeKind.UUID))
            == WidgetKind.SEARCH_SELECT
        )

        # str field with _id suffix is not affected (rule is uuid-only)
        assert resolve_widget(_make_field("some_id", FieldTypeKind.STR)) == WidgetKind.TEXT_INPUT

        # uuid not ending in _id stays TEXT_INPUT
        assert (
            resolve_widget(_make_field("record_uuid", FieldTypeKind.UUID)) == WidgetKind.TEXT_INPUT
        )


# ---------------------------------------------------------------------------
# resolve_widget: has_source override
# ---------------------------------------------------------------------------


class TestResolveWidgetHasSource:
    @pytest.mark.parametrize(
        ("field", "has_source", "expected"),
        [
            pytest.param(
                _make_field("owner", FieldTypeKind.STR),
                True,
                WidgetKind.SEARCH_SELECT,
                id="overrides-str",
            ),
            # Even 'id' gets SEARCH_SELECT when has_source=True.
            pytest.param(
                _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK]),
                True,
                WidgetKind.SEARCH_SELECT,
                id="overrides-uuid-pk-id",
            ),
            pytest.param(
                _make_field("notes", FieldTypeKind.TEXT),
                False,
                WidgetKind.TEXTAREA,
                id="false-leaves-default",
            ),
        ],
    )
    def test_has_source(self, field: FieldSpec, has_source: bool, expected: WidgetKind) -> None:
        assert resolve_widget(field, has_source=has_source) == expected


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


def _one_transition_sm(
    from_state: str, to_state: str, trigger: TransitionTrigger
) -> StateMachineSpec:
    """Two-state machine with a single transition."""
    return StateMachineSpec(
        status_field="status",
        states=[from_state, to_state],
        transitions=[StateTransition(from_state=from_state, to_state=to_state, trigger=trigger)],
    )


# ---------------------------------------------------------------------------
# TestGetPermittedPersonas
# ---------------------------------------------------------------------------


class TestGetPermittedPersonas:
    @pytest.mark.parametrize(
        ("permissions", "persona_ids", "query_entity", "query_op", "expected"),
        [
            (
                [(PermissionKind.READ, [])],
                ("admin", "viewer", "editor"),
                "Task",
                PermissionKind.READ,
                {"admin", "viewer", "editor"},
            ),
            (
                [(PermissionKind.UPDATE, ["editor", "admin"])],
                ("admin", "viewer", "editor"),
                "Task",
                PermissionKind.UPDATE,
                {"editor", "admin"},
            ),
            (
                None,
                ("admin", "viewer"),
                "Task",
                PermissionKind.READ,
                {"admin", "viewer"},
            ),
            (
                [(PermissionKind.READ, ["admin"])],
                ("admin", "viewer"),
                "Other",
                PermissionKind.READ,
                {"admin", "viewer"},
            ),
            (
                [(PermissionKind.READ, ["admin"])],
                ("admin", "viewer"),
                "Task",
                PermissionKind.DELETE,
                set(),
            ),
            (
                [
                    (PermissionKind.READ, ["admin"]),
                    (PermissionKind.READ, ["viewer"]),
                ],
                ("admin", "viewer", "editor"),
                "Task",
                PermissionKind.READ,
                {"admin", "viewer"},
            ),
        ],
        ids=[
            "test_open_permissions_all_personas",
            "test_restricted_to_named_personas_only",
            "test_no_access_spec_defaults_to_all_personas",
            "test_entity_not_found_returns_all_personas",
            "test_operation_without_rule_returns_empty",
            "test_multiple_rules_same_operation_union",
        ],
    )
    def test_get_permitted_personas(
        self, permissions, persona_ids, query_entity, query_op, expected
    ) -> None:
        if permissions is None:
            entity = _make_entity("Task")
        else:
            entity = _make_entity("Task", permissions=permissions)
        personas = _make_personas(*persona_ids)
        result = get_permitted_personas([entity], personas, query_entity, query_op)
        assert set(result) == expected

    @pytest.mark.parametrize(
        ("rules", "personas", "op", "expected"),
        [
            # The #1281 short-form `permit: create: false` must not fall
            # through to the open-rule branch and permit every persona.
            pytest.param(
                [
                    PermissionRule(
                        operation=PermissionKind.CREATE,
                        personas=[],
                        deny_all=True,
                        effect=PolicyEffect.PERMIT,
                    )
                ],
                _make_personas("admin", "teacher"),
                PermissionKind.CREATE,
                [],
                id="deny-all-permits-nobody-1520",
            ),
            # Cedar forbid > permit: a persona matched by a FORBID rule is
            # excluded even when an open PERMIT rule also matches it.
            pytest.param(
                [
                    PermissionRule(
                        operation=PermissionKind.READ, personas=[], effect=PolicyEffect.PERMIT
                    ),
                    PermissionRule(
                        operation=PermissionKind.READ,
                        personas=["viewer"],
                        effect=PolicyEffect.FORBID,
                    ),
                ],
                _make_personas("admin", "viewer"),
                PermissionKind.READ,
                ["admin"],
                id="forbid-overrides-permit-1520",
            ),
            # A persona whose `role:` differs from its id matches rules naming
            # the role, and the returned list carries the persona id.
            pytest.param(
                [
                    PermissionRule(
                        operation=PermissionKind.UPDATE,
                        personas=["staff"],
                        effect=PolicyEffect.PERMIT,
                    )
                ],
                [
                    PersonaSpec(id="alice", label="Alice", role="staff"),
                    PersonaSpec(id="bob", label="Bob", role="customer"),
                ],
                PermissionKind.UPDATE,
                ["alice"],
                id="matches-effective-role-not-persona-id-1520-1147",
            ),
        ],
    )
    def test_rule_semantics(
        self,
        rules: list[PermissionRule],
        personas: list[PersonaSpec],
        op: PermissionKind,
        expected: list[str],
    ) -> None:
        entity = _make_entity("Task").model_copy(update={"access": AccessSpec(permissions=rules)})
        assert get_permitted_personas([entity], personas, "Task", op) == expected


# ---------------------------------------------------------------------------
# TestResolveSurfaceActions
# ---------------------------------------------------------------------------


class TestResolveSurfaceActions:
    @pytest.mark.parametrize(
        ("permissions", "state_machine", "mode", "with_edit_surface", "persona_ids", "expected"),
        [
            # List mode always has list and detail_link actions.
            pytest.param(
                [(PermissionKind.READ, [])],
                None,
                SurfaceMode.LIST,
                False,
                ("admin",),
                ["list", "detail_link"],
                id="list-basic-no-create-link-without-create-rule",
            ),
            pytest.param(
                [(PermissionKind.READ, []), (PermissionKind.CREATE, ["admin"])],
                None,
                SurfaceMode.LIST,
                False,
                ("admin", "viewer"),
                ["list", "detail_link", "create_link"],
                id="list-create-link-when-create-permitted",
            ),
            pytest.param(
                [(PermissionKind.READ, []), (PermissionKind.UPDATE, ["admin"])],
                None,
                SurfaceMode.VIEW,
                False,
                ("admin",),
                [],
                id="view-no-edit-link-without-edit-surface",
            ),
            pytest.param(
                [(PermissionKind.READ, []), (PermissionKind.UPDATE, ["admin"])],
                None,
                SurfaceMode.VIEW,
                True,
                ("admin",),
                ["edit_link"],
                id="view-edit-link-with-edit-surface",
            ),
            pytest.param(
                [(PermissionKind.READ, []), (PermissionKind.DELETE, ["admin"])],
                None,
                SurfaceMode.VIEW,
                False,
                ("admin",),
                ["delete_button"],
                id="view-delete-button-when-delete-permitted",
            ),
            pytest.param(
                [(PermissionKind.READ, [])],
                None,
                SurfaceMode.VIEW,
                False,
                ("admin",),
                [],
                id="view-no-delete-button-without-delete-rule",
            ),
            pytest.param(
                [(PermissionKind.READ, [])],
                _one_transition_sm("open", "closed", TransitionTrigger.MANUAL),
                SurfaceMode.VIEW,
                False,
                ("admin",),
                ["transition:open->closed"],
                id="view-manual-transition-action",
            ),
            # Auto transitions are NOT surfaced as user-facing actions.
            pytest.param(
                [(PermissionKind.READ, [])],
                _one_transition_sm("pending", "done", TransitionTrigger.AUTO),
                SurfaceMode.VIEW,
                False,
                ("admin",),
                [],
                id="view-auto-transition-excluded",
            ),
        ],
    )
    def test_action_names(
        self,
        permissions: list[tuple[PermissionKind, list[str]]],
        state_machine: StateMachineSpec | None,
        mode: SurfaceMode,
        with_edit_surface: bool,
        persona_ids: tuple[str, ...],
        expected: list[str],
    ) -> None:
        entity = _make_entity("Task", permissions=permissions, state_machine=state_machine)
        surface = _make_surface("task_surface", "Task", mode)
        all_surfaces = [surface]
        if with_edit_surface:
            all_surfaces.append(_make_surface("task_edit", "Task", SurfaceMode.EDIT))
        result = resolve_surface_actions(
            entity, surface, all_surfaces, _make_personas(*persona_ids), [entity]
        )
        assert [t.action for t in result] == expected

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
