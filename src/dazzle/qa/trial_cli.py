"""CLI helpers for trial-inventory / trial-coverage / trial-hypotheses.

Kept out of ``cli/qa.py`` to stay under the complexity / MI ratchet.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer


def run_trial_inventory(project_dir: Path, *, as_json: bool) -> None:
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.trial_inventory import build_coverage_inventory, inventory_to_json

    appspec = load_project_appspec(project_dir)
    targets = build_coverage_inventory(appspec)
    if as_json:
        typer.echo(json.dumps(inventory_to_json(targets), indent=2))
        return
    for t in targets:
        typer.echo(f"{t.kind:16} {t.url:40} {t.name}")


def run_trial_coverage(
    project_dir: Path,
    *,
    persona: str,
    base_url: str | None,
    output: Path | None,
) -> None:
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.trial_inventory import (
        build_coverage_inventory,
        coverage_report_to_json,
        inventory_to_json,
    )

    appspec = load_project_appspec(project_dir)
    targets = build_coverage_inventory(appspec)
    app_name = project_dir.name

    if not base_url:
        payload = inventory_to_json(targets)
        payload["mode"] = "coverage_static"
        payload["app"] = app_name
        path = _default_coverage_path(project_dir, output, "qa-coverage-static")
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"Static inventory: {len(targets)} targets → {path}")
        return

    if not persona:
        typer.echo("--persona is required for live coverage probe", err=True)
        raise typer.Exit(code=2)

    hits = _live_probe(base_url.rstrip("/"), persona, targets, appspec=appspec)
    report = coverage_report_to_json(app=app_name, persona=persona, targets=targets, hits=hits)
    path = _default_coverage_path(project_dir, output, f"qa-coverage-{persona}")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    counts = report.get("counts") or {}
    typer.echo(f"Coverage {persona}: {counts} → {path} ({len(hits)} hits / {len(targets)} targets)")


def _default_coverage_path(project_dir: Path, output: Path | None, stem: str) -> Path:
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        return output
    out_dir = project_dir / "dev_docs"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return out_dir / f"{stem}-{stamp}.json"


def _live_probe(
    base: str,
    persona: str,
    targets: list[Any],
    *,
    appspec: Any = None,
) -> list[Any]:
    import httpx

    from dazzle.qa.trial_inventory import (
        CoverageHit,
        classify_http_status,
        matrix_expected_deny,
    )

    try:
        ml = httpx.post(
            f"{base}/qa/magic-link",
            json={"persona_id": persona},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        typer.echo(f"Could not reach {base}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if ml.status_code != 200:
        typer.echo(
            f"magic-link failed HTTP {ml.status_code} — need DAZZLE_QA_MODE=1 "
            f"and persona {persona}",
            err=True,
        )
        raise typer.Exit(code=1)

    link = ml.json().get("url") or ""
    hits: list[CoverageHit] = []
    with httpx.Client(base_url=base, timeout=20.0, follow_redirects=True) as client:
        client.get(link)
        for t in targets:
            try:
                resp = client.get(t.url)
                status, own = classify_http_status(resp.status_code)
                detail = ""
                if status == "rbac_denied" and appspec is not None:
                    expected = matrix_expected_deny(appspec, persona, t)
                    if expected is True:
                        own = "rbac_expected"
                        detail = "matrix DENY"
                    elif expected is False:
                        own = "product"
                        detail = "matrix allows but HTTP denied — unexpected"
                        status = "blocked"
                hits.append(
                    CoverageHit(
                        url=t.url,
                        name=t.name,
                        kind=t.kind,
                        persona=persona,
                        status=status,
                        http_status=resp.status_code,
                        detail=detail,
                        ownership_hint=own,
                    )
                )
            except httpx.HTTPError as exc:
                hits.append(
                    CoverageHit(
                        url=t.url,
                        name=t.name,
                        kind=t.kind,
                        persona=persona,
                        status="error",
                        detail=str(exc),
                        ownership_hint="harness",
                    )
                )
    return hits


def run_trial_hypotheses(project_dir: Path) -> None:
    candidates = [
        project_dir / "agent" / "domain-theory",
        project_dir / "docs" / "domain-theory.md",
        project_dir / "docs" / "qa" / "domain-theory.md",
    ]
    found: list[Path] = []
    for c in candidates:
        if c.is_dir():
            found.extend(sorted(c.glob("*.md")))
        elif c.is_file():
            found.append(c)
    if not found:
        typer.echo(
            "No domain-theory file found. Create agent/domain-theory/<domain>.md "
            "with falsifiable H-ids (see docs/recipes/agent-qa-ladder.md)."
        )
        return
    for p in found:
        try:
            typer.echo(str(p.relative_to(project_dir)))
        except ValueError:
            typer.echo(str(p))


def run_smoke_crawl(
    project_dir: Path,
    *,
    persona: str,
    base_url: str,
    output: Path | None,
    headless: bool = True,
    max_clicks: int = 20,
    enable_bfs: bool = True,
    fail_on_product: bool = False,
) -> None:
    """Mechanical browser smoke crawl (404 / empty main / pageerror).

    Requires a running app with ``DAZZLE_QA_MODE=1`` and Playwright Chromium.
    """
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.smoke_crawl import build_smoke_report
    from dazzle.qa.smoke_crawl import run_smoke_crawl as _crawl
    from dazzle.qa.trial_inventory import build_coverage_inventory

    if not persona:
        typer.echo("--persona is required for smoke-crawl", err=True)
        raise typer.Exit(code=2)
    if not base_url:
        typer.echo("--base-url is required (running app with DAZZLE_QA_MODE=1)", err=True)
        raise typer.Exit(code=2)

    appspec = load_project_appspec(project_dir)
    targets = build_coverage_inventory(appspec)
    app_name = project_dir.name

    try:
        hits = _crawl(
            base_url=base_url.rstrip("/"),
            persona=persona,
            targets=targets,
            appspec=appspec,
            headless=headless,
            max_clicks=max_clicks,
            enable_bfs=enable_bfs,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    report = build_smoke_report(
        app=app_name,
        persona=persona,
        base_url=base_url.rstrip("/"),
        hits=hits,
        max_clicks=max_clicks,
    )
    path = _default_coverage_path(project_dir, output, f"qa-smoke-{persona}")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    counts = report.get("counts") or {}
    n_seed = len(report.get("auto_seed") or [])
    typer.echo(
        f"Smoke crawl {persona}: {counts} auto_seed={n_seed} → {path} "
        f"({len(hits)} hits / {len(targets)} inventory targets)"
    )
    for h in hits:
        if h.ok:
            continue
        codes = ",".join(i.code for i in h.issues) or "fail"
        typer.echo(f"  FAIL {h.phase:10} {h.url:40} {codes} ({h.ownership_hint})")

    if fail_on_product and n_seed:
        raise typer.Exit(code=1)
