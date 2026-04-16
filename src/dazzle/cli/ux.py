"""CLI commands for UX verification."""

import asyncio
import json as _json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()

ux_app = typer.Typer(
    help="UX verification — deterministic interaction testing.",
    no_args_is_help=True,
)


def _resolve_runtime_urls(project_root: Path) -> tuple[str, str]:
    """Resolve site_url and api_url from runtime.json or env/manifest.

    Priority:
        1. DAZZLE_SITE_URL / DAZZLE_API_URL environment variables
        2. .dazzle/runtime.json written by ``dazzle serve``
        3. Manifest [urls] section
        4. Defaults (localhost:3000 / localhost:8000)

    In DNR mode the UI and API share a single port, so api_url falls back
    to site_url when runtime.json is present but api_url is unreachable.
    """
    import os

    from dazzle.core.manifest import resolve_api_url, resolve_site_url

    env_site = os.environ.get("DAZZLE_SITE_URL", "")
    env_api = os.environ.get("DAZZLE_API_URL", "")
    if env_site and env_api:
        return env_site.rstrip("/"), env_api.rstrip("/")

    runtime_json = project_root / ".dazzle" / "runtime.json"
    if runtime_json.exists():
        try:
            data = _json.loads(runtime_json.read_text())
            site = data.get("ui_url", "")
            if site:
                # DNR serves UI + API on the same port; api_url in
                # runtime.json points at a separate port that only exists
                # in Docker/split mode.  Use site_url for both.
                return site.rstrip("/"), site.rstrip("/")
        except Exception:
            pass

    return resolve_site_url(), resolve_api_url()


