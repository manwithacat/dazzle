# Plan 12 — Production-Path Parity for Fragment-Rendered Surfaces

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove every Fragment-rendered example surface renders correctly through the real FastAPI route stack — not just the in-process renderer call — so integration regressions in dispatch context, htmx swap headers, or route-handler context-building can never silently ship.

**Architecture:** Mount each example app's page routes onto a bare FastAPI app via `create_page_routes(appspec, backend_url=<stub>)` (the existing pattern from `tests/integration/test_template_pages.py`), wrap with `TestClient`, GET the primary list / detail / create URL of each app, and assert: (1) 200 status, (2) Fragment-chrome CSS classes present in body. The stub backend URL means data calls fail gracefully into the empty-state path — which is exactly what we want to verify renders cleanly through Fragment.

**Tech Stack:** Python 3.12, FastAPI TestClient, pytest, `dazzle_page.runtime.page_routes.create_page_routes`.

**Pre-flight:** Plan 11 closed the surface flip; `tests/integration/test_examples_fragment_smoke.py` pins DSL-level state. Plan 12 closes the gap between "DSL says fragment" and "the HTTP response actually came through the Fragment renderer."

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/integration/test_examples_fragment_http.py` (new) | TestClient-driven parity: every example app's primary list URL returns 200 + Fragment chrome |

One file. The plan is small on purpose — it's a verification expansion, not a feature.

---

## Task 1: TestClient parity — primary list per example

The first surface a user lands on is the primary list. Every example has one; Plan 11's smoke test already pinned the DSL flip. This task adds the HTTP transport layer.

**Files:**
- Create: `tests/integration/test_examples_fragment_http.py`

- [ ] **Step 1: Write the failing test**

```python
"""Plan 12 — Production-path parity for Fragment-rendered example surfaces.

Asserts that GETting each example app's primary list URL through a real
FastAPI TestClient returns 200 with Fragment-chrome CSS classes in the
response body. Catches integration regressions Plan 11's IR-level smoke
test can't see: route-handler context shape, htmx swap headers,
error-response wrapping, dispatch routing through the renderer registry.

Why a stub backend: page routes proxy data fetches to a backend HTTP
service. With no real backend, the data fetch fails into the empty-state
path — which is exactly what a fresh app shows on first boot, and which
exercises the full render stack without needing fixture data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle_page.runtime.page_routes")
from dazzle_page.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"

# (app_dir, primary_list_url) — primary_list_url derives from the entity
# the surface is bound to, lowercased, e.g. simple_task.task_list →
# uses entity Task → URL /task. If a future plan changes route
# generation, update both columns together.
_APPS: tuple[tuple[str, str], ...] = (
    ("simple_task", "/task"),
    ("contact_manager", "/contact"),
    ("support_tickets", "/user"),
    ("ops_dashboard", "/system"),
    ("fieldtest_hub", "/device"),
)

# CSS classes the Fragment renderer emits from a list-mode Surface +
# Region(kind=list). If the response body lacks these, either the
# renderer didn't run (production path is still on Jinja) or its output
# was stripped before the response was returned.
_FRAGMENT_LIST_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-list",
)


def _client_for(app_name: str) -> TestClient:
    appspec = load_project_appspec(_EXAMPLES / app_name)
    fastapi_app = FastAPI()
    router = create_page_routes(appspec, backend_url="http://127.0.0.1:9999")
    fastapi_app.include_router(router)
    return TestClient(fastapi_app)


@pytest.mark.parametrize("app_name,primary_list_url", _APPS)
def test_primary_list_renders_via_fragment_path(
    app_name: str, primary_list_url: str
) -> None:
    """The primary list URL of every example serves a 200 response whose
    body contains the Fragment renderer's chrome classes. Both halves
    matter: 200 alone could mean a Jinja fallback rendered something;
    Fragment classes alone could mean the route 500'd but the test client
    swallowed it. Together they pin the production path."""
    client = _client_for(app_name)
    resp = client.get(primary_list_url)
    assert resp.status_code == 200, (
        f"{app_name} GET {primary_list_url}: status {resp.status_code}, "
        f"body[:500]={resp.text[:500]!r}"
    )
    body = resp.text
    for marker in _FRAGMENT_LIST_MARKERS:
        assert marker in body, (
            f"{app_name} GET {primary_list_url}: response body missing "
            f"Fragment chrome class {marker!r}. Either the renderer "
            f"registry routed to Jinja, or the Fragment output was "
            f"stripped before the response. body[:500]={body[:500]!r}"
        )
```

- [ ] **Step 2: Run the test to see it fail OR pass**

```bash
pytest tests/integration/test_examples_fragment_http.py -v
```

Expected (best case): all 5 pass — the production path is already wired correctly because Plans 1–11 set it up. If any fail, the failure message reveals the gap. Most likely failure modes:

- **404 on `/task` etc.**: route generation uses a different URL convention. Read `src/dazzle_page/runtime/page_routes.py` for the primary-list URL pattern and update `_APPS` accordingly.
- **500**: the route-handler raised. Body will include the trace; investigate and either fix in this task or file an issue.
- **200 but missing `dz-surface`**: the Fragment path didn't actually run. Check the renderer registry wiring and the dispatch logic in `_maybe_dispatch_inner_html`.

- [ ] **Step 3: If route URLs are wrong, fix `_APPS`**

If the test fails on 404, find the actual URL pattern. Quickest probe — print every registered route:

```bash
python -c "
from pathlib import Path
from dazzle.core.appspec_loader import load_project_appspec
from dazzle_page.runtime.page_routes import create_page_routes
from fastapi import FastAPI
appspec = load_project_appspec(Path('examples/simple_task'))
app = FastAPI()
app.include_router(create_page_routes(appspec, backend_url='http://localhost'))
for r in app.routes:
    print(r.path, getattr(r, 'methods', None))
"
```

Update `_APPS` in the test to match the actual URL pattern. If the pattern is e.g. `/tasks` (plural) or `/task/list`, that's the source of truth — change the test, not the runtime.

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/integration/test_examples_fragment_http.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_examples_fragment_http.py
git commit -m "test(integration): production-path parity for Fragment-rendered example apps (Plan 12)

Asserts every example's primary list URL returns 200 with Fragment
chrome classes via real FastAPI TestClient. Closes the gap between
Plan 11's IR-level smoke test (DSL says fragment) and 'the HTTP
response actually came through the Fragment renderer'.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: TestClient parity — VIEW + CREATE modes for simple_task

LIST is the most common surface and Task 1 covers it cross-app. VIEW and CREATE exercise different adapter branches (`_build_view`, `_build_form`). Pin both for at least one example so a regression in either branch fails an HTTP test, not just an in-process unit test.

simple_task is the right example for this — it has all four modes wired and is the canonical reference app.

**Files:**
- Modify: `tests/integration/test_examples_fragment_http.py`

- [ ] **Step 1: Append the new tests**

Add to the bottom of `tests/integration/test_examples_fragment_http.py`:

```python
# ─────────────────────────── Mode coverage ───────────────────────────
#
# Task 1 covers LIST cross-app. These pin VIEW + CREATE for simple_task
# (the canonical reference example) — different adapter branches
# (_build_view, _build_form) so a regression in either fails an HTTP
# test, not just an in-process unit test.

_FRAGMENT_DETAIL_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-detail",
)

_FRAGMENT_FORM_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-form",
    "dz-form-stack",
)


def test_simple_task_create_url_renders_form_via_fragment() -> None:
    """GET /task/new returns the CREATE form rendered through the
    Fragment _build_form path."""
    client = _client_for("simple_task")
    resp = client.get("/task/new")
    assert resp.status_code == 200, (
        f"simple_task GET /task/new: status {resp.status_code}, "
        f"body[:500]={resp.text[:500]!r}"
    )
    body = resp.text
    for marker in _FRAGMENT_FORM_MARKERS:
        assert marker in body, (
            f"simple_task GET /task/new: missing Fragment form marker "
            f"{marker!r}. body[:500]={body[:500]!r}"
        )


def test_simple_task_detail_url_renders_via_fragment_or_404() -> None:
    """GET /task/<id> for a non-existent id either renders a 404 page
    via the Fragment path (acceptable — the framework's 404 surface
    might use Fragment chrome) OR returns the empty detail surface
    rendered via Fragment. Either is fine; what's not fine is a 500."""
    client = _client_for("simple_task")
    resp = client.get("/task/00000000-0000-0000-0000-000000000000")
    assert resp.status_code in (200, 404), (
        f"simple_task GET /task/<bogus-id>: status {resp.status_code} "
        f"(expected 200 or 404), body[:500]={resp.text[:500]!r}"
    )
    # If 200, the Fragment detail path rendered. If 404, accept any
    # rendered page (the 404 handler may not be on the Fragment path).
    if resp.status_code == 200:
        body = resp.text
        for marker in _FRAGMENT_DETAIL_MARKERS:
            assert marker in body, (
                f"simple_task GET /task/<bogus-id> returned 200 but "
                f"missing Fragment detail marker {marker!r}. "
                f"body[:500]={body[:500]!r}"
            )
