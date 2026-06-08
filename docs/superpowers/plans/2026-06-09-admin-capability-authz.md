# Admin-capability authorization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the flat `org_admin_roles` gate into a small, IAM-flavored capability model (`manage_members` + `manage_connections`) so a multi-tenant app can distinguish a business administrator from an IT/technical admin — with zero behavior change for existing apps.

**Architecture:** A pure `AdminPolicy` value object resolves `capability → personas` from the manifest (`org_admin_roles` is the default for any unlisted capability), built once at boot onto `app.state.admin_policy`. Framework org-admin routes gate on `policy.may(capability, effective_roles)` instead of the flat list. Default-deny, fail-closed. Spec: `docs/superpowers/specs/2026-06-09-admin-capability-authz-design.md`.

**Tech Stack:** Python 3.12, dataclasses, FastAPI/Starlette routes, pytest. PostgreSQL-only runtime (no schema change here — this is config + authz logic).

---

## File structure

| File | Responsibility |
|---|---|
| `src/dazzle/back/runtime/auth/admin_policy.py` (create) | `CAPABILITIES` tuple + `AdminPolicy` value object (`from_config`, `may`, `roles_for`) + `unknown_admin_personas` helper. Pure, no I/O. |
| `src/dazzle/core/manifest.py` (modify) | `AuthConfig.admin_capabilities` field + parse it in the auth loader. |
| `src/dazzle/back/runtime/subsystems/auth.py` (modify) | Build `app.state.admin_policy`; log a warning for unknown personas. |
| `src/dazzle/back/runtime/auth/member_admin.py` (modify) | Re-target `active_admins`/`would_orphan_org` param to the resolved `manage_members` persona set. |
| `src/dazzle/back/runtime/auth/member_admin_routes.py` (modify) | Gate on `manage_members` via `AdminPolicy`. |
| `src/dazzle/back/runtime/auth/invitation_routes.py` (modify) | Gate on `manage_members` via `AdminPolicy`. |
| `src/dazzle/back/runtime/auth/connection_admin_routes.py` (modify) | Gate on `manage_connections` via `AdminPolicy`. |
| `src/dazzle/back/runtime/auth/invitations.py` (modify) | Remove `may_manage_members` (clean break, ADR-0003). |
| `tests/unit/test_admin_policy.py` (create) | AdminPolicy unit tests. |
| `tests/unit/test_admin_capability_drift.py` (create) | Drift gate: every capability consumed + invariants. |

---

## Task 1: `AdminPolicy` core

**Files:**
- Create: `src/dazzle/back/runtime/auth/admin_policy.py`
- Test: `tests/unit/test_admin_policy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_admin_policy.py
"""Tests for the admin-capability authorization value object (#1342-adjacent)."""

from dazzle.back.runtime.auth.admin_policy import (
    CAPABILITIES,
    AdminPolicy,
    unknown_admin_personas,
)


def test_capabilities_are_the_two_framework_capabilities():
    assert CAPABILITIES == ("manage_members", "manage_connections")


def test_no_map_falls_back_to_org_admin_roles_for_every_capability():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    for cap in CAPABILITIES:
        assert p.may(cap, ["org_admin"]) is True
        assert p.may(cap, ["member"]) is False  # default-deny


def test_explicit_map_is_honored_per_capability():
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"],
        admin_capabilities={"manage_connections": ["it_admin"]},
    )
    # mapped capability uses its own set
    assert p.may("manage_connections", ["it_admin"]) is True
    assert p.may("manage_connections", ["org_admin"]) is False
    # an UNLISTED capability falls back to org_admin_roles (not empty)
    assert p.may("manage_members", ["org_admin"]) is True
    assert p.may("manage_members", ["it_admin"]) is False


def test_fail_closed_when_nothing_configured():
    p = AdminPolicy.from_config(org_admin_roles=[], admin_capabilities={})
    assert p.may("manage_members", ["org_admin"]) is False
    assert p.may("manage_connections", ["anyone"]) is False


def test_unknown_capability_denies():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    assert p.may("manage_billing", ["org_admin"]) is False


def test_roles_for_returns_resolved_set():
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"],
        admin_capabilities={"manage_members": ["business_admin"]},
    )
    assert p.roles_for("manage_members") == frozenset({"business_admin"})
    assert p.roles_for("manage_connections") == frozenset({"org_admin"})  # fallback
    assert p.roles_for("nope") == frozenset()


def test_empty_role_list_in_map_falls_back_not_locks_out():
    # an explicitly-empty list is treated as "unset" → fall back to org_admin_roles
    p = AdminPolicy.from_config(
        org_admin_roles=["org_admin"], admin_capabilities={"manage_members": []}
    )
    assert p.may("manage_members", ["org_admin"]) is True


def test_unknown_admin_personas_flags_typos():
    declared = {"org_admin", "it_admin", "business_admin"}
    caps = {"manage_connections": ["it_admin", "typo_admin"], "manage_members": ["business_admin"]}
    assert unknown_admin_personas(caps, declared) == {"typo_admin"}
    assert unknown_admin_personas({}, declared) == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_admin_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.back.runtime.auth.admin_policy'`.

