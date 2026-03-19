"""
Deploy Routes for Founder Console.

Wraps deploy.runner, deploy.preflight, deploy.config for the console UI.
Includes preflight, generate, deploy actions and rollback.
"""

import logging
from dataclasses import dataclass
from functools import partial
from typing import Any

from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    APIRouter,
    HTMLResponse,
    Request,
)

logger = logging.getLogger("dazzle.deploy_routes")


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _DeployDeps:
    deploy_history_store: Any | None
    spec_version_store: Any | None
    rollback_manager: Any | None
    appspec: Any | None
    project_dir: Any | None
    get_current_user: Any


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _run_preflight(deps: _DeployDeps, request: Request) -> dict[str, Any]:
    """Run deployment preflight checks."""
    result: dict[str, Any] = {"status": "ok", "checks": [], "can_proceed": True}

    try:
        from pathlib import Path

        from dazzle.deploy.preflight import PreflightConfig, PreflightMode, PreflightRunner

        proj = deps.project_dir or Path(".")
        infra_dir = proj / "infra"

        if not infra_dir.exists():
            return {
                "status": "warning",
                "checks": [
                    {
                        "name": "Infrastructure",
                        "severity": "info",
                        "message": "No infra directory found. Run 'Generate' first.",
                    }
                ],
                "can_proceed": False,
            }

        config = PreflightConfig(mode=PreflightMode.STATIC_ONLY)
        runner = PreflightRunner(
            project_root=proj,
            infra_dir=infra_dir,
            config=config,
        )
        report = runner.run()

        checks = []
        for stage in report.stages:
            for finding in stage.findings:
                checks.append(
                    {
                        "name": finding.code,
                        "severity": finding.severity.value,
                        "message": finding.message,
                        "remediation": finding.remediation,
                    }
                )

        can_proceed = report.summary.can_proceed if report.summary else True
        result = {
            "status": "passed" if can_proceed else "blocked",
            "checks": checks,
            "can_proceed": can_proceed,
        }

        # Record in history
        if deps.deploy_history_store:
            from dazzle_back.runtime.deploy_history import DeployStatus

            deploy = deps.deploy_history_store.create_deployment(
                environment="default",
                initiated_by="console",
            )
            deps.deploy_history_store.update_status(
                deploy.id,
                DeployStatus.PREFLIGHT,
                preflight_result=result,
            )

    except ImportError:
        result = {
            "status": "error",
            "checks": [
                {
                    "name": "Deploy Module",
                    "severity": "high",
                    "message": "Deploy module not available",
                }
            ],
            "can_proceed": False,
        }
    except Exception as e:
        logger.error("Preflight check failed: %s", e)
        result = {
            "status": "error",
            "checks": [
                {"name": "Preflight", "severity": "high", "message": "Preflight check failed"}
            ],
            "can_proceed": False,
        }

    return result


async def _generate_stacks(deps: _DeployDeps, request: Request) -> dict[str, Any]:
    """Generate CDK stacks from AppSpec."""
    try:
        from pathlib import Path

        from dazzle.deploy import DeploymentRunner
        from dazzle.deploy.config import load_deployment_config

        proj = deps.project_dir or Path(".")
        config = load_deployment_config(proj / "dazzle.toml")
        if deps.appspec is None:
            return {"status": "error", "message": "No AppSpec loaded"}
        runner = DeploymentRunner(deps.appspec, proj, config)
        result = runner.run(dry_run=True)

        return {
            "status": "ok",
            "stacks": result.stacks_generated,
            "output_dir": str(result.artifacts.get("estimated_files", "")),
        }
    except ImportError:
        return {"status": "error", "message": "Deploy module not available"}
    except Exception as e:
        logger.error("Stack generation failed: %s", e)
        return {"status": "error", "message": "Stack generation failed"}


