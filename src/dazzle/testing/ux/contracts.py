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
from typing import Literal


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
