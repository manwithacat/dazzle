# Declarative CSRF — Phase 3 (redefined): Disposition Model + Static Policy Audit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Consolidate Phase-2's origin gate + the hardcoded exempt lists into a single, auditable `csrf_disposition` predicate, and surface every CSRF disposition + its rationale in the RBAC/compliance report — so an agent (or human) can read *what* is exempt from CSRF and *why*.

**Architecture:** Two pure functions — `csrf_disposition(method, path, headers, config) -> Disposition` (classify from auth-class signals + disposition-labeled config rules) and `csrf_admits(disposition, headers, host, csrf_token, config) -> bool` (admit/reject). `CSRFMiddleware.__call__` is refactored to `classify → admit?`, behavior-preserving. A pure `render_csrf_policy(config)` emits the disposition rules as a compliance-report section.

**Tech Stack:** Pure ASGI middleware (`src/dazzle/http/runtime/csrf.py`), `src/dazzle/rbac/report.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md` §4.1, §4.5, §6. **Depends on:** Phase 1 (v0.81.15) + Phase 2 (v0.81.16).

## Scope decision (read first)

- The spec's original Phase 3 bundled a `<body hx-headers>` **transport switch** (retire `dz-csrf.js`). Investigation (2026-06-03) found that switch would replace one central bundled script with per-site token threading across 6+ `Page`-construction sites, for marginal benefit — and post-Phase-2 the token is only a fallback leg. **Decision (user-approved): keep `dz-csrf.js`; drop the transport switch.** This phase is the disposition-model + audit half only.
- **`UNAUTH_MUTATING` and `ESCAPE_HATCH`** are defined in the `Disposition` enum for completeness but are **NOT produced by the classifier in this phase** — they need request-time session-presence detection and the DSL escape-hatch knob, which land in Phase 4. The classifier returns only `NA_BEARER` / `NA_SIGNATURE` / `NA_PREAUTH` / `PROTECTED_SESSION`. This is documented in the enum + classifier.
- **Behavior-preserving:** every request that admits/rejects today must admit/reject identically after the refactor. The existing CSRF suites (`test_csrf_exempt_paths`, `test_csrf_origin_gate_phase2`, `test_csrf_wiring_1337`, `test_csrf_session_binding_phase1`, `test_csrf_middleware_defers_to_route_cookie`, `test_consent_csrf_exempt`) are the equivalence oracle and MUST stay green.

## Files

- **Modify** `src/dazzle/http/runtime/csrf.py` — `Disposition` enum; `na_signature_prefixes`/`na_signature_regexes` config fields (webhooks + sign moved here from the generic lists); `csrf_disposition` + `csrf_admits`; refactor `CSRFMiddleware.__call__`; `render_csrf_policy`.
- **Modify** `src/dazzle/rbac/report.py` — add a `_render_csrf_policy` section to `generate_report`.
- **Modify** `tests/unit/test_csrf_exempt_paths.py` — update for webhooks/sign moving to the signature fields (same paths, new field names).
- **Test** `tests/unit/test_csrf_disposition_phase3.py` (new), `tests/unit/test_csrf_policy_report_phase3.py` (new).

---

### Task 1: `Disposition` enum + signature config fields + `csrf_disposition` / `csrf_admits`

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py`
- Test: `tests/unit/test_csrf_disposition_phase3.py`

- [ ] **Step 1: Write the failing test (classification truth table + admits)**

```python
# tests/unit/test_csrf_disposition_phase3.py
"""Phase 3: CSRF disposition model (spec §4.1)."""

from dazzle.http.runtime.csrf import (
    CSRFConfig,
    Disposition,
    csrf_admits,
    csrf_disposition,
)


def _h(**kw) -> list[tuple[bytes, bytes]]:
    out = []
    for k, v in kw.items():
        out.append((k.replace("_", "-").encode("latin-1"), v.encode("latin-1")))
    return out


CFG = CSRFConfig(enabled=True)


