# Answer-First Landing (2a → L4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take UX-maturity criterion 2a (answer-first landing) from L3 to L4 by inferring a persona's landing workspace from its rhythm when `default_workspace` is unset, plus a `dazzle rhythm fidelity` drift warning when a declared landing contradicts the rhythm.

**Architecture:** A new rhythm-only pure helper `infer_landing_workspace` (+ `check_landing_drift`) in `src/dazzle/page/runtime/landing_resolver.py`. It is consulted from the existing `_resolve_persona_route` precedence chain (a new "step 2.5", after declared `default_workspace`, before the generic workspace fallbacks). The drift helper is surfaced in `dazzle rhythm fidelity`. The `_probe_2a` maturity probe (currently absent) is written against synthetic in-memory IR and the 2a criterion is bumped L3→L4.

**Tech Stack:** Python 3.12, Pydantic IR models (`dazzle.core.ir`), pytest.

## Global Constraints

- **Rhythm-only** — no story path. Stories carry no landing concept.
- **No grammar change, no new DSL keyword** — `default_workspace` stays the author's knob.
- **Cold-start byte-identical** — an app with a declared `default_workspace` on every persona, or with no rhythms, produces an identical route map. Inference fires ONLY when both `persona.default_route` and `persona.default_workspace` are unset.
- **Declaration authoritative** — inference never overrides an explicit declaration.
- **`rhythms` is a REQUIRED parameter** (clean break per ADR-0003 — update all callers in the same commit; no default value, no shim).
- **Persona identity by `.id`** — `RhythmSpec.persona` holds the persona id; match `rhythm.persona == persona.id`. Never `.name`/`.label`.
- **v1 workspace-only surface resolution** — infer only when the scene's `surface` names a workspace directly; a bare surface → `None` (fall through).
- **venv python:** `/Volumes/SSD/Dazzle/.venv/bin/python`. Run tests as `… -m pytest <path> -p no:cacheprovider`.

Reference IR field facts (verified):
- `PersonaSpec`: `id: str` (req), `label: str` (req), `default_workspace: str | None = None`, `default_route: str | None = None`.
- `WorkspaceSpec`: `name: str` (req), everything else defaulted.
- `RhythmSpec`: `name: str` (req), `persona: str` (req), `phases: list[PhaseSpec] = []`.
- `PhaseSpec`: `name: str` (req), `kind: PhaseKind | None = None`, `scenes: list[SceneSpec] = []`.
- `SceneSpec`: `name: str` (req), `surface: str` (req).
- `PhaseKind`: `ONBOARDING, GATE, ACTIVE, PERIODIC, AMBIENT, OFFBOARDING`.

---

### Task 1: `infer_landing_workspace` + `check_landing_drift` (pure helpers)

**Files:**
- Create: `src/dazzle/page/runtime/landing_resolver.py`
- Test: `tests/unit/test_landing_resolver.py`

