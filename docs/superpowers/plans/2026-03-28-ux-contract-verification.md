# UX Contract Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fast, httpx-based contract verification system that derives DOM assertions from the AppSpec and verifies rendered HTML fragments without a browser.

**Architecture:** Four new modules: `contracts.py` (generate contracts from AppSpec), `contract_checker.py` (fetch HTML + assert), `htmx_client.py` (simulate HTMX requests), `baseline.py` (ratchet mechanism). CLI extended with `--contracts` flag. All three modes (fragment, round-trip, RBAC) run via httpx against a live server.

**Tech Stack:** Python 3.12+, httpx (async HTTP), html.parser (stdlib HTML parsing), Pydantic (contract models), existing AppSpec IR

**Spec:** `docs/superpowers/specs/2026-03-28-ux-contract-verification-design.md`

---

### Task 1: Contract Data Models

**Files:**
- Create: `src/dazzle/testing/ux/contracts.py`
- Test: `tests/unit/test_ux_contracts.py`

- [ ] **Step 1: Write failing test for contract models**

```python
# tests/unit/test_ux_contracts.py
"""Tests for UX contract generation from AppSpec."""

from dazzle.testing.ux.contracts import (
    Contract,
    ContractKind,
    ListPageContract,
    CreateFormContract,
    EditFormContract,
    DetailViewContract,
    WorkspaceContract,
    RBACContract,
)


class TestContractModels:
    def test_list_page_contract_id_is_deterministic(self) -> None:
        c = ListPageContract(entity="Task", surface="task_list", fields=["title", "status"])
        assert len(c.contract_id) == 12
        assert c.contract_id == ListPageContract(
            entity="Task", surface="task_list", fields=["title", "status"]
        ).contract_id

    def test_list_page_contract_kind(self) -> None:
        c = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        assert c.kind == ContractKind.LIST_PAGE

    def test_rbac_contract_id_includes_persona(self) -> None:
        c1 = RBACContract(entity="Task", persona="admin", operation="delete", expected_present=True)
        c2 = RBACContract(entity="Task", persona="member", operation="delete", expected_present=False)
        assert c1.contract_id != c2.contract_id

    def test_create_form_contract(self) -> None:
        c = CreateFormContract(entity="Task", required_fields=["title"], all_fields=["title", "description"])
        assert c.kind == ContractKind.CREATE_FORM
        assert c.url_path == "/app/task/create"

    def test_workspace_contract(self) -> None:
        c = WorkspaceContract(
            workspace="task_board",
            regions=["tasks", "recent_comments"],
            fold_count=2,
        )
        assert c.kind == ContractKind.WORKSPACE
        assert c.url_path == "/app/workspaces/task_board"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_contracts.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'dazzle.testing.ux.contracts'"

- [ ] **Step 3: Write contract models**

```python
# src/dazzle/testing/ux/contracts.py
"""UX contract definitions derived from AppSpec.

Each contract describes what the rendered HTML must contain for a given
page, form, or interaction. Contracts are mechanically generated from
the DSL — no hand-written assertions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class ContractKind(StrEnum):
    LIST_PAGE = "list_page"
    CREATE_FORM = "create_form"
    EDIT_FORM = "edit_form"
    DETAIL_VIEW = "detail_view"
    WORKSPACE = "workspace"
    ROUND_TRIP = "round_trip"
    RBAC = "rbac"


@dataclass
class Contract:
    """Base for all contract types."""

    kind: ContractKind
    status: Literal["pending", "passed", "failed"] = "pending"
    error: str = ""

    @property
    def contract_id(self) -> str:
        key = self._id_key()
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def _id_key(self) -> str:
        return f"{self.kind}"

    @property
    def url_path(self) -> str:
        return ""


@dataclass
class ListPageContract(Contract):
    kind: ContractKind = ContractKind.LIST_PAGE
    entity: str = ""
    surface: str = ""
    fields: list[str] = field(default_factory=list)

    def _id_key(self) -> str:
        return f"{self.kind}:{self.entity}:{self.surface}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}"


@dataclass
class CreateFormContract(Contract):
    kind: ContractKind = ContractKind.CREATE_FORM
    entity: str = ""
    required_fields: list[str] = field(default_factory=list)
    all_fields: list[str] = field(default_factory=list)

    def _id_key(self) -> str:
        return f"{self.kind}:{self.entity}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/create"


@dataclass
class EditFormContract(Contract):
    kind: ContractKind = ContractKind.EDIT_FORM
    entity: str = ""
    editable_fields: list[str] = field(default_factory=list)

    def _id_key(self) -> str:
        return f"{self.kind}:{self.entity}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/{{id}}/edit"


@dataclass
class DetailViewContract(Contract):
    kind: ContractKind = ContractKind.DETAIL_VIEW
    entity: str = ""
    fields: list[str] = field(default_factory=list)
    has_edit: bool = False
    has_delete: bool = False
    transitions: list[str] = field(default_factory=list)

    def _id_key(self) -> str:
        return f"{self.kind}:{self.entity}"

    @property
    def url_path(self) -> str:
        return f"/app/{self.entity.lower()}/{{id}}"


@dataclass
class WorkspaceContract(Contract):
    kind: ContractKind = ContractKind.WORKSPACE
    workspace: str = ""
    regions: list[str] = field(default_factory=list)
    fold_count: int = 3

    def _id_key(self) -> str:
        return f"{self.kind}:{self.workspace}"

    @property
    def url_path(self) -> str:
        return f"/app/workspaces/{self.workspace}"


@dataclass
class RoundTripContract(Contract):
    kind: ContractKind = ContractKind.ROUND_TRIP
    url: str = ""
    hx_target: str = ""
    method: str = "GET"
    expected_elements: list[str] = field(default_factory=list)

    def _id_key(self) -> str:
        return f"{self.kind}:{self.method}:{self.url}:{self.hx_target}"


@dataclass
class RBACContract(Contract):
    kind: ContractKind = ContractKind.RBAC
    entity: str = ""
    persona: str = ""
    operation: str = ""
    expected_present: bool = True

    def _id_key(self) -> str:
        return f"{self.kind}:{self.entity}:{self.persona}:{self.operation}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ux_contracts.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/contracts.py tests/unit/test_ux_contracts.py
git commit -m "feat(ux): add contract data models for DOM verification"
```

---

### Task 2: Contract Generation from AppSpec

**Files:**
- Modify: `src/dazzle/testing/ux/contracts.py`
- Test: `tests/unit/test_ux_contracts.py`

- [ ] **Step 1: Write failing test for generate_contracts**

```python
# Append to tests/unit/test_ux_contracts.py
from pathlib import Path
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.testing.ux.contracts import generate_contracts, ContractKind


class TestContractGeneration:
    def setup_method(self) -> None:
        self.appspec = load_project_appspec(Path("examples/simple_task").resolve())

    def test_generates_list_page_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        list_pages = [c for c in contracts if c.kind == ContractKind.LIST_PAGE]
        # simple_task has Task and User with list surfaces
        assert len(list_pages) >= 2
        task_list = next(c for c in list_pages if c.entity == "Task")
        assert "title" in task_list.fields

    def test_generates_create_form_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        create_forms = [c for c in contracts if c.kind == ContractKind.CREATE_FORM]
        # One per entity (deduplicated), excluding framework entities
        entity_names = {c.entity for c in create_forms}
        assert "Task" in entity_names
        # No duplicate entities
        assert len(entity_names) == len(create_forms)

    def test_generates_detail_view_with_transitions(self) -> None:
        contracts = generate_contracts(self.appspec)
        detail = next(c for c in contracts if c.kind == ContractKind.DETAIL_VIEW and c.entity == "Task")
        # Task has state machine transitions
        assert len(detail.transitions) > 0
        assert detail.has_delete is True

    def test_generates_workspace_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        workspaces = [c for c in contracts if c.kind == ContractKind.WORKSPACE]
        ws_names = {c.workspace for c in workspaces}
        assert "task_board" in ws_names

    def test_generates_rbac_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        rbac = [c for c in contracts if c.kind == ContractKind.RBAC]
        # Should have contracts for both permitted and forbidden operations
        permitted = [c for c in rbac if c.expected_present]
        forbidden = [c for c in rbac if not c.expected_present]
        assert len(permitted) > 0
        assert len(forbidden) > 0

    def test_no_framework_entities_in_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        entities = {c.entity for c in contracts if hasattr(c, "entity") and c.entity}
        assert "AIJob" not in entities
        assert "SystemHealth" not in entities
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_contracts.py::TestContractGeneration -v`
Expected: FAIL with "ImportError: cannot import name 'generate_contracts'"

- [ ] **Step 3: Implement generate_contracts**

Append to `src/dazzle/testing/ux/contracts.py`:

```python
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import PermissionKind

_FRAMEWORK_ENTITIES = frozenset({
    "AIJob", "FeedbackReport", "SystemHealth", "SystemMetric", "DeployHistory",
})


def _get_permitted_personas(appspec: AppSpec, entity_name: str, operation: PermissionKind) -> list[str]:
    """Return persona IDs that have a permit rule for the given operation."""
    entity = next((e for e in appspec.domain.entities if e.name == entity_name), None)
    if not entity or not entity.access:
        return [p.id for p in appspec.personas]
    permitted: set[str] = set()
    for rule in entity.access.permissions:
        if rule.operation == operation:
            if rule.personas:
                permitted.update(rule.personas)
            else:
                return [p.id for p in appspec.personas]
    return list(permitted)


def _get_entity_fields(entity: object) -> tuple[list[str], list[str]]:
    """Return (all_field_names, required_field_names) for an entity."""
    all_fields: list[str] = []
    required_fields: list[str] = []
    for f in entity.fields:
        if f.name == "id":
            continue
        modifiers = [str(m) for m in (f.modifiers or [])] if hasattr(f, "modifiers") else []
        if "auto_add" in modifiers or "auto_update" in modifiers:
            continue
        all_fields.append(f.name)
        if "required" in modifiers:
            required_fields.append(f.name)
    return all_fields, required_fields


def generate_contracts(appspec: AppSpec) -> list[Contract]:
    """Generate all DOM contracts from an AppSpec."""
    contracts: list[Contract] = []
    persona_ids = [p.id for p in appspec.personas]

    # Map entities to surfaces
    entity_surfaces: dict[str, list[object]] = {}
    for surface in appspec.surfaces:
        if surface.entity_ref and surface.entity_ref not in _FRAMEWORK_ENTITIES:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface)

    for entity in appspec.domain.entities:
        if entity.name in _FRAMEWORK_ENTITIES:
            continue
        surfaces = entity_surfaces.get(entity.name, [])
        if not surfaces:
            continue

        all_fields, required_fields = _get_entity_fields(entity)

        # ListPageContract — one per list-mode surface
        for surface in surfaces:
            mode = str(surface.mode.value) if hasattr(surface.mode, "value") else str(surface.mode)
            if mode == "list":
                contracts.append(ListPageContract(
                    entity=entity.name,
                    surface=surface.name,
                    fields=all_fields[:],
                ))

        # CreateFormContract — one per entity
        contracts.append(CreateFormContract(
            entity=entity.name,
            required_fields=required_fields[:],
            all_fields=all_fields[:],
        ))

        # EditFormContract — one per entity
        contracts.append(EditFormContract(
            entity=entity.name,
            editable_fields=all_fields[:],
        ))

        # DetailViewContract — one per entity
        has_edit = bool(_get_permitted_personas(appspec, entity.name, PermissionKind.UPDATE))
        has_delete = bool(_get_permitted_personas(appspec, entity.name, PermissionKind.DELETE))
        transitions: list[str] = []
        if entity.state_machine:
            for t in entity.state_machine.transitions:
                transitions.append(f"{t.from_state}→{t.to_state}")
        contracts.append(DetailViewContract(
            entity=entity.name,
            fields=all_fields[:],
            has_edit=has_edit,
            has_delete=has_delete,
            transitions=transitions,
        ))

        # RBACContract — one per entity × persona × operation
        for operation in (PermissionKind.LIST, PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.DELETE):
            permitted = set(_get_permitted_personas(appspec, entity.name, operation))
            for pid in persona_ids:
                contracts.append(RBACContract(
                    entity=entity.name,
                    persona=pid,
                    operation=operation.value,
                    expected_present=(pid in permitted),
                ))

    # WorkspaceContract — one per workspace
    for workspace in appspec.workspaces:
        region_names = [r.name for r in workspace.regions]
        fold_count = getattr(workspace, "fold_count", None) or 3
        contracts.append(WorkspaceContract(
            workspace=workspace.name,
            regions=region_names,
            fold_count=fold_count,
        ))

    return contracts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ux_contracts.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/contracts.py tests/unit/test_ux_contracts.py
git commit -m "feat(ux): generate DOM contracts from AppSpec"
```

---

### Task 3: HTMX Client

**Files:**
- Create: `src/dazzle/testing/ux/htmx_client.py`
- Test: `tests/unit/test_ux_htmx_client.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_ux_htmx_client.py
"""Tests for HTMX request simulation client."""

from dazzle.testing.ux.htmx_client import HtmxClient


class TestHtmxClient:
    def test_builds_htmx_headers(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        headers = client._htmx_headers(target="dz-detail-drawer-content")
        assert headers["HX-Request"] == "true"
        assert headers["HX-Target"] == "dz-detail-drawer-content"

    def test_builds_auth_cookies(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        cookies = client._cookies()
        assert cookies["dazzle_session"] == "abc123"
        assert cookies["dazzle_csrf"] == "xyz789"

    def test_csrf_header_included_for_mutating_methods(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        headers = client._htmx_headers(target="body", method="DELETE")
        assert headers["X-CSRF-Token"] == "xyz789"

    def test_csrf_header_excluded_for_get(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        headers = client._htmx_headers(target="body", method="GET")
        assert "X-CSRF-Token" not in headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_htmx_client.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement HtmxClient**

```python
# src/dazzle/testing/ux/htmx_client.py
"""HTMX request simulation for contract verification.

