# Capability Opt-In Model — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general `[capabilities]` opt-in registry that gates framework features on declared per-app intent, and make enterprise auth (OIDC/SAML/SCIM) its first consumer — so a greenfield app never sprouts enterprise routes just because a pip extra is installed.

**Architecture:** A framework-side capability registry (`src/dazzle/core/capabilities/`) where each `Capability` self-describes its required pip extra + a probe module. At boot, `resolve_capabilities(declared)` computes `active = requested ∧ available`; a capability *requested but whose extra is missing* is a hard, actionable boot error. The resolved set rides on `SubsystemContext.capabilities`; the auth subsystem gates each enterprise route group on `caps.active(<id>)` instead of `find_spec(...)`. A boot guard fails loud if connection rows exist for an undeclared protocol.

**Tech Stack:** Python 3.12, dataclasses, `tomllib`, Typer (CLI), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-06-capability-opt-in-model-design.md` (Phase 1 only; cognition gating = Phase 2, #1342 backlog = Phase 3).

---

## File Structure

- **Create** `src/dazzle/core/capabilities/__init__.py` — public exports.
- **Create** `src/dazzle/core/capabilities/models.py` — `Capability` dataclass, `ResolvedCapabilities`, `CapabilityUnavailableError`.
- **Create** `src/dazzle/core/capabilities/registry.py` — process registry + the three enterprise-auth capabilities + `resolve_capabilities()`.
- **Create** `tests/unit/test_capabilities.py` — model/registry/resolution tests.
- **Modify** `src/dazzle/core/manifest.py` — add `CapabilitiesConfig` + `capabilities` field + `[capabilities]` parse in `load_manifest`.
- **Modify** `src/dazzle/http/runtime/subsystems/__init__.py` — add `capabilities` field to `SubsystemContext`.
- **Modify** `src/dazzle/http/runtime/server.py:462` — compute + attach resolved capabilities.
- **Modify** `src/dazzle/http/runtime/subsystems/auth.py:236-307` — gate enterprise routes on `caps.active(...)`; add the connection boot guard.
- **Create** `src/dazzle/cli/capability.py` — `dazzle capability list/enable/disable/status`.
- **Modify** `src/dazzle/cli/__init__.py` — register the `capability` typer.
- **Modify** `src/dazzle/cli/validate` path (the `validate_command`) — surface unknown/unavailable capability diagnostics.
- **Modify** `docs/reference/enterprise-sso.md` — opt-in header.
- **Modify** `CHANGELOG.md` — `### Added` + `### Changed` (migration note).

---

## Task 1: Capability model

**Files:**
- Create: `src/dazzle/core/capabilities/models.py`
- Test: `tests/unit/test_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_capabilities.py
from dazzle.core.capabilities.models import Capability


def test_capability_is_frozen_and_self_describing():
    cap = Capability(
        id="auth.enterprise.saml",
        label="Enterprise SAML SSO",
        probe_module="onelogin",
        required_extras=("saml",),
        remediation="pip install 'dazzle-dsl[saml]'  # needs native libxmlsec1",
    )
    assert cap.id == "auth.enterprise.saml"
    assert cap.required_extras == ("saml",)
    # frozen
    import dataclasses, pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.id = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_capabilities.py::test_capability_is_frozen_and_self_describing -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.core.capabilities`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/dazzle/core/capabilities/models.py
"""Capability model for the opt-in feature-gating system (#1342).

A capability is a framework feature an app must explicitly opt into via
``[capabilities]`` in dazzle.toml. Each one self-describes the pip extra it needs
(for the runbook) and the importable module used to probe availability.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    """A declarable, gateable framework capability.

    Attributes:
        id: Dotted identifier, e.g. ``auth.enterprise.oidc``.
        label: Human-readable name for CLI/diagnostics.
        probe_module: Importable module whose presence means the capability is
            *available* in this runtime (e.g. ``authlib``). Probed with
            ``importlib.util.find_spec``.
        required_extras: pip extras that install ``probe_module`` (for the
            remediation runbook), e.g. ``("sso",)``.
        remediation: Exact, actionable fix shown when declared-but-unavailable.
    """

    id: str
    label: str
    probe_module: str
    required_extras: tuple[str, ...]
    remediation: str


class CapabilityUnavailableError(RuntimeError):
    """Raised at boot when a declared capability's extra is not installed."""


