"""Unit tests for ``dazzle inspect rls`` (RLS tenancy Phase D, Task 3).

That ``rls`` is listed in ``dazzle inspect --help`` is a row of
``test_cli_inspect.py::test_inspect_manifest_only_output``.

Manifest-only paths only — the default mode derives the expected RLS policy
set from the linked AppSpec with no DB. The ``--runtime`` path needs a live
PostgreSQL connection (covered by the Phase D integration tests), so it is not
exercised here.

The shared-schema fixture ``fixtures/tenant_rls`` carries:
  - ``Project`` — a SCOPED entity (per-verb ``scope:`` rules) → fence +
    ``scope_select`` (read+list union) + ``scope_update``; no baseline.
  - ``Task`` / ``Member`` — tenant-flat scoped entities → fence + baseline.
  - ``Workspace`` — the tenant root (not tenant-scoped) → no policies.

A non-tenant app (``examples/simple_task``) → empty result + the
"no row-level tenancy" note.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.helpers.cli import run_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
TENANT_RLS = REPO_ROOT / "fixtures" / "tenant_rls"
SIMPLE_TASK = REPO_ROOT / "examples" / "simple_task"


def test_inspect_rls_lists_expected_policies_per_scoped_entity() -> None:
    """Manifest mode lists fence + baseline / scope_* per tenant-scoped entity."""
    payload = json.loads(run_cli(["inspect", "rls", "--project", TENANT_RLS, "--json"]))
    assert payload["ext_point"] == "rls"

    # Build (entity, name) -> entry index.
    by_key = {(e["detail"].split()[0], e["name"]): e for e in payload["entries"]}

    # Project (scoped): fence (restrictive, framework) + scope_select +
    # scope_update (permissive, scope-rule). NO baseline, NO scope_insert /
    # scope_delete (those verbs have no scope rule).
    fence = by_key[("Project", "tenant_fence")]
    assert fence["source"] == "framework"
    assert "ALL" in fence["detail"]
    assert "RESTRICTIVE" in fence["detail"]

    sel = by_key[("Project", "scope_select")]
    assert sel["source"] == "scope-rule"
    assert "SELECT" in sel["detail"]
    assert "PERMISSIVE" in sel["detail"]

    upd = by_key[("Project", "scope_update")]
    assert upd["source"] == "scope-rule"
    assert "UPDATE" in upd["detail"]

    assert ("Project", "tenant_baseline") not in by_key
    assert ("Project", "scope_insert") not in by_key
    assert ("Project", "scope_delete") not in by_key

    # Task (tenant-flat): fence + baseline only.
    task_fence = by_key[("Task", "tenant_fence")]
    assert task_fence["source"] == "framework"
    assert "RESTRICTIVE" in task_fence["detail"]

    task_baseline = by_key[("Task", "tenant_baseline")]
    assert task_baseline["source"] == "framework"
    assert "PERMISSIVE" in task_baseline["detail"]
    assert "ALL" in task_baseline["detail"]

    # Member (tenant-flat): fence + baseline.
    assert ("Member", "tenant_fence") in by_key
    assert ("Member", "tenant_baseline") in by_key

    # Workspace is the tenant root (not tenant-scoped) → no policies.
    assert not any(e["detail"].startswith("Workspace") for e in payload["entries"])
    assert any("shared_schema" in n and "topology" in n for n in payload["notes"]), payload["notes"]


def test_inspect_rls_human_output() -> None:
    """Human output names the scoped entity + its policies."""
    out = run_cli(["inspect", "rls", "--project", TENANT_RLS])
    for policy in ("tenant_fence", "scope_select", "tenant_baseline"):
        assert policy in out


def test_inspect_rls_non_tenant_app_is_empty_with_note() -> None:
    """A non-tenant app yields an empty result + the no-row-level-tenancy note."""
    payload = json.loads(run_cli(["inspect", "rls", "--project", SIMPLE_TASK, "--json"]))
    assert payload["entries"] == []
    assert payload["mismatches"] == []
    assert any("no row-level tenancy" in n.lower() for n in payload["notes"])
