"""Boolean predicates over an AppSpec that gate framework value-claims.

A claim in ``claims.toml`` names one of these via its ``detector`` field; the
claim only enters the brief when the predicate returns True for the app.

Detector discipline: a detector must only return True for a property the app
*genuinely* exercises. The whole feature's integrity rests on this — a claim is
shown to investors as fact, so a detector that fires loosely produces a lie.
In particular, "scope rules are declared" (app-layer filtering) is a strictly
weaker property than "Postgres row-level security is enforced" (requires
``shared_schema`` tenancy); they are deliberately split (``has_rls`` vs
``has_database_rls``).
"""

from collections.abc import Callable

from dazzle.core import ir
from dazzle.core.ir.governance import TenancyMode


def has_rls(app: ir.AppSpec) -> bool:
    """True if any entity declares row-filtering scope rules (app-layer or DB)."""
    return any(e.access is not None and bool(e.access.scopes) for e in app.domain.entities)


def has_database_rls(app: ir.AppSpec) -> bool:
    """True only when scope/tenant rules compile to *Postgres* RLS policies.

    RLS DDL is generated solely for ``shared_schema`` tenancy
    (see ``dazzle.http.runtime.rls_schema.build_all_rls_ddl``). Without it,
    scope rules are enforced by application-layer query filtering, not by the
    database — so the "even if the app has a bug" guarantee does not hold.
    """
    return app.tenancy is not None and app.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA


def has_provable_rbac(app: ir.AppSpec) -> bool:
    """True if personas are declared and at least one entity carries access rules."""
    if not app.personas:
        return False
    return any(
        e.access is not None and (bool(e.access.permissions) or bool(e.access.scopes))
        for e in app.domain.entities
    )


def is_multi_tenant(app: ir.AppSpec) -> bool:
    """True if the app declares genuine multi-tenant isolation.

    A ``tenancy:`` block with ``mode = single`` is *not* multi-tenant, so the
    bare ``app.tenancy is not None`` check would over-claim.
    """
    return app.tenancy is not None and app.tenancy.isolation.mode != TenancyMode.SINGLE


def has_events(app: ir.AppSpec) -> bool:
    """True if the app declares HLESS streams or an event model."""
    return bool(app.streams) or app.event_model is not None


def has_compliance_evidence(app: ir.AppSpec) -> bool:
    """True if the app declares data classifications (compliance evidence source)."""
    return app.policies is not None and bool(app.policies.classifications)


def has_ledger(app: ir.AppSpec) -> bool:
    """True if the app declares double-entry ledger accounts."""
    return bool(app.ledgers)


def has_background_work(app: ir.AppSpec) -> bool:
    """True if the app declares processes or schedules (durable background work)."""
    return bool(app.processes) or bool(app.schedules)


def has_approvals(app: ir.AppSpec) -> bool:
    """True if the app declares approval rules (explicit sign-off controls)."""
    return bool(app.approvals)


def has_slas(app: ir.AppSpec) -> bool:
    """True if the app declares SLA commitments."""
    return bool(app.slas)


def has_ai_assist(app: ir.AppSpec) -> bool:
    """True if the app declares LLM intents (governed, model-declared AI steps)."""
    return bool(app.llm_intents)


def always(_app: ir.AppSpec) -> bool:
    """For framework constants true of every Dazzle app (Postgres, SSR)."""
    return True


REGISTRY: dict[str, Callable[[ir.AppSpec], bool]] = {
    "has_rls": has_rls,
    "has_database_rls": has_database_rls,
    "has_provable_rbac": has_provable_rbac,
    "is_multi_tenant": is_multi_tenant,
    "has_events": has_events,
    "has_compliance_evidence": has_compliance_evidence,
    "has_ledger": has_ledger,
    "has_background_work": has_background_work,
    "has_approvals": has_approvals,
    "has_slas": has_slas,
    "has_ai_assist": has_ai_assist,
    "always": always,
}