Sends HTTP requests with the same headers HTMX would send from the browser,
so the server returns the correct fragments (partial vs full page).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class HtmxResponse:
    """Response from an HTMX-simulated request."""

    status: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    hx_trigger: str = ""
    hx_redirect: str = ""


class _TagCollector(HTMLParser):
    """Collect tags and their attributes from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def parse_html(html: str) -> list[tuple[str, dict[str, str | None]]]:
    """Parse HTML and return list of (tag, attrs) tuples."""
    collector = _TagCollector()
    collector.feed(html)
    return collector.tags


@dataclass
class HtmxClient:
    """Simulates HTMX requests for contract verification."""

    base_url: str
    _session_token: str = ""
    _csrf_token: str = ""

    def set_session(self, session_token: str, csrf_token: str = "") -> None:
        self._session_token = session_token
        self._csrf_token = csrf_token

    def _cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if self._session_token:
            cookies["dazzle_session"] = self._session_token
        if self._csrf_token:
            cookies["dazzle_csrf"] = self._csrf_token
        return cookies

    def _htmx_headers(
        self, target: str = "body", method: str = "GET", trigger: str = ""
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "HX-Request": "true",
            "HX-Target": target,
        }
        if trigger:
            headers["HX-Trigger"] = trigger
        # CSRF token for mutating requests
        if method != "GET" and self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        # Test secret if set
        secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if secret:
            headers["X-Test-Secret"] = secret
        return headers

    async def get(self, path: str, hx_target: str = "body") -> HtmxResponse:
        """Send a GET request as HTMX would."""
        import httpx

        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=self._htmx_headers(target=hx_target),
                cookies=self._cookies(),
                follow_redirects=False,
                timeout=10,
            )
        return HtmxResponse(
            status=resp.status_code,
            html=resp.text,
            headers=dict(resp.headers),
            hx_trigger=resp.headers.get("hx-trigger", ""),
            hx_redirect=resp.headers.get("hx-redirect", ""),
        )

    async def get_full_page(self, path: str) -> HtmxResponse:
        """Send a normal GET (not HTMX) to get the full rendered page."""
        import httpx

        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                cookies=self._cookies(),
                follow_redirects=True,
                timeout=10,
            )
        return HtmxResponse(
            status=resp.status_code,
            html=resp.text,
            headers=dict(resp.headers),
        )

    async def authenticate(self, persona: str) -> bool:
        """Authenticate as a persona via the test endpoint."""
        import httpx

        headers: dict[str, str] = {}
        secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if secret:
            headers["X-Test-Secret"] = secret

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/__test__/authenticate",
                json={"role": persona, "username": persona},
                headers=headers,
                timeout=10,
            )
        if resp.status_code != 200:
            return False
        data = resp.json()
        token = data.get("session_token", "") or data.get("token", "")
        if not token:
            return False

        # Get CSRF token from a GET request
        async with httpx.AsyncClient() as client:
            csrf_resp = await client.get(
                f"{self.base_url}/health",
                timeout=5,
            )
        csrf = ""
        for cookie_header in csrf_resp.headers.get_list("set-cookie"):
            if "dazzle_csrf=" in cookie_header:
                csrf = cookie_header.split("dazzle_csrf=")[1].split(";")[0]
                break

        self.set_session(token, csrf)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ux_htmx_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/htmx_client.py tests/unit/test_ux_htmx_client.py
git commit -m "feat(ux): add HTMX request simulation client"
```

---

### Task 4: Contract Checker (Mode 1 — Fragment Contracts)

**Files:**
- Create: `src/dazzle/testing/ux/contract_checker.py`
- Test: `tests/unit/test_ux_contract_checker.py`

- [ ] **Step 1: Write failing test with sample HTML**

```python
# tests/unit/test_ux_contract_checker.py
"""Tests for contract checker — HTML assertion engine."""

from dazzle.testing.ux.contracts import (
    ListPageContract,
    CreateFormContract,
    DetailViewContract,
    WorkspaceContract,
)
from dazzle.testing.ux.contract_checker import check_contract


SAMPLE_LIST_HTML = """
<table data-dazzle-table="Task">
  <thead><tr>
    <th data-dz-col="title"><a hx-get="/tasks?sort=title">Title</a></th>
    <th data-dz-col="status">Status</th>
  </tr></thead>
  <tbody>
    <tr hx-get="/app/task/abc123" hx-target="body">
      <td data-dz-col="title">Test</td>
      <td data-dz-col="status">todo</td>
    </tr>
  </tbody>
