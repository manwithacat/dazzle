# Feedback Loop System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the human→agent feedback loop with MCP tool, CLI commands, knowledge graph, and bootstrap integration.

**Architecture:** The linker generates a third synthetic EDIT surface for FeedbackReport. A shared impl module (`feedback_impl.py`) provides list/get/triage/resolve/delete/stats functions that call the running server's CRUD endpoints via httpx. Both the MCP handler and CLI are thin wrappers over this impl. The knowledge graph gets feedback concepts; bootstrap recommends the widget on auth-enabled apps.

**Tech Stack:** Python 3.12, Typer (CLI), httpx (HTTP client), TOML (semantics KB)

**Spec:** `docs/superpowers/specs/2026-03-25-feedback-loop-system-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/core/linker.py` | Add `_build_feedback_edit_surface()`, add `triaged→resolved` transition |
| `src/dazzle/cli/feedback.py` | Typer command group: list, get, triage, resolve, delete, stats |
| `src/dazzle/cli/feedback_impl.py` | Shared impl functions (httpx calls to CRUD endpoints) |
| `src/dazzle/mcp/server/handlers/feedback.py` | MCP handler: list, get, triage, resolve operations |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register feedback handler |
| `src/dazzle/mcp/server/tools_consolidated.py` | Register feedback tool definition |
| `src/dazzle/mcp/semantics_kb/feedback.toml` | Knowledge graph concepts + workflows |
| `src/dazzle/mcp/semantics_kb/__init__.py` | Add `feedback.toml` to `TOML_FILES` |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Bump `SEED_SCHEMA_VERSION` |
| `src/dazzle/mcp/server/handlers/bootstrap.py` | Add feedback_widget recommendation step |
| `src/dazzle/cli/__init__.py` | Register feedback command group |
| `src/dazzle_back/runtime/csrf.py` | Add `/feedbackreports/` prefix exemption |
| `tests/unit/test_feedback_widget.py` | EDIT surface + state machine tests |
| `tests/integration/test_runtime_e2e.py` | PUT, DELETE, lifecycle E2E tests |

---

### Task 1: EDIT Surface + State Machine Shortcut

**Files:**
- Modify: `src/dazzle/core/linker.py`
- Test: `tests/unit/test_feedback_widget.py`

- [ ] **Step 1: Write failing tests for EDIT surface and triaged→resolved transition**

Add to `TestFeedbackWidgetSurfaces` in `tests/unit/test_feedback_widget.py`:

```python
def test_edit_surface_generated(self) -> None:
    """feedback_widget: enabled produces a feedback_edit surface."""
    app = self._link(self._DSL_ENABLED)
    surface_names = {s.name for s in app.surfaces}
    assert "feedback_edit" in surface_names

def test_edit_surface_mode_and_entity(self) -> None:
    """feedback_edit surface is mode=edit referencing FeedbackReport."""
    from dazzle.core.ir.surfaces import SurfaceMode

    app = self._link(self._DSL_ENABLED)
    edit = next(s for s in app.surfaces if s.name == "feedback_edit")
    assert edit.mode == SurfaceMode.EDIT
    assert edit.entity_ref == "FeedbackReport"

def test_edit_surface_has_editable_fields(self) -> None:
    """feedback_edit surface has triage/resolution fields."""
    app = self._link(self._DSL_ENABLED)
    edit = next(s for s in app.surfaces if s.name == "feedback_edit")
    assert len(edit.sections) == 1
    field_names = {e.field_name for e in edit.sections[0].elements}
    assert "status" in field_names
    assert "assigned_to" in field_names
    assert "agent_notes" in field_names

def test_edit_surface_has_admin_access(self) -> None:
    """feedback_edit surface restricted to admin/super_admin."""
    app = self._link(self._DSL_ENABLED)
    edit = next(s for s in app.surfaces if s.name == "feedback_edit")
    assert edit.access is not None
    assert edit.access.require_auth is True
    assert "admin" in edit.access.allow_personas
```

Add to `TestFeedbackReportAutoEntity`:

