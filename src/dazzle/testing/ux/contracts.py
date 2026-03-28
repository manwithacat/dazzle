"""Contract data models for UX DOM verification.

Each contract represents an assertion about a specific page or interaction
that can be verified against a live Dazzle app.  Contracts are value objects:
identical inputs must produce identical contract_ids so that runs can be
compared across deploys.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.domain import PermissionKind


class ContractKind(StrEnum):
    LIST_PAGE = "list_page"
    CREATE_FORM = "create_form"
    EDIT_FORM = "edit_form"
    DETAIL_VIEW = "detail_view"
    WORKSPACE = "workspace"
    ROUND_TRIP = "round_trip"
    RBAC = "rbac"


@dataclass
class Contract:
    """Abstract base for all UX contracts."""

    kind: ContractKind = field(init=False)
    status: Literal["pending", "passed", "failed"] = "pending"
    error: str | None = None

    # ------------------------------------------------------------------
    # Subclasses must override _id_key() to include their identifying fields
    # ------------------------------------------------------------------

    def _id_key(self) -> str:  # pragma: no cover
        return str(self.kind)

    @property
    def contract_id(self) -> str:
        """12-character hex digest derived from the contract's identity key."""
        return hashlib.sha256(self._id_key().encode()).hexdigest()[:12]

    @property
    def url_path(self) -> str:  # pragma: no cover
        raise NotImplementedError


@dataclass
class ListPageContract(Contract):
    """Contract asserting that a list page renders with the expected fields."""

    entity: str = ""
    surface: str = ""
    fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ContractKind.LIST_PAGE

    def _id_key(self) -> str:
        return f"list_page:{self.entity}:{self.surface}:{','.join(sorted(self.fields))}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}"


@dataclass
class CreateFormContract(Contract):
    """Contract asserting that a create form renders with the expected fields."""

    entity: str = ""
    required_fields: list[str] = field(default_factory=list)
    all_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ContractKind.CREATE_FORM

    def _id_key(self) -> str:
        return (
            f"create_form:{self.entity}"
            f":{','.join(sorted(self.required_fields))}"
            f":{','.join(sorted(self.all_fields))}"
        )

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/create"


@dataclass
class EditFormContract(Contract):
    """Contract asserting that an edit form renders with the expected fields."""

    entity: str = ""
    editable_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ContractKind.EDIT_FORM

    def _id_key(self) -> str:
        return f"edit_form:{self.entity}:{','.join(sorted(self.editable_fields))}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/{{id}}/edit"


@dataclass
class DetailViewContract(Contract):
    """Contract asserting that a detail view renders with the expected fields."""

    entity: str = ""
    fields: list[str] = field(default_factory=list)
    has_edit: bool = False
    has_delete: bool = False
    transitions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ContractKind.DETAIL_VIEW

    def _id_key(self) -> str:
        return (
            f"detail_view:{self.entity}"
            f":{','.join(sorted(self.fields))}"
            f":edit={self.has_edit}:delete={self.has_delete}"
            f":{','.join(sorted(self.transitions))}"
        )

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/{{id}}"


@dataclass
class WorkspaceContract(Contract):
    """Contract asserting that a workspace renders with the expected regions."""

    workspace: str = ""
    regions: list[str] = field(default_factory=list)
    fold_count: int = 0

    def __post_init__(self) -> None:
        self.kind = ContractKind.WORKSPACE

    def _id_key(self) -> str:
        return (
            f"workspace:{self.workspace}:{','.join(sorted(self.regions))}:folds={self.fold_count}"
        )

    @property
    def url_path(self) -> str:
        return f"/app/workspaces/{self.workspace}"


@dataclass
class RoundTripContract(Contract):
    """Contract asserting that an HTMX round-trip returns the expected DOM."""

    url: str = ""
    hx_target: str = ""
    method: str = "GET"
    expected_elements: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = ContractKind.ROUND_TRIP

    def _id_key(self) -> str:
        return (
            f"round_trip:{self.url}:{self.hx_target}:{self.method}"
            f":{','.join(sorted(self.expected_elements))}"
        )

    @property
    def url_path(self) -> str:
        return self.url


@dataclass
class RBACContract(Contract):
    """Contract asserting that a persona can or cannot perform an operation."""

    entity: str = ""
    persona: str = ""
    operation: str = ""
    expected_present: bool = True

    def __post_init__(self) -> None:
        self.kind = ContractKind.RBAC

    def _id_key(self) -> str:
        return f"rbac:{self.entity}:{self.persona}:{self.operation}:{self.expected_present}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}"


# ---------------------------------------------------------------------------
# Framework entities to exclude from user-facing contracts
# ---------------------------------------------------------------------------

_FRAMEWORK_ENTITIES: frozenset[str] = frozenset(
    {"AIJob", "FeedbackReport", "SystemHealth", "SystemMetric", "DeployHistory"}
)


