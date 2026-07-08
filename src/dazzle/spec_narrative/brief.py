"""Build a fact-only SpecBrief from an AppSpec: facts + activated claims + skeleton."""

import hashlib

from dazzle.core import ir
from dazzle.spec_narrative.claims import load_claims
from dazzle.spec_narrative.detectors import REGISTRY
from dazzle.spec_narrative.english import predicate_to_english
from dazzle.spec_narrative.models import (
    ActivatedClaim,
    ActorItem,
    AutomationItem,
    CapabilityItem,
    DomainItem,
    JourneyItem,
    PlaceItem,
    RelationshipItem,
    ScopeRuleItem,
    SectionPlan,
    SecurityPosture,
    SpecBrief,
)

# Fixed document section order (the layered document, top → depth).
_SECTIONS = [
    "executive_summary",
    "what_it_does",
    "who_uses_it",
    "where_work_happens",
    "how_work_flows",
    "automation_and_controls",
    "technical_foundation",
    "compliance_posture",
]


def _user_entities(app: ir.AppSpec) -> list[ir.EntitySpec]:
    """Entities the user actually modelled.

    Excludes framework-injected platform plumbing (AIJob, FeedbackReport,
    SystemHealth, …), which ``admin_builder`` stamps ``domain == "platform"`` by
    construction (``_build_admin_entities``). These are infrastructure, not
    "things the system manages", and must never surface in a stakeholder-facing
    document. NB: ``cli/spec.py`` excludes the same set by *name*
    (``_FRAMEWORK_INJECTED_ENTITIES``); the ``domain`` attribute is the more
    robust signal and is preferred here.
    """
    return [e for e in app.domain.entities if e.domain != "platform"]


def _user_surfaces(app: ir.AppSpec) -> list[ir.SurfaceSpec]:
    """Surfaces the user actually modelled.

    Excludes framework-injected plumbing that would misrepresent the system if
    shown to a stakeholder, on two signals:
      * admin dashboard surfaces (``_admin_health``, ``_admin_metrics``, …),
        identified by the ``_admin_`` name prefix; and
      * surfaces that target a framework ``platform`` entity (e.g. the
        ``feedback_*`` surfaces over ``FeedbackReport``), which are not
        ``_admin_``-prefixed but are still framework features, not product ones.
    """
    platform_names = {e.name for e in app.domain.entities if e.domain == "platform"}
    return [
        s
        for s in app.surfaces
        if not s.name.startswith("_admin_") and s.entity_ref not in platform_names
    ]


def build_brief(app: ir.AppSpec) -> SpecBrief:
    """Extract verified facts and activate framework claims for ``app``."""
    entities = _user_entities(app)
    entity_titles = {e.name: e.title for e in entities}
    domain = [
        DomainItem(
            name=e.name,
            title=e.title,
            intent=e.intent,
            lifecycle_states=(e.state_machine.state_names() if e.state_machine else []),
            relationships=_relationships(e, entity_titles),
        )
        for e in entities
    ]
    actors = [
        ActorItem(
            id=p.id,
            label=p.label,
            description=p.description,
            goals=list(p.goals),
            workspaces=_actor_workspaces(app, p),
        )
        for p in app.personas
    ]
    capabilities = [
        CapabilityItem(name=s.name, title=s.title, entity=s.entity_ref, mode=s.mode.value)
        for s in _user_surfaces(app)
    ]
    scoped = [e.name for e in entities if e.access is not None and e.access.scopes]
    security = SecurityPosture(
        has_row_level_security=bool(scoped),
        scoped_entities=scoped,
        persona_count=len(app.personas),
        scope_rules=_scope_rules(entities),
    )
    activated = _activate_claims(app)
    journeys = _journeys(app)
    places = _places(app)
    automation = _automation(app)
    skeleton = _plan_skeleton(app, entities, activated, journeys, places, automation)
    return SpecBrief(
        app_name=app.name,
        app_title=app.title,
        domain=domain,
        actors=actors,
        capabilities=capabilities,
        journeys=journeys,
        places=places,
        automation=automation,
        security=security,
        activated_claims=activated,
        skeleton=skeleton,
    )