class TestCsrfDisposition:
    def test_bearer_is_na_bearer(self) -> None:
        d = csrf_disposition("POST", "/anything", _h(authorization="Bearer x"), CFG)
        assert d is Disposition.NA_BEARER

    def test_webhook_is_na_signature(self) -> None:
        d = csrf_disposition("POST", "/webhooks/stripe", _h(), CFG)
        assert d is Disposition.NA_SIGNATURE

    def test_sign_route_is_na_signature(self) -> None:
        path = "/api/sign/contract/12345678-1234-1234-1234-123456789abc"
        d = csrf_disposition("POST", path, _h(), CFG)
        assert d is Disposition.NA_SIGNATURE

    def test_auth_prefix_is_na_preauth(self) -> None:
        d = csrf_disposition("POST", "/auth/login", _h(), CFG)
        assert d is Disposition.NA_PREAUTH

    def test_consent_exact_is_na_preauth(self) -> None:
        d = csrf_disposition("POST", "/_dazzle/consent", _h(), CFG)
        assert d is Disposition.NA_PREAUTH

    def test_ordinary_mutating_is_protected_session(self) -> None:
        d = csrf_disposition("POST", "/academicyears", _h(), CFG)
        assert d is Disposition.PROTECTED_SESSION

    def test_bearer_wins_over_signature_path(self) -> None:
        # A Bearer credential classifies as NA_BEARER even on a webhook path.
        d = csrf_disposition("POST", "/webhooks/x", _h(authorization="Bearer t"), CFG)
        assert d is Disposition.NA_BEARER


class TestCsrfAdmits:
    def test_na_dispositions_admit(self) -> None:
        for d in (Disposition.NA_BEARER, Disposition.NA_SIGNATURE, Disposition.NA_PREAUTH):
            assert csrf_admits(d, _h(host="app.example.com"), "app.example.com", None, CFG) is True

    def test_protected_session_same_origin_admits_without_token(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(sec_fetch_site="same-origin", host="app.example.com"),
            "app.example.com",
            None,
            CFG,
        )
        assert ok is True

    def test_protected_session_cross_site_rejected_with_token(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(sec_fetch_site="cross-site", host="app.example.com"),
            "app.example.com",
            "tok",  # cookie token present
            CFG,
        )
        # The header would also need to match; cross-site rejects regardless.
        assert ok is False

    def test_protected_session_no_signal_token_match_admits(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(host="app.example.com", x_csrf_token="tok"),
            "app.example.com",
            "tok",  # cookie value
            CFG,
        )
        assert ok is True

    def test_protected_session_no_signal_token_mismatch_rejects(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(host="app.example.com", x_csrf_token="WRONG"),
            "app.example.com",
            "tok",
            CFG,
        )
        assert ok is False
```

- [ ] **Step 2: Run → confirm fail** — `python -m pytest tests/unit/test_csrf_disposition_phase3.py -v` (ImportError on `Disposition`/`csrf_disposition`/`csrf_admits`).

- [ ] **Step 3: Add the `Disposition` enum** (top of csrf.py, after imports):

```python
from enum import Enum


class Disposition(str, Enum):
    """How a state-changing request relates to CSRF (spec §4.1).

    CSRF is a control on *ambient authority* (the session cookie). A request
    authenticated by a caller-presented credential is structurally immune, so it
    derives an ``NA_*`` disposition rather than being CSRF-validated.

    NOTE: ``UNAUTH_MUTATING`` and ``ESCAPE_HATCH`` are defined for completeness
    but are NOT produced by ``csrf_disposition`` in this phase — they require
    request-time session-presence detection and the DSL escape-hatch knob, which
    land in Phase 4. The classifier currently returns only the other four.
    """

    PROTECTED_SESSION = "protected_session"  # ambient session → origin gate + token
    NA_BEARER = "na_bearer"  # Authorization: Bearer — caller-presented credential
    NA_SIGNATURE = "na_signature"  # HMAC/signature-authed (webhooks, doc signing)
    NA_PREAUTH = "na_preauth"  # pre-session / idempotent cookie-setter / infra
    UNAUTH_MUTATING = "unauth_mutating"  # Phase 4: mutating, no auth — admit + audit-flag
    ESCAPE_HATCH = "escape_hatch"  # Phase 4: explicit cross-origin-allowed
