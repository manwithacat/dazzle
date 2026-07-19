"""Closed-loop demo seed via ``/__test__/*`` (#1627).

Tribal knowledge that previously lived only in agent folklore:

1. Prefer ``/__test__/reset`` then ``/__test__/seed`` (FixtureData shape)
   over ``dazzle demo load`` entity POSTs (CSRF / port mismatch).
2. Authenticate with ``role=`` **after** reset so principals use
   ``STABLE_PERSONA_USER_IDS`` (dual-identity trap if auth first).
3. Seed rows that bind to ``current_user`` must use those stable UUIDs
   (``a1000000-…``), never random auth ids.
4. Persona emails for stable principals are ``{role}@demo.dazzle.local``.

This module is the deterministic write-side companion to MCP
``status(demo_world)`` (#1629 read plane).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.identity import spec_display_id
from dazzle.core.strings import to_api_plural
from dazzle.demo_data.loader import find_seed_files, read_seed_file, topological_sort_entities
from dazzle.product_quality.persona_homes import (
    STABLE_PERSONA_USER_IDS,
    score_persona_homes,
)

logger = logging.getLogger(__name__)

# Canonical email domain for test-mode persona principals (#1627).
PERSONA_EMAIL_DOMAIN = "demo.dazzle.local"


def demo_ops_playbook() -> dict[str, Any]:
    """Agent-readable tribal knowledge pack (no project needed)."""
    stable_ids = sorted(STABLE_PERSONA_USER_IDS.keys())
    return {
        "title": "Closed-loop persona demo ops",
        "issue": 1627,
        "related_issues": [1627, 1629, 1630],
        "order": [
            "dazzle serve --project <app>  # writes .dazzle/runtime.json",
            "Re-read .dazzle/runtime.json after every serve (ports may change)",
            "dazzle demo reset-and-load --project <app> -y",
            'POST /__test__/authenticate {"role": "<persona>"} with X-Test-Secret',
            "Open persona default_workspace (browser/networkidle for HTMX regions)",
        ],
        "rules": [
            "Never authenticate before reset — random UUIDs break assignment seeds.",
            "Persona *ids* for assignment-aware demo must be STABLE map keys "
            f"({', '.join(stable_ids[:8])}, …) — use human titles for display names "
            "(#1630: promoter→requester, booker→approver).",
            "Domain User / assignment FKs must use STABLE_PERSONA_USER_IDS values.",
            "Do not invent seed UUIDs in the a1000000-… reserved range for non-personas.",
            "User.jsonl rows at STABLE ids are auto-skipped by reset-and-load "
            "(reset already mirrors those principals) — #1630.",
            "Canonical persona email domain is @demo.dazzle.local.",
            "Workspace HTML without a browser is skeleton only (hx-trigger=load).",
            "Metrics that filter current_user may read 0 while lists show rows (F10) — "
            "trust list regions + product_quality score until runtime is fixed.",
            "After renaming personas, re-check every `as:` / permit role token — "
            "static residual can be 0 while a desk is empty (#1630).",
            "Same-field region OR is OK (`status = held or status = confirmed` → "
            "status__in); mixed-field OR fail-closed — split regions (#1630).",
            "Residual 0 is necessary not sufficient — check live_desk / stills "
            "(counter-prior empty_desk_false_green).",
        ],
        "stable_persona_ids": stable_ids,
        "stable_persona_user_ids": dict(STABLE_PERSONA_USER_IDS),
        "persona_email_domain": PERSONA_EMAIL_DOMAIN,
        "persona_email_template": f"{{role}}@{PERSONA_EMAIL_DOMAIN}",
        "cli": "dazzle demo reset-and-load --project <app> -y",
        "mcp_read": "status(operation=demo_world, project_path=…)",
        "verify": "dazzle demo quality --project <app>  # persona_homes residual",
        # Always-on KG entry points (inference layer; ADR-0002 reads)
        "knowledge_concepts": [
            "demo_identity",
            "stable_personas",
            "workspace_region_filters",
            "empty_desk_false_green",
            "first_principles_demo",
            "bootstrap_pollution",
            "version_cognition",
        ],
        "counter_priors": [
            "empty_desk_false_green",
            "free_persona_id_not_stable",
            "workspace_filter_or_silent_empty",
            "reseed_stable_users",
            "faker_seed_over_story_spine",
            "bootstrap_pollution",
            "metric_current_user_lie",
            "version_pin_distrust",
        ],
        "workflow": "first_principles_demo",
        "knowledge_hint": (
            "knowledge(concept='demo_identity'|'bootstrap_pollution'|'version_cognition') · "
            "counter_priors empty_desk_false_green / metric_current_user_lie / "
            "bootstrap_pollution · workflow first_principles_demo · "
            "status.mcp version_cognition"
        ),
    }


def resolve_serve_binding(project_root: Path) -> dict[str, Any]:
    """Resolve live serve URL + test secret from runtime.json / env."""
    project_root = project_root.resolve()
    runtime_path = project_root / ".dazzle" / "runtime.json"
    runtime: dict[str, Any] = {}
    if runtime_path.is_file():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            runtime = {}

    api_url = (
        runtime.get("api_url")
        or os.environ.get("DAZZLE_API_URL")
        or (f"http://localhost:{runtime['api_port']}" if runtime.get("api_port") else None)
        or "http://localhost:8000"
    )
    secret = runtime.get("test_secret") or os.environ.get("DAZZLE_TEST_SECRET") or ""
    return {
        "project_root": str(project_root),
        "runtime_file": str(runtime_path) if runtime_path.is_file() else None,
        "api_url": str(api_url).rstrip("/"),
        "ui_url": runtime.get("ui_url"),
        "test_secret_present": bool(isinstance(secret, str) and secret),
        "test_secret": secret if isinstance(secret, str) else "",
        "database_url_present": bool(runtime.get("database_url")),
    }


def _dir_has_seed_files(path: Path) -> bool:
    """True when *path* holds loadable Entity.jsonl / Entity.csv (not only blueprint)."""
    if not path.is_dir():
        return False
    return any(path.glob("*.jsonl")) or any(path.glob("*.csv"))


def find_demo_data_dir(project_root: Path) -> Path | None:
    """Resolve seed directory for closed-loop ``reset-and-load``.

    Prefer **authored story seeds** (STABLE assignment UUIDs) over generated
    faker dumps under ``.dazzle/demo_data/`` (#1626 recapture). Faker CSVs use
    random User ids that 400 on seed and leave persona homes empty.

    Precedence:
    1. ``dsl/seeds/demo_data/`` — assignment-aware story spine
    2. ``demo_data/`` — project-root authored seeds
    3. ``.dazzle/demo_data/`` — generated (``dazzle demo generate``) last resort

    Directories that only contain ``blueprint.json`` (no entity rows) are
    skipped so we fall through to generated data when present.
    """
    for candidate in (
        project_root / "dsl" / "seeds" / "demo_data",
        project_root / "demo_data",
        project_root / ".dazzle" / "demo_data",
    ):
        if _dir_has_seed_files(candidate):
            return candidate
    return None


def _is_stable_persona_user_fixture(entity_name: str, row: dict[str, Any]) -> bool:
    """True when this domain User seed is redundant with reset's auth mirror.

    ``/__test__/reset`` mirrors auth principals into domain User when the entity
    is mirrorable (scalar-only required fields). Re-seeding those 400s with
    \"already exists\" (#1630).

    Multi-tenant apps require ``tenant_id`` (a ref) on User — the mirror cannot
    placeholder refs, so domain User stays empty after reset. Keep those seed
    rows so ``submitted_by`` / assignment FKs resolve (#1626 invoice desks).
    """
    if entity_name != "User":
        return False
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id:
        return False
    if row_id not in STABLE_PERSONA_USER_IDS.values():
        return False
    # Tenant-scoped User seeds are load-bearing; do not skip.
    if row.get("tenant_id"):
        return False
    return True


def jsonl_dir_to_fixtures(
    data_dir: Path,
    *,
    entity_order: list[str] | None = None,
    skip_stable_users: bool = True,
) -> list[dict[str, Any]]:
    """Convert ``Entity.jsonl`` seed files into ``/__test__/seed`` FixtureData dicts.

    Each jsonl row becomes ``{id, entity, data}``. Row ``id`` is preferred;
    otherwise a synthetic fixture id is assigned. Files are ordered by
    ``entity_order`` when provided (parents first).

    When *skip_stable_users* is True (default), domain ``User`` rows whose
    ``id`` is in :data:`STABLE_PERSONA_USER_IDS` are omitted — reset already
    provisioned them (#1630 User collision).
    """
    seed_files = find_seed_files(data_dir)
    if not seed_files:
        return []

    if entity_order:
        ordered_names = [n for n in entity_order if n in seed_files]
        ordered_names.extend(sorted(n for n in seed_files if n not in entity_order))
    else:
        ordered_names = sorted(seed_files.keys())

    fixtures: list[dict[str, Any]] = []
    for entity_name in ordered_names:
        path = seed_files[entity_name]
        try:
            rows = read_seed_file(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("skip seed file %s: %s", path, exc)
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if skip_stable_users and _is_stable_persona_user_fixture(entity_name, row):
                continue
            row_id = row.get("id")
            fid = str(row_id) if row_id else f"{entity_name}-{i + 1}"
            fixtures.append(
                {
                    "id": fid,
                    "entity": entity_name,
                    "data": dict(row),
                }
            )
    return fixtures


def _fail(error: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": error, "playbook": demo_ops_playbook()}
    out.update(extra)
    return out


def _entity_order(project_root: Path) -> list[str] | None:
    try:
        appspec = load_project_appspec(project_root)
        return topological_sort_entities(appspec.domain.entities)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        logger.debug("entity order fallback: %s", exc)
        return None


def _base_report(
    api_url: str,
    data_dir: Path,
    fixtures: list[dict[str, Any]],
    *,
    skipped_stable_users: int = 0,
) -> dict[str, Any]:
    return {
        "ok": False,
        "api_url": api_url,
        "data_dir": str(data_dir),
        "fixture_count": len(fixtures),
        "skipped_stable_user_fixtures": skipped_stable_users,
        "entities": sorted({f["entity"] for f in fixtures}),
        "steps": [],
        "playbook": demo_ops_playbook(),
        "stable_persona_user_ids": dict(STABLE_PERSONA_USER_IDS),
        "persona_email_domain": PERSONA_EMAIL_DOMAIN,
        "next": (
            f"POST {api_url}/__test__/authenticate "
            f'{{"role":"<persona>"}} with X-Test-Secret — *after* this command.'
        ),
    }


def _http_reset_and_seed(
    report: dict[str, Any],
    *,
    api_url: str,
    secret: str,
    fixtures: list[dict[str, Any]],
    timeout: float,
) -> bool:
    """Mutate report with HTTP steps. Return True if seed succeeded."""
    headers = {"X-Test-Secret": secret, "Content-Type": "application/json"}
    try:
        with httpx.Client(base_url=api_url, timeout=timeout, headers=headers) as client:
            reset_resp = client.post("/__test__/reset")
            report["steps"].append(_step("reset", reset_resp))
            if reset_resp.status_code != 200:
                report["error"] = f"/__test__/reset failed: HTTP {reset_resp.status_code}"
                return False

            seed_resp = client.post("/__test__/seed", json={"fixtures": fixtures})
            report["steps"].append(_step("seed", seed_resp))
            if seed_resp.status_code != 200:
                report["error"] = f"/__test__/seed failed: HTTP {seed_resp.status_code}"
                return False
            report["created_count"] = _created_count(seed_resp)
    except httpx.HTTPError as exc:
        report["error"] = f"HTTP error talking to {api_url}: {exc}"
        return False
    return True


def _step(name: str, resp: httpx.Response) -> dict[str, Any]:
    return {
        "step": name,
        "status_code": resp.status_code,
        "ok": resp.status_code == 200,
        "body": _clip(resp.text),
    }


def _created_count(seed_resp: httpx.Response) -> int | None:
    try:
        created = seed_resp.json().get("created", {})
        return len(created) if isinstance(created, dict) else 0
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return None


def _attach_persona_homes(report: dict[str, Any], project_root: Path) -> None:
    try:
        homes = score_persona_homes(project_root)
        residual = sum(1 for h in homes if h.residual)
        report["persona_homes_residual"] = residual
        report["persona_homes"] = [
            {
                "persona": h.persona,
                "default_workspace": h.default_workspace,
                "residual": h.residual,
                "reasons": h.residual_reasons,
            }
            for h in homes
        ]
        report["ok"] = residual == 0
        if residual:
            report["warning"] = (
                f"persona_homes residual={residual} — seed rows may not match "
                "STABLE ids / current_user filters for some desks."
            )
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        report["persona_homes_residual"] = None
        report["persona_homes_error"] = str(exc)[:200]
        report["ok"] = True  # seed HTTP succeeded


def _prepare_fixtures(
    project_root: Path, data_dir: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (all, seedable, skipped_stable_count)."""
    entity_order = _entity_order(project_root)
    all_fixtures = jsonl_dir_to_fixtures(
        data_dir, entity_order=entity_order, skip_stable_users=False
    )
    fixtures = [
        f
        for f in all_fixtures
        if not _is_stable_persona_user_fixture(f["entity"], f.get("data") or {})
    ]
    return all_fixtures, fixtures, len(all_fixtures) - len(fixtures)


def _reset_only(report: dict[str, Any], *, api_url: str, secret: str, timeout: float) -> bool:
    headers = {"X-Test-Secret": secret, "Content-Type": "application/json"}
    try:
        with httpx.Client(base_url=api_url, timeout=timeout, headers=headers) as client:
            reset_resp = client.post("/__test__/reset")
            report["steps"].append(_step("reset", reset_resp))
            if reset_resp.status_code != 200:
                report["error"] = f"/__test__/reset failed: HTTP {reset_resp.status_code}"
                return False
    except httpx.HTTPError as exc:
        report["error"] = f"HTTP error talking to {api_url}: {exc}"
        return False
    return True


def _finalize_verify(
    report: dict[str, Any],
    project_root: Path,
    *,
    api_url: str,
    secret: str,
    timeout: float,
    verify_persona_homes: bool,
) -> None:
    if not verify_persona_homes:
        report["ok"] = True
        return
    _attach_persona_homes(report, project_root)
    if report.get("ok"):
        try:
            _attach_live_desk_residual(
                report, project_root, api_url=api_url, secret=secret, timeout=timeout
            )
        except Exception as exc:  # noqa: BLE001 — never fail seed on live probe infra
            report["live_desk_error"] = str(exc)[:200]


def reset_and_load(
    project_root: Path,
    *,
    base_url: str | None = None,
    test_secret: str | None = None,
    data_dir: Path | None = None,
    verify_persona_homes: bool = True,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST ``/__test__/reset`` then ``/__test__/seed`` with project jsonl seeds.

    Returns a structured report for CLI/MCP. Does **not** authenticate a
    session — agents must call authenticate with ``role=`` after this.
    """
    project_root = project_root.resolve()
    binding = resolve_serve_binding(project_root)
    api_url = (base_url or binding["api_url"]).rstrip("/")
    secret = test_secret if test_secret is not None else binding["test_secret"]
    public_binding = {k: v for k, v in binding.items() if k != "test_secret"}

    if not secret:
        return _fail(
            "No test_secret: start with `dazzle serve` (writes "
            ".dazzle/runtime.json) or set DAZZLE_TEST_SECRET.",
            binding=public_binding,
        )

    if data_dir is None:
        data_dir = find_demo_data_dir(project_root)
    if data_dir is None or not data_dir.is_dir():
        return _fail(
            "No demo data directory (demo_data/, .dazzle/demo_data/, or dsl/seeds/demo_data/).",
            binding=public_binding,
        )

    all_fixtures, fixtures, skipped_stable = _prepare_fixtures(project_root, data_dir)
    if not all_fixtures:
        return _fail(f"No seed rows found under {data_dir}", data_dir=str(data_dir))

    report = _base_report(api_url, data_dir, fixtures, skipped_stable_users=skipped_stable)
    if not fixtures:
        if not _reset_only(report, api_url=api_url, secret=secret, timeout=timeout):
            return report
        report["note"] = "Only STABLE User fixtures present; skipped after reset mirror."
        _finalize_verify(
            report,
            project_root,
            api_url=api_url,
            secret=secret,
            timeout=timeout,
            verify_persona_homes=verify_persona_homes,
        )
        return report

    if not _http_reset_and_seed(
        report, api_url=api_url, secret=secret, fixtures=fixtures, timeout=timeout
    ):
        return report

    _finalize_verify(
        report,
        project_root,
        api_url=api_url,
        secret=secret,
        timeout=timeout,
        verify_persona_homes=verify_persona_homes,
    )
    return report


def _probe_one_persona(client: httpx.Client, persona: Any, appspec: Any) -> dict[str, Any] | None:
    pid = spec_display_id(persona, default=None, prefer="id")
    dws = getattr(persona, "default_workspace", None)
    if not pid or not dws or pid in ("admin", "platform_admin", "superuser"):
        return None
    entities = _default_workspace_list_entities(appspec, str(dws))
    if not entities:
        return None
    auth = client.post("/__test__/authenticate", json={"role": str(pid)})
    if auth.status_code != 200:
        return {
            "persona": str(pid),
            "ok": False,
            "error": f"authenticate HTTP {auth.status_code}",
        }
    # Try list/queue sources until one has rows — first region may be an
    # empty satellite (e.g. PaymentAttempt) while Invoice is populated.
    fail_entry: dict[str, Any] | None = None
    for entity_name in entities:
        list_resp = client.get(f"/{to_api_plural(entity_name)}")
        total = _list_total(list_resp)
        ok = list_resp.status_code == 200 and (total is None or total > 0)
        entry: dict[str, Any] = {
            "persona": str(pid),
            "entity": entity_name,
            "status_code": list_resp.status_code,
            "total": total,
            "ok": ok,
        }
        if ok:
            return entry
        if fail_entry is None:
            entry["hint"] = (
                "Empty live list under authenticated persona while "
                "static residual may still be 0 — check `as:` role "
                "tokens and permits match declared personas (#1630). "
                "Tried list/queue sources on the default workspace; "
                "satellite entities without story seeds are not residual."
            )
            fail_entry = entry
    return fail_entry


def _attach_live_desk_residual(
    report: dict[str, Any],
    project_root: Path,
    *,
    api_url: str,
    secret: str,
    timeout: float,
) -> None:
    """Auth as each persona with a default workspace; flag empty list APIs (#1630).

    Complements static persona_homes: residual 0 with empty live desks is the
    scope ``as:`` drift failure mode.
    """
    try:
        appspec = load_project_appspec(project_root)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        return

    live: list[dict[str, Any]] = []
    headers_base = {"X-Test-Secret": secret, "Content-Type": "application/json"}
    try:
        with httpx.Client(base_url=api_url, timeout=timeout, headers=headers_base) as client:
            for persona in appspec.personas or []:
                entry = _probe_one_persona(client, persona, appspec)
                if entry is not None:
                    live.append(entry)
    except httpx.HTTPError as exc:
        report["live_desk_error"] = str(exc)[:200]
        return

    report["live_desk"] = live
    empty = [e for e in live if not e.get("ok")]
    report["live_desk_residual"] = len(empty)
    if empty:
        report["ok"] = False
        prior = report.get("warning")
        prefix = f"{prior} " if isinstance(prior, str) and prior else ""
        report["warning"] = prefix + (
            f"live_desk residual={len(empty)} — desks empty under session "
            f"for {[e['persona'] for e in empty]} (#1630)."
        )


def _is_listish_display(display: str) -> bool:
    d = display.lower()
    return d in ("list", "queue") or "list" in d or "queue" in d


def _is_aggregate_display(display: str) -> bool:
    d = display.lower()
    return "metric" in d or "chart" in d or "funnel" in d


def _default_workspace_list_entities(appspec: Any, workspace_name: str) -> list[str]:
    """Ordered list/queue sources on a workspace (job densest first).

    Prefer ``list`` / ``queue`` display regions over charts. Metrics-only
    regions are skipped. Returns unique entity names so live_desk can try
    each until one has rows (audit desks with empty PaymentAttempt +
    populated Invoice).
    """
    preferred: list[str] = []
    other: list[str] = []
    for ws in appspec.workspaces or []:
        if str(spec_display_id(ws, default=None)) != workspace_name:
            continue
        for region in getattr(ws, "regions", None) or []:
            display = str(getattr(region, "display", "") or "")
            if _is_aggregate_display(display):
                continue
            src = getattr(region, "source", None)
            if not src:
                continue
            src_s = str(src)
            bucket = preferred if _is_listish_display(display) else other
            if src_s not in preferred and src_s not in other:
                bucket.append(src_s)
    return preferred + other


def _default_workspace_list_entity(appspec: Any, workspace_name: str) -> str | None:
    """First list/queue source for a workspace (compat helper)."""
    entities = _default_workspace_list_entities(appspec, workspace_name)
    return entities[0] if entities else None


def _list_total(resp: httpx.Response) -> int | None:
    if resp.status_code != 200:
        return 0
    try:
        data = resp.json()
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if "total" in data:
            try:
                return int(data["total"])
            except (TypeError, ValueError):
                pass
        for key in ("items", "results", "data", "rows"):
            val = data.get(key)
            if isinstance(val, list):
                return len(val)
    return None


def _clip(text: str, limit: int = 400) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"
