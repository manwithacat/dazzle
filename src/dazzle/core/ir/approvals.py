"""
Approval types for DAZZLE IR.

First-class approval gates with quorum, escalation, and auto-rules.

DSL Syntax (v0.25.0):

    approval PurchaseApproval "Purchase Order Approval":
      entity: PurchaseOrder
      trigger: status -> pending_approval
      approver_role: finance_manager
      quorum: 1
      threshold: amount > 1000
      escalation:
        after: 48 hours
        to: finance_director
      auto_approve:
        when: amount <= 100
      outcomes:
        approved -> approved
        rejected -> rejected
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr


class ApprovalEscalationSpec(BaseModel):
    """Escalation configuration for an approval gate."""

    after_value: int = 0
    after_unit: str = "hours"
    to_role: str = ""

    model_config = ConfigDict(frozen=True)


class ApprovalOutcomeSpec(BaseModel):
    """Maps a decision to a target entity status."""

    decision: str = ""
    target_status: str = ""

    model_config = ConfigDict(frozen=True)


class ApprovalSpec(BaseModel):
    """
    An approval gate definition.

    Attributes:
        name: Approval identifier
        title: Human-readable title
        entity: Entity requiring approval
        trigger_field: Field that triggers approval (default: status)
        trigger_value: Value that triggers approval
        approver_role: Role authorized to approve
        quorum: Number of approvals required
        threshold: Condition that activates the approval requirement
        escalation: Escalation configuration
        auto_approve: Condition for automatic approval
        outcomes: Mapping of decisions to entity status transitions
    """

    name: str
    title: str | None = None
    entity: str = ""
    trigger_field: str = "status"
    trigger_value: str = ""
    approver_role: str = ""
    quorum: int = 1
    threshold: ConditionExpr | None = None
    escalation: ApprovalEscalationSpec | None = None
    auto_approve: ConditionExpr | None = None
    outcomes: list[ApprovalOutcomeSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