def _relationships(
    e: ir.EntitySpec, entity_titles: dict[str, str | None]
) -> list[RelationshipItem]:
    """Declared links to other user-modelled entities (ref / belongs_to / poly_ref)."""
    out: list[RelationshipItem] = []
    ref_kinds = (ir.FieldTypeKind.REF, ir.FieldTypeKind.BELONGS_TO)
    for f in e.fields:
        kind = f.type.kind
        targets: list[str] = []
        if kind in ref_kinds and f.type.ref_entity:
            targets = [f.type.ref_entity]
        elif kind == ir.FieldTypeKind.POLY_REF:
            targets = list(getattr(f.type, "poly_targets", None) or [])
        for target in targets:
            if target not in entity_titles:
                continue  # framework/platform target — not part of the story
            required = any(
                getattr(m, "value", None) == "required" or str(m) == "required"
                for m in (f.modifiers or [])
            )
            out.append(
                RelationshipItem(
                    field=f.name,
                    target=target,
                    target_title=entity_titles.get(target),
                    required=required,
                )
            )
    return out


def _actor_workspaces(app: ir.AppSpec, persona: ir.PersonaSpec) -> list[str]:
    """Workspaces this persona is EXPLICITLY granted or lands in by default.

    Conservative by design: a workspace with no access block is not attributed
    to anyone (the brief must not assert access the model doesn't declare).
    """
    names: list[str] = []
    for ws in _user_workspaces(app):
        allowed = ws.access is not None and persona.id in (ws.access.allow_personas or [])
        is_default = persona.default_workspace == ws.name
        if allowed or is_default:
            names.append(ws.title or ws.name)
    return names


def _user_workspaces(app: ir.AppSpec) -> list[ir.WorkspaceSpec]:
    """Workspaces the user actually modelled.

    Excludes framework-injected plumbing (``_platform_admin`` and friends) by
    the same ``_``-prefix rule ``_user_surfaces`` applies to admin surfaces.
    """
    return [ws for ws in app.workspaces if not ws.name.startswith("_")]


def _journeys(app: ir.AppSpec) -> list[JourneyItem]:
    """Authored stories, as structured journey facts (narrative source of truth)."""
    return [
        JourneyItem(
            id=s.story_id,
            title=s.title,
            actor=s.persona,
            description=s.description,
            when=[c.expression for c in s.when],
            outcomes=[c.expression for c in s.then],
        )
        for s in app.stories
    ]


def _places(app: ir.AppSpec) -> list[PlaceItem]:
    """Workspaces (dashboards) and experiences (guided flows) as named places."""
    out: list[PlaceItem] = []
    for ws in _user_workspaces(app):
        personas = list(ws.access.allow_personas) if ws.access else []
        contents = [
            f"{(r.display.value if hasattr(r.display, 'value') else r.display)} of {r.source}"
            for r in ws.regions
            if getattr(r, "source", None)
        ]
        out.append(
            PlaceItem(
                name=ws.name,
                title=ws.title,
                kind="workspace",
                purpose=ws.purpose,
                personas=personas,
                contents=contents,
            )
        )
    for exp in app.experiences:
        out.append(
            PlaceItem(
                name=exp.name,
                title=exp.title,
                kind="experience",
                purpose=None,
                personas=[],
                contents=[step.name for step in exp.steps],
            )
        )
    return out


def _automation(app: ir.AppSpec) -> list[AutomationItem]:
    """Processes, schedules, controls, AI assists, integrations, and ledgers."""
    return (
        _automation_workflows(app)
        + _automation_controls(app)
        + _automation_connections(app)
        + _automation_money(app)
    )


def _automation_workflows(app: ir.AppSpec) -> list[AutomationItem]:
    """Processes and schedules — work the system drives on its own."""
    out: list[AutomationItem] = []
    for p in app.processes:
        trigger = p.trigger
        detail = None
        if trigger is not None and trigger.entity_name:
            detail = f"runs when a {trigger.entity_name} changes"
        out.append(
            AutomationItem(
                kind="process", name=p.name, title=p.title, description=p.description, detail=detail
            )
        )
    for s in app.schedules:
        cadence = s.cron or (f"every {s.interval_seconds}s" if s.interval_seconds else None)
        out.append(
            AutomationItem(
                kind="schedule",
                name=s.name,
                title=s.title,
                description=s.description,
                detail=f"on a schedule ({cadence})" if cadence else "on a schedule",
            )
        )
    return out


def _automation_controls(app: ir.AppSpec) -> list[AutomationItem]:
    """Approvals and SLAs — declared constraints on how work happens."""
    out: list[AutomationItem] = []
    for a in app.approvals:
        detail = (
            f"changes on {a.entity} require {a.quorum} approval"
            f"{'' if a.quorum == 1 else 's'} from {a.approver_role}"
        )
        out.append(AutomationItem(kind="approval", name=a.name, title=a.title, detail=detail))
    for sla in app.slas:
        tiers = len(sla.tiers)
        out.append(
            AutomationItem(
                kind="sla",
                name=sla.name,
                title=sla.title,
                detail=f"response-time commitment on {sla.entity}"
                + (f" with {tiers} escalation tier{'' if tiers == 1 else 's'}" if tiers else ""),
            )
        )
    return out