@dataclass(frozen=True, slots=True)
class ResolvedCapabilities:
    """Boot-time resolution of declared capabilities.

    ``active`` = declared ∧ available. ``unavailable`` = declared ∧ not-installed
    (each a boot error). ``declared`` is the raw manifest list (for diagnostics).
    """

    active: frozenset[str]
    unavailable: frozenset[str]
    declared: tuple[str, ...]

    def is_active(self, capability_id: str) -> bool:
        return capability_id in self.active
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_capabilities.py::test_capability_is_frozen_and_self_describing -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/capabilities/models.py tests/unit/test_capabilities.py
git commit -m "feat(capabilities): Capability + ResolvedCapabilities model (#1342)"
```

---

## Task 2: Registry + enterprise-auth capabilities + resolution

**Files:**
- Create: `src/dazzle/core/capabilities/registry.py`
- Create: `src/dazzle/core/capabilities/__init__.py`
- Test: `tests/unit/test_capabilities.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/unit/test_capabilities.py
from dazzle.core.capabilities import (
    known_capability_ids,
    resolve_capabilities,
)
from dazzle.core.capabilities.models import CapabilityUnavailableError


def test_enterprise_capabilities_are_registered():
    ids = known_capability_ids()
    assert {
        "auth.enterprise.oidc",
        "auth.enterprise.saml",
        "auth.enterprise.scim",
    } <= ids


def test_resolution_active_requires_declared_and_available(monkeypatch):
    # Force OIDC's probe module to look installed, SAML's to look absent.
    import dazzle.core.capabilities.registry as reg

    def fake_find_spec(name):
        return object() if name == "authlib" else None

    monkeypatch.setattr(reg, "find_spec", fake_find_spec)

    resolved = resolve_capabilities(["auth.enterprise.oidc"])
    assert resolved.is_active("auth.enterprise.oidc")
    assert not resolved.is_active("auth.enterprise.saml")  # not declared


def test_declared_but_unavailable_raises_with_remediation(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: None)  # nothing installed

    with pytest.raises(CapabilityUnavailableError) as exc:
        resolve_capabilities(["auth.enterprise.saml"])
    assert "dazzle-dsl[saml]" in str(exc.value)  # runbook present


def test_unknown_id_is_reported_not_resolved():
    from dazzle.core.capabilities import unknown_capability_ids

    assert unknown_capability_ids(["auth.enterprise.oidc", "auth.bogus"]) == [
        "auth.bogus"
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_capabilities.py -v`
Expected: FAIL — `ImportError: cannot import name 'known_capability_ids'`.

- [ ] **Step 3: Write the registry + resolution**

```python
# src/dazzle/core/capabilities/registry.py
"""Process-wide capability registry + boot-time resolution (#1342)."""

from importlib.util import find_spec

from dazzle.core.capabilities.models import (
    Capability,
    CapabilityUnavailableError,
    ResolvedCapabilities,
)

_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> None:
    """Register a capability. Idempotent across imports (last wins)."""
    _REGISTRY[capability.id] = capability


def get(capability_id: str) -> Capability | None:
    return _REGISTRY.get(capability_id)


def all_capabilities() -> list[Capability]:
    return sorted(_REGISTRY.values(), key=lambda c: c.id)


def known_capability_ids() -> set[str]:
    return set(_REGISTRY)


def unknown_capability_ids(declared: list[str]) -> list[str]:
    """Declared ids with no registered capability (for validate diagnostics)."""
    known = known_capability_ids()
    return [cid for cid in declared if cid not in known]


def is_available(capability: Capability) -> bool:
    """True iff the capability's probe module is importable in this runtime."""
    return find_spec(capability.probe_module) is not None


def resolve_capabilities(declared: list[str]) -> ResolvedCapabilities:
    """Compute active/unavailable from the declared list.

    Unknown ids are ignored here (``validate`` reports them); this function
    concerns *availability*. Raises ``CapabilityUnavailableError`` listing every
    declared-but-unavailable capability with its remediation runbook.
    """
    active: set[str] = set()
    unavailable: set[str] = set()
    for cid in declared:
        cap = _REGISTRY.get(cid)
        if cap is None:
            continue  # unknown — handled by validate, not a boot error here
        if is_available(cap):
            active.add(cid)
        else:
            unavailable.add(cid)

    if unavailable:
        lines = [
            f"  - {cid}: {_REGISTRY[cid].remediation}" for cid in sorted(unavailable)
        ]
        raise CapabilityUnavailableError(
            "These capabilities are declared in [capabilities] but their packages "
            "are not installed:\n" + "\n".join(lines)
        )

    return ResolvedCapabilities(
        active=frozenset(active),
        unavailable=frozenset(unavailable),
        declared=tuple(declared),
    )


# --- Enterprise auth capabilities (consumer #1) -----------------------------
register(
    Capability(
        id="auth.enterprise.oidc",
        label="Enterprise OIDC SSO",
        probe_module="authlib",
        required_extras=("sso",),
        remediation="pip install 'dazzle-dsl[sso]'",
    )
)
register(
    Capability(
        id="auth.enterprise.saml",
        label="Enterprise SAML SSO",
        probe_module="onelogin",
        required_extras=("saml",),
        remediation="pip install 'dazzle-dsl[saml]'  # needs native libxmlsec1",
    )
)
register(
    Capability(
        id="auth.enterprise.scim",
        label="Enterprise SCIM provisioning",
        probe_module="authlib",
        required_extras=("sso",),
        remediation="pip install 'dazzle-dsl[sso]'",
    )
)
```

```python
# src/dazzle/core/capabilities/__init__.py
"""Capability opt-in registry (#1342).

Import side effect: registers the framework's built-in capabilities.
"""

from dazzle.core.capabilities.models import (
    Capability,
    CapabilityUnavailableError,
    ResolvedCapabilities,
)
from dazzle.core.capabilities.registry import (
    all_capabilities,
    get,
    is_available,
    known_capability_ids,
    register,
    resolve_capabilities,
    unknown_capability_ids,
)

__all__ = [
    "Capability",
    "CapabilityUnavailableError",
    "ResolvedCapabilities",
    "all_capabilities",
    "get",
    "is_available",
    "known_capability_ids",
    "register",
    "resolve_capabilities",
    "unknown_capability_ids",
]
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_capabilities.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/capabilities/
git commit -m "feat(capabilities): registry + resolution + enterprise-auth capabilities (#1342)"
```

---

## Task 3: Manifest `[capabilities]` parsing

**Files:**
- Modify: `src/dazzle/core/manifest.py` (add `CapabilitiesConfig` near `SpecConfig` ~line 421; field on `ProjectManifest` ~line 600; parse in `load_manifest` ~line 1000; pass to constructor ~line 1011)
- Test: `tests/unit/test_manifest_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_manifest_capabilities.py
from pathlib import Path

from dazzle.core.manifest import load_manifest


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )
    return p


