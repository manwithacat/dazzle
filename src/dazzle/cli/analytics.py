"""Analytics CLI commands (v0.61.0).

Commands:
- analytics audit: Inspect DSL for PII-annotation gaps and subprocessor
  misalignment. Warn-only — never fails a build.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

analytics_app = typer.Typer(
    help="Analytics, consent, and privacy tooling (v0.61.0).",
    no_args_is_help=True,
)

# Field names whose presence suggests the field probably holds PII. If the
# DSL author has declared the field without a `pii(...)` annotation, the audit
# flags it as a likely miss. Names are matched case-insensitively as
# substrings; this is a heuristic, not a rule.
# Order matters — first matching substring wins. More-specific patterns
# come first so `ip_address` hits the location hint before `address`
# catches it as contact.
_PII_NAME_HINTS: list[tuple[str, str]] = [
    # Location (specific IP/geo patterns first)
    ("ip_address", "location"),
    ("ipaddress", "location"),
    ("latitude", "location"),
    ("longitude", "location"),
    ("gps", "location"),
    # Biometric
    ("biometric", "biometric"),
    ("fingerprint", "biometric"),
    ("face_template", "biometric"),
    # Health
    ("medical", "health"),
    ("diagnosis", "health"),
    ("prescription", "health"),
    # Financial
    ("bank_account", "financial"),
    ("iban", "financial"),
    ("card_number", "financial"),
    ("credit_card", "financial"),
    ("salary", "financial"),
    ("income", "financial"),
    # Identity (specific patterns before name-substring catches)
    ("date_of_birth", "identity"),
    ("dob", "identity"),
    ("birthday", "identity"),
    ("ssn", "identity"),
    ("national_id", "identity"),
    ("passport", "identity"),
    ("tax_id", "identity"),
    ("nino", "identity"),
    ("first_name", "identity"),
    ("last_name", "identity"),
    ("full_name", "identity"),
    ("given_name", "identity"),
    ("family_name", "identity"),
    ("surname", "identity"),
    ("forename", "identity"),
    # Contact (broadest, matched last)
    ("email", "contact"),
    ("phone", "contact"),
    ("mobile", "contact"),
    ("postcode", "contact"),
    ("zipcode", "contact"),
    ("zip_code", "contact"),
    ("street", "contact"),
    ("address", "contact"),
]


@analytics_app.command("audit")
def analytics_audit(
    project_dir: Path = typer.Option(  # noqa: B008
        ".",
        "--project-dir",
        "-p",
        help="Project root directory (default: current directory)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Report PII annotation gaps and subprocessor alignment issues.

    Scans the linked AppSpec for three classes of misalignment:

    1. **Likely-PII unannotated**: entity fields whose names strongly suggest
       personal data (email, phone, dob, etc.) but lack a `pii(...)` modifier.

    2. **Subprocessor collision**: app-declared subprocessors that shadow a
       framework default AND differ in consent_category / jurisdiction.

    3. **Orphaned subprocessors**: framework-provided subprocessors declared
       but not referenced by any integration or provider declaration (future
       Phase 3 check; today just surfaces everything).

    All findings are warnings — this command never fails the build. Run
    before shipping to keep the privacy surface honest.
    """
    from dazzle.core.appspec_loader import load_project_appspec

    root = project_dir.resolve()
    spec = load_project_appspec(root)

    findings_pii = _scan_pii_name_hints(spec)
    findings_subproc = _scan_subprocessors(spec)

    if format == "json":
        typer.echo(
            json.dumps(
                {
                    "pii_name_hints": findings_pii,
                    "subprocessors": findings_subproc,
                },
                indent=2,
            )
        )
        return

    _print_table(findings_pii, findings_subproc)


def _scan_pii_name_hints(spec) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    """Yield one finding per entity field whose name looks like PII but isn't annotated."""
    out: list[dict[str, str]] = []
    entities = getattr(spec, "domain", None)
    if entities is None:
        return out
    for entity in entities.entities:
        for field in entity.fields:
            if field.pii is not None:
                continue
            hint = _match_pii_hint(field.name)
            if hint is None:
                continue
            out.append(
                {
                    "entity": entity.name,
                    "field": field.name,
                    "suggested_category": hint,
                    "message": (
                        f"Field `{entity.name}.{field.name}` looks like {hint} PII "
                        f"but has no pii() annotation."
                    ),
                }
            )
    return out


