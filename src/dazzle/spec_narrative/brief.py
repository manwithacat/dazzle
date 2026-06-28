"""Build a fact-only SpecBrief from an AppSpec: facts + activated claims + skeleton."""

from dazzle.core import ir
from dazzle.spec_narrative.claims import load_claims
from dazzle.spec_narrative.detectors import REGISTRY
from dazzle.spec_narrative.models import (
    ActivatedClaim,
    ActorItem,
    CapabilityItem,
    DomainItem,
    SectionPlan,
    SecurityPosture,
    SpecBrief,
)

# Fixed document section order (the layered document, top → depth).
_SECTIONS = [
    "executive_summary",
    "what_it_does",
    "who_uses_it",
    "how_work_flows",
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
    domain = [
        DomainItem(
            name=e.name,
            title=e.title,
            intent=e.intent,
            lifecycle_states=(e.state_machine.state_names() if e.state_machine else []),
        )
        for e in entities
    ]
    actors = [ActorItem(id=p.id, label=p.label, description=p.description) for p in app.personas]
    capabilities = [
        CapabilityItem(name=s.name, title=s.title, entity=s.entity_ref, mode=s.mode.value)
        for s in _user_surfaces(app)
    ]
    scoped = [e.name for e in entities if e.access is not None and e.access.scopes]
    security = SecurityPosture(
        has_row_level_security=bool(scoped),
        scoped_entities=scoped,
        persona_count=len(app.personas),
    )
    activated = _activate_claims(app)
    skeleton = _plan_skeleton(app, entities, activated)
    return SpecBrief(
        app_name=app.name,
        app_title=app.title,
        domain=domain,
        actors=actors,
        capabilities=capabilities,
        security=security,
        activated_claims=activated,
        skeleton=skeleton,
    )


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
    app: ir.AppSpec, entities: list[ir.EntitySpec], activated: list[ActivatedClaim]
) -> list[SectionPlan]:
    """Decide which document sections are populated and which claims belong where."""
    has_lifecycle = any(e.state_machine is not None for e in entities) or bool(app.approvals)
    compliance_ids = [c.id for c in activated if c.group == "compliance"]
    foundation_ids = [c.id for c in activated if c.group != "compliance"]
    populated = {
        "executive_summary": True,
        "what_it_does": bool(entities),
        "who_uses_it": bool(app.personas),
        "how_work_flows": has_lifecycle,
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
