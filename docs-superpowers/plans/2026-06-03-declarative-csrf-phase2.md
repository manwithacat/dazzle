# Declarative CSRF — Phase 2: Origin-Primary Admission Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Sec-Fetch-Site` + `Origin` the primary CSRF admission gate for session-authed state-changing requests, with the Phase-1 session-bound token as the fallback leg for requests carrying no origin signal.

**Architecture:** A pure `origin_disposition(headers, host, config)` function returns admit / reject / no-signal from the request's `Sec-Fetch-Site` (primary) and `Origin`-vs-`Host` (secondary) signals. `CSRFMiddleware` consults it after the existing exemption + Bearer checks and before token validation: admit → pass; reject → 403; no-signal → fall through to the existing token check. A `trusted_origins` allowlist covers the same-site/embedder case and is threaded from `ServerConfig` like `csrf_exempt_paths`.

**Tech Stack:** Pure ASGI middleware (`src/dazzle/http/runtime/csrf.py`), FastAPI/Starlette, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md` §4.2. **Depends on:** Phase 1 (the session-bound token it falls back to), shipped v0.81.15.

---

## Background the implementer needs

- CSRF today (`csrf.py`, post-Phase-1): `CSRFMiddleware.__call__` handles safe methods, then exempt paths/prefixes/regexes, then `Authorization: Bearer` exempt, then validates `header_token == csrf_token` (double-submit), else 403. Phase 2 inserts the origin gate **between the Bearer check and the token validation**.
- **Security model:** `Sec-Fetch-Site` is browser-set and cannot be forged by a cross-site attacker; `same-origin`/`none` means the request originated from our own page (or a direct navigation/non-fetch), `cross-site` means a different site initiated it, `same-site` means a sibling subdomain (e.g. another tenant). For a same-origin request the `Origin` header's host authority equals the request `Host` header. So the gate needs no per-app config for the common case — comparing `Origin` host:port against `Host` is a per-request same-origin check that handles `tenant_host` multi-tenancy automatically (each tenant's request matches its own Host; a cross-tenant POST does not).
- **Posture (locked in the spec, §4.2):** origin-primary, token-fallback. A same-origin request admits **without** requiring a token (this is the "boring" win). A provably cross-site / same-site request is **rejected even if it carries a token** (defends against token leakage / cross-tenant posting). Only when there is **no** origin signal at all (legacy/non-browser clients) does the gate fall back to the token check. Phase-1 ensures legitimate same-origin requests carry the token anyway (dz-csrf.js / future hx-headers), so nothing legitimate is locked out on the fallback path.

## Files

- **Modify** `src/dazzle/http/runtime/csrf.py` — add `CSRFConfig.trusted_origins`; add the module-level `origin_disposition` helper; wire it into `CSRFMiddleware.__call__`; thread `extra_trusted_origins` through `configure_csrf_for_profile` / `apply_csrf_protection`.
- **Modify** `src/dazzle/http/runtime/server.py` — add `ServerConfig.csrf_trusted_origins` and pass it into `apply_csrf_protection` (mirror `csrf_exempt_paths`, server.py:152/319/495).
- **Test** `tests/unit/test_csrf_origin_gate_phase2.py` (new) — the `origin_disposition` truth table + middleware-level behavior via an ASGI driver.

---

### Task 1: `origin_disposition` helper + `trusted_origins` config

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py` (add `trusted_origins` to `CSRFConfig`; add `origin_disposition` + a small `_origin_host` parser near the other module helpers `_parse_cookies`/`_get_header`)
- Test: `tests/unit/test_csrf_origin_gate_phase2.py`

- [ ] **Step 1: Write the failing test (the truth table)**

