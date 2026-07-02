"""Pydantic IR for the spec brief — fact-only, no generated prose."""

from pydantic import BaseModel, Field


class RelationshipItem(BaseModel):
    """A declared link from one domain item to another, in human terms."""

    field: str
    target: str
    target_title: str | None = None
    required: bool = False


class DomainItem(BaseModel):
    """A thing the system manages, in human terms."""

    name: str
    title: str | None = None
    intent: str | None = None
    lifecycle_states: list[str] = Field(default_factory=list)
    relationships: list[RelationshipItem] = Field(default_factory=list)


class ActorItem(BaseModel):
    """A persona who uses the system."""

    id: str
    label: str
    description: str | None = None
    goals: list[str] = Field(default_factory=list)
    # Workspaces this persona is EXPLICITLY granted (allow_personas) or lands in
    # by default — never inferred from an absent access block.
    workspaces: list[str] = Field(default_factory=list)


class JourneyItem(BaseModel):
    """An authored user story — persona, intent, and expected outcomes."""

    id: str
    title: str
    actor: str
    description: str | None = None
    when: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)


class PlaceItem(BaseModel):
    """A named place work happens: a workspace (dashboard) or experience (flow)."""

    name: str
    title: str | None = None
    kind: str  # "workspace" | "experience"
    purpose: str | None = None
    personas: list[str] = Field(default_factory=list)
    contents: list[str] = Field(default_factory=list)


class AutomationItem(BaseModel):
    """Something the system does without a human driving each step, or a
    declared control (approval / SLA / ledger) that constrains how work happens."""

    kind: (
        str  # process | schedule | approval | sla | llm_intent | integration | ledger | transaction
    )
    name: str
    title: str | None = None
    description: str | None = None
    detail: str | None = None


class ScopeRuleItem(BaseModel):
    """One row-visibility rule, rendered in plain English."""

    entity: str
    operation: str
    personas: list[str] = Field(default_factory=list)
    rule: str


class CapabilityItem(BaseModel):
    """A surface — something an actor can do."""

    name: str
    title: str | None = None
    entity: str | None = None
    mode: str


class SecurityPosture(BaseModel):
    """The access model, summarised."""

    has_row_level_security: bool
    scoped_entities: list[str] = Field(default_factory=list)
    persona_count: int
    scope_rules: list[ScopeRuleItem] = Field(default_factory=list)


class ActivatedClaim(BaseModel):
    """A framework value-claim whose detector fired for this app."""

    id: str
    group: str
    audience: str
    claim: str
    evidence: str


class SectionPlan(BaseModel):
    """Which document section is populated, and which claims belong in it."""

    section: str
    populated: bool
    claim_ids: list[str] = Field(default_factory=list)


class SpecBrief(BaseModel):
    """The deterministic contract handed to the narrative stage."""

    app_name: str
    app_title: str | None = None
    domain: list[DomainItem] = Field(default_factory=list)
    actors: list[ActorItem] = Field(default_factory=list)
    capabilities: list[CapabilityItem] = Field(default_factory=list)
    journeys: list[JourneyItem] = Field(default_factory=list)
    places: list[PlaceItem] = Field(default_factory=list)
    automation: list[AutomationItem] = Field(default_factory=list)
    security: SecurityPosture
    activated_claims: list[ActivatedClaim] = Field(default_factory=list)
    skeleton: list[SectionPlan] = Field(default_factory=list)
