# `dazzle auth connection doctor --probe` — live reachability — Design

**Issue:** #1342 (enterprise auth deferred backlog) — Tooling item "`doctor --probe`".

## Goal

Add an **opt-in** live reachability probe to `dazzle auth connection doctor`, layered on top of the existing network-free config audit. The probe confirms the IdP endpoints a connection points at are actually reachable/serving — the one thing the static audit cannot tell you ("config looks complete" ≠ "the IdP answers").

## Why opt-in + CLI-only

- `connection_doctor.diagnose_connection` is **pure + network-free by design** (its docstring promises "no network I/O — no SSRF surface"), and the **org-admin web readiness panel** reuses it. Network I/O on a request path is an SSRF surface. So the probe must NOT live in `connection_doctor.py` and must NOT be reachable from the web panel — it is a **CLI-only, explicitly-opt-in** (`--probe`) operator action. Default behaviour is unchanged (no network).

## SSRF defense — reuse, don't reinvent

The IdP-metadata-import path already ships a hardened fetcher, `saml_metadata.validate_metadata_url` + `fetch_idp_metadata`:
- https-only; rejects userinfo / backslash forms (CVE-2023-24329 split class);
- resolves the host and rejects any non-`is_global` IP (allowlist-by-exclusion — also catches CGNAT/reserved that `is_private` misses); unwraps IPv4-mapped IPv6;
- no redirects (a redirect could bounce to an internal host); bounded timeout; streaming size cap (decompression-amplification guard).

The probe **reuses `validate_metadata_url`** for its SSRF gate. Same documented residual: validation resolves *now*, httpx re-resolves at connect (DNS-rebind window) — acceptable for an operator-run CLI with a trusted resolver, exactly as the import path already accepts.

## What gets probed, per type

| Type | Target | Check |
|------|--------|-------|
| **OIDC** | discovery doc: `config["discovery_url"]` else `{issuer}/.well-known/openid-configuration` | fetch → 200 + valid JSON containing `authorization_endpoint` **and** `token_endpoint`. A document we *consume*, so content is validated. |
| **SAML** | `config["idp_sso_url"]` (the persisted SSO endpoint; `idp_metadata_url` is **not** stored — it's create-time only) | **reachability**: any HTTP status = reachable (an SSO endpoint with no SAMLRequest legitimately returns 200/400/405); only DNS/connect/timeout/SSRF-reject = fail. `idp_slo_url` probed too when present (recommended). |
| **SCIM** | — | informational: SCIM is **inbound** (the IdP pushes to us); there is no outbound endpoint to probe. |

## Architecture

New module `src/dazzle/http/runtime/auth/connection_probe.py`:

- `probe_connection(connection, *, http_get=_default_http_get) -> tuple[Check, ...]` — returns `connection_doctor.Check` records (reused dataclass, for output consistency). `http_get` is **injected** so tests need no network. All probe checks are `level="recommended"` — a transient IdP outage must not flip the activation-ready/exit-0 gate, which means *config* completeness. Reachability is supplementary live evidence.
- `_default_http_get(url, *, timeout=10.0) -> tuple[int, bytes]` — `validate_metadata_url(url)` (SSRF gate) then httpx GET, `follow_redirects=False`, `Accept-Encoding: identity`, streaming size-cap (1 MiB), returns `(status_code, body)`. Does **not** `raise_for_status` (the caller decides what a status means — reachability vs content). Connect/DNS errors and `SamlMetadataError` (SSRF reject) propagate as a typed `ProbeError`.
- One check per probed endpoint: `ok` (reachable / valid), `warn` (unreachable / invalid / SSRF-rejected), with a concrete `detail` (status code or error reason). Never echoes a secret (the probe only touches non-secret config URLs).

CLI (`src/dazzle/cli/auth_connection.py`, `doctor` command):
- Add `--probe` flag (default `False`). When set, after the static diagnosis, call `probe_connection(conn)` and render the probe checks in their own **"Live probe (network)"** section (human + `--json` under a `probe` key).
- Exit code stays `0 ⟺ diagnosis.ready` (config-based, unchanged). The probe is informational. Documented explicitly so no one wires CI to gate on transient IdP uptime via this exit code.
- `--probe` without network access / with an unreachable IdP yields `warn` checks, never a crash or a 500-class stack leak.

## Non-goals

- **No** persisted `idp_metadata_url` re-fetch/diff (the URL isn't stored; out of scope — a separate "metadata freshness" feature if ever wanted).
- **No** SAML protocol round-trip (we don't send a real AuthnRequest); reachability only.
- **No** web-panel exposure (SSRF on a request path — explicitly excluded).
- **No** exit-code gating on probe results (config-readiness only).

## Testing

`tests/unit/test_connection_probe.py` — `probe_connection` with an **injected** `http_get`:
- OIDC: discovery 200 + valid endpoints → ok; 404/500 → warn; 200 but missing `token_endpoint` → warn; `discovery_url` overrides issuer-derived.
- SAML: `idp_sso_url` returns 200/405 → reachable (ok); injected connect error → warn (unreachable); `idp_slo_url` present → extra check.
- SCIM: informational n/a check, no `http_get` call.
- SSRF: injected `http_get` raising `ProbeError` (simulating a `validate_metadata_url` reject) → warn with the reason, never propagates.
- The SSRF gate itself (`validate_metadata_url`) is already covered by `test_saml_metadata*`; reused, not re-tested.

CLI smoke (extend `test_auth_connection*` if present): `doctor --probe` with a stubbed store + injected probe renders the section and keeps exit code config-based.
