"""RBAC verification CLI commands."""

from __future__ import annotations  # required: forward reference

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import typer

from dazzle.cli.common import resolve_project
from dazzle.testing.byte_route_proof import find_byte_route_violations

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

    # #1141: framework's /auth/login expects application/json, not
    # form-encoded. The pre-fix `data=` shape produced a 422 against
    # vanilla Dazzle projects, surfacing as "Admin login failed" on
    # every persona row with no signal that the verifier and the
    # framework auth endpoint disagreed on encoding.
    resp = await async_retrying_request(
        client,
        "POST",
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
    )
    if resp.status_code >= 400:
        # #1141: include the response body excerpt so a 422 from a
        # project that required extra fields (2FA, captcha) gives the
        # operator something to act on. Pre-fix the error was bare
        # `Login failed (422): <email>` with no hint of the cause.
        body = (getattr(resp, "text", "") or "")[:200]
        raise RuntimeError(f"Login failed ({resp.status_code}): {email} — {body!r}")
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

    import httpx

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0
    ) as client:  # DZ-HTTP-NORETRY  one-shot CLI
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


@rbac_app.command("routes")
def routes_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero on any violation (CI security gate)."
    ),
) -> None:
    """Route-override conformance: every domain route is RBAC-matrix-represented.

    #1420 Slice 3 / ADR-0040 D3. Flags custom route-overrides in ``routes/`` that
    shadow a generated entity route without a ``# dazzle:implements`` binding (no
    matrix row), and bindings naming an entity/op the AppSpec lacks (dangling).
    Run ``dazzle rbac routes --strict`` in CI to fail the build on any escape.
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.surface_converter import convert_surfaces_to_services
    from dazzle.http.runtime.route_overrides import (
        discover_route_overrides,
        verify_route_matrix_completeness,
    )

    root = resolve_project(manifest)
    appspec = load_project_appspec(root)
    overrides = discover_route_overrides(root / "routes")
    _services, endpoints = convert_surfaces_to_services(appspec.surfaces, appspec.domain)
    generated = {(ep.method.value, ep.path) for ep in endpoints}
    violations = verify_route_matrix_completeness(appspec, overrides, generated)

    if not violations:
        typer.echo("Route matrix-completeness: OK — every domain route is matrix-represented.")
        return
    for v in violations:
        typer.echo(f"VIOLATION: {v}", err=True)
    typer.echo(f"\n{len(violations)} route(s) escape the RBAC matrix.", err=True)
    if strict:
        raise typer.Exit(code=1)


@rbac_app.command("verify")
def verify_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
) -> None:
    """Run dynamic RBAC verification against an in-process app (Layer 2)."""
    from dazzle.rbac.verifier import verify

    root = resolve_project(manifest)
    try:
        report = asyncio.run(verify(root))
    except Exception as exc:
        typer.echo(f"RBAC verification failed: {exc}", err=True)
        raise typer.Exit(code=1)

    report_path = root / ".dazzle" / "rbac-verify-report.json"
    report.save(report_path)

    # Boot failure — verify() returns a zeroed report with `error` set.
    if report.error is not None:
        typer.echo(f"RBAC verification could not run: {report.error}", err=True)
        typer.echo(f"Report: {report_path}")
        raise typer.Exit(code=1)

    typer.echo(
        f"RBAC verification: {report.total} cells | {report.passed} passed | "
        f"{report.violated} violated | {report.warnings} warnings"
    )
    # #1314 — atomic-flow permit-gate probes, reported separately from CRUD cells.
    flow_violations = [f for f in report.flows if f.result.value == "VIOLATION"]
    if report.flows:
        flow_passed = sum(1 for f in report.flows if f.result.value == "PASS")
        flow_warn = sum(1 for f in report.flows if f.result.value == "WARNING")
        typer.echo(
            f"Atomic flows: {len(report.flows)} probes | {flow_passed} passed | "
            f"{len(flow_violations)} violated | {flow_warn} warnings"
        )
    typer.echo(f"Report: {report_path}")
    for cell in report.cells:
        if cell.result.value == "VIOLATION":
            typer.echo(
                f"  VIOLATION  {cell.role}/{cell.entity}/{cell.operation}: "
                f"expected {cell.expected.value}, got HTTP {cell.observed_status}",
                err=True,
            )
    for flow in flow_violations:
        typer.echo(
            f"  VIOLATION  atomic:{flow.flow} as {flow.role}: "
            f"expected {flow.expected.value}, got HTTP {flow.observed_status}",
            err=True,
        )
    if report.violated > 0 or flow_violations:
        raise typer.Exit(code=1)


@rbac_app.command("prove")
def prove_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
) -> None:
    """Prove RBAC meta-properties from the DSL (WP-2; no server required).

    Discharges the Proof-class properties of docs/reference/rbac-proof-model.md §5
    over the static core (scope satisfiability, least-privilege containment,
    deny-overrides precedence, role-hierarchy acyclicity, separation-of-duty),
    emitting a counter-model on any violation. Exits non-zero if a property fails.
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.rbac.prove import prove_all

    root = resolve_project(manifest)
    appspec = load_project_appspec(root)
    report = prove_all(appspec)

    if format == "json":
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(f"RBAC proof — {report.project}")
        for p in report.properties:
            # The status is printed verbatim — PROVED / VACUOUS / INFORMATIONAL /
            # FAILED are visually distinct so a vacuous or informational result is
            # never mistaken for a substantive proof.
            typer.echo(f"  [{p.status.value}] {p.name} ({p.evidence.value}): {p.summary}")
            for v in p.violations:
                typer.echo(f"      ✗ {v.description}", err=True)
                if v.counter_model:
                    typer.echo(f"        counter-model: {v.counter_model}", err=True)
        if report.residual_notes:
            # Surface the actual abstraction notes, not just a count, so the auditor
            # sees which scopes are over-approximated (rbac-proof-model.md §4).
            typer.echo("  residual model abstractions (over-approximation; see §4):")
            for note in report.residual_notes:
                typer.echo(f"      · {note}")
        verdict = "VIOLATIONS FOUND" if not report.passed else "no violations"
        typer.echo(
            f"  → {verdict} — {report.substantive_obligations} substantive obligation(s) discharged"
        )

    if not report.passed:
        raise typer.Exit(code=1)


