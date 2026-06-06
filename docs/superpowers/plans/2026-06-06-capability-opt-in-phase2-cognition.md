# Capability Opt-In Model — Phase 2 (Cognition Gating) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make capability-gated guidance *push-only-when-declared* and *pull-always*, and surface a "declare this capability" suggestion when a spec states the requirement — so enterprise auth (and future gated features) never gets proactively pushed at an agent building a simple app, but is always discoverable on demand.

**Architecture:** Proactive cognition surfaces (bootstrap, `dsl(lint)` relevance, `spec_analyze` pattern proposals) learn an *active capability set* (resolved non-raising from the project manifest) and a per-item `capability` gate. A shared `partition_by_capability` splits surfaced items from gated ones; gated items that the spec/structure *requested* become "enable `dazzle capability …`" suggestions instead of full guidance. Pull surfaces (the `knowledge` tool) are untouched — direct queries always return gated content.

**Tech Stack:** Python 3.12, dataclasses/Pydantic, the existing MCP handlers + `core/discovery` engine + `semantics_kb`. Builds on Phase 1's `dazzle.core.capabilities`.

**Spec:** `docs/superpowers/specs/2026-06-06-capability-opt-in-model-design.md` (§Cognition gating). Phase 1 shipped v0.81.69.

**Reality check (investigated):** there is *no* enterprise-auth content surfaced proactively today (the `user_archetype` pattern has no triggers; counter-priors/discovery have zero SSO entries). So this phase ships the *mechanism*; Task 9 adds one real gated pattern trigger so the mechanism is exercised end-to-end against live data rather than only in unit tests.

---

## File Structure

- **Create** `src/dazzle/core/capabilities/cognition.py` — non-raising active-set resolution + `partition_by_capability` + enable-suggestion formatting. The single home for "how surfaces gate".
- **Modify** `src/dazzle/core/capabilities/registry.py` — add `active_capability_ids(declared)` (non-raising).
- **Modify** `src/dazzle/core/capabilities/__init__.py` — export the new helpers.
- **Modify** `src/dazzle/core/discovery/models.py` — add `gated_by: str | None` to `Relevance`.
- **Modify** `src/dazzle/core/discovery/engine.py` — accept `active: set[str]`, partition gated relevance.
- **Modify** `src/dazzle/core/lint.py` — thread `active` into `suggest_capabilities`.
- **Modify** `src/dazzle/mcp/server/handlers/dsl/validate.py` (or wherever lint is invoked) — resolve active from `project_root`, pass it down.
- **Modify** `src/dazzle/mcp/server/handlers/spec_analyze.py` — `_propose_patterns` reads an optional per-pattern `capability`, accepts `active`, emits `capability_suggestions` for gated-but-matched.
- **Modify** `src/dazzle/mcp/server/handlers/bootstrap.py` — resolve active from `work_dir`, thread into the cognition pass, surface `capability_suggestions` in the briefing.
- **Modify** `src/dazzle/mcp/semantics_kb/counter_priors.py` — optional `capability` on `CounterPrior`.
- **Modify** `src/dazzle/mcp/semantics_kb/patterns.toml` — Task 9: give one enterprise pattern a `capability` + triggers.
- **Tests:** `tests/unit/test_capability_cognition.py`, plus additions to discovery/bootstrap/spec_analyze tests.

---

## Task 1: Non-raising active-capability resolution

**Files:**
- Modify: `src/dazzle/core/capabilities/registry.py`
- Modify: `src/dazzle/core/capabilities/__init__.py`
- Test: `tests/unit/test_capability_cognition.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_capability_cognition.py
import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities import active_capability_ids


def test_active_capability_ids_is_non_raising(monkeypatch):
    # OIDC available, SAML not. Unlike resolve_capabilities, this must NOT raise
    # when a declared capability's extra is missing — it just omits it.
    monkeypatch.setattr(
        reg, "find_spec", lambda name: object() if name == "authlib" else None
    )
    active = active_capability_ids(
        ["auth.enterprise.oidc", "auth.enterprise.saml", "auth.bogus"]
    )
    assert active == {"auth.enterprise.oidc", "auth.enterprise.scim"} - {
        "auth.enterprise.scim"
    } | {"auth.enterprise.oidc"}
    assert "auth.enterprise.saml" not in active  # declared but unavailable → omitted
    assert "auth.bogus" not in active  # unknown → omitted
```