def test_capabilities_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, ""))
    assert m.capabilities.enabled == []


def test_capabilities_parsed(tmp_path):
    m = load_manifest(
        _write(
            tmp_path,
            '\n[capabilities]\nenabled = ["auth.enterprise.oidc", "auth.enterprise.scim"]\n',
        )
    )
    assert m.capabilities.enabled == [
        "auth.enterprise.oidc",
        "auth.enterprise.scim",
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_manifest_capabilities.py -v`
Expected: FAIL — `AttributeError: 'ProjectManifest' object has no attribute 'capabilities'`.

- [ ] **Step 3a: Add the `CapabilitiesConfig` dataclass** (place it immediately after `class SpecConfig` and before the next class)

```python
@dataclass
class CapabilitiesConfig:
    """Opt-in capability declarations (#1342).

    Reads ``[capabilities]`` from dazzle.toml:

        [capabilities]
        enabled = ["auth.enterprise.oidc"]

    Default empty → a greenfield app activates no gated capability.
    """

    enabled: list[str] = field(default_factory=list)
```

- [ ] **Step 3b: Add the field to `ProjectManifest`** (after the `spec: SpecConfig = ...` line ~600)

```python
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)
```

- [ ] **Step 3c: Parse it in `load_manifest`** (next to the `spec_config = SpecConfig(...)` line ~1000)

```python
    cap_data = data.get("capabilities", {})
    capabilities_config = CapabilitiesConfig(
        enabled=list(cap_data.get("enabled", [])),
    )
```

- [ ] **Step 3d: Pass it to the `ProjectManifest(...)` constructor** (next to `spec=spec_config,` ~line 1028)

```python
        capabilities=capabilities_config,
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_manifest_capabilities.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/manifest.py tests/unit/test_manifest_capabilities.py
git commit -m "feat(manifest): parse [capabilities] enabled list (#1342)"
```

---

## Task 4: `dazzle validate` — unknown / unavailable capability diagnostics

**Files:**
- Modify: the `validate_command` (find with `git grep -n "def validate_command" src/dazzle/cli/`)
- Test: `tests/unit/test_capability_validate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_capability_validate.py
from dazzle.core.capabilities import unknown_capability_ids


def test_unknown_capability_suggestion_helper():
    # The validate command renders this; pin the underlying check.
    bad = unknown_capability_ids(["auth.enterprise.oidc", "auth.enterprize.oidc"])
    assert bad == ["auth.enterprize.oidc"]