@rbac_app.command("report")
def report_cmd(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown"),
    lint: bool = typer.Option(
        False, "--lint", help="Lint marketing copy (README) against the claim ledger (WP-7)."
    ),
) -> None:
    """Generate compliance report from last verification run, or --lint the copy.

    With --lint, checks the claim ledger's integrity and scans the README for
    access-control claims that exceed their discharged evidence class (e.g.
    'provably enforced' when enforcement is only conformance-tested). Exits
    non-zero on any finding. Needs no verification run or project.
    """
    if lint:
        from pathlib import Path

        from dazzle.rbac.claim_ledger import lint_readme, verify_ledger_integrity

        repo_root = Path(__file__).resolve().parents[3]
        errors = verify_ledger_integrity()
        findings = lint_readme(repo_root / "README.md")
        for e in errors:
            typer.echo(f"  LEDGER ERROR: {e}", err=True)
        for f in findings:
            typer.echo(f"  OVERCLAIM in {f.source}: …{f.excerpt}…", err=True)
            typer.echo(f"               → {f.reason}", err=True)
        if errors or findings:
            typer.echo(
                f"claim-lint: {len(errors)} ledger error(s), {len(findings)} overclaim(s)", err=True
            )
            raise typer.Exit(code=1)
        typer.echo("claim-lint: clean — all RBAC copy is within its discharged evidence class.")
        return

    from dazzle.rbac.report import generate_report
    from dazzle.rbac.verifier import VerificationReport

    root = resolve_project(manifest)
    report_path = root / ".dazzle" / "rbac-verify-report.json"
    if not report_path.exists():
        typer.echo("No verification report found. Run `dazzle rbac verify` first.", err=True)
        raise typer.Exit(code=1)
    report = VerificationReport.load(report_path)
    typer.echo(generate_report(report, format=format))


@rbac_app.command("access-review")
def access_review_cmd(
    tenant: str = typer.Option(..., "--tenant", "-t", help="Organization (tenant) id"),
    as_of: str = typer.Option("", "--as-of", help="Roster as of ISO-8601 datetime (default: now)"),
    since: str = typer.Option("", "--since", help="JML change-period start (ISO-8601)"),
    until: str = typer.Option("", "--until", help="JML change-period end (ISO-8601)"),
    output_format: str = typer.Option("markdown", "--format", "-f", help="markdown | json"),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
) -> None:
    """Generate an access-review evidence pack for an org (auth Plan 2b).

    Reads the live auth store: a membership roster (current, or point-in-time via
    --as-of), the Joiner/Mover/Leaver change stream over [--since, --until],
    SOC 2 / ISO 27001 control mappings, and a tamper-evidence attestation.
    """
    import json
    from datetime import UTC, datetime

    from dazzle.cli.db import _resolve_url
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.rbac.access_evidence import build_access_review
    from dazzle.rbac.report import render_access_review_markdown

    url = _resolve_url(database_url)
    if not url:
        typer.echo("No database URL — set DATABASE_URL or pass --database-url.", err=True)
        raise typer.Exit(code=1)

    store = AuthStore(database_url=url)

    # M4: a typo'd tenant must not silently render as an empty org. Warn if the
    # org id is unknown to the framework registry (non-fatal — legacy/domain-root
    # apps may not register it, but an empty pack on a typo is a dangerous false
    # "no access" negative).
    if (
        getattr(store, "get_organization", None) is not None
        and store.get_organization(tenant) is None
    ):
        typer.echo(
            f"WARNING: no organization with id {tenant!r} in the registry — "
            "the evidence pack may be empty because the tenant id is wrong.",
            err=True,
        )

    try:
        review = build_access_review(
            store,
            tenant,
            as_of=as_of or None,
            since=since or None,
            until=until or None,
            generated_at=datetime.now(UTC).isoformat(),
        )
    except ValueError as exc:
        # H3: an unparseable / non-UTC --as-of/--since/--until would otherwise
        # become a silent lexical mis-filter. Fail loud instead.
        typer.echo(f"Invalid date input: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if output_format == "json":
        typer.echo(json.dumps(review.to_dict(), indent=2))
    else:
        typer.echo(render_access_review_markdown(review))
    # Non-zero exit if the evidence's own integrity chain is broken (audit signal).
    if not review.chain.ok:
        typer.echo(
            f"WARNING: membership_events tamper-evidence chain BROKEN "
            f"({review.chain.mismatched_count} mismatch(es))",
            err=True,
        )
        raise typer.Exit(code=1)


@rbac_app.command("byte-routes")
def byte_routes_cmd(
    strict: bool = typer.Option(
        False, "--strict", help="Exit 1 if any byte route bypasses serve_bytes"
    ),
) -> None:
    """Prove every stored-byte route goes through serve_bytes (#1551)."""
    from pathlib import Path

    repo = Path.cwd()
    violations = find_byte_route_violations(repo)
    if not violations:
        typer.echo("OK: every byte-serving route goes through serve_bytes.")
        return
    for v in violations:
        typer.echo(f"VIOLATION: {v}", err=True)
    if strict:
        raise typer.Exit(code=1)


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