(Simplify the assertion to `assert active == {"auth.enterprise.oidc"}` — the set-algebra above is just emphasising scim isn't implicitly added.)

- [ ] **Step 2: Run → fail** — `pytest tests/unit/test_capability_cognition.py -q` → ImportError on `active_capability_ids`.

- [ ] **Step 3: Implement** in `registry.py` (after `resolve_capabilities`):

```python
def active_capability_ids(declared: list[str]) -> set[str]:
    """The subset of declared ids that are registered AND available.

    Non-raising (unlike ``resolve_capabilities``): for advisory/cognition surfaces
    that must never crash on an unavailable or unknown declared capability. A
    declared-but-unavailable capability is simply omitted from the active set.
    """
    return {cid for cid in declared if (cap := get(cid)) is not None and is_available(cap)}
```

Export it from `__init__.py` (`active_capability_ids` in the import block + `__all__`).

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(capabilities): non-raising active_capability_ids for cognition (#1342)`

---

## Task 2: Manifest-aware active-set + the gating helper

**Files:**
- Create: `src/dazzle/core/capabilities/cognition.py`
- Modify: `src/dazzle/core/capabilities/__init__.py`
- Test: `tests/unit/test_capability_cognition.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_active_capabilities_for_reads_manifest(tmp_path, monkeypatch):
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities.cognition import active_capabilities_for

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # all available
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname="t"\nversion="0.0.1"\n\n[modules]\npaths=["app"]\n\n'
        '[capabilities]\nenabled=["auth.enterprise.oidc"]\n',
        encoding="utf-8",
    )
    assert active_capabilities_for(tmp_path) == {"auth.enterprise.oidc"}


def test_active_capabilities_for_missing_manifest_is_empty(tmp_path):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    assert active_capabilities_for(tmp_path) == set()  # no dazzle.toml → empty


def test_partition_by_capability_splits_surfaced_and_gated():
    from dazzle.core.capabilities.cognition import partition_by_capability

    items = [
        {"id": "a", "cap": None},
        {"id": "b", "cap": "auth.enterprise.oidc"},
        {"id": "c", "cap": "auth.enterprise.saml"},
    ]
    surfaced, gated = partition_by_capability(
        items, active={"auth.enterprise.oidc"}, capability_of=lambda it: it["cap"]
    )
    assert [i["id"] for i in surfaced] == ["a", "b"]  # ungated + active
    assert gated == [(items[2], "auth.enterprise.saml")]  # gated + inactive
```

- [ ] **Step 2: Run → fail** (module missing).

- [ ] **Step 3: Implement** `src/dazzle/core/capabilities/cognition.py`:

```python
"""Capability gating for advisory cognition surfaces (#1342 Phase 2).

These helpers decide what proactive surfaces (bootstrap, lint relevance,
spec-analyze proposals) may push. They are deliberately *non-raising*: an
advisory read must never crash a project on a malformed/incomplete manifest.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

from dazzle.core.capabilities.registry import active_capability_ids, get

T = TypeVar("T")


def active_capabilities_for(project_root: Path | str) -> set[str]:
    """Active capability ids declared in ``<project_root>/dazzle.toml``.

    Empty set when there is no manifest or it can't be read — advisory only.
    """
    path = Path(project_root) / "dazzle.toml"
    if not path.is_file():
        return set()
    try:
        from dazzle.core.manifest import load_manifest

        return active_capability_ids(load_manifest(path).capabilities.enabled)
    except Exception:
        return set()  # malformed manifest must not break cognition


def partition_by_capability(
    items: Iterable[T],
    active: set[str],
    capability_of: Callable[[T], str | None],
) -> tuple[list[T], list[tuple[T, str]]]:
    """Split items into (surfaced, gated).

    ``surfaced`` = ungated (capability None) or whose capability is active.
    ``gated`` = (item, capability_id) for each item gated by an inactive capability.
    """
    surfaced: list[T] = []
    gated: list[tuple[T, str]] = []
    for item in items:
        cap = capability_of(item)
        if cap is None or cap in active:
            surfaced.append(item)
        else:
            gated.append((item, cap))
    return surfaced, gated


def enable_suggestion(capability_id: str) -> dict[str, Any]:
    """A structured 'declare this capability' hint for a requirement the spec
    stated but the app hasn't opted into."""
    cap = get(capability_id)
    label = cap.label if cap else capability_id
    remediation = cap.remediation if cap else ""
    return {
        "capability": capability_id,
        "label": label,
        "enable": f"dazzle capability enable {capability_id}",
        "remediation": remediation,
    }
```

Export `active_capabilities_for`, `partition_by_capability`, `enable_suggestion` from `__init__.py`.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(capabilities): cognition gating helpers — active-for-project + partition (#1342)`

---

## Task 3: `gated_by` on discovery Relevance + engine filter

**Files:**
- Modify: `src/dazzle/core/discovery/models.py`, `engine.py`
- Test: `tests/unit/test_capability_cognition.py` (+ existing discovery tests stay green)

- [ ] **Step 1: Write the failing test**

```python
def test_engine_filters_gated_relevance(monkeypatch):
    from dazzle.core.discovery.engine import suggest_capabilities

    # With a gated relevance present, suggest_capabilities(active=set()) must omit it.
    # (Construct minimal entities/surfaces that produce at least one relevance, then
    #  assert any gated_by item is dropped when its capability isn't active.)
    # See discovery test fixtures for builders.
    ...
```

(Use the existing discovery test fixtures/builders for entities+surfaces; assert that an item whose `gated_by` is set is present when `active` includes it and absent when it doesn't. If no rule emits a gated relevance yet, this test is written against a synthetic `Relevance` passed through the filter function directly — extract the filter as `_filter_relevance(items, active)` in engine.py and unit-test that.)

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3a: Add the field** in `models.py` `Relevance`:

```python
    gated_by: str | None = None  # capability id required to surface this (#1342)
```

- [ ] **Step 3b: Filter in `engine.py`** — change `suggest_capabilities(...)` to accept `active: set[str] | None = None` and drop gated-inactive items before returning:

```python
def suggest_capabilities(..., active: set[str] | None = None) -> list[Relevance]:
    active = active or set()
    ...
    enriched = [...]  # existing
    from dazzle.core.capabilities.cognition import partition_by_capability

    surfaced, _gated = partition_by_capability(
        enriched, active, capability_of=lambda r: r.gated_by
    )
    return surfaced
```

(Default `active=set()` keeps every existing caller's behaviour identical, because no rule sets `gated_by` yet → nothing is filtered.)

- [ ] **Step 4: Run → pass**, and `pytest tests/unit -k discovery -q` stays green.

- [ ] **Step 5: Commit** — `feat(discovery): gated_by on Relevance + active-capability filter (#1342)`

---

## Task 4: Thread `active` through lint → dsl(lint) handler

**Files:**
- Modify: `src/dazzle/core/lint.py` (`lint_appspec` → pass `active` into `suggest_capabilities`)
- Modify: the dsl lint handler (resolve active from `project_root`)
- Test: addition asserting the handler passes the resolved set

- [ ] **Step 1: Write the failing test** — a test that `lint_appspec(appspec, active={...})` forwards to `suggest_capabilities` (monkeypatch `suggest_capabilities` to capture the `active` kwarg), and that the dsl handler resolves it from the project manifest.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3:** Add an `active: set[str] | None = None` param to `lint_appspec` (default None → `set()`), forward it to `suggest_capabilities(..., active=active)`. In the dsl lint handler (which has `project_root`), call `active_capabilities_for(project_root)` and pass it. Find the exact call site: `git grep -n "lint_appspec(" src/dazzle/mcp`.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(lint): gate relevance suggestions by active capabilities (#1342)`

---

## Task 5: spec_analyze — per-pattern `capability` + requirement-detection

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/spec_analyze.py` (`_propose_patterns`)
- Test: `tests/unit/test_capability_cognition.py`

- [ ] **Step 1: Write the failing test**

```python
def test_propose_patterns_gates_and_suggests(monkeypatch):
    from dazzle.mcp.server.handlers.spec_analyze import _propose_patterns

    # A spec that mentions an enterprise trigger, with the capability NOT active,
    # yields a capability_suggestion (enable hint), NOT a full pattern proposal.
    result = _propose_patterns(
        {"spec": "Staff sign in via Okta SSO."},
        active=set(),  # nothing declared
    )
    sugg = result.get("capability_suggestions", [])
    assert any(s["capability"] == "auth.enterprise.oidc" for s in sugg)
    # And when active, it surfaces as a normal proposal, not a suggestion:
    result2 = _propose_patterns(
        {"spec": "Staff sign in via Okta SSO."},
        active={"auth.enterprise.oidc"},
    )
    assert not result2.get("capability_suggestions")
```

(This test depends on Task 9 wiring a `capability` + triggers onto an enterprise pattern in patterns.toml. Land Task 9's patterns.toml edit first, or use a monkeypatched patterns blob in the test. Recommended: monkeypatch the patterns blob the function reads so this task is independent of Task 9.)

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3:** In `_propose_patterns`:
  - Read an optional `capability = entry.get("capability")` per pattern.
  - Accept `active: set[str] | None = None` (default empty).
  - After computing `matched` triggers: if the pattern has a `capability` and it's not in `active`, append an `enable_suggestion(capability)` to a `capability_suggestions` list instead of adding the full proposal to `pattern_proposals`. Ungated or active patterns proceed as today.
  - Return `capability_suggestions` in the result dict (default `[]`).
  - Bump `SEED_SCHEMA_VERSION`? No — this reads patterns.toml at request time, not the KG seed. (Only Task 9's patterns.toml data change needs the KG reseed consideration — and patterns proposals read the TOML directly here, so no reseed needed.)

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(spec-analyze): gate pattern proposals + emit capability suggestions (#1342)`

---

## Task 6: bootstrap — resolve active + surface suggestions

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/bootstrap.py`
- Test: addition to a bootstrap test

- [ ] **Step 1: Write the failing test** — invoke the bootstrap cognition pass with a `work_dir` whose manifest declares nothing and a spec mentioning "Okta"; assert the briefing contains a `capability_suggestions` entry for `auth.enterprise.oidc`. With the capability declared, assert it's absent from suggestions.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3:** In `_run_cognition_pass` (`bootstrap.py:114`):
  - `active = active_capabilities_for(work_dir)` (work_dir is at `bootstrap.py:39`; thread it into `_run_cognition_pass`).
  - Pass `active` into the `propose_patterns` call (via the handler args or a direct `_propose_patterns(..., active=active)`).
  - Add `result["capability_suggestions"]` from the propose result into the briefing (e.g. `briefing["analysis"]["capability_suggestions"]`), and add a one-line `agent_instructions` note: "If a capability_suggestion is present, run its `enable` command before authoring that area."

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(bootstrap): surface capability-enable suggestions from the spec (#1342)`

---

## Task 7: counter-prior optional `capability` gate

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/counter_priors.py` (model + loader)
- Modify: `src/dazzle/mcp/server/handlers/spec_analyze.py` (antipattern-flag filter)
- Test: addition

- [ ] **Step 1: Write the failing test** — a counter-prior with `capability` set is flagged as an antipattern only when not active → becomes a suggestion; ungated counter-priors always flag. (Monkeypatch the loaded counter-prior list.)

- [ ] **Step 2–4:** Add optional `capability: str | None = None` to the `CounterPrior` model (Pydantic, default None) + read it from the `.md` frontmatter in the loader. In `_propose_patterns`'s antipattern-flag loop, apply the same gate as Task 5. Run → pass.

- [ ] **Step 5: Commit** — `feat(counter-priors): optional capability gate on antipattern flags (#1342)`

---

## Task 8: keep the pull path ungated (regression test)

**Files:**
- Test: `tests/unit/test_capability_cognition.py`

- [ ] **Step 1: Write the test** — call the `knowledge` `counter_prior` / `concept` handlers directly for a (hypothetically) capability-gated entry and assert the content is returned regardless of active capabilities. This pins the push/pull contract: direct queries never gate.

- [ ] **Step 2: Run → pass** (no code change expected — the knowledge handlers don't filter; this is a guard test). If it fails, the pull path was wrongly gated — fix by removing the filter there.

- [ ] **Step 3: Commit** — `test(capabilities): pull path (knowledge tool) stays ungated (#1342)`

---

## Task 9: one real gated pattern (exercise the mechanism end-to-end)

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/patterns.toml`
- Test: an end-to-end assertion through bootstrap

- [ ] **Step 1:** Give the enterprise pattern a `capability` + triggers in `patterns.toml`, e.g. on a new/existing `enterprise_sso` pattern:

```toml
[patterns.enterprise_sso]
category = "Auth"
capability = "auth.enterprise.oidc"
triggers = ["okta", "entra", "azure ad", "enterprise sso", "saml", "single sign-on", "scim"]
definition = "Per-org enterprise SSO via OIDC/SAML connections (opt-in capability)."
# … existing pattern fields …
```

- [ ] **Step 2:** End-to-end test: a spec mentioning "Okta" with no capability declared → bootstrap briefing carries the `auth.enterprise.oidc` enable suggestion and NO full enterprise_sso proposal; with it declared → the proposal appears and the suggestion does not.

- [ ] **Step 3:** Run → pass; run `pytest tests/unit -k "spec_analyze or bootstrap or docs_drift" -q` (the patterns.toml change may touch drift tests — update baselines if a drift gate flags the new pattern, with a CHANGELOG note).

- [ ] **Step 4: Commit** — `feat(kb): enterprise_sso pattern gated by auth.enterprise.oidc (#1342)`

---

## Task 10: docs + CHANGELOG

- [ ] Update `docs/superpowers/specs/2026-06-06-capability-opt-in-model-design.md`? No — spec is the record. Instead note Phase 2 done in the CHANGELOG and add a short "Cognition gating" subsection to `docs/reference/enterprise-sso.md` ("the agent only suggests enterprise SSO when your spec asks for it; declare the capability to enable full guidance").
- [ ] CHANGELOG `### Added`: push/pull cognition gating — proactive surfaces (bootstrap, lint relevance, spec-analyze proposals, counter-prior flags) gate on active capabilities; a stated requirement surfaces a `dazzle capability enable` suggestion; the `knowledge` pull path stays ungated.
- [ ] `#### Agent Guidance`: to gate guidance behind a capability, set `gated_by` (Relevance) / `capability` (pattern, counter-prior); it auto-converts to an enable-suggestion when the spec requests it but the app hasn't opted in.

---

## Final integration check (before ship)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/`
- [ ] `mypy src/dazzle`
- [ ] `pytest tests/ -m "not e2e"` — full unit suite green (watch `test_docs_drift` / KG-seed tests for the patterns.toml change)
- [ ] Manual MCP smoke: `bootstrap` on a spec mentioning Okta (no `[capabilities]`) → briefing has the enable suggestion; add `enabled=["auth.enterprise.oidc"]` → suggestion gone, proposal present; `knowledge counter_prior` for any gated entry still returns it.
- [ ] `/bump patch`, commit, push, monitor CI, comment on #1342.

## Notes for the implementer
- **Default-empty active set everywhere** keeps every existing caller byte-identical until a `gated_by`/`capability` is actually set — so Tasks 1-8 are safe no-ops behaviourally until Task 9 wires the first gated entry.
- **Non-raising on the cognition path** is load-bearing: never let `active_capabilities_for` or a filter raise into an advisory MCP read.
- **No KG reseed** needed for the proposal path (reads patterns.toml live); only confirm `test_docs_drift` if it enumerates patterns.