```python
def test_triaged_to_resolved_shortcut(self) -> None:
    """State machine allows triaged → resolved (agent shortcut)."""
    dsl = (
        'module test\napp test "Test"\n\n'
        'entity User "User":\n'
        "  id: uuid pk\n"
        "  name: str(100)\n\n"
        "feedback_widget: enabled\n"
    )
    app = self._link(dsl)
    entity = app.get_entity("FeedbackReport")
    assert entity is not None
    assert entity.state_machine is not None
    transition_strs = {
        f"{t.from_state} -> {t.to_state}" for t in entity.state_machine.transitions
    }
    assert "triaged -> resolved" in transition_strs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_feedback_widget.py::TestFeedbackWidgetSurfaces::test_edit_surface_generated tests/unit/test_feedback_widget.py::TestFeedbackReportAutoEntity::test_triaged_to_resolved_shortcut -v`
Expected: FAIL (no `feedback_edit` surface, no `triaged→resolved` transition)

- [ ] **Step 3: Implement EDIT surface builder and state machine change**

In `src/dazzle/core/linker.py`, add after `_build_feedback_admin_surface()`:

```python
def _build_feedback_edit_surface() -> ir.SurfaceSpec:
    """Build a headless EDIT surface for FeedbackReport (triage/resolve).

    Admin-only. Exposes status transitions + agent triage fields via
    PUT /feedbackreports/{id}.
    """
    elements = [
        ir.SurfaceElement(field_name=name, label=label)
        for name, label in [
            ("status", "Status"),
            ("assigned_to", "Assigned To"),
            ("agent_notes", "Agent Notes"),
            ("agent_classification", "Classification"),
            ("related_entity", "Related Entity"),
            ("related_story", "Related Story"),
        ]
    ]
    return ir.SurfaceSpec(
        name="feedback_edit",
        title="Edit Feedback Report",
        entity_ref="FeedbackReport",
        mode=ir.SurfaceMode.EDIT,
        sections=[ir.SurfaceSection(name="main", title="Triage", elements=elements)],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin", "super_admin"],
        ),
    )
```

Update the surface generation line in `build_appspec()` (~line 120):

```python
surfaces = [*surfaces, _build_feedback_create_surface(), _build_feedback_admin_surface(), _build_feedback_edit_surface()]
```

Add the `triaged→resolved` transition in `_build_feedback_report_entity()` (after the existing `triaged → duplicate` line):

```python
ir.StateTransition(from_state="triaged", to_state="resolved"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_feedback_widget.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/linker.py tests/unit/test_feedback_widget.py
git commit -m "feat(feedback): add EDIT surface + triaged→resolved shortcut (#685)"
```

---

### Task 2: CSRF Prefix Exemption + E2E Tests for PUT/DELETE

**Files:**
- Modify: `src/dazzle_back/runtime/csrf.py`
- Modify: `tests/integration/test_runtime_e2e.py`

- [ ] **Step 1: Add CSRF prefix exemption**

In `src/dazzle_back/runtime/csrf.py`, add `"/feedbackreports/"` to `exempt_path_prefixes`:

```python
exempt_path_prefixes: list[str] = field(
    default_factory=lambda: [
        "/webhooks/",
        "/api/v1/webhooks/",
        "/__test__/",
        "/dazzle/dev/",
        "/auth/",
        "/feedbackreports/",
    ]
)
```

- [ ] **Step 2: Add E2E tests for PUT and DELETE**

Add to `TestFeedbackWidget` in `tests/integration/test_runtime_e2e.py`:

