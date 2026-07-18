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
    return {
        "title": "Closed-loop persona demo ops",
        "issue": 1627,
        "order": [
            "dazzle serve --project <app>  # writes .dazzle/runtime.json",
            "dazzle demo reset-and-load --project <app> -y",
            'POST /__test__/authenticate {"role": "<persona>"} with X-Test-Secret',
            "Open persona default_workspace (browser/networkidle for HTMX regions)",
        ],
        "rules": [
            "Never authenticate before reset — random UUIDs break assignment seeds.",
            "Domain User / assignment FKs must use STABLE_PERSONA_USER_IDS values.",
            "Do not invent seed UUIDs in the a1000000-… reserved range for non-personas.",
            "Canonical persona email domain is @demo.dazzle.local.",
            "Workspace HTML without a browser is skeleton only (hx-trigger=load).",
            "Metrics that filter current_user may read 0 while lists show rows (F10) — "
            "trust list regions + product_quality score until runtime is fixed.",
        ],
        "stable_persona_user_ids": dict(STABLE_PERSONA_USER_IDS),
        "persona_email_domain": PERSONA_EMAIL_DOMAIN,
        "persona_email_template": f"{{role}}@{PERSONA_EMAIL_DOMAIN}",
        "cli": "dazzle demo reset-and-load --project <app> -y",
        "mcp_read": "status(operation=demo_world, project_path=…)",
        "verify": "dazzle demo quality --project <app>  # persona_homes residual",
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


def find_demo_data_dir(project_root: Path) -> Path | None:
    """Same precedence as ``dazzle demo load``."""
    for candidate in (
        project_root / "demo_data",
        project_root / ".dazzle" / "demo_data",
        project_root / "dsl" / "seeds" / "demo_data",
    ):
        if candidate.is_dir():
            return candidate
    return None


def jsonl_dir_to_fixtures(
    data_dir: Path,
    *,
    entity_order: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert ``Entity.jsonl`` seed files into ``/__test__/seed`` FixtureData dicts.

    Each jsonl row becomes ``{id, entity, data}``. Row ``id`` is preferred;
    otherwise a synthetic fixture id is assigned. Files are ordered by
    ``entity_order`` when provided (parents first).
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


def _base_report(api_url: str, data_dir: Path, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": False,
        "api_url": api_url,
        "data_dir": str(data_dir),
        "fixture_count": len(fixtures),
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

    fixtures = jsonl_dir_to_fixtures(data_dir, entity_order=_entity_order(project_root))
    if not fixtures:
        return _fail(f"No seed rows found under {data_dir}", data_dir=str(data_dir))

    report = _base_report(api_url, data_dir, fixtures)
    if not _http_reset_and_seed(
        report, api_url=api_url, secret=secret, fixtures=fixtures, timeout=timeout
    ):
        return report

    if verify_persona_homes:
        _attach_persona_homes(report, project_root)
    else:
        report["ok"] = True
    return report


def _clip(text: str, limit: int = 400) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"
