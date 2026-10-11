# Fragment Coverage Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dazzle fragment-audit` — a deterministic coverage tool that walks any AppSpec and reports, per surface, whether the typed Fragment substrate can render it now and (if not) which feature blocks it. Each subsequent plan becomes "close blocker X" guided by the audit's aggregated counts. Replaces ad-hoc per-surface conversion with a measurable, prioritisable migration strategy.

**Architecture:** A new `dazzle.render.fragment.coverage` module owns the analysis. `audit_appspec(appspec) -> CoverageReport` walks every surface, inspects its IR features (mode, fields, related_groups, companions, transitions, etc.), cross-references against the adapter's known capability matrix, and produces a structured report. Per-surface results carry a status (`ready` | `blocked`) plus a list of typed `Blocker` records; the report aggregates blockers across the appspec. A new `dazzle fragment-audit` CLI wraps the analysis with text + JSON output, mirroring the existing `dazzle coverage` command's shape (which audits framework-artefact coverage; this audits Fragment-rendering coverage).

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plans 1-5, Typer for the CLI (follows the existing CLI pattern at `src/dazzle/cli/coverage.py`).

**Reference:** the user's pivot from per-surface conversion to deterministic strategy. The audit becomes the primary tool driving subsequent plans — each plan closes a blocker the audit identified.

**Out of scope:** auto-flipping surfaces ("when ready, set render: fragment"), closing any blocker the audit identifies (those are subsequent plans), MCP-tool surface for the audit (CLI only for now; MCP can wrap later).

---

## Stop condition

> **`dazzle fragment-audit examples/simple_task` produces a structured report** showing per-surface status (✓ ready / ✗ blocked) plus aggregated blocker counts. The report is consumable both by humans (text format) and by tooling (`--json` flag). Exit code 0 if every surface is `ready`; non-zero if any are blocked (so `--fail-on-blocked` can run as a CI gate or be used by `/improve`-style loops to drive blocker-closure prioritisation).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle/render/fragment/coverage.py` | Create | `audit_appspec(appspec) -> CoverageReport`; typed `Blocker` records; `CoverageReport` with `to_text()` / `to_json()` |
| `src/dazzle/cli/fragment_audit.py` | Create | Typer command `dazzle fragment-audit`; loads appspec, calls `audit_appspec`, prints report |
| `src/dazzle/cli/__init__.py` | Modify | Register the new command on the main `app` Typer |
| `tests/unit/render/fragment/test_coverage.py` | Create | Unit tests for `audit_appspec` against synthetic AppSpec fixtures |
| `tests/integration/test_fragment_audit_cli.py` | Create | End-to-end test invoking the CLI on `examples/simple_task` and asserting the structured report shape |
| `CHANGELOG.md` | Modify | Note the new audit command |

6 files. ~6 tasks.

---

## Conventions

- **TDD throughout.** Failing test → minimal implementation → commit.
- **Lint after each task:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- **Type check:** `mypy src/dazzle/render --strict` and `mypy src/dazzle --ignore-missing-imports` clean.
- **Commit messages:** `feat(render): <subject>` for analysis module; `feat(cli): <subject>` for the command; `test(render): <subject>` for tests.

---

## Task 1: Define the coverage types

**Files:**
- Create: `src/dazzle/render/fragment/coverage.py` (initial skeleton)
- Create: `tests/unit/render/fragment/test_coverage.py`

Start with the type vocabulary. The audit needs `Blocker` (an enum + an optional detail), `SurfaceCoverage` (per-surface result), and `CoverageReport` (the whole-appspec roll-up).

- [ ] **Step 1: Write failing tests for the types**

```python
# tests/unit/render/fragment/test_coverage.py
"""Unit tests for the Fragment coverage audit."""

import pytest

from dazzle.render.fragment.coverage import (
    Blocker,
    BlockerKind,
    CoverageReport,
    SurfaceCoverage,
)


def test_blocker_kind_enum_values() -> None:
    """Each blocker kind names a structural reason an adapter can't render
    a surface. Adding a new failure mode means adding to the enum."""
    expected = {
        "unsupported_mode",
        "unsupported_field_type",
        "unsupported_feature",
    }
    assert {k.value for k in BlockerKind} == expected


def test_blocker_dataclass() -> None:
    b = Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW")
    assert b.kind == BlockerKind.UNSUPPORTED_MODE
    assert b.detail == "VIEW"