```

- [ ] **Step 4: Move webhooks/sign into signature fields on `CSRFConfig`**

Remove `"/webhooks/"` and `"/api/v1/webhooks/"` from `exempt_path_prefixes`, and the two `r"^/sign/..."`/`r"^/api/sign/..."` regexes from `exempt_path_regexes`. Add two new fields (keep the existing explanatory comments, moved):

```python
    # Signature-authenticated endpoints (spec §4.1 NA_SIGNATURE). The HMAC /
    # shared-secret signature IS the control; CSRF is categorically N/A. Moved
    # out of the generic exempt lists so the disposition is explicit + auditable.
    na_signature_prefixes: list[str] = field(
        default_factory=lambda: ["/webhooks/", "/api/v1/webhooks/"]
    )
    na_signature_regexes: list[str] = field(
        default_factory=lambda: [
            r"^/sign/[^/]+/" + _UUID_RE + r"$",
            r"^/api/sign/[^/]+/" + _UUID_RE + r"$",
        ]
    )
```

The remaining `exempt_paths` / `exempt_path_prefixes` / `exempt_path_regexes` entries (health, docs, consent, i18n, auth, qa, test, dev, feedbackreports) keep their NA_PREAUTH meaning. `CSRFMiddleware.__init__` already precompiles `exempt_path_regexes`; add a parallel `self._na_signature_regexes = [re.compile(p) for p in config.na_signature_regexes]`.

- [ ] **Step 5: Add `csrf_disposition` + `csrf_admits`** (module-level, after `origin_disposition`):

```python
def csrf_disposition(
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    config: CSRFConfig,
    *,
    signature_regexes: list[Any] | None = None,
) -> Disposition:
    """Classify a request's CSRF disposition from its auth-class signals (§4.1).

    Returns one of NA_BEARER / NA_SIGNATURE / NA_PREAUTH / PROTECTED_SESSION.
    (UNAUTH_MUTATING / ESCAPE_HATCH are Phase 4 — see the enum.) Default-deny:
    anything not positively classified as NA_* is PROTECTED_SESSION.

    ``signature_regexes`` accepts the middleware's precompiled patterns; when
    None it compiles from ``config.na_signature_regexes`` (used by callers
    without a precompile cache, e.g. the policy renderer / tests).
    """
    # Bearer credential — caller-presented, CSRF N/A. Wins over path-based rules.
    auth = _get_header(headers, b"authorization") or ""
    if auth.startswith("Bearer "):
        return Disposition.NA_BEARER

    # Signature-authenticated (webhooks, doc signing).
    for prefix in config.na_signature_prefixes:
        if path.startswith(prefix):
            return Disposition.NA_SIGNATURE
    sig_res = signature_regexes
    if sig_res is None:
        sig_res = [re.compile(p) for p in config.na_signature_regexes]
    for pattern in sig_res:
        if pattern.fullmatch(path):
            return Disposition.NA_SIGNATURE

    # Pre-session / idempotent / infra exemptions (the remaining lists).
    if path in config.exempt_paths:
        return Disposition.NA_PREAUTH
    for prefix in config.exempt_path_prefixes:
        if path.startswith(prefix):
            return Disposition.NA_PREAUTH

    return Disposition.PROTECTED_SESSION


def csrf_admits(
    disposition: Disposition,
    headers: list[tuple[bytes, bytes]],
    host: str | None,
    csrf_cookie: str | None,
    config: CSRFConfig,
) -> bool:
    """Decide admission for a classified request (spec §4.2/§4.5).

    NA_* / ESCAPE_HATCH / UNAUTH_MUTATING admit. PROTECTED_SESSION runs the
    origin-primary gate (Phase 2) with the double-submit token as fallback.
    """
    if disposition is not Disposition.PROTECTED_SESSION:
        # NA_* (and the Phase-4 admit-with-audit dispositions) all admit here.
        return True

    verdict = origin_disposition(headers, host, config)
    if verdict is True:
        return True
    if verdict is False:
        return False
    # No origin signal — fall back to double-submit token.
    header_token = _get_header(headers, config.header_name.lower().encode())
    return bool(header_token and csrf_cookie and header_token == csrf_cookie)
