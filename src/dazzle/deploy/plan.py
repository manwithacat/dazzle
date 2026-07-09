"""Target-agnostic deployment planning.

Surfaces the AppSpec → infrastructure-requirements inference (the reusable core
of the retired AWS-CDK generator, ADR/issue #1568) as a deploy-target-neutral
plan: *what* a Dazzle app needs to run in production (a Postgres database, N
queues, object storage, a ledger cluster, …) and *which* environment variables
its host must provide — independent of how you provision it (buildpack/Heroku,
your own container, a managed platform).

The inference itself lives in :mod:`dazzle.core.infra_analyzer` (domain-driven,
no cloud assumptions); this module renders it for humans and machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.infra_analyzer import (
    analyze_infra_requirements,
    get_required_env_vars,
)

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

__all__ = ["InfraComponent", "InfraPlan", "build_infra_plan"]


@dataclass
class InfraComponent:
    """A single infrastructure component an app needs in production."""

    kind: str  # "database" | "cache" | "queue" | "workers" | "storage" | "ledger" | "webhooks"
    summary: str  # one-line human description
    detail: str | None = None  # optional extra detail (sizing hint, counts, …)
    required: bool = True  # required vs optional/managed-elsewhere

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "required": self.required,
        }


@dataclass
class InfraPlan:
    """A target-agnostic deployment plan for an app."""

    app_name: str
    components: list[InfraComponent] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_stateless(self) -> bool:
        """True when the app needs no backing infrastructure at all."""
        return not self.components

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app_name,
            "components": [c.to_dict() for c in self.components],
            "required_env_vars": self.required_env_vars,
            "notes": self.notes,
        }


def build_infra_plan(appspec: AppSpec) -> InfraPlan:
    """Infer a target-agnostic infrastructure plan from an AppSpec."""
    reqs = analyze_infra_requirements(appspec)
    components: list[InfraComponent] = []

    if reqs.needs_database:
        size = (
            "large" if reqs.entity_count > 20 else "medium" if reqs.entity_count > 10 else "small"
        )
        components.append(
            InfraComponent(
                kind="database",
                summary=f"{reqs.database_type.capitalize()} database",
                detail=f"{reqs.entity_count} entit{'y' if reqs.entity_count == 1 else 'ies'} "
                f"(~{size} footprint)",
            )
        )

    if reqs.needs_cache:
        components.append(
            InfraComponent(
                kind="cache",
                summary=f"{reqs.cache_type.capitalize()} cache",
                detail="sessions / caching",
                required=False,
            )
        )

    if reqs.needs_queue:
        components.append(
            InfraComponent(
                kind="queue",
                summary="Message queue",
                detail=f"queue backend: {reqs.queue_type}",
            )
        )

    if reqs.needs_workers:
        names = ", ".join(reqs.async_service_names or []) or "async services"
        components.append(
            InfraComponent(kind="workers", summary="Background worker process(es)", detail=names)
        )

    if reqs.needs_webhooks:
        names = ", ".join(reqs.webhook_service_names or []) or "webhook endpoints"
        components.append(
            InfraComponent(
                kind="webhooks",
                summary="Publicly reachable webhook endpoint(s)",
                detail=names,
                required=False,
            )
        )

    if reqs.needs_storage:
        components.append(
            InfraComponent(
                kind="storage",
                summary=f"Object storage ({reqs.storage_type})",
                detail="file uploads / assets",
            )
        )

    if reqs.needs_tigerbeetle:
        ledgers = (
            ", ".join(reqs.tigerbeetle_ledger_names or [])
            or f"{reqs.tigerbeetle_ledger_count} ledger(s)"
        )
        components.append(
            InfraComponent(
                kind="ledger",
                summary="TigerBeetle ledger cluster",
                detail=f"{ledgers} — a dedicated consensus cluster (odd node count) must be provisioned",
            )
        )

    notes: list[str] = []
    if components:
        notes.append(
            "Provision these yourself (managed services or your own containers) and pass "
            "the connection details via the environment variables below."
        )
        notes.append(
            "The Dazzle app runs as a single core process — deploy it with a buildpack "
            "(see `dazzle deploy heroku`) or any Python host; it does not require a Dockerfile."
        )
    else:
        notes.append("This app is stateless — no backing infrastructure required.")

    return InfraPlan(
        app_name=appspec.name,
        components=components,
        required_env_vars=get_required_env_vars(reqs),
        notes=notes,
    )
