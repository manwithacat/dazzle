"""
Widget resolution, permission helpers, and surface action derivation for DAZZLE IR.

This module provides:
- WidgetKind: enumeration of UI widget types
- _WIDGET_MAP: mapping from FieldTypeKind to WidgetKind
- resolve_widget(): derives the correct widget for a FieldSpec
- SurfaceFieldTriple: frozen Pydantic model capturing per-field UI metadata
- Permission helpers (_condition_matches_role, _condition_is_pure_role_only,
  _rule_matches_persona, get_permitted_personas): static permission analysis
- SurfaceActionTriple: frozen Pydantic model capturing per-action UI metadata
- resolve_surface_actions(): derives the set of actions for a surface

The widget mapping mirrors the form-type logic in
``dazzle_ui/converters/template_compiler.py`` but lives in the IR layer
with no UI-layer imports, making it available to static analysis, testing
and the contract verification layer.

Permission helpers were originally in ``dazzle.testing.ux.contracts`` and
are migrated here so the IR layer owns the derivation logic independently
of the testing layer.
"""

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dazzle.core.ir.fields import FieldSpec, FieldTypeKind


class WidgetKind(StrEnum):
    """UI widget types that can be rendered for a surface field."""

    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    DATE_PICKER = "date_picker"
    DATETIME_PICKER = "datetime_picker"
    NUMBER_INPUT = "number_input"
    EMAIL_INPUT = "email_input"
    ENUM_SELECT = "enum_select"
    SEARCH_SELECT = "search_select"
    MONEY_INPUT = "money_input"
    FILE_UPLOAD = "file_upload"


# Default mapping from field type kind to widget kind.
# Relationship types (REF, HAS_MANY, HAS_ONE, EMBEDS, BELONGS_TO) all map to
# SEARCH_SELECT because they always resolve against another entity.
_WIDGET_MAP: dict[FieldTypeKind, WidgetKind] = {
    FieldTypeKind.STR: WidgetKind.TEXT_INPUT,
    FieldTypeKind.TEXT: WidgetKind.TEXTAREA,
    FieldTypeKind.INT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.DECIMAL: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.FLOAT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.BOOL: WidgetKind.CHECKBOX,
    FieldTypeKind.DATE: WidgetKind.DATE_PICKER,
    FieldTypeKind.DATETIME: WidgetKind.DATETIME_PICKER,
    FieldTypeKind.UUID: WidgetKind.TEXT_INPUT,
    FieldTypeKind.ENUM: WidgetKind.ENUM_SELECT,
    FieldTypeKind.REF: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.EMAIL: WidgetKind.EMAIL_INPUT,
    FieldTypeKind.JSON: WidgetKind.TEXTAREA,
    FieldTypeKind.MONEY: WidgetKind.MONEY_INPUT,
    FieldTypeKind.FILE: WidgetKind.FILE_UPLOAD,
    FieldTypeKind.URL: WidgetKind.TEXT_INPUT,
    FieldTypeKind.TIMEZONE: WidgetKind.TEXT_INPUT,
    FieldTypeKind.HAS_MANY: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.HAS_ONE: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.EMBEDS: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.BELONGS_TO: WidgetKind.SEARCH_SELECT,
}


def resolve_widget(field: FieldSpec, *, has_source: bool = False) -> WidgetKind:
    """Derive the appropriate UI widget kind for a field.

    Resolution order:
    1. ``has_source=True`` always yields ``SEARCH_SELECT`` — the field has a
       declared data source so it renders as a search/select control.
    2. UUID fields whose name ends in ``_id`` (but are not literally named
       ``"id"``) are treated as FK columns and yield ``SEARCH_SELECT``.
    3. All other fields resolve through ``_WIDGET_MAP``; unmapped kinds fall
       back to ``TEXT_INPUT``.

    Args:
        field: The ``FieldSpec`` to inspect.
        has_source: Whether the field has an explicit ``source:`` declaration
            in the DSL that points to an entity or view.

    Returns:
        The ``WidgetKind`` appropriate for rendering this field.
    """
    if has_source:
        return WidgetKind.SEARCH_SELECT

    # UUID FK column convention: foo_id → SEARCH_SELECT, but plain 'id' stays TEXT_INPUT
    if field.type.kind == FieldTypeKind.UUID and field.name != "id" and field.name.endswith("_id"):
        return WidgetKind.SEARCH_SELECT

    return _WIDGET_MAP.get(field.type.kind, WidgetKind.TEXT_INPUT)