```

- [ ] **Step 2: Run to verify it fails (or passes trivially)**

Run: `pytest tests/unit/test_capability_validate.py -v`
Expected: PASS (helper exists from Task 2) — this test pins the contract validate relies on.

- [ ] **Step 3: Wire the diagnostic into `validate_command`**

In `validate_command`, after the manifest is loaded (`manifest = load_manifest(...)`), add:

```python
    from dazzle.core.capabilities import known_capability_ids, unknown_capability_ids

    declared = manifest.capabilities.enabled
    bad = unknown_capability_ids(declared)
    if bad:
        known = sorted(known_capability_ids())
        for cid in bad:
            # closest-match suggestion
            import difflib

            hint = difflib.get_close_matches(cid, known, n=1)
            suffix = f" — did you mean '{hint[0]}'?" if hint else ""
            typer.secho(
                f"✗ Unknown capability '{cid}' in [capabilities].{suffix}",
                fg=typer.colors.RED,
            )
        raise typer.Exit(code=1)
```

(Match the surrounding error-reporting style — if `validate_command` collects errors into a list rather than printing inline, append to that list instead and let the existing exit path handle it.)

- [ ] **Step 4: Verify**

Run: `pytest tests/unit/test_capability_validate.py -v` → PASS.
Manual: create a temp project with `enabled = ["auth.bogus"]`, run `dazzle validate` → exits 1 with the did-you-mean line.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/ tests/unit/test_capability_validate.py
git commit -m "feat(validate): reject unknown [capabilities] ids with suggestions (#1342)"
```

---

## Task 5: Thread resolved capabilities onto `SubsystemContext`

**Files:**
- Modify: `src/dazzle/http/runtime/subsystems/__init__.py` (add field after `security_profile` ~line 80)
- Modify: `src/dazzle/http/runtime/server.py:462` (`_build_subsystem_context`)
- Test: `tests/unit/test_capability_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_capability_context.py
from dazzle.core.capabilities import resolve_capabilities


def test_resolved_set_is_attachable_and_queryable(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # all available
    resolved = resolve_capabilities(["auth.enterprise.oidc"])
    assert resolved.is_active("auth.enterprise.oidc")
    assert not resolved.is_active("auth.enterprise.scim")
```

- [ ] **Step 2: Run to verify it passes** (pins the contract Task 6 depends on)

Run: `pytest tests/unit/test_capability_context.py -v` → PASS.

- [ ] **Step 3a: Add the field to `SubsystemContext`** (after `security_profile: str = "basic"`)

```python
    # Resolved opt-in capabilities (#1342) — set by DazzleBackendApp before
    # subsystem startup. Query with `.is_active("auth.enterprise.oidc")`.
    capabilities: Any = None
```

- [ ] **Step 3b: Compute + attach in `server.py`** — in `_build_subsystem_context`, before the `return SubsystemContext(` (line 462), resolve from the manifest the app already loaded. If the manifest is on `self._config` or a loaded manifest object, read `enabled` from it; otherwise default to `[]`:

```python
        from dazzle.core.capabilities import resolve_capabilities

        declared = getattr(getattr(self, "_manifest", None), "capabilities", None)
        enabled = list(declared.enabled) if declared is not None else []
        resolved_caps = resolve_capabilities(enabled)  # raises CapabilityUnavailableError if declared-but-missing
```

…then pass `capabilities=resolved_caps,` inside the `SubsystemContext(...)` call.

(If `DazzleBackendApp` does not already hold the `ProjectManifest`, thread it in where the manifest is loaded during app construction — search `load_manifest(` in `server.py` and stash the result on `self._manifest`.)

- [ ] **Step 4: Run the broader context + server smoke**

Run: `pytest tests/unit/test_capability_context.py tests/unit -k "subsystem and context" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/subsystems/__init__.py src/dazzle/http/runtime/server.py tests/unit/test_capability_context.py
git commit -m "feat(runtime): resolve + thread capabilities onto SubsystemContext (#1342)"
```

---

## Task 6: Gate enterprise auth routes on capabilities