def _condition_matches_role(condition: object, role: str) -> bool:
    """Return True if a ConditionExpr contains a role_check matching *role*."""
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
    """Return True if condition is exclusively role_check nodes (no field comparisons)."""
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

    Personas whose ID matches a role name in the condition are treated as
    having that role for the purpose of static contract generation.
    """
    personas = getattr(rule, "personas", [])
    condition = getattr(rule, "condition", None)
    if not personas:
        if _condition_is_pure_role_only(condition):
            return _condition_matches_role(condition, persona_id)
        return True  # No restriction — open to all authenticated
    if persona_id in personas:
        return True
    if _condition_matches_role(condition, persona_id):
        return True
    return False


def _get_permitted_personas(
    appspec: AppSpec, entity_name: str, operation: PermissionKind
) -> list[str]:
    """Return persona IDs that have a permit rule for the given operation."""
    entity = next((e for e in appspec.domain.entities if e.name == entity_name), None)
    if not entity or not entity.access:
        return [p.id for p in appspec.personas]
    permitted: set[str] = set()
    for rule in entity.access.permissions:
        if rule.operation == operation:
            if rule.personas:
                permitted.update(rule.personas)
            else:
                # Check if condition is a pure role gate
                condition = getattr(rule, "condition", None)
                if _condition_is_pure_role_only(condition):
                    # Only personas whose ID matches a role in the condition
                    for p in appspec.personas:
                        if _condition_matches_role(condition, p.id):
                            permitted.add(p.id)
                else:
                    return [p.id for p in appspec.personas]
    return list(permitted)


def generate_contracts(appspec: AppSpec) -> list[Contract]:
    """Generate the full set of UX contracts from an AppSpec."""
    from dazzle.core.ir.domain import PermissionKind

    contracts: list[Contract] = []

    # Map entity names → their surfaces (skip framework entities)
    entity_surfaces: dict[str, list] = {}
    for surface in appspec.surfaces:
        if surface.entity_ref and surface.entity_ref not in _FRAMEWORK_ENTITIES:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface)

    for entity in appspec.domain.entities:
        if entity.name in _FRAMEWORK_ENTITIES:
            continue
        surfaces = entity_surfaces.get(entity.name, [])
        if not surfaces:
            continue

        # Collect non-auto, non-id field info
        all_fields: list[str] = []
        required_fields: list[str] = []
        editable_fields: list[str] = []
        for f in entity.fields:
            if f.name == "id":
                continue
            modifiers = [str(m) for m in (f.modifiers or [])]
            if "auto_add" in modifiers or "auto_update" in modifiers:
                continue
            # FK reference fields render as search-selects, not plain inputs.
            # Detect by ref_entity attribute OR _id suffix convention.
            ref_entity = getattr(f.type, "ref_entity", None)
            is_fk = ref_entity is not None or (f.name.endswith("_id") and f.name != "id")
            all_fields.append(f.name)
            if "required" in modifiers and not is_fk:
                required_fields.append(f.name)
            if not is_fk:
                editable_fields.append(f.name)

        # ListPageContract — one per list-mode surface
        for surface_spec in surfaces:
            mode = (
                str(surface_spec.mode.value)
                if hasattr(surface_spec.mode, "value")
                else str(surface_spec.mode)
            )
            if mode == "list":
                # Collect field names from sections
                section_fields: list[str] = []
                for section in getattr(surface_spec, "sections", []):
                    for elem in getattr(section, "elements", []):
                        fname = getattr(elem, "field_name", None) or getattr(elem, "name", None)
                        if fname:
                            section_fields.append(fname)
                contracts.append(
                    ListPageContract(
                        entity=entity.name,
                        surface=surface_spec.name,
                        fields=section_fields if section_fields else all_fields,
                    )
                )

        # Determine which surface modes exist for this entity
        surface_modes = {
            str(s.mode.value) if hasattr(s.mode, "value") else str(s.mode) for s in surfaces
        }

        # CreateFormContract — only if entity has a create surface
        if "create" in surface_modes:
            contracts.append(
                CreateFormContract(
                    entity=entity.name,
                    required_fields=required_fields,
                    all_fields=all_fields,
                )
            )

        # EditFormContract — only if entity has an edit surface
        if "edit" in surface_modes:
            contracts.append(
                EditFormContract(
                    entity=entity.name,
                    editable_fields=editable_fields,
                )
            )

        # DetailViewContract — only if entity has a view surface
        if "view" in surface_modes:
            transitions: list[str] = []
            if entity.state_machine:
                for t in entity.state_machine.transitions:
                    from_s = t.from_state if isinstance(t.from_state, str) else t.from_state.name
                    to_s = t.to_state if isinstance(t.to_state, str) else t.to_state.name
                    transitions.append(f"{from_s}\u2192{to_s}")

            has_edit = bool(_get_permitted_personas(appspec, entity.name, PermissionKind.UPDATE))
            has_delete = bool(_get_permitted_personas(appspec, entity.name, PermissionKind.DELETE))

            contracts.append(
                DetailViewContract(
                    entity=entity.name,
                    fields=all_fields,
                    has_edit=has_edit,
                    has_delete=has_delete,
                    transitions=transitions,
                )
            )

        # RBACContract — one per entity × persona × operation
        all_personas = [p.id for p in appspec.personas]
        for operation in (
            PermissionKind.LIST,
            PermissionKind.CREATE,
            PermissionKind.UPDATE,
            PermissionKind.DELETE,
        ):
            permitted = set(_get_permitted_personas(appspec, entity.name, operation))
            for pid in all_personas:
                contracts.append(
                    RBACContract(
                        entity=entity.name,
                        persona=pid,
                        operation=str(operation),
                        expected_present=pid in permitted,
                    )
                )

    # WorkspaceContracts
    for workspace in appspec.workspaces:
        region_names = [r.name for r in getattr(workspace, "regions", [])]
        contracts.append(
            WorkspaceContract(
                workspace=workspace.name,
                regions=region_names,
                fold_count=0,
            )
        )

    return contracts
