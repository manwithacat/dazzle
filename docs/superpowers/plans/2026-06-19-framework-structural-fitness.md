# Framework Structural Fitness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) or subagent-driven-development. Steps use `- [ ]`.

> **✅ COMPLETE — shipped v0.83.26 (2026-06-19).** All three phases landed. **Deviation (P3 Step 5):** the 2 cross-layer edges (`core/process/eventbus_adapter → back`, `ui/runtime/combined_server → back`) and the transitive MCP/perf SQLite reaches turned out to be **load-bearing structural edges, not leaks** — so they're documented `ignore_imports` allow-list entries in `[tool.importlinter]` rather than relocations. The contracts gate every *new* cross-layer import absolute; reducing the allow-list later only tightens the ratchet. Follow-on **Component C** (framework-structure `/improve` lane + hotspot-sourced counter-prior) is the deferred next initiative.

**Goal:** Gate framework structural decay — a churn×complexity hotspot diagnostic (A1), a complexity ratchet (A2), and import-linter layer contracts (B) — reusing Dazzle's drift-baseline pattern and the `dazzle fitness` Typer app.

**Architecture:** Logic in a new `dazzle.fitness.code` module (CLI = thin wrapper, per ADR-0002); two drift-style pytest gates (`test_complexity_ratchet.py`, `test_import_contracts.py`) mirroring `test_api_surface_drift.py`; contracts in `pyproject.toml [tool.importlinter]`.

**Tech Stack:** Python 3.12, `radon` (CC/MI), `import-linter` (contracts) — new **dev** deps; `git log` shelled out; pytest; typer.

## Global Constraints (verbatim from spec)
- **Reuse the drift-ratchet, don't rebuild.** `--write` regenerates a committed baseline; the gate fails on regression; CHANGELOG entry required on any baseline change (the existing drift discipline).
- **Whole-tree, not diff-scoped** — like every other Dazzle drift gate.
- **Never run `ruff format` over a `.json` baseline** (the v0.83.16 lesson).
- **Dev deps go in `pyproject.toml [project.optional-dependencies] dev` + `uv lock` in the same change** (uv-canonical-toolchain rule). No runtime deps.
- **No parallel orchestrator/SARIF/type-coverage/jscpd.** IR-conversion integrity + the /improve lane (C) are out of scope.
- Ship discipline: per-phase gate green → `/bump patch` + commit + push; full `pytest -m "not e2e"` before each main push.