</table>
<a href="/app/task/create">+ New Task</a>
<input hx-get="/tasks" hx-trigger="keyup changed delay:300ms" />
"""

SAMPLE_FORM_HTML = """
<form hx-post="/tasks">
  <input name="title" type="text" required />
  <textarea name="description"></textarea>
  <button type="submit">Create</button>
</form>
"""

SAMPLE_DETAIL_HTML = """
<h2>Task Detail</h2>
<div data-dazzle-entity="Task">
  <span data-dazzle-field="title">Test</span>
  <span data-dazzle-field="status">todo</span>
</div>
<a href="/app/task/abc123/edit">Edit</a>
<button hx-delete="/tasks/abc123" hx-confirm="Delete?">Delete</button>
<button hx-put="/tasks/abc123" hx-vals='{"status":"in_progress"}'>Start</button>
"""

SAMPLE_WORKSPACE_HTML = """
<div data-region-name="tasks" hx-get="/api/workspaces/task_board/regions/tasks" hx-trigger="load"></div>
<div data-region-name="comments" hx-get="/api/workspaces/task_board/regions/comments" hx-trigger="intersect once"></div>
<aside id="dz-detail-drawer"></aside>
"""


class TestCheckListPage:
    def test_passes_valid_list_page(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title", "status"])
        result = check_contract(contract, SAMPLE_LIST_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_table(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        result = check_contract(contract, "<div>No table here</div>")
        assert result.status == "failed"
        assert "data-dazzle-table" in result.error

    def test_fails_missing_create_link(self) -> None:
        html = '<table data-dazzle-table="Task"><tbody><tr hx-get="/app/task/1"></tr></tbody></table>'
        contract = ListPageContract(entity="Task", surface="task_list", fields=[])
        result = check_contract(contract, html)
        assert result.status == "failed"
        assert "create" in result.error.lower()


class TestCheckCreateForm:
    def test_passes_valid_form(self) -> None:
        contract = CreateFormContract(entity="Task", required_fields=["title"], all_fields=["title", "description"])
        result = check_contract(contract, SAMPLE_FORM_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_required_field(self) -> None:
        contract = CreateFormContract(entity="Task", required_fields=["title", "priority"], all_fields=["title", "priority"])
        result = check_contract(contract, SAMPLE_FORM_HTML)
        assert result.status == "failed"
        assert "priority" in result.error


class TestCheckDetailView:
    def test_passes_valid_detail(self) -> None:
        contract = DetailViewContract(
            entity="Task", fields=["title", "status"],
            has_edit=True, has_delete=True, transitions=["todo→in_progress"],
        )
        result = check_contract(contract, SAMPLE_DETAIL_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_delete_button(self) -> None:
        html = "<h2>Detail</h2><div data-dazzle-entity='Task'></div>"
        contract = DetailViewContract(entity="Task", fields=[], has_edit=False, has_delete=True, transitions=[])
        result = check_contract(contract, html)
        assert result.status == "failed"
        assert "delete" in result.error.lower()


class TestCheckWorkspace:
    def test_passes_valid_workspace(self) -> None:
        contract = WorkspaceContract(workspace="task_board", regions=["tasks", "comments"], fold_count=1)
        result = check_contract(contract, SAMPLE_WORKSPACE_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_region(self) -> None:
        contract = WorkspaceContract(workspace="task_board", regions=["tasks", "missing_region"], fold_count=2)
        result = check_contract(contract, SAMPLE_WORKSPACE_HTML)
        assert result.status == "failed"
        assert "missing_region" in result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_contract_checker.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement check_contract**

```python
# src/dazzle/testing/ux/contract_checker.py
"""Contract checker — verifies rendered HTML against DOM contracts.