```

- [ ] **Step 6: Run → all pass** — `python -m pytest tests/unit/test_csrf_disposition_phase3.py -v`.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py tests/unit/test_csrf_disposition_phase3.py
git commit -m "feat(csrf): Disposition enum + csrf_disposition/csrf_admits predicate (Phase 3)"
```

---

### Task 2: Refactor `CSRFMiddleware.__call__` onto the predicate (behavior-preserving)

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py` (`CSRFMiddleware.__call__`, `__init__`)
- Modify: `tests/unit/test_csrf_exempt_paths.py` (webhooks/sign now in `na_signature_*`)
- Test: existing CSRF suites are the equivalence oracle.

- [ ] **Step 1: Update `test_csrf_exempt_paths.py` for the moved fields.** Read it; any assertion that `"/webhooks/"` / `"/api/v1/webhooks/"` is in `exempt_path_prefixes`, or that a `^/sign/` / `^/api/sign/` regex is in `exempt_path_regexes`, must move to assert membership in `na_signature_prefixes` / `na_signature_regexes`. The signing-exemption behavioral tests (a sign URL is exempt; a deeper/non-UUID path is NOT) should still pass through the middleware unchanged — keep them, they're the behavior oracle. Run it → confirm it now reflects the new field locations.

- [ ] **Step 2: Refactor `__call__`.** Replace the block from `# Check exemptions` through the end of `# Validate CSRF token` with the predicate. The new body (after the safe-method passthrough, keeping the cookie-parse/new_token logic above it unchanged):

```python
        # Classify + admit via the disposition predicate (spec §4.1/§4.5).
        disposition = csrf_disposition(
            scope.get("method", "GET"),
            path,
            headers,
            self.config,
            signature_regexes=self._na_signature_regexes,
        )
        host = _get_header(headers, b"host")
        if csrf_admits(disposition, headers, host, csrf_token, self.config):
            await self._pass_through(scope, receive, send, new_token)
            return
        await self._send_403(send)
        return
```

Delete the now-dead inline blocks (exact-path / prefix / regex exemptions, the Bearer check, the Phase-2 origin gate block, and the old token-validation block) — they are all now inside `csrf_disposition` + `csrf_admits`. Keep `__init__`'s `self._exempt_regexes` (still used for the NA_PREAUTH regex list if any remain — note: after Task 1 there are no NA_PREAUTH regexes left, so `exempt_path_regexes` defaults empty; the `csrf_disposition` above does not check NA_PREAUTH regexes — confirm none remain, and if `exempt_path_regexes` is now always empty, you may drop the `self._exempt_regexes` precompile, but ONLY if nothing else references it; otherwise leave it). Add `self._na_signature_regexes = [re.compile(p) for p in config.na_signature_regexes]` in `__init__`.

IMPORTANT subtlety: the old `csrf_token` variable (the cookie value, possibly a freshly-minted `new_token`) is what `csrf_admits` must receive as `csrf_cookie` so the token-fallback comparison is identical to before. Pass the same `csrf_token` the old validation used.

- [ ] **Step 3: Run the FULL existing CSRF suite (the equivalence oracle)**

Run: `python -m pytest tests/unit/test_csrf_exempt_paths.py tests/unit/test_consent_csrf_exempt.py tests/unit/test_csrf_origin_gate_phase2.py tests/unit/test_csrf_wiring_1337.py tests/unit/test_csrf_session_binding_phase1.py tests/unit/test_csrf_middleware_defers_to_route_cookie.py tests/unit/test_csrf_disposition_phase3.py -v`
Expected: ALL pass. Any failure means the refactor changed behavior — fix the refactor (NOT the test) until green. If a test genuinely encoded a now-relocated field (Task 1 handled exempt-paths), that's the only legitimate test edit.

