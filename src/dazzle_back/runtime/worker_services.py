"""Build the minimal service set the standalone `dazzle worker` needs (#992).

The cycle-9 `dazzle worker` CLI runs in a separate process from
`dazzle serve`, so it can't share the FastAPI server's services
dict. Pre-fix, it passed ``services={}`` to the worker + retention
loops, which meant:

- `JobRun` status transitions logged but not persisted
- Retention sweep no-op'd (no `JobRun` / `AuditEntry` service to
  sweep against)

This module builds the minimal set the loops actually use:

- `JobRun` service — for the worker loop's status-write path and
  retention's row-count sweep
- `AuditEntry` service — for retention's per-entity-type sweep

The factory mirrors the relevant subset of `server.py`'s
`_setup_models`, `_setup_database`, `_setup_services`, but stays
detached from FastAPI's app lifecycle so the worker can own its
own pool open/close.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.converters.entity_converter import convert_entities
from dazzle_back.runtime.model_generator import generate_all_entity_models
from dazzle_back.runtime.pg_backend import PostgresBackend
from dazzle_back.runtime.repository import RepositoryFactory
from dazzle_back.runtime.service_generator import CRUDService

logger = logging.getLogger(__name__)


WORKER_SERVICE_ENTITIES = ("JobRun", "AuditEntry")
"""Platform entities the worker process needs services for.

Both are auto-injected by the linker (cycle 2 of #953 + #956)
when the DSL declares any `job:` or `audit on …` block.
"""


def build_worker_services(
    appspec: Any,
    database_url: str,
    *,
    pool_min: int = 1,
    pool_max: int = 4,
) -> tuple[dict[str, CRUDService[Any, Any, Any]], PostgresBackend]:
    """Build CRUD services for the platform entities the worker writes to.

    Returns a ``(services, db_manager)`` tuple. The caller owns the
    db_manager — call ``db_manager.close_pool()`` on shutdown.

    Pool defaults are smaller than the server's because the worker
    has only two concurrent loops (worker + retention) that touch
    the DB; ``pool_max=4`` leaves headroom without burning
    connections an idle worker process won't use.

    Returns an empty services dict when the AppSpec doesn't declare
    `JobRun` / `AuditEntry` (i.e. no `job:` or `audit on …` blocks
    in the DSL — the linker hasn't injected the entities). The
    worker will still run, but loops degrade to log-only behaviour.
    """
    entities = convert_entities(appspec.domain.entities)
    entity_specs = {e.name: e for e in entities}

    needed = [name for name in WORKER_SERVICE_ENTITIES if name in entity_specs]
    if not needed:
        logger.info(
            "No platform entities (%s) in AppSpec — worker loops will degrade to "
            "log-only persistence",
            ", ".join(WORKER_SERVICE_ENTITIES),
        )
        # Still return a live db_manager so the caller's shutdown path is uniform.
        db_manager = PostgresBackend(database_url)
        db_manager.open_pool(min_size=pool_min, max_size=pool_max)
        return {}, db_manager

    models = generate_all_entity_models(entities)

    db_manager = PostgresBackend(database_url)
    db_manager.open_pool(min_size=pool_min, max_size=pool_max)

    # Build repositories for every entity (the FK display-field
    # graph touches them all) but only expose CRUD services for the
    # platform set. Building all keeps RepositoryFactory's internal
    # consistency without constraining the worker to a partial view.
    repo_factory = RepositoryFactory(db_manager, models)
    repos = repo_factory.create_all_repositories(entities)

    services: dict[str, CRUDService[Any, Any, Any]] = {}
    for name in needed:
        model = models[name]
        spec = entity_specs[name]
        repo = repos.get(name)
        if repo is None:
            logger.warning("No repository created for %s — skipping", name)
            continue
        service: CRUDService[Any, Any, Any] = CRUDService(
            entity_name=name,
            model_class=model,
            create_schema=model,
            update_schema=model,
            state_machine=getattr(spec, "state_machine", None),
            entity_spec=spec,
        )
        service.set_repository(repo)
        services[name] = service

    logger.info("Built worker services: %s", sorted(services.keys()))
    return services, db_manager