**Files:**
- Modify: `src/dazzle/http/runtime/subsystems/auth.py:236-307`
- Test: `tests/unit/test_auth_capability_gating.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_auth_capability_gating.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dazzle.core.capabilities import resolve_capabilities


def _ctx(caps, *, database_url="postgresql://localhost/test"):
    return SimpleNamespace(
        app=MagicMock(name="app"),
        capabilities=caps,
        # minimal surface the SSO-mount block reads:
        auth_config=SimpleNamespace(oauth_providers=None),
        database_url=database_url,
    )


def test_no_capabilities_mounts_no_enterprise_routes(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # available...
    caps = resolve_capabilities([])  # ...but nothing declared
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    sub = AuthSubsystem()
    with patch.object(sub, "_mount_enterprise_sso") as oidc, patch.object(
        sub, "_mount_saml"
    ) as saml, patch.object(sub, "_mount_scim") as scim:
        sub._mount_enterprise_capabilities(_ctx(caps))  # the extracted gate method
    oidc.assert_not_called()
    saml.assert_not_called()
    scim.assert_not_called()


def test_declared_oidc_mounts_only_oidc(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())
    caps = resolve_capabilities(["auth.enterprise.oidc"])
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    sub = AuthSubsystem()
    with patch.object(sub, "_mount_enterprise_sso") as oidc, patch.object(
        sub, "_mount_saml"
    ) as saml, patch.object(sub, "_mount_scim") as scim:
        sub._mount_enterprise_capabilities(_ctx(caps))
    oidc.assert_called_once()
    saml.assert_not_called()
    scim.assert_not_called()  # SCIM no longer unconditional
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_auth_capability_gating.py -v`
Expected: FAIL — `AttributeError: 'AuthSubsystem' object has no attribute '_mount_enterprise_capabilities'`.

- [ ] **Step 3: Refactor `auth.py`** — extract the three mount blocks (lines 275-307) into helper methods and a capability-gated dispatcher. Replace the `enterprise_enabled = find_spec(...)` / `saml_enabled = ...` gating (236-307) with:

```python
        caps = ctx.capabilities
        any_enterprise = caps is not None and any(
            caps.is_active(c)
            for c in ("auth.enterprise.oidc", "auth.enterprise.saml", "auth.enterprise.scim")
        )

        # SessionMiddleware backs Authlib/SAML state — add it when a global social
        # provider is configured OR any enterprise capability is active.
        if configured or any_enterprise:
            import os
            import secrets

            from starlette.middleware.sessions import SessionMiddleware

            session_secret = os.environ.get("DAZZLE_SESSION_SECRET") or secrets.token_urlsafe(64)
            ctx.app.add_middleware(
                SessionMiddleware,
                secret_key=session_secret,
                same_site="lax",
                https_only=False,
            )

        if configured:
            ctx.app.include_router(create_sso_routes())

        self._mount_enterprise_capabilities(ctx)
```

Add the helper methods:

```python
    def _mount_enterprise_capabilities(self, ctx: Any) -> None:
        """Mount enterprise auth route groups gated on declared capabilities (#1342)."""
        caps = ctx.capabilities
        if caps is None:
            return
        if caps.is_active("auth.enterprise.oidc"):
            self._mount_enterprise_sso(ctx)
        if caps.is_active("auth.enterprise.saml"):
            self._mount_saml(ctx)
        if caps.is_active("auth.enterprise.scim"):
            self._mount_scim(ctx)

    def _mount_enterprise_sso(self, ctx: Any) -> None:
        from dazzle.http.runtime.auth.enterprise_routes import create_enterprise_sso_routes
        from dazzle.http.runtime.auth.oidc_provider import register_native_oidc

        register_native_oidc()
        ctx.app.include_router(create_enterprise_sso_routes())

    def _mount_saml(self, ctx: Any) -> None:
        from dazzle.http.runtime.auth.saml_provider import register_native_saml
        from dazzle.http.runtime.auth.saml_routes import create_saml_routes

        register_native_saml()
        ctx.app.include_router(create_saml_routes())

    def _mount_scim(self, ctx: Any) -> None:
        from dazzle.http.runtime.auth.scim_routes import create_scim_routes

        ctx.app.include_router(create_scim_routes())
```

Delete the old unconditional SCIM mount (lines 301-307) and the `find_spec`-based `enterprise_enabled`/`saml_enabled` locals.

- [ ] **Step 3b: Gate the org-admin connection surface** — the `/auth/connections` admin surface mounts unconditionally at `auth.py:185-189`. Gate it on any active enterprise capability. Replace:

```python
        from dazzle.http.runtime.auth.connection_admin_routes import (
            create_connection_admin_routes,
        )

        ctx.app.include_router(create_connection_admin_routes())
```

with:

```python
        # Org-admin connection surface — only when an enterprise capability is
        # active (#1342). No enterprise capability declared → no admin surface.
        if ctx.capabilities is not None and any(
            ctx.capabilities.is_active(c)
            for c in ("auth.enterprise.oidc", "auth.enterprise.saml", "auth.enterprise.scim")
        ):
            from dazzle.http.runtime.auth.connection_admin_routes import (
                create_connection_admin_routes,
            )

            ctx.app.include_router(create_connection_admin_routes())
```

Add a test to `tests/unit/test_auth_capability_gating.py`:

```python
def test_admin_surface_gated(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    # With no enterprise capability active, the admin-surface guard is False.
    caps_off = resolve_capabilities([])
    assert not any(
        caps_off.is_active(c)
        for c in ("auth.enterprise.oidc", "auth.enterprise.saml", "auth.enterprise.scim")
    )
    caps_on = resolve_capabilities(["auth.enterprise.oidc"])
    assert any(
        caps_on.is_active(c)
        for c in ("auth.enterprise.oidc", "auth.enterprise.saml", "auth.enterprise.scim")
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_auth_capability_gating.py tests/unit/test_auth_subsystem_jwt_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/subsystems/auth.py tests/unit/test_auth_capability_gating.py
git commit -m "feat(auth): gate enterprise OIDC/SAML/SCIM routes on capabilities (#1342)"
```

---

## Task 7: Existing-connections boot guard

**Files:**
- Create: `src/dazzle/http/runtime/auth/connection_guard.py`
- Modify: `src/dazzle/http/runtime/subsystems/auth.py` (call the guard before `_mount_enterprise_capabilities`)
- Test: `tests/unit/test_connection_boot_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_connection_boot_guard.py
import pytest

from dazzle.http.runtime.auth.connection_guard import (
    UndeclaredConnectionError,
    check_connections_match_capabilities,
)


def test_connection_type_without_capability_raises():
    # types present in DB but no matching active capability → loud error
    with pytest.raises(UndeclaredConnectionError) as exc:
        check_connections_match_capabilities(
            present_types={"oidc"},
            active_ids=frozenset(),  # nothing declared
        )
    msg = str(exc.value)
    assert "auth.enterprise.oidc" in msg
    assert "dazzle capability enable" in msg


def test_present_type_with_active_capability_is_ok():
    check_connections_match_capabilities(
        present_types={"oidc"},
        active_ids=frozenset({"auth.enterprise.oidc"}),
    )  # no raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_connection_boot_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: ...connection_guard`.

- [ ] **Step 3: Implement the guard**

```python
# src/dazzle/http/runtime/auth/connection_guard.py
"""Boot guard: existing connection rows must have their capability declared (#1342)."""

_TYPE_TO_CAPABILITY = {
    "oidc": "auth.enterprise.oidc",
    "saml": "auth.enterprise.saml",
    "scim": "auth.enterprise.scim",
}


class UndeclaredConnectionError(RuntimeError):
    """A connection row exists for a protocol whose capability isn't active."""


def check_connections_match_capabilities(
    present_types: set[str], active_ids: frozenset[str]
) -> None:
    """Raise if any present connection type lacks an active capability."""
    missing = []
    for ctype in sorted(present_types):
        cap = _TYPE_TO_CAPABILITY.get(ctype)
        if cap is not None and cap not in active_ids:
            missing.append((ctype, cap))
    if missing:
        lines = [
            f"  - {ctype} connection(s) exist but '{cap}' is not enabled; "
            f"add it to [capabilities] or run `dazzle capability enable {cap}`"
            for ctype, cap in missing
        ]
        raise UndeclaredConnectionError(
            "Enterprise connections exist for undeclared capabilities:\n"
            + "\n".join(lines)
        )


async def present_connection_types(db: object) -> set[str]:
    """Return the distinct `type` values in the `connections` table.

    Uses the project psycopg3 helpers (fetchall, %s params, dict rows).
    """
    from dazzle.http.runtime.connection import fetchall

    rows = await fetchall(db, "SELECT DISTINCT type FROM connections")
    return {r["type"] for r in rows}
```

(Confirm the `fetchall` import path matches the psycopg3 helper added in the asyncpg→psycopg3 migration; if the helper signature differs, adapt the call — the contract is "distinct `type` from `connections`".)

- [ ] **Step 4: Wire it into `auth.py`** — in `startup`, after computing `caps` and before `_mount_enterprise_capabilities`, guard only when a DB is available:

```python
        if ctx.capabilities is not None and ctx.database_url:
            from dazzle.http.runtime.auth.connection_guard import (
                check_connections_match_capabilities,
                present_connection_types,
            )

            try:
                types = await present_connection_types(ctx.db_manager)
            except Exception:
                types = set()  # table absent on a fresh DB — nothing to guard
            check_connections_match_capabilities(types, ctx.capabilities.active)
```

- [ ] **Step 5: Run + commit**

Run: `pytest tests/unit/test_connection_boot_guard.py -v` → PASS.

```bash
git add src/dazzle/http/runtime/auth/connection_guard.py src/dazzle/http/runtime/subsystems/auth.py tests/unit/test_connection_boot_guard.py
git commit -m "feat(auth): boot guard — existing connections require declared capability (#1342)"
```

---

## Task 8: `dazzle capability` CLI