- [ ] **Step 4: mypy + ruff** — `mypy src/dazzle && ruff check src/ tests/ --fix && ruff format src/ tests/`. Clean.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py tests/unit/test_csrf_exempt_paths.py
git commit -m "refactor(csrf): middleware __call__ onto csrf_disposition/csrf_admits (Phase 3)"
```

---

### Task 3: Static CSRF policy audit in the compliance report

**Files:**
- Modify: `src/dazzle/http/runtime/csrf.py` (add `render_csrf_policy`)
- Modify: `src/dazzle/rbac/report.py` (call it from `generate_report`)
- Test: `tests/unit/test_csrf_policy_report_phase3.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_csrf_policy_report_phase3.py
"""Phase 3: the CSRF disposition policy is auditable in the compliance report."""

from dazzle.http.runtime.csrf import CSRFConfig, render_csrf_policy


class TestRenderCsrfPolicy:
    def test_lists_signature_and_preauth_rules_with_dispositions(self) -> None:
        md = "\n".join(render_csrf_policy(CSRFConfig(enabled=True)))
        assert "CSRF" in md
        # Signature rules surfaced with their disposition.
        assert "/webhooks/" in md
        assert "NA_SIGNATURE" in md or "na_signature" in md
        # Pre-auth rules surfaced.
        assert "/auth/" in md
        assert "NA_PREAUTH" in md or "na_preauth" in md
        # The default-deny posture is stated.
        assert "PROTECTED_SESSION" in md or "protected_session" in md

    def test_empty_when_disabled(self) -> None:
        md = render_csrf_policy(CSRFConfig(enabled=False))
        # Either an empty list or a clearly-marked "disabled" notice — never a
        # misleading "everything protected" claim.
        assert md == [] or any("disabled" in line.lower() for line in md)
```

- [ ] **Step 2: Run → fail** — `python -m pytest tests/unit/test_csrf_policy_report_phase3.py -v` (ImportError on `render_csrf_policy`).

- [ ] **Step 3: Add `render_csrf_policy`** to csrf.py:

```python
def render_csrf_policy(config: CSRFConfig) -> list[str]:
    """Render the CSRF disposition policy as Markdown lines for the audit report.

    Lists every exemption rule with its derived disposition and the rationale,
    so an agent/auditor can see WHAT is exempt from CSRF and WHY — rather than
    inferring protection from absence (spec §6).
    """
    if not config.enabled:
        return ["## CSRF Policy", "", "> CSRF protection is **disabled**.", ""]
    lines = [
        "## CSRF Policy",
        "",
        "State-changing requests default to **PROTECTED_SESSION** (origin-primary "
        "gate + session-bound double-submit token). The rules below derive a "
        "non-protected disposition because the request is authenticated by a "
        "caller-presented credential (CSRF is categorically N/A):",
        "",
        "| Rule | Match | Disposition |",
        "| --- | --- | --- |",
    ]
    for prefix in config.na_signature_prefixes:
        lines.append(f"| `{prefix}` | prefix | NA_SIGNATURE |")
    for rx in config.na_signature_regexes:
        lines.append(f"| `{rx}` | regex | NA_SIGNATURE |")
    for path in config.exempt_paths:
        lines.append(f"| `{path}` | exact | NA_PREAUTH |")
    for prefix in config.exempt_path_prefixes:
        lines.append(f"| `{prefix}` | prefix | NA_PREAUTH |")
    if config.trusted_origins:
        lines.append("")
        lines.append("Trusted cross-origin embedders (admitted despite Host mismatch):")
        for origin in config.trusted_origins:
            lines.append(f"- `{origin}`")
    lines.append("")
    return lines
```

- [ ] **Step 4: Wire it into the compliance report.** In `src/dazzle/rbac/report.py`, import `render_csrf_policy` and `CSRFConfig` (lazy import inside `generate_report` to avoid a back-runtime import at module load if that's the existing convention — check the file's imports; if `report.py` already imports from `dazzle.http.runtime`, follow suit, else lazy-import). Add, after `_render_methodology()` (or before it), a CSRF section. Since `generate_report` takes a `VerificationReport` (no CSRFConfig), render the policy from a **default** `CSRFConfig(enabled=True)` (the framework defaults are what the audit documents) unless a config is threaded later:

```python
    from dazzle.http.runtime.csrf import CSRFConfig, render_csrf_policy

    lines.extend(render_csrf_policy(CSRFConfig(enabled=True)))