```python
@pytest.mark.e2e
def test_put_updates_feedback_status(self, simple_task_server: DazzleLocalServerManager) -> None:
    """PUT /feedbackreports/{id} transitions status via state machine."""
    api = simple_task_server.api_url

    # Create a feedback report
    resp = _request_with_retry(
        "POST", f"{api}/feedbackreports",
        json={
            "category": "bug",
            "severity": "minor",
            "description": "PUT test feedback",
            "reported_by": "e2e@example.com",
        },
    )
    assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
    report_id = resp.json()["id"]

    # Triage it (new → triaged)
    resp = _request_with_retry(
        "PUT", f"{api}/feedbackreports/{report_id}",
        json={"status": "triaged", "agent_notes": "Looks like a CSS issue"},
    )
    assert resp.status_code == 200, f"PUT failed: {resp.text}"
    assert resp.json()["status"] == "triaged"

@pytest.mark.e2e
def test_delete_removes_feedback(self, simple_task_server: DazzleLocalServerManager) -> None:
    """DELETE /feedbackreports/{id} removes the record."""
    api = simple_task_server.api_url

    # Create a feedback report
    resp = _request_with_retry(
        "POST", f"{api}/feedbackreports",
        json={
            "category": "ux",
            "severity": "minor",
            "description": "Delete test feedback",
            "reported_by": "e2e@example.com",
        },
    )
    assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
    report_id = resp.json()["id"]

    # Delete it
    resp = _request_with_retry("DELETE", f"{api}/feedbackreports/{report_id}")
    assert resp.status_code in (200, 204), f"Delete failed: {resp.text}"

    # Verify it's gone
    resp = _request_with_retry("GET", f"{api}/feedbackreports/{report_id}")
    assert resp.status_code == 404

@pytest.mark.e2e
def test_triage_resolve_lifecycle(self, simple_task_server: DazzleLocalServerManager) -> None:
    """Full lifecycle: create → triage → resolve."""
    api = simple_task_server.api_url

    # Create
    resp = _request_with_retry(
        "POST", f"{api}/feedbackreports",
        json={
            "category": "bug",
            "severity": "annoying",
            "description": "Lifecycle test feedback",
            "reported_by": "e2e@example.com",
        },
    )
    assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
    report_id = resp.json()["id"]

    # Triage (new → triaged)
    resp = _request_with_retry(
        "PUT", f"{api}/feedbackreports/{report_id}",
        json={"status": "triaged"},
    )
    assert resp.json()["status"] == "triaged"

    # Resolve (triaged → resolved, shortcut)
    resp = _request_with_retry(
        "PUT", f"{api}/feedbackreports/{report_id}",
        json={"status": "resolved", "agent_notes": "Fixed in commit abc123"},
    )
    assert resp.status_code == 200, f"Resolve failed: {resp.text}"
    assert resp.json()["status"] == "resolved"
```

- [ ] **Step 3: Run E2E tests**

Run: `DATABASE_URL=postgresql://localhost:5432/dazzle_dev REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_runtime_e2e.py -k "Feedback" -v --timeout=120`
Expected: All 6 feedback tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/runtime/csrf.py tests/integration/test_runtime_e2e.py
git commit -m "feat(feedback): CSRF prefix exemption + PUT/DELETE E2E tests (#685)"
```

---

### Task 3: Shared Impl Module

**Files:**
- Create: `src/dazzle/cli/feedback_impl.py`

- [ ] **Step 1: Create the shared implementation module**

```python
"""Shared feedback operations for CLI and MCP handler.

Calls the running Dazzle server's CRUD endpoints via httpx.
Both the CLI (`dazzle feedback`) and MCP handler (`feedback` tool)
import from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def _get_server_url(project_root: Path | None = None) -> str:
    """Read the running server URL from .dazzle/runtime.json.

    Uses api_port (FastAPI) since /feedbackreports is an API route.
    Falls back to the unified port (ui_port) for single-port deployments.
    """
    root = project_root or Path.cwd().resolve()
    runtime_file = root / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            data = json.loads(runtime_file.read_text())
            # Prefer explicit api_url, then api_port, then ui_port (unified server)
            if "api_url" in data:
                return data["api_url"]
            port = data.get("api_port", data.get("ui_port", 3000))
            return f"http://127.0.0.1:{port}"
        except (json.JSONDecodeError, KeyError):
            pass
    return "http://127.0.0.1:3000"


def _auth_cookies(project_root: Path | None = None) -> dict[str, str]:
    """Read session cookie from .dazzle/session.json if available."""
    root = project_root or Path.cwd().resolve()
    session_file = root / ".dazzle" / "session.json"
    if session_file.exists():
        try:
            return json.loads(session_file.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


async def feedback_list(
    project_root: Path | None = None,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List feedback reports with optional filters."""
    url = _get_server_url(project_root)
    params: dict[str, str | int] = {"page_size": limit}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    if severity:
        params["severity"] = severity

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/feedbackreports",
            params=params,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return resp.json()