def _match_pii_hint(field_name: str) -> str | None:
    """Return the suggested PII category if field name matches a heuristic pattern."""
    lower = field_name.lower()
    for hint, category in _PII_NAME_HINTS:
        if hint in lower:
            return category
    return None


def _scan_subprocessors(spec) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Report subprocessor summary + collisions with framework defaults."""
    from dazzle.compliance.analytics import FRAMEWORK_SUBPROCESSORS
    from dazzle.core.ir import SubprocessorSpec as _SP

    app_declared: list[_SP] = list(getattr(spec, "subprocessors", []) or [])
    app_by_name = {sp.name: sp for sp in app_declared}
    framework_by_name = {sp.name: sp for sp in FRAMEWORK_SUBPROCESSORS}

    out: list[dict[str, object]] = []

    # Emit a row per declared subprocessor (framework + app merged view).
    for name, sp in {**framework_by_name, **app_by_name}.items():
        overridden = name in app_by_name and name in framework_by_name
        collision_details: dict[str, str] | None = None
        if overridden:
            default = framework_by_name[name]
            if (
                sp.consent_category != default.consent_category
                or sp.jurisdiction != default.jurisdiction
                or sp.legal_basis != default.legal_basis
            ):
                collision_details = {
                    "framework_consent_category": default.consent_category.value,
                    "app_consent_category": sp.consent_category.value,
                    "framework_jurisdiction": default.jurisdiction,
                    "app_jurisdiction": sp.jurisdiction,
                    "framework_legal_basis": default.legal_basis.value,
                    "app_legal_basis": sp.legal_basis.value,
                }
        out.append(
            {
                "name": sp.name,
                "label": sp.label,
                "handler": sp.handler,
                "handler_address": sp.handler_address or "",
                "jurisdiction": sp.jurisdiction,
                "consent_category": sp.consent_category.value,
                "legal_basis": sp.legal_basis.value,
                "retention": sp.retention,
                "dpa_url": sp.dpa_url or "",
                "scc_url": sp.scc_url or "",
                "data_categories": [c.value for c in sp.data_categories],
                "cookies": list(sp.cookies),
                "needs_sccs": sp.needs_sccs,
                "is_framework_default": sp.is_framework_default,
                "collision_with_framework_default": collision_details,
            }
        )
    return out


def _print_table(
    pii_findings: list[dict[str, str]],
    subproc_findings: list[dict[str, object]],
) -> None:
    """Human-readable table output."""
    typer.echo("=" * 60)
    typer.echo("PII annotation audit")
    typer.echo("=" * 60)
    if not pii_findings:
        typer.echo("  ✓ No likely-PII fields missing pii() annotation.")
    else:
        for f in pii_findings:
            typer.echo(
                f"  ! {f['entity']}.{f['field']}  "
                f"(looks like {f['suggested_category']} PII — add pii(category={f['suggested_category']}))"
            )

    typer.echo("")
    typer.echo("=" * 60)
    typer.echo(f"Subprocessors ({len(subproc_findings)})")
    typer.echo("=" * 60)
    for sp in subproc_findings:
        marker = "framework-default" if sp.get("is_framework_default") else "app-declared"
        sccs = " [needs SCCs]" if sp.get("needs_sccs") else ""
        typer.echo(
            f"  • {sp['name']:25} {sp['label']:30} "
            f"{sp['jurisdiction']:5} "
            f"consent={sp['consent_category']:15} "
            f"({marker}){sccs}"
        )
        collision = sp.get("collision_with_framework_default")
        if collision:
            typer.echo(f"    ⚠  Collision with framework default: {collision}")

    typer.echo("")
    typer.echo(f"PII findings: {len(pii_findings)}   Subprocessors: {len(subproc_findings)}")