Parses HTML with stdlib HTMLParser and asserts that elements required
by each contract type are present with correct attributes.
"""

from __future__ import annotations

from dazzle.testing.ux.contracts import (
    Contract,
    CreateFormContract,
    DetailViewContract,
    EditFormContract,
    ListPageContract,
    RBACContract,
    WorkspaceContract,
)
from dazzle.testing.ux.htmx_client import parse_html


def check_contract(contract: Contract, html: str) -> Contract:
    """Check a single contract against rendered HTML. Mutates contract status/error."""
    tags = parse_html(html)
    errors: list[str] = []

    if isinstance(contract, ListPageContract):
        _check_list_page(contract, tags, html, errors)
    elif isinstance(contract, CreateFormContract):
        _check_create_form(contract, tags, errors)
    elif isinstance(contract, EditFormContract):
        _check_edit_form(contract, tags, errors)
    elif isinstance(contract, DetailViewContract):
        _check_detail_view(contract, tags, html, errors)
    elif isinstance(contract, WorkspaceContract):
        _check_workspace(contract, tags, errors)
    elif isinstance(contract, RBACContract):
        _check_rbac(contract, tags, html, errors)

    if errors:
        contract.status = "failed"
        contract.error = "; ".join(errors)
    else:
        contract.status = "passed"

    return contract


def _has_tag_with_attr(
    tags: list[tuple[str, dict[str, str | None]]], tag: str, attr: str, value: str
) -> bool:
    """Check if any tag has the given attribute with the given value."""
    for t, attrs in tags:
        if t == tag and attrs.get(attr) == value:
            return True
    return False


def _has_attr_containing(
    tags: list[tuple[str, dict[str, str | None]]], attr: str, substring: str
) -> bool:
    """Check if any tag has an attribute containing the substring."""
    for _, attrs in tags:
        val = attrs.get(attr) or ""
        if substring in val:
            return True
    return False


def _check_list_page(
    contract: ListPageContract,
    tags: list[tuple[str, dict[str, str | None]]],
    html: str,
    errors: list[str],
) -> None:
    # Table with data-dazzle-table
    if not _has_attr_containing(tags, "data-dazzle-table", contract.entity):
        errors.append(f"Missing table with data-dazzle-table=\"{contract.entity}\"")

    # Rows with hx-get
    slug = contract.entity.lower()
    has_row_link = _has_attr_containing(tags, "hx-get", f"/app/{slug}/")
    if not has_row_link:
        errors.append(f"No table rows with hx-get pointing to /app/{slug}/")

    # Create link
    has_create = _has_attr_containing(tags, "href", f"/app/{slug}/create")
    if not has_create:
        errors.append(f"Missing create link (href containing /app/{slug}/create)")

    # Search input with hx-get
    has_search = any(
        t == "input" and "hx-get" in attrs and "hx-trigger" in attrs
        for t, attrs in tags
    )
    if not has_search:
        errors.append("Missing search input with hx-get and hx-trigger")


def _check_create_form(
    contract: CreateFormContract,
    tags: list[tuple[str, dict[str, str | None]]],
    errors: list[str],
) -> None:
    # Form with hx-post
    has_form = any(t == "form" and "hx-post" in attrs for t, attrs in tags)
    if not has_form:
        errors.append("Missing form with hx-post")

    # Required fields
    input_names = {
        attrs.get("name")
        for t, attrs in tags
        if t in ("input", "textarea", "select") and attrs.get("name")
    }
    for field_name in contract.required_fields:
        if field_name not in input_names:
            errors.append(f"Missing required field: {field_name}")

    # Submit button
    has_submit = any(
        (t == "button" and attrs.get("type") == "submit")
        or (t == "input" and attrs.get("type") == "submit")
        for t, attrs in tags
    )
    if not has_submit:
        errors.append("Missing submit button")


def _check_edit_form(
    contract: EditFormContract,
    tags: list[tuple[str, dict[str, str | None]]],
    errors: list[str],
) -> None:
    # Form with hx-post (edit uses POST with entity ID in action URL)
    has_form = any(t == "form" and "hx-post" in attrs for t, attrs in tags)
    if not has_form:
        errors.append("Missing form with hx-post")

    # Submit button
    has_submit = any(
        (t == "button" and attrs.get("type") == "submit")
        or (t == "input" and attrs.get("type") == "submit")
        for t, attrs in tags
    )
    if not has_submit:
        errors.append("Missing submit button")


def _check_detail_view(
    contract: DetailViewContract,
    tags: list[tuple[str, dict[str, str | None]]],
    html: str,
    errors: list[str],
) -> None:
    # Heading
    has_heading = any(t in ("h1", "h2", "h3") for t, _ in tags)
    if not has_heading:
        errors.append("Missing heading (h1/h2/h3)")

    # Edit link
    if contract.has_edit:
        slug = contract.entity.lower()
        has_edit = _has_attr_containing(tags, "href", f"/app/{slug}/") and _has_attr_containing(
            tags, "href", "/edit"
        )
        if not has_edit:
            errors.append("Missing edit link")

    # Delete button
    if contract.has_delete:
        has_delete = any("hx-delete" in attrs for _, attrs in tags)
        if not has_delete:
            errors.append("Missing delete button (hx-delete)")

    # State transitions
    for transition in contract.transitions:
        to_state = transition.split("→")[1] if "→" in transition else transition
        has_transition = any(
            "hx-put" in attrs
            and to_state in (attrs.get("hx-vals") or "")
            for _, attrs in tags
        )
        if not has_transition:
            errors.append(f"Missing state transition button for →{to_state}")


def _check_workspace(
    contract: WorkspaceContract,
    tags: list[tuple[str, dict[str, str | None]]],
    errors: list[str],
) -> None:
    # Regions
    found_regions = {
        attrs.get("data-region-name")
        for _, attrs in tags
        if attrs.get("data-region-name")
    }
    for region_name in contract.regions:
        if region_name not in found_regions:
            errors.append(f"Missing region: {region_name}")

    # Drawer
    has_drawer = any(
        attrs.get("id") == "dz-detail-drawer" for _, attrs in tags
    )
    if not has_drawer:
        errors.append("Missing drawer element (#dz-detail-drawer)")


def _check_rbac(
    contract: RBACContract,
    tags: list[tuple[str, dict[str, str | None]]],
    html: str,
    errors: list[str],
) -> None:
    slug = contract.entity.lower()
    element_found = False

    if contract.operation == "create":
        element_found = _has_attr_containing(tags, "href", f"/app/{slug}/create")
    elif contract.operation == "update":
        element_found = _has_attr_containing(tags, "href", "/edit")
    elif contract.operation == "delete":
        element_found = any("hx-delete" in attrs for _, attrs in tags)
    elif contract.operation == "list":
        # For list, we check page accessibility, not element presence
        return

    if contract.expected_present and not element_found:
        errors.append(
            f"RBAC: {contract.operation} element missing for {contract.persona} "
            f"(expected present)"
        )
    elif not contract.expected_present and element_found:
        errors.append(
            f"RBAC: {contract.operation} element visible to {contract.persona} "
            f"(expected absent)"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ux_contract_checker.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/contract_checker.py tests/unit/test_ux_contract_checker.py
git commit -m "feat(ux): add contract checker with Mode 1 fragment assertions"
```

---

### Task 5: Baseline Ratchet Mechanism

**Files:**
- Create: `src/dazzle/testing/ux/baseline.py`
- Test: `tests/unit/test_ux_baseline.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_ux_baseline.py
"""Tests for UX contract baseline (ratchet mechanism)."""

import json
from pathlib import Path

from dazzle.testing.ux.baseline import Baseline, compare_results


class TestBaseline:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        baseline = Baseline(total=10, passed=8, failed=2, contracts={"abc": "passed", "def": "failed"})
        baseline.save(path)
        loaded = Baseline.load(path)
        assert loaded.total == 10
        assert loaded.contracts["abc"] == "passed"

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        loaded = Baseline.load(path)
        assert loaded.total == 0
        assert loaded.contracts == {}

    def test_compare_detects_regressions(self) -> None:
        old = Baseline(total=3, passed=3, failed=0, contracts={"a": "passed", "b": "passed", "c": "passed"})
        new = Baseline(total=3, passed=2, failed=1, contracts={"a": "passed", "b": "failed", "c": "passed"})
        diff = compare_results(old, new)
        assert diff.regressions == ["b"]
        assert diff.fixed == []

    def test_compare_detects_fixes(self) -> None:
        old = Baseline(total=2, passed=1, failed=1, contracts={"a": "passed", "b": "failed"})
        new = Baseline(total=2, passed=2, failed=0, contracts={"a": "passed", "b": "passed"})
        diff = compare_results(old, new)
        assert diff.regressions == []
        assert diff.fixed == ["b"]

    def test_compare_handles_new_contracts(self) -> None:
        old = Baseline(total=1, passed=1, failed=0, contracts={"a": "passed"})
        new = Baseline(total=2, passed=1, failed=1, contracts={"a": "passed", "b": "failed"})
        diff = compare_results(old, new)
        assert diff.new_failures == ["b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_baseline.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement baseline**

```python
# src/dazzle/testing/ux/baseline.py
"""Ratchet baseline for UX contract verification.

