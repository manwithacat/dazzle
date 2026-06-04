"""Unit tests for ``dazzle inspect rls`` (RLS tenancy Phase D, Task 3).

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

import pytest
from typer.testing import CliRunner

from dazzle.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]
TENANT_RLS = REPO_ROOT / "fixtures" / "tenant_rls"
SIMPLE_TASK = REPO_ROOT / "examples" / "simple_task"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_inspect_rls_in_help(runner: CliRunner) -> None:
    """`dazzle inspect --help` must list the new `rls` subcommand."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "rls" in result.stdout


def test_inspect_rls_lists_expected_policies_per_scoped_entity(runner: CliRunner) -> None:
    """Manifest mode lists fence + baseline / scope_* per tenant-scoped entity."""
    result = runner.invoke(app, ["inspect", "rls", "--project", str(TENANT_RLS), "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
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


def test_inspect_rls_human_output(runner: CliRunner) -> None:
    """Human output names the scoped entity + its policies."""
    result = runner.invoke(app, ["inspect", "rls", "--project", str(TENANT_RLS)])
    assert result.exit_code == 0, result.stdout
    assert "tenant_fence" in result.stdout
    assert "scope_select" in result.stdout
    assert "tenant_baseline" in result.stdout


def test_inspect_rls_non_tenant_app_is_empty_with_note(runner: CliRunner) -> None:
    """A non-tenant app yields an empty result + the no-row-level-tenancy note."""
    result = runner.invoke(app, ["inspect", "rls", "--project", str(SIMPLE_TASK), "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["entries"] == []
    assert payload["mismatches"] == []
    assert any("no row-level tenancy" in n.lower() for n in payload["notes"])