def _automation_connections(app: ir.AppSpec) -> list[AutomationItem]:
    """AI-assisted steps and external-service integrations."""
    out: list[AutomationItem] = []
    for intent in app.llm_intents:
        out.append(
            AutomationItem(
                kind="llm_intent",
                name=intent.name,
                title=intent.title,
                description=intent.description,
                detail="AI-assisted",
            )
        )
    for integ in app.integrations:
        out.append(
            AutomationItem(
                kind="integration",
                name=integ.name,
                title=integ.title,
                detail="connects to an external service",
            )
        )
    return out


def _automation_money(app: ir.AppSpec) -> list[AutomationItem]:
    """Double-entry ledger accounts and balanced transactions."""
    out: list[AutomationItem] = []
    for ledger in app.ledgers:
        out.append(
            AutomationItem(
                kind="ledger",
                name=ledger.name,
                title=ledger.label,
                description=ledger.intent,
                detail=f"double-entry account in {ledger.currency}",
            )
        )
    for txn in app.transactions:
        out.append(
            AutomationItem(
                kind="transaction",
                name=txn.name,
                title=txn.label,
                description=txn.intent,
                detail="balanced money movement",
            )
        )
    return out


def _scope_rules(entities: list[ir.EntitySpec]) -> list[ScopeRuleItem]:
    """Every scope rule on a user entity, rendered as plain English."""
    out: list[ScopeRuleItem] = []
    for e in entities:
        if e.access is None:
            continue
        for rule in e.access.scopes:
            op = rule.operation.value if hasattr(rule.operation, "value") else str(rule.operation)
            out.append(
                ScopeRuleItem(
                    entity=e.name,
                    operation=op,
                    personas=list(rule.personas or []),
                    rule=predicate_to_english(rule.predicate),
                )
            )
    return out


def _activate_claims(app: ir.AppSpec) -> list[ActivatedClaim]:
    """Run each catalogue claim's detector; keep those that fire (catalogue order)."""
    out: list[ActivatedClaim] = []
    for c in load_claims():
        detector = REGISTRY.get(c.detector)
        if detector is None:
            # Gated for the bundled catalogue by the claim-integrity test, but a
            # caller can pass a custom claims.toml via load_claims(path=...) —
            # fail loud and specific rather than with a bare KeyError traceback.
            raise ValueError(
                f"Claim {c.id!r} references unknown detector {c.detector!r}. "
                f"Known detectors: {sorted(REGISTRY)}"
            )
        if detector(app):
            out.append(
                ActivatedClaim(
                    id=c.id, group=c.group, audience=c.audience, claim=c.claim, evidence=c.evidence
                )
            )
    return out


def _plan_skeleton(
    app: ir.AppSpec,
    entities: list[ir.EntitySpec],
    activated: list[ActivatedClaim],
    journeys: list[JourneyItem],
    places: list[PlaceItem],
    automation: list[AutomationItem],
) -> list[SectionPlan]:
    """Decide which document sections are populated and which claims belong where."""
    has_lifecycle = (
        any(e.state_machine is not None for e in entities) or bool(app.approvals) or bool(journeys)
    )
    compliance_ids = [c.id for c in activated if c.group == "compliance"]
    foundation_ids = [c.id for c in activated if c.group != "compliance"]
    populated = {
        "executive_summary": True,
        "what_it_does": bool(entities),
        "who_uses_it": bool(app.personas),
        "where_work_happens": bool(places),
        "how_work_flows": has_lifecycle,
        "automation_and_controls": bool(automation),
        "technical_foundation": bool(foundation_ids),
        "compliance_posture": bool(compliance_ids),
    }
    claim_map = {
        "technical_foundation": foundation_ids,
        "compliance_posture": compliance_ids,
    }
    return [
        SectionPlan(section=s, populated=populated[s], claim_ids=claim_map.get(s, []))
        for s in _SECTIONS
    ]


def brief_fingerprint(brief: SpecBrief) -> str:
    """Stable content hash of a brief — the freshness anchor for committed docs.

    A generated ``SPECIFICATION.md`` carries this as a footer comment
    (``<!-- dazzle-spec-brief: sha256:… -->``); the example-spec drift gate
    recomputes it from the live DSL and fails when the model changed but the
    document wasn't regenerated. Canonical JSON (sorted keys, no whitespace
    variance) so the hash is independent of serialization cosmetics.
    """
    canonical = brief.model_dump_json()
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