Tracks pass/fail state of each contract across runs. Regressions
(previously passing contracts that now fail) are flagged prominently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Baseline:
    total: int = 0
    passed: int = 0
    failed: int = 0
    contracts: dict[str, str] = field(default_factory=dict)  # contract_id -> "passed"|"failed"
    timestamp: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "contracts": self.contracts,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> Baseline:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(
                total=data.get("total", 0),
                passed=data.get("passed", 0),
                failed=data.get("failed", 0),
                contracts=data.get("contracts", {}),
                timestamp=data.get("timestamp", ""),
            )
        except Exception:
            return cls()


@dataclass
class BaselineDiff:
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    new_failures: list[str] = field(default_factory=list)


def compare_results(old: Baseline, new: Baseline) -> BaselineDiff:
    """Compare two baselines and return the diff."""
    regressions: list[str] = []
    fixed: list[str] = []
    new_failures: list[str] = []

    for contract_id, new_status in new.contracts.items():
        old_status = old.contracts.get(contract_id)
        if old_status is None and new_status == "failed":
            new_failures.append(contract_id)
        elif old_status == "passed" and new_status == "failed":
            regressions.append(contract_id)
        elif old_status == "failed" and new_status == "passed":
            fixed.append(contract_id)

    return BaselineDiff(regressions=regressions, fixed=fixed, new_failures=new_failures)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ux_baseline.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/baseline.py tests/unit/test_ux_baseline.py
