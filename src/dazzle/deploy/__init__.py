"""
Dazzle Deploy — target-agnostic deployment planning + buildpack deploy files.

Dazzle apps run as a single core process that deploys cleanly to buildpack
platforms (Heroku and similar); containerisation, if you want it, is your own
concern. This package provides:

- `build_infra_plan(appspec)` — infer, target-neutrally, what infrastructure an
  app needs (database, queues, storage, ledger cluster, …) and which environment
  variables its host must supply. Surfaced as `dazzle deploy plan`.
- Heroku/uv-buildpack file generation (`dazzle deploy heroku`).

The AWS-CDK code generator that used to live here (ECS Fargate + ECR, i.e.
container-first) was retired in v0.101.0 — it contradicted the framework's
core-process/buildpack direction. See issue #1568 for the rationale and the
salvaged patterns; a no-local-Docker managed-AWS target is tracked separately.

Usage:
    dazzle deploy plan        # Target-agnostic infrastructure plan
    dazzle deploy heroku      # Generate Heroku/uv-buildpack deploy files
"""

from .plan import InfraComponent, InfraPlan, build_infra_plan

__all__ = [
    "InfraPlan",
    "InfraComponent",
    "build_infra_plan",
]