**Files:**
- Create: `src/dazzle/cli/capability.py`
- Modify: `src/dazzle/cli/__init__.py` (register near line 328 where `auth_app` is added)
- Test: `tests/unit/test_capability_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_capability_cli.py
from typer.testing import CliRunner

from dazzle.cli.capability import capability_app

runner = CliRunner()


def test_list_shows_enterprise_capabilities():
    result = runner.invoke(capability_app, ["list"])
    assert result.exit_code == 0
    assert "auth.enterprise.oidc" in result.stdout
    assert "auth.enterprise.saml" in result.stdout


def test_enable_writes_manifest_entry(tmp_path, monkeypatch):
    manifest = tmp_path / "dazzle.toml"
    manifest.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "auth.enterprise.oidc"])
    assert result.exit_code == 0
    assert "auth.enterprise.oidc" in manifest.read_text()
    assert "pip install 'dazzle-dsl[sso]'" in result.stdout  # runbook printed


def test_enable_rejects_unknown_id(tmp_path, monkeypatch):
    manifest = tmp_path / "dazzle.toml"
    manifest.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "auth.bogus"])
    assert result.exit_code != 0
    assert "Unknown capability" in result.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_capability_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.cli.capability`.

- [ ] **Step 3: Implement the CLI**

```python
# src/dazzle/cli/capability.py
"""`dazzle capability` — manage opt-in feature capabilities (#1342)."""

from pathlib import Path

import typer

from dazzle.core.capabilities import (
    all_capabilities,
    get,
    is_available,
    known_capability_ids,
)

capability_app = typer.Typer(help="Manage opt-in feature capabilities.")


def _manifest_path() -> Path:
    p = Path.cwd() / "dazzle.toml"
    if not p.exists():
        typer.secho("No dazzle.toml in the current directory.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    return p


def _declared(path: Path) -> list[str]:
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data.get("capabilities", {}).get("enabled", []))


@capability_app.command("list")
def list_capabilities() -> None:
    """List every capability and its status."""
    try:
        declared = set(_declared(_manifest_path()))
    except typer.Exit:
        declared = set()
    for cap in all_capabilities():
        avail = is_available(cap)
        if cap.id in declared and avail:
            status = "active"
        elif cap.id in declared and not avail:
            status = f"DECLARED-BUT-UNAVAILABLE ({cap.remediation})"
        elif avail:
            status = "dormant (available, not enabled)"
        else:
            status = "unavailable (not enabled)"
        typer.echo(f"{cap.id:28} {cap.label:32} {status}")


@capability_app.command("enable")
def enable(capability_id: str) -> None:
    """Enable a capability: append to [capabilities] + print the runbook."""
    if capability_id not in known_capability_ids():
        import difflib

        hint = difflib.get_close_matches(capability_id, sorted(known_capability_ids()), n=1)
        suffix = f" Did you mean '{hint[0]}'?" if hint else ""
        typer.secho(f"Unknown capability '{capability_id}'.{suffix}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    path = _manifest_path()
    declared = _declared(path)
    if capability_id not in declared:
        declared.append(capability_id)
        _write_enabled(path, declared)
        typer.secho(f"✓ Enabled {capability_id}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"{capability_id} already enabled.")

    cap = get(capability_id)
    assert cap is not None
    if not is_available(cap):
        typer.secho(f"\nNext: install the package — {cap.remediation}", fg=typer.colors.YELLOW)
    typer.echo(
        "\nActivation runbook:\n"
        f"  1. {cap.remediation}\n"
        "  2. Configure the connection: `dazzle auth connection create …` "
        "(see docs/reference/enterprise-sso.md)\n"
        "  3. Set DAZZLE_CONNECTION_SECRET for encrypted secret storage.\n"
        "  4. Verify readiness: `dazzle auth connection doctor <id>`."
    )


@capability_app.command("disable")
def disable(capability_id: str) -> None:
    """Remove a capability from [capabilities]."""
    path = _manifest_path()
    declared = _declared(path)
    if capability_id in declared:
        declared.remove(capability_id)
        _write_enabled(path, declared)
        typer.secho(f"✓ Disabled {capability_id}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"{capability_id} was not enabled.")


def _write_enabled(path: Path, enabled: list[str]) -> None:
    """Rewrite the [capabilities] enabled list in dazzle.toml (string-edit,
    preserving the rest of the file)."""
    import re

    text = path.read_text(encoding="utf-8")
    rendered = "enabled = [" + ", ".join(f'"{c}"' for c in enabled) + "]"
    if "[capabilities]" in text:
        text = re.sub(r"enabled\s*=\s*\[[^\]]*\]", rendered, text, count=1)
    else:
        text = text.rstrip() + f"\n\n[capabilities]\n{rendered}\n"
    path.write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Register the typer** in `src/dazzle/cli/__init__.py` (near line 328, alongside `app.add_typer(auth_app, name="auth")`):

```python
from dazzle.cli.capability import capability_app  # noqa: E402