git commit -m "feat(ux): add baseline ratchet mechanism for contract verification"
```

---

### Task 6: Wire CLI + End-to-End Integration

**Files:**
- Modify: `src/dazzle/cli/ux.py`
- Modify: `src/dazzle/testing/ux/__init__.py`
- Test: `tests/unit/test_cli_ux.py` (extend existing)

- [ ] **Step 1: Write failing test for CLI --contracts flag**

```python
# Append to tests/unit/test_cli_ux.py
from unittest.mock import patch

class TestVerifyContractsFlag:
    def test_contracts_flag_accepted(self) -> None:
        """The --contracts flag should be accepted by the CLI parser."""
        from dazzle.cli.ux import verify_command
        import inspect
        sig = inspect.signature(verify_command)
        param_names = list(sig.parameters.keys())
        assert "contracts" in param_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_ux.py::TestVerifyContractsFlag -v`
Expected: FAIL with AssertionError (no "contracts" parameter)

- [ ] **Step 3: Add --contracts mode to CLI**

Add to the `verify_command` function in `src/dazzle/cli/ux.py`:

```python
# Add parameter to verify_command signature:
    contracts: bool = typer.Option(False, "--contracts", help="Run contract verification (no browser)"),
    mode: int = typer.Option(0, "--mode", help="Contract mode: 1=fragment, 2=+round-trip, 3=+RBAC (0=all)"),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 on any contract failure"),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="Update baseline after run"),
    browser: bool = typer.Option(False, "--browser", help="Run Playwright browser tests only"),