```python
# tests/unit/test_csrf_origin_gate_phase2.py
"""Phase 2: Sec-Fetch-Site + Origin admission gate (spec §4.2)."""

from dazzle.http.runtime.csrf import CSRFConfig, origin_disposition


def _h(**kw) -> list[tuple[bytes, bytes]]:
    """Build raw ASGI headers from kwargs (underscores -> dashes)."""
    out = []
    for k, v in kw.items():
        out.append((k.replace("_", "-").encode("latin-1"), v.encode("latin-1")))
    return out


CFG = CSRFConfig(enabled=True)
CFG_TRUSTED = CSRFConfig(enabled=True, trusted_origins=["https://embed.partner.com"])


class TestSecFetchSite:
    def test_same_origin_admits(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="same-origin"), "app.example.com", CFG) is True

    def test_none_admits(self) -> None:
        # Direct nav / typed URL / non-fetch — browser sends "none".
        assert origin_disposition(_h(sec_fetch_site="none"), "app.example.com", CFG) is True

    def test_cross_site_rejects(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="cross-site"), "app.example.com", CFG) is False

    def test_same_site_rejects_by_default(self) -> None:
        # Sibling subdomain (e.g. another tenant) — reject unless trusted.
        assert origin_disposition(_h(sec_fetch_site="same-site"), "app.example.com", CFG) is False


class TestOriginVsHost:
    def test_origin_matches_host_admits(self) -> None:
        hdrs = _h(origin="https://app.example.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is True

    def test_origin_matches_host_with_port_admits(self) -> None:
        hdrs = _h(origin="http://localhost:8000", host="localhost:8000")
        assert origin_disposition(hdrs, "localhost:8000", CFG) is True

    def test_origin_differs_from_host_rejects(self) -> None:
        hdrs = _h(origin="https://evil.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is False

    def test_cross_tenant_subdomain_rejects(self) -> None:
        # tenant-b posting to tenant-a — different host authority.
        hdrs = _h(origin="https://tenant-b.example.com", host="tenant-a.example.com")
        assert origin_disposition(hdrs, "tenant-a.example.com", CFG) is False

    def test_origin_null_rejects(self) -> None:
        # Sandboxed iframe / privacy mode sends Origin: null.
        hdrs = _h(origin="null", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is False


class TestTrustedOrigins:
    def test_trusted_origin_admits_despite_host_mismatch(self) -> None:
        hdrs = _h(origin="https://embed.partner.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is True

    def test_untrusted_origin_still_rejects(self) -> None:
        hdrs = _h(origin="https://other.partner.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is False

    def test_same_site_in_trusted_admits(self) -> None:
        hdrs = _h(sec_fetch_site="same-site", origin="https://embed.partner.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is True


class TestNoSignalFallsBack:
    def test_no_origin_no_fetch_metadata_returns_none(self) -> None:
        # Legacy / non-browser client: no signal -> fall back to token (None).
        assert origin_disposition(_h(host="app.example.com"), "app.example.com", CFG) is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py -v`
Expected: ImportError (`origin_disposition` not defined) / AttributeError (`trusted_origins`).

- [ ] **Step 3: Add `trusted_origins` to `CSRFConfig`**

In `csrf.py`, add to the `CSRFConfig` dataclass (after `exempt_path_regexes`):

```python
    # Phase 2 (declarative CSRF §4.2): origins to admit even when they don't
    # match the request Host (e.g. a same-site embedder). Same-origin requests
    # never need to be listed — they pass via the Origin==Host check. Empty by
    # default: a vanilla app admits only its own origin.
    trusted_origins: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Add the helper functions**

Add near `_get_header` in `csrf.py`:

```python
def _origin_host(origin: str) -> str | None:
    """Return the host[:port] authority of an Origin header, or None.

    `Origin` is `scheme://host[:port]`. Returns None for the opaque value
    "null" (sandboxed iframe / some privacy modes) so it never matches a Host.
    """
    if not origin or origin == "null":
        return None
    # Strip scheme.
    after_scheme = origin.split("://", 1)[-1]
    # Authority ends at the first '/' (there shouldn't be one on an Origin).
    return after_scheme.split("/", 1)[0] or None


