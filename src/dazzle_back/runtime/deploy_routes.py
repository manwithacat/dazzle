"""
Deploy Routes for Founder Console.

Wraps deploy.runner, deploy.preflight, deploy.config for the console UI.
Includes preflight, generate, deploy actions and rollback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import HTMLResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if TYPE_CHECKING:
    pass  # Types used via Any for flexibility

logger = logging.getLogger("dazzle.deploy_routes")


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

    @router.post("/api/preflight")
    async def run_preflight(
        request: Request,
    ) -> dict[str, Any]:
        """Run deployment preflight checks."""
        result: dict[str, Any] = {"status": "ok", "checks": [], "can_proceed": True}

        try:
            from pathlib import Path

            from dazzle.deploy.preflight import PreflightConfig, PreflightMode, PreflightRunner

            proj = project_dir or Path(".")
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
            if deploy_history_store:
                from dazzle_back.runtime.deploy_history import DeployStatus

                deploy = deploy_history_store.create_deployment(
                    environment="default",
                    initiated_by="console",
                )
                deploy_history_store.update_status(
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
            result = {
                "status": "error",
                "checks": [{"name": "Preflight", "severity": "high", "message": str(e)}],
                "can_proceed": False,
            }

        return result

    @router.post("/api/generate")
    async def generate_stacks(
        request: Request,
    ) -> dict[str, Any]:
        """Generate CDK stacks from AppSpec."""
        try:
            from pathlib import Path

            from dazzle.deploy import DeploymentRunner
            from dazzle.deploy.config import load_deployment_config

            proj = project_dir or Path(".")
            config = load_deployment_config(proj / "dazzle.toml")
            runner = DeploymentRunner(appspec, proj, config)
            result = runner.run(dry_run=True)

            return {
                "status": "ok",
                "stacks": result.get("stacks", []),
                "output_dir": str(result.get("output_dir", "")),
            }
        except ImportError:
            return {"status": "error", "message": "Deploy module not available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/deploy")
    async def run_deploy(
        request: Request,
    ) -> dict[str, Any]:
        """Execute deployment."""
        try:
            from pathlib import Path

            from dazzle.deploy import DeploymentRunner
            from dazzle.deploy.config import load_deployment_config

            proj = project_dir or Path(".")
            config = load_deployment_config(proj / "dazzle.toml")
            runner = DeploymentRunner(appspec, proj, config)
            result = runner.run(dry_run=False)

            if deploy_history_store:
                from dazzle_back.runtime.deploy_history import DeployStatus

                deploy = deploy_history_store.create_deployment(
                    environment=config.environment,
                    initiated_by="console",
                )
                deploy_history_store.update_status(
                    deploy.id,
                    DeployStatus.COMPLETED,
                    stacks=result.get("stacks", []),
                )

            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.post("/api/rollback/{version_id}")
    async def rollback_to_version(
        version_id: str,
        request: Request,
    ) -> dict[str, Any]:
        """Rollback to a specific spec version."""
        if not rollback_manager:
            return {"status": "error", "message": "Rollback not available"}

        try:
            result = rollback_manager.rollback_to(version_id)
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.get("/partials/preflight-results", response_class=HTMLResponse)
    async def preflight_results_partial() -> HTMLResponse:
        """HTMX partial: preflight check results."""
        from dazzle_back.runtime.console_routes import _create_jinja_env

        env = _create_jinja_env()
        template = env.get_template("console/partials/preflight_results.html")
        html = template.render(checks=[])
        return HTMLResponse(content=html)

    @router.get("/partials/rollback-confirm/{version_id}", response_class=HTMLResponse)
    async def rollback_confirm_partial(version_id: str) -> HTMLResponse:
        """HTMX partial: rollback confirmation modal."""
        diff: dict[str, Any] = {}
        if spec_version_store:
            diff = spec_version_store.get_diff(version_id)

        from dazzle_back.runtime.console_routes import _create_jinja_env

        env = _create_jinja_env()
        template = env.get_template("console/partials/rollback_confirm.html")
        html = template.render(diff=diff, version_id=version_id)
        return HTMLResponse(content=html)

    return router