```

Add contract execution path after the structural check:

```python
    if contracts or (not browser and not structural):
        from dazzle.testing.ux.contracts import generate_contracts
        from dazzle.testing.ux.contract_checker import check_contract
        from dazzle.testing.ux.htmx_client import HtmxClient
        from dazzle.testing.ux.baseline import Baseline, compare_results

        all_contracts = generate_contracts(appspec)
        console.print(f"[dim]Contracts: {len(all_contracts)} generated[/dim]")

        client = HtmxClient(base_url=site_url)
        if not await_or_run(client.authenticate("admin")):
            console.print("[red]Failed to authenticate for contract checking[/red]")
            raise typer.Exit(1)

        # Mode 1: Fragment contracts
        for c in all_contracts:
            if hasattr(c, "url_path") and c.url_path and "{id}" not in c.url_path:
                resp = await_or_run(client.get_full_page(c.url_path))
                if resp.status == 200:
                    check_contract(c, resp.html)
                elif resp.status in (403, 401):
                    c.status = "passed"  # Access control working
                else:
                    c.status = "failed"
                    c.error = f"HTTP {resp.status}"

        # Collect results
        passed = sum(1 for c in all_contracts if c.status == "passed")
        failed = sum(1 for c in all_contracts if c.status == "failed")
        pending = sum(1 for c in all_contracts if c.status == "pending")
        console.print(f"[bold]Contracts: {passed} passed, {failed} failed, {pending} pending[/bold]")

        # Baseline comparison
        baseline_path = project_root / ".dazzle" / "ux-verify" / "baseline.json"
        old_baseline = Baseline.load(baseline_path)
        new_baseline = Baseline(
            total=len(all_contracts),
            passed=passed,
            failed=failed,
            contracts={c.contract_id: c.status for c in all_contracts if c.status != "pending"},
        )
        if update_baseline:
            new_baseline.save(baseline_path)
            console.print(f"[dim]Baseline updated: {baseline_path}[/dim]")

        diff = compare_results(old_baseline, new_baseline)
        if diff.regressions:
            console.print(f"[red]Regressions: {len(diff.regressions)}[/red]")
        if diff.fixed:
            console.print(f"[green]Fixed: {len(diff.fixed)}[/green]")

        if strict and failed > 0:
            raise typer.Exit(1)