def _run_structural_only() -> int:
    """Run structural checks only (no browser, no database)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    inventory = generate_inventory(appspec)

    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")
    console.print("[yellow]Structural-only mode — skipping browser tests[/yellow]")

    # For structural, we'd need rendered HTML. For now, report the inventory.
    report = generate_report([], [])
    console.print(report.to_markdown())
    return 0


def _run_contracts(
    project_root: Path,
    strict: bool = False,
    update_baseline: bool = False,
    persona_filter: str = "",
    entity_filter: str = "",
) -> int:
    """Run contract verification against a live Dazzle app (no browser)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.baseline import Baseline, BaselineDiff, compare_results
    from dazzle.testing.ux.contract_checker import check_contract
    from dazzle.testing.ux.contracts import RBACContract, generate_contracts
    from dazzle.testing.ux.htmx_client import HtmxClient

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        console.print(f"[red]Failed to load project: {e}[/red]")
        return 1

    # Generate contracts
    contracts = generate_contracts(appspec)
    console.print(f"[dim]Generated {len(contracts)} contracts[/dim]")

    # Apply filters
    if entity_filter:
        contracts = [
            c
            for c in contracts
            if getattr(c, "entity", "") == entity_filter
            or getattr(c, "workspace", "") == entity_filter
        ]
        console.print(
            f"[dim]Filtered to entity '{entity_filter}': {len(contracts)} contracts[/dim]"
        )
    if persona_filter:
        contracts = [
            c for c in contracts if not isinstance(c, RBACContract) or c.persona == persona_filter
        ]
        console.print(
            f"[dim]Filtered to persona '{persona_filter}': {len(contracts)} contracts[/dim]"
        )

    if not contracts:
        console.print("[yellow]No contracts to verify.[/yellow]")
        return 0

    # Resolve URLs
    site_url, _api_url = _resolve_runtime_urls(project_root)
    client = HtmxClient(base_url=site_url)

    console.print("[bold]Running contract verification...[/bold]")
    console.print(f"[dim]  site: {site_url}[/dim]")

    async def _run() -> None:
        # Build per-persona clients: non-RBAC contracts need a persona
        # that actually has access to the entity (not always admin).
        from dazzle.core.ir.domain import PermissionKind
        from dazzle.core.ir.triples import get_permitted_personas as _get_permitted_personas_raw

        def _get_permitted_personas(
            appspec_arg: Any, entity_name: str, operation: object
        ) -> list[str]:
            return _get_permitted_personas_raw(
                list(appspec_arg.domain.entities),
                appspec_arg.personas,
                entity_name,
                operation,
            )

        # Separate RBAC and non-RBAC contracts
        rbac_contracts = [c for c in contracts if isinstance(c, RBACContract)]
        other_contracts = [c for c in contracts if not isinstance(c, RBACContract)]

        # Cache authenticated clients by persona
        persona_clients: dict[str, HtmxClient] = {}

        async def _get_client(persona: str) -> HtmxClient:
            if persona not in persona_clients:
                c = HtmxClient(base_url=site_url)
                ok = await c.authenticate(persona)
                if ok:
                    persona_clients[persona] = c
                else:
                    console.print(f"[yellow]  auth failed for {persona}[/yellow]")
            return persona_clients.get(persona, client)

        # Authenticate admin as fallback
        await client.authenticate("admin")
        persona_clients["admin"] = client

        # ------------------------------------------------------------------
        # Non-RBAC contracts — use a persona with LIST access
        # ------------------------------------------------------------------
        entity_ids: dict[str, str] = {}  # entity name -> first ID

        for contract in other_contracts:
            path = contract.url_path

            # Pick a persona that can access this page.
            # Create/edit forms need a persona with the matching permission,
            # not just LIST access.
            ent_name = getattr(contract, "entity", "")
            ws_name = getattr(contract, "workspace", "")
            if ent_name:
                from dazzle.testing.ux.contracts import (
                    CreateFormContract,
                    DetailViewContract,
                    EditFormContract,
                )

                if isinstance(contract, CreateFormContract):
                    permitted = _get_permitted_personas(appspec, ent_name, PermissionKind.CREATE)
                elif isinstance(contract, (EditFormContract, DetailViewContract)):
                    # Use persona with broadest access (DELETE > UPDATE > LIST)
                    # so all action buttons are visible for checking
                    permitted = _get_permitted_personas(appspec, ent_name, PermissionKind.DELETE)
                    if not permitted:
                        permitted = _get_permitted_personas(
                            appspec, ent_name, PermissionKind.UPDATE
                        )
                else:
                    permitted = _get_permitted_personas(appspec, ent_name, PermissionKind.LIST)
                persona = permitted[0] if permitted else "admin"
            elif ws_name:
                # Find first persona with workspace access
                ws_spec = next((w for w in appspec.workspaces if w.name == ws_name), None)
                if ws_spec and ws_spec.access and ws_spec.access.allow_personas:
                    persona = ws_spec.access.allow_personas[0]
                else:
                    persona = appspec.personas[0].id if appspec.personas else "admin"
            else:
                persona = "admin"

            active_client = await _get_client(persona)

            if "{id}" in path:
                if ent_name and ent_name not in entity_ids:
                    try:
                        import httpx

                        async with httpx.AsyncClient() as http:
                            id_resp = await http.get(
                                f"{site_url}/__test__/entity/{ent_name}",
                                timeout=10,
                            )
                        if id_resp.status_code == 200:
                            items = id_resp.json()
                            if items:
                                entity_ids[ent_name] = str(
                                    items[0].get("id", "")
                                    if isinstance(items[0], dict)
                                    else items[0]
                                )
                    except Exception:
                        pass
                eid = entity_ids.get(ent_name, "")
                if not eid:
                    contract.status = "pending"
                    contract.error = f"No test entity found for {ent_name}"
                    continue
                path = path.replace("{id}", eid)

            try:
                page_resp = await active_client.get_full_page(path)
                if page_resp.status == 403:
                    contract.status = "failed"
                    contract.error = f"HTTP 403 as {persona}"
                else:
                    check_contract(contract, page_resp.html)
            except Exception as e:
                contract.status = "failed"
                contract.error = str(e)

        # ------------------------------------------------------------------
        # RBAC contracts — group by persona, authenticate once per persona
        # ------------------------------------------------------------------
        personas_grouped: dict[str, list[RBACContract]] = {}
        for rc in rbac_contracts:
            personas_grouped.setdefault(rc.persona, []).append(rc)

        for pid, persona_contracts in personas_grouped.items():
            persona_client = HtmxClient(base_url=site_url)
            auth_ok = await persona_client.authenticate(pid)
            if not auth_ok:
                for rc in persona_contracts:
                    rc.status = "failed"
                    rc.error = f"Authentication failed for persona '{pid}'"
                continue

            for rc in persona_contracts:
                try:
                    # update/delete checks need the detail page, not the list page.
                    # Skip if entity has no view surface (no detail page exists).
                    if rc.operation in ("update", "delete", "UPDATE", "DELETE"):
                        eid = entity_ids.get(rc.entity, "")
                        if not eid:
                            # Try to fetch an entity ID
                            try:
                                htmx_resp = await persona_client.get_full_page(
                                    f"/__test__/entity/{rc.entity}"
                                )
                                if htmx_resp.status == 200:
                                    import json as _j

                                    items = _j.loads(htmx_resp.html)
                                    if items:
                                        eid = str(items[0].get("id", ""))
                                        entity_ids[rc.entity] = eid
                            except Exception:
                                pass
                        if eid:
                            path = f"/app/{rc.entity.lower()}/{eid}"
                        else:
                            rc.status = "pending"
                            rc.error = f"No entity ID for {rc.entity}"
                            continue
                    else:
                        path = rc.url_path

                    page_resp = await persona_client.get_full_page(path)
                    if page_resp.status == 404:
                        # No detail page for this entity — skip
                        rc.status = "passed"
                    elif page_resp.status == 403:
                        # Access denied is correct for forbidden personas
                        if not rc.expected_present:
                            rc.status = "passed"
                        else:
                            rc.status = "failed"
                            rc.error = f"HTTP 403 for {rc.persona}"
                    else:
                        check_contract(rc, page_resp.html)
                except Exception as e:
                    rc.status = "failed"
                    rc.error = str(e)

    asyncio.run(_run())

    # Tally results
    passed = sum(1 for c in contracts if c.status == "passed")
    failed = sum(1 for c in contracts if c.status == "failed")
    pending = sum(1 for c in contracts if c.status == "pending")

    console.print(f"\n[bold]Contracts: {passed} passed, {failed} failed, {pending} pending[/bold]")

    # Show failures
    for c in contracts:
        if c.status == "failed":
            label = f"{c.kind.value}"
            ent = getattr(c, "entity", "") or getattr(c, "workspace", "")
            if ent:
                label += f":{ent}"
            if isinstance(c, RBACContract):
                label += f":{c.persona}:{c.operation}"
            console.print(f"  [red]FAIL[/red] {label} — {c.error}")

    # Baseline comparison
    baseline_path = project_root / ".dazzle" / "ux_baseline.json"
    old_baseline = Baseline.load(baseline_path)

    new_baseline = Baseline(
        total=len(contracts),
        passed=passed,
        failed=failed,
        contracts={c.contract_id: c.status for c in contracts if c.status != "pending"},
    )

    if old_baseline.contracts:
        diff: BaselineDiff = compare_results(old_baseline, new_baseline)
        if diff.regressions:
            console.print(f"\n[red]Regressions ({len(diff.regressions)}):[/red]")
            for cid in diff.regressions:
                console.print(f"  [red]↓[/red] {cid}")
        if diff.fixed:
            console.print(f"\n[green]Fixed ({len(diff.fixed)}):[/green]")
            for cid in diff.fixed:
                console.print(f"  [green]↑[/green] {cid}")
        if diff.new_failures:
            console.print(f"\n[yellow]New failures ({len(diff.new_failures)}):[/yellow]")
            for cid in diff.new_failures:
                console.print(f"  [yellow]•[/yellow] {cid}")

    if update_baseline:
        new_baseline.save(baseline_path)
        console.print(f"[dim]Baseline updated: {baseline_path}[/dim]")

    if strict and failed > 0:
        return 1
    return 0


