# In-process data-access core (page→REST self-fetch elimination) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the page handlers' HTTP self-fetch-to-their-own-REST-API with direct in-process `gated_*` calls that apply scope + permit identically, eliminating the #1421 loopback/Host-forward failure class.

**Architecture:** A new transport-agnostic core (`access/gated.py`) holds the enforcement+data logic *relocated* (not rewritten) out of the existing route-handler closures. REST routes and page handlers both become thin adapters that call the same `gated_*` functions. Enforcement (scope already in the repository SQL; permit relocated from the route closures into `gated_*`) lives in exactly one place.

**Tech Stack:** Python 3.12, FastAPI, async/await, Pydantic, PostgreSQL, pytest. Cedar-style access via `dazzle.render.access_evaluator.evaluate_permission`; scope via `dazzle.http.runtime.scope_filters`.

## Global Constraints

- **Relocate, do not rewrite.** Each `gated_*` body is lifted verbatim from the named route closure; reuse the same `_scoped_pre_read` / `evaluate_permission` / `_resolve_scope_filters` calls. No new enforcement logic.
- **Parity gate before removal.** A scope+permit parity test must pass *before* a self-fetch site is deleted. Order within each phase: add `gated_*` + parity test → REST delegates → page delegates → only then remove the fetch.
- **Behavior parity, not redesign.** No change to rendered HTML, JSON shapes, or status codes. Permit-denied READ stays **404** ("row-existence opaque to the caller", per `read_handlers.py:194`), not 403 — preserve this.
- **Co-located only.** `DAZZLE_BACKEND_URL` + the loopback/Host-forward machinery are removed (clean break, ADR-0003). `--backend-only` / `--ui-only` serve modes untouched.
- **Audit parity.** `gated_*` takes an optional `audit_logger`; the REST adapter passes its logger (unchanged auditing), the page adapter passes `None` (pages don't audit today — preserve that; broadening audit to pages is out of scope).
- **Pre-ship:** `ruff check src/ tests/ && mypy src/dazzle && pytest tests/ -m "not e2e"`; when touching scope/tenancy run `DATABASE_URL=… pytest -m postgres`. `/bump patch` + commit each shippable task.

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/access/__init__.py` (create) | Package marker; re-export `gated_read/list/aggregate/create/update/delete`, `AccessContext`, `AccessForbidden`, `RecordNotFound`. |
| `src/dazzle/http/runtime/access/gated.py` (create) | The transport-agnostic core: typed errors, `AccessContext`, `access_context_from`, and the `gated_*` functions. |
| `src/dazzle/http/runtime/handlers/read_handlers.py` (modify) | `_read_cedar` closure delegates to `gated_read`. |
| `src/dazzle/http/runtime/handlers/list_handlers.py` (modify) | `_list_handler_body` delegates to `gated_list`. |
| `src/dazzle/http/runtime/audit_wrap.py` (modify) | `_build_cedar_handler` delegates to `gated_create/update/delete`. |
| `src/dazzle/http/runtime/page_routes.py` (modify) | `_handle_detail` / `_handle_edit_form` / `_handle_table` call `gated_*`; delete `_resolve_backend_url`, `_resolve_host_to_forward`, `_sync_fetch`, `_fetch_url`, `_fetch_json`, the `host`/`effective_backend_url` fields of `_PageRequestContext`. |
| `src/dazzle/http/runtime/experience_routes.py` (modify) | `_experience_step_post` calls `gated_create/update`; delete `_sync_post`, `_proxy_to_backend`. |
| `tests/integration/test_gated_access_parity.py` (create) | The scope+permit parity gate (REST result == `gated_*` result; permit-denied parity). |

---

## Task 1: Access package — typed errors, `AccessContext`, builder

**Files:**
- Create: `src/dazzle/http/runtime/access/__init__.py`
- Create: `src/dazzle/http/runtime/access/gated.py`
- Test: `tests/unit/test_access_context.py`

**Interfaces:**
- Produces:
  - `class AccessForbidden(Exception)` — permit denied.
  - `class RecordNotFound(Exception)` — missing or scope-denied row.
  - `@dataclass(frozen=True) class AccessContext` with fields: `auth_context: Any`, `entity_name: str`, `cedar_access_spec: Any | None`, `fk_graph: Any | None`, `admin_personas: list[str] | None`.
  - `def access_context_from(request, *, entity_name, cedar_access_spec, fk_graph, admin_personas) -> AccessContext` — pulls `auth_context` from the resolved auth dependency value passed in (the caller supplies it; the builder just bundles).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_access_context.py
from dazzle.http.runtime.access.gated import AccessContext, access_context_from

def test_access_context_bundles_inputs():
    sentinel_auth = object()
    ac = access_context_from(
        auth_context=sentinel_auth,
        entity_name="Project",
        cedar_access_spec="SPEC",
        fk_graph="FK",
        admin_personas=["admin"],
    )
    assert ac.auth_context is sentinel_auth
    assert ac.entity_name == "Project"
    assert ac.cedar_access_spec == "SPEC"
    assert ac.fk_graph == "FK"
    assert ac.admin_personas == ["admin"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_access_context.py -v`
Expected: FAIL with `ModuleNotFoundError: dazzle.http.runtime.access`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/dazzle/http/runtime/access/gated.py
"""Transport-agnostic data-access core (#1422 option b).

The enforcement+data logic relocated out of the REST route-handler closures so
both the REST API and the HTML page layer call ONE core, in-process, instead of
the page layer self-fetching its own REST endpoint over loopback HTTP.

Scope (tenant isolation) is already compiled into Repository SQL via the
``__scope_predicate`` filter key; permit (Cedar) is relocated here from the route
closures. See docs/superpowers/specs/2026-06-20-page-rest-inprocess-core-design.md.
"""

from dataclasses import dataclass
from typing import Any


class AccessForbidden(Exception):
    """Permit (Cedar) denied the operation."""


class RecordNotFound(Exception):
    """Row is missing or hidden by a scope predicate."""


@dataclass(frozen=True)
class AccessContext:
    """Everything enforcement needs, bundled once per request."""

    auth_context: Any
    entity_name: str
    cedar_access_spec: Any | None
    fk_graph: Any | None
    admin_personas: list[str] | None


def access_context_from(
    *,
    auth_context: Any,
    entity_name: str,
    cedar_access_spec: Any | None,
    fk_graph: Any | None,
    admin_personas: list[str] | None,
) -> AccessContext:
    """Bundle the per-request enforcement inputs into an AccessContext."""
    return AccessContext(
        auth_context=auth_context,
        entity_name=entity_name,
        cedar_access_spec=cedar_access_spec,
        fk_graph=fk_graph,
        admin_personas=admin_personas,
    )
```

```python
# src/dazzle/http/runtime/access/__init__.py
from dazzle.http.runtime.access.gated import (
    AccessContext,
    AccessForbidden,
    RecordNotFound,
    access_context_from,
)

__all__ = [
    "AccessContext",
    "AccessForbidden",
    "RecordNotFound",
    "access_context_from",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_access_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/access/ tests/unit/test_access_context.py
git commit -m "feat(access): scaffold transport-agnostic access core (errors + AccessContext) (#1422)"
```

---

## Task 2: `gated_read` + REST read route delegates

**Files:**
- Modify: `src/dazzle/http/runtime/access/gated.py` (add `gated_read`)
- Modify: `src/dazzle/http/runtime/handlers/read_handlers.py:110-199` (`_read_cedar` delegates)
- Test: `tests/integration/test_gated_access_parity.py` (create — read parity)

**Interfaces:**
- Consumes: `AccessContext`, `AccessForbidden`, `RecordNotFound` (Task 1); `_scoped_pre_read`, `_build_access_context`, `_record_to_dict` (`scope_filters.py` / `read_handlers.py`); `evaluate_permission` (`dazzle.render.access_evaluator`).
- Produces: `async def gated_read(service, access: AccessContext, entity_id, *, include=None, audit_logger=None, request=None) -> dict` — returns the record dict; raises `RecordNotFound` (missing/scope-denied) or `AccessForbidden` (permit-denied).

**Relocation recipe:** `gated_read`'s body is lines `read_handlers.py:125-194` (the `_read_cedar` body *minus* the final `_render_detail_html` call at 195-196, which is HTTP-shaping that stays in the REST adapter). Replace `raise HTTPException(404)` with `raise RecordNotFound` and the permit-denied branch with `raise AccessForbidden`. Keep `_scoped_pre_read`, the `auto_include` re-hydration, `_build_access_context`, and `evaluate_permission` calls verbatim. Audit only when `audit_logger` is provided.

- [ ] **Step 1: Write the failing parity test**

```python
# tests/integration/test_gated_access_parity.py
import pytest
from dazzle.http.runtime.access.gated import gated_read, AccessForbidden, RecordNotFound, access_context_from

@pytest.mark.postgres
@pytest.mark.asyncio
async def test_gated_read_matches_rest_for_in_scope_row(scope_runtime_app):
    """gated_read returns the same record the REST detail endpoint returns,
    for a user whose scope+permit allow the row."""
    app = scope_runtime_app  # fixture: booted scope_runtime fixture app + seeded rows
    user, row_id, entity = app.member_user, app.member_visible_row_id, app.entity_name
    # REST path (over the test client):
    rest = app.client.get(f"/{app.plural(entity)}/{row_id}", headers=app.auth_headers(user)).json()
    # in-process path:
    access = access_context_from(
        auth_context=app.auth_context_for(user),
        entity_name=entity,
        cedar_access_spec=app.cedar_spec(entity),
        fk_graph=app.fk_graph,
        admin_personas=app.admin_personas(entity),
    )
    got = await gated_read(app.service(entity), access, row_id, include=app.auto_include(entity))
    assert got == rest

@pytest.mark.postgres
@pytest.mark.asyncio
async def test_gated_read_scope_denied_row_raises_not_found(scope_runtime_app):
    app = scope_runtime_app
    access = access_context_from(
        auth_context=app.auth_context_for(app.member_user),
        entity_name=app.entity_name,
        cedar_access_spec=app.cedar_spec(app.entity_name),
        fk_graph=app.fk_graph,
        admin_personas=app.admin_personas(app.entity_name),
    )
    with pytest.raises(RecordNotFound):
        await gated_read(app.service(app.entity_name), access, app.other_tenant_row_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=$TEST_DB pytest tests/integration/test_gated_access_parity.py -m postgres -v`
Expected: FAIL with `ImportError: cannot import name 'gated_read'`. (If the `scope_runtime_app` fixture does not yet exist, build it in this step from `fixtures/scope_runtime` + the existing `tests/integration/test_scope_runtime_pg.py` boot helpers — reuse, do not duplicate.)

- [ ] **Step 3: Implement `gated_read`**

Add to `src/dazzle/http/runtime/access/gated.py` (body relocated from `read_handlers.py:125-194`):

```python
async def gated_read(
    service: Any,
    access: AccessContext,
    entity_id: Any,
    *,
    include: list[str] | None = None,
    audit_logger: Any = None,
    request: Any = None,
) -> dict[str, Any]:
    from dazzle.core.access import AccessDecision, AccessOperationKind
    from dazzle.http.runtime.audit_log import measure_evaluation_time
    from dazzle.http.runtime.handlers.read_handlers import (
        _build_access_context,
        _log_audit_decision,
        _record_to_dict,
        _SCOPE_DENY_EFFECT,
    )
    from dazzle.http.runtime.scope_filters import _scoped_pre_read
    from dazzle.render.access_evaluator import evaluate_permission

    assert access.cedar_access_spec is not None
    result = await _scoped_pre_read(
        service=service,
        operation="read",
        id=entity_id,
        cedar_access_spec=access.cedar_access_spec,
        auth_context=access.auth_context,
        entity_name=access.entity_name,
        fk_graph=access.fk_graph,
        admin_personas=access.admin_personas,
    )
    if result is None:
        if audit_logger and request is not None:
            _u, _ = _build_access_context(access.auth_context)
            await _log_audit_decision(
                audit_logger, request, operation="read", entity_name=access.entity_name,
                entity_id=str(entity_id), decision="deny", matched_policy=_SCOPE_DENY_EFFECT,
                policy_effect=_SCOPE_DENY_EFFECT, user=_u,
            )
        raise RecordNotFound(access.entity_name)

    if include:
        hydrated = await service.execute(operation="read", id=entity_id, include=include)
        if hydrated is not None:
            result = hydrated

    user, ctx = _build_access_context(access.auth_context)
    decision: AccessDecision
    decision, eval_us = measure_evaluation_time(
        lambda: evaluate_permission(
            access.cedar_access_spec, AccessOperationKind.READ,
            _record_to_dict(result), ctx, entity_name=access.entity_name,
        )
    )
    if audit_logger and request is not None:
        await _log_audit_decision(
            audit_logger, request, operation="read", entity_name=access.entity_name,
            entity_id=str(entity_id), decision="allow" if decision.allowed else "deny",
            matched_policy=decision.matched_policy, policy_effect=decision.effect,
            user=user, evaluation_time_us=eval_us,
        )
    if not decision.allowed:
        raise RecordNotFound(access.entity_name)  # permit-denied READ is opaque (404), per read_handlers.py:194
    return result
```

Re-export from `access/__init__.py` (`gated_read`).

- [ ] **Step 4: Make `_read_cedar` delegate**

Replace `read_handlers.py:110-196` body with a thin adapter: build `AccessContext` from the closure's captured `cedar_access_spec`/`entity_name`/`fk_graph`/`admin_personas` + the `auth_context` dep, call `gated_read(service, access, id, include=auto_include, audit_logger=audit_logger, request=request)` inside `try/except (RecordNotFound,) → raise HTTPException(404)`, then `_render_detail_html(request, result, entity_name)` and return. (Permit-denied surfaces as `RecordNotFound` → 404, identical to today.)

- [ ] **Step 5: Run tests**

Run: `DATABASE_URL=$TEST_DB pytest tests/integration/test_gated_access_parity.py tests/integration/test_scope_runtime_pg.py -m postgres -v`
Expected: PASS (parity + the existing scope-runtime suite unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/access/ src/dazzle/http/runtime/handlers/read_handlers.py tests/integration/test_gated_access_parity.py
git commit -m "feat(access): gated_read; REST read route delegates to in-process core (#1422)"
```

---

## Task 3: Page detail handler calls `gated_read`

**Files:**
- Modify: `src/dazzle/http/runtime/page_routes.py:1275-1399` (`_handle_detail`)
- Test: `tests/integration/test_gated_access_parity.py` (add page-vs-REST detail parity)

**Interfaces:**
- Consumes: `gated_read`, `access_context_from`, `AccessForbidden`, `RecordNotFound` (Task 2); `prc.auth_ctx`, `prc.deps` (service + cedar_access_spec + fk_graph for the entity), `prc.path_id`, `prc.request` (`_PageRequestContext`, `page_routes.py:639`).

- [ ] **Step 1: Write the failing test** — assert the page's prepared `req_detail.item` equals the REST detail JSON for the same user, and that a forbid-detail persona yields the forbid-detail render (not a row). (Add to `test_gated_access_parity.py`, mirroring Task 2's fixture usage but driving `_handle_detail` via a booted page request.)

- [ ] **Step 2: Run — Expected:** FAIL (page still self-fetches; assertion on in-process path import fails or the item differs in error-shape).

- [ ] **Step 3: Implement** — replace the `_fetch_json(...)` call (`page_routes.py:1280-1286`) with:

```python
from dazzle.http.runtime.access.gated import gated_read, access_context_from, AccessForbidden, RecordNotFound

svc = prc.deps.service_for(prc.ctx.detail.entity_name)          # existing service lookup on deps
access = access_context_from(
    auth_context=prc.auth_ctx,
    entity_name=prc.ctx.detail.entity_name,
    cedar_access_spec=prc.deps.cedar_spec_for(prc.ctx.detail.entity_name),
    fk_graph=prc.deps.fk_graph,
    admin_personas=prc.deps.admin_personas_for(prc.ctx.detail.entity_name),
)
try:
    req_detail.item = await gated_read(svc, access, prc.path_id, include=prc.deps.auto_include_for(prc.ctx.detail.entity_name))
except RecordNotFound:
    req_detail.item = {"error": "not_found"}     # preserves the existing error-state shape consumed below
except AccessForbidden:
    req_detail.item = {"error": "forbidden"}     # routes into the existing forbid-detail render branch
```

**Execution findings (2026-06-20, refines this task):**

1. **Boot-state plumbing (DONE, prep).** The per-entity service map + `fk_graph` + `admin_personas` are NOT on `_PageRouterConfig` (only `entity_cedar_specs` is). They live on the route_generator at boot. Wired them onto `app.state` at `server.py:~1815` (right after `RouteGenerator(...)`): `app.state.entity_services = self._services`, `entity_fk_graph = _fk_graph`, `entity_admin_personas = _admin_personas`, `entity_auto_includes = self._entity_auto_includes`. The page handler reads them via `prc.request.app.state`; the cedar spec via `prc.deps.entity_cedar_specs.get(entity)`.

2. **Serialization parity (the real subtlety — build the parity test FIRST).** The original `_fetch_json` returned the **FastAPI-serialized JSON dict** (UUIDs→str, dates→ISO, FK dicts). `gated_read` returns the **pre-serialization** object (a Pydantic model, or a relations-hydrated dict). The page's downstream code (`_inject_display_names`, `when_expr` eval at `1300-1306`, FK display) depends on the JSON shape. So the swap MUST serialize the `gated_read` result to the same dict the REST detail response produces *before* assigning `req_detail.item`. Determine the REST detail serialization (the response model / `model_dump(mode="json")` vs the dict-passthrough when relations are included) and apply it in-process. The page-vs-REST parity test is what proves this — write it before the swap and make it assert deep-equality of the prepared `req_detail.item` against the REST detail JSON.

3. **Cedar / non-cedar branch.** Entities with a cedar spec → `gated_read`; entities without → plain `service.execute("read", id, include=auto_include)` (matches the REST `_core` path, which has no permit eval). Map a missing/None result and `RecordNotFound` → `{"error": "not_found"}` so the existing `"error" in req_detail.item` → 404 branch (`page_routes.py:1291-1298`) is preserved.

(Original sketch — superseded by the findings above: "add thin accessors on `_PageRouterConfig`" — the data wasn't there; it's on app.state now.)

- [ ] **Step 4: Run** `pytest tests/integration/test_gated_access_parity.py -m postgres -v` and the existing page/detail suite (`pytest tests/ -m "not e2e" -k "detail or page_route" -q`). Expected: PASS.

- [ ] **Step 5: Commit** `feat(page): detail handler reads in-process via gated_read, no self-fetch (#1422)`

---

## Task 4: Page edit-form handler calls `gated_read`

**Files:** Modify `src/dazzle/http/runtime/page_routes.py:1402-1430` (`_handle_edit_form`). Test: extend parity test for the edit/initial-values path.

Same swap as Task 3: replace the `_fetch_json(...)` at `page_routes.py:1407` with a `gated_read(...)` call (entity from `prc.ctx.form`), map `RecordNotFound`→ existing not-found handling, keep the `initial_values` + `PersonaVariant` logic at `1410-1424` unchanged. TDD steps mirror Task 3. Commit: `feat(page): edit-form handler reads in-process via gated_read (#1422)`.

---

## Task 5: `gated_list` + REST list route delegates

**Files:**
- Modify: `src/dazzle/http/runtime/access/gated.py` (add `gated_list`)
- Modify: `src/dazzle/http/runtime/handlers/list_handlers.py:263-669` (`_list_handler_body` delegates)
- Test: `tests/integration/test_gated_access_parity.py` (list parity, incl. scope-filtered + pagination)

**Interfaces:**
- Produces: `async def gated_list(service, access: AccessContext, *, page, page_size, filters=None, sort=None, search=None, include=None, audit_logger=None, request=None) -> dict` — returns `{"items", "total", "page", "page_size"}`; applies the list permit gate then scope-filtered `service.list`.

**Relocation recipe:** the enforcement is `list_handlers.py:302-373` — the Cedar LIST gate (302-332, raises 403 on deny → here raise `AccessForbidden`) + `_resolve_scope_filters` merge (340-373). The data call is `service.list(...)` (646). `gated_list` = {permit gate → scope merge → `service.list`}. The HTTP-shaping tail (audit 444-456, `__display__` 477-490, graph format 492-562, json_projection 649-669, HTMX/HTML 564-647) **stays in the REST adapter** — the page doesn't need it (the page renders from `items`/`total`). Note: list permit-deny is **403** in REST today; `gated_list` raises `AccessForbidden`, the REST adapter maps to 403, the page adapter maps to the forbid render.

TDD: parity test asserting `gated_list(...).items/total` equals the REST list JSON `items/total` for an in-scope user across (no-filter, filtered, paginated) cases, and `AccessForbidden` for a list-denied role. Then `_list_handler_body` delegates: build `AccessContext`, `result = await gated_list(...)`, then run the existing shaping tail on `result`. Commit: `feat(access): gated_list; REST list delegates to in-process core (#1422)`.

---

## Task 6: Page table + related-tabs call `gated_list`

**Files:** Modify `src/dazzle/http/runtime/page_routes.py:1449-1565` (`_handle_table`) and the related-tabs fetch at `page_routes.py:1378-1397`. Test: page-list parity + related-tabs parity.

Replace `_fetch_url(fetch_url, ...)` (`page_routes.py:1533`) with `gated_list(svc, access, page=…, page_size=…, filters=…, sort=…, search=…)`, deriving params from the request query as today (`1499-1530`), keeping the empty-state logic (`1534-1563`) unchanged. Replace the related-tab `_fetch_url` (`1378`) with `gated_list` filtered by the FK field. The `asyncio.gather` over tabs stays (now gathering in-process coroutines). TDD mirrors Task 3/5. Commit: `feat(page): table + related-tabs read in-process via gated_list (#1422)`.

---

## Task 7: `gated_create` / `gated_update` / `gated_delete`

**Files:**
- Modify: `src/dazzle/http/runtime/access/gated.py` (add write functions)
- Modify: `src/dazzle/http/runtime/audit_wrap.py:260-443` (`_build_cedar_handler` delegates)
- Test: `tests/integration/test_gated_access_parity.py` (write parity: create/update/delete permit + scope)

**Interfaces:**
- Produces: `async def gated_create(service, access, data, *, audit_logger=None, request=None) -> dict`; `async def gated_update(service, access, entity_id, data, *, audit_logger=None, request=None) -> dict`; `async def gated_delete(service, access, entity_id, *, audit_logger=None, request=None) -> None`. Permit-denied → `AccessForbidden`; scope-denied destination (update/delete pre-read) → `RecordNotFound`.

**Relocation recipe:** body is `audit_wrap.py:305-382` — the `_scoped_pre_read` for update/delete (305-314 → `RecordNotFound`), `evaluate_permission` (339-342), deny→raise (374-382 → `AccessForbidden`), then the core `service.create/update/delete`. The audit + response shaping stay in the REST adapter. TDD: write-parity test (a permit-denied create raises `AccessForbidden` just as REST returns 403; an out-of-scope update raises `RecordNotFound`/404). Then `_build_cedar_handler` delegates. Commit: `feat(access): gated_create/update/delete; REST write routes delegate (#1422)`.

---

## Task 8: Experience-POST calls `gated_create`/`gated_update`

**Files:** Modify `src/dazzle/http/runtime/experience_routes.py:483-670` (`_experience_step_post`). Test: experience-form submission parity (created entity == REST-created; validation error path preserved).

Replace `_proxy_to_backend(effective_backend_url, entity_ref, body, _cookies)` (`experience_routes.py:550`) with `gated_create(svc, access, body)` (or `gated_update` when the step targets an existing id). Map `AccessForbidden`/validation to the existing error re-render (`557-582`); keep the success/advance logic (`584-641`) unchanged. TDD mirrors prior tasks. Commit: `feat(experience): form POST mutates in-process via gated_create, no self-fetch (#1422)`.

---

## Task 9: Delete the loopback machinery + `DAZZLE_BACKEND_URL`

**Files:**
- Modify: `src/dazzle/http/runtime/page_routes.py` — delete `_resolve_backend_url` (157-184), `_resolve_host_to_forward` (190-208), `_sync_fetch` (100-122), `_fetch_url` (125-152), `_fetch_json` (211-236), and the `effective_backend_url`/`host` fields of `_PageRequestContext` (647-651) + their construction in `_page_handler` (2115-2132).
- Modify: `src/dazzle/http/runtime/experience_routes.py` — delete `_sync_post` (35-52), `_proxy_to_backend` (55-77), `_resolve_backend_url` import/use (517).
- Delete: `tests/unit/test_page_route_internal_fetch_host_1421.py`; prune the `DAZZLE_BACKEND_URL` cases in `tests/unit/test_url_consistency.py:589-649`.
- Grep gate: `grep -rn "DAZZLE_BACKEND_URL\|_resolve_backend_url\|_fetch_json\|_proxy_to_backend" src/ tests/` returns nothing.

- [ ] **Step 1:** Verify Tasks 3/4/6/8 removed every caller — `grep -rn "_fetch_json\|_fetch_url\|_proxy_to_backend\|effective_backend_url" src/dazzle/http/runtime/` returns only the definitions about to be deleted.
- [ ] **Step 2:** Delete the functions, fields, construction, and the `host`/`effective_backend_url` threading. Update `_PageRequestContext` callers.
- [ ] **Step 3:** Delete `test_page_route_internal_fetch_host_1421.py`; remove `DAZZLE_BACKEND_URL` cases from `test_url_consistency.py`. Remove the `/ship` pinned-regression line for `test_page_route_internal_fetch_host_1421.py` if present.
- [ ] **Step 4:** Run full gate: `ruff check src/ tests/ && mypy src/dazzle && pytest tests/ -m "not e2e" -q` and `DATABASE_URL=$TEST_DB pytest -m postgres -q`. Expected: PASS; grep gate empty.
- [ ] **Step 5:** CHANGELOG under `### Removed` (DAZZLE_BACKEND_URL + loopback self-fetch) and `### Changed` (page layer reads/writes in-process); note the #1421 class is structurally eliminated. `/bump patch`.
- [ ] **Step 6: Commit** `refactor(page)!: remove page→REST loopback self-fetch + DAZZLE_BACKEND_URL — in-process core only (#1422)`.

---

## Self-Review (completed)

**Spec coverage:** §4.1 core → Tasks 1,2,5,7. §4.2 permit relocation → Tasks 2,5,7 (relocation recipes cite exact anchors). §4.3 adapters → Tasks 2–8. §5 error taxonomy → Task 1 errors + adapter mapping in 2/5/7. §6 migration order → Tasks 2→3/4→5/6→7/8→9 (matches P1–P5). §7 parity gate → `test_gated_access_parity.py`, gating every removal. §3 drop DAZZLE_BACKEND_URL → Task 9. §9 audit follow-on → out of scope (post-implementation, not a task). No gaps.

**Placeholder scan:** Tasks 1–2 carry full code; Tasks 3–9 carry exact anchors + relocation recipes + concrete signatures (the body is being *moved* from a cited line range, so the anchor is the source of truth — not a placeholder). The parity test is concrete.

**Type consistency:** `gated_read/list/create/update/delete` signatures, `AccessContext` fields, and `AccessForbidden`/`RecordNotFound` names are consistent across Tasks 1–9. Permit-denied is 404 for READ (opaque) and 403 for LIST/writes — matched to current REST behavior per task.