def test_surface_coverage_ready_when_no_blockers() -> None:
    sc = SurfaceCoverage(name="task_list", mode="LIST", blockers=())
    assert sc.is_ready


def test_surface_coverage_blocked_when_blockers_present() -> None:
    sc = SurfaceCoverage(
        name="task_detail",
        mode="VIEW",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
    )
    assert not sc.is_ready


def test_coverage_report_aggregates() -> None:
    a = SurfaceCoverage(name="task_list", mode="LIST", blockers=())
    b = SurfaceCoverage(
        name="task_detail",
        mode="VIEW",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
    )
    c = SurfaceCoverage(
        name="task_create",
        mode="CREATE",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="CREATE"),),
    )
    report = CoverageReport(surfaces=(a, b, c))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    # Aggregated: 1 surface blocked on mode=VIEW, 1 on mode=CREATE
    assert report.aggregated_blockers == {
        ("unsupported_mode", "VIEW"): 1,
        ("unsupported_mode", "CREATE"): 1,
    }
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the coverage types**

```python
# src/dazzle/render/fragment/coverage.py
"""Fragment-rendering coverage audit.

Walks any AppSpec and reports, per surface, whether the typed Fragment
substrate can render it given the adapter's current capabilities.

The audit is structural — it inspects each surface's IR features (mode,
field types, related_groups, companions, transitions) and cross-references
against the adapter's capability matrix. It does NOT actually invoke the
renderer or build a Fragment tree (no test data is required).

Subsequent plans close blockers by extending the adapter; the audit's
aggregated counts drive prioritisation: closing whichever blocker affects
the most surfaces first.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum


class BlockerKind(str, Enum):
    """Why a surface cannot currently be rendered via Fragment."""

    UNSUPPORTED_MODE = "unsupported_mode"
    UNSUPPORTED_FIELD_TYPE = "unsupported_field_type"
    UNSUPPORTED_FEATURE = "unsupported_feature"


@dataclass(frozen=True, slots=True)
class Blocker:
    """A single reason a surface is not Fragment-renderable today.

    `kind` names the structural class of obstruction; `detail` carries
    the specific instance (e.g. mode name, field type name, feature name).
    """

    kind: BlockerKind
    detail: str


@dataclass(frozen=True, slots=True)
class SurfaceCoverage:
    """Per-surface audit result."""

    name: str
    mode: str  # SurfaceMode.value as a string
    blockers: tuple[Blocker, ...]

    @property
    def is_ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Whole-AppSpec audit result."""

    surfaces: tuple[SurfaceCoverage, ...]

    @property
    def ready_count(self) -> int:
        return sum(1 for s in self.surfaces if s.is_ready)

    @property
    def blocked_count(self) -> int:
        return sum(1 for s in self.surfaces if not s.is_ready)

    @property
    def aggregated_blockers(self) -> dict[tuple[str, str], int]:
        """Map (kind, detail) → count of surfaces affected. Sorted by
        descending count when materialised; the dict itself is unordered."""
        counter: Counter[tuple[str, str]] = Counter()
        for s in self.surfaces:
            for b in s.blockers:
                counter[(b.kind.value, b.detail)] += 1
        return dict(counter)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): coverage audit types — Blocker, SurfaceCoverage, CoverageReport"
```

---

## Task 2: Implement audit_appspec

The walker. Reads each surface's IR features and cross-references against the adapter's capability matrix.

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/render/fragment/test_coverage.py`:

```python
from dazzle.core.ir import (
    AppSpec,
    BusinessPriority,
    SurfaceMode,
    SurfaceSpec,
)
from dazzle.render.fragment.coverage import audit_appspec


def _make_appspec(surfaces: list[SurfaceSpec]) -> AppSpec:
    """Build a minimal AppSpec — the audit only consults surfaces."""
    return AppSpec(
        name="test",
        title="Test App",
        entities=[],
        surfaces=surfaces,
        workspaces=[],
        personas=[],
    )


def test_audit_marks_simple_list_as_ready() -> None:
    """A LIST-mode surface with no related_groups, no companions, no
    transitions is renderable today."""
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 1
    assert report.blocked_count == 0
    assert report.surfaces[0].is_ready


def test_audit_marks_view_mode_as_blocked() -> None:
    """VIEW mode is not yet supported by the adapter (Plan 6 not landed)."""
    surface = SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 0
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(
        b.kind.value == "unsupported_mode" and b.detail == "VIEW"
        for b in blockers
    )