def origin_disposition(
    headers: list[tuple[bytes, bytes]],
    host: str | None,
    config: CSRFConfig,
) -> bool | None:
    """Decide admission from the request's origin signals (spec §4.2).

    Returns:
        True  — admit (same-origin / trusted).
        False — reject (provably cross-site / same-site / mismatched origin).
        None  — no origin signal at all; caller should fall back to the token.
    """
    trusted = set(config.trusted_origins)

    sec_fetch_site = _get_header(headers, b"sec-fetch-site")
    origin = _get_header(headers, b"origin")
    origin_host = _origin_host(origin) if origin else None

    if sec_fetch_site is not None:
        if sec_fetch_site in ("same-origin", "none"):
            return True
        # cross-site or same-site: admit only if the Origin is explicitly trusted.
        if origin and origin in trusted:
            return True
        return False

    if origin is not None:
        # No fetch metadata, but an Origin header is present: same-origin iff its
        # host authority equals the request Host. Per-request, so tenant_host
        # multi-tenancy works without configuration.
        if origin in trusted:
            return True
        if origin_host is not None and host is not None and origin_host == host:
            return True
        return False

    # No Sec-Fetch-Site and no Origin — legacy/non-browser. Fall back to token.
    return None
```

- [ ] **Step 5: Run the truth-table tests**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py tests/unit/test_csrf_origin_gate_phase2.py
git commit -m "feat(csrf): origin_disposition gate helper + trusted_origins config (Phase 2)"
```

---

### Task 2: Wire the gate into `CSRFMiddleware`

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py` (`CSRFMiddleware.__call__`)
- Test: `tests/unit/test_csrf_origin_gate_phase2.py`

- [ ] **Step 1: Write the failing middleware test**

Append to `tests/unit/test_csrf_origin_gate_phase2.py`. Model the ASGI driver on `tests/unit/test_csrf_wiring_1337.py`'s `_drive` (read it first). The driver must let you pass arbitrary headers and a cookie + X-CSRF-Token, and return the response status.

```python
import asyncio

from dazzle.http.runtime.csrf import CSRFMiddleware


async def _drive(config, *, method, path, headers_extra):
    headers = list(headers_extra)
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    status = {"code": 0}

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    await CSRFMiddleware(inner, config)(scope, receive, send)
    return status["code"]


class TestMiddlewareOriginGate:
    def test_same_origin_post_admits_without_token(self) -> None:
        # The "boring" win: a same-origin POST with NO csrf token now passes.
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/academicyears",
                headers_extra=_h(sec_fetch_site="same-origin", host="app.example.com"),
            )
        )
        assert status == 200

    def test_cross_site_post_rejected_even_with_valid_token(self) -> None:
        # cross-site is rejected regardless of a matching double-submit token.
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/academicyears",
                headers_extra=_h(
                    sec_fetch_site="cross-site",
                    cookie="dazzle_csrf=abc",
                    x_csrf_token="abc",
                    host="app.example.com",
                ),
            )
        )
        assert status == 403

    def test_no_origin_signal_falls_back_to_token_pass(self) -> None:
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/academicyears",
                headers_extra=_h(cookie="dazzle_csrf=abc", x_csrf_token="abc", host="app.example.com"),
            )
        )
        assert status == 200

    def test_no_origin_signal_falls_back_to_token_reject(self) -> None:
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/academicyears",
                headers_extra=_h(host="app.example.com"),  # no origin, no token
            )
        )
        assert status == 403

    def test_exempt_path_still_exempt_regardless_of_origin(self) -> None:
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/webhooks/stripe",  # exempt prefix
                headers_extra=_h(sec_fetch_site="cross-site", host="app.example.com"),
            )
        )
        assert status == 200

    def test_bearer_still_exempt_regardless_of_origin(self) -> None:
        status = asyncio.run(
            _drive(
                CSRFConfig(enabled=True),
                method="POST",
                path="/api/x",
                headers_extra=_h(authorization="Bearer tok", sec_fetch_site="cross-site", host="app.example.com"),
            )
        )
        assert status == 200
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py::TestMiddlewareOriginGate -v`
Expected: `test_same_origin_post_admits_without_token` FAILS (currently 403 — no token), and `test_cross_site_post_rejected_even_with_valid_token` FAILS (currently 200 — token matches). These two prove the behavior change.

- [ ] **Step 3: Wire the gate into `__call__`**

In `CSRFMiddleware.__call__`, immediately AFTER the `Bearer` exempt block and BEFORE the `# Validate CSRF token` block, insert:

```python
        # Origin-primary admission gate (Phase 2, spec §4.2). Sec-Fetch-Site /
        # Origin are browser-set and unforgeable cross-site, so a same-origin
        # request admits without a token; a provably cross-site/same-site one is
        # rejected even with a token. Only a request with NO origin signal
        # (legacy/non-browser) falls through to the double-submit token check.
        host = _get_header(headers, b"host")
        verdict = origin_disposition(headers, host, self.config)
        if verdict is True:
            await self._pass_through(scope, receive, send, new_token)
            return
        if verdict is False:
            await self._send_403(send)
            return
        # verdict is None -> fall through to token validation below.
```

- [ ] **Step 4: Run the middleware tests + the truth table**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the existing CSRF suites (no regression)**

Run: `python -m pytest tests/unit/test_csrf_exempt_paths.py tests/unit/test_consent_csrf_exempt.py tests/unit/test_csrf_wiring_1337.py tests/unit/test_csrf_middleware_defers_to_route_cookie.py tests/unit/test_csrf_session_binding_phase1.py -v`
Expected: all PASS. **Note:** if any existing test posted with a token but no origin header and expected 200, it still passes (no-signal → token fallback). If a test posted cross-site expecting 200 via token, it will now 403 — inspect whether that test encoded the OLD posture; if so, update it to send a same-origin signal (that's the realistic case) and note it in the commit. Do NOT weaken the gate to make a stale test pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py tests/unit/test_csrf_origin_gate_phase2.py
git commit -m "feat(csrf): origin-primary admission gate in CSRFMiddleware (Phase 2)"
```

---

### Task 3: Thread `csrf_trusted_origins` from `ServerConfig`

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py` (`configure_csrf_for_profile`, `apply_csrf_protection` — add `extra_trusted_origins`)
- Modify: `src/dazzle/http/runtime/server.py` (`ServerConfig.csrf_trusted_origins`; pass through at the `apply_csrf_protection` call)
- Test: `tests/unit/test_csrf_origin_gate_phase2.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConfigThreading:
    def test_extra_trusted_origins_merged(self) -> None:
        from dazzle.http.runtime.csrf import configure_csrf_for_profile

        cfg = configure_csrf_for_profile("standard", extra_trusted_origins=["https://embed.partner.com"])
        assert "https://embed.partner.com" in cfg.trusted_origins

    def test_no_extra_trusted_origins_is_empty(self) -> None:
        from dazzle.http.runtime.csrf import configure_csrf_for_profile

        cfg = configure_csrf_for_profile("standard")
        assert cfg.trusted_origins == []
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py::TestConfigThreading -v`
Expected: FAIL (`configure_csrf_for_profile` has no `extra_trusted_origins`).

- [ ] **Step 3: Add `extra_trusted_origins` to `configure_csrf_for_profile`**

```python
def configure_csrf_for_profile(
    profile: str,
    extra_exempt_paths: list[str] | None = None,
    extra_trusted_origins: list[str] | None = None,
) -> CSRFConfig:
    config = CSRFConfig(enabled=True)
    if extra_exempt_paths:
        for path in extra_exempt_paths:
            if path not in config.exempt_paths:
                config.exempt_paths.append(path)
    if extra_trusted_origins:
        for origin in extra_trusted_origins:
            if origin not in config.trusted_origins:
                config.trusted_origins.append(origin)
    return config
```

- [ ] **Step 4: Thread through `apply_csrf_protection`**

```python
def apply_csrf_protection(
    app: Any,
    profile: str,
    extra_exempt_paths: list[str] | None = None,
    extra_trusted_origins: list[str] | None = None,
) -> None:
    config = configure_csrf_for_profile(
        profile,
        extra_exempt_paths=extra_exempt_paths,
        extra_trusted_origins=extra_trusted_origins,
    )
    app.state.csrf_config = config
    if not config.enabled:
        return
    app.add_middleware(CSRFMiddleware, config=config)
    logger.info("CSRF protection enabled (profile=%s)", profile)
```

- [ ] **Step 5: Add `ServerConfig.csrf_trusted_origins` + pass it**

In `server.py`: add `csrf_trusted_origins: list[str] = field(default_factory=list)` next to `csrf_exempt_paths` (line 152); add `self._csrf_trusted_origins = list(config.csrf_trusted_origins)` next to line 319; and at the `apply_csrf_protection(...)` call (line 495), add `extra_trusted_origins=self._csrf_trusted_origins or None,`.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/unit/test_csrf_origin_gate_phase2.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py src/dazzle/http/runtime/server.py tests/unit/test_csrf_origin_gate_phase2.py
git commit -m "feat(csrf): thread csrf_trusted_origins from ServerConfig (Phase 2)"
```

---

### Task 4: Full-suite gate, CHANGELOG, ship

- [ ] **Step 1: Broad gate** — `python -m pytest tests/ -m "not e2e" -q`. All pass. **Pay attention to integration tests that boot the app and POST** (e.g. `tests/integration/test_auth_*`, chrome-gate tests, any UX-contract POST): these now go through the origin gate. A test client that POSTs without any `Origin`/`Sec-Fetch-Site` header falls back to the token path (unchanged); one that the app drives with a same-origin signal admits. If any integration test starts 403'ing, determine whether it was relying on token-only with no origin header AND no token — if so, it was already exempt or needs a token/origin; fix the test to send a realistic same-origin header, don't weaken the gate. Report each such test touched.
- [ ] **Step 2: Types + lint** — `mypy src/dazzle && ruff check src/ tests/ --fix && ruff format src/ tests/`. Clean.
- [ ] **Step 3: CHANGELOG** — under `## [Unreleased]` → `### Changed`:

```markdown
- **CSRF admission is now origin-primary (declarative-CSRF Phase 2).** `Sec-Fetch-Site` + `Origin` (vs the request `Host`) are the primary gate for session-authed state-changing requests; a same-origin request admits without a token, a provably cross-site/same-site one is rejected even with one, and only a request with no origin signal falls back to the Phase-1 session-bound double-submit token. Per-request `Origin`==`Host` comparison makes `tenant_host` multi-tenancy work without configuration; a `csrf_trusted_origins` allowlist (`ServerConfig.csrf_trusted_origins`) covers same-site embedders. See `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md` §4.2.
```

- [ ] **Step 4: Ship** — `/bump patch`, commit referencing the spec, push to main, monitor CI to green (watch the integration + PostgreSQL jobs that exercise real POSTs), leave the worktree clean.

---

## Subsequent phases

- **Phase 3** — `csrf_disposition` predicate replacing the hardcoded exempt lists; `<body hx-headers>` transport; retire `dz-csrf.js`; shared-predicate middleware refactor. Depends on this phase's gate.
- **Phase 4** — compliance-report CSRF section; validate/lint findings; `ESCAPE_HATCH` DSL knob; guarded-action seam; `regenerate_session_csrf` rowcount guard (Phase-1 M3); test-harness refactor; ADR-0033.

## Self-review notes

- **Spec coverage (§4.2):** Sec-Fetch-Site primary (Task 1/2), Origin==Host secondary (Task 1), token fallback on no-signal (Task 2), trusted-origins allowlist + config threading (Task 1/3), tenant_host handled by per-request Origin==Host (no extra code).
- **Posture:** origin-primary, token-fallback — same-origin admits tokenless; cross/same-site rejected even with token; pinned by `test_same_origin_post_admits_without_token` + `test_cross_site_post_rejected_even_with_valid_token`.
- **No placeholders:** every step has real code; the "inspect a stale test" guidance in Task 2 Step 5 / Task 4 Step 1 is explicit (send a realistic same-origin header; never weaken the gate).
- **Type consistency:** `origin_disposition(headers, host, config) -> bool | None` used identically in Task 1 (defn), Task 2 (call site passes `host = _get_header(headers, b"host")`). `trusted_origins: list[str]` consistent across config, helper, threading.
- **Risk:** the behavior change (same-origin admits tokenless; cross-site rejected with token) could surface latent assumptions in integration tests; Task 2 Step 5 + Task 4 Step 1 require inspecting, not silencing, any newly-403ing test.
