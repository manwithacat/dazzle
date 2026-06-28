"""Pydantic IR for the spec brief — fact-only, no generated prose."""

from pydantic import BaseModel, Field


class DomainItem(BaseModel):
    """A thing the system manages, in human terms."""

    name: str
    title: str | None = None
    intent: str | None = None
    lifecycle_states: list[str] = Field(default_factory=list)


class ActorItem(BaseModel):
    """A persona who uses the system."""

    id: str
    label: str
    description: str | None = None


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
    security: SecurityPosture
    activated_claims: list[ActivatedClaim] = Field(default_factory=list)
    skeleton: list[SectionPlan] = Field(default_factory=list)
