# UX Catalogue MVP Implementation Plan (Sub-project A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a GitHub-Pages UX component catalogue — one mkdocs page rendering 8 curated Dazzle display modes (+ the `outlier_on` decorator) to real HTML from real DSL, each with its DSL snippet + description.

**Architecture:** Extend `fixtures/component_showcase` with a `ux_catalogue` workspace (8 regions). A no-DB render harness drives the **real** orchestration + adapter (`compute_region_render_inputs` → `render_region_html`) with sample data from a manifest (items + canned aggregate buckets via a fake repository). A generator emits a markdown page rendered into the existing mkdocs/GitHub-Pages site.

**Tech Stack:** Python 3.12, Pydantic IR, pytest, mkdocs Material. Reuses `build_workspace_context`, `_build_entity_columns`, `compute_region_render_inputs`, `render_region_html`, `AggregateBucket`, and the `dazzle.min.css` bundle.

## Global Constraints

- `ruff check src/ tests/ scripts/` + `ruff format` clean; bare `mypy src/dazzle` clean (matches CI).
- **Run the full `pytest -m "not e2e"` before shipping.** The 3 `test_fuzzer_oracle` failures are pre-existing pollution (pass isolated) — ignore.
- The fixture gains a workspace → regenerate `tests/unit/fixtures/dazzle_validate_baseline.json`. `fixtures/component_showcase` must stay `dazzle validate` exit 0 and keep its existing `Showcase` form entity + widget surface (they back widget-type capability demonstrations in `mcp/semantics_kb/capabilities.toml`).
- Curated MVP modes (8): `list` (+ `outlier_on`), `metrics`, `bar_chart`, `comparison`, `heatmap`, `pivot_table`, `bullet`, `kanban`. No other modes (Sub-project B).
- The render harness uses the **real** DSL→IR→orchestration→adapter→HTML path — no DB, no server, no browser. Sample data (items + buckets) comes from the manifest.
- Complexity ratchet: new functions ≤ CC 15; extract helpers if exceeded.

## File structure

- `fixtures/component_showcase/dsl/app.dsl` — add `ux_catalogue` workspace + catalogue entity/entities.
- `src/dazzle/testing/ux_catalogue_manifest.py` — per-region `{description, sample_items, canned_buckets}`.
- `src/dazzle/testing/ux_catalogue.py` — the render harness (`render_catalogue_region`, `iter_catalogue_regions`).
- `scripts/gen_ux_catalogue.py` — the page generator (`--mode=ci` staleness gate).
- `docs/reference/ux-catalogue.md` — generated, committed.
- `docs/assets/dazzle-catalogue.css` — scoped CSS copy of the framework bundle.
- `mkdocs.yml` — nav entry + `extra_css`.
- `.github/workflows/docs.yml` — add the generator step before `mkdocs build`.
- `tests/unit/test_ux_catalogue.py` — fidelity gate + staleness test.

---

## Task 1: Fixture — `ux_catalogue` workspace + entities

**Files:**
- Modify: `fixtures/component_showcase/dsl/app.dsl`
- Modify: `tests/unit/fixtures/dazzle_validate_baseline.json` (regen)
- Test: the fixture's own `dazzle validate`

**Interfaces — Produces:** a `component_showcase` AppSpec containing a workspace named `ux_catalogue` with 8 regions named `cat_list`, `cat_metrics`, `cat_bar_chart`, `cat_comparison`, `cat_heatmap`, `cat_pivot`, `cat_bullet`, `cat_kanban`, sourced from a new `Box` entity.

- [ ] **Step 1:** Read the current fixture: `fixtures/component_showcase/dsl/app.dsl` (entity `Showcase` + admin role/user — leave untouched). Add a numeric/enum/date entity for the catalogue and the workspace. Append:

```dsl
entity Box "Box":
  id: uuid pk
  name: str(80) required
  team: enum[platform,payments,growth,data]=platform
  status: enum[healthy,degraded,critical]=healthy
  latency_ms: int
  error_rate: decimal(5,2)
  target_ms: int
  opened_at: datetime

workspace ux_catalogue "UX Catalogue":
  cat_list:
    source: Box
    display: list
    sort: name asc
    outlier_on: latency_ms
    outlier_method: iqr
    empty: "No boxes"

  cat_metrics:
    source: Box
    display: metrics
    aggregate:
      total: count(Box)
      critical: count(Box where status = critical)
      avg_latency: avg(latency_ms)

  cat_bar_chart:
    source: Box
    display: bar_chart
    group_by: team
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_comparison:
    source: Box
    display: comparison
    group_by: team
    aggregate:
      total: count(Box)
    rank_by: total
    order: desc
    outlier_method: iqr
    empty: "No boxes"

  cat_heatmap:
    source: Box
    display: heatmap
    group_by: status
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_pivot:
    source: Box
    display: pivot_table
    group_by: [team, status]
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_bullet:
    source: Box
    display: bullet
    bullet_label: name
    bullet_actual: latency_ms
    bullet_target: target_ms
    empty: "No boxes"

  cat_kanban:
    source: Box
    display: kanban
    group_by: status
    empty: "No boxes"
```

