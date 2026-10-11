# Route-override response contract + authoring guardrails (#1392 item 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) or subagent-driven-development. Steps use `- [ ]`.

**Goal:** Give route-overrides a declared response contract (`# dazzle:returns page|fragment|partial|json`), with chrome-wrap as one consumer (only `fragment` is shell-wrapped; `page` = declared full-bleed, never refused), plus the authoring-guardrail deliverable (RBAC mandatory; shape+chrome a declared choice).

**Architecture:** A reusable `build_app_page_context(request, *, deps)` (extracted nav/chrome builder) feeds `dispatch_render_page` to chrome a `fragment` override. A `# dazzle:returns` header → `RouteOverrideDescriptor.returns_kind` drives `_wrap_with_response_contract`, composed outside the existing `_wrap_with_policy_gate`. An undeclared `/app` HTML override logs a one-time advisory.

**Tech Stack:** Python 3.12, FastAPI route-override discovery (regex scan), the typed Fragment renderer (`dispatch_render_page`), pytest.

## Global Constraints (verbatim from spec)
- **RBAC orthogonal + unchanged.** The contract wrapper composes OUTSIDE `_wrap_with_policy_gate`; permit/scope is untouched.
- **`page` is never refused** — declared full-bleed/novel-UX/island-host. Consistency errors fire only for `fragment`/`partial` returning a full `<!doctype>`.
- **Opt-in + advisory nudge** — declaring `# dazzle:returns` is opt-in; undeclared `/app` HTML logs a one-time advisory (never JSON/HTMX/non-`/app`). Never a hard gate (novel UI welcome).
- **Kind encodes chrome** — only `fragment` wrapped; no separate `chrome:` attribute. Vocabulary closed: `page|fragment|partial|json` (unknown = discovery error).
- Ship discipline: per-phase gate green → `/bump patch` + commit + push; full `pytest -m "not e2e"` before each main push.

## File map
- `src/dazzle/page/runtime/page_routes.py` — new `build_app_page_context(request, *, deps, current_route, inner_html_title=None) -> tuple[PageContext, _ChromeAssets]`; refactor the two inline `PageContext` sites (L2447 workspace, L2376 entity) to consume the shared chrome-asset + nav-model helpers (behavior-preserving).
- `src/dazzle/http/runtime/route_overrides.py` — `_RETURNS_RE`, `RouteOverrideDescriptor.returns_kind`, parse in `discover_route_overrides`, `_VALID_RETURN_KINDS`, `_wrap_with_response_contract`, advisory nudge; apply in the mount loop (L466) outside `_wrap_with_policy_gate`.
- `docs/counter-priors/custom-route-undeclared-response.md` + INDEX — the guardrail counter-prior.
- `docs/reference/` — route-override contract section.
- `fixtures/custom_renderer/` (or a routes/ fixture) — dogfood a `fragment` + a `page` override.
- `tests/unit/test_route_override_response_contract.py`, `tests/unit/test_build_app_page_context.py`.

---

## Task 1 (P1): extract `build_app_page_context`

**Files:** Modify `src/dazzle/page/runtime/page_routes.py`; Test `tests/unit/test_build_app_page_context.py`.

**Interfaces — Produces:** `build_app_page_context(request, *, deps: _PageRouterConfig, current_route: str) -> tuple[PageContext, _ChromeAssets]` where `_ChromeAssets` is a frozen dataclass `(css_links, js_scripts, theme, font_preconnect, favicon)`. Reuses `_resolve_nav_model` (L711) + the app-state chrome-asset resolution (currently inline at L2462-2480).