- [ ] **Step 3: Implement the module**

```python
# src/dazzle/back/runtime/auth/admin_policy.py
"""Administrative-capability authorization for the framework's org-admin surfaces.

Generalizes the flat ``org_admin_roles`` gate: the framework names a small fixed set of admin
CAPABILITIES (the "actions"), the app binds each to a set of personas (the "principals") in the
manifest, and a check is the set-intersection of the caller's effective in-org roles with the
capability's persona set. Default-deny, fail-closed. ``org_admin_roles`` is the default persona set
for any capability not explicitly mapped, so apps that set only ``org_admin_roles`` are unchanged.

This is the framework's OWN admin surfaces only (members, connections) — separate from the
app-domain ``permit:``/``scope:``/``grant_schema`` plane. Pure + I/O-free → unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: The framework-defined admin capabilities. The single source of truth (tests + drift gate
#: assert against this). Add a name here (and wire a surface to it) to introduce a capability.
CAPABILITIES: tuple[str, ...] = ("manage_members", "manage_connections")


@dataclass(frozen=True)
class AdminPolicy:
    """Resolved ``capability -> frozenset[persona]`` for one app. Built once at boot."""

    _by_capability: Mapping[str, frozenset[str]]

    @classmethod
    def from_config(
        cls,
        *,
        org_admin_roles: Iterable[str] | None,
        admin_capabilities: Mapping[str, Iterable[str]] | None,
    ) -> "AdminPolicy":
        default = frozenset(org_admin_roles or ())
        caps = admin_capabilities or {}
        resolved: dict[str, frozenset[str]] = {}
        for cap in CAPABILITIES:
            roles = caps.get(cap)
            # An explicitly-empty / missing list falls back to org_admin_roles, so adding one
            # capability's map never silently locks out another.
            resolved[cap] = frozenset(roles) if roles else default
        return cls(resolved)

    def may(self, capability: str, effective_roles: Iterable[str]) -> bool:
        """True iff a member with ``effective_roles`` holds ``capability``. Fail-closed: an
        unknown capability or an empty resolved set denies."""
        allowed = self._by_capability.get(capability)
        if not allowed:
            return False
        return bool(set(effective_roles) & allowed)

    def roles_for(self, capability: str) -> frozenset[str]:
        """The resolved persona set for ``capability`` (empty for an unknown capability)."""
        return self._by_capability.get(capability, frozenset())


def unknown_admin_personas(
    admin_capabilities: Mapping[str, Iterable[str]], declared_personas: Iterable[str]
) -> set[str]:
    """Persona names referenced in ``admin_capabilities`` that aren't declared personas — a typo
    that would silently grant nobody. Returns the offending names (empty when all are known)."""
    declared = set(declared_personas)
    referenced: set[str] = set()
    for roles in admin_capabilities.values():
        referenced.update(roles)
    return referenced - declared
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_admin_policy.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/back/runtime/auth/admin_policy.py tests/unit/test_admin_policy.py
git commit -m "feat(auth): AdminPolicy capability value object (admin-authz core)"
```

---

## Task 2: Manifest `admin_capabilities` field

**Files:**
- Modify: `src/dazzle/core/manifest.py` — `AuthConfig` field (~line 167) + the `auth_config = AuthConfig(...)` block inside `load_manifest` (~line 877)
- Create: `tests/unit/test_manifest_admin_capabilities.py`