(Add a minimal list surface for `Box` if `dazzle validate` warns about a missing surface — mirror the existing `Showcase` surface shape. Confirm each region's keywords against the real grammar by re-checking `examples/ops_dashboard/dsl/app.dsl` for `bullet_*`, `group_by: [..]`, etc.)

- [ ] **Step 2:** `cd fixtures/component_showcase && uv run dazzle validate` → exit 0 (warnings OK, no errors). If a region errors on an unknown keyword, fix the DSL against the grammar.

- [ ] **Step 3: regen the validate baseline:** from repo root, run the command the test uses to regenerate `tests/unit/fixtures/dazzle_validate_baseline.json` (inspect `tests/unit/test_*` that loads it for the regen flag; if none, hand-update the `fixtures/component_showcase` entry). Then `uv run pytest tests/unit/test_example_index.py -q` → PASS.

- [ ] **Step 4:** `uv run pytest tests/unit/test_cli_sweep.py tests/unit/test_example_index.py -q` → PASS (fixture still discovered + validates).

- [ ] **Step 5: commit**

```bash
git add fixtures/component_showcase/dsl/app.dsl tests/unit/fixtures/dazzle_validate_baseline.json
git commit -m "feat: ux_catalogue workspace in component_showcase fixture (8 display modes)"
```

---

## Task 2: Render harness + `list` mode (the orchestration-seam spike)

**Files:**
- Create: `src/dazzle/testing/ux_catalogue.py`
- Create: `src/dazzle/testing/ux_catalogue_manifest.py`
- Test: `tests/unit/test_ux_catalogue.py`

**Interfaces — Produces:**
- `CATALOGUE_MANIFEST: dict[str, CatalogueEntry]` where `CatalogueEntry = {"description": str, "sample_items": list[dict], "canned_buckets": list[dict] | None}` keyed by region name.
- `iter_catalogue_regions(appspec) -> list[tuple[ir_region, ctx_region]]` — the `ux_catalogue` workspace's regions paired with their `ctx_region`.
- `render_catalogue_region(appspec, ir_region, ctx_region, entry) -> str` — real-render HTML for one region.
- `load_showcase_appspec() -> AppSpec` — parse + link the fixture.

**Read first (pinned seams):**
- `build_workspace_context(workspace, appspec)` (`src/dazzle/page/runtime/workspace_renderer.py:443`) → `ws_ctx.regions` are the `ctx_region` pydantic models, index-aligned to `workspace.regions`.
- `WorkspaceRegionContext` (`src/dazzle/http/runtime/workspace_context.py:19`) — most fields default; required: `ctx_region, ir_region, source, entity_spec, attention_signals, ws_access, repositories, require_auth, auth_middleware`.
- `RequestUserContext` (`src/dazzle/http/runtime/workspace_region_prelude.py:32`) — `RequestUserContext(user_id=None, user_entity=None, auth_ctx_for_filters=None, filter_context={})`.
- `RegionItemsResult` (`src/dazzle/http/runtime/workspace_region_fetch.py:45`) — `RegionItemsResult(items=..., total=..., scope_only_filters={}, context_filters={}, scope_denied=False)` (check exact field names/defaults).
- `compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)` and `render_region_html(request, ctx, user_ctx, inputs, sort, sort_dir)` (`workspace_region_orchestration.py` / `workspace_region_render.py:601`).
- `_build_entity_columns(entity)` (`src/dazzle/page/converters/template_compiler.py:1057`) for columns (dump to `list[dict]` if it returns typed `ColumnContext` — match what the route builder passes as `columns`).

- [ ] **Step 1: failing test** (start with `list` — item-based, no buckets)

```python
# tests/unit/test_ux_catalogue.py
from dazzle.testing.ux_catalogue import (
    iter_catalogue_regions,
    load_showcase_appspec,
    render_catalogue_region,
    CATALOGUE_MANIFEST,
)


def _render(name: str) -> str:
    appspec = load_showcase_appspec()
    for ir_region, ctx_region in iter_catalogue_regions(appspec):
        if ir_region.name == name:
            return render_catalogue_region(appspec, ir_region, ctx_region, CATALOGUE_MANIFEST[name])
    raise AssertionError(f"region {name} not found")


def test_list_renders_table_with_outlier_badge() -> None:
    html = _render("cat_list")
    assert "<table" in html or "dz-list" in html
    assert 'data-dz-tone="warning"' in html  # outlier_on flags the latency outlier
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_ux_catalogue.py::test_list_renders_table_with_outlier_badge -q` → FAIL (module missing).

- [ ] **Step 3: manifest.** Create `src/dazzle/testing/ux_catalogue_manifest.py`. For `cat_list`, sample_items must include a clear latency outlier so the badge renders (≥6 finite values, one anomalous):

```python
"""Sample data + descriptions for the ux_catalogue regions (#ux-catalogue)."""

_BOXES = [
    {"name": "alpha", "team": "platform", "status": "healthy", "latency_ms": 42, "error_rate": 0.1, "target_ms": 50},
    {"name": "bravo", "team": "platform", "status": "healthy", "latency_ms": 38, "error_rate": 0.2, "target_ms": 50},
    {"name": "charlie", "team": "payments", "status": "degraded", "latency_ms": 44, "error_rate": 1.4, "target_ms": 50},
    {"name": "delta", "team": "payments", "status": "healthy", "latency_ms": 40, "error_rate": 0.3, "target_ms": 50},
    {"name": "echo", "team": "growth", "status": "healthy", "latency_ms": 46, "error_rate": 0.2, "target_ms": 50},
    {"name": "foxtrot", "team": "data", "status": "critical", "latency_ms": 380, "error_rate": 7.2, "target_ms": 50},
]

CATALOGUE_MANIFEST = {
    "cat_list": {
        "description": "The workhorse table. Here it carries the `outlier_on` decorator — the `latency_ms` cell flags the statistical outlier (⚠ high) vs the displayed rows.",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    # ... (other 7 added in Task 3)
}
```

- [ ] **Step 4: implement the harness.** Create `src/dazzle/testing/ux_catalogue.py`. Build the real pipeline with the pinned seams. Sketch (wire against the real signatures — adjust field names per the read-first list):

```python
"""No-DB render harness for the UX catalogue (Sub-project A).

Drives the REAL DSL->IR->orchestration->adapter->HTML path for one
ux_catalogue region, feeding sample data (items + canned aggregate
buckets) from the manifest via a fake repository. No DB/server/browser.
"""

import asyncio
from pathlib import Path
from typing import Any

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.http.runtime.aggregate import AggregateBucket
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_fetch import RegionItemsResult
from dazzle.http.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.http.runtime.workspace_region_prelude import RequestUserContext
from dazzle.http.runtime.workspace_region_render import render_region_html
from dazzle.page.converters.template_compiler import _build_entity_columns
from dazzle.page.runtime.workspace_renderer import build_workspace_context

from dazzle.testing.ux_catalogue_manifest import CATALOGUE_MANIFEST  # noqa: F401

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "component_showcase"


class _FakeRequest:
    def __init__(self) -> None:
        self.query_params: dict[str, str] = {}
        self.headers: dict[str, str] = {}


class _CatalogueRepo:
    """Serves canned aggregate buckets; item lists arrive via RegionItemsResult."""

    def __init__(self, buckets: list[dict[str, Any]] | None) -> None:
        self._buckets = buckets or []

    async def aggregate(self, *, dimensions: Any, measures: Any, filters: Any = None, **kw: Any) -> list[AggregateBucket]:
        return [AggregateBucket(dimensions=b["dimensions"], measures=b["measures"]) for b in self._buckets]


def load_showcase_appspec() -> Any:
    modules = parse_modules(sorted((_FIXTURE / "dsl").glob("*.dsl")))
    return build_appspec(modules, "component_showcase")


def iter_catalogue_regions(appspec: Any) -> list[tuple[Any, Any]]:
    ws = next(w for w in appspec.workspaces if w.name == "ux_catalogue")
    ws_ctx = build_workspace_context(ws, appspec)
    return list(zip(ws.regions, ws_ctx.regions, strict=False))


def render_catalogue_region(appspec: Any, ir_region: Any, ctx_region: Any, entry: dict[str, Any]) -> str:
    source = ir_region.source or ""
    entity_spec = next((e for e in appspec.domain.entities if e.name == source), None)
    columns = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in _build_entity_columns(entity_spec)] if entity_spec else []
    repo = _CatalogueRepo(entry.get("canned_buckets"))
    ctx = WorkspaceRegionContext(
        ctx_region=ctx_region,
        ir_region=ir_region,
        source=source,
        entity_spec=entity_spec,
        attention_signals=[],
        ws_access=None,
        repositories={source: repo},
        require_auth=False,
        auth_middleware=None,
        precomputed_columns=columns,
    )
    fetched = RegionItemsResult(
        items=list(entry.get("sample_items") or []),
        total=len(entry.get("sample_items") or []),
        scope_only_filters={},
        context_filters={},
        scope_denied=False,
    )
    user_ctx = RequestUserContext(user_id=None, user_entity=None, auth_ctx_for_filters=None, filter_context={})
    request = _FakeRequest()

    async def _run() -> str:
        inputs = await compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)
        return await render_region_html(request, ctx, user_ctx, inputs, None, "")

    return asyncio.run(_run())
```

- [ ] **Step 5:** `uv run pytest tests/unit/test_ux_catalogue.py::test_list_renders_table_with_outlier_badge -q` → PASS. Iterate on the harness against the real signatures until green (this is the spike — the field names/defaults of `RegionItemsResult` / `WorkspaceRegionContext` are pinned above; adjust only if a constructor rejects an arg).

- [ ] **Step 6:** `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle` clean (the harness is under `src/dazzle/testing/` so it's type-checked).

- [ ] **Step 7: commit**

```bash
git add src/dazzle/testing/ux_catalogue.py src/dazzle/testing/ux_catalogue_manifest.py tests/unit/test_ux_catalogue.py
git commit -m "feat: no-DB ux_catalogue render harness + list mode (real orchestration seam)"
```

---

## Task 3: Chart/aggregate modes — fake repo buckets + fidelity tests

**Files:**
- Modify: `src/dazzle/testing/ux_catalogue_manifest.py` (canned buckets for the 7 remaining modes)
- Test: `tests/unit/test_ux_catalogue.py`

**Interfaces — Consumes:** `_CatalogueRepo.aggregate` (Task 2). **Produces:** manifest entries with `canned_buckets` for `cat_metrics`, `cat_bar_chart`, `cat_comparison`, `cat_heatmap`, `cat_pivot`; `sample_items` for `cat_bullet`, `cat_kanban`.

- [ ] **Step 1: failing test** — one fidelity assertion per remaining mode, asserting the mode's primitive marker:

```python
import pytest


@pytest.mark.parametrize(
    "name, marker",
    [
        ("cat_metrics", "dz-metric"),
        ("cat_bar_chart", "dz-bar"),
        ("cat_comparison", "dz-bar-track"),  # comparison renders a BarTrack
        ("cat_heatmap", "dz-heatmap"),
        ("cat_pivot", "dz-pivot"),
        ("cat_bullet", "dz-bullet"),
        ("cat_kanban", "dz-kanban"),
    ],
)
def test_mode_renders_primitive(name: str, marker: str) -> None:
    html = _render(name)
    assert html.strip(), f"{name} rendered empty"
    assert marker in html, f"{name} missing {marker!r}"
```

(Verify each `marker` against the real emitter — grep `src/dazzle/render/fragment/renderer/` for the class name per primitive, e.g. `dz-bar-track`, `dz-heatmap`. Adjust the marker to the actual class the emitter writes.)

- [ ] **Step 2:** `uv run pytest tests/unit/test_ux_catalogue.py -q` → FAIL (empty/missing buckets for the aggregate modes).

- [ ] **Step 3: implement** — add the manifest entries. Buckets mirror the real `aggregate()` shape: each bucket is `{"dimensions": {<group_by>: <value>, "<group_by>_label": <label>}, "measures": {<metric>: <number>}}`. Example for `cat_bar_chart` (group_by team, count):

```python
    "cat_bar_chart": {
        "description": "Distribution by a category — one bar per group. Compiles to a single scope-aware GROUP BY.",
        "sample_items": [],
        "canned_buckets": [
            {"dimensions": {"team": "platform", "team_label": "platform"}, "measures": {"count": 12}},
            {"dimensions": {"team": "payments", "team_label": "payments"}, "measures": {"count": 7}},
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"count": 4}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"count": 9}},
        ],
    },
    "cat_comparison": {
        "description": "Ranked league — rows ranked by a metric with inline bars + automatic outlier flag.",
        "sample_items": [],
        "canned_buckets": [
            {"dimensions": {"team": "platform", "team_label": "platform"}, "measures": {"total": 12}},
            {"dimensions": {"team": "payments", "team_label": "payments"}, "measures": {"total": 11}},
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"total": 10}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"total": 9}},
            {"dimensions": {"team": "infra", "team_label": "infra"}, "measures": {"total": 9}},
            {"dimensions": {"team": "ml", "team_label": "ml"}, "measures": {"total": 1}},
        ],
    },
```

For `cat_metrics` (scalar aggregates, no group_by) the orchestration uses a different path (`_compute_aggregate_metrics`) — read `workspace_region_orchestration.py` for how metrics regions fetch, and provide what that path reads (it may compute from `items` or call the repo). If metrics needs items, give `sample_items`; if it calls `aggregate`, give buckets keyed by the metric names. `cat_bullet` + `cat_kanban` are item-based — give `sample_items` (Box rows). `cat_heatmap`/`cat_pivot` read `group_by` buckets — give the two-dim buckets for pivot.

- [ ] **Step 4:** `uv run pytest tests/unit/test_ux_catalogue.py -q` → PASS (all 8 modes). Iterate the buckets/items per mode until each renders its marker.

- [ ] **Step 5:** ruff + mypy clean.

- [ ] **Step 6: commit**

```bash
git add src/dazzle/testing/ux_catalogue_manifest.py tests/unit/test_ux_catalogue.py
git commit -m "feat: ux_catalogue chart modes (canned buckets) + fidelity tests for 8 modes"
```

---

## Task 4: Generator — `scripts/gen_ux_catalogue.py`

**Files:**
- Create: `scripts/gen_ux_catalogue.py`
- Create: `docs/reference/ux-catalogue.md` (generated, committed)
- Test: `tests/unit/test_ux_catalogue.py` (staleness)

**Interfaces — Consumes:** `iter_catalogue_regions`, `render_catalogue_region`, `CATALOGUE_MANIFEST` (Task 2/3). **Produces:** `generate_catalogue_markdown() -> str` and a `--mode=ci` staleness gate.

- [ ] **Step 1: failing test**

```python
def test_generated_page_is_current() -> None:
    from scripts.gen_ux_catalogue import generate_catalogue_markdown
    from pathlib import Path

    committed = Path("docs/reference/ux-catalogue.md").read_text()
    assert generate_catalogue_markdown() == committed, (
        "ux-catalogue.md is stale — run `python scripts/gen_ux_catalogue.py`"
    )


def test_generated_page_has_all_modes() -> None:
    from scripts.gen_ux_catalogue import generate_catalogue_markdown

    md = generate_catalogue_markdown()
    for marker in ("UX Catalogue", "cat_list", "data-dz-tone", "```dsl"):
        assert marker in md
```

- [ ] **Step 2:** run → FAIL (module missing).

- [ ] **Step 3: implement** `scripts/gen_ux_catalogue.py`:

```python
#!/usr/bin/env python3
"""Generate docs/reference/ux-catalogue.md from the component_showcase ux_catalogue workspace."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dazzle.testing.ux_catalogue import (  # noqa: E402
    CATALOGUE_MANIFEST,
    iter_catalogue_regions,
    load_showcase_appspec,
    render_catalogue_region,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "reference" / "ux-catalogue.md"
_DSL = Path(__file__).resolve().parents[1] / "fixtures" / "component_showcase" / "dsl" / "app.dsl"


def _dsl_snippet(region_name: str) -> str:
    """Slice the region block from the fixture DSL by indentation."""
    lines = _DSL.read_text().splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.strip().startswith(f"{region_name}:"):
            capturing = True
            out.append(line.strip())
            continue
        if capturing:
            if line.strip() and not line.startswith("    "):
                break
            if line.strip().endswith(":") and not line.startswith("      ") and out:
                # next region at same indent
                if line.startswith("  ") and not line.startswith("    "):
                    break
            out.append(line.rstrip())
    return "\n".join(out).strip()


def generate_catalogue_markdown() -> str:
    appspec = load_showcase_appspec()
    parts = [
        "# UX Catalogue",
        "",
        "Every component below is rendered from real Dazzle DSL through the real "
        "render pipeline — the same code that produces a running app's HTML. "
        "Each card shows the live component and the DSL that produced it.",
        "",
    ]
    for ir_region, ctx_region in iter_catalogue_regions(appspec):
        name = ir_region.name
        entry = CATALOGUE_MANIFEST.get(name)
        if not entry:
            continue
        html = render_catalogue_region(appspec, ir_region, ctx_region, entry)
        title = (getattr(ir_region, "display", "") or name).replace("_", " ").title()
        parts += [
            f"## {title}",
            "",
            entry["description"],
            "",
            '<div class="dz-catalogue-preview" markdown="0">',
            html,
            "</div>",
            "",
            "```dsl",
            _dsl_snippet(name),
            "```",
            "",
        ]
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["write", "ci"], default="write")
    args = ap.parse_args()
    md = generate_catalogue_markdown()
    if args.mode == "ci":
        current = OUT.read_text() if OUT.exists() else ""
        if current != md:
            print("ux-catalogue.md is stale — run: python scripts/gen_ux_catalogue.py", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4:** generate the page: `uv run python scripts/gen_ux_catalogue.py`. Then `uv run pytest tests/unit/test_ux_catalogue.py -q` → PASS. Eyeball `docs/reference/ux-catalogue.md` — confirm each mode has description + rendered HTML + DSL block. Fix `_dsl_snippet` if a block is mis-sliced (verify against the fixture's actual indentation).

- [ ] **Step 5:** ruff + mypy clean (`scripts/` is ruff-checked; mypy targets `src/dazzle` so the script itself isn't mypy-gated, but keep it clean).

- [ ] **Step 6: commit**

```bash
git add scripts/gen_ux_catalogue.py docs/reference/ux-catalogue.md tests/unit/test_ux_catalogue.py
git commit -m "feat: ux-catalogue page generator (--mode=ci staleness gate)"
```

---

## Task 5: Publish — CSS + mkdocs nav + docs workflow

**Files:**
- Create: `docs/assets/dazzle-catalogue.css`
- Modify: `mkdocs.yml` (nav + `extra_css`)
- Modify: `.github/workflows/docs.yml` (generator step)

- [ ] **Step 1:** Create the scoped CSS. Read `src/dazzle/page/runtime/static/dist/dazzle.min.css` (the bundle). Copy it to `docs/assets/dazzle-catalogue.css`. Inspect its selectors: if they're global (e.g. bare `table`, `body`), prefix the component rules under `.dz-catalogue-preview ` so they don't restyle the Material theme; if they're already `.dz-*`-scoped, a raw copy is fine. Add a wrapper rule:

```css
.dz-catalogue-preview {
  border: 1px solid var(--md-default-fg-color--lightest, #ddd);
  border-radius: 8px;
  padding: 1rem;
  margin: 0.5rem 0 1rem;
  background: #fff;
  overflow-x: auto;
}
```

- [ ] **Step 2:** In `mkdocs.yml`, add the stylesheet and nav entry:

```yaml
extra_css:
  - assets/dazzle-catalogue.css

# under nav:, add (in a sensible section, e.g. near Reference):
  - UX Catalogue: reference/ux-catalogue.md
```

(Read the existing `nav:` block and insert the entry in the matching style/indentation.)

- [ ] **Step 3:** Build the docs locally to confirm no mkdocs error: `uv run mkdocs build --strict 2>&1 | tail -20` (install docs extra if needed: `uv pip install ".[docs]"` or `mkdocs-material`). Expected: build succeeds; `site/reference/ux-catalogue/index.html` exists and contains `dz-catalogue-preview`. If `--strict` fails on the embedded HTML, ensure the page uses `markdown="0"` on the preview div (already in the generator) or configure `md_in_html`.

- [ ] **Step 4:** In `.github/workflows/docs.yml`, add a generator step before `mkdocs build` (next to the existing `gen_reference_docs.py` step):

```yaml
      - name: Generate UX catalogue
        run: python scripts/gen_ux_catalogue.py --mode=ci
```

(Use `--mode=ci` so a stale committed page fails the build, mirroring the reference-docs gate. The page itself is committed, so CI doesn't write — it only verifies freshness.)

- [ ] **Step 5: commit**

```bash
git add docs/assets/dazzle-catalogue.css mkdocs.yml .github/workflows/docs.yml
git commit -m "feat: publish ux-catalogue to GitHub Pages (mkdocs nav + scoped CSS + docs CI gate)"
```

---

## Task 6: Full suite + ship

**Files:**
- Modify: `CHANGELOG.md`, version files (`/bump`)

- [ ] **Step 1: full suite:** `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 pre-existing `test_fuzzer_oracle` pollution failures (confirm in isolation). Fix anything else.

- [ ] **Step 2:** `uv run ruff check src/ tests/ scripts/ && uv run mypy src/dazzle` clean.

- [ ] **Step 3:** `/bump patch` (all 6 version lines + `uv lock`). CHANGELOG `### Added` (the UX catalogue: GitHub-Pages component gallery rendered from real DSL via the real pipeline; 8 modes; the no-DB harness doubles as a fidelity gate) + `### Agent Guidance` (how to add a mode to the catalogue: add a region to the `ux_catalogue` workspace + a manifest entry + regen the page; the harness/manifest pattern; the Sub-project B/C deferrals).

- [ ] **Step 4: commit + tag + push**, then `gh run watch <ci-run-id> --exit-status` AND confirm the `docs` workflow goes green (it runs the catalogue generator + deploys Pages). Confirm the page is live at `https://manwithacat.github.io/dazzle/reference/ux-catalogue/` after deploy. Keep `git status` clean.

---

## Self-review

- **Spec coverage:** fixture extension (Task 1) → spec §Architecture-1; no-DB real-render harness (Task 2) → §Architecture-2 + the flagged risk; canned-buckets data mechanism (Task 2/3) → decision 4; 8 curated modes (Task 1/3) → decision 5; generator + page (Task 4) → §Architecture-3; CSS scoping + mkdocs + docs.yml publish (Task 5) → §Architecture-4; fidelity gate + staleness (Task 2/3/4) → §Testing; ship (Task 6). All spec sections covered.
- **The flagged risk (orchestration-input construction)** is Task 2, front-loaded with every seam pinned to an exact file:line + a working construction sketch. If a constructor rejects a field, the read-first list says which file to check.
- **Type consistency:** `render_catalogue_region(appspec, ir_region, ctx_region, entry) -> str` (Task 2) is the single render entry, consumed unchanged by the generator (Task 4). `CATALOGUE_MANIFEST[name] = {"description", "sample_items", "canned_buckets"}` is the one data shape across Tasks 2/3/4. Bucket shape `{"dimensions": {...}, "measures": {...}}` matches `AggregateBucket`.
- **Placeholder scan:** the harness sketch (Task 2 Step 4) and `_dsl_snippet` (Task 4) are the two spots that need verify-against-reality; both are flagged with the exact files to check, not left vague.

## Notes

- **Small deviation from the spec, surfaced:** the MVP manifest carries **sample items** (not just canned buckets) for item-based modes, rather than wiring the `demo_data` seed-loader. Same intent (fixture-provided sample data injected at the orchestration seam) but self-contained and far less plumbing. Real `demo_data` integration is a clean Sub-project B item.
- **Markers in tests** (`dz-bar-track`, `dz-heatmap`, …) must be verified against the actual emitters in `src/dazzle/render/fragment/renderer/` — the plan says to grep+adjust per mode rather than trust the guessed class name.
- The harness lives in `src/dazzle/testing/` (test infrastructure) so it's mypy-gated and importable by both the script and the test — single source of render truth for the catalogue.
