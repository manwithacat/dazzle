"""#1626 MCP thin wrapper — hyperpart presentation process.

Doctrine: ``docs/reference/hyperpart-presentation.md``.
Logic lives in ``dazzle.render.presentation``, ``dazzle.qa.hyperpart_opportunity``,
and ``dazzle.product_quality.presentation`` (no circular MCP deps).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.mcp.server.handlers.common import error_response, wrap_handler_errors
from dazzle.product_quality.presentation import score_presentation
from dazzle.qa.hyperpart_dsl_shapes import agent_shape_table, load_shapes, shapes_snapshot
from dazzle.qa.hyperpart_opportunity import build_opportunity_report, scan_appspec
from dazzle.qa.hyperpart_scenarios import catalogue_snapshot, load_scenarios
from dazzle.render.presentation import cognition_snapshot


@wrap_handler_errors
def presentation_cognition_handler(_project_root: Path, _args: dict[str, Any]) -> str:
    """Matrix / host audit state for agent OBSERVE (no project required)."""
    payload = {
        "ok": True,
        "doctrine": "docs/reference/hyperpart-presentation.md",
        "force": "framework-ux hyperpart_presentation",
        "cognition": cognition_snapshot(),
        "cli": {
            "opportunities": "dazzle qa hyperpart-opportunities --table",
            "felt_bar": "dazzle demo quality -p <app-or-examples>",
            "recapture": ".venv/bin/python scripts/recapture_demo_fleet_1626.py --apps <app>",
        },
        "mcp": {
            "product_quality": "product_quality(operation=score) — residual_total includes presentation",
            "presentation_opportunities": "presentation(operation=opportunities, app=…)",
            "presentation_residual": "presentation(operation=residual, app=…)",
            "presentation_shapes": "presentation(operation=shapes) — rational DSL shapes + scenario_missing",
            "knowledge": "knowledge(operation=counter_prior, id=ref_as_repr)",
        },
    }
    return json.dumps(payload, indent=2, default=str)


def _resolve_app_root(project_root: Path, args: dict[str, Any]) -> Path | None:
    """Resolve app directory with dazzle.toml from project_root and optional app=."""
    app = args.get("app")
    root = project_root
    if app and (project_root / "examples" / str(app) / "dazzle.toml").is_file():
        root = project_root / "examples" / str(app)
    elif app and (project_root / str(app) / "dazzle.toml").is_file():
        root = project_root / str(app)
    if not (root / "dazzle.toml").is_file():
        return None
    return root


@wrap_handler_errors
def presentation_opportunities_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Static hyperpart opportunity scan (+ presentation_cognition block)."""
    root = _resolve_app_root(project_root, args)
    if root is None:
        return error_response(
            "project with dazzle.toml required "
            "(pass project_path to an app, or app= when project_path is examples/)"
        )
    appspec = load_project_appspec(root)
    opps = scan_appspec(appspec)
    report = build_opportunity_report(app=root.name, opportunities=opps)
    report["ok"] = True
    report["force"] = "framework-ux hyperpart_presentation"
    return json.dumps(report, indent=2, default=str)


@wrap_handler_errors
def presentation_residual_handler(project_root: Path, args: dict[str, Any]) -> str:
    """OCR presentation residual (ref_as_repr / person_as_text) for one app."""
    root = _resolve_app_root(project_root, args)
    if root is None:
        return error_response(
            "project with dazzle.toml required "
            "(pass project_path to an app, or app= when project_path is examples/)"
        )
    scores = score_presentation(root, root.name)
    residual = sum(1 for s in scores if s.residual)
    payload = {
        "ok": True,
        "app": root.name,
        "residual": residual,
        "force": "framework-ux hyperpart_presentation" if residual else None,
        "scores": [
            {
                "name": s.name,
                "path": s.path,
                "residual": s.residual,
                "kind": s.kind,
                "reason": s.reason,
                "snippet": s.snippet,
            }
            for s in scores
        ],
        "notes": (
            "Absent stills or missing tesseract → ocr_skip (not residual). "
            "Folded into product_quality residual_total when scoring the fleet."
        ),
    }
    return json.dumps(payload, indent=2, default=str)


def _filter_shape_table(
    table: list[dict[str, str]], *, status_f: str, id_f: str
) -> list[dict[str, str]]:
    rows = table
    if status_f:
        rows = [r for r in rows if r.get("status") == status_f]
    if id_f:
        rows = [r for r in rows if str(r.get("id") or "").lower() == id_f]
    return rows


def _shape_detail(id_f: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    if not id_f:
        return None, None
    shapes = {r.id: r for r in load_shapes()}
    shape = shapes.get(id_f)
    sc_rows = [s.to_json() for s in load_scenarios() if s.hyperpart.lower() == id_f]
    return (shape.to_json() if shape is not None else None, sc_rows)


@wrap_handler_errors
def presentation_shapes_handler(_project_root: Path, args: dict[str, Any]) -> str:
    """Rational DSL shapes + scenario coverage for domain-modelling agents.

    No project required. Optional ``id=<hyperpart>`` filters to one part;
    optional ``status=live|planned|chrome_only`` filters the table.
    """
    snap = shapes_snapshot()
    status_f = str(args.get("status") or "").strip().lower()
    id_f = str(args.get("id") or args.get("hyperpart") or "").strip().lower()
    table = _filter_shape_table(agent_shape_table(), status_f=status_f, id_f=id_f)
    shape_json, sc_rows = _shape_detail(id_f)
    missing = int(snap.get("scenario_missing") or 0)
    planned = int(snap.get("planned") or 0)
    cat = catalogue_snapshot()
    payload: dict[str, Any] = {
        "ok": True,
        "doctrine": snap.get("doctrine"),
        "force": ("framework-ux hyperpart_emitter" if (missing > 0 or planned > 0) else None),
        "snapshot": snap,
        "shapes": table,
        "scenario_catalogue": {"count": cat.get("count"), "path": cat.get("path")},
        "cli": {
            "probes": "python scripts/improve_example_probes.py --status",
            "opportunities": "dazzle qa hyperpart-opportunities --table",
        },
        "notes": (
            "Every live pick-a-surface / pick-a-work-surface shape needs a scenario "
            "row so agents can model domains without inventing DSL. "
            "scenario_missing residual forces /improve framework-ux hyperpart_emitter."
        ),
    }
    if shape_json is not None:
        payload["shape"] = shape_json
        payload["scenarios"] = sc_rows
    return json.dumps(payload, indent=2, default=str)


def handle_presentation(arguments: dict[str, Any]) -> str:
    """Dispatch presentation tool operations."""
    op = arguments.get("operation") or "cognition"
    root_raw = (
        arguments.get("project_root")
        or arguments.get("_resolved_project_path")
        or arguments.get("project_path")
    )
    root = Path(root_raw) if root_raw else Path(".")

    if op == "cognition":
        return presentation_cognition_handler(root, arguments)
    if op == "opportunities":
        if root_raw is None and not arguments.get("app"):
            return error_response("project_path (app or examples/) required for opportunities")
        return presentation_opportunities_handler(root, arguments)
    if op == "residual":
        if root_raw is None and not arguments.get("app"):
            return error_response("project_path (app or examples/) required for residual")
        return presentation_residual_handler(root, arguments)
    if op in ("shapes", "dsl_shapes", "shape"):
        return presentation_shapes_handler(root, arguments)
    return error_response(f"Unknown presentation operation: {op}")