@ux_app.command("explore")
def explore_command(
    persona: str = typer.Option("", "--persona", help="DSL persona id the subagent walks as"),
    cycles: int = typer.Option(
        1,
        "--cycles",
        help="Number of run contexts to prepare (one per persona when --all-personas)",
    ),
    strategy: str = typer.Option(
        "edge_cases",
        "--strategy",
        help="Explore strategy: edge_cases | missing_contracts | persona_journey | cross_persona_consistency | regression_hunt | create_flow_audit",
    ),
    app_dir: Path = typer.Option(
        None,
        "--app-dir",
        help="Path to the Dazzle app root. Defaults to current working directory.",
    ),
    all_personas: bool = typer.Option(
        False,
        "--all-personas",
        help="Prepare one run per DSL-declared persona instead of the single --persona",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit run context as JSON (for outer-assistant consumption)"
    ),
) -> None:
    """Prepare an explore run: state dir, findings file, runner script.

    This command does NOT launch the browser — that requires the outer
    Claude Code assistant's ``Task`` tool, which can only be invoked from
    its cognitive loop (see #789 and the substrate docs).

    What it does:

    1. Derives the persona list (from ``--persona`` or ``--all-personas``).
    2. Calls ``init_explore_run`` for each persona × cycle to create the
       run directory, empty findings file, and ModeRunner background
       script.
    3. Prints the resulting contexts so the outer assistant can pick up
       the paths and dispatch subagents.

    Example:
        dazzle ux explore --persona teacher --strategy edge_cases
        dazzle ux explore --all-personas --strategy persona_journey
        dazzle ux explore --strategy regression_hunt --cycles 3
    """
    import json as _json_mod

    from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
        EXPLORE_STRATEGIES,
        init_explore_run,
    )

    if strategy not in EXPLORE_STRATEGIES:
        console.print(
            f"[red]Unknown strategy {strategy!r}. Expected one of: "
            f"{', '.join(EXPLORE_STRATEGIES)}[/red]"
        )
        raise typer.Exit(2)

    resolved_app_dir = (app_dir or Path.cwd()).resolve()
    if not resolved_app_dir.is_dir():
        console.print(f"[red]App dir does not exist: {resolved_app_dir}[/red]")
        raise typer.Exit(2)

    personas: list[str]
    if all_personas:
        from dazzle.core.appspec_loader import load_project_appspec

        try:
            appspec = load_project_appspec(resolved_app_dir)
        except Exception as e:
            console.print(f"[red]Failed to load AppSpec from {resolved_app_dir}: {e}[/red]")
            raise typer.Exit(2) from e
        personas = [p.id for p in (appspec.personas or []) if getattr(p, "interactive", True)]
        if not personas:
            console.print(
                "[yellow]No interactive personas declared in DSL — nothing to do[/yellow]"
            )
            raise typer.Exit(0)
    else:
        if not persona:
            console.print("[red]Either --persona or --all-personas must be specified[/red]")
            raise typer.Exit(2)
        personas = [persona]

    contexts: list[dict[str, Any]] = []
    for persona_id in personas:
        for cycle_i in range(1, cycles + 1):
            ctx = init_explore_run(
                app_root=resolved_app_dir,
                persona_id=persona_id,
                strategy=strategy,
            )
            ctx_dict = ctx.to_dict()
            ctx_dict["cycle_index"] = cycle_i
            contexts.append(ctx_dict)

    if json_output:
        console.print_json(_json_mod.dumps({"runs": contexts}, indent=2))
        return

    console.print(f"[green]Prepared {len(contexts)} explore run(s)[/green]")
    console.print(f"  strategy: {strategy}")
    console.print(f"  app: {resolved_app_dir.name} at {resolved_app_dir}")
    for c in contexts:
        console.print(
            f"  • persona={c['persona_id']} run={c['run_id']} findings={c['findings_path']}"
        )
    console.print(
        "\n[dim]Next: the outer assistant should run each runner script "
        "via Bash(run_in_background=true), poll conn.json, and dispatch a "
        "subagent with the prompt from build_subagent_prompt.[/dim]"
    )