class SurfaceFieldTriple(BaseModel):
    """Frozen snapshot of per-field UI metadata for a surface.

    Captures everything the contract verification and template layers need to
    know about how a single field should be rendered, without re-deriving it
    from the raw FieldSpec on every pass.

    Attributes:
        field_name: The DSL field identifier.
        widget: The resolved widget kind for this field.
        is_required: Whether the field carries the ``required`` modifier.
        is_fk: Whether this field is a foreign-key reference to another entity.
        ref_entity: Name of the referenced entity when ``is_fk`` is ``True``.
    """

    model_config = ConfigDict(frozen=True)

    field_name: str
    widget: WidgetKind
    is_required: bool
    is_fk: bool
    ref_entity: str | None


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _condition_matches_role(condition: object, role: str) -> bool:
    """Return True if a ConditionExpr tree contains a role_check matching *role*.

    Uses duck-typing via ``getattr`` so the IR condition types are not imported
    at module level (avoids circular imports).
    """
    if condition is None:
        return False
    role_check = getattr(condition, "role_check", None)
    if role_check is not None:
        return getattr(role_check, "role_name", None) == role
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None or right is not None:
        return _condition_matches_role(left, role) or _condition_matches_role(right, role)
    return False


def _condition_is_pure_role_only(condition: object) -> bool:
    """Return True if the condition tree contains only role_check nodes.

    A condition is "pure role only" when it has no field comparisons
    (``comparison``) and no grant checks (``grant_check``).  Such a condition
    can be mapped directly to a persona list by matching role names against
    persona IDs.
    """
    if condition is None:
        return False
    if getattr(condition, "comparison", None) is not None:
        return False
    if getattr(condition, "grant_check", None) is not None:
        return False
    if getattr(condition, "role_check", None) is not None:
        return True
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None or right is not None:
        left_pure = _condition_is_pure_role_only(left) if left is not None else True
        right_pure = _condition_is_pure_role_only(right) if right is not None else True
        return left_pure and right_pure
    return False


def _rule_matches_persona(rule: object, persona_id: str) -> bool:
    """Return True if a PermissionRule applies to the given persona ID.

    Evaluation order:
    1. If the rule has explicit ``personas``, check membership.
    2. If the condition is a pure role gate, check whether the role name
       matches the persona ID.
    3. Otherwise (open rule), return True — any authenticated persona matches.
    """
    personas = getattr(rule, "personas", [])
    condition = getattr(rule, "condition", None)
    if not personas:
        if _condition_is_pure_role_only(condition):
            return _condition_matches_role(condition, persona_id)
        return True  # open to all authenticated
    if persona_id in personas:
        return True
    if _condition_matches_role(condition, persona_id):
        return True
    return False


def get_permitted_personas(
    entities: Sequence[object],
    personas: Sequence[object],
    entity_name: str,
    operation: object,
) -> list[str]:
    """Return persona IDs that hold a PERMIT rule for *operation* on *entity_name*.

    Args:
        entities: Sequence of ``EntitySpec`` instances to search.
        personas: Sequence of ``PersonaSpec`` instances (provides the full set
            of known persona IDs).
        entity_name: The entity to check permissions against.
        operation: A ``PermissionKind`` value naming the operation
            (``create``, ``read``, ``update``, ``delete``, ``list``).

    Returns:
        A list of persona IDs.  When the entity has no access spec the full
        persona list is returned (open-by-default).  When the access spec
        exists but has no rule for *operation* an empty list is returned
        (deny-by-default for that operation).
    """
    from dazzle.core.ir.domain import PolicyEffect

    entity = next((e for e in entities if getattr(e, "name", None) == entity_name), None)
    if entity is None or not getattr(entity, "access", None):
        return [getattr(p, "id", str(p)) for p in personas]

    permitted: set[str] = set()
    access = entity.access
    for rule in getattr(access, "permissions", []):
        if getattr(rule, "operation", None) != operation:
            continue
        effect = getattr(rule, "effect", PolicyEffect.PERMIT)
        if effect != PolicyEffect.PERMIT:
            continue
        rule_personas: list[str] = getattr(rule, "personas", [])
        if rule_personas:
            permitted.update(rule_personas)
        else:
            condition = getattr(rule, "condition", None)
            if _condition_is_pure_role_only(condition):
                for p in personas:
                    pid = getattr(p, "id", str(p))
                    if _condition_matches_role(condition, pid):
                        permitted.add(pid)
            else:
                # Open rule — all personas permitted
                return [getattr(p, "id", str(p)) for p in personas]

    return list(permitted)