**Interfaces:**
- Produces:
  - `infer_landing_workspace(persona: ir.PersonaSpec, rhythms: list[ir.RhythmSpec], workspaces: list[ir.WorkspaceSpec]) -> str | None`
  - `check_landing_drift(persona: ir.PersonaSpec, rhythms: list[ir.RhythmSpec], workspaces: list[ir.WorkspaceSpec]) -> str | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_landing_resolver.py
from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.page.runtime.landing_resolver import (
    check_landing_drift,
    infer_landing_workspace,
)


def _persona(pid, *, default_workspace=None, default_route=None):
    return ir.PersonaSpec(
        id=pid, label=pid.title(),
        default_workspace=default_workspace, default_route=default_route,
    )


def _ws(*names):
    return [ir.WorkspaceSpec(name=n) for n in names]


def _rhythm(persona, phases):
    # phases: list of (kind, [scene_surface, ...])
    return ir.RhythmSpec(
        name=f"{persona}_rhythm", persona=persona,
        phases=[
            ir.PhaseSpec(
                name=f"p{i}", kind=kind,
                scenes=[ir.SceneSpec(name=f"s{j}", surface=surf)
                        for j, surf in enumerate(surfaces)],
            )
            for i, (kind, surfaces) in enumerate(phases)
        ],
    )


def test_infers_first_active_scene_workspace():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue", "detail"])])
    assert infer_landing_workspace(p, [r], _ws("queue", "detail")) == "queue"


def test_kind_unset_uses_first_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["queue"]), (None, ["reports"])])
    assert infer_landing_workspace(p, [r], _ws("queue", "reports")) == "queue"


def test_explicit_active_preferred_over_earlier_unmarked_phase():
    p = _persona("agent")
    r = _rhythm("agent", [(None, ["onboard"]), (PhaseKind.ACTIVE, ["queue"])])
    # first unmarked phase 'onboard' is NOT a one-time kind, but an explicit
    # ACTIVE phase wins over it.
    assert infer_landing_workspace(p, [r], _ws("onboard", "queue")) == "queue"


def test_skips_onboarding_gate_offboarding_phases():
    p = _persona("agent")
    r = _rhythm("agent", [
        (PhaseKind.ONBOARDING, ["welcome"]),
        (PhaseKind.GATE, ["verify"]),
        (None, ["queue"]),
    ])
    assert infer_landing_workspace(p, [r], _ws("welcome", "verify", "queue")) == "queue"


def test_only_one_time_phases_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ONBOARDING, ["welcome"]),
                          (PhaseKind.OFFBOARDING, ["bye"])])
    assert infer_landing_workspace(p, [r], _ws("welcome", "bye")) is None


def test_bare_surface_not_a_workspace_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["ticket_list"])])  # a surface, no ws
    assert infer_landing_workspace(p, [r], _ws("queue", "reports")) is None


def test_no_rhythm_for_persona_infers_nothing():
    p = _persona("agent")
    r = _rhythm("manager", [(PhaseKind.ACTIVE, ["queue"])])  # different persona
    assert infer_landing_workspace(p, [r], _ws("queue")) is None


def test_multiple_rhythms_first_declared_wins():
    p = _persona("agent")
    r1 = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    r2 = _rhythm("agent", [(PhaseKind.ACTIVE, ["reports"])])
    assert infer_landing_workspace(p, [r1, r2], _ws("queue", "reports")) == "queue"


def test_empty_active_phase_infers_nothing():
    p = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, [])])  # no scenes
    assert infer_landing_workspace(p, [r], _ws("queue")) is None


def test_drift_warns_when_declared_contradicts_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    msg = check_landing_drift(p, [r], _ws("queue", "reports"))
    assert msg is not None and "reports" in msg and "queue" in msg


def test_drift_silent_when_declared_matches_rhythm():
    p = _persona("agent", default_workspace="queue")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p, [r], _ws("queue")) is None


def test_drift_silent_without_declaration_or_rhythm():
    p_nodecl = _persona("agent")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    assert check_landing_drift(p_nodecl, [r], _ws("queue")) is None
    p_norhythm = _persona("agent", default_workspace="queue")
    assert check_landing_drift(p_norhythm, [], _ws("queue")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_landing_resolver.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: dazzle.page.runtime.landing_resolver`.

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/page/runtime/landing_resolver.py
"""#1558 (2a → L4): infer a persona's answer-first landing workspace from its
rhythm when `default_workspace` is unset, and detect declared-vs-rhythm drift.

Rhythm-only, pure, no I/O. Declaration precedence lives in the caller
(`_resolve_persona_route`); this module only produces the *inferred* signal.
"""

from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind

# Phases that are NOT a persona's day-to-day landing (one-time / boundary).
_ONE_TIME_KINDS = frozenset({PhaseKind.ONBOARDING, PhaseKind.GATE, PhaseKind.OFFBOARDING})


def _select_active_phase(rhythm: ir.RhythmSpec) -> ir.PhaseSpec | None:
    """The phase whose first scene represents the persona's day-to-day landing.

    `PhaseSpec.kind` is an optional hint (usually unset). Prefer an explicit
    ACTIVE phase; else the first phase that is not a one-time boundary phase
    (with kind unset everywhere this is simply the first declared phase, since
    phases are in temporal order); else None.
    """
    for phase in rhythm.phases:
        if phase.kind == PhaseKind.ACTIVE:
            return phase
    for phase in rhythm.phases:
        if phase.kind not in _ONE_TIME_KINDS:  # None / ACTIVE / PERIODIC / AMBIENT
            return phase
    return None