async def feedback_get(
    report_id: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Get a single feedback report by ID."""
    url = _get_server_url(project_root)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{url}/feedbackreports/{report_id}",
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return resp.json()


async def feedback_triage(
    report_id: str,
    project_root: Path | None = None,
    *,
    agent_notes: str | None = None,
    agent_classification: str | None = None,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Triage a feedback report (new → triaged)."""
    url = _get_server_url(project_root)
    payload: dict[str, str] = {"status": "triaged"}
    if agent_notes:
        payload["agent_notes"] = agent_notes
    if agent_classification:
        payload["agent_classification"] = agent_classification
    if assigned_to:
        payload["assigned_to"] = assigned_to

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{url}/feedbackreports/{report_id}",
            json=payload,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return resp.json()


async def feedback_resolve(
    report_id: str,
    project_root: Path | None = None,
    *,
    agent_notes: str | None = None,
    resolved_by: str | None = None,
) -> dict[str, Any]:
    """Resolve a feedback report (triaged/in_progress → resolved)."""
    url = _get_server_url(project_root)
    payload: dict[str, str] = {"status": "resolved"}
    if agent_notes:
        payload["agent_notes"] = agent_notes
    if resolved_by:
        payload["resolved_by"] = resolved_by

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            f"{url}/feedbackreports/{report_id}",
            json=payload,
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return resp.json()


async def feedback_delete(
    report_id: str,
    project_root: Path | None = None,
) -> bool:
    """Delete a feedback report. Returns True on success."""
    url = _get_server_url(project_root)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{url}/feedbackreports/{report_id}",
            cookies=_auth_cookies(project_root),
        )
        resp.raise_for_status()
        return True