def test_audit_marks_related_groups_as_blocked() -> None:
    """A LIST surface with related_groups uses an unsupported feature."""
    from dazzle.core.ir.surfaces import RelatedDisplayMode, RelatedGroup

    surface = SurfaceSpec(
        name="x",
        mode=SurfaceMode.LIST,
        related_groups=[
            RelatedGroup(name="comments", entity_ref="Comment", display=RelatedDisplayMode.TABLE),
        ],
    )
    report = audit_appspec(_make_appspec([surface]))
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(
        b.kind.value == "unsupported_feature" and b.detail == "related_groups"
        for b in blockers
    )


def test_audit_aggregates_across_surfaces() -> None:
    """Three surfaces, two blocked on VIEW mode — count is 2."""
    surfaces = [
        SurfaceSpec(name="a", mode=SurfaceMode.VIEW),
        SurfaceSpec(name="b", mode=SurfaceMode.VIEW),
        SurfaceSpec(name="c", mode=SurfaceMode.LIST),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    assert report.aggregated_blockers[("unsupported_mode", "VIEW")] == 2
```

(Field types — `RelatedGroup`, `RelatedDisplayMode` — adjust imports to match the actual IR module structure. Use `grep -n "class RelatedGroup\|class RelatedDisplayMode" src/dazzle/core/ir/surfaces.py` to confirm.)

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: 4 new tests FAIL with `ImportError: cannot import name 'audit_appspec'`.

- [ ] **Step 3: Implement audit_appspec**

Append to `src/dazzle/render/fragment/coverage.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, SurfaceSpec


# Capability matrix — what the FragmentSurfaceAdapter currently supports.
# Updated when the adapter gains new mode/feature/field-type support.
_SUPPORTED_MODES: frozenset[str] = frozenset({"list"})

# Surface-level features that block Fragment rendering when present.
# Each entry is the SurfaceSpec attribute name; if the attribute is
# truthy/non-empty, the surface is blocked on that feature.
_UNSUPPORTED_FEATURES: tuple[str, ...] = (
    "related_groups",
    "companions",
    "search_fields",  # search bar; Plan 1 primitives don't include it
    "actions",         # action buttons beyond the primary
)

# Field types the adapter can't render. Plan 3's _format_cell str-coerces
# everything, so for now no field type is structurally blocked — but this
# constant is the seam for future restrictions (e.g. ref-cell rendering
# requires FK-aware adapter support).
_UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset()


def _audit_surface(surface: "SurfaceSpec") -> SurfaceCoverage:
    """Inspect one surface against the capability matrix; produce a
    SurfaceCoverage entry."""
    blockers: list[Blocker] = []

    mode_value = surface.mode.value if hasattr(surface.mode, "value") else str(surface.mode)
    if mode_value not in _SUPPORTED_MODES:
        blockers.append(
            Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail=mode_value.upper())
        )

    for feature_attr in _UNSUPPORTED_FEATURES:
        value = getattr(surface, feature_attr, None)
        if value:  # non-empty list / non-None object
            blockers.append(
                Blocker(kind=BlockerKind.UNSUPPORTED_FEATURE, detail=feature_attr)
            )

    # Field types — walk sections.fields if present
    for section in getattr(surface, "sections", []) or []:
        for field_spec in getattr(section, "fields", []) or []:
            ft = getattr(field_spec, "type", None) or getattr(field_spec, "field_type", None)
            if ft and str(ft).lower() in _UNSUPPORTED_FIELD_TYPES:
                blockers.append(
                    Blocker(
                        kind=BlockerKind.UNSUPPORTED_FIELD_TYPE,
                        detail=str(ft).lower(),
                    )
                )

    return SurfaceCoverage(
        name=surface.name,
        mode=mode_value.upper(),
        blockers=tuple(blockers),
    )


def audit_appspec(appspec: "AppSpec") -> CoverageReport:
    """Walk every surface in `appspec` and report Fragment-rendering coverage.

    Returns a CoverageReport whose `aggregated_blockers` drives the
    prioritisation of subsequent migration plans: close whichever blocker
    affects the most surfaces first.
    """
    surfaces = tuple(_audit_surface(s) for s in appspec.surfaces)
    return CoverageReport(surfaces=surfaces)
```

(The TYPE_CHECKING import keeps coverage.py from forcing an AppSpec import at module load — only the function body needs the types. Pyright/mypy still see them.)

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: 9 PASS (5 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): audit_appspec — walk surfaces, classify blockers"
```

---

## Task 3: Text rendering for CoverageReport