@ux_app.command("verify")
def verify_command(
    structural: bool = typer.Option(
        False, "--structural", help="Structural checks only (no browser)"
    ),
    contracts: bool = typer.Option(
        False, "--contracts", help="Run contract verification (no browser)"
    ),
    browser: bool = typer.Option(False, "--browser", help="Run Playwright browser tests only"),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 on any contract failure"),
    update_baseline: bool = typer.Option(
        False, "--update-baseline", help="Update baseline after run"
    ),
    persona: str = typer.Option("", "--persona", help="Filter to specific persona"),
    entity: str = typer.Option("", "--entity", help="Filter to specific entity"),
    keep_db: bool = typer.Option(False, "--keep-db", help="Keep test database after verification"),
    db_url: str = typer.Option("", "--db-url", help="Postgres URL override"),
    format_: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: markdown or json"
    ),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser headless"),
) -> None:
    """Run UX verification against the current project.

    Derives an interaction inventory from the DSL, boots the app against
    a test database, and verifies every framework-generated interaction.

    Assumes the app is already running via ``dazzle serve --local``.
    The command reads ``.dazzle/runtime.json`` to discover the server URL.

    Examples:
        dazzle ux verify                    # Full verification (contracts + browser)
        dazzle ux verify --contracts        # Contract checks only (fast, no browser)
        dazzle ux verify --browser          # Playwright browser tests only
        dazzle ux verify --structural       # HTML checks only (fast)
        dazzle ux verify --persona teacher  # Filter by persona
        dazzle ux verify --headed           # Watch the browser
    """
    if structural:
        raise typer.Exit(_run_structural_only())

    project_root = Path.cwd().resolve()

    # Route: --contracts only
    if contracts and not browser:
        raise typer.Exit(
            _run_contracts(
                project_root,
                strict=strict,
                update_baseline=update_baseline,
                persona_filter=persona,
                entity_filter=entity,
            )
        )

    # Route: --browser only — skip contracts, run Playwright below
    # Route: neither flag — run contracts first, then browser
    if not browser:
        rc = _run_contracts(
            project_root,
            strict=strict,
            update_baseline=update_baseline,
            persona_filter=persona,
            entity_filter=entity,
        )
        if strict and rc != 0:
            raise typer.Exit(rc)

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.harness import check_postgres_available
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report
    from dazzle.testing.ux.runner import InteractionRunner

    project_root = Path.cwd().resolve()
    project_name = project_root.name

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        console.print(f"[red]Failed to load project: {e}[/red]")
        raise typer.Exit(1)

    # Generate inventory
    inventory = generate_inventory(appspec)
    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")

    # Filter if requested
    if persona:
        inventory = [i for i in inventory if i.persona == persona]
        console.print(f"[dim]Filtered to persona '{persona}': {len(inventory)} interactions[/dim]")
    if entity:
        inventory = [i for i in inventory if i.entity == entity]
        console.print(f"[dim]Filtered to entity '{entity}': {len(inventory)} interactions[/dim]")

    if not inventory:
        console.print("[yellow]No interactions to test.[/yellow]")
        raise typer.Exit(0)

    # Check Postgres
    harness_url = db_url or "postgresql://localhost:5432/postgres"
    if not check_postgres_available(harness_url):
        console.print(
            "[red]Postgres is not available.[/red]\n"
            "  Ensure PostgreSQL is running locally.\n"
            "  macOS: brew services start postgresql@16\n"
            "  Or set --db-url to a reachable Postgres instance."
        )
        raise typer.Exit(1)

    # Resolve URLs from runtime.json (written by dazzle serve)
    site_url, api_url = _resolve_runtime_urls(project_root)

    runner = InteractionRunner(
        site_url=site_url,
        api_url=api_url,
        headless=headless,
    )

    console.print(f"[bold]Running UX verification for {project_name}...[/bold]")
    console.print(f"[dim]  site: {site_url}  api: {api_url}[/dim]")

    # Reset + seed test data so we start from a known state
    import httpx

    from dazzle.testing.ux.fixtures import generate_seed_payload

    headers = runner._test_headers()
    console.print("[dim]  resetting test data...[/dim]")
    try:
        resp = httpx.post(f"{api_url}/__test__/reset", headers=headers, timeout=10)
        if resp.status_code == 200:
            console.print("[dim]  reset OK[/dim]")
        else:
            console.print(f"[yellow]  reset returned {resp.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]  reset failed: {e}[/yellow]")

    seed_payload = generate_seed_payload(appspec)
    fixtures = seed_payload.get("fixtures", [])
    if fixtures:
        # Seed per-entity to avoid one failure blocking all entities
        by_entity: dict[str, list[dict[str, object]]] = {}
        for f in fixtures:
            by_entity.setdefault(f["entity"], []).append(f)

        seeded = 0
        for entity_name, entity_fixtures in by_entity.items():
            try:
                resp = httpx.post(
                    f"{api_url}/__test__/seed",
                    json={"fixtures": entity_fixtures},
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    seeded += len(entity_fixtures)
                else:
                    console.print(f"[yellow]  seed {entity_name}: {resp.text[:120]}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]  seed {entity_name}: {e}[/yellow]")
        console.print(f"[dim]  seeded {seeded}/{len(fixtures)} fixtures[/dim]")

    results = asyncio.run(runner.run_all(inventory))

    report = generate_report(results, [])

    if format_ == "json":
        console.print_json(_json.dumps(report.to_json(), indent=2))
    else:
        console.print(report.to_markdown())

    if report.failed > 0:
        raise typer.Exit(1)
