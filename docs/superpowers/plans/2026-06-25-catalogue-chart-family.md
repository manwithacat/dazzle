# UX Catalogue — Complete the Chart Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 7 remaining chart-family display modes (line_chart, area_chart, sparkline, histogram, box_plot, radar, funnel_chart) to the published UX catalogue (10 → 17), and fold the per-mode fidelity marker into the manifest so the fidelity test derives from `CATALOGUE_MANIFEST`.

**Architecture:** Content + a test refactor — no render-code change. Each mode = a region in the `ux_catalogue` fixture workspace (DSL proven by `examples/ops_dashboard` + `examples/support_tickets`) + a `CATALOGUE_MANIFEST` entry (sample data + description + `marker`). The fidelity test switches from a hand-listed parametrize to iterating the manifest.

**Tech Stack:** Python 3.12, pytest, the no-DB catalogue harness (`src/dazzle/testing/ux_catalogue.py`), the real DSL→IR→orchestration→adapter→fragment render path.

## Global Constraints

- No new render code — the 7 modes already have builders (`_build_time_series`, `_build_histogram`, `_build_box_plot`, `_build_radar`, `_build_funnel_chart`).
- The fixture DSL region is the *real DSL* the catalogue renders — it stays; the manifest carries only sample data + description + marker.
- `marker` lives in the manifest entry for *every* mode (the 10 existing + 7 new).
- Ship discipline: `/bump patch`, ruff format before commit, `uv lock` after bump, clean worktree, watch CI + docs deploy green.
- Session-lens trailer `🔖 Claude-lens: dazzle` as the last line on any GitHub write.

---

## Proven DSL configs (mirrored from working examples)

From `examples/ops_dashboard` (Alert/System) + `examples/support_tickets` (Ticket), adapted to the catalogue's `Box` entity (`name`, `team` enum[platform,payments,growth,data], `status` enum[healthy,degraded,critical], `latency_ms` int, `error_rate` decimal, `target_ms` int, `opened_at` datetime):

| mode | group_by / value | aggregate | data source in harness |
|------|------------------|-----------|------------------------|
| line_chart | `bucket(opened_at, day)` | `count: count(Box)` | canned_buckets (fast-path GROUP BY via `repo.aggregate`) |
| area_chart | `[bucket(opened_at, week), team]` | `count: count(Box)` | canned_buckets (multi-dim) |
| sparkline | `bucket(opened_at, day)` | `count: count(Box)` | canned_buckets |
| histogram | `value: latency_ms` + `bins: auto` | — | `sample_items` = `_BOXES` (`_compute_histogram_bins`) |
| box_plot | `group_by: team` + `value: latency_ms` + `show_outliers: true` | — | `sample_items` = `_BOXES` (`_compute_box_plot_stats`) |
| radar | `group_by: team` | `count: count(Box where team = current_bucket)` | slow-path per-bucket via `repo.list` canned totals |
| funnel_chart | `group_by: status` | `count: count(Box)` | `sample_items` + kanban_columns from status enum |

**Probe-then-pin:** for each new mode, after adding the DSL region + a first-guess manifest entry, run the per-mode fidelity test; if it renders empty or the marker is wrong, dump the HTML, read the real `dz-*` class + adjust the canned data shape, and re-run. The aggregate-driven modes (line/sparkline/radar/area) need their canned-bucket dimension keys matched to what the orchestration's bucket-shaping reads (`<dim>` + `<dim>_label` for categorical; time buckets format via `_format_bucket_label`); the item-driven modes (histogram/box_plot) need only `sample_items`.

---

## Task 1: Fold the marker into the manifest (registry-SSOT refactor)

**Files:**
- Modify: `src/dazzle/testing/ux_catalogue_manifest.py` — add `"marker"` to each of the 10 entries.
- Modify: `tests/unit/test_ux_catalogue.py` — switch `test_mode_renders_primitive` to iterate the manifest.

**Interfaces:**
- Produces: every `CATALOGUE_MANIFEST[name]` dict has a `"marker": str` key (the `dz-*` class that mode emits).

- [ ] **Step 1: Add the existing markers to the manifest**

Add a `"marker"` key to each of the 10 current entries, using the markers already asserted in the test today:

```python
# cat_list → "dz-list" (table) — but cat_list also asserts the outlier badge;
# the generic marker is the table/list container:
"cat_list":     marker = "dz-list-region"   # confirm via probe; fall back to "<table"
"cat_metrics":  marker = "dz-metric-tile"
"cat_bar_chart":marker = "dz-bar-chart-region"
"cat_comparison":marker = "dz-bar-track"
"cat_heatmap":  marker = "dz-heatmap-region"
"cat_pivot":    marker = "dz-pivot-region"
"cat_bullet":   marker = "dz-bullet-region"
"cat_kanban":   marker = "dz-kanban-board"
"cat_insight":  marker = "dz-stack"
"cat_rag":      marker = "dz-badge"
```

For `cat_list` the current test asserts `"<table" in html or "dz-list" in html`; pick the stable substring the rendered list emits (probe: `python -c "from tests... import _render; print('dz-list' in _render('cat_list'))"`). Use the substring that is present.

- [ ] **Step 2: Switch the fidelity test to iterate the manifest**

Replace the `@pytest.mark.parametrize("name, marker", [...])` block + `test_mode_renders_primitive` with:

```python
@pytest.mark.parametrize("name", sorted(CATALOGUE_MANIFEST))
def test_mode_renders_primitive(name: str) -> None:
    html = _render(name)
    marker = CATALOGUE_MANIFEST[name]["marker"]
    assert html.strip(), f"{name} rendered empty"
    assert marker in html, f"{name} missing {marker!r}"
    assert "dz-empty" not in html, f"{name} fell through to an empty state"
```

Keep `test_list_renders_table_with_outlier_badge` (it asserts the outlier badge specifically) and `test_every_catalogue_region_has_a_manifest_entry`.

- [ ] **Step 3: Run the fidelity test — all 10 modes still green, now manifest-driven**

Run: `pytest tests/unit/test_ux_catalogue.py -q`
Expected: PASS (10 modes, markers sourced from the manifest). If any marker substring is wrong, dump the HTML for that mode and correct the `"marker"` value.

- [ ] **Step 4: Commit**

```bash
ruff format src/dazzle/testing/ux_catalogue_manifest.py tests/unit/test_ux_catalogue.py
git add src/dazzle/testing/ux_catalogue_manifest.py tests/unit/test_ux_catalogue.py
git commit -m "refactor(#1470): fold fidelity marker into the catalogue manifest"
```

---

## Task 2: Add the item-driven chart modes (histogram, box_plot)

These read from `sample_items` only — lowest risk, so they go first among the new modes.

**Files:**
- Modify: `fixtures/component_showcase/dsl/app.dsl` — add `cat_histogram`, `cat_box_plot` regions to `ux_catalogue`.
- Modify: `src/dazzle/testing/ux_catalogue_manifest.py` — add the two entries.

- [ ] **Step 1: Add the two regions to the fixture workspace**

Append to the `ux_catalogue` workspace (after `cat_rag`):

```dsl
  cat_histogram:
    source: Box
    display: histogram
    value: latency_ms
    bins: auto
    empty: "No boxes"

  cat_box_plot:
    source: Box
    display: box_plot
    group_by: team
    value: latency_ms
    show_outliers: true
    empty: "No boxes"
```

- [ ] **Step 2: Add the two manifest entries**

```python
"cat_histogram": {
    "description": "Continuous-axis distribution — `latency_ms` binned (Sturges' rule).",
    "marker": "dz-histogram-region",  # confirm via probe
    "sample_items": _BOXES,
    "canned_buckets": None,
},
"cat_box_plot": {
    "description": "Quartile spread per team — Q1/median/Q3 + Tukey whiskers over `latency_ms`.",
    "marker": "dz-box-plot-region",  # confirm via probe
    "sample_items": _BOXES,
    "canned_buckets": None,
},
```

- [ ] **Step 3: Validate the fixture parses**

Run: `cd fixtures/component_showcase && dazzle validate; cd -`
Expected: exit 0 (warnings OK).

- [ ] **Step 4: Probe + run the two fidelity tests**

Run: `pytest tests/unit/test_ux_catalogue.py -q -k "histogram or box_plot"`
If empty or marker missing, dump HTML:
`python -c "import sys; sys.argv=['x']; from tests.unit.test_ux_catalogue import _render; print(_render('cat_histogram'))"`
Read the real container class, set `marker` to it, re-run until PASS.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/testing/ux_catalogue_manifest.py
git add fixtures/component_showcase/dsl/app.dsl src/dazzle/testing/ux_catalogue_manifest.py
git commit -m "feat(#1470): catalogue histogram + box_plot modes"
```

---

## Task 3: Add the funnel_chart mode

`funnel_chart` is grouped-mode (kanban_columns from the status enum) + reads `sample_items`. Verify the harness threads what the funnel builder needs (it counts items per status); if the builder's primary path needs `group_by` in the adapter ctx and the harness path doesn't supply it, fall back to the legacy `buckets`/`metrics` ctx shape via a canned entry — pin by probe.

**Files:**
- Modify: `fixtures/component_showcase/dsl/app.dsl` — add `cat_funnel`.
- Modify: `src/dazzle/testing/ux_catalogue_manifest.py` — add the entry.

- [ ] **Step 1: Add the region**

```dsl
  cat_funnel:
    source: Box
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Box)
    empty: "No boxes"