The loader is `load_manifest(path: Path)` reading a TOML file; tests write a `dazzle.toml` and call it (mirror `tests/unit/test_manifest_capabilities.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_manifest_admin_capabilities.py
"""Manifest [auth.admin_capabilities] parsing (admin-authz)."""

from pathlib import Path

from dazzle.core.manifest import load_manifest


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )
    return p


def test_admin_capabilities_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, ""))
    assert m.auth_config.admin_capabilities == {}


def test_admin_capabilities_parsed(tmp_path):
    m = load_manifest(
        _write(
            tmp_path,
            '\n[auth]\nenabled = true\norg_admin_roles = ["org_admin"]\n'
            '\n[auth.admin_capabilities]\n'
            'manage_members = ["business_admin"]\n'
            'manage_connections = ["it_admin"]\n',
        )
    )
    assert m.auth_config.admin_capabilities == {
        "manage_members": ["business_admin"],
        "manage_connections": ["it_admin"],
    }
```

> Confirm the manifest attribute name for the auth config: run
> `grep -n "auth_config" src/dazzle/core/manifest.py | tail -3`. The `ProjectManifest` returned by
> `load_manifest` exposes it (used as `getattr(ctx.config, "auth_config", None)` at runtime). If the
> attribute is named differently on `ProjectManifest`, adjust `m.auth_config` accordingly.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_manifest_admin_capabilities.py -q`
Expected: FAIL — `test_admin_capabilities_parsed` errors with `TypeError: __init__() got an unexpected keyword argument 'admin_capabilities'` (the field doesn't exist yet).

- [ ] **Step 3: Add the field + parse**

In `src/dazzle/core/manifest.py`, after the `org_admin_roles` field (line ~167):

```python
    org_admin_roles: list[str] = field(default_factory=list)
    # Capability -> personas map for the framework's org-admin surfaces. Empty = every capability
    # falls back to org_admin_roles (back-compat). See auth/admin_policy.py CAPABILITIES.
    admin_capabilities: dict[str, list[str]] = field(default_factory=dict)
```

In the `auth_config = AuthConfig(...)` block inside `load_manifest` (right after the
`org_admin_roles=list(auth_data.get("org_admin_roles", [])),` line, ~877):

```python
        org_admin_roles=list(auth_data.get("org_admin_roles", [])),
        admin_capabilities={
            str(k): [str(r) for r in (v or [])]
            for k, v in (auth_data.get("admin_capabilities", {}) or {}).items()
        },
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_manifest_admin_capabilities.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/manifest.py tests/unit/test_manifest_admin_capabilities.py
git commit -m "feat(auth): manifest [auth.admin_capabilities] map"
```

---

## Task 3: Boot wiring + unknown-persona warning

**Files:**
- Modify: `src/dazzle/back/runtime/subsystems/auth.py:71` (after the `org_admin_roles` line)

- [ ] **Step 1: Add the wiring**

After `ctx.app.state.org_admin_roles = list(getattr(_auth_cfg, "org_admin_roles", []) or [])` (line 71):

```python
        # Admin-capability policy (manage_members / manage_connections). org_admin_roles is the
        # default for any unlisted capability, so apps that set only org_admin_roles are unchanged.
        from dazzle.back.runtime.auth.admin_policy import AdminPolicy, unknown_admin_personas

        _admin_caps = dict(getattr(_auth_cfg, "admin_capabilities", {}) or {})
        ctx.app.state.admin_policy = AdminPolicy.from_config(
            org_admin_roles=ctx.app.state.org_admin_roles,
            admin_capabilities=_admin_caps,
        )
        # Warn (don't fail) on personas referenced in the map that aren't declared — a typo would
        # silently grant nobody. ctx.config.personas is the declared-persona source (id-keyed).
        _declared = {p["id"] for p in (getattr(ctx.config, "personas", None) or []) if "id" in p}
        _unknown = unknown_admin_personas(_admin_caps, _declared)
        if _unknown:
            logger.warning(
                "auth.admin_capabilities references undeclared personas %s — those entries grant "
                "nobody. Declared personas: %s",
                sorted(_unknown),
                sorted(_declared),
            )
```

> Confirm `logger` is module-level in `subsystems/auth.py` (`grep -n "^logger" src/dazzle/back/runtime/subsystems/auth.py`). If it's named differently (e.g. `_log`/`LOGGER`), use that name.

- [ ] **Step 2: Verify it boots + the subsystem wiring test still passes**

Run: `python -m pytest src/dazzle/back/tests/test_auth.py -k "subsystem or wiring" -q`
Expected: PASS (the fake-ctx wiring test from earlier work tolerates the new attr; if a test asserts an exact `app.state` attr set, update it to include `admin_policy`).

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/back/runtime/subsystems/auth.py
git commit -m "feat(auth): build app.state.admin_policy at boot + unknown-persona warning"
```

---

## Task 4: Re-target the member-admin orphan guards

**Files:**
- Modify: `src/dazzle/back/runtime/auth/member_admin.py`
- Test: `tests/unit/test_member_admin.py`

The two pure functions currently take `org_admin_roles: list[str]`. Rename the parameter to
`admin_roles` (it now receives the resolved `manage_members` persona set) — behavior is identical, it
is the *source* of the set that changes (caller passes `policy.roles_for("manage_members")`).

- [ ] **Step 1: Update the callers' expectation in the unit test**

In `tests/unit/test_member_admin.py`, change every `org_admin_roles=` keyword passed to
`active_admins`/`would_orphan_org` to `admin_roles=` (positional calls need no change). Run
`grep -n "org_admin_roles" tests/unit/test_member_admin.py` first to enumerate them. Add one test:

```python
def test_guards_accept_a_frozenset_admin_set():
    from dazzle.back.runtime.auth.member_admin import active_admins, would_orphan_org

    roster = [("m1", ["it_admin"], "active"), ("m2", ["member"], "active")]
    assert active_admins(roster, frozenset({"it_admin"})) == ["m1"]
    assert would_orphan_org(roster, "m1", new_roles=None, admin_roles=frozenset({"it_admin"})) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_member_admin.py -q`
Expected: FAIL — `would_orphan_org() got an unexpected keyword argument 'admin_roles'` (and the new frozenset test errors on the keyword).

- [ ] **Step 3: Rename the parameter in `member_admin.py`**

Replace `org_admin_roles` with `admin_roles` in BOTH function signatures and bodies:

```python
def active_admins(
    roster: list[tuple[str, list[str], str]], admin_roles: "Iterable[str]"
) -> list[str]:
    """Membership ids that are ACTIVE and hold at least one persona in ``admin_roles`` (the
    resolved ``manage_members`` capability set)."""
    admin_set = set(admin_roles)
    return [mid for (mid, roles, status) in roster if status == "active" and admin_set & set(roles)]


def would_orphan_org(
    roster: list[tuple[str, list[str], str]],
    target_id: str,
    *,
    new_roles: list[str] | None,
    admin_roles: "Iterable[str]",
) -> bool:
    """True iff applying the change to ``target_id`` leaves the org with no member who holds the
    ``manage_members`` capability. (Docstring concurrency caveat unchanged.)"""
    before = active_admins(roster, admin_roles)
    if not before:
        return False
    admin_set = set(admin_roles)
    after: list[str] = []
    for mid, roles, status in roster:
        if mid == target_id:
            if new_roles is None:
                continue
            if status == "active" and admin_set & set(new_roles):
                after.append(mid)
        elif status == "active" and admin_set & set(roles):
            after.append(mid)
    return len(after) == 0
```

Add `from collections.abc import Iterable` to the imports (keep `from __future__ import annotations`).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_member_admin.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/back/runtime/auth/member_admin.py tests/unit/test_member_admin.py
git commit -m "refactor(auth): orphan guards take the resolved manage_members set"
```

---

## Task 5: Migrate routes to `AdminPolicy`; remove `may_manage_members`

**Files:**
- Modify: `member_admin_routes.py`, `invitation_routes.py`, `connection_admin_routes.py`, `invitations.py`
- Test: `tests/integration/test_connection_admin_routes.py`, `tests/unit/test_member_admin.py` (route-level tests live where the existing ones do — confirm)

Add a shared read helper in EACH of the three route modules (they don't share a base; keep it local,
matching the existing local `_org_admin_roles` pattern):

```python
def _admin_policy(request: Request):
    """The app's AdminPolicy, falling back to an org_admin_roles-only policy when not wired
    (the back-compat default + keeps existing tests that set only app.state.org_admin_roles green)."""
    from dazzle.back.runtime.auth.admin_policy import AdminPolicy

    policy = getattr(request.app.state, "admin_policy", None)
    if policy is None:
        policy = AdminPolicy.from_config(
            org_admin_roles=list(getattr(request.app.state, "org_admin_roles", []) or []),
            admin_capabilities={},
        )
    return policy
```

- [ ] **Step 1: Write the failing route tests**

In `tests/integration/test_connection_admin_routes.py`, the `_client(...)` helper sets
`app.state.org_admin_roles`. Add a way to set the policy, then the separation tests:

```python
def _client_with_policy(store, *, manage_connections, manage_members=("admin",)):
    from dazzle.back.runtime.auth.admin_policy import AdminPolicy

    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.admin_policy = AdminPolicy.from_config(
        org_admin_roles=["admin"],
        admin_capabilities={
            "manage_connections": list(manage_connections),
            "manage_members": list(manage_members),
        },
    )
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    c = TestClient(app)
    c.cookies.set("dazzle_session", "good-sid")
    return c


def test_connection_surface_gated_on_manage_connections() -> None:
    # the session's role is "admin" (see _Store.validate_session). Map manage_connections to a
    # DIFFERENT persona → the admin can no longer reach the connection surface.
    store = _Store(connections=[_conn()])
    r = _client_with_policy(store, manage_connections=("it_admin",)).get("/auth/connections")
    assert r.status_code == 403


def test_connection_surface_allows_mapped_persona() -> None:
    store = _Store(connections=[_conn()], roles=("it_admin",))
    r = _client_with_policy(store, manage_connections=("it_admin",)).get("/auth/connections")
    assert r.status_code == 200


def test_backcompat_org_admin_roles_only_still_authorizes() -> None:
    # no admin_policy on app.state → fallback to org_admin_roles; the existing _client does this.
    store = _Store(connections=[_conn()])
    assert _client(store).get("/auth/connections").status_code == 200
```

> `_Store.validate_session` returns `roles=self._roles` (default `("admin",)`); `roles=(...)` on
> `_Store(...)` sets the caller's in-org roles. Use that to model the it_admin caller.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/integration/test_connection_admin_routes.py -k "manage_connections or backcompat" -q`
Expected: FAIL — `test_connection_surface_gated_on_manage_connections` returns 200 (still on the flat gate) until the route is migrated.

- [ ] **Step 3: Migrate `connection_admin_routes.py`**

In `_gate` (lines ~68-84), replace the `may_manage_members` check:

```python
        from dazzle.back.runtime.auth.models import effective_roles_of

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        if not _admin_policy(request).may("manage_connections", list(effective_roles_of(ctx))):
            return None
        return store, ctx, ctx.active_membership.tenant_id
```

Remove the now-unused `from ...invitations import may_manage_members` and the `_org_admin_roles`
helper if present in this file. Add the `_admin_policy` helper (above) at module level. Update the
module docstring line that says "fail-closed `may_manage_members`" → "fail-closed
`manage_connections` capability".

- [ ] **Step 4: Migrate `member_admin_routes.py`**

In `_gate`, replace:

```python
        if not _admin_policy(request).may("manage_members", list(effective_roles_of(ctx))):
            return None
```

Replace the two guard call sites:
- `admins = set(active_admins(roster, _org_admin_roles(request)))`
  → `admins = set(active_admins(roster, _admin_policy(request).roles_for("manage_members")))`
- `would_orphan_org(_roster_rows(store, org_id), membership_id, new_roles=..., org_admin_roles=_org_admin_roles(request))`
  → `... admin_roles=_admin_policy(request).roles_for("manage_members"))` (run
  `grep -n "would_orphan_org" src/dazzle/back/runtime/auth/member_admin_routes.py` to find all call
  sites — there may be two, change_roles and remove). Add the `_admin_policy` helper; remove the
  `may_manage_members` import. Keep `_org_admin_roles` only if still referenced (it isn't after this).

- [ ] **Step 5: Migrate `invitation_routes.py`**

Replace (line ~61-62):

```python
        from dazzle.back.runtime.auth.models import effective_roles_of

        if not _admin_policy(request).may("manage_members", list(effective_roles_of(ctx))):
            return HTMLResponse("Forbidden", status_code=403)  # keep the existing failure shape
```

Add the `_admin_policy` helper; remove the `may_manage_members` import and the local
`org_admin_roles = ...` line. (Match the existing forbidden-response shape used here — read lines
55-70 first.)

- [ ] **Step 6: Remove `may_manage_members` (clean break, ADR-0003)**

Delete the `may_manage_members` function from `src/dazzle/back/runtime/auth/invitations.py`. Run
`grep -rn "may_manage_members" src/ tests/` — every remaining hit must be removed/migrated. If a
unit test targeted `may_manage_members` directly, delete it (its coverage moved to
`test_admin_policy.py`'s `may` tests).

- [ ] **Step 7: Run the route + auth suites**

Run: `python -m pytest tests/integration/test_connection_admin_routes.py tests/unit/test_member_admin.py src/dazzle/back/tests/test_auth.py -q`
Expected: PASS (incl. the new separation + back-compat tests). Also run
`grep -rn "may_manage_members" src/ tests/` → no output.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/back/runtime/auth/member_admin_routes.py src/dazzle/back/runtime/auth/invitation_routes.py src/dazzle/back/runtime/auth/connection_admin_routes.py src/dazzle/back/runtime/auth/invitations.py tests/integration/test_connection_admin_routes.py
git commit -m "feat(auth): gate org-admin surfaces on admin capabilities; drop may_manage_members"
```

---

## Task 6: Drift gate

**Files:**
- Create: `tests/unit/test_admin_capability_drift.py`

- [ ] **Step 1: Write the gate**

```python
# tests/unit/test_admin_capability_drift.py
"""Drift gate: every framework admin capability is consumed by a surface, and AdminPolicy holds its
default-deny / fail-closed invariants. Catches an orphaned capability or a regressed default."""

from pathlib import Path

from dazzle.back.runtime.auth.admin_policy import CAPABILITIES, AdminPolicy

_AUTH_DIR = Path(__file__).resolve().parents[2] / "src/dazzle/back/runtime/auth"


def test_every_capability_is_consumed_by_a_route_or_guard():
    sources = "\n".join(
        p.read_text(encoding="utf-8")
        for p in _AUTH_DIR.glob("*.py")
        if p.name not in {"admin_policy.py"}
    )
    for cap in CAPABILITIES:
        assert f'"{cap}"' in sources or f"'{cap}'" in sources, (
            f"capability {cap!r} is defined but no surface gates on it — orphan capability"
        )


def test_default_deny_and_fallback_invariants():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    assert all(p.may(c, ["org_admin"]) for c in CAPABILITIES)  # fallback to org_admin_roles
    assert not any(p.may(c, ["nobody"]) for c in CAPABILITIES)  # default-deny
    empty = AdminPolicy.from_config(org_admin_roles=[], admin_capabilities={})
    assert not any(empty.may(c, ["anyone"]) for c in CAPABILITIES)  # fail-closed
```

- [ ] **Step 2: Run to verify pass**

Run: `python -m pytest tests/unit/test_admin_capability_drift.py -q`
Expected: PASS (both capabilities appear in the migrated routes from Task 5).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_admin_capability_drift.py
git commit -m "test(auth): admin-capability drift gate"
```

---

## Task 7: Docs, CHANGELOG, ship

**Files:**
- Modify: `docs/reference/enterprise-sso.md` (or a short new `docs/reference/admin-roles.md` linked from nav) + `CHANGELOG.md`

- [ ] **Step 1: Document the capability map**

Add a short section (in `enterprise-sso.md` near the readiness/CLI text, or a new `admin-roles.md`
added to `mkdocs.yml` nav) describing `[auth.admin_capabilities]`, the two capabilities, the
`org_admin_roles` back-compat default, and that connection management is `manage_connections`. Show
the example manifest block from the spec.

- [ ] **Step 2: CHANGELOG entry**

Under `## [Unreleased]` add `### Added` (the capability model) + `### Changed` (connection surface now
gates on `manage_connections`; behavior unchanged unless an app declares `admin_capabilities`) +
`### Agent Guidance` (org-admin surfaces gate on named capabilities via `app.state.admin_policy`;
`may_manage_members` removed — use `policy.may("manage_members"/"manage_connections", roles)`).

- [ ] **Step 3: Full pre-ship gates**

Run:
```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
python -m pytest tests/ -m "not e2e" -q
mkdocs build --strict
```
Expected: all green. (`tests/ -m "not e2e"` covers the auth unit + integration suites touched here.)

- [ ] **Step 4: Bump + ship**

`/bump patch`, then `/ship` (commit + tag + push). Then poll CI + PyPI green.

---

## Notes for the implementer

- **No DB schema change** — this is config + authz logic only. No Alembic, no `_init_db` edit.
- **Back-compat is the headline invariant**: an app that sets only `org_admin_roles` must behave
  exactly as before. The `_admin_policy` route fallback + the `from_config` org_admin_roles default
  both enforce it; the `test_backcompat_*` tests pin it. If any existing auth test regresses,
  that's a real back-compat break — fix the code, not the test.
- **Security-sensitive**: this is an authorization change. After Task 5, run an independent review
  (fresh reviewer subagent or `/code-review`) focused on: no surface left on the old flat gate, the
  fail-closed/default-deny paths, and that the route fallback can't accidentally widen access.
- **PersonaSpec identity**: declared personas are id-keyed (`ctx.config.personas` → `p["id"]`); the
  CLAUDE.md gotcha (`.id` not `.name`) applies if you switch to `ctx.appspec.personas`.