async def feedback_stats(
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Compute feedback statistics by status, category, and severity."""
    data = await feedback_list(project_root, limit=1000)
    items = data.get("items", [])

    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for item in items:
        s = item.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        c = item.get("category", "unknown")
        by_category[c] = by_category.get(c, 0) + 1
        v = item.get("severity", "unknown")
        by_severity[v] = by_severity.get(v, 0) + 1

    return {
        "total": len(items),
        "by_status": by_status,
        "by_category": by_category,
        "by_severity": by_severity,
    }
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle/cli/feedback_impl.py
git commit -m "feat(feedback): shared impl module for CLI and MCP (#685)"
```

---

### Task 4: CLI Command Group

**Files:**
- Create: `src/dazzle/cli/feedback.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create CLI command group**

Create `src/dazzle/cli/feedback.py`:

```python
"""CLI commands for feedback widget management."""

from __future__ import annotations

import asyncio
import json as json_mod
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

feedback_app = typer.Typer(help="Feedback reports — list, triage, resolve.", no_args_is_help=True)
console = Console()


@feedback_app.command("list")
def list_command(
    status: str = typer.Option("", "--status", "-s", help="Filter by status (new, triaged, resolved, ...)"),
    category: str = typer.Option("", "--category", "-c", help="Filter by category (bug, ux, ...)"),
    severity: str = typer.Option("", "--severity", help="Filter by severity (blocker, annoying, minor)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List feedback reports."""
    from dazzle.cli.feedback_impl import feedback_list

    result = asyncio.run(
        feedback_list(status=status or None, category=category or None, severity=severity or None, limit=limit)
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    items = result.get("items", [])
    if not items:
        console.print("[dim]No feedback reports found.[/dim]")
        return

    table = Table(title=f"Feedback Reports ({result.get('total', len(items))} total)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Description", max_width=40)
    table.add_column("Reported By")

    for item in items:
        table.add_row(
            item["id"][:8],
            item.get("status", ""),
            item.get("category", ""),
            item.get("severity", ""),
            (item.get("description", "") or "")[:40],
            item.get("reported_by", ""),
        )
    console.print(table)


@feedback_app.command("get")
def get_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get a single feedback report."""
    from dazzle.cli.feedback_impl import feedback_get

    result = asyncio.run(feedback_get(report_id))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    for key, value in result.items():
        if value is not None:
            console.print(f"[bold]{key}:[/bold] {value}")


@feedback_app.command("triage")
def triage_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    notes: str = typer.Option("", "--notes", "-n", help="Agent notes"),
    assign: str = typer.Option("", "--assign", "-a", help="Assign to"),
    classify: str = typer.Option("", "--classify", help="Classification"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Triage a feedback report (new → triaged)."""
    from dazzle.cli.feedback_impl import feedback_triage

    result = asyncio.run(
        feedback_triage(
            report_id,
            agent_notes=notes or None,
            assigned_to=assign or None,
            agent_classification=classify or None,
        )
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} triaged → status={result['status']}")


@feedback_app.command("resolve")
def resolve_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    notes: str = typer.Option("", "--notes", "-n", help="Resolution notes"),
    resolved_by: str = typer.Option("", "--resolved-by", help="Who resolved it"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Resolve a feedback report (triaged/in_progress → resolved)."""
    from dazzle.cli.feedback_impl import feedback_resolve

    result = asyncio.run(
        feedback_resolve(report_id, agent_notes=notes or None, resolved_by=resolved_by or None)
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} resolved → status={result['status']}")


@feedback_app.command("delete")
def delete_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a feedback report."""
    from dazzle.cli.feedback_impl import feedback_delete

    asyncio.run(feedback_delete(report_id))

    if as_json:
        console.print(json_mod.dumps({"deleted": report_id}))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} deleted")


@feedback_app.command("stats")
def stats_command(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show feedback statistics."""
    from dazzle.cli.feedback_impl import feedback_stats

    result = asyncio.run(feedback_stats())

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[bold]Total:[/bold] {result['total']}")
    console.print("\n[bold]By Status:[/bold]")
    for k, v in result.get("by_status", {}).items():
        console.print(f"  {k}: {v}")
    console.print("\n[bold]By Category:[/bold]")
    for k, v in result.get("by_category", {}).items():
        console.print(f"  {k}: {v}")
    console.print("\n[bold]By Severity:[/bold]")
    for k, v in result.get("by_severity", {}).items():
        console.print(f"  {k}: {v}")
```

- [ ] **Step 2: Register in CLI __init__.py**

Add to `src/dazzle/cli/__init__.py` alongside the other `add_typer` calls:

```python
from dazzle.cli.feedback import feedback_app  # noqa: E402

app.add_typer(feedback_app, name="feedback")
```

- [ ] **Step 3: Verify CLI loads**

Run: `dazzle feedback --help`
Expected: Shows help with list, get, triage, resolve, delete, stats commands

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/feedback.py src/dazzle/cli/__init__.py
git commit -m "feat(feedback): CLI command group — list, triage, resolve, delete, stats (#685)"
```

---

### Task 5: MCP Handler

**Files:**
- Create: `src/dazzle/mcp/server/handlers/feedback.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`

- [ ] **Step 1: Create MCP handler**

Create `src/dazzle/mcp/server/handlers/feedback.py`:

```python
"""MCP handler for feedback widget operations.

Provides list/get/triage/resolve operations for the human→agent feedback loop.
Calls the running server's CRUD endpoints via the shared feedback_impl module.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .common import extract_progress


def list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List feedback reports with optional filters."""
    from dazzle.cli.feedback_impl import feedback_list

    progress = extract_progress(args)
    progress.log_sync("Listing feedback reports...")

    result = asyncio.run(
        feedback_list(
            project_root,
            status=args.get("status"),
            category=args.get("category"),
            severity=args.get("severity"),
            limit=int(args.get("limit", 20)),
        )
    )
    return json.dumps(result, indent=2)


def get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get a single feedback report by ID."""
    from dazzle.cli.feedback_impl import feedback_get

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Fetching feedback report {report_id[:8]}...")
    result = asyncio.run(feedback_get(report_id, project_root))
    return json.dumps(result, indent=2)


def triage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Triage a feedback report (new → triaged)."""
    from dazzle.cli.feedback_impl import feedback_triage

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Triaging feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_triage(
            report_id,
            project_root,
            agent_notes=args.get("agent_notes"),
            agent_classification=args.get("agent_classification"),
            assigned_to=args.get("assigned_to"),
        )
    )
    return json.dumps(result, indent=2)


def resolve_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Resolve a feedback report (triaged/in_progress → resolved)."""
    from dazzle.cli.feedback_impl import feedback_resolve

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Resolving feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_resolve(
            report_id,
            project_root,
            agent_notes=args.get("agent_notes"),
            resolved_by=args.get("resolved_by"),
        )
    )
    return json.dumps(result, indent=2)
```

- [ ] **Step 2: Register handler in handlers_consolidated.py**

Add near the other handler definitions (after the demo_data section):

```python
# =============================================================================
# Feedback Handler
# =============================================================================

_MOD_FEEDBACK = "dazzle.mcp.server.handlers.feedback"

handle_feedback: Callable[[dict[str, Any]], str] = _make_project_handler(
    "feedback",
    {
        "list": f"{_MOD_FEEDBACK}:list_handler",
        "get": f"{_MOD_FEEDBACK}:get_handler",
        "triage": f"{_MOD_FEEDBACK}:triage_handler",
        "resolve": f"{_MOD_FEEDBACK}:resolve_handler",
    },
)
```

Add to `CONSOLIDATED_TOOL_HANDLERS` dict:

```python
"feedback": handle_feedback,
```

- [ ] **Step 3: Register tool definition in tools_consolidated.py**

Add to `get_consolidated_tools()` list:

```python
Tool(
    name="feedback",
    description=(
        "Feedback operations: list, get, triage, resolve. "
        "Query and manage user-submitted feedback reports. "
        "Use 'list' to see open feedback, 'get' for detail, "
        "'triage' to mark as triaged, 'resolve' to close."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "get", "triage", "resolve"],
                "description": "Operation to perform",
            },
            "id": {
                "type": "string",
                "description": "Feedback report ID (required for get/triage/resolve)",
            },
            "status": {
                "type": "string",
                "description": "Filter by status (list only)",
            },
            "category": {
                "type": "string",
                "description": "Filter by category (list only)",
            },
            "severity": {
                "type": "string",
                "description": "Filter by severity (list only)",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (list only, default 20)",
            },
            "agent_notes": {
                "type": "string",
                "description": "Agent notes (triage/resolve)",
            },
            "agent_classification": {
                "type": "string",
                "description": "Classification (triage only)",
            },
            "assigned_to": {
                "type": "string",
                "description": "Assign to (triage only)",
            },
            "resolved_by": {
                "type": "string",
                "description": "Who resolved (resolve only)",
            },
            **PROJECT_PATH_SCHEMA,
        },
        "required": ["operation"],
    },
),
```

- [ ] **Step 4: Create MCP handler tests**

Create `tests/unit/mcp/test_feedback_handler.py`. **Important:** MCP handler tests require `sys.modules` isolation — follow the pattern in `tests/unit/mcp/conftest.py` which provides `install_handlers_common_mock()`. The handler imports `from .common import extract_progress` which needs the mock setup.

Test functions:
- `test_feedback_list_returns_reports` — mock httpx response, verify JSON output shape
- `test_feedback_get_returns_full_report` — mock httpx, verify all fields returned
- `test_feedback_triage_transitions_status` — mock httpx PUT, verify payload has status=triaged
- `test_feedback_resolve_transitions_status` — mock httpx PUT, verify payload has status=resolved

- [ ] **Step 5: Verify tool loads**

Run: `python -c "from dazzle.mcp.server.tools_consolidated import get_consolidated_tools; tools = get_consolidated_tools(); print([t.name for t in tools if 'feedback' in t.name])"`
Expected: `['feedback']`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/server/handlers/feedback.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py
git commit -m "feat(feedback): MCP tool — list, get, triage, resolve (#685)"
```