```

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/integration/test_examples_fragment_http.py::test_simple_task_create_url_renders_form_via_fragment tests/integration/test_examples_fragment_http.py::test_simple_task_detail_url_renders_via_fragment_or_404 -v
```

Expected: 2 passed.

If `/task/new` 404s, the create URL pattern is different — probe it like Step 3 of Task 1 and update.

- [ ] **Step 3: Run the full file**

```bash
pytest tests/integration/test_examples_fragment_http.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_examples_fragment_http.py
git commit -m "test(integration): VIEW + CREATE mode HTTP parity for simple_task (Plan 12)

Pins the _build_view and _build_form adapter branches at the HTTP layer.
A regression in either now fails an integration test, not just a unit
test built on a hand-constructed SurfaceSpec.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Roadmap + CHANGELOG + bump + ship

**Files:**
- Modify: `docs/superpowers/plans/migration-roadmap.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the roadmap**

In `docs/superpowers/plans/migration-roadmap.md`, find the "Where we are" status table and add Plan 12 as a row:

```markdown
| 12 | Production-path parity | ✓ Shipped | TestClient HTTP test for every example's primary list + simple_task VIEW/CREATE — pins Fragment chrome at the response layer |
```

In the "Where we're going" section, remove the Plan 12 entry (it's now shipped). Plan 13 becomes the next active item.

If the HTTP tests surfaced any discoveries (URL pattern mismatches, response shape changes, missing markers), record them under "Lessons learned" with a Plan 12 subsection.

- [ ] **Step 2: CHANGELOG entry**

Add to `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- `tests/integration/test_examples_fragment_http.py` — TestClient-driven HTTP parity test for Fragment-rendered surfaces. Asserts every example app's primary list URL returns 200 with Fragment chrome classes; pins simple_task VIEW + CREATE mode at the HTTP layer. Closes the gap between Plan 11's IR-level smoke (DSL says `fragment`) and "the HTTP response actually came through the Fragment renderer". (Plan 12)
```

- [ ] **Step 3: Run the full pre-ship gate**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
mypy src/dazzle_http/ --ignore-missing-imports
pytest tests/ -m "not e2e" -q
```

Expected: all green.

- [ ] **Step 4: Commit roadmap + CHANGELOG**

```bash
git add docs/superpowers/plans/migration-roadmap.md CHANGELOG.md
git commit -m "docs: Plan 12 closure — production-path parity locked in

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Bump and ship**

```
/bump patch
/ship
```

Expected after `/ship`: clean worktree, new tag pushed.

---

## Self-Review

**Spec coverage:** "Prove every Fragment-rendered surface renders correctly through the real FastAPI route stack" → Task 1 covers list cross-app, Task 2 covers VIEW + CREATE for the canonical example. Cross-app VIEW/CREATE coverage is deliberately not added — Plan 11's smoke test already asserts every flipped surface declares `render: fragment` in the IR, and the adapter branches are the same per mode. Adding 5×3 = 15 cross-app HTTP cases would multiply runtime without adding signal. ✓

**Placeholder scan:** No "TBD". Each step has exact code, exact commands, exact expected output. Discovery-handling steps (Task 1 Step 3, Task 2 Step 2) acknowledge the failure mode but give the diagnostic path. ✓

**Type consistency:** `_client_for(app_name)` defined in Task 1 is reused in Task 2's added tests — same signature, same return type. CSS marker tuples (`_FRAGMENT_LIST_MARKERS`, `_FRAGMENT_DETAIL_MARKERS`, `_FRAGMENT_FORM_MARKERS`) all reference real classes asserted by `tests/unit/test_fragment_primitive_css.py`. ✓