def infer_landing_workspace(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> str | None:
    """Return the workspace name inferred from the persona's rhythm, or None.

    Does NOT consider `persona.default_workspace` — the caller owns declaration
    precedence. v1 acts only when the scene surface names a workspace directly.
    """
    rhythm = next((r for r in rhythms if r.persona == persona.id), None)
    if rhythm is None:
        return None
    phase = _select_active_phase(rhythm)
    if phase is None or not phase.scenes:
        return None
    surface = phase.scenes[0].surface
    workspace_names = {ws.name for ws in workspaces}
    return surface if surface in workspace_names else None


def check_landing_drift(
    persona: ir.PersonaSpec,
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> str | None:
    """Return an advisory warning when a declared `default_workspace`
    contradicts the persona's rhythm-inferred landing, else None."""
    if not persona.default_workspace:
        return None
    inferred = infer_landing_workspace(persona, rhythms, workspaces)
    if inferred is None or inferred == persona.default_workspace:
        return None
    return (
        f"persona {persona.id!r} declares default_workspace="
        f"{persona.default_workspace!r}, but its rhythm's active landing points "
        f"at {inferred!r} — the landing may not be answer-first for this persona"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_landing_resolver.py -q -p no:cacheprovider`
Expected: PASS (12 tests).

- [ ] **Step 5: Lint + type-check**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/page/runtime/landing_resolver.py tests/unit/test_landing_resolver.py --fix && /Volumes/SSD/Dazzle/.venv/bin/python -m ruff format src/dazzle/page/runtime/landing_resolver.py tests/unit/test_landing_resolver.py`
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/page/runtime/landing_resolver.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/page/runtime/landing_resolver.py tests/unit/test_landing_resolver.py
git commit -m "feat(landing): rhythm-based answer-first landing inference + drift helper (#1558)"
```

---

### Task 2: Wire inference into `_resolve_persona_route` (step 2.5)

**Files:**
- Modify: `src/dazzle/page/converters/workspace_converter.py` (`compute_persona_default_routes` ~476, `_resolve_persona_route` ~507)
- Modify: `src/dazzle/http/runtime/app_factory.py:855` and `:1256` (call sites)
- Modify: `src/dazzle/cli/runtime_impl/serve.py:587` (call site)
- Test: `tests/unit/test_landing_resolver.py` (add integration cases)

**Interfaces:**
- Consumes: `infer_landing_workspace` (Task 1).
- Produces: `compute_persona_default_routes(personas, workspaces, rhythms)` — `rhythms` is a REQUIRED 3rd positional param; `_resolve_persona_route(persona, workspaces, rhythms)` likewise.

- [ ] **Step 1: Write the failing integration test**

```python
# append to tests/unit/test_landing_resolver.py
from dazzle.page.converters.workspace_converter import compute_persona_default_routes


def test_route_map_infers_when_default_workspace_unset():
    p = _persona("agent")  # no default_workspace, no default_route
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r])
    # 'queue' workspace root route ends with the workspace slug.
    assert "agent" in routes
    assert "queue" in routes["agent"]


def test_route_map_declaration_wins_over_rhythm():
    p = _persona("agent", default_workspace="reports")
    r = _rhythm("agent", [(PhaseKind.ACTIVE, ["queue"])])  # contradicts
    routes = compute_persona_default_routes([p], _ws("queue", "reports"), [r])
    assert "reports" in routes["agent"] and "queue" not in routes["agent"]


def test_route_map_no_rhythm_is_unchanged_fallback():
    # No declaration, no rhythm: falls through to the first-workspace fallback
    # exactly as before (byte-identical behaviour).
    p = _persona("agent")
    routes_with = compute_persona_default_routes([p], _ws("first", "second"), [])
    assert routes_with["agent"] == compute_persona_default_routes(
        [p], _ws("first", "second"), []
    )["agent"]
    assert "first" in routes_with["agent"]
```

- [ ] **Step 2: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_landing_resolver.py -q -p no:cacheprovider -k route_map`
Expected: FAIL — `compute_persona_default_routes()` takes 2 positional args but 3 given.

- [ ] **Step 3: Add `rhythms` param + step 2.5**

In `src/dazzle/page/converters/workspace_converter.py`, add the import near the top:

```python
from dazzle.page.runtime.landing_resolver import infer_landing_workspace
```

Change `compute_persona_default_routes`:

```python
def compute_persona_default_routes(
    personas: list[ir.PersonaSpec],
    workspaces: list[ir.WorkspaceSpec],
    rhythms: list[ir.RhythmSpec],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for persona in personas:
        route = _resolve_persona_route(persona, workspaces, rhythms)
        if route:
            result[persona.id] = route
    return result
```

Change `_resolve_persona_route` — add `rhythms` param and insert step 2.5 between the `default_workspace` block and the "First workspace with explicit persona access" block:

```python
def _resolve_persona_route(
    persona: ir.PersonaSpec,
    workspaces: list[ir.WorkspaceSpec],
    rhythms: list[ir.RhythmSpec],
) -> str | None:
    """Resolve the default route for a single persona."""
    # 1. Explicit default_route
    if persona.default_route:
        return persona.default_route

    # 2. Default workspace
    if persona.default_workspace:
        for ws in workspaces:
            if ws.name == persona.default_workspace:
                return _workspace_root_route(ws)

    # 2.5 (#1558): infer the answer-first landing from the persona's rhythm.
    inferred = infer_landing_workspace(persona, rhythms, workspaces)
    if inferred:
        for ws in workspaces:
            if ws.name == inferred:
                return _workspace_root_route(ws)

    # 3. First workspace with explicit persona access
    for ws in workspaces:
        if ws.access and persona.id in ws.access.allow_personas:
            return _workspace_root_route(ws)

    # 4. First workspace with AUTHENTICATED access (any logged-in user)
    for ws in workspaces:
        if ws.access and ws.access.level == ir.WorkspaceAccessLevel.AUTHENTICATED:
            return _workspace_root_route(ws)

    # 5. Fallback to first workspace
    if workspaces:
        return _workspace_root_route(workspaces[0])

    return None
```

Leave `resolve_persona_workspace_route` (~539) UNCHANGED — it is a separate workspace-only variant not on the redirect path; out of scope.

- [ ] **Step 4: Update all call sites (clean break — same commit)**

`src/dazzle/http/runtime/app_factory.py:855`:
```python
            persona_routes = compute_persona_default_routes(
                appspec.personas, appspec.workspaces, appspec.rhythms
            )
```
`src/dazzle/http/runtime/app_factory.py:1256`:
```python
    persona_routes = compute_persona_default_routes(
        appspec.personas, appspec.workspaces, appspec.rhythms
    )
```
`src/dazzle/cli/runtime_impl/serve.py:587`:
```python
    persona_routes = compute_persona_default_routes(
        appspec.personas, appspec.workspaces, appspec.rhythms
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_landing_resolver.py -q -p no:cacheprovider`
Expected: PASS (all Task 1 + Task 2 tests).

Then guard against a missed caller anywhere in the tree:

Run: `grep -rn "compute_persona_default_routes(" src/dazzle tests | grep -v "def compute_persona_default_routes"`
Expected: every call passes THREE arguments. Fix any two-arg call (including in tests).

- [ ] **Step 6: Lint + type-check the changed files**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/page/converters/workspace_converter.py src/dazzle/http/runtime/app_factory.py src/dazzle/cli/runtime_impl/serve.py --fix`
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/page/converters/workspace_converter.py src/dazzle/http/runtime/app_factory.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(landing): consult rhythm inference in persona route resolution (#1558)"
```

---

### Task 3: Surface the drift warning in `dazzle rhythm fidelity`

**Files:**
- Modify: `src/dazzle/cli/rhythm.py` (`rhythm_fidelity` command, ~86)
- Test: `tests/unit/test_rhythm_fidelity_drift.py` (new)

**Interfaces:**
- Consumes: `check_landing_drift` (Task 1).

- [ ] **Step 1: Read the current command**

Run: `sed -n '86,140p' src/dazzle/cli/rhythm.py`
Note how it loads the AppSpec/manifest and prints output (`typer.echo` / `format_output`). The drift line is emitted for the fidelity target rhythm's persona.

- [ ] **Step 2: Write the failing test**

The command needs an AppSpec with a persona whose `default_workspace` contradicts its rhythm. Rather than boot a project, test the surfacing helper directly. Add a thin module-level helper in `rhythm.py` that the command calls, and unit-test the helper:

```python
# tests/unit/test_rhythm_fidelity_drift.py
from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.cli.rhythm import landing_drift_lines


def _ws(*names):
    return [ir.WorkspaceSpec(name=n) for n in names]


def test_landing_drift_lines_reports_contradiction():
    p = ir.PersonaSpec(id="agent", label="Agent", default_workspace="reports")
    r = ir.RhythmSpec(
        name="agent_daily", persona="agent",
        phases=[ir.PhaseSpec(name="active", kind=PhaseKind.ACTIVE,
                             scenes=[ir.SceneSpec(name="s", surface="queue")])],
    )
    lines = landing_drift_lines([p], [r], _ws("queue", "reports"))
    assert len(lines) == 1 and "queue" in lines[0] and "reports" in lines[0]


def test_landing_drift_lines_empty_when_coherent():
    p = ir.PersonaSpec(id="agent", label="Agent", default_workspace="queue")
    r = ir.RhythmSpec(
        name="agent_daily", persona="agent",
        phases=[ir.PhaseSpec(name="active", kind=PhaseKind.ACTIVE,
                             scenes=[ir.SceneSpec(name="s", surface="queue")])],
    )
    assert landing_drift_lines([p], [r], _ws("queue")) == []
```

- [ ] **Step 3: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_rhythm_fidelity_drift.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'landing_drift_lines'`.

- [ ] **Step 4: Add the helper + call it from the command**

In `src/dazzle/cli/rhythm.py`, add:

```python
from dazzle.core import ir
from dazzle.page.runtime.landing_resolver import check_landing_drift


def landing_drift_lines(
    personas: list[ir.PersonaSpec],
    rhythms: list[ir.RhythmSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> list[str]:
    """One advisory line per persona whose declared default_workspace
    contradicts its rhythm-inferred answer-first landing (#1558)."""
    lines: list[str] = []
    for persona in personas:
        msg = check_landing_drift(persona, rhythms, workspaces)
        if msg:
            lines.append(msg)
    return lines
```

Then, inside `rhythm_fidelity`, after the existing fidelity output is produced and the AppSpec is in scope (it loads the manifest/appspec — reuse that `appspec` variable), emit the drift lines:

```python
    drift = landing_drift_lines(appspec.personas, appspec.rhythms, appspec.workspaces)
    for line in drift:
        typer.echo(f"landing-drift: {line}")
```

If `rhythm_fidelity` does not already hold an `appspec`, load it the same way `rhythm_gaps` does (copy the manifest→appspec load lines from that command in the same file — do not invent a new loader).

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_rhythm_fidelity_drift.py -q -p no:cacheprovider`
Expected: PASS (2 tests).

- [ ] **Step 6: Lint + type-check**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/cli/rhythm.py tests/unit/test_rhythm_fidelity_drift.py --fix`
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/cli/rhythm.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(rhythm): surface answer-first landing drift in rhythm fidelity (#1558)"
```

---

### Task 4: `_probe_2a` + criterion L3 → L4

**Files:**
- Modify: `src/dazzle/qa/ux_maturity.py` (add `_probe_2a`; change the `"2a"` `Criterion` — `declared` 3→4, `probe` None→`_probe_2a`, update `evidence`)
- Test: `tests/unit/test_ux_maturity_2a.py` (new)

**Interfaces:**
- Consumes: `infer_landing_workspace`, `check_landing_drift` (Task 1); `compute_persona_default_routes` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_maturity_2a.py
from dazzle.qa import ux_maturity as m


def _crit(cid):
    return next(c for c in m.CRITERIA if c.id == cid)


def test_2a_declared_l4_with_probe():
    c = _crit("2a")
    assert c.declared == 4
    assert c.probe is not None


def test_2a_probe_passes():
    c = _crit("2a")
    result = c.probe()
    assert result.ok, result.note
```

- [ ] **Step 2: Run to verify failure**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_ux_maturity_2a.py -q -p no:cacheprovider`
Expected: FAIL — `c.declared == 3` and `c.probe is None`.

- [ ] **Step 3: Write `_probe_2a` and bump the criterion**

Add near the other probes in `src/dazzle/qa/ux_maturity.py`:

```python
def _probe_2a() -> ProbeResult:
    """Answer-first landing is inferred from rhythms when default_workspace is
    unset, declaration stays authoritative, and drift is detectable (level 4,
    #1558). Exercised against synthetic in-memory IR (no app boot)."""
    from dazzle.core import ir
    from dazzle.core.ir.rhythm import PhaseKind
    from dazzle.page.converters.workspace_converter import (
        compute_persona_default_routes,
    )
    from dazzle.page.runtime.landing_resolver import check_landing_drift

    ws = [ir.WorkspaceSpec(name="queue"), ir.WorkspaceSpec(name="reports")]
    rhythm = ir.RhythmSpec(
        name="agent_daily", persona="agent",
        phases=[ir.PhaseSpec(name="active", kind=PhaseKind.ACTIVE,
                             scenes=[ir.SceneSpec(name="review", surface="queue")])],
    )

    # (a) infer when unset
    p_unset = ir.PersonaSpec(id="agent", label="Agent")
    infer_routes = compute_persona_default_routes([p_unset], ws, [rhythm])
    infers = "agent" in infer_routes and "queue" in infer_routes["agent"]

    # (b) declaration authoritative (contradicting rhythm ignored)
    p_decl = ir.PersonaSpec(id="agent", label="Agent", default_workspace="reports")
    decl_routes = compute_persona_default_routes([p_decl], ws, [rhythm])
    declaration_wins = "reports" in decl_routes["agent"] and "queue" not in decl_routes["agent"]

    # (c) drift detected on contradiction, silent on coherence
    drift_fires = check_landing_drift(p_decl, [rhythm], ws) is not None
    p_ok = ir.PersonaSpec(id="agent", label="Agent", default_workspace="queue")
    drift_silent = check_landing_drift(p_ok, [rhythm], ws) is None

    # cold-start: no rhythm → no inferred entry (fall through unchanged)
    cold = compute_persona_default_routes([p_unset], ws, [])
    cold_start_safe = "queue" not in cold.get("agent", "")

    ok = infers and declaration_wins and drift_fires and drift_silent and cold_start_safe
    return ProbeResult(
        ok=ok,
        note=(
            f"infer={infers} declaration_wins={declaration_wins} "
            f"drift_fires={drift_fires} drift_silent={drift_silent} "
            f"cold_start_safe={cold_start_safe}"
        ),
    )
```

Then change the `"2a"` entry in the `CRITERIA` list. Find the tuple/`Criterion` with `id="2a"` (currently `declared=3`, `probe=None`). Set `declared=4`, `probe=_probe_2a`, and replace the `evidence` string with:

```python
        "#1558 L3 + rhythm inference L4 — the answer-first landing is inferred "
        "from a persona's rhythm (first ACTIVE-phase scene naming a workspace) "
        "when default_workspace is unset, via infer_landing_workspace consulted "
        "in _resolve_persona_route; an explicit default_workspace stays "
        "authoritative and cold-start (no rhythm) is byte-identical; declared "
        "vs rhythm drift surfaces in `dazzle rhythm fidelity`.",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/test_ux_maturity_2a.py -q -p no:cacheprovider`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the maturity-model tests (index moved, no drift-gate breakage)**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -k "ux_maturity or maturity"`
Expected: PASS. If a test asserts the exact overall index or the count at L4 (was 11/13), update it to the new value (12/13). Show the diff of any such assertion before changing it.

- [ ] **Step 6: Lint + type-check**

Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m ruff check src/dazzle/qa/ux_maturity.py tests/unit/test_ux_maturity_2a.py --fix`
Run: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle/qa/ux_maturity.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(qa): 2a answer-first landing to L4 with rhythm-inference probe (#1558)"
```

---

## Final verification (before ship)

- [ ] Full type check: `/Volumes/SSD/Dazzle/.venv/bin/python -m mypy src/dazzle` → `Success`.
- [ ] Broader suite touching the changed seams:
  `/Volumes/SSD/Dazzle/.venv/bin/python -m pytest tests/unit/ -q -p no:cacheprovider -k "landing or persona_route or workspace_converter or ux_maturity or rhythm"` → PASS.
- [ ] `grep -rn "compute_persona_default_routes(" src/dazzle tests | grep -v "def "` → every call site passes 3 args.
- [ ] Ship discipline (per project CLAUDE.md): `/bump patch`, then commit + push (push main BEFORE tagging), then monitor CI. Add a CHANGELOG entry under `### Added` with an `### Agent Guidance` note that `default_workspace` inference now falls back to a persona's rhythm ACTIVE-phase landing, and that `dazzle rhythm fidelity` reports declared-vs-rhythm drift.

## Self-review notes (author)

- **Spec coverage:** resolver (Task 1) ✓; wiring/precedence (Task 2) ✓; drift check in rhythm fidelity (Task 3) ✓; probe L3→L4 (Task 4) ✓; cold-start byte-identical (Task 2 test + probe) ✓; no fixture (synthetic IR) ✓.
- **Type consistency:** `infer_landing_workspace(persona, rhythms, workspaces)` and `check_landing_drift(persona, rhythms, workspaces)` use identical signatures across Tasks 1/2/3/4; `compute_persona_default_routes(personas, workspaces, rhythms)` consistent across Task 2 + probe.
- **YAGNI:** no story path; no bare-surface→workspace mapping; `resolve_persona_workspace_route` left untouched.