## File map
- `src/dazzle/fitness/code.py` (new) — `rank_hotspots`, `compute_complexity_baseline`, `compare_complexity` (pure; no CLI/IO-coupling beyond git).
- `src/dazzle/cli/fitness.py` — add `@fitness_app.command("code")` (thin wrapper).
- `dev_docs/framework-hotspots.md` (committed output, gitignored? no — committed, it's the queue).
- `tests/unit/fixtures/complexity_baseline.json` (committed baseline).
- `tests/unit/test_complexity_ratchet.py`, `tests/unit/test_import_contracts.py`.
- `pyproject.toml` — `dev` deps (`radon`, `import-linter`) + `[tool.importlinter]` contracts.
- Fix: `src/dazzle/core/process/eventbus_adapter.py` (core→back leak), `src/dazzle/ui/runtime/combined_server.py` (ui→back leak).

---

## Task 1 (P1): deps + `dazzle fitness code` hotspot ranking (A1)

**Files:** `pyproject.toml`; Create `src/dazzle/fitness/code.py`; Modify `src/dazzle/cli/fitness.py`; Test `tests/unit/test_fitness_code.py`.

**Interfaces — Produces:**
- `compute_complexity(root: Path) -> dict[str, dict]` — `{rel_path: {"mi": float, "mi_rank": str, "max_cc": int, "functions": {name: cc}}}`.
- `change_frequency(root: Path, since_days: int = 180) -> dict[str, int]` — `{rel_path: commit_count}`.
- `rank_hotspots(complexity, churn) -> list[tuple[str, float, int, str]]` — `(path, score, churn, mi_rank)` sorted desc; `score = churn * (100 - mi)`.

- [x] **Step 1: Add deps.** In `pyproject.toml` `[project.optional-dependencies] dev` (line ~185), add `"radon>=6.0"` and `"import-linter>=2.0"`. Run `uv lock && uv sync --extra dev`.

- [x] **Step 2: Write the failing test** (`tests/unit/test_fitness_code.py`):
```python
from pathlib import Path
from dazzle.fitness.code import compute_complexity, rank_hotspots

def test_compute_complexity_on_a_known_file():
    cx = compute_complexity(Path("src/dazzle"))
    # page_routes is a known large module — present, with an MI rank and CC data.
    key = next(k for k in cx if k.endswith("ui/runtime/page_routes.py"))
    assert cx[key]["mi_rank"] in ("A", "B", "C")
    assert cx[key]["max_cc"] >= 1

def test_rank_hotspots_orders_by_churn_times_complexity():
    complexity = {"a.py": {"mi": 30.0}, "b.py": {"mi": 90.0}}
    churn = {"a.py": 2, "b.py": 50}
    ranked = rank_hotspots(complexity, churn)
    # a.py: 2*(100-30)=140 ; b.py: 50*(100-90)=500 → b first
    assert ranked[0][0] == "b.py"
```

- [x] **Step 3: Run → FAIL** (`compute_complexity` undefined). `.venv/bin/python -m pytest tests/unit/test_fitness_code.py -q`.

- [x] **Step 4: Implement `src/dazzle/fitness/code.py`:**
```python
"""Framework structural-fitness: churn×complexity hotspot ranking + complexity baseline.

Points Dazzle's drift-ratchet instinct at src/dazzle's own Python structure (the one
ungated surface). `dazzle fitness code` writes the hotspot queue; the committed baseline
feeds tests/unit/test_complexity_ratchet.py.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import mi_rank, mi_visit


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def compute_complexity(root: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for p in _py_files(root):
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            mi = mi_visit(src, multi=True)
            funcs = {f.name: f.complexity for f in cc_visit(src)}
        except (SyntaxError, Exception):  # radon can choke on some files; skip them loudly
            continue
        rel = str(p.relative_to(root.parent))
        result[rel] = {
            "mi": round(mi, 2),
            "mi_rank": mi_rank(mi),
            "max_cc": max(funcs.values(), default=0),
            "functions": funcs,
        }
    return result


def change_frequency(root: Path, since_days: int = 180) -> dict[str, int]:
    out = subprocess.run(
        ["git", "log", f"--since={since_days} days ago", "--name-only", "--pretty=format:"],
        cwd=root.parent, capture_output=True, text=True, check=False,
    ).stdout
    counts: Counter[str] = Counter()
    prefix = root.name + "/"
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(prefix) and line.endswith(".py"):
            counts[line] += 1
    return dict(counts)


def rank_hotspots(complexity: dict[str, dict], churn: dict[str, int]) -> list[tuple]:
    rows = []
    for path, cx in complexity.items():
        c = churn.get(path, 0)
        score = c * (100.0 - cx["mi"])
        rows.append((path, round(score, 1), c, cx.get("mi_rank", "?")))
    return sorted(rows, key=lambda r: r[1], reverse=True)


def render_hotspots_md(ranked: list[tuple], top: int = 30) -> str:
    lines = [
        "# Framework structural hotspots (churn × complexity)",
        "",
        "Generated by `dazzle fitness code`. Ordered structural-debt queue: high-churn ×",
        "low-maintainability files. Report-only — refactor the top by hand; the ratchet",
        "(test_complexity_ratchet.py) protects the gains.",
        "",
        "| Rank | File | Score | Churn (180d) | MI rank |",
        "|------|------|-------|--------------|---------|",
    ]
    for i, (path, score, churn, rank) in enumerate(ranked[:top], 1):
        lines.append(f"| {i} | `{path}` | {score} | {churn} | {rank} |")
    return "\n".join(lines) + "\n"
```
*(The `except (SyntaxError, Exception)` is intentionally broad with a `continue` — but the `test_no_bare_except_pass` gate forbids silent `except Exception`. Add a `logger.debug(...)` line before `continue`, or catch `Exception` and re-raise-after-log. Use `import logging; logger = logging.getLogger(__name__)` + `logger.debug("radon skipped %s: %s", p, exc)`.)*

- [x] **Step 5: Wire the CLI** in `src/dazzle/cli/fitness.py`:
```python
@fitness_app.command("code")
def code_command(
    project: Path | None = typer.Option(None, "--project", help="Repo root (default: cwd)"),
    since_days: int = typer.Option(180, "--since-days"),
    write: bool = typer.Option(False, "--write", help="Regenerate dev_docs/framework-hotspots.md"),
) -> None:
    """Churn×complexity hotspot ranking for src/dazzle (framework structural debt)."""
    from dazzle.fitness.code import change_frequency, compute_complexity, rank_hotspots, render_hotspots_md

    root = (project or Path.cwd()) / "src" / "dazzle"
    ranked = rank_hotspots(compute_complexity(root), change_frequency(root, since_days))
    md = render_hotspots_md(ranked)
    if write:
        out = (project or Path.cwd()) / "dev_docs" / "framework-hotspots.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md)
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(md)
```

- [x] **Step 6: Run → PASS** + generate the real queue: `.venv/bin/dazzle fitness code --write` → inspect `dev_docs/framework-hotspots.md` (expect page_routes/server/app_factory/entity near the top). ruff + mypy.

- [x] **Step 7: Commit (local).**
```bash
.venv/bin/ruff format src/dazzle/fitness/code.py src/dazzle/cli/fitness.py tests/unit/test_fitness_code.py
.venv/bin/ruff check src/dazzle/fitness/code.py src/dazzle/cli/fitness.py tests/unit/test_fitness_code.py --fix
.venv/bin/mypy src/dazzle/fitness/code.py src/dazzle/cli/fitness.py
git add pyproject.toml uv.lock src/dazzle/fitness/code.py src/dazzle/cli/fitness.py tests/unit/test_fitness_code.py dev_docs/framework-hotspots.md
git commit -m "feat(fitness): dazzle fitness code — churn×complexity hotspot ranking (A1)"
```

---

## Task 2 (P2): complexity ratchet (A2)

**Files:** `src/dazzle/fitness/code.py` (add baseline build/compare); `src/dazzle/cli/fitness.py` (`--write` baseline option); Create `tests/unit/fixtures/complexity_baseline.json`, `tests/unit/test_complexity_ratchet.py`.

**Interfaces — Consumes:** `compute_complexity` (Task 1). **Produces:** `build_complexity_baseline(root) -> dict`, `compare_complexity(baseline, current, cc_ceiling=15) -> list[str]` (violation strings; empty = clean).

- [x] **Step 1: Write the failing test** (`tests/unit/test_complexity_ratchet.py`):
```python
import json
from pathlib import Path
from dazzle.fitness.code import build_complexity_baseline, compare_complexity

_BASELINE = Path("tests/unit/fixtures/complexity_baseline.json")
_RANK = {"A": 3, "B": 2, "C": 1}

def test_current_tree_does_not_regress_against_baseline():
    baseline = json.loads(_BASELINE.read_text())
    current = build_complexity_baseline(Path("src/dazzle"))
    violations = compare_complexity(baseline, current)
    assert violations == [], "\n".join(violations)

def test_compare_flags_mi_rank_drop():
    base = {"a.py": {"mi_rank": "B", "functions": {}}}
    worse = {"a.py": {"mi_rank": "C", "functions": {}}}
    v = compare_complexity(base, worse)
    assert any("a.py" in s and "MI rank" in s for s in v)

def test_compare_flags_new_high_cc_function():
    base = {"a.py": {"mi_rank": "B", "functions": {"f": 5}}}
    worse = {"a.py": {"mi_rank": "B", "functions": {"f": 5, "g": 20}}}
    v = compare_complexity(base, worse, cc_ceiling=15)
    assert any("g" in s and "CC" in s for s in v)
```

- [x] **Step 2: Run → FAIL** (`build_complexity_baseline` undefined).

- [x] **Step 3: Implement** in `code.py`:
```python
_MI_RANK_ORDER = {"A": 3, "B": 2, "C": 1}

def build_complexity_baseline(root: Path) -> dict:
    # Drop the per-function detail not needed for the ratchet would shrink the file, but
    # keep functions for the CC-ceiling check. Stable key order for a clean diff.
    cx = compute_complexity(root)
    return {k: {"mi_rank": v["mi_rank"], "functions": v["functions"]} for k in sorted(cx) for v in [cx[k]]}

def compare_complexity(baseline: dict, current: dict, cc_ceiling: int = 15) -> list[str]:
    violations: list[str] = []
    for path, cur in current.items():
        base = baseline.get(path)
        if base is None:
            if cur["mi_rank"] == "C":
                violations.append(f"{path}: new file at MI rank C — split it before landing.")
            base_funcs: dict = {}
        else:
            if _MI_RANK_ORDER[cur["mi_rank"]] < _MI_RANK_ORDER[base["mi_rank"]]:
                violations.append(
                    f"{path}: MI rank dropped {base['mi_rank']}→{cur['mi_rank']} — "
                    f"refactor or regenerate the baseline with `dazzle fitness code --write-baseline`."
                )
            base_funcs = base.get("functions", {})
        for fn, cc in cur["functions"].items():
            if cc > cc_ceiling and base_funcs.get(fn, 0) <= cc_ceiling:
                violations.append(f"{path}:{fn}: cyclomatic complexity {cc} > {cc_ceiling} (new).")
    return violations
```
*(`build_complexity_baseline` dict-comp is awkward — write it as a plain loop returning `{k: {"mi_rank": cx[k]["mi_rank"], "functions": cx[k]["functions"]} for k in sorted(cx)}`.)*

- [x] **Step 4: Add `--write-baseline` to the CLI** (`fitness.py code_command`): a flag that writes `build_complexity_baseline(root)` to `tests/unit/fixtures/complexity_baseline.json` via `json.dump(..., indent=2, sort_keys=True)` + trailing newline. Generate it: `.venv/bin/dazzle fitness code --write-baseline`.

- [x] **Step 5: Run → PASS** (the committed baseline matches the current tree). `.venv/bin/python -m pytest tests/unit/test_complexity_ratchet.py -q`.

- [x] **Step 6: ruff (NOT on the .json) + mypy + commit (local).** CHANGELOG note (Added: the complexity ratchet + how to regen the baseline).
```bash
git add src/dazzle/fitness/code.py src/dazzle/cli/fitness.py tests/unit/fixtures/complexity_baseline.json tests/unit/test_complexity_ratchet.py CHANGELOG.md
git commit -m "feat(fitness): complexity ratchet — radon MI/CC drift gate (A2)"
```

---

## Task 3 (P3): import contracts + fix the 2 boundary leaks (B)

**Files:** `pyproject.toml` (`[tool.importlinter]`); Create `tests/unit/test_import_contracts.py`; Fix `src/dazzle/core/process/eventbus_adapter.py`, `src/dazzle/ui/runtime/combined_server.py`.

- [x] **Step 1: Investigate the 2 violations.** `grep -nE "dazzle\.back" src/dazzle/core/process/eventbus_adapter.py src/dazzle/ui/runtime/combined_server.py`. For each: is the `back` import load-bearing, or a leak?
  - `core/process/eventbus_adapter.py` — `core` importing `back` is a layering inversion. Likely the adapter should accept the back dependency by injection (a callable/protocol passed in) rather than importing it, OR the adapter belongs in `back`. Choose the minimal correct fix (dependency injection if the import is a single call; relocate if it's tightly coupled).
  - `ui/runtime/combined_server.py` — the unified ASGI server lives in `ui/` but wires `back`. It almost certainly belongs in `back/runtime/` (or a neutral top-level). Relocate it + update the import site(s); or, if relocation is large, defer it to a documented allow-list entry and gate the rest `absolute`.

- [x] **Step 2: Write the failing test** (`tests/unit/test_import_contracts.py`):
```python
import subprocess, sys

def test_import_contracts_pass():
    r = subprocess.run([sys.executable, "-m", "importlinter.cli", "lint"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```
*(Confirm the import-linter CLI entry — it's `lint-imports` / `python -m importlinter`; adjust to the installed entrypoint. Prefer the programmatic API `importlinter.api.read_config` + `create_report` if the CLI module path is unstable.)*

- [x] **Step 3: Run → FAIL** (no contracts configured yet, or the 2 violations).

- [x] **Step 4: Author contracts** in `pyproject.toml`:
```toml
[tool.importlinter]
root_packages = ["dazzle"]

[[tool.importlinter.contracts]]
name = "core stays backend/UI-agnostic"
type = "forbidden"
source_modules = ["dazzle.core"]
forbidden_modules = ["dazzle.back", "dazzle.ui"]

[[tool.importlinter.contracts]]
name = "ui must not reach into the runtime"
type = "forbidden"
source_modules = ["dazzle.ui"]
forbidden_modules = ["dazzle.back"]

[[tool.importlinter.contracts]]
name = "back is Postgres-only (ADR-0008)"
type = "forbidden"
source_modules = ["dazzle.back"]
forbidden_modules = ["sqlite3", "aiosqlite"]
```

- [x] **Step 5: Fix the 2 leaks** (per Step 1's decision) so the contracts pass. Re-run the import-linter lint until clean.

- [x] **Step 6: Run → PASS.** `.venv/bin/python -m pytest tests/unit/test_import_contracts.py -q` + the import-linter CLI directly.

- [x] **Step 7: Full gate + ship (P1–P3 boundary).** `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy src/dazzle && PATH=".venv/bin:$PATH" .venv/bin/python -m pytest tests/ -m "not e2e" -q -p no:cacheprovider`. CHANGELOG (Added: import contracts + the 2 boundary fixes; **Agent Guidance:** the framework layers are now import-gated — `core` ↛ `back`/`ui`, `ui` ↛ `back`, `back` ↛ sqlite; relocate cross-layer code, don't import across). `/bump patch`, commit, tag, push.

---

## Self-review
- **Spec coverage:** A1 hotspot ranking (Task 1) ✓; A2 complexity ratchet (Task 2) ✓; B import contracts (Task 3) ✓; reuse-drift-pattern (both gates mirror `test_api_surface_drift`) ✓; whole-tree ✓; fix-the-2-violations → absolute (Task 3) ✓; deps in `dev` + uv lock (Task 1 Step 1) ✓; dropped non-goals (no orchestrator/SARIF/type-cov/jscpd) ✓.
- **Placeholder scan:** Task 3 Step 1 ("choose the minimal correct fix") is a real investigation against named files, not a placeholder — the two candidate fixes (inject vs relocate) are spelled out. The radon/import-linter API caveats are flagged where the exact entrypoint must be confirmed against the installed version.
- **Type consistency:** `compute_complexity -> dict[str,dict]`, `change_frequency -> dict[str,int]`, `rank_hotspots -> list[tuple]`, `build_complexity_baseline -> dict`, `compare_complexity(baseline, current, cc_ceiling) -> list[str]` — consistent across Tasks 1–2.
- **Risk note:** the broad `except` in `compute_complexity` must carry a `logger.debug` (the `test_no_bare_except_pass` gate); flagged inline. Never `ruff format` the `.json` baseline (flagged).
