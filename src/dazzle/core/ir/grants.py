"""
Grant schema specification types for DAZZLE IR.

Grant schemas define runtime-configurable delegation permissions
that layer over the existing Cedar-style static access rules.

DSL Syntax (v0.42.0):
    grant_schema department_delegation "Department Delegation":
      scope: Department
      relation acting_hod "Assign covering HoD":
        granted_by: role(senior_leadership)
        approval: required
        expiry: required
        max_duration: 90d
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .conditions import ConditionExpr
from .location import SourceLocation


class GrantApprovalMode(StrEnum):
    REQUIRED = "required"
    IMMEDIATE = "immediate"
    NONE = "none"


class GrantExpiryMode(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class GrantRelationSpec(BaseModel):
    name: str
    label: str
    description: str | None = None
    principal_label: str | None = None
    confirmation: str | None = None
    revoke_verb: str | None = None
    granted_by: ConditionExpr
    approved_by: ConditionExpr | None = None
    approval: GrantApprovalMode = GrantApprovalMode.REQUIRED
    expiry: GrantExpiryMode = GrantExpiryMode.REQUIRED
    max_duration: str | None = None
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class GrantSchemaSpec(BaseModel):
    name: str
    label: str
    description: str | None = None
    scope: str
    relations: list[GrantRelationSpec]
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
