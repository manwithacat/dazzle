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
    """Contract asserting that a workspace renders (or 403s) for a given persona.

    Mirrors the ``RBACContract`` shape: one contract per (workspace, persona) pair
    with ``expected_present`` indicating whether that persona should be allowed.
    The generator derives ``expected_present`` from
    ``workspace_allowed_personas`` — the single source of truth for workspace
    visibility (see #835 / ``src/dazzle_ui/converters/workspace_converter.py``).
    """

    workspace: str = ""
    regions: list[str] = field(default_factory=list)
    fold_count: int = 0
    persona: str = ""
    expected_present: bool = True

    def __post_init__(self) -> None:
        self.kind = ContractKind.WORKSPACE

    def _id_key(self) -> str:
        return (
            f"workspace:{self.workspace}:{self.persona}:present={self.expected_present}"
            f":{','.join(sorted(self.regions))}:folds={self.fold_count}"
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


def generate_contracts(appspec: AppSpec) -> list[Contract]:
    """Generate the full set of UX contracts from an AppSpec.

    Reads from ``appspec.triples`` (the pre-computed VerifiableTriple list)
    and maps each triple to the appropriate Contract subclass.  RBAC contracts
    are derived from the permission helpers in ``dazzle.core.ir.triples``.
    Workspace contracts are generated directly from the appspec (workspaces
    don't participate in the triple model).
    """
    from dazzle.core.ir.domain import PermissionKind
    from dazzle.core.ir.triples import get_permitted_personas

    contracts: list[Contract] = []

    # Track which entities have already emitted each CRUD contract kind
    # to avoid duplicates when multiple surfaces exist for the same entity.
    seen_list: set[tuple[str, str]] = set()  # (entity, surface)
    seen_create: set[str] = set()
    seen_edit: set[str] = set()
    seen_detail: set[str] = set()
    seen_rbac_entities: set[str] = set()

    for triple in appspec.triples:
        entity_name = triple.entity
        surface_name = triple.surface
        mode = (
            str(triple.surface_mode.value)
            if hasattr(triple.surface_mode, "value")
            else str(triple.surface_mode)
        )

        # Derive field lists from the triple's field metadata
        all_fields = [f.field_name for f in triple.fields]
        required_fields = [f.field_name for f in triple.fields if f.is_required and not f.is_fk]
        editable_fields = [f.field_name for f in triple.fields if not f.is_fk]

        # ListPageContract — one per (entity, surface) with list mode
        if mode == "list":
            key = (entity_name, surface_name)
            if key not in seen_list:
                seen_list.add(key)
                contracts.append(
                    ListPageContract(
                        entity=entity_name,
                        surface=surface_name,
                        fields=all_fields,
                    )
                )

        # CreateFormContract — one per entity with a create surface
        if mode == "create" and entity_name not in seen_create:
            seen_create.add(entity_name)
            contracts.append(
                CreateFormContract(
                    entity=entity_name,
                    required_fields=required_fields,
                    all_fields=all_fields,
                )
            )

        # EditFormContract — one per entity with an edit surface
        if mode == "edit" and entity_name not in seen_edit:
            seen_edit.add(entity_name)
            contracts.append(
                EditFormContract(
                    entity=entity_name,
                    editable_fields=editable_fields,
                )
            )

        # DetailViewContract — one per entity with a view surface
        if mode == "view" and entity_name not in seen_detail:
            seen_detail.add(entity_name)

            # Look up entity for state machine transitions
            entity_spec = appspec.get_entity(entity_name)
            transitions: list[str] = []
            if entity_spec and entity_spec.state_machine:
                for t in entity_spec.state_machine.transitions:
                    from_s = t.from_state if isinstance(t.from_state, str) else t.from_state.name
                    to_s = t.to_state if isinstance(t.to_state, str) else t.to_state.name
                    transitions.append(f"{from_s}\u2192{to_s}")

            has_edit = bool(
                get_permitted_personas(
                    appspec.domain.entities, appspec.personas, entity_name, PermissionKind.UPDATE
                )
            )
            has_delete = bool(
                get_permitted_personas(
                    appspec.domain.entities, appspec.personas, entity_name, PermissionKind.DELETE
                )
            )

            contracts.append(
                DetailViewContract(
                    entity=entity_name,
                    fields=all_fields,
                    has_edit=has_edit,
                    has_delete=has_delete,
                    transitions=transitions,
                )
            )

        # RBACContract — one per entity × persona × operation (emitted once per entity)
        if entity_name not in seen_rbac_entities:
            seen_rbac_entities.add(entity_name)
            all_persona_ids = [p.id for p in appspec.personas]
            for operation in (
                PermissionKind.LIST,
                PermissionKind.CREATE,
                PermissionKind.UPDATE,
                PermissionKind.DELETE,
            ):
                permitted = set(
                    get_permitted_personas(
                        appspec.domain.entities, appspec.personas, entity_name, operation
                    )
                )
                for pid in all_persona_ids:
                    contracts.append(
                        RBACContract(
                            entity=entity_name,
                            persona=pid,
                            operation=str(operation),
                            expected_present=pid in permitted,
                        )
                    )

    # WorkspaceContracts — one per (workspace, persona) pair. expected_present
    # comes from workspace_allowed_personas(). When the helper returns None
    # ("no filter"), every persona is expected to access the workspace.
    # See #835 — prior to this pattern the generator emitted one contract
    # per workspace with no persona field, which falsely flagged
    # persona-scoped workspaces as framework bugs whenever the admin driver
    # was redirected to 403.
    from dazzle_ui.converters.workspace_converter import workspace_allowed_personas

    all_persona_ids = [p.id for p in appspec.personas]
    for workspace in appspec.workspaces:
        region_names = [r.name for r in getattr(workspace, "regions", [])]
        allowed = workspace_allowed_personas(workspace, list(appspec.personas))
        allowed_set = set(all_persona_ids) if allowed is None else set(allowed)
        for pid in all_persona_ids:
            contracts.append(
                WorkspaceContract(
                    workspace=workspace.name,
                    regions=region_names,
                    fold_count=0,
                    persona=pid,
                    expected_present=pid in allowed_set,
                )
            )

    return contracts
