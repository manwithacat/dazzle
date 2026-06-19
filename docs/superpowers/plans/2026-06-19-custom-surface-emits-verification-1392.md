# Custom-surface emitted-target verification (#1392 item 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, this session) or superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Let a custom surface declare the surfaces/routes it links to (DSL `emits:` clause on `render:`/custom surfaces; `# dazzle:emits` header on route-overrides), and fail the build when a declared target resolves to nothing.

**Architecture:** Two declaration sites, resolved in their native layer — DSL `emits:` (surface names) validated in **core** (`dazzle validate`, mirroring `primary_action -> surface`); `# dazzle:emits <path>` (route-override header) validated in **back** (mirroring `verify_route_matrix_completeness`, #1420 D3). A dead target is a build/validate error.

**Tech Stack:** Python 3.12, Pydantic frozen IR, the dispatch-table surface parser, the route-override regex-scan discovery, pytest.

## Global Constraints (verbatim from spec)
- **Opt-in / incremental:** no `emits:` / no `# dazzle:emits` ⇒ no new constraint (today's behavior). `SurfaceSpec.emits` default `()`.
- **Declared-target resolution only** — NOT render-and-crawl. Verify declared targets resolve; do not detect undeclared emitted links.
- **Build error** on a dead target (matches `primary_action -> surface` + the issue's "fail the build").
- **Not a fix for #1421** (framework-route bug, distinct).
- Ship discipline: per-phase gate green → `/bump patch` + commit + push; full `pytest -m "not e2e"` before each main push; ir-types baseline regen when IR changes.

## File map
- `src/dazzle/core/ir/surfaces.py` — add `SurfaceSpec.emits: tuple[str, ...] = ()`.
- `src/dazzle/core/dsl_parser_impl/surface.py` — `_kw_emits` + register in `_SURFACE_IDENT_KEYWORDS`; `_SurfaceState.emits`; wire into `_build_surface`.
- `src/dazzle/core/validation/ux.py` (or `surfaces.py`) — `validate_emits_targets` (surface-name resolution); wired into the validate/lint pass.
- `src/dazzle/back/runtime/route_overrides.py` — `_EMITS_RE`, `RouteOverrideDescriptor.emits_paths`, parse in `discover_route_overrides`, `verify_emits_paths(overrides, route_paths)`.
- `tests/unit/test_emits_*.py` — parser, validator, header-scan, path-resolver.
- one example/fixture custom surface + `docs/reference/` note + CHANGELOG.

---

## Task 1 (P1): `SurfaceSpec.emits` IR + DSL parser

**Files:**
- Modify: `src/dazzle/core/ir/surfaces.py` (SurfaceSpec, ~line 364 near `render:`)
- Modify: `src/dazzle/core/dsl_parser_impl/surface.py` (`_SurfaceState` ~L660, `_kw_*` defs ~L696, `_SURFACE_IDENT_KEYWORDS` ~L850, `_build_surface` SurfaceSpec call)
- Test: `tests/unit/test_emits_parsing.py`

**Interfaces — Produces:** `SurfaceSpec.emits: tuple[str, ...]` (default `()`); DSL `emits: [name, name]` clause.

- [ ] **Step 1: Write the failing test** (`tests/unit/test_emits_parsing.py`)
```python
from pathlib import Path
from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """module t
app t "T"
entity Task "Task":
  id: uuid pk
  title: str(80)
surface task_detail "Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [task_detail, task_create]
"""

def _surfaces(dsl):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return {s.name: s for s in frag.surfaces}

def test_emits_clause_parses_into_tuple():
    board = _surfaces(_DSL)["task_board"]
    assert board.emits == ("task_detail", "task_create")

def test_absent_emits_defaults_empty():
    board = _surfaces(_DSL)["task_detail"]
    assert board.emits == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_parsing.py -q`
Expected: FAIL — `emits: [...]` is an unknown keyword (parse error) or `SurfaceSpec` has no `emits`.

- [ ] **Step 3: Add the IR field** — in `surfaces.py`, after the `render: str | None = None` field on `SurfaceSpec`:
```python
    # #1392 item 3: surfaces this custom surface links to (the dead-target gate).
    # Each name must resolve to a declared surface (validated like primary_action).
    # () = undeclared/unconstrained (opt-in).
    emits: tuple[str, ...] = ()
```

- [ ] **Step 4: Add the parser** — in `surface.py`:

State field (in `_SurfaceState`, near `display: str | None = None`):
```python
    emits: list[str] = field(default_factory=list)  # #1392 item 3
```
Keyword parser (near `_kw_display`):
```python
def _kw_emits(parser: Any, state: _SurfaceState) -> None:
    """``emits: [surface_a, surface_b]`` — surfaces this custom surface links to (#1392 item 3)."""
    parser.advance()  # consume 'emits'
    parser.expect(TokenType.COLON)
    parser.expect(TokenType.LBRACKET)
    while not parser.match(TokenType.RBRACKET):
        state.emits.append(parser.expect_identifier_or_keyword().value)
        if parser.match(TokenType.COMMA):
            parser.advance()
    parser.expect(TokenType.RBRACKET)
    parser.skip_newlines()
```
Register (in `_SURFACE_IDENT_KEYWORDS`):
```python
    "emits": _kw_emits,  # #1392 item 3 — declared link targets
```
Wire into `_build_surface`'s `ir.SurfaceSpec(...)` call:
```python
        emits=tuple(state.emits),
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_parsing.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Regen ir-types baseline + drift**

Run: `.venv/bin/dazzle inspect api ir-types --write && .venv/bin/python -m pytest tests/unit/test_api_surface_drift.py tests/integration/test_golden_master.py -q -p no:cacheprovider`
Expected: PASS (golden-master may need `--snapshot-update` — if so, run `.venv/bin/python -m pytest tests/integration/test_golden_master.py --snapshot-update -q` and re-run). CHANGELOG note for the baseline change comes in Task 4.

- [ ] **Step 7: ruff + commit**
```bash
.venv/bin/ruff format src/dazzle/core/ir/surfaces.py src/dazzle/core/dsl_parser_impl/surface.py tests/unit/test_emits_parsing.py
.venv/bin/ruff check src/dazzle/core/ir/surfaces.py src/dazzle/core/dsl_parser_impl/surface.py tests/unit/test_emits_parsing.py --fix
git add src/dazzle/core/ir/surfaces.py src/dazzle/core/dsl_parser_impl/surface.py tests/unit/test_emits_parsing.py docs/api-surface/ir-types.txt tests/integration/__snapshots__/test_golden_master.ambr
git commit -m "feat(dsl): emits: surface clause IR + parser (#1392 item 3 P1)"
```

---

## Task 2 (P2): route-override `# dazzle:emits` header scan

**Files:**
- Modify: `src/dazzle/back/runtime/route_overrides.py` (`_IMPLEMENTS_RE` block ~L43, `RouteOverrideDescriptor` ~L55, `discover_route_overrides` parse ~L210)
- Test: `tests/unit/test_emits_header_scan.py`

**Interfaces — Consumes:** `RouteOverrideDescriptor`. **Produces:** `RouteOverrideDescriptor.emits_paths: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test** (`tests/unit/test_emits_header_scan.py`)
```python
from pathlib import Path
from dazzle.back.runtime.route_overrides import discover_route_overrides

_OVERRIDE = '''# dazzle:route-override GET /app/board
# dazzle:emits /app/tasks/{id}
# dazzle:emits /app/tasks/create
def board(request):
    return None
'''

def test_emits_header_parsed(tmp_path: Path):
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "board.py").write_text(_OVERRIDE)
    overrides = discover_route_overrides(routes)
    o = next(o for o in overrides if o.path == "/app/board")
    assert o.emits_paths == ("/app/tasks/{id}", "/app/tasks/create")

def test_no_emits_header_is_empty(tmp_path: Path):
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "x.py").write_text("# dazzle:route-override GET /x\ndef x(r): return None\n")
    overrides = discover_route_overrides(routes)
    assert overrides[0].emits_paths == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_header_scan.py -q`
Expected: FAIL — `RouteOverrideDescriptor` has no `emits_paths`.

- [ ] **Step 3: Implement** — in `route_overrides.py`:

Regex (near `_IMPLEMENTS_RE`):
```python
# #1392 item 3: declared link/fetch targets the handler emits (one path per line).
_EMITS_RE = re.compile(r"#\s*dazzle:emits\s+(\S+)", re.IGNORECASE)
```
Descriptor field (in `RouteOverrideDescriptor`, after `implements_via`):
```python
    emits_paths: tuple[str, ...] = ()  # #1392 item 3 — declared link targets
```
Parse in `discover_route_overrides` (where `_IMPLEMENTS_RE.search(content)` runs ~L210):
```python
        emits_paths = tuple(m.group(1) for m in _EMITS_RE.finditer(content))
```
…and pass `emits_paths=emits_paths` into the `RouteOverrideDescriptor(...)` construction.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_header_scan.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: ruff + commit**
```bash
.venv/bin/ruff format src/dazzle/back/runtime/route_overrides.py tests/unit/test_emits_header_scan.py
.venv/bin/ruff check src/dazzle/back/runtime/route_overrides.py tests/unit/test_emits_header_scan.py --fix
git add src/dazzle/back/runtime/route_overrides.py tests/unit/test_emits_header_scan.py
git commit -m "feat(routes): # dazzle:emits header scan into RouteOverrideDescriptor (#1392 item 3 P2)"
```

---

## Task 3 (P3): resolver + build gate

**Files:**
- Modify: `src/dazzle/core/validation/ux.py` — `validate_emits_targets(appspec)` (DSL surface-name resolution)
- Modify: `src/dazzle/core/lint.py` — wire `validate_emits_targets` into the validate/lint pass (alongside the existing surface validators)
- Modify: `src/dazzle/back/runtime/route_overrides.py` — `verify_emits_paths(overrides, route_paths)` (override path resolution, mirrors `verify_route_matrix_completeness`)
- Test: `tests/unit/test_emits_validation.py`

**Interfaces — Consumes:** `SurfaceSpec.emits` (Task 1), `RouteOverrideDescriptor.emits_paths` (Task 2).
**Produces:** `validate_emits_targets(appspec) -> tuple[list[str], list[str]]` (errors, warnings); `verify_emits_paths(overrides: list[RouteOverrideDescriptor], route_paths: set[str]) -> list[str]` (violations).

- [ ] **Step 1: Write the failing test** (`tests/unit/test_emits_validation.py`)
```python
from pathlib import Path
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation.ux import validate_emits_targets

def _appspec(dsl):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return build_appspec([ModuleIR(name=n or "t", file=Path("t.dsl"), app_name=a,
        app_title=t, app_config=c, uses=u, fragment=frag)], "t")

_BASE = """module t
app t "T"
entity Task "Task":
  id: uuid pk
  title: str(80)
surface task_detail "Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [{targets}]
"""

def test_resolvable_emits_clean():
    errs, _ = validate_emits_targets(_appspec(_BASE.format(targets="task_detail")))
    assert errs == []

def test_dead_emit_target_errors():
    errs, _ = validate_emits_targets(_appspec(_BASE.format(targets="nonexistent_surface")))
    assert any("nonexistent_surface" in e and "E_DEAD_EMIT_TARGET" in e for e in errs)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_validation.py -q`
Expected: FAIL — `validate_emits_targets` does not exist.

- [ ] **Step 3: Implement the DSL resolver** — in `validation/ux.py`:
```python
def validate_emits_targets(appspec: "ir.AppSpec") -> tuple[list[str], list[str]]:
    """#1392 item 3: every surface `emits:` target must resolve to a declared surface."""
    errors: list[str] = []
    known = {s.name for s in appspec.surfaces}
    for s in appspec.surfaces:
        for target in getattr(s, "emits", ()):  # () when undeclared
            if target not in known:
                errors.append(
                    f"E_DEAD_EMIT_TARGET: surface '{s.name}' emits: '{target}', which is not a "
                    f"declared surface. Fix the name or remove it from `emits:`."
                )
    return errors, []
```

- [ ] **Step 4: Wire into validate/lint** — in `lint.py`, after the existing surface/ux validators:
```python
    from dazzle.core.validation.ux import validate_emits_targets

    errors, warnings = validate_emits_targets(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
```

- [ ] **Step 5: Implement the route-override path resolver** — in `route_overrides.py` (mirror `verify_route_matrix_completeness`):
```python
def verify_emits_paths(
    overrides: list[RouteOverrideDescriptor], route_paths: set[str]
) -> list[str]:
    """#1392 item 3: every `# dazzle:emits <path>` must match a mounted route path.
    `route_paths` = generated routes + override paths + page routes (template form, e.g.
    '/app/tasks/{id}')."""
    violations: list[str] = []
    for o in overrides:
        for path in o.emits_paths:
            if path not in route_paths:
                violations.append(
                    f"E_DEAD_EMIT_TARGET: route-override {o.path!r} emits {path!r}, which "
                    f"matches no mounted route."
                )
    return violations
```

- [ ] **Step 6: Test the path resolver** — append to `tests/unit/test_emits_validation.py`:
```python
from dazzle.back.runtime.route_overrides import RouteOverrideDescriptor, verify_emits_paths

def test_override_emits_path_resolves():
    o = RouteOverrideDescriptor(method="GET", path="/app/board", emits_paths=("/app/tasks/{id}",))
    assert verify_emits_paths([o], {"/app/board", "/app/tasks/{id}"}) == []

def test_override_dead_emit_path_violates():
    o = RouteOverrideDescriptor(method="GET", path="/app/board", emits_paths=("/app/gone",))
    v = verify_emits_paths([o], {"/app/board"})
    assert len(v) == 1 and "/app/gone" in v[0]
```
(Construct `RouteOverrideDescriptor` with whatever required fields its dataclass declares — check the definition; fill `handler`/`module`/etc. with placeholder strings if required.)

- [ ] **Step 7: Run to verify all pass**

Run: `.venv/bin/python -m pytest tests/unit/test_emits_validation.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Verify the E2E validate path** — create a temp project with a dead `emits:` target and confirm `dazzle validate` errors (per the "verify the runtime path" rule):
```bash
# build a tiny project dir with the _BASE dead-target DSL, then:
.venv/bin/dazzle validate  # expect: ERROR: E_DEAD_EMIT_TARGET ...
```

- [ ] **Step 9: ruff + commit**
```bash
.venv/bin/ruff format src/dazzle/core/validation/ux.py src/dazzle/core/lint.py src/dazzle/back/runtime/route_overrides.py tests/unit/test_emits_validation.py
.venv/bin/ruff check src/dazzle/core/validation/ux.py src/dazzle/core/lint.py src/dazzle/back/runtime/route_overrides.py tests/unit/test_emits_validation.py --fix
.venv/bin/mypy src/dazzle/core/validation/ux.py src/dazzle/core/lint.py src/dazzle/back/runtime/route_overrides.py
git add -A
git commit -m "feat(validation): emits-target build gate E_DEAD_EMIT_TARGET (#1392 item 3 P3)"
```

---

## Task 4 (P4): dogfood + docs + ship

**Files:**
- Modify: one example/fixture with a custom surface (e.g. a `render:` surface) → add a resolvable `emits:` clause.
- Modify: `docs/reference/` (the custom-renderer / surface reference) + `CHANGELOG.md`.

- [ ] **Step 1: Dogfood** — pick an example with a `render:`/`mode: custom` surface (grep `examples/*/dsl` + `fixtures/custom_renderer`); add `emits: [<a real surface it links to>]`. Run `cd <example> && dazzle validate` → exit 0.

- [ ] **Step 2: Full gate**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy src/dazzle && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/ -m "not e2e" -q -p no:cacheprovider`
Expected: all green.

- [ ] **Step 3: CHANGELOG + docs** — add an Added entry (and an Agent Guidance bullet: "declare `emits:` on custom surfaces / `# dazzle:emits` on route-overrides to get dead-target build failures; ir-types baseline updated"). Add a short reference note where custom renderers are documented.

- [ ] **Step 4: Bump + ship**
```bash
# /bump patch (6 version lines), CHANGELOG roll, uv lock
git add -A && git commit -m "feat: emits-target verification — dogfood + docs (#1392 item 3 P4)"
git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z
```

- [ ] **Step 5: Close-out** — comment on #1392 (item 3 shipped; item 2 chrome-enforcement remains) with the `🔖 Claude-lens: dazzle` trailer. Do NOT close #1392 (item 2 still open).

---

## Self-review
- **Spec coverage:** DSL `emits:` (P1) ✓; `# dazzle:emits` header (P2) ✓; resolver + build error (P3) ✓; dogfood + docs + model-driven note (P4/spec) ✓; opt-in default `()` ✓; not-render-and-crawl ✓; not-#1421 ✓.
- **Placeholders:** none — every step has concrete code/commands. (Task 3 Step 6 notes "check the descriptor's required fields" — that's a real lookup, not a placeholder; the dataclass is at route_overrides.py:55.)
- **Type consistency:** `emits: tuple[str,...]` (IR) ← `tuple(state.emits)` (parser, list→tuple); `emits_paths: tuple[str,...]`; `validate_emits_targets(appspec)->(errors,warnings)`; `verify_emits_paths(overrides, route_paths:set[str])->list[str]`. Consistent across tasks.