async def _run_deploy(deps: _DeployDeps, request: Request) -> dict[str, Any]:
    """Execute deployment."""
    try:
        from pathlib import Path

        from dazzle.deploy import DeploymentRunner
        from dazzle.deploy.config import load_deployment_config

        proj = deps.project_dir or Path(".")
        config = load_deployment_config(proj / "dazzle.toml")
        if deps.appspec is None:
            return {"status": "error", "message": "No AppSpec loaded"}
        runner = DeploymentRunner(deps.appspec, proj, config)
        result = runner.run(dry_run=False)

        if deps.deploy_history_store:
            from dazzle_back.runtime.deploy_history import DeployStatus

            deploy = deps.deploy_history_store.create_deployment(
                environment=config.environment,
                initiated_by="console",
            )
            deps.deploy_history_store.update_status(
                deploy.id,
                DeployStatus.COMPLETED,
                stacks=result.stacks_generated,
            )

        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Deployment failed: %s", e)
        return {"status": "error", "message": "Deployment failed"}


async def _rollback_to_version(
    deps: _DeployDeps, version_id: str, request: Request
) -> dict[str, Any]:
    """Rollback to a specific spec version."""
    if not deps.rollback_manager:
        return {"status": "error", "message": "Rollback not available"}

    try:
        result = deps.rollback_manager.rollback_to(version_id)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Rollback failed: %s", e)
        return {"status": "error", "message": "Rollback failed"}


async def _preflight_results_partial(deps: _DeployDeps) -> HTMLResponse:
    """HTMX partial: preflight check results."""
    from dazzle_back.runtime.console_routes import _create_jinja_env

    env = _create_jinja_env()
    template = env.get_template("console/partials/preflight_results.html")
    html = template.render(checks=[])  # nosemgrep
    return HTMLResponse(content=html)


async def _rollback_confirm_partial(deps: _DeployDeps, version_id: str) -> HTMLResponse:
    """HTMX partial: rollback confirmation modal."""
    diff: dict[str, Any] = {}
    if deps.spec_version_store:
        diff = deps.spec_version_store.get_diff(version_id)

    from dazzle_back.runtime.console_routes import _create_jinja_env

    env = _create_jinja_env()
    template = env.get_template("console/partials/rollback_confirm.html")
    html = template.render(diff=diff, version_id=version_id)  # nosemgrep
    return HTMLResponse(content=html)


# =============================================================================
# Route Factory
# =============================================================================


def create_deploy_routes(
    deploy_history_store: Any | None = None,
    spec_version_store: Any | None = None,
    rollback_manager: Any | None = None,
    appspec: Any | None = None,
    project_dir: Any | None = None,
    get_current_user: Any = None,
) -> APIRouter:
    """
    Create deploy routes for the Founder Console.

    Args:
        deploy_history_store: Deployment history store
        spec_version_store: Spec version store
        rollback_manager: Rollback manager
        appspec: Loaded AppSpec
        project_dir: Project directory path
        get_current_user: Auth dependency

    Returns:
        FastAPI APIRouter
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI required")

    router = APIRouter(prefix="/_console", tags=["Founder Console - Deploy"])

    deps = _DeployDeps(
        deploy_history_store=deploy_history_store,
        spec_version_store=spec_version_store,
        rollback_manager=rollback_manager,
        appspec=appspec,
        project_dir=project_dir,
        get_current_user=get_current_user,
    )

    router.add_api_route("/api/preflight", partial(_run_preflight, deps), methods=["POST"])
    router.add_api_route("/api/generate", partial(_generate_stacks, deps), methods=["POST"])
    router.add_api_route("/api/deploy", partial(_run_deploy, deps), methods=["POST"])
    router.add_api_route(
        "/api/rollback/{version_id}", partial(_rollback_to_version, deps), methods=["POST"]
    )
    router.add_api_route(
        "/partials/preflight-results",
        partial(_preflight_results_partial, deps),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/partials/rollback-confirm/{version_id}",
        partial(_rollback_confirm_partial, deps),
        methods=["GET"],
        response_class=HTMLResponse,
    )

    return router