```

- [ ] **Step 2: Add the manifest entry (first guess: sample_items)**

```python
"cat_funnel": {
    "description": "Stage funnel — boxes counted through the status lifecycle.",
    "marker": "dz-funnel-region",  # confirm via probe
    "sample_items": _BOXES,
    "canned_buckets": None,
},
```

- [ ] **Step 3: Probe + run the fidelity test**

Run: `pytest tests/unit/test_ux_catalogue.py -q -k funnel`
If empty: dump HTML, inspect what the funnel builder received. If it needs items+group_by that the harness doesn't thread, the funnel builder also accepts legacy `metrics`/`buckets` — but the catalogue feeds the adapter via the real render path, so prefer making `sample_items` carry status values that the kanban-column counting picks up (the `_BOXES` rows already have `status` healthy/degraded/critical). Adjust `_BOXES` coverage if a stage is empty; re-run until PASS + correct marker.

- [ ] **Step 4: Commit**

```bash
ruff format src/dazzle/testing/ux_catalogue_manifest.py
git add fixtures/component_showcase/dsl/app.dsl src/dazzle/testing/ux_catalogue_manifest.py
git commit -m "feat(#1470): catalogue funnel_chart mode"
```

---

## Task 4: Add the aggregate-driven time/polar modes (line_chart, sparkline, radar, area_chart)

These read `bucketed_metrics` shaped from `repo.aggregate` (fast path) or `repo.list` (slow path, radar's `current_bucket`). Canned data must match the shaping. Probe each.

**Files:**
- Modify: `fixtures/component_showcase/dsl/app.dsl` — add `cat_line`, `cat_sparkline`, `cat_radar`, `cat_area`.
- Modify: `src/dazzle/testing/ux_catalogue_manifest.py` — add four entries.

- [ ] **Step 1: Add the four regions**

```dsl
  cat_line:
    source: Box
    display: line_chart
    group_by: bucket(opened_at, day)
    aggregate:
      count: count(Box)
    empty: "No boxes"

  cat_sparkline:
    source: Box
    display: sparkline
    group_by: bucket(opened_at, day)
    aggregate:
      count: count(Box)
    empty: "—"

  cat_radar:
    source: Box
    display: radar
    group_by: team
    aggregate:
      count: count(Box where team = current_bucket)
    empty: "No boxes"

  cat_area:
    source: Box
    display: area_chart
    group_by: [bucket(opened_at, week), team]
    aggregate:
      count: count(Box)
    empty: "No boxes"
