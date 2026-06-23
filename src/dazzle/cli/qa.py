"""CLI sub-app for the Dazzle visual QA toolkit."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import typer

from dazzle.core.ir.fields import FieldModifier, FieldTypeKind
from dazzle.core.manifest import load_manifest
from dazzle.qa.signing_seed import (
    SeededDoc,
    SigningSeedContext,
    mint_ephemeral_cert_env,
    write_mock_inbox,
)
from dazzle.qa.signing_verifier import SigningOutcome, verify_signing_outcome
from dazzle.signing.tokens import mint_token

qa_app = typer.Typer(
    help="QA toolkit — visual quality evaluation and screenshot capture.",
    no_args_is_help=True,
)


# Patterns for classifying seed circuit-breaker failures (#1207).
# Schema-drift: DSL declares a field/entity that the live DB schema lacks —
# the recovery path is Alembic, not blueprint regeneration.
# Quotes may appear plain (`"X"`) or JSON-escaped (`\"X\"`) depending on whether
# resp.text returned the raw HTTP body (escaped) or a decoded detail string.
_COL_MISSING_RE = re.compile(
    r'column \\?"([^"\\]+)\\?" of relation \\?"([^"\\]+)\\?" does not exist'
)
_TABLE_MISSING_RE = re.compile(r'relation \\?"([^"\\]+)\\?" does not exist')


def _diagnose_seed_failures(sample_errors: list[str]) -> str | None:
    """Return a recovery hint for the dominant failure mode, or None for generic blueprint-drift.

    Inspects the collected sample_errors strings (each is "Entity/uuid: HTTP 400 {...}").
    Schema-drift wins over table-missing if both appear, since column-add is the more
    common DSL edit; table-missing indicates a never-migrated app and is less frequent.
    """
    for err in sample_errors:
        m = _COL_MISSING_RE.search(err)
        if m:
            column, table = m.group(1), m.group(2)
            return (
                f'Detected schema drift: column "{column}" missing in relation "{table}". '
                f"The DSL declares the field but the live schema doesn't have it. "
                f'Recovery: run `dazzle db revision -m "add {table}.{column}"` '
                f"then `dazzle db upgrade`."
            )
    for err in sample_errors:
        m = _TABLE_MISSING_RE.search(err)
        if m:
            table = m.group(1)
            return (
                f'Detected schema drift: relation "{table}" does not exist. '
                f"The DSL declares the entity but no migration has been applied. "
                f'Recovery: run `dazzle db revision -m "create {table}"` '
                f"then `dazzle db upgrade`."
            )
    return None  # fall back to blueprint-drift message


def _resolve_project_dir(app: str | None) -> Path:
    """Resolve the project directory from --app flag or cwd.

    If *app* is given, looks for ``examples/{app}/`` starting from cwd, then
    falls back to the dazzle package root.  Otherwise returns cwd.
    """
    if app is None:
        return Path.cwd()

    # Try cwd/examples/{app}
    candidate = Path.cwd() / "examples" / app
    if candidate.is_dir():
        return candidate

    # Best-effort fallback to the dazzle package root (#smells-1.1).
    with suppress(Exception):
        import dazzle

        pkg_root = Path(dazzle.__file__).resolve().parents[2]
        candidate = pkg_root / "examples" / app
        if candidate.is_dir():
            return candidate

    typer.echo(f"App directory not found for '{app}'", err=True)
    raise typer.Exit(code=1)


def _seed_demo_data_for_trial(project_dir: Path, site_url: str, test_secret: str) -> bool:
    """Seed demo data after the trial server is up (#817, #820).

    ``--fresh-db`` truncates the DB, which left every trial running
    against an empty app. This helper runs after the reset and after
    ``launch_interaction_server`` has the app listening:

    1. Finds the blueprint (default location
       ``dsl/seeds/demo_data/blueprint.json``). If none, return silently.
    2. Generates JSONL data files from the blueprint into a tempdir
       (unless pre-generated files already exist).
    3. POSTs each entity's rows as a fixture batch to
       ``/__test__/seed`` — this endpoint bypasses Cedar entirely (it
       calls the repository layer directly) so seed succeeds regardless
       of which persona can ``create`` a given entity (#820).

    The test-secret gate keeps the seed endpoint safe; non-dev servers
    don't enable test routes.

    Returns:
        ``True`` if seeding succeeded, was skipped harmlessly (no
        blueprint, no rows, soft failure inside the loop), or partially
        succeeded under the circuit breaker. ``False`` only when the
        hard-gate blueprint verifier flagged validation errors — the
        outer trial flow must abort in that case rather than run the
        LLM agent against an empty DB (#1077).
    """
    import json as _json
    import tempfile

    import httpx

    from dazzle.cli.demo import _find_data_dir
    from dazzle.cli.utils import load_project_appspec
    from dazzle.demo_data.loader import topological_sort_entities
    from dazzle.mcp.server.handlers.demo_data import demo_generate_impl

    blueprint = project_dir / "dsl" / "seeds" / "demo_data" / "blueprint.json"
    existing_data = _find_data_dir(project_dir)

    if not blueprint.exists() and existing_data is None:
        return True  # nothing to seed — harmless skip

    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        typer.echo(f"Seed skipped: could not load appspec ({exc})", err=True)
        return True

    # Hard-gate (#826): verify the blueprint up front and abort the
    # trial when there are errors. Previously this was a soft-gate —
    # errors were reported as a count and the seed loop ran anyway,
    # producing 213 × 400 responses on a stale blueprint plus an
    # opaque "timed out" failure at the end. Aborting here saves the
    # server from the 400 storm (which empirically destabilises the
    # subsequent /__test__/authenticate call) and gives adopters an
    # actionable "run `dazzle demo verify` for details" path.
    #
    # Verifier-internal exceptions (bug in the verifier, not the
    # blueprint) still fall through to the seed attempt so a broken
    # verifier doesn't block qa-trial adoption.
    if blueprint.exists():
        try:
            from dazzle.core.demo_blueprint_persistence import load_blueprint
            from dazzle.demo_data.verify import verify_blueprint

            loaded = load_blueprint(project_dir)
            if loaded is not None:
                report = verify_blueprint(loaded, appspec)
                errors = report.errors()
                if errors:
                    typer.echo(
                        f"Seed aborted: blueprint has {len(errors)} validation "
                        f"error(s). Run `dazzle demo verify` for the full list.",
                        err=True,
                    )
                    for violation in errors[:5]:
                        typer.echo(
                            f"  - {violation.entity}"
                            f"{'.' + violation.field if violation.field else ''}"
                            f": {violation.rule} — {violation.message}",
                            err=True,
                        )
                    if len(errors) > 5:
                        typer.echo(f"  ... and {len(errors) - 5} more.", err=True)
                    return False  # hard-gate abort — outer flow must bail (#1077)
        except Exception:
            # A bug in the verifier must never block a trial — fall through
            # to the seed attempt with whatever blueprint exists (#smells-1.1).
            typer.echo(
                "Note: blueprint verifier raised; continuing without hard-gate.",
                err=True,
            )

    if existing_data is None or not any(existing_data.glob("*.jsonl")):
        tmp_root = Path(tempfile.mkdtemp(prefix="dazzle-trial-seed-"))
        try:
            result = demo_generate_impl(
                project_dir, output_format="jsonl", output_dir=str(tmp_root)
            )
            if result.get("status") != "generated":
                typer.echo(
                    f"Seed skipped: demo_generate_impl returned {result.get('status')}",
                    err=True,
                )
                return True
            data_dir = Path(result["output_dir"])
        except Exception as exc:
            typer.echo(f"Seed skipped: demo data generation failed ({exc})", err=True)
            return True
    else:
        data_dir = existing_data

    # Build the fixture batch by walking files in topological order.
    entity_order = topological_sort_entities(appspec.domain.entities)
    fixtures: list[dict[str, Any]] = []
    for entity_name in entity_order:
        entity_file = data_dir / f"{entity_name}.jsonl"
        if not entity_file.exists():
            continue
        with entity_file.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                fixtures.append(
                    {
                        "id": str(row.get("id", "")),
                        "entity": entity_name,
                        "data": row,
                    }
                )

    if not fixtures:
        typer.echo("Seed skipped: no rows to seed", err=True)
        return True

    headers = {"Content-Type": "application/json"}
    if test_secret:
        headers["X-Test-Secret"] = test_secret

    # /__test__/seed is atomic — a single failure rolls back every
    # fixture in the batch. Blueprint-generated data has #821 quality
    # issues that make partial failure common, so POST per-fixture:
    # bad rows fail individually and good ones persist. ~40 rows per
    # app × a few apps keeps total requests well under any real budget.
    # Circuit breaker (#826): abort after N consecutive non-200
    # responses. Without this, a stale blueprint produces 200+ × 400
    # responses that empirically destabilise the server enough that
    # the downstream /__test__/authenticate call times out. 10 is
    # enough to surface recurring drift patterns (topological order
    # means early failures are usually consistent across the batch)
    # without wasting requests.
    _FAIL_STREAK_ABORT = 10

    created_count = 0
    sample_errors: list[str] = []
    fail_streak = 0
    fail_total = 0
    aborted_by_circuit = False
    try:
        with httpx.Client(timeout=60.0) as client:
            for fixture in fixtures:
                resp = client.post(
                    f"{site_url}/__test__/seed",
                    json={"fixtures": [fixture]},
                    headers=headers,
                )
                if resp.status_code == 200:
                    created_count += len(resp.json().get("created") or {})
                    fail_streak = 0
                else:
                    fail_streak += 1
                    fail_total += 1
                    if len(sample_errors) < 3:
                        err_text = resp.text[:240]
                        sample_errors.append(
                            f"{fixture['entity']}/{fixture['id']}: "
                            f"HTTP {resp.status_code} {err_text}"
                        )
                    if fail_streak >= _FAIL_STREAK_ABORT:
                        aborted_by_circuit = True
                        break
    except Exception as exc:
        typer.echo(f"Seed skipped: POST /__test__/seed raised {exc}", err=True)
        return True

    typer.echo(
        f"Seeded demo data: {created_count} of {len(fixtures)} fixture(s) "
        f"created via /__test__/seed (bypasses Cedar)."
    )
    for err in sample_errors:
        typer.echo(f"  seed error: {err}", err=True)
    if aborted_by_circuit:
        hint = _diagnose_seed_failures(sample_errors)
        if hint is None:
            hint = (
                "Blueprint drift is the most likely cause — run "
                "`dazzle demo verify` to see full details."
            )
        typer.echo(
            f"Seed aborted after {fail_streak} consecutive failures "
            f"(total {fail_total} so far). {hint}",
            err=True,
        )
    return True


def _missing_signing_server_deps() -> list[str]:
    """Importable-module names from the [signing] extra that the signing
    SERVER path needs but the current environment lacks."""
    return [mod for mod in ("fpdf", "pyhanko") if importlib.util.find_spec(mod) is None]


def _provision_signing_env(
    app_spec: Any,
    tmp_root: Path,
    *,
    project_name: str,
    validator_reject: bool = False,
) -> SigningSeedContext | None:
    """Mint ephemeral cert + token secret if the app has any signable entity.

    Returns a :class:`~dazzle.qa.signing_seed.SigningSeedContext` with the
    generated env vars and an empty inbox stub, or ``None`` when no signable
    entity exists.  The caller is responsible for merging ``ctx.env`` into
    ``os.environ`` before booting the server subprocess.

    When *validator_reject* is set (#1382), a UUID is pre-generated for each
    signable entity and ``DAZZLE_QA_SIGNING_REJECT_IDS`` is armed with the
    comma-joined ids in the returned env — so the project ``signing_validator``
    (which reads that var at request time) rejects the seeded row's signature.
    Pre-generation is required because the env is fixed *before* boot but the
    row is seeded *after*; the ids are threaded into the seed so the inserted
    row carries exactly the armed id (the ``/__test__/seed`` endpoint honours an
    explicit ``data["id"]``). Mirrors the proven integration-test pattern in
    ``tests/integration/helpers/signable_runner.py``.
    """
    if not app_spec.has_signable_entity():
        return None
    # Preflight the SERVER half of the signing stack before burning an
    # LLM persona run (#1377): minting the cert needs only cryptography,
    # but sign_document needs fpdf2 + pyhanko in the server process. A
    # missing extra used to surface 6 steps later as an HTTP 500 the
    # persona could only describe as "showstopper".
    missing = _missing_signing_server_deps()
    if missing:
        typer.echo(
            f"Signing trial harness: {' + '.join(missing)} not installed — the app "
            "has signable entities and sign_document would return HTTP 500. "
            "Install with: pip install 'dazzle-dsl[signing]' "
            "(or: uv pip install 'fpdf2>=2.8.0' 'pyhanko>=0.25.0' 'Pillow>=10.0')",
            err=True,
        )
        raise typer.Exit(code=2)
    env = mint_ephemeral_cert_env(tmp_root, project_name=project_name)
    inbox_path = tmp_root / "mock_inbox.json"
    inbox_path.write_text("[]", encoding="utf-8")

    # #1382: pre-generate one UUID per signable entity so the reject env var can
    # be armed before boot with the exact id the seed will then insert under.
    import uuid as _uuid_mod

    signable_ids: dict[str, str] = {
        entity.name: str(_uuid_mod.uuid4())
        for entity in app_spec.domain.entities
        if getattr(entity, "signable", False)
    }
    if validator_reject and signable_ids:
        env["DAZZLE_QA_SIGNING_REJECT_IDS"] = ",".join(signable_ids.values())

    return SigningSeedContext(
        env=env,
        inbox_path=inbox_path,
        seeded_docs=[],
        signable_ids=signable_ids,
        validator_reject=validator_reject,
    )


# Per-entity realistic seed payloads for the trial harness.
# These align with the corresponding ``[[scenario]]`` business contexts in
# the example apps' trial.toml — so when the persona reads the document
# they see content matching what their persona was told to expect.
#
# Unknown entities fall through to _minimal_fields_for's per-field
# type-based placeholders.
_REALISTIC_SEED_OVERRIDES: dict[str, dict[str, Any]] = {
    # contact_manager (parent for EngagementLetter ref)
    "Contact": {
        "first_name": "Marcus",
        "last_name": "Chen",
        "email": "marcus.chen@northwind-apparel.example",
        "company": "Northwind Apparel Ltd",
        "phone": "+44 20 7946 0958",
        "is_favorite": False,
    },
    # contact_manager (signable)
    "EngagementLetter": {
        "party": "Northwind Apparel Ltd",
        "scope_summary": (
            "Q4 brand refresh: new logo system, updated colour palette, "
            "typography rationale, and a 16-page brand book. Delivery in "
            "three milestones over 12 weeks; £42,000 fixed fee + agreed "
            "pass-through costs."
        ),
        "effective_date": "2026-10-01",
        "signatory_name": "Priya Sharma",
        "signatory_email": "priya.sharma@northwind-apparel.example",
    },
    # support_tickets (parent for SlaWaiver ref)
    "Ticket": {
        "title": "P1: Checkout API 503s across EU region",
        "description": (
            "Customer reported intermittent 503 errors on POST "
            "/checkout/finalise from 14:02 UTC. Initial triage suggests "
            "upstream payment processor connection-pool exhaustion."
        ),
        # ticket_number is unique — the suffix logic in _minimal_fields_for
        # will append a run_id prefix to avoid collisions.
        "ticket_number": "INC-2026-0428",
        "subject": "Checkout API intermittent 503",
        "status": "open",
        "priority": "high",
        "severity": "high",
    },
    # support_tickets (signable)
    "SlaWaiver": {
        "breach_summary": (
            "P1 SLA target was 4-hour resolution. The incident on "
            "INC-2026-0428 (Checkout API 503s) took 9 hours to fully "
            "resolve. Root cause: upstream payment processor connection "
            "pool exhaustion compounded by a deficient retry policy on "
            "our side. Customer-visible impact: ~3.2% of EU checkouts "
            "failed during the window."
        ),
        "waiver_terms": (
            "In settlement of the SLA breach: "
            "(a) 20% service credit applied to the November invoice; "
            "(b) written postmortem delivered within 10 business days; "
            "(c) retry-policy fix shipped to staging by Friday and to "
            "production within 14 days; "
            "(d) no further claims arising from the same incident."
        ),
        "signatory_role": "VP Customer Success",
        "signatory_name": "Devon Park",
        "signatory_email": "devon.park@retailco.example",
    },
    # fixtures/signing_validation
    "TestDoc": {
        "party": "Test Co Ltd",
        "body": "Generic test document body. No signatures required for fixture.",
        "signatory_email": "test@example.test",
    },
}


def _placeholder_for_field_type(field: Any, *, _run_id: str | None = None) -> Any:
    """Return a valid placeholder value for a scalar (non-ref) field.

    Used by ``_build_signing_seed_batch`` to populate required fields on
    parent fixture entities and on the signable entity itself.  The returned
    value is always serialisable as JSON.

    ``_run_id`` is appended to unique-constrained string values (email,
    unique str) so repeated calls within the same DB don't cause unique
    violations.  The caller passes a short UUID prefix for this purpose.
    """
    kind = field.type.kind
    if kind == FieldTypeKind.EMAIL:
        suffix = f"-{_run_id}" if _run_id else ""
        return f"trial-parent{suffix}@example.com"
    if kind == FieldTypeKind.DATE:
        return "2026-05-28"
    if kind == FieldTypeKind.DATETIME:
        return "2026-05-28T00:00:00Z"
    if kind == FieldTypeKind.BOOL:
        return False
    if kind in (FieldTypeKind.INT, FieldTypeKind.FLOAT, FieldTypeKind.DECIMAL):
        return 0
    if kind == FieldTypeKind.UUID:
        import uuid as _uuid_mod

        return str(_uuid_mod.uuid4())
    if kind == FieldTypeKind.ENUM:
        vals = field.type.enum_values or []
        return vals[0] if vals else ""
    if kind == FieldTypeKind.MONEY:
        return "0.00"
    if kind in (FieldTypeKind.TEXT, FieldTypeKind.JSON):
        return "Trial-harness seed."
    # STR, URL, TIMEZONE and any unrecognised scalar → short string
    return "Trial parent"


def _minimal_fields_for(entity: Any, *, _run_id: str | None = None) -> dict[str, Any]:
    """Return a minimal required-field payload for *entity* (no refs).

    Only required, non-PK, non-relationship scalar fields are included.
    Relationship fields (HAS_MANY / HAS_ONE / BELONGS_TO / EMBEDS /
    LATEST_ONE / DESCENDANTS_OF / ANCESTORS_OF) and REF FK fields are
    skipped — FK refs for required REF fields are handled via the
    ``refs`` mapping in the fixture batch.

    ``_run_id`` is forwarded to ``_placeholder_for_field_type`` to generate
    unique values for fields with a uniqueness constraint (e.g. email).
    """
    _REL_KINDS = {
        FieldTypeKind.HAS_MANY,
        FieldTypeKind.HAS_ONE,
        FieldTypeKind.BELONGS_TO,
        FieldTypeKind.EMBEDS,
        FieldTypeKind.LATEST_ONE,
        FieldTypeKind.DESCENDANTS_OF,
        FieldTypeKind.ANCESTORS_OF,
        FieldTypeKind.REF,  # refs go in the `refs:` mapping, not `data:`
    }

    data: dict[str, Any] = {}
    for field in entity.fields:
        if FieldModifier.PK in field.modifiers:
            continue
        if field.type.kind in _REL_KINDS:
            continue
        if FieldModifier.REQUIRED not in field.modifiers:
            continue
        data[field.name] = _placeholder_for_field_type(field, _run_id=_run_id)

    # Layer realistic overrides on top — these win over generic placeholders.
    overrides = _REALISTIC_SEED_OVERRIDES.get(entity.name, {})
    entity_field_names = {f.name for f in entity.fields}
    for field_name, value in overrides.items():
        # Only apply if the field actually exists on the entity (guard against
        # DSL renames / removals without updating the overrides dict).
        if field_name in entity_field_names:
            data[field_name] = value

    # Suffix unique-constrained STR and EMAIL fields so repeated seeds don't
    # collide.  Note: _placeholder_for_field_type already suffixes EMAIL fields
    # when it generates the placeholder, but when an override replaces the
    # placeholder with a fixed value the suffix must be applied here instead.
    if _run_id:
        for field in entity.fields:
            is_unique = FieldModifier.UNIQUE in field.modifiers
            if not is_unique:
                continue
            if field.name not in data:
                continue
            if not isinstance(data[field.name], str):
                continue
            if field.type.kind == FieldTypeKind.STR:
                data[field.name] = f"{data[field.name]}-{_run_id[:6]}"
            elif field.type.kind == FieldTypeKind.EMAIL:
                # For email fields, insert the suffix before the '@' so the
                # value remains a syntactically valid email address.
                email_val: str = data[field.name]
                if "@" in email_val:
                    local, domain = email_val.split("@", 1)
                    data[field.name] = f"{local}-{_run_id[:6]}@{domain}"

    return data


def _collect_parent_fixtures(
    entity: Any,
    by_name: dict[str, Any],
    run_id: str,
    fixture_prefix: str,
    collected: list[dict[str, Any]],
    visited: set[str],
) -> dict[str, str]:
    """Recursively collect parent fixture dicts for all required REF fields.

    Returns a ``refs`` mapping of ``{field_name: fixture_id}`` for the
    *entity* being processed.  Grandparent fixtures (required REFs on parent
    entities) are prepended so they appear before their dependants in the
    batch list — the seed endpoint processes fixtures in order.

    *visited* prevents infinite recursion on self-referential entities.
    """
    refs: dict[str, str] = {}
    for field in entity.fields:
        if field.type.kind != FieldTypeKind.REF:
            continue
        if FieldModifier.REQUIRED not in field.modifiers:
            continue
        target_name = field.type.ref_entity
        if target_name in visited:
            continue  # break cycle
        target_entity = by_name.get(target_name)
        if target_entity is None:
            continue

        parent_fixture_id = f"{fixture_prefix}_{target_name.lower()}"
        visited_copy = visited | {target_name}

        # Recurse: collect grandparent fixtures first so they appear before
        # the parent fixture in the batch.
        grandparent_refs = _collect_parent_fixtures(
            target_entity,
            by_name,
            run_id,
            parent_fixture_id,
            collected,
            visited_copy,
        )

        parent_fixture: dict[str, Any] = {
            "id": parent_fixture_id,
            "entity": target_name,
            "data": _minimal_fields_for(target_entity, _run_id=run_id),
        }
        if grandparent_refs:
            parent_fixture["refs"] = grandparent_refs
        collected.append(parent_fixture)

        refs[field.name] = parent_fixture_id

    return refs


def _build_signing_seed_batch(
    entity: Any, app_spec: Any, signatory_email: str, *, signable_id: str | None = None
) -> list[dict[str, Any]]:
    """Build a fixtures batch for one signable entity via ``/__test__/seed``.

    Walks the entity's fields to discover required ``ref`` FK fields, creates
    a minimal parent fixture for each, and wires them up via ``refs:``.
    Required REFs on parent entities (grandparents, etc.) are resolved
    recursively so multi-hop FK chains (e.g. SlaWaiver→Ticket→User) don't
    produce 400 errors.  The signable entity itself is always the last fixture
    in the list under the fixture-id ``"signable_row"``.

    When *signable_id* is given (#1382), the signable row's ``data["id"]`` is
    pinned to it so the inserted row carries the UUID pre-armed in
    ``DAZZLE_QA_SIGNING_REJECT_IDS``. The ``/__test__/seed`` endpoint honours an
    explicit ``data["id"]`` (see ``test_routes._seed_fixtures``).

    Returns a list of fixture dicts ready for ``SeedRequest.fixtures``.
    """
    import uuid as _uuid_mod

    # Short unique suffix so repeated seeds (e.g., re-running integration tests)
    # don't collide on unique-constrained fields (email, etc.).
    run_id = _uuid_mod.uuid4().hex[:8]

    by_name = {e.name: e for e in app_spec.domain.entities}

    parent_fixtures: list[dict[str, Any]] = []
    refs = _collect_parent_fixtures(
        entity, by_name, run_id, "parent", parent_fixtures, {entity.name}
    )

    # Build the signable entity's own data dict: required non-ref scalar fields
    # plus the well-known signatory fields.
    signable_data = _minimal_fields_for(entity, _run_id=run_id)
    # status + signing_service are harness mechanics; always force.
    # status is an auto-injected enum; "sent" is the correct seed state.
    signable_data["status"] = "sent"
    # signing_service is auto-injected by the linker; "native" = Dazzle PDF+PKCS#7.
    signable_data["signing_service"] = "native"
    # signatory fields: prefer the entity's realistic override (already applied
    # by _minimal_fields_for via _REALISTIC_SEED_OVERRIDES); fall back to caller args.
    if "signatory_email" not in signable_data:
        signable_data["signatory_email"] = signatory_email
    if "signatory_name" not in signable_data:
        signable_data["signatory_name"] = "Trial Signatory"
    # #1382: pin the row id when the caller pre-generated one (reject scenarios).
    if signable_id:
        signable_data["id"] = signable_id

    signable_fixture: dict[str, Any] = {
        "id": "signable_row",
        "entity": entity.name,
        "data": signable_data,
    }
    if refs:
        signable_fixture["refs"] = refs

    return [*parent_fixtures, signable_fixture]


def _seed_signable_rows(
    *,
    app_spec: Any,
    base_url: str,
    signatory_email: str,
    test_secret: str = "",
    token_state: str = "fresh",
    signable_ids: dict[str, str] | None = None,
    validator_reject: bool = False,
) -> list[SeededDoc]:
    """For each signable entity in *app_spec*, insert one row + mint a token.

    Uses ``/__test__/seed`` (Cedar-bypass path) rather than the Cedar-gated
    ``/api/{entity}`` endpoint, so this works on apps with Cedar policies.
    Required FK refs are resolved via the AppSpec IR and included as parent
    fixtures in the same batch (#1285).

    ``token_state="expired"`` mints already-expired tokens so *_token_expired*
    scenarios exercise the real "Invalid or expired link" page (TR-51).

    ``signable_ids`` (#1382) maps entity name → a pre-generated UUID to insert
    the row under (so it matches the armed ``DAZZLE_QA_SIGNING_REJECT_IDS``).
    ``validator_reject`` stamps each :class:`SeededDoc` so the verifier expects
    the row to stay ``sent`` (the signature is blocked by the validator).

    Returns a list of :class:`~dazzle.qa.signing_seed.SeededDoc` objects
    (one per signable entity) ready to write into the mock inbox.
    """
    import httpx

    signable_ids = signable_ids or {}

    headers: dict[str, str] = {}
    if test_secret:
        headers["X-Test-Secret"] = test_secret

    docs: list[SeededDoc] = []
    for entity in app_spec.domain.entities:
        if not getattr(entity, "signable", False):
            continue

        fixtures = _build_signing_seed_batch(
            entity, app_spec, signatory_email, signable_id=signable_ids.get(entity.name)
        )
        # The signable row may carry its own realistic signatory_email (from the
        # demo-field overrides in _REALISTIC_SEED_OVERRIDES — e.g. SlaWaiver's
        # "devon.park@retailco.example"). The token + mock-inbox metadata MUST
        # match the *row*, otherwise the rendered document names one signatory
        # while the inbox/token names another. That internal contradiction
        # mis-calibrates qualitative trials: the agent distrusts the document and
        # declines, so server-side signing_validators never fire and the run
        # emits a false "no authority check exists" verdict.
        effective_email = signatory_email
        for fx in fixtures:
            if fx.get("id") == "signable_row":
                effective_email = fx["data"].get("signatory_email", signatory_email)
                break
        resp = httpx.post(
            f"{base_url}/__test__/seed",
            json={"fixtures": fixtures},
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()

        created = resp.json().get("created", {})
        row_id = str(created.get("signable_row", {}).get("id", ""))
        if not row_id:
            raise RuntimeError(
                f"/__test__/seed response missing 'signable_row' id for {entity.name}; "
                f"got created keys: {list(created)}"
            )

        # expires_hours=-1 mints a token whose expiry is already in the
        # past — verify_token then rejects it exactly as it would a real
        # two-week-old email link.
        expires_hours = -1 if token_state == "expired" else 72
        token = mint_token(record_id=row_id, email=effective_email, expires_hours=expires_hours)
        docs.append(
            SeededDoc(
                entity=entity.name,
                id=row_id,
                token=token,
                signing_url=f"{base_url}/sign/{entity.name}/{row_id}?token={token}",
                signatory_email=effective_email,
                token_state=token_state,
                validator_reject=validator_reject,
            )
        )
    return docs


def _build_db_reader(project_dir: Path) -> Callable[[str, str], dict[str, Any] | None]:
    """Return a callable that reads (entity, id) from the runtime Postgres DB.

    Reads the ``DATABASE_URL`` env var at *call* time (not at factory-call
    time) so that env vars set by the server subprocess after factory
    construction are visible.  Passes silently when the env var is absent —
    ``None`` rows are treated as harness errors by the verifier.
    """
    import psycopg
    import psycopg.rows

    def _read(entity: str, row_id: str) -> dict[str, Any] | None:
        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn:
            return None
        # Use psycopg.sql.Identifier to safely quote the table name —
        # parameterised queries cannot bind table names directly, but
        # psycopg's Identifier class escapes the identifier correctly and
        # prevents SQL injection (the entity name comes from the AppSpec IR,
        # but we still want the scan to be clean).
        from psycopg import sql

        query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(entity))
        with psycopg.connect(dsn) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(query, (row_id,))  # nosemgrep
                return cur.fetchone()

    return _read


def _pyhanko_validator(pdf_path: str) -> dict[str, Any]:
    """Validate a PAdES PDF signature via pyhanko.

    Thin wrapper — raises ``ImportError`` if pyhanko is absent (callers
    treat that as a ``{"valid": False, "error": ...}`` result via the
    verifier's try/except guard).
    """
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator.context import ValidationContext

    with open(pdf_path, "rb") as fh:
        reader = PdfFileReader(fh)
        sig = reader.embedded_signatures[0]
        status: Any = validate_pdf_signature(sig, ValidationContext())
    return {
        "valid": bool(status.intact and status.valid),
        "embedded_timestamp": (
            str(status.timestamp_validity) if status.timestamp_validity else None
        ),
        "summary": status.pretty_print_details(),
    }


def _reset_db_for_trial(project_dir: Path) -> None:
    """Truncate entity tables before a trial run (#810).

    Prior ``dazzle qa trial`` runs can leave placeholder rows
    (``Test name 1``, ``UX Edited Value``) in the app's database that
    subsequent trials observe and flag as bugs. This truncates those
    rows while preserving auth — the same behaviour as
    ``dazzle db reset --yes`` but invoked programmatically so we skip
    the interactive confirmation and work against the correct project
    root without requiring a cwd change.
    """
    import os

    from dazzle.cli.db import _resolve_url, _run_with_connection
    from dazzle.cli.utils import load_project_appspec
    from dazzle.db.reset import db_reset_impl

    old_cwd = Path.cwd()
    try:
        os.chdir(project_dir)
        appspec = load_project_appspec(project_dir)
        entities = appspec.domain.entities
        url = _resolve_url("")

        async def _run(conn: Any) -> Any:
            return await db_reset_impl(entities=entities, conn=conn)

        result = asyncio.run(_run_with_connection(project_dir, url, _run, schema=""))
        typer.echo(
            f"Fresh DB: truncated {result['truncated']} tables "
            f"({result['total_rows']:,} rows removed). Auth preserved."
        )
    finally:
        os.chdir(old_cwd)


@qa_app.command("capture")
def qa_capture(
    url: str | None = typer.Option(None, "--url", "-u", help="URL of a running app"),
    app: str | None = typer.Option(None, "--app", "-a", help="Example app name (e.g. simple_task)"),
    persona: str | None = typer.Option(
        None, "--persona", "-p", help="Restrict capture to a single persona"
    ),
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        "-m",
        help=(
            "Path to a fleet-wide JSON manifest. Captured screens are appended "
            "under the app's entry (replacing any prior entry for this app — "
            "re-runs overwrite). Used by the /improve example-apps Tier 2 "
            "sub-strategy to hand a multi-app manifest to a CC subagent."
        ),
    ),
) -> None:
    """Capture screenshots only — no LLM evaluation needed."""
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.capture import build_capture_plan, capture_screenshots, write_manifest
    from dazzle.qa.server import AppConnection, wait_for_ready

    project_dir = _resolve_project_dir(app)

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as e:
        typer.echo(f"Failed to load AppSpec: {e}", err=True)
        raise typer.Exit(code=1)

    # Build capture plan
    targets = build_capture_plan(appspec)
    if not targets:
        typer.echo("No capture targets found (no workspaces or personas defined).", err=True)
        raise typer.Exit(code=1)

    # Filter by persona if requested
    if persona:
        targets = [t for t in targets if t.persona == persona]
        if not targets:
            typer.echo(f"No targets found for persona '{persona}'.", err=True)
            raise typer.Exit(code=1)

    if url is None:
        typer.echo(
            "--url is required. Start the app in another terminal first:\n"
            f"  dazzle e2e env start {app or '<example>'}\n"
            "Then pass its URL:\n"
            "  dazzle qa capture --url http://localhost:8981 ...",
            err=True,
        )
        raise typer.Exit(code=2)

    api_url_resolved = url.replace(":3000", ":8000") if ":3000" in url else url
    connection = AppConnection(
        site_url=url,
        api_url=api_url_resolved,
        process=None,
    )

    try:
        typer.echo("Waiting for server to be ready…")
        ready = asyncio.run(wait_for_ready(connection.api_url))
        if not ready:
            typer.echo("Server did not become ready in time.", err=True)
            raise typer.Exit(code=1)

        # Capture screenshots
        typer.echo(f"Capturing {len(targets)} screen(s)…")
        screens = asyncio.run(
            capture_screenshots(
                targets,
                site_url=connection.site_url,
                api_url=connection.api_url,
                project_dir=project_dir,
            )
        )

    finally:
        connection.stop()

    if not screens:
        typer.echo("No screenshots captured.", err=True)
        raise typer.Exit(code=1)

    # Print paths of captured screenshots
    for screen in screens:
        typer.echo(str(screen.screenshot))

    if manifest is not None:
        app_name = str(getattr(appspec, "name", None) or project_dir.name)
        write_manifest(screens, app_name=app_name, manifest_path=manifest)
        typer.echo(f"Manifest: {manifest}")


@qa_app.command("trial")
def qa_trial(
    app: str | None = typer.Option(None, "--app", "-a", help="Example app name (defaults to cwd)"),
    scenario: str | None = typer.Option(
        None, "--scenario", "-s", help="Scenario name from trial.toml (defaults to first)"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Report output path (default: dev_docs/qa-trial-*.md)"
    ),
    headless: bool = typer.Option(
        True, "--headless/--headed", help="Run browser headless (default) or visible"
    ),
    model: str | None = typer.Option(
        None, "--model", help="Override LLM model (default: Claude Sonnet)"
    ),
    llm_driver: str | None = typer.Option(
        None,
        "--llm-driver",
        help=(
            "How the trial persona reaches the model: 'claude-cli' "
            "(Claude Code CLI, billed to your Claude subscription — no API "
            "key) or 'anthropic-api' (metered, ANTHROPIC_API_KEY). Default: "
            "DAZZLE_LLM_DRIVER env, then [llm] driver in dazzle.toml, then "
            "auto-detect. See docs/reference/llm-drivers.md."
        ),
    ),
    fresh_db: bool = typer.Option(
        False,
        "--fresh-db",
        help=(
            "Truncate entity tables before starting the server. Prevents the "
            "trial from observing stale rows left behind by prior runs "
            "(placeholder values, old fixture data, etc.). Auth is preserved."
        ),
    ),
) -> None:
    """Run a qualitative business-user trial of a Dazzle app.

    Puts an LLM in the shoes of a real business user evaluating this
    software. The LLM attempts meaningful tasks and records friction —
    things that would make a real user hesitate to recommend the
    software. Output is a markdown report for human triage, NOT a
    pass/fail CI gate.

    Requires ``trial.toml`` in the app directory declaring at least
    one scenario. See ``examples/support_tickets/trial.toml`` for
    format.

    Example:

        cd examples/support_tickets
        dazzle qa trial
        # → dev_docs/qa-trial-<scenario>-<timestamp>.md

    """
    import sys
    import time
    import tomllib

    from dazzle.agent.core import DazzleAgent
    from dazzle.agent.executor import PlaywrightExecutor
    from dazzle.agent.missions.trial import build_trial_mission
    from dazzle.agent.observer import PlaywrightObserver
    from dazzle.cli.runtime_impl.ports import read_runtime_test_secret
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.trial_report import (
        build_trial_report,
        render_trial_report,
        trial_abort_message,
    )
    from dazzle.testing.ux.interactions.server_fixture import launch_interaction_server

    project_dir = _resolve_project_dir(app)
    trial_path = project_dir / "trial.toml"

    if not trial_path.exists():
        typer.echo(
            f"No trial.toml at {trial_path}. Create one to declare scenarios — "
            "see examples/support_tickets/trial.toml for format.",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        trial_cfg = tomllib.loads(trial_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        typer.echo(f"trial.toml parse failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    scenarios = trial_cfg.get("scenario", [])
    if not scenarios:
        typer.echo(f"No [[scenario]] entries in {trial_path}", err=True)
        raise typer.Exit(code=2)

    if scenario:
        chosen = next((s for s in scenarios if s.get("name") == scenario), None)
        if chosen is None:
            names = [s.get("name", "?") for s in scenarios]
            typer.echo(
                f"Scenario '{scenario}' not found. Available: {', '.join(names)}",
                err=True,
            )
            raise typer.Exit(code=2)
    else:
        chosen = scenarios[0]

    scenario_name = chosen.get("name", "unnamed")
    login_persona = chosen.get("login_persona", "")
    if not login_persona:
        typer.echo(
            f"Scenario '{scenario_name}' has no login_persona. "
            "Set login_persona to the DSL persona ID to trial as.",
            err=True,
        )
        raise typer.Exit(code=2)

    # Resolve the LLM driver before any server/db work so a missing
    # key or CLI fails fast with onboarding guidance, not mid-trial.
    from dazzle.llm.driver import LLMDriverError, resolve_llm_driver

    manifest_driver: str | None = None
    manifest_path = project_dir / "dazzle.toml"
    if manifest_path.exists():
        try:
            manifest_driver = load_manifest(manifest_path).llm.driver
        except Exception:
            manifest_driver = None  # manifest problems surface later, in full
    try:
        resolved_driver = resolve_llm_driver(explicit=llm_driver, manifest_driver=manifest_driver)
    except LLMDriverError as exc:
        typer.echo(f"LLM driver: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    billing_note = (
        "Claude subscription via Claude Code CLI"
        if resolved_driver == "claude-cli"
        else "Anthropic API (metered)"
    )
    typer.echo(f"Trial scenario: {scenario_name} (as persona {login_persona})")
    typer.echo(f"LLM driver: {resolved_driver} ({billing_note})")

    # Optional per-scenario signing-token state (TR-51). "expired" seeds an
    # already-expired token so *_token_expired scenarios exercise the real
    # "Invalid or expired link" page instead of a fresh, signable token.
    signing_token_state = str(chosen.get("signing_token_state", "fresh"))
    if signing_token_state not in ("fresh", "expired"):
        typer.echo(
            f"Scenario '{scenario_name}': signing_token_state must be "
            f"'fresh' or 'expired', got {signing_token_state!r}.",
            err=True,
        )
        raise typer.Exit(code=2)
    if signing_token_state == "expired":
        typer.echo("Signing trial harness: seeding an EXPIRED token per scenario config.")

    # Optional per-scenario validator-reject arming (#1382). When true, the
    # seeded row's id is pre-armed in DAZZLE_QA_SIGNING_REJECT_IDS so the
    # project signing_validator rejects the signature — the *_validator_rejected
    # scenarios exercise the authority-check path instead of silently signing.
    signing_validator_reject = bool(chosen.get("signing_validator_reject", False))
    if signing_validator_reject and signing_token_state == "expired":
        typer.echo(
            f"Scenario '{scenario_name}': signing_validator_reject and "
            "signing_token_state='expired' are mutually exclusive (an expired "
            "token never reaches the validator).",
            err=True,
        )
        raise typer.Exit(code=2)
    if signing_validator_reject:
        typer.echo(
            "Signing trial harness: arming the project signing_validator to "
            "REJECT the seeded row per scenario config."
        )

    if fresh_db:
        _reset_db_for_trial(project_dir)

    # Load appspec to check for signable entities.  A load failure is
    # non-fatal for the trial itself — signing features are disabled when
    # appspec cannot be read.
    try:
        _trial_appspec = load_project_appspec(project_dir)
    except Exception as _appspec_exc:
        typer.echo(
            f"Note: could not load appspec for signing check ({_appspec_exc}); "
            "signing trial harness disabled for this run.",
            err=True,
        )
        _trial_appspec = None

    # Provision ephemeral cert + token secret when the app has signable entities.
    # The tmp_root scratch dir is always created so the finally block is
    # unconditional (avoids a NameError if the Playwright import fails).
    tmp_root = Path(tempfile.mkdtemp(prefix="dazzle-trial-signing-"))
    seed_ctx: SigningSeedContext | None = None
    if _trial_appspec is not None:
        seed_ctx = _provision_signing_env(
            _trial_appspec,
            tmp_root,
            project_name=getattr(_trial_appspec, "name", None) or project_dir.name,
            validator_reject=signing_validator_reject,
        )
    if seed_ctx is not None:
        # Inject signing env into this process so the server subprocess
        # (launched by launch_interaction_server) inherits them.
        os.environ.update(seed_ctx.env)
        typer.echo("Signing trial harness: ephemeral cert provisioned.")

    transcript_sink: dict[str, list[dict[str, Any]]] = {"friction": [], "verdict": []}
    started_at = time.monotonic()
    signing_action_sink: dict[str, Any] = {}
    signing_tools_list: list[Any] = []

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        shutil.rmtree(tmp_root, ignore_errors=True)
        typer.echo(
            "Playwright is not installed. Install with: pip install 'dazzle-dsl[e2e]' "
            "or pip install 'playwright>=1.40'",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    try:
        with launch_interaction_server(project_dir) as conn:
            site_url = conn.site_url
            try:
                test_secret_val = read_runtime_test_secret(project_dir) or ""
            except Exception:
                test_secret_val = ""

            if fresh_db:
                seed_ok = _seed_demo_data_for_trial(project_dir, site_url, test_secret_val)
                if not seed_ok:
                    # #1077: seed helper hard-aborted on blueprint drift.
                    # Without this guard the outer flow would continue and
                    # run the LLM agent against an empty DB, producing a
                    # misleading "I cannot recommend this app" verdict that
                    # is actually about data emptiness, not framework UX.
                    typer.echo(
                        "Trial aborted: blueprint drift detected. "
                        "Fix the blueprint and re-run (no LLM agent dispatched).",
                        err=True,
                    )
                    raise typer.Exit(code=3)

            # Seed one signing row per signable entity, then build the
            # persona-facing signing tools.  This happens after the demo-data
            # seed so the runtime API is fully responsive.
            if seed_ctx is not None and _trial_appspec is not None:
                try:
                    seeded = _seed_signable_rows(
                        app_spec=_trial_appspec,
                        base_url=site_url,
                        signatory_email="trial-signatory@example.com",
                        test_secret=test_secret_val,
                        token_state=signing_token_state,
                        signable_ids=seed_ctx.signable_ids,
                        validator_reject=seed_ctx.validator_reject,
                    )
                    seed_ctx = SigningSeedContext(
                        env=seed_ctx.env,
                        inbox_path=seed_ctx.inbox_path,
                        seeded_docs=seeded,
                        signable_ids=seed_ctx.signable_ids,
                        validator_reject=seed_ctx.validator_reject,
                    )
                    write_mock_inbox(tmp_root, seeded)
                    from dazzle.qa.signing_tools import build_signing_tools

                    signing_tools_list = build_signing_tools(
                        base_url=site_url,
                        inbox_path=seed_ctx.inbox_path,
                        seeded_docs=seeded,
                        action_sink=signing_action_sink,
                    )
                    typer.echo(
                        f"Signing trial harness: {len(seeded)} doc(s) seeded, "
                        f"{len(signing_tools_list)} signing tool(s) registered."
                    )
                except Exception as _seed_exc:
                    typer.echo(
                        f"Signing row seed failed ({_seed_exc}); "
                        "signing tools disabled for this run.",
                        err=True,
                    )
                    signing_tools_list = []

            async def _run_trial() -> tuple[Any, Any]:
                """Full async path: start browser, authenticate via POST +
                add_cookies, run the agent, tear down. PlaywrightObserver
                expects an async page, so this all has to live under the
                same event loop."""
                import httpx

                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=headless)
                    context = await browser.new_context()

                    # Authenticate via the /__test__/ endpoint (same
                    # protocol _authenticate_persona_on_context uses,
                    # but awaitable).
                    headers = {"X-Test-Secret": test_secret_val} if test_secret_val else {}
                    async with httpx.AsyncClient() as http:  # DZ-HTTP-NORETRY  one-shot CLI
                        resp = await http.post(
                            f"{site_url}/__test__/authenticate",
                            json={"role": login_persona, "username": login_persona},
                            headers=headers,
                            timeout=10,
                        )
                    if resp.status_code != 200:
                        typer.echo(
                            f"[auth] /__test__/authenticate returned {resp.status_code} "
                            f"(body: {resp.text[:200]!r}). Persona {login_persona!r} may "
                            f"not be a valid role, or test-mode may be disabled.",
                            err=True,
                        )
                        await browser.close()
                        raise typer.Exit(code=2)
                    token = resp.json().get("session_token") or resp.json().get("token") or ""
                    if token:
                        await context.add_cookies(
                            [{"name": "dazzle_session", "value": token, "url": site_url}]
                        )

                    page = await context.new_page()
                    observer_inner = PlaywrightObserver(
                        page,
                        include_screenshots=False,
                        capture_console=True,
                    )
                    executor_inner = PlaywrightExecutor(page)
                    agent_inner = DazzleAgent(
                        observer=observer_inner,
                        executor=executor_inner,
                        model=model,
                        # Native tool use needs the SDK; the claude-cli
                        # driver carries tools over the text protocol.
                        use_tool_calls=resolved_driver != "claude-cli",
                        llm_driver=resolved_driver,
                    )
                    mission_inner = build_trial_mission(
                        chosen,
                        base_url=site_url,
                        transcript_sink=transcript_sink,
                        signing_tools=signing_tools_list or None,
                    )
                    typer.echo(
                        f"Starting trial — up to {mission_inner.max_steps} steps, "
                        f"budget {mission_inner.token_budget:,} tokens"
                    )
                    t = await agent_inner.run(mission_inner)
                    await browser.close()
                    return t, mission_inner

            transcript, _mission = asyncio.run(_run_trial())

    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    duration_s = time.monotonic() - started_at

    friction = transcript_sink.get("friction", [])
    verdict_entries = transcript_sink.get("verdict", [])
    verdict = verdict_entries[0]["text"] if verdict_entries else ""

    # Fallback verdict synthesis — trials can run out of max_steps
    # before the LLM calls submit_verdict. The verdict is the most
    # important output, so we guarantee one via a single follow-up
    # LLM call that reads the friction observations and writes a
    # 1-paragraph verdict in the user's voice.
    if not verdict and friction:
        from dazzle.qa.trial_verdict_fallback import synthesize_verdict

        typer.echo("No verdict captured — synthesizing one from recorded friction…")
        verdict = synthesize_verdict(
            user_identity=chosen.get("user_identity", ""),
            business_context=chosen.get("business_context", ""),
            friction=friction,
            model=model,
            llm_driver=resolved_driver,
        )
        if verdict:
            verdict = f"(synthesized from recorded friction — agent ran out of steps)\n\n{verdict}"

    # Post-run signing verification — only when the persona actually
    # interacted with a signing link (detected via action_sink).
    signing_outcome: SigningOutcome | None = None
    if seed_ctx is not None and signing_action_sink.get("invoked"):
        try:
            db_reader = _build_db_reader(project_dir)
            signing_outcome = verify_signing_outcome(
                action_sink=signing_action_sink,
                seeded_docs=seed_ctx.seeded_docs,
                db_reader=db_reader,
                pdf_validator=_pyhanko_validator,
            )
        except Exception as _verify_exc:
            typer.echo(
                f"Signing outcome verification failed ({_verify_exc}); "
                "signing_outcomes block omitted from report.",
                err=True,
            )

    report = build_trial_report(
        scenario_name=scenario_name,
        user_identity=chosen.get("user_identity", ""),
        friction=friction,
        verdict=verdict,
        step_count=len(transcript.steps),
        duration_seconds=duration_s,
        tokens_used=transcript.tokens_used,
        outcome=transcript.outcome,
        signing_outcome=signing_outcome,
    )
    rendered = render_trial_report(report)

    if output is None:
        dev_docs = project_dir / "dev_docs"
        dev_docs.mkdir(exist_ok=True)
        stamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
        output = dev_docs / f"qa-trial-{scenario_name}-{stamp}.md"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(rendered, encoding="utf-8")

    # #1375: an agent-loop death (LLM billing/auth failure, observer
    # crash) must exit nonzero — autonomous consumers read the exit code
    # and would otherwise book an infrastructure failure as a clean PASS.
    # The report is still written above: it's the forensic record.
    abort_msg = trial_abort_message(
        transcript.outcome, transcript.error, step_count=len(transcript.steps)
    )
    if abort_msg is not None:
        typer.echo(f"\n{abort_msg}\nReport (forensics): {output}", err=True)
        raise typer.Exit(code=3)

    typer.echo(
        f"\nTrial complete. {len(friction)} friction observation(s) recorded. Report: {output}",
        file=sys.stdout,
    )