- [ ] **Step 1: Write the failing test** (`tests/unit/test_build_app_page_context.py`) — assert the builder returns a `PageContext` with the app nav + the chrome assets from `request.app.state`, for a synthetic request + minimal `_PageRouterConfig`:
```python
from types import SimpleNamespace
from dazzle.page.runtime.page_routes import build_app_page_context, _PageRouterConfig

def _req(app_state):
    return SimpleNamespace(app=SimpleNamespace(state=app_state), state=SimpleNamespace(tenant_config={}), cookies={})

def test_builder_returns_context_and_chrome_assets():
    app_state = SimpleNamespace(
        fragment_chrome_css_links=("/x.css",), fragment_chrome_js_scripts=("/x.js",),
        fragment_chrome_theme=None, fragment_chrome_font_preconnect=(), fragment_chrome_favicon="/f.svg",
    )
    deps = _PageRouterConfig(...)  # minimal: nav data + get_auth_context=None (anon)
    ctx, assets = build_app_page_context(_req(app_state), deps=deps, current_route="/app/board")
    assert ctx.current_route == "/app/board"
    assert assets.css_links == ("/x.css",) and assets.favicon == "/f.svg"
```
*(Construct `_PageRouterConfig` per its actual dataclass fields — read the definition; pass the app's nav items/groups it already carries and `get_auth_context=None` for the anon path.)*

- [ ] **Step 2: Run → FAIL** (`build_app_page_context` undefined). `pytest tests/unit/test_build_app_page_context.py -q`.

- [ ] **Step 3: Implement.** Add a `_ChromeAssets` frozen dataclass + `_resolve_chrome_assets(app_state) -> _ChromeAssets` (extract L2462-2480 verbatim), and `build_app_page_context(request, *, deps, current_route)` that builds the nav `PageContext` from `deps` (nav items/groups) + `_resolve_nav_model(deps, user_roles, authenticated=...)` + request auth/tenant_config, with `current_route` as given. The app nav (sidebar) is the persona-resolved general nav — NOT a surface-specific `visible_nav`.

- [ ] **Step 4: Refactor the two inline sites (behavior-preserving).** Replace the inline `css_links=.../favicon=...` blocks at L2462 (and the entity-page equivalent) with `assets = _resolve_chrome_assets(app_state)` + `dispatch_render_page(page_ctx, inner, css_links=assets.css_links, ...)`. Leave the page-specific `page_ctx` construction as-is (don't unify the surface-specific nav). The goal: the chrome-asset resolution is shared, so an override's chrome === a page's chrome.

- [ ] **Step 5: Run + the existing page tests** — `pytest tests/unit/test_build_app_page_context.py tests/unit -k "page_route or page_handler or workspace_handler" -q`. Expected PASS (parity).

- [ ] **Step 6: Regen golden-master if the refactor shifted any rendered bytes** (it shouldn't — same assets). `pytest tests/integration/test_golden_master.py -q`; if it fails, diff to confirm it's identical output, then `--snapshot-update`.

- [ ] **Step 7: ruff + mypy + commit (local).**
```bash
.venv/bin/ruff format src/dazzle/page/runtime/page_routes.py tests/unit/test_build_app_page_context.py
.venv/bin/ruff check src/dazzle/page/runtime/page_routes.py tests/unit/test_build_app_page_context.py --fix
.venv/bin/mypy src/dazzle/page/runtime/page_routes.py
git add src/dazzle/page/runtime/page_routes.py tests/unit/test_build_app_page_context.py
git commit -m "refactor(ui): extract build_app_page_context + _resolve_chrome_assets (#1392 item 2 P1)"
```

---

## Task 2 (P2): `# dazzle:returns` marker

**Files:** Modify `src/dazzle/http/runtime/route_overrides.py`; Test `tests/unit/test_route_override_response_contract.py`.

**Interfaces — Produces:** `RouteOverrideDescriptor.returns_kind: str | None`; `_VALID_RETURN_KINDS = frozenset({"page","fragment","partial","json"})`.

- [ ] **Step 1: Write the failing test:**
```python
from pathlib import Path
from dazzle.http.runtime.route_overrides import discover_route_overrides

def test_returns_kind_parsed(tmp_path):
    routes = tmp_path / "routes"; routes.mkdir()
    (routes / "board.py").write_text(
        "# dazzle:route-override GET /app/board\n# dazzle:returns fragment\n\n"
        "async def handler(request):\n    return None\n")
    o = next(o for o in discover_route_overrides(routes) if o.path == "/app/board")
    assert o.returns_kind == "fragment"

def test_unknown_returns_kind_is_error(tmp_path):
    routes = tmp_path / "routes"; routes.mkdir()
    (routes / "x.py").write_text(
        "# dazzle:route-override GET /x\n# dazzle:returns bogus\n\nasync def handler(request):\n    return None\n")
    import pytest
    with pytest.raises(ValueError, match="dazzle:returns"):
        discover_route_overrides(routes)
```

- [ ] **Step 2: Run → FAIL** (no `returns_kind`).

- [ ] **Step 3: Implement.** Add `_RETURNS_RE = re.compile(r"#\s*dazzle:returns\s+(\w+)", re.IGNORECASE)`, `_VALID_RETURN_KINDS`, `returns_kind: str | None = None` on the descriptor; in `discover_route_overrides` parse `m = _RETURNS_RE.search(content)`, validate the kind ∈ `_VALID_RETURN_KINDS` (raise `ValueError` with a clear message on unknown), pass `returns_kind=` into the descriptor.

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: ruff + commit (local).** `git commit -m "feat(routes): # dazzle:returns marker -> returns_kind (#1392 item 2 P2)"`

---

## Task 3 (P3): `_wrap_with_response_contract` + advisory nudge

**Files:** Modify `src/dazzle/http/runtime/route_overrides.py` (+ pass the nav `deps`/builder in at mount); Test extends `tests/unit/test_route_override_response_contract.py`.

**Interfaces — Consumes:** `returns_kind` (P2), `build_app_page_context` (P1). **Produces:** `_wrap_with_response_contract(handler, *, returns_kind, path, page_ctx_builder)`.

- [ ] **Step 1: Write failing tests** (Starlette `TestClient` with a tiny app mounting a wrapped handler):
  - `fragment` + `HX-Request` header → response body == handler inner HTML (no `<html>`).
  - `fragment` + no `HX-Request` → body contains the inner HTML AND the app-shell nav markup (chromed).
  - `fragment` handler returning `<!doctype html>...` → 500 with the typed message.
  - `partial` → raw inner HTML, no chrome, on both request kinds.
  - `page` → full `<!doctype>` served as-is (status 200, no error).
  - `json` → passthrough.
  - undeclared `/app` HTML on a full-page request → exactly one `WARNING` advisory (caplog), keyed by path (second request: no second log).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `_wrap_with_response_contract`.** An async wrapper that calls the handler, then by `returns_kind`:
  - normalise the handler result to `(body_text, status, headers, media_type)` (handle `str`, `HTMLResponse`, `JSONResponse`, `Response`); non-HTML media types short-circuit to passthrough.
  - `fragment`: if body sniffs as a full doc (`_is_full_document(body)`), raise the typed error; elif `request.headers.get("HX-Request")`: return the inner HTML as `HTMLResponse`; else `ctx, assets = page_ctx_builder(request, current_route=path)` → `HTMLResponse(dispatch_render_page(ctx, body, css_links=assets.css_links, ...))`.
  - `partial`: full-doc → typed error; else return inner HTML as-is.
  - `page`: return as-is (no checks).
  - `json`: passthrough (debug-log if body sniffs HTML).
  - `None` (undeclared): passthrough + `_advise_undeclared(path, request, body, media_type)` (one-time, keyed by path, only `/app` + `text/html` + non-`HX-Request`).
  - `_is_full_document(body)`: `body.lstrip()[:200].lower()` startswith `<!doctype` or `<html`.

- [ ] **Step 4: Wire at mount.** In the override mount loop (`route_overrides.py` ~L466), after the `_wrap_with_policy_gate` wrap, apply `_wrap_with_response_contract` OUTSIDE it when `override.returns_kind is not None OR override.path.startswith("/app")` (the nudge needs undeclared `/app` too). Thread a `page_ctx_builder` callable (bound to `build_app_page_context` + the page-router `deps`) from `app_factory` where overrides are mounted — add a parameter to the mount function. For unit tests, inject a stub builder.

- [ ] **Step 5: Run → PASS** (all per-kind + nudge tests).

- [ ] **Step 6: Composition test** — a handler with BOTH `# dazzle:implements` and `# dazzle:returns fragment`: RBAC gate denies an unauthorized user (403) AND an authorized one gets the chromed fragment. ruff + mypy + commit (local).

---

## Task 4 (P4): guardrail deliverable + dogfood + ship + close #1392

**Files:** `docs/counter-priors/custom-route-undeclared-response.md` + `docs/counter-priors/INDEX.md`; `docs/reference/` (route-override contract section); a `routes/` dogfood fixture; `CHANGELOG.md`.

- [ ] **Step 1: Counter-prior.** Write `docs/counter-priors/custom-route-undeclared-response.md` with the required frontmatter (id/name/layer=filter/status/summary/triggers_text/triggers_code) + the four body sections (`## The corpus prior`, `## Wrong shape`, `## Right shape`, `## Why this matters here`). Pathology: a route-override returns HTML with no `# dazzle:returns` and/or touches an entity with no `# dazzle:implements`. Right shape shows both markers. Add the INDEX line. Run `pytest tests/unit/test_counter_priors_drift.py -q`.

- [ ] **Step 2: Reference docs.** Add a route-override contract section (the marker vocabulary `route-override`/`implements`/`emits`/`returns` + the two-line guardrail model: RBAC mandatory, shape+chrome a declared choice). `mkdocs build --strict`.

- [ ] **Step 3: Dogfood.** Add a `routes/` fixture override declaring `# dazzle:returns fragment` (returns inner HTML → renders chromed) and one declaring `page` (full-bleed, un-refused). Add a boot/contract test asserting the chromed one is shell-wrapped and the `page` one is served as-is.

- [ ] **Step 4: Full gate.** `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy src/dazzle && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/ -m "not e2e" -q -p no:cacheprovider` + `mkdocs build --strict`. All green.

- [ ] **Step 5: CHANGELOG + Agent Guidance + bump + ship.** Added entry + an `### Agent Guidance` bullet (RBAC mandatory via `# dazzle:implements`; declare `# dazzle:returns page|fragment|partial|json` for response shape + chrome). `/bump patch`, commit, tag, push.

- [ ] **Step 6: Close #1392.** Comment (items 1–4 all shipped) + `gh issue close 1392`. Memory update.

---

## Self-review
- **Spec coverage:** build_app_page_context (P1) ✓; `# dazzle:returns` marker (P2) ✓; per-kind wrapper + consistency + nudge (P3) ✓; guardrail counter-prior/docs/Agent-Guidance + dogfood + close (P4) ✓; RBAC-orthogonal composition (P3 step 6) ✓; `page` never refused (P3) ✓.
- **Placeholders:** the `_PageRouterConfig` construction in P1 Step 1 and the mount-wiring in P3 Step 4 say "read the actual definition / thread from app_factory" — these are real lookups against named anchors (page_routes.py `_PageRouterConfig`, route_overrides.py L466 mount loop), not vague placeholders.
- **Type consistency:** `returns_kind: str | None`, `_VALID_RETURN_KINDS`, `build_app_page_context(...) -> (PageContext, _ChromeAssets)`, `_wrap_with_response_contract(handler, *, returns_kind, path, page_ctx_builder)` — consistent across P1–P3.
- **Risk note (P1):** the nav-context extraction is the architecture-material piece; the plan keeps it low-risk by sharing only the chrome-asset resolution + nav-model call (not unifying the surface-specific PageContext), so the existing page tests are the parity oracle.