app.add_typer(capability_app, name="capability")
```

- [ ] **Step 5: Run + commit**

Run: `pytest tests/unit/test_capability_cli.py -v` → PASS.

```bash
git add src/dazzle/cli/capability.py src/dazzle/cli/__init__.py tests/unit/test_capability_cli.py
git commit -m "feat(cli): dazzle capability list/enable/disable (#1342)"
```

---

## Task 9: Registry contract test, docs header, CHANGELOG

**Files:**
- Test: `tests/unit/test_capabilities.py` (append contract test)
- Modify: `docs/reference/enterprise-sso.md` (header)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the registry contract test**

```python
# append to tests/unit/test_capabilities.py
def test_every_capability_declares_extras_and_remediation():
    from dazzle.core.capabilities import all_capabilities

    for cap in all_capabilities():
        assert cap.required_extras, f"{cap.id} missing required_extras"
        assert cap.remediation.strip(), f"{cap.id} missing remediation"
        assert cap.probe_module, f"{cap.id} missing probe_module"
```

- [ ] **Step 2: Run** → `pytest tests/unit/test_capabilities.py -v` → PASS.

- [ ] **Step 3: Add the opt-in header to `docs/reference/enterprise-sso.md`** (immediately after the H1)

```markdown
!!! note "Opt-in capability"
    Enterprise SSO/SCIM is **off by default**. An app must declare it in
    `dazzle.toml` (`[capabilities] enabled = ["auth.enterprise.oidc", …]`) — or run
    `dazzle capability enable auth.enterprise.oidc` — before any enterprise route or
    admin surface mounts. A greenfield app sees none of this. See the capability
    model: `docs/superpowers/specs/2026-06-06-capability-opt-in-model-design.md`.
```

- [ ] **Step 4: CHANGELOG** — add under a new version section:

```markdown
### Added
- **`[capabilities]` opt-in model (#1342, Phase 1).** A general manifest registry
  gating framework features on declared per-app intent. `dazzle capability
  list/enable/disable`; enable prints the activation runbook. `active = requested ∧
  available`; a declared-but-uninstalled capability is a loud boot error.

### Changed
- **Enterprise auth (OIDC/SAML/SCIM) now requires an explicit capability.** Routes
  no longer mount on mere `[sso]`/`[saml]` pip-extra presence — declare
  `auth.enterprise.{oidc,saml,scim}` in `[capabilities]`. SCIM is no longer mounted
  unconditionally. **Migration:** existing deployments add the capability (or run
  `dazzle capability enable …`); a boot guard fails loud if connection rows exist
  for an undeclared protocol.
```

#### Agent Guidance
- Gate any new heavy/advanced framework feature behind a `Capability` (register in `src/dazzle/core/capabilities/registry.py`) so it stays opt-in. Query `ctx.capabilities.is_active("…")` at mount time.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_capabilities.py docs/reference/enterprise-sso.md CHANGELOG.md
git commit -m "feat(capabilities): contract test + enterprise-sso opt-in header + CHANGELOG (#1342)"
```

---

## Final integration check (before ship)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/`
- [ ] `mypy src/dazzle`
- [ ] `pytest tests/ -m "not e2e"` — full unit suite green
- [ ] `DATABASE_URL=…/dazzle_dev pytest -m postgres -q` — the boot guard touches the DB path; run the postgres job (per the pre-ship-test-scope rule for auth/runtime/boot changes)
- [ ] Manual: a fresh example app with no `[capabilities]` boots and serves `/health`; `curl /auth/saml/login` → 404 (not mounted). Add `enabled = ["auth.enterprise.oidc"]` with `[sso]` installed → enterprise routes mount; without `[sso]` → loud boot error naming `pip install 'dazzle-dsl[sso]'`.
- [ ] `/bump patch`, commit, push, monitor CI, comment on #1342 linking spec + plan.

---

## Notes for the implementer

- **psycopg3 helpers:** the boot-guard query uses the `fetchall` helper added in the asyncpg→psycopg3 migration (`%s` params, dict rows). Confirm the exact import in `src/dazzle/http/runtime/connection.py`.
- **`auth.py` is async:** `startup` is `async`; the boot guard call must be `await`ed (already shown).
- **Don't gate the CLI** `dazzle auth connection …` — it stays available so an operator can configure before/while enabling the capability.
- **Phase 2 (cognition gating) and Phase 3 (#1342 backlog items) are out of scope here** — this plan closes the runtime/surface leak and ships the model.