```

(If `report.py` must stay free of a back-runtime import for layering reasons — check whether `rbac/` already depends on `back/runtime` elsewhere; the RBAC package does verify a running app, so it likely may. If it genuinely must not, instead expose `render_csrf_policy` results via a small parameter on `generate_report` and have the CLI caller pass the policy lines. Prefer the direct import if the dependency already exists.)

- [ ] **Step 5: Run the report test + the rbac report tests**

Run: `python -m pytest tests/unit/test_csrf_policy_report_phase3.py -v` and any existing `test_rbac*report*` / `tests/unit/test_rbac_*` that exercises `generate_report`.
Expected: pass; the existing report tests should still pass (a new section appended). If an existing report test asserts the EXACT full report text, update it to include the new section.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/csrf.py src/dazzle/rbac/report.py tests/unit/test_csrf_policy_report_phase3.py
git commit -m "feat(csrf): static CSRF disposition policy in the compliance report (Phase 3)"
```

---

### Task 4: Full-suite gate, CHANGELOG, ship

- [ ] **Step 1:** `python -m pytest tests/ -m "not e2e" -q` — all pass. The CSRF middleware refactor is behavior-preserving; if any integration/security test changes outcome, the refactor regressed — fix it, don't silence the test.
- [ ] **Step 2:** `mypy src/dazzle && ruff check src/ tests/ --fix && ruff format src/ tests/` — clean.
- [ ] **Step 3: CHANGELOG** under `## [Unreleased]` → `### Changed`:

```markdown
- **CSRF admission is now a single auditable disposition predicate (declarative-CSRF Phase 3).** `CSRFMiddleware` classifies every state-changing request into a `Disposition` (`NA_BEARER` / `NA_SIGNATURE` / `NA_PREAUTH` / `PROTECTED_SESSION`) via `csrf_disposition`, then admits via `csrf_admits` (origin-primary gate + token fallback for `PROTECTED_SESSION`, admit for the rest) — consolidating the Phase-2 gate, the Bearer check, and the former hardcoded exempt lists into one predicate. Behavior is unchanged; the win is that the CSRF policy is now explicit and surfaced in the RBAC compliance report (`render_csrf_policy`) so every exemption and its rationale is auditable rather than inferred from absence. Signature-authenticated routes (webhooks, doc signing) now carry an explicit `NA_SIGNATURE` disposition. Spec §4.1/§4.5/§6. (The `<body hx-headers>` transport switch from the original plan was dropped — `dz-csrf.js` is a central bundled script and the swap would have scattered it; `UNAUTH_MUTATING`/`ESCAPE_HATCH` dispositions + the DSL escape hatch land in Phase 4.)
```

- [ ] **Step 4: Ship** — `/bump patch`, commit, push to main, CI green, clean worktree.

---

## Self-review notes

- **Spec coverage:** Disposition enum (§4.1) — Task 1; `csrf_disposition`/`csrf_admits` two-function model (§4.5) — Task 1; middleware consolidation (§4.5) — Task 2; exempt-list → disposition migration (§6.1) — Tasks 1-2 (signature split out; rest = NA_PREAUTH); auditable disposition surface in compliance report (§6) — Task 3. Deferred to Phase 4 (documented): UNAUTH_MUTATING/ESCAPE_HATCH runtime classification, the DSL escape hatch, the guarded-action seam, ADR-0033, per-route enumeration, `regenerate_session_csrf` rowcount guard (M3).
- **Behavior-preservation is the central risk** — Task 2 Step 3 runs the entire existing CSRF suite as the equivalence oracle and forbids editing those tests to pass (except the Task-1 field relocation in test_csrf_exempt_paths).
- **No placeholders:** every step has real code; the report-import layering caveat (Task 3 Step 4) gives an explicit fallback rather than leaving it open.
- **Type consistency:** `csrf_disposition(...) -> Disposition` and `csrf_admits(disposition, headers, host, csrf_cookie, config) -> bool` used identically across Task 1 (defn), Task 2 (call site passes `csrf_token` as `csrf_cookie`), and the policy renderer. `na_signature_prefixes`/`na_signature_regexes` consistent across config, classifier, `__init__` precompile, and the renderer.