```

- [ ] **Step 2: Add four manifest entries with first-guess canned data**

For the **time modes** (line/sparkline) — fast-path GROUP BY over a time bucket; canned buckets carry the time dimension. First guess (pin via probe — the bucket dimension key is the field name `opened_at`, value an ISO date, plus the measure):

```python
_TIME_BUCKETS = [
    {"dimensions": {"opened_at": "2026-06-21"}, "measures": {"count": 3}},
    {"dimensions": {"opened_at": "2026-06-22"}, "measures": {"count": 5}},
    {"dimensions": {"opened_at": "2026-06-23"}, "measures": {"count": 4}},
    {"dimensions": {"opened_at": "2026-06-24"}, "measures": {"count": 8}},
    {"dimensions": {"opened_at": "2026-06-25"}, "measures": {"count": 6}},
]
"cat_line": {
    "description": "Time series — daily box volume. One `date_trunc('day')` GROUP BY.",
    "marker": "dz-time-series-region",  # confirm via probe
    "sample_items": [],
    "canned_buckets": _TIME_BUCKETS,
},
"cat_sparkline": {
    "description": "Compact trend tile — the same daily series as a headline + tiny SVG.",
    "marker": "dz-sparkline",  # confirm via probe
    "sample_items": [],
    "canned_buckets": _TIME_BUCKETS,
},
```

For **radar** — slow path (`current_bucket`) per team via `repo.list` canned totals (≥3 axes needed → 4 teams). The harness `_CatalogueRepo.list` pops `canned_list_totals` in order:

```python
"cat_radar": {
    "description": "Polar profile — one spoke per team, value = box count for that team.",
    "marker": "dz-radar-region",  # confirm via probe
    "sample_items": [],
    "canned_buckets": None,
    "canned_list_totals": [12, 7, 4, 9],  # platform, payments, growth, data
},
```

For **area_chart** — multi-dim (week × team); canned buckets carry both dims:

```python
"cat_area": {
    "description": "Stacked area — weekly volume split by team. Multi-dim time bucket.",
    "marker": "dz-time-series-region",  # confirm via probe (area shares TimeSeries)
    "sample_items": [],
    "canned_buckets": [
        {"dimensions": {"opened_at": "2026-06-15", "team": "platform"}, "measures": {"count": 6}},
        {"dimensions": {"opened_at": "2026-06-15", "team": "payments"}, "measures": {"count": 4}},
        {"dimensions": {"opened_at": "2026-06-22", "team": "platform"}, "measures": {"count": 8}},
        {"dimensions": {"opened_at": "2026-06-22", "team": "payments"}, "measures": {"count": 5}},
    ],
},
```

- [ ] **Step 3: Probe each mode, pin the canned shape + marker**

Run per mode: `pytest tests/unit/test_ux_catalogue.py -q -k line` (then sparkline, radar, area).
For each that renders empty: dump HTML + add a debug print inside a throwaway script of the `bucketed_metrics`/`axes`/`points` the builder received, correct the canned dimension/measure keys (e.g. the time-bucket label may need an ISO-parseable value so `_format_bucket_label` produces a label; radar needs ≥3 non-zero axes), re-run until PASS with the correct marker.

If a mode proves to need a data shape the no-DB harness can't cleanly fake (e.g. the slow-path radar enumeration needs distinct-bucket discovery the fake repo can't answer), note it and either (a) extend `_CatalogueRepo` minimally to serve it, or (b) defer that one mode with a logged note — do NOT ship a guessed/empty entry.

- [ ] **Step 4: Commit**

```bash
ruff format src/dazzle/testing/ux_catalogue_manifest.py
git add fixtures/component_showcase/dsl/app.dsl src/dazzle/testing/ux_catalogue_manifest.py
git commit -m "feat(#1470): catalogue line/sparkline/radar/area modes"
```

---

## Task 5: Regenerate the catalogue page + full-suite gate + ship

**Files:**
- Modify (generated): `docs/reference/ux-catalogue.md`, `docs/assets/dazzle-catalogue.css` (CSS only if sources changed — likely unchanged).
- Modify: `CHANGELOG.md`, version files (via `/bump patch`).

- [ ] **Step 1: Regenerate the page**

Run: `python scripts/gen_ux_catalogue.py`
Expected: `docs/reference/ux-catalogue.md` now shows 17 modes in declared order.

- [ ] **Step 2: Run the catalogue freshness + fidelity tests**

Run: `pytest tests/unit/test_ux_catalogue.py -q`
Expected: PASS — including `test_generated_page_is_current` (page matches generator output).

- [ ] **Step 3: Full unit suite (ignore known pollution failures)**

Run: `pytest tests/ -m "not e2e" -q`
Expected: PASS except the documented pollution failures (`test_alembic_env_url[empty_url]`, 3× `test_fuzzer_oracle`) which pass in isolation. The `test_dazzle_validate_drift` gate should stay within the warning grace (7 new regions add warnings); if it trips, regenerate its baseline per its instructions and note it in the commit.

- [ ] **Step 4: Lint + type**

Run: `ruff check src/dazzle tests/unit/test_ux_catalogue.py --fix && ruff format src/dazzle tests/unit/test_ux_catalogue.py && mypy src/dazzle`
Expected: clean.

- [ ] **Step 5: Bump + CHANGELOG**

Run `/bump patch`. Add a CHANGELOG `### Added` entry: the 7 chart-family catalogue modes (line_chart, area_chart, sparkline, histogram, box_plot, radar, funnel_chart) taking the catalogue to 17 modes, plus the manifest-driven fidelity marker (adding a catalogue mode is now a 2-place edit). Run `uv lock` after the bump.

- [ ] **Step 6: Commit, tag, push, watch CI + docs green**

```bash
git add -A
git commit -m "release: vX.Y.Z — catalogue chart family (#1470)"
git tag vX.Y.Z && git push && git push --tags
gh run watch  # CI + docs deploy
```

Confirm the live catalogue (GitHub Pages) shows 17 modes, then verify clean worktree (`git status`).