---

### Task 6: Knowledge Graph + Bootstrap

**Files:**
- Create: `src/dazzle/mcp/semantics_kb/feedback.toml`
- Modify: `src/dazzle/mcp/semantics_kb/__init__.py`
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`
- Modify: `src/dazzle/mcp/server/handlers/bootstrap.py`

- [ ] **Step 1: Create feedback.toml**

Create `src/dazzle/mcp/semantics_kb/feedback.toml`:

```toml
# Feedback Widget — knowledge for the human→agent feedback loop.

[concepts.feedback_widget]
category = "Framework Feature"
definition = """
In-app feedback collection. When `feedback_widget: enabled` is declared in the DSL,
the framework auto-generates a FeedbackReport entity, three synthetic surfaces
(CREATE, LIST, EDIT), and corresponding CRUD routes. A floating button appears on
every authenticated page, letting users report bugs, UX issues, and suggestions.
"""
syntax = """
feedback_widget: enabled
  position: bottom-right
  shortcut: backtick
  categories: [bug, ux, visual, behaviour, enhancement, other]
  severities: [blocker, annoying, minor]
  capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
"""

[concepts.feedback_report]
category = "Auto-Generated Entity"
definition = """
The FeedbackReport entity is auto-generated by the linker when `feedback_widget: enabled`.
It stores user-submitted feedback with category, severity, description, auto-captured context
(page URL, viewport, console errors, navigation history), and agent triage fields.

State machine: new → triaged → in_progress → resolved → verified (also: wont_fix, duplicate).
Shortcut: triaged → resolved (for quick fixes).
"""

