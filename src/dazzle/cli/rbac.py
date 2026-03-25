"""RBAC verification CLI commands."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import typer

from dazzle.cli.common import resolve_project

rbac_app = typer.Typer(help="RBAC verification and compliance.", no_args_is_help=True)


# ---------------------------------------------------------------------------
# Scope verification types and helpers
# ---------------------------------------------------------------------------


@dataclass
class ScopeTarget:
    """An entity + persona pair that should have row-level scope filtering."""

    entity_name: str
    persona_id: str
    is_all: bool  # True when scope condition is None (= "all")


@dataclass
class ScopeCheckResult:
    """Result of a single scope verification probe."""

    entity_name: str
    persona_id: str
    admin_count: int
    persona_count: int
    is_all: bool
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        if self.is_all:
            return "PASS"
        if self.admin_count == 0:
            return "SKIP"
        if self.persona_count < self.admin_count:
            return "PASS"
        return "FAIL"

    @property
    def status_display(self) -> str:
        s = self.status
        if s == "PASS" and self.is_all:
            return "PASS (scope: all)"
        if s == "FAIL":
            pct = (
                round(self.persona_count / self.admin_count * 100) if self.admin_count > 0 else 100
            )
            return f"FAIL ({pct}% visible)"
        if s == "SKIP":
            return "SKIP (0 rows)"
        if s == "ERROR":
            return f"ERROR ({self.error})"
        return "PASS"


@dataclass
class ScopeVerificationReport:
    """Full report of scope fidelity verification."""

    results: list[ScopeCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == "ERROR")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")

    def to_json(self) -> list[dict[str, Any]]:
        return [
            {
                "entity": r.entity_name,
                "persona": r.persona_id,
                "admin_count": r.admin_count,
                "persona_count": r.persona_count,
                "is_all": r.is_all,
                "status": r.status,
                "error": r.error,
            }
            for r in self.results
        ]


def analyze_scope_targets(appspec: Any) -> list[ScopeTarget]:
    """Extract entity/persona pairs that have scope rules from the appspec.

    Returns a list of :class:`ScopeTarget` for each entity that has at least
    one ``ScopeRule`` in its ``access.scopes``.  Scope rules with
    ``condition=None`` are treated as ``scope: all`` (no filtering expected).
    """
    from dazzle.core.ir.domain import PermissionKind

    targets: list[ScopeTarget] = []
    for entity in appspec.domain.entities:
        if entity.access is None:
            continue
        for scope_rule in entity.access.scopes:
            # Only care about read/list scopes for verification
            if scope_rule.operation not in (PermissionKind.READ, PermissionKind.LIST):
                continue
            personas = scope_rule.personas if scope_rule.personas else ["*"]
            is_all = scope_rule.condition is None
            for persona_id in personas:
                targets.append(
                    ScopeTarget(
                        entity_name=entity.name,
                        persona_id=persona_id,
                        is_all=is_all,
                    )
                )
    return targets


async def _login(
    client: Any,
    base_url: str,
    email: str,
    password: str,
) -> dict[str, str]:
    """Login via the app's auth endpoint and return session cookies."""
    from dazzle.core.http_client import async_retrying_request

    resp = await async_retrying_request(
        client,
        "POST",
        f"{base_url}/auth/login",
        data={"email": email, "password": password},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Login failed ({resp.status_code}): {email}")
    return dict(resp.cookies)


async def _get_entity_count(
    client: Any,
    base_url: str,
    entity_plural: str,
    cookies: dict[str, str] | None = None,
) -> int:
    """Query entity list endpoint and return total count from pagination."""
    from dazzle.core.http_client import async_retrying_request

    url = f"{base_url}/api/{entity_plural}?page_size=1"
    resp = await async_retrying_request(client, "GET", url, cookies=cookies)
    if resp.status_code == 403:
        return 0  # correctly denied
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {url} returned {resp.status_code}")
    data = resp.json()
    count: int = data.get("total", len(data.get("items", [])))
    return count


async def run_scope_verification(
    appspec: Any,
    base_url: str,
    admin_email: str,
    admin_password: str,
) -> ScopeVerificationReport:
    """Run scope fidelity checks against a live Dazzle instance."""
    from dazzle.core.strings import to_api_plural

    targets = analyze_scope_targets(appspec)
    report = ScopeVerificationReport()

    if not targets:
        return report

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Login as admin
        try:
            admin_cookies = await _login(client, base_url, admin_email, admin_password)
        except Exception as exc:
            for t in targets:
                report.results.append(
                    ScopeCheckResult(
                        entity_name=t.entity_name,
                        persona_id=t.persona_id,
                        admin_count=0,
                        persona_count=0,
                        is_all=t.is_all,
                        error=f"Admin login failed: {exc}",
                    )
                )
            return report

        # Cache admin counts per entity
        admin_counts: dict[str, int] = {}

        for target in targets:
            entity_plural = to_api_plural(target.entity_name)

            # Get admin count (cached)
            if target.entity_name not in admin_counts:
                try:
                    admin_counts[target.entity_name] = await _get_entity_count(
                        client, base_url, entity_plural, cookies=admin_cookies
                    )
                except Exception as exc:
                    report.results.append(
                        ScopeCheckResult(
                            entity_name=target.entity_name,
                            persona_id=target.persona_id,
                            admin_count=0,
                            persona_count=0,
                            is_all=target.is_all,
                            error=f"Admin query failed: {exc}",
                        )
                    )
                    continue

            admin_count = admin_counts[target.entity_name]

            # For "all" scope, no need to query — persona sees everything
            if target.is_all:
                report.results.append(
                    ScopeCheckResult(
                        entity_name=target.entity_name,
                        persona_id=target.persona_id,
                        admin_count=admin_count,
                        persona_count=admin_count,
                        is_all=True,
                    )
                )
                continue

            # Login as persona test user
            persona_email = f"{target.persona_id}@test.local"
            try:
                persona_cookies = await _login(client, base_url, persona_email, "test")
            except Exception as exc:
                report.results.append(
                    ScopeCheckResult(
                        entity_name=target.entity_name,
                        persona_id=target.persona_id,
                        admin_count=admin_count,
                        persona_count=0,
                        is_all=False,
                        error=f"Persona login failed: {exc}",
                    )
                )
                continue

            # Query as persona
            try:
                persona_count = await _get_entity_count(
                    client, base_url, entity_plural, cookies=persona_cookies
                )
            except Exception as exc:
                report.results.append(
                    ScopeCheckResult(
                        entity_name=target.entity_name,
                        persona_id=target.persona_id,
                        admin_count=admin_count,
                        persona_count=0,
                        is_all=False,
                        error=f"Persona query failed: {exc}",
                    )
                )
                continue

            report.results.append(
                ScopeCheckResult(
                    entity_name=target.entity_name,
                    persona_id=target.persona_id,
                    admin_count=admin_count,
                    persona_count=persona_count,
                    is_all=False,
                )
            )

    return report


def format_scope_report(report: ScopeVerificationReport) -> str:
    """Format a scope verification report as a table."""
    lines: list[str] = []
    lines.append("Scope Fidelity Verification")
    lines.append("\u2501" * 28)
    lines.append("")

    if not report.results:
        lines.append("No entities with scope rules found.")
        return "\n".join(lines)

    # Column widths
    ew = max(len(r.entity_name) for r in report.results)
    ew = max(ew, len("Entity"))
    pw = max(len(r.persona_id) for r in report.results)
    pw = max(pw, len("Persona"))

    header = f"{'Entity':<{ew}}  {'Persona':<{pw}}  {'Admin':>6}  {'Scoped':>6}  Status"
    lines.append(header)
    lines.append("\u2500" * len(header))

    for r in report.results:
        admin_str = str(r.admin_count) if r.error is None else "-"
        persona_str = str(r.persona_count) if r.error is None else "-"
        mark = "\u2713" if r.status in ("PASS", "SKIP") else "\u2717"
        lines.append(
            f"{r.entity_name:<{ew}}  {r.persona_id:<{pw}}  {admin_str:>6}  "
            f"{persona_str:>6}  {mark} {r.status_display}"
        )

    lines.append("")
    lines.append(
        f"Total: {len(report.results)} checks | "
        f"{report.passed} passed | {report.failed} failed | "
        f"{report.skipped} skipped | {report.errors} errors"
    )
    return "\n".join(lines)


@rbac_app.command("matrix")
def matrix(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
) -> None:
    """Generate static access matrix from DSL (no server required)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.rbac.matrix import generate_access_matrix

    root = resolve_project(manifest)
    appspec = load_project_appspec(root)
    access_matrix = generate_access_matrix(appspec)

    if format == "json":
        typer.echo(json.dumps(access_matrix.to_json(), indent=2))
    elif format == "csv":
        typer.echo(access_matrix.to_csv())
    else:
        typer.echo(access_matrix.to_table())

    for w in access_matrix.warnings:
        typer.echo(f"WARNING: {w.message}", err=True)


@rbac_app.command("verify")
def verify_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
) -> None:
    """Run RBAC verification against a live server (Layer 2)."""
    typer.echo(
        "RBAC verification not yet implemented — use `dazzle rbac matrix` for static analysis"
    )
    raise typer.Exit(code=0)


@rbac_app.command("report")
def report_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown"),
) -> None:
    """Generate compliance report from last verification run."""
    from dazzle.rbac.report import generate_report
    from dazzle.rbac.verifier import VerificationReport

    root = resolve_project(manifest)
    report_path = root / ".dazzle" / "rbac-verify-report.json"
    if not report_path.exists():
        typer.echo("No verification report found. Run `dazzle rbac verify` first.", err=True)
        raise typer.Exit(code=1)
    report = VerificationReport.load(report_path)
    typer.echo(generate_report(report, format=format))


@rbac_app.command("verify-scope")
def verify_scope_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    base_url: str = typer.Option("http://localhost:8000", "--url", help="Running app URL"),
    admin_email: str = typer.Option("admin@example.com", "--admin-email", help="Admin user email"),
    admin_password: str = typer.Option("admin", "--admin-password", help="Admin user password"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Verify scope filters restrict data on a running instance.

    Authenticates as each persona and queries scoped entities to confirm
    that row-level filtering is working.  Requires test users to be seeded
    (via ``dazzle demo save`` or the test-authenticate endpoint).
    """
    from dazzle.core.appspec_loader import load_project_appspec

    root = resolve_project(manifest)
    appspec = load_project_appspec(root)

    try:
        report = asyncio.run(run_scope_verification(appspec, base_url, admin_email, admin_password))
    except Exception as exc:
        typer.echo(f"Scope verification failed: {exc}", err=True)
        raise typer.Exit(code=1)

    if as_json:
        typer.echo(json.dumps(report.to_json(), indent=2))
    else:
        typer.echo(format_scope_report(report))

    if report.failed > 0:
        raise typer.Exit(code=1)