The audit returns structured data; the consumer needs human-readable output.

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_coverage_report_to_text_basic_shape() -> None:
    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    text = report.to_text()
    # Header
    assert "Coverage:" in text
    assert "1 / 2" in text  # 1 ready of 2 total
    # Per-surface lines
    assert "task_list" in text
    assert "task_detail" in text
    # Status indicators
    assert "✓" in text or "ready" in text
    assert "✗" in text or "blocked" in text
    # Aggregated blockers section
    assert "unsupported_mode" in text or "VIEW" in text
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/render/fragment/test_coverage.py::test_coverage_report_to_text_basic_shape -v
```

Expected: FAIL — no `to_text` method.

- [ ] **Step 3: Implement `to_text`**

Add to `CoverageReport` class in `coverage.py`:

```python
    def to_text(self) -> str:
        """Render a human-readable report.

        Format roughly mirrors `dazzle coverage`: header line, ready
        section, blocked section, aggregated-blockers section."""
        lines: list[str] = []
        total = len(self.surfaces)
        lines.append(f"Coverage: {self.ready_count} / {total} surfaces ready to flip")
        lines.append("")

        ready = [s for s in self.surfaces if s.is_ready]
        blocked = [s for s in self.surfaces if not s.is_ready]

        if ready:
            lines.append(f"Ready ({len(ready)}):")
            for s in ready:
                lines.append(f"  ✓ {s.name:30s} mode={s.mode.lower()}")
            lines.append("")

        if blocked:
            lines.append(f"Blocked ({len(blocked)}):")
            for s in blocked:
                blocker_summary = "; ".join(
                    f"{b.kind.value}={b.detail}" for b in s.blockers
                )
                lines.append(f"  ✗ {s.name:30s} mode={s.mode.lower()}: {blocker_summary}")
            lines.append("")

        if blocked:
            lines.append("Aggregated blockers (close highest-count first):")
            agg = self.aggregated_blockers
            for (kind, detail), count in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"  {count:>3d}  {kind}={detail}")
            lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): CoverageReport.to_text — human-readable audit output"
```

---

## Task 4: JSON rendering for CoverageReport

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`

- [ ] **Step 1: Write failing test**

Append:

```python
import json


def test_coverage_report_to_json_shape() -> None:
    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    payload = json.loads(report.to_json())
    # Top-level shape
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["total"] == 2
    # Per-surface entries
    assert len(payload["surfaces"]) == 2
    by_name = {s["name"]: s for s in payload["surfaces"]}
    assert by_name["task_list"]["is_ready"] is True
    assert by_name["task_list"]["mode"] == "LIST"
    assert by_name["task_list"]["blockers"] == []
    assert by_name["task_detail"]["is_ready"] is False
    assert by_name["task_detail"]["mode"] == "VIEW"
    assert {"kind": "unsupported_mode", "detail": "VIEW"} in by_name["task_detail"]["blockers"]
    # Aggregated blockers — list of {kind, detail, count}, sorted by count desc
    assert payload["aggregated_blockers"][0] == {
        "kind": "unsupported_mode",
        "detail": "VIEW",
        "count": 1,
    }
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/render/fragment/test_coverage.py::test_coverage_report_to_json_shape -v
```

Expected: FAIL — no `to_json` method.

- [ ] **Step 3: Implement `to_json`**

Add to `CoverageReport`:

```python
    def to_json(self, *, indent: int | None = 2) -> str:
        """Render the report as JSON. Stable shape for piping into
        tooling (`/improve`, CI gates, etc.)."""
        import json

        agg = self.aggregated_blockers
        agg_list = [
            {"kind": kind, "detail": detail, "count": count}
            for (kind, detail), count in sorted(
                agg.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ]
        payload = {
            "total": len(self.surfaces),
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
            "surfaces": [
                {
                    "name": s.name,
                    "mode": s.mode,
                    "is_ready": s.is_ready,
                    "blockers": [
                        {"kind": b.kind.value, "detail": b.detail}
                        for b in s.blockers
                    ],
                }
                for s in self.surfaces
            ],
            "aggregated_blockers": agg_list,
        }
        return json.dumps(payload, indent=indent)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v
```

Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): CoverageReport.to_json — machine-readable audit output"
```

---

## Task 5: CLI command — `dazzle fragment-audit`

**Files:**
- Create: `src/dazzle/cli/fragment_audit.py`
- Modify: `src/dazzle/cli/__init__.py`
- Create: `tests/integration/test_fragment_audit_cli.py`

- [ ] **Step 1: Inspect the existing `dazzle coverage` CLI for the pattern**

```bash
sed -n '1,80p' src/dazzle/cli/coverage.py
```

The existing command takes a project path, loads the AppSpec, runs the audit, prints text or JSON, exits with a code. Mirror this pattern.

- [ ] **Step 2: Write failing integration test**

```python
# tests/integration/test_fragment_audit_cli.py
"""End-to-end test for `dazzle fragment-audit`."""