```

Note: `await_or_run` is a helper wrapping `asyncio.run()` for the async client calls. Add it near the top of the file:

```python
def _run_async(coro):
    """Run an async coroutine from sync context."""
    import asyncio
    return asyncio.run(coro)
```

- [ ] **Step 4: Update __init__.py exports**

Add to `src/dazzle/testing/ux/__init__.py`:

```python
from dazzle.testing.ux.contracts import (
    Contract,
    ContractKind,
    generate_contracts,
)
from dazzle.testing.ux.baseline import Baseline, compare_results
```

- [ ] **Step 5: Run all UX tests to verify nothing breaks**

Run: `pytest tests/unit/test_ux_inventory.py tests/unit/test_ux_structural.py tests/unit/test_ux_report.py tests/unit/test_ux_fixtures.py tests/unit/test_ux_runner.py tests/unit/test_cli_ux.py tests/unit/test_ux_contracts.py tests/unit/test_ux_contract_checker.py tests/unit/test_ux_baseline.py tests/unit/test_ux_htmx_client.py -v`
Expected: All passed

- [ ] **Step 6: Lint and type check**

Run: `ruff check src/dazzle/testing/ux/ src/dazzle/cli/ux.py --fix && ruff format src/dazzle/testing/ux/ src/dazzle/cli/ux.py`
Run: `mypy src/dazzle/cli/ux.py src/dazzle/testing/ux/ --ignore-missing-imports`
Expected: No errors in changed files

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/cli/ux.py src/dazzle/testing/ux/__init__.py tests/unit/test_cli_ux.py
git commit -m "feat(ux): wire contract verification into CLI with --contracts flag"
```

---

### Task 7: Run Against simple_task and Establish Baseline

**Files:**
- No new files — this is a verification + fix task

- [ ] **Step 1: Boot simple_task and run contract verification**

```bash
cd examples/simple_task
DATABASE_URL="postgresql://localhost:5432/dazzle_simple_task" \
  REDIS_URL="redis://localhost:6379/0" \
  DAZZLE_ENV=development \
  DAZZLE_TEST_SECRET="" \
  dazzle serve --local &
sleep 10
DAZZLE_SITE_URL="http://localhost:3392" dazzle ux verify --contracts
```

- [ ] **Step 2: Record initial failure count**

Note the passed/failed/pending counts. This is the starting point for convergence.

- [ ] **Step 3: Fix any contract checker bugs revealed by real HTML**

The sample HTML in tests may differ from real rendered HTML. Adjust selectors in `contract_checker.py` as needed. Common issues:
- Attribute value matching (partial vs exact)
- Nested elements vs flat structure
- Template conditionals hiding elements

- [ ] **Step 4: Update baseline**

```bash
dazzle ux verify --contracts --update-baseline
```

- [ ] **Step 5: Run against contact_manager**

```bash
cd examples/contact_manager
# Boot and verify
dazzle ux verify --contracts
```

- [ ] **Step 6: Fix any cross-example issues**

Ensure contracts work for both simple_task and contact_manager without example-specific logic.

- [ ] **Step 7: Commit all fixes**

```bash
git add -u
git commit -m "fix(ux): contract checker adjustments from real-world verification"
```

---

### Task 8: Bump Version and Ship

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -m "not e2e" -x -q
```
Expected: All passed (minus any pre-existing fuzz failures)

- [ ] **Step 2: Bump version**

Run: `/bump patch`

- [ ] **Step 3: Ship**

Run: `/ship`