# ---------------------------------------------------------------------------
# SurfaceActionTriple + resolve_surface_actions
# ---------------------------------------------------------------------------


class SurfaceActionTriple(BaseModel):
    """Frozen snapshot of a derived user-facing action for a surface.

    Captures the action name, the permission kind that governs it, and the
    set of persona IDs that can see/perform the action.

    Attributes:
        action: Canonical action identifier (e.g. ``"list"``, ``"create_link"``,
            ``"edit_link"``, ``"delete_button"``, ``"transition:open->closed"``,
            ``"create_submit"``, ``"edit_submit"``).
        requires_permission: The ``PermissionKind`` that controls this action.
        visible_to: Persona IDs permitted to perform this action.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    requires_permission: object  # PermissionKind — typed as object to avoid import cycle
    visible_to: list[str]


def resolve_surface_actions(
    entity: object,
    surface: object,
    all_surfaces: Sequence[object],
    personas: Sequence[object],
    entities: Sequence[object],
) -> list[SurfaceActionTriple]:
    """Derive the set of user-facing action triples for a surface.

    Derives actions based on the surface mode and the permission rules on the
    entity.  The derivation rules are:

    * ``list`` → always ``list`` + ``detail_link``; ``create_link`` if CREATE
      is permitted to at least one persona.
    * ``view`` → ``edit_link`` if UPDATE is permitted AND a sibling edit
      surface exists for the entity; ``delete_button`` if DELETE is permitted;
      ``transition:{from}->{to}`` for each non-auto state transition.
    * ``create`` → ``create_submit`` only.
    * ``edit`` → ``edit_submit`` only.

    Args:
        entity: An ``EntitySpec`` instance.
        surface: A ``SurfaceSpec`` instance for which actions are derived.
        all_surfaces: All ``SurfaceSpec`` instances in the app (used to detect
            sibling edit surfaces for view-mode ``edit_link``).
        personas: All ``PersonaSpec`` instances.
        entities: All ``EntitySpec`` instances (passed to
            ``get_permitted_personas``).

    Returns:
        A list of ``SurfaceActionTriple`` instances, one per derived action.
    """
    from dazzle.core.ir.domain import PermissionKind
    from dazzle.core.ir.state_machine import TransitionTrigger
    from dazzle.core.ir.surfaces import SurfaceMode

    entity_name: str = getattr(entity, "name", "")
    mode: SurfaceMode = getattr(surface, "mode", SurfaceMode.CUSTOM)

    def _permitted(op: PermissionKind) -> list[str]:
        return get_permitted_personas(entities, personas, entity_name, op)

    triples: list[SurfaceActionTriple] = []

    if mode == SurfaceMode.LIST:
        read_permitted = _permitted(PermissionKind.READ)
        triples.append(
            SurfaceActionTriple(
                action="list",
                requires_permission=PermissionKind.READ,
                visible_to=read_permitted,
            )
        )
        triples.append(
            SurfaceActionTriple(
                action="detail_link",
                requires_permission=PermissionKind.READ,
                visible_to=read_permitted,
            )
        )
        create_permitted = _permitted(PermissionKind.CREATE)
        if create_permitted:
            triples.append(
                SurfaceActionTriple(
                    action="create_link",
                    requires_permission=PermissionKind.CREATE,
                    visible_to=create_permitted,
                )
            )

    elif mode == SurfaceMode.VIEW:
        update_permitted = _permitted(PermissionKind.UPDATE)
        if update_permitted:
            # Only add edit_link if there is a sibling edit surface for this entity
            has_edit_surface = any(
                getattr(s, "mode", None) == SurfaceMode.EDIT
                and getattr(s, "entity_ref", None) == entity_name
                for s in all_surfaces
            )
            if has_edit_surface:
                triples.append(
                    SurfaceActionTriple(
                        action="edit_link",
                        requires_permission=PermissionKind.UPDATE,
                        visible_to=update_permitted,
                    )
                )

        delete_permitted = _permitted(PermissionKind.DELETE)
        if delete_permitted:
            triples.append(
                SurfaceActionTriple(
                    action="delete_button",
                    requires_permission=PermissionKind.DELETE,
                    visible_to=delete_permitted,
                )
            )

        # State machine transitions (manual only)
        sm = getattr(entity, "state_machine", None)
        if sm is not None:
            for transition in getattr(sm, "transitions", []):
                trigger = getattr(transition, "trigger", None)
                if trigger == TransitionTrigger.AUTO:
                    continue
                from_state = getattr(transition, "from_state", "")
                to_state = getattr(transition, "to_state", "")
                triples.append(
                    SurfaceActionTriple(
                        action=f"transition:{from_state}->{to_state}",
                        requires_permission=PermissionKind.UPDATE,
                        visible_to=_permitted(PermissionKind.UPDATE),
                    )
                )

    elif mode == SurfaceMode.CREATE:
        triples.append(
            SurfaceActionTriple(
                action="create_submit",
                requires_permission=PermissionKind.CREATE,
                visible_to=_permitted(PermissionKind.CREATE),
            )
        )

    elif mode == SurfaceMode.EDIT:
        triples.append(
            SurfaceActionTriple(
                action="edit_submit",
                requires_permission=PermissionKind.UPDATE,
                visible_to=_permitted(PermissionKind.UPDATE),
            )
        )

    return triples


# ---------------------------------------------------------------------------
# VerifiableTriple + derive_triples
# ---------------------------------------------------------------------------

# Framework-generated entities that must be excluded from triple derivation.
# These are created by DSL constructs (llm_intent, feedback_widget, etc.) and
# should never appear as verifiable surface triples.
_FRAMEWORK_ENTITIES: frozenset[str] = frozenset(
    {
        "AIJob",
        "FeedbackReport",
        "SystemHealth",
        "SystemMetric",
        "DeployHistory",
    }
)


class VerifiableTriple(BaseModel):
    """Atomic unit of verifiable UI behaviour: (Entity, Surface, Persona).

    Each triple captures everything the contract verification layer needs to
    assert correct behaviour for one persona on one surface: which entity is
    being displayed, the surface mode, which actions the persona can perform,
    and which fields should be present.

    Attributes:
        entity: Name of the entity this surface is bound to.
        surface: Name of the surface (DSL identifier).
        persona: ID of the persona for which this triple was derived.
        surface_mode: The ``SurfaceMode`` of the surface.
        actions: Action identifiers the persona can perform (e.g. ``"list"``,
            ``"create_link"``, ``"edit_submit"``).
        fields: Field-level triples describing widget, FK status and
            requiredness for each visible field.
    """

    model_config = ConfigDict(frozen=True)

    entity: str
    surface: str
    persona: str
    surface_mode: object  # SurfaceMode — typed as object to avoid import cycle
    actions: list[str]
    fields: list[SurfaceFieldTriple]


def _resolve_surface_fields(
    entity: object,
    surface: object,
) -> list[SurfaceFieldTriple]:
    """Build field triples for a surface.

    If the surface has sections with elements, only the declared elements are
    included (respecting any ``source=`` option which marks the field as a
    FK search-select).  When no sections exist, all entity fields are used,
    excluding PK (``FieldModifier.PK``) and auto-managed fields
    (``FieldModifier.AUTO_ADD``, ``FieldModifier.AUTO_UPDATE``).

    FK fields — those with a ``ref_entity`` or whose name ends in ``_id``
    (UUID kind) — carry ``is_required=False`` in the triple even when marked
    ``required`` in the entity, because FK search-selects handle validation
    differently from plain inputs.

    Args:
        entity: An ``EntitySpec`` instance.
        surface: A ``SurfaceSpec`` instance.

    Returns:
        A list of ``SurfaceFieldTriple`` instances.
    """
    from dazzle.core.ir.fields import FieldModifier, FieldTypeKind

    entity_fields: dict[str, object] = {
        getattr(f, "name", ""): f for f in getattr(entity, "fields", [])
    }

    def _build_triple(field_spec: object, *, has_source: bool = False) -> SurfaceFieldTriple:
        fname = getattr(field_spec, "name", "")
        ftype = getattr(field_spec, "type", None)
        modifiers = getattr(field_spec, "modifiers", [])
        ref_entity = getattr(ftype, "ref_entity", None) if ftype is not None else None
        ftype_kind = getattr(ftype, "kind", None) if ftype is not None else None

        is_fk = ref_entity is not None or (
            ftype_kind == FieldTypeKind.UUID and fname != "id" and fname.endswith("_id")
        )
        # FK fields: is_required=False in the triple regardless of entity modifier
        raw_required = FieldModifier.REQUIRED in modifiers
        is_required = raw_required and not is_fk

        widget = resolve_widget(field_spec, has_source=has_source)  # type: ignore[arg-type]
        return SurfaceFieldTriple(
            field_name=fname,
            widget=widget,
            is_required=is_required,
            is_fk=is_fk,
            ref_entity=ref_entity,
        )

    _EXCLUDED_MODIFIERS = {FieldModifier.PK, FieldModifier.AUTO_ADD, FieldModifier.AUTO_UPDATE}

    # If surface has sections with elements, use those
    sections = getattr(surface, "sections", [])
    elements_found: list[tuple[object, bool]] = []  # (field_spec, has_source)
    for section in sections:
        for element in getattr(section, "elements", []):
            field_name = getattr(element, "field_name", "")
            options = getattr(element, "options", {}) or {}
            has_source = bool(options.get("source"))
            field_spec = entity_fields.get(field_name)
            if field_spec is not None:
                elements_found.append((field_spec, has_source))

    if elements_found:
        return [_build_triple(fs, has_source=hs) for fs, hs in elements_found]

    # Fallback: all entity fields excluding PK and auto-managed
    result: list[SurfaceFieldTriple] = []
    for field_spec in getattr(entity, "fields", []):
        modifiers = getattr(field_spec, "modifiers", [])
        if any(m in _EXCLUDED_MODIFIERS for m in modifiers):
            continue
        result.append(_build_triple(field_spec))
    return result


def derive_triples(
    entities: Sequence[object],
    surfaces: Sequence[object],
    personas: Sequence[object],
) -> list[VerifiableTriple]:
    """Derive the full set of verifiable triples for an app.

    A triple is emitted for each (entity, surface, persona) combination where:
    - The entity is not a framework-generated entity.
    - The surface is bound to the entity (``entity_ref`` matches).
    - The persona has at least one permitted action on that surface.

    Args:
        entities: All ``EntitySpec`` instances from the app.
        surfaces: All ``SurfaceSpec`` instances from the app.
        personas: All ``PersonaSpec`` instances from the app.

    Returns:
        A list of ``VerifiableTriple`` instances.
    """
    # Index surfaces by entity_ref for O(1) lookup
    surfaces_by_entity: dict[str, list[object]] = {}
    for surface in surfaces:
        entity_ref = getattr(surface, "entity_ref", None)
        if entity_ref:
            surfaces_by_entity.setdefault(entity_ref, []).append(surface)

    triples: list[VerifiableTriple] = []

    for entity in entities:
        entity_name: str = getattr(entity, "name", "")
        if entity_name in _FRAMEWORK_ENTITIES:
            continue

        entity_surfaces = surfaces_by_entity.get(entity_name, [])
        for surface in entity_surfaces:
            surface_name: str = getattr(surface, "name", "")
            surface_mode = getattr(surface, "mode", None)

            fields = _resolve_surface_fields(entity, surface)
            actions = resolve_surface_actions(entity, surface, surfaces, personas, entities)

            for persona in personas:
                persona_id: str = getattr(persona, "id", str(persona))
                # Filter actions to those visible to this persona
                persona_actions = [a.action for a in actions if persona_id in a.visible_to]
                if not persona_actions:
                    continue  # Persona has no permitted actions → skip

                triples.append(
                    VerifiableTriple(
                        entity=entity_name,
                        surface=surface_name,
                        persona=persona_id,
                        surface_mode=surface_mode,
                        actions=persona_actions,
                        fields=fields,
                    )
                )

    return triples
