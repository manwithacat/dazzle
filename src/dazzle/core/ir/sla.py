"""
SLA types for DAZZLE IR.

Service Level Agreement definitions with deadline tiers, business hours,
and breach actions.

DSL Syntax (v0.25.0):

    sla TicketResponse "Ticket Response SLA":
      entity: SupportTicket
      starts_when: status -> open
      pauses_when: status = on_hold
      completes_when: status -> resolved
      tiers:
        warning: 4 hours
        breach: 8 hours
        critical: 24 hours
      business_hours:
        schedule: "Mon-Fri 09:00-17:00"
        timezone: "Europe/London"
      on_breach:
        notify: support_lead
        set: escalated = true
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .process import FieldAssignment


class SLATierSpec(BaseModel):
    """A single SLA tier with name and duration."""

    name: str = ""
    duration_value: int = 0
    duration_unit: str = "hours"

    model_config = ConfigDict(frozen=True)


class BusinessHoursSpec(BaseModel):
    """Business hours schedule for SLA calculation."""

    schedule: str = ""
    timezone: str = "UTC"

    model_config = ConfigDict(frozen=True)


class SLABreachActionSpec(BaseModel):
    """Actions taken when an SLA tier is breached."""

    notify_role: str | None = None
    field_assignments: list[FieldAssignment] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class SLAConditionSpec(BaseModel):
    """Condition that starts, pauses, or completes SLA tracking."""

    field: str = "status"
    operator: str = "->"
    value: str = ""

    model_config = ConfigDict(frozen=True)


class SLASpec(BaseModel):
    """
    An SLA definition.

    Attributes:
        name: SLA identifier
        title: Human-readable title
        entity: Entity being tracked
        starts_when: Condition that starts the SLA clock
        pauses_when: Condition that pauses the SLA clock
        completes_when: Condition that completes (stops) the SLA clock
        tiers: Escalation tiers with durations
        business_hours: Business hours configuration
        on_breach: Actions to take when SLA is breached
    """

    name: str
    title: str | None = None
    entity: str = ""
    starts_when: SLAConditionSpec | None = None
    pauses_when: SLAConditionSpec | None = None
    completes_when: SLAConditionSpec | None = None
    tiers: list[SLATierSpec] = Field(default_factory=list)
    business_hours: BusinessHoursSpec | None = None
    on_breach: SLABreachActionSpec | None = None

    model_config = ConfigDict(frozen=True)