import json
import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SIMPLE_TASK = _REPO_ROOT / "examples" / "simple_task"


def test_fragment_audit_text_on_simple_task() -> None:
    """The CLI emits a human-readable report for examples/simple_task."""
    result = subprocess.run(
        ["python", "-m", "dazzle.cli", "fragment-audit", str(_SIMPLE_TASK)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    # Exit code: 0 iff every surface is ready. simple_task has detail
    # surfaces, so currently non-zero.
    assert result.returncode != 0
    out = result.stdout
    assert "Coverage:" in out
    assert "task_list" in out
    assert "task_detail" in out
    assert "ready" in out.lower() or "✓" in out
    assert "blocked" in out.lower() or "✗" in out


def test_fragment_audit_json_on_simple_task() -> None:
    """The --json flag emits structured JSON."""
    result = subprocess.run(
        ["python", "-m", "dazzle.cli", "fragment-audit", str(_SIMPLE_TASK), "--json"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    payload = json.loads(result.stdout)
    assert "ready_count" in payload
    assert "blocked_count" in payload
    assert "surfaces" in payload
    assert any(s["name"] == "task_list" for s in payload["surfaces"])
```

(Adjust the `python -m dazzle.cli` invocation to match how the project's CLI entrypoint is wired — search `pyproject.toml` for `[project.scripts]` or the `__main__.py` file.)

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/integration/test_fragment_audit_cli.py -v
```

Expected: FAIL — no `fragment-audit` command registered.

- [ ] **Step 4: Implement the CLI command**

Create `src/dazzle/cli/fragment_audit.py`:

```python
"""`dazzle fragment-audit` — Fragment-rendering coverage audit.

Walks any AppSpec and reports per-surface whether the typed Fragment
substrate can render it. Aggregates blockers across the appspec so the
user can see which closure unlocks the most surfaces.

Mirrors the shape of `dazzle coverage` (framework-artefact coverage).

Usage
-----
    dazzle fragment-audit <project-path>     # human-readable
    dazzle fragment-audit <project-path> --json     # JSON
    dazzle fragment-audit <project-path> --fail-on-blocked     # CI gate
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from dazzle.core.dsl_parser_impl import parse_modules
from dazzle.core.linker import build_appspec
from dazzle.render.fragment.coverage import audit_appspec
from dazzle_http.runtime.renderers.init import default_renderer_names

app = typer.Typer(help="Audit Fragment-rendering coverage across an AppSpec.")


@app.command(name="fragment-audit")
def fragment_audit(
    project_path: Path = typer.Argument(
        ..., help="Path to a Dazzle project (directory containing dsl/ subdirectory).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
    fail_on_blocked: bool = typer.Option(
        False,
        "--fail-on-blocked",
        help="Exit 1 if any surface is blocked (CI-gate mode).",
    ),
) -> None:
    """Audit Fragment-rendering coverage for the given project."""
    if not project_path.exists():
        typer.echo(f"Project path does not exist: {project_path}", err=True)
        raise typer.Exit(code=2)

    modules = parse_modules([project_path.resolve()])
    appspec = build_appspec(
        modules,
        root_module_name=_root_module_name(modules),
        known_renderers=default_renderer_names(),
    )
    report = audit_appspec(appspec)

    if json_output:
        typer.echo(report.to_json())
    else:
        typer.echo(report.to_text())

    # Exit code: 0 if every surface ready, non-zero if any blocked.
    # --fail-on-blocked makes this explicit for CI; without it the exit
    # code mirrors the same logic by default (matches `dazzle coverage`).
    if fail_on_blocked or report.blocked_count > 0:
        raise typer.Exit(code=1 if report.blocked_count > 0 else 0)


def _root_module_name(modules: list) -> str:
    """Pick the module containing an `app` declaration.

    Mirrors the resolution `dazzle validate` performs when called with
    a project path (rather than an explicit root module).
    """
    for mod in modules:
        if getattr(mod, "app_name", None) or getattr(mod, "app", None):
            return mod.name
    return modules[0].name if modules else ""
```

(Adjust imports: `parse_modules`, `build_appspec`, `default_renderer_names` are confirmed-existing per Plans 1-5. The `_root_module_name` heuristic mirrors what other CLI commands do; if a clean shared helper exists, use that instead — search `grep -rn "_root_module\|root_module_name=" src/dazzle/cli/`.)

In `src/dazzle/cli/__init__.py`, register the command. Find where other commands are added to the main `app`:

```bash
grep -n "app.add_typer\|app.command" src/dazzle/cli/__init__.py | head -20
```

Add a similar import + registration line. Likely something like:

```python
from dazzle.cli.fragment_audit import fragment_audit  # noqa: E402

app.command(name="fragment-audit")(fragment_audit)
```

— or use `app.add_typer` if the existing pattern uses sub-Typers.

- [ ] **Step 5: Verify the integration test passes**

```bash
pytest tests/integration/test_fragment_audit_cli.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Manually verify the CLI works**

```bash
python -m dazzle.cli fragment-audit examples/simple_task
echo "exit=$?"
python -m dazzle.cli fragment-audit examples/simple_task --json | head -20
```

Expected: text output with surfaces listed; non-zero exit; JSON with structured output.

- [ ] **Step 7: Lint, types, suite**

```bash
ruff check src/dazzle/cli src/dazzle/render/fragment tests/ --fix && ruff format src/dazzle/cli src/dazzle/render/fragment tests/
mypy src/dazzle/render --strict
mypy src/dazzle --ignore-missing-imports
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

All clean / no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/cli/fragment_audit.py src/dazzle/cli/__init__.py tests/integration/test_fragment_audit_cli.py
git commit -m "feat(cli): dazzle fragment-audit — text + json + CI-gate exit code"
```

---

## Task 6: CHANGELOG + final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run full unit suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 2: Run a real audit on simple_task and report the output**

```bash
python -m dazzle.cli fragment-audit examples/simple_task
```

Capture the output and use the aggregated-blockers list to prime the next plan's prioritisation.

- [ ] **Step 3: Update CHANGELOG**

In `CHANGELOG.md`, add to `## [Unreleased]` under `### Added`:

```markdown
- **`dazzle fragment-audit` CLI command (Plan 7).** Walks any AppSpec
  and reports per-surface Fragment-rendering coverage: ✓ ready / ✗
  blocked, with typed blocker reasons (unsupported mode, unsupported
  feature, unsupported field type) and aggregated counts. Text and
  JSON output; non-zero exit when any surface is blocked, suitable as
  a CI gate. Drives prioritisation of subsequent migration plans —
  close whichever blocker affects the most surfaces first.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 7 — dazzle fragment-audit"
```

---

## Plan completion checklist

- [ ] `pytest tests/unit/render/fragment/test_coverage.py tests/integration/test_fragment_audit_cli.py -v` — all pass.
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `python -m dazzle.cli fragment-audit examples/simple_task` produces a useful report.
- [ ] `git status` clean.
- [ ] **Stop condition met:** the audit tool produces structured output for any AppSpec; aggregated blockers drive next-plan prioritisation.

---

## Self-Review

**Spec coverage:**
- Goal: deterministic strategy via lint tool. Tasks 1-4 build the analysis library; Task 5 wraps as a CLI; Task 6 closes documentation.

**Placeholder scan:**
- Field-type detection in Task 2's `_audit_surface` uses a defensive `getattr` chain (`type` or `field_type`) because the IR's field-spec attribute name may vary; that's a deliberate adaptive read, not a TBD.
- The "_root_module_name" heuristic in Task 5 hedges because the project path → root module resolution exists in multiple call sites; the engineer is told to search for and reuse the existing helper if there is one.

**Type consistency:**
- `Blocker`, `BlockerKind`, `SurfaceCoverage`, `CoverageReport` defined in Task 1, consumed in Tasks 2-5.
- `audit_appspec(appspec) -> CoverageReport` signature consistent across uses.
- The `to_text()` and `to_json()` methods on `CoverageReport` are introduced in Tasks 3 and 4 respectively and consumed in Task 5's CLI.

**Scope check:**
- Plan covers only the audit tool. Closing any blocker the audit identifies is a subsequent plan. Leaving Plan 6 (detail mode) in the docs as a candidate closure that the audit may rank as worth doing — but its priority is now data-driven, not assumption-driven.