[concepts.feedback_loop]
category = "Workflow Pattern"
definition = """
The human→agent feedback loop:
1. User submits feedback via the widget (POST /feedbackreports)
2. Agent reads feedback via MCP tool: feedback(operation='list')
3. Agent reads detail: feedback(operation='get', id='...')
4. Agent fixes the issue (edits code, updates DSL, etc.)
5. Agent resolves: feedback(operation='resolve', id='...', agent_notes='Fixed in commit ...')

The CLI (`dazzle feedback list/triage/resolve`) provides human override.
"""

[workflows.feedback_triage]
name = "Feedback Triage Workflow"
steps = [
    "feedback(operation='list', status='new') — see unprocessed feedback",
    "feedback(operation='get', id='<id>') — read full report with context",
    "Fix the reported issue (edit code, DSL, CSS, etc.)",
    "feedback(operation='resolve', id='<id>', agent_notes='Fixed in commit <sha>') — close the loop",
]
```

- [ ] **Step 2: Register feedback.toml in TOML_FILES**

In `src/dazzle/mcp/semantics_kb/__init__.py`, append `"feedback.toml"` to the existing `TOML_FILES` list (after `"runtime.toml"`):

```python
    "feedback.toml",
```

Do NOT replace the full list — just append to it.

- [ ] **Step 3: Bump SEED_SCHEMA_VERSION**

In `src/dazzle/mcp/knowledge_graph/seed.py`, increment `SEED_SCHEMA_VERSION` by 1 from its current value and add a comment:

```python
# Increment existing value by 1, e.g. 5 → 6
# Add comment: feedback_widget concepts + triage workflow
```

- [ ] **Step 4: Add bootstrap recommendation**

In `src/dazzle/mcp/server/handlers/bootstrap.py`, in the `else` branch of `_build_instructions()` (the direct-generation path), find the `steps` list entry `"8. Generate surfaces ..."` and insert after it:

```python
(
    "8a. If the app has auth enabled, add `feedback_widget: enabled` after the app "
    "declaration. This creates a human→agent feedback loop — users report issues "
    "via an in-app widget, agents read and resolve them via the feedback MCP tool."
),
```

- [ ] **Step 5: Verify TOML loads**

Run: `python -c "from dazzle.mcp.semantics_kb import _load_all_toml; data = _load_all_toml(); print('feedback_widget' in str(data))"`
Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/feedback.toml src/dazzle/mcp/semantics_kb/__init__.py src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/server/handlers/bootstrap.py
git commit -m "feat(feedback): knowledge graph concepts + bootstrap recommendation (#685)"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/unit/test_feedback_widget.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`
Expected: All pass, no regressions

- [ ] **Step 3: Run lint + type check**

Run: `ruff check src/dazzle/core/linker.py src/dazzle/cli/feedback.py src/dazzle/cli/feedback_impl.py src/dazzle/mcp/server/handlers/feedback.py --fix && ruff format src/ tests/`

Run: `mypy src/dazzle/core/linker.py src/dazzle/cli/feedback.py src/dazzle/cli/feedback_impl.py src/dazzle/mcp/server/handlers/feedback.py --ignore-missing-imports`

Expected: Clean

- [ ] **Step 4: Run E2E tests**

Run: `DATABASE_URL=postgresql://localhost:5432/dazzle_dev REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_runtime_e2e.py -k "Feedback" -v --timeout=120`
Expected: All 6 feedback tests PASS

- [ ] **Step 5: Fix any issues and commit**

```bash
git add -u
git commit -m "fix(feedback): lint and type fixes"
```
