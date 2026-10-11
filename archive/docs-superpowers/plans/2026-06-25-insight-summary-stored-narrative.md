# insight_summary Slice 2a — Stored-Narrative Contract Implementation Plan (#1470)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an `insight_summary` region render a pre-computed/stored narrative (prose + confidence + "as of" freshness) over the always-present deterministic citations, falling back to the deterministic Slice-1 narrative when none — with generation stubbed behind a provider seam.

**Architecture:** A render-layer `StoredInsight` type + an in-memory provider seam (no DB). The orchestration always computes the deterministic narrative (Slice 1) and additionally reads a stored narrative via the provider; the render branches stored-vs-deterministic, with the deterministic citations as the shared grounding. Layers `http → page → render → core`.

**Tech Stack:** Python 3.12, Pydantic/dataclass, pytest. Reuses the Slice-1 `InsightNarrative` + `_build_insight_summary` + the chart-family ctx wiring.

## Global Constraints

- `ruff check src/ tests/` + `ruff format` clean; bare `mypy src/dazzle` clean (matches CI).
- **Run the full `pytest -m "not e2e"` before shipping.** The 3 `test_fuzzer_oracle` failures are pre-existing pollution (pass isolated) — ignore.
- **No IR change** in 2a (`StoredInsight` is a render-layer type; no DSL grammar) → no api-surface / golden-master drift expected. Confirm at ship.
- The provider registry MUST be a **dict mutated in place** (not a reassigned module global) to pass the #1445 mutable-globals ratchet (`tests/unit/test_no_new_mutable_globals_1445.py`).
- The deterministic citations render beneath any prose — the grounding contract. All prose escaped at emit.
- Provider key = `region_name` (a 2a simplification; `WorkspaceRegionContext` carries no workspace name. 2b's real store keys more fully).
- Complexity ratchet: new functions ≤ CC 15.
- The catalogue fidelity test stays green (the `cat_insight` mode gains a stored-narrative card).

## File structure

- `src/dazzle/render/fragment/insight.py` — add `StoredInsight` (beside `InsightNarrative`).
- `src/dazzle/http/runtime/insight_store.py` (new) — provider seam (`get_stored_insight`, `set_insight_provider`, `reset_insight_provider`).
- `src/dazzle/http/runtime/workspace_region_orchestration.py` — read the provider in the INSIGHT_SUMMARY branch.
- `src/dazzle/http/runtime/workspace_region_render.py` — `RegionRenderInputs.stored_insight` + chart adapter-ctx key.
- `src/dazzle/render/fragment/region/_context.py` — RegionContext TypedDict key.
- `src/dazzle/render/fragment/region/_builders_charts.py` — `_build_insight_summary` stored branch.
- `src/dazzle/testing/ux_catalogue.py` — inject a stub provider so `cat_insight` shows the stored card.

---

## Task 1: `StoredInsight` type + provider seam

**Files:**
- Modify: `src/dazzle/render/fragment/insight.py` (add `StoredInsight`)
- Create: `src/dazzle/http/runtime/insight_store.py`
- Test: `tests/unit/test_insight_store.py`

**Interfaces — Produces:**
- `StoredInsight` (frozen dataclass): `prose: tuple[str, ...]`, `confidence: Literal["high","medium","low"]`, `generated_at: str`.
- `get_stored_insight(region_name: str) -> StoredInsight | None`
- `set_insight_provider(fn: Callable[[str], StoredInsight | None]) -> None`
- `reset_insight_provider() -> None`

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_store.py
from dazzle.http.runtime.insight_store import (
    get_stored_insight,
    reset_insight_provider,
    set_insight_provider,
)
from dazzle.render.fragment.insight import StoredInsight


def test_default_provider_returns_none() -> None:
    reset_insight_provider()
    assert get_stored_insight("any_region") is None


def test_settable_provider() -> None:
    si = StoredInsight(prose=("Revenue is climbing.",), confidence="high", generated_at="2026-06-25")
    set_insight_provider(lambda region: si if region == "team_insight" else None)
    try:
        assert get_stored_insight("team_insight") is si
        assert get_stored_insight("other") is None
    finally:
        reset_insight_provider()
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_insight_store.py -q` → FAIL.

- [ ] **Step 3: implement.** In `insight.py`, add `Literal` to the typing import if absent, then beside `InsightNarrative`:

```python
@dataclass(frozen=True, slots=True)
class StoredInsight:
    """A pre-computed (eventually LLM-authored) narrative overlay (#1470 Slice 2a).

    Rendered ABOVE the deterministic citations (the always-present grounding),
    so the prose is always verifiable against the real values beneath it.
    """

    prose: tuple[str, ...]
    confidence: Literal["high", "medium", "low"]
    generated_at: str
```

Create `src/dazzle/http/runtime/insight_store.py`:

```python
"""Stored-narrative provider seam for display: insight_summary (#1470 Slice 2a).

The region render reads a pre-computed narrative through this seam. The default
provider returns None (so the region falls back to the deterministic Slice-1
narrative). Slice 2b registers a real provider (a scheduled process that calls
the LLM over the grounded buckets and writes a store). Tests + the catalogue
inject a stub.

The registry is a dict mutated in place (not a reassigned module global) to
stay clear of the #1445 mutable-globals ratchet.
"""

from collections.abc import Callable

from dazzle.render.fragment.insight import StoredInsight

_Provider = Callable[[str], "StoredInsight | None"]


def _default_provider(_region_name: str) -> "StoredInsight | None":
    return None


_REGISTRY: dict[str, _Provider] = {"provider": _default_provider}


def set_insight_provider(fn: _Provider) -> None:
    """Register the stored-narrative provider (keyed by region name)."""
    _REGISTRY["provider"] = fn


def reset_insight_provider() -> None:
    """Restore the default (None-returning) provider."""
    _REGISTRY["provider"] = _default_provider


def get_stored_insight(region_name: str) -> "StoredInsight | None":
    """Return the stored narrative for ``region_name``, or None (→ deterministic fallback)."""
    return _REGISTRY["provider"](region_name)
```

- [ ] **Step 4:** `uv run pytest tests/unit/test_insight_store.py -q` → PASS.

- [ ] **Step 5:** ruff + mypy clean; `uv run pytest tests/unit/test_no_new_mutable_globals_1445.py -q` → PASS (the dict-in-place registry must not trip the ratchet; if it lists a new `global`, there's a reassignment to fix).

- [ ] **Step 6: commit**

```bash
git add src/dazzle/render/fragment/insight.py src/dazzle/http/runtime/insight_store.py tests/unit/test_insight_store.py
git commit -m "feat(#1470): StoredInsight type + insight-store provider seam (Slice 2a)"
```

---

## Task 2: Orchestration — read the provider into ctx

**Files:**
- Modify: `src/dazzle/http/runtime/workspace_region_orchestration.py`
- Modify: `src/dazzle/http/runtime/workspace_region_render.py` (`RegionRenderInputs` + adapter ctx)
- Modify: `src/dazzle/render/fragment/region/_context.py` (TypedDict)
- Test: `tests/unit/test_insight_stored_orchestration.py`

**Interfaces — Consumes:** `get_stored_insight` (Task 1). **Produces:** `ctx["stored_insight"]` = a `StoredInsight` or None.

- [ ] **Step 1: failing test** — assert that, with a stub provider, the INSIGHT_SUMMARY render shows the stored prose; the test drives the full adapter via a constructed `RegionRenderInputs` is heavy, so test at the seam: the orchestration sets `RegionRenderInputs.stored_insight`. The simplest real test is end-to-end through the render (Task 3), so here add a focused unit test that the provider read + None-on-error wrapper behaves:

```python
# tests/unit/test_insight_stored_orchestration.py
from dazzle.http.runtime.insight_store import reset_insight_provider, set_insight_provider
from dazzle.http.runtime.workspace_region_orchestration import _read_stored_insight
from dazzle.render.fragment.insight import StoredInsight


def test_read_stored_insight_returns_provider_value() -> None:
    si = StoredInsight(prose=("x",), confidence="high", generated_at="2026-06-25")
    set_insight_provider(lambda r: si)
    try:
        assert _read_stored_insight("r") is si
    finally:
        reset_insight_provider()


def test_read_stored_insight_swallows_provider_error() -> None:
    def _boom(_r: str):
        raise RuntimeError("provider down")

    set_insight_provider(_boom)
    try:
        assert _read_stored_insight("r") is None  # error → None → deterministic fallback
    finally:
        reset_insight_provider()
```

- [ ] **Step 2:** run → FAIL (`_read_stored_insight` missing).

- [ ] **Step 3: implement.** In `workspace_region_orchestration.py`:
  - Add the import: `from dazzle.http.runtime.insight_store import get_stored_insight`.
  - Add a small wrapper (module-level, near the top) that never lets a provider error break render:

```python
def _read_stored_insight(region_name: str) -> Any:
    """Read the stored narrative for a region; a provider error → None (fallback)."""
    try:
        return get_stored_insight(region_name)
    except Exception:
        logger.warning("insight_summary stored-narrative provider failed for %r", region_name, exc_info=True)
        return None
```

  - In the existing `INSIGHT_SUMMARY` compute branch (where `insight_narrative` is built), set `stored_insight` too; in the `else`, None:

```python
    if display == "INSIGHT_SUMMARY" and group_by and bucketed_metrics:
        # ... existing build_insight_inputs(...) assigning insight_narrative ...
        stored_insight = _read_stored_insight(getattr(ctx.ir_region, "name", "") or "")
    else:
        insight_narrative = None
        stored_insight = None
```

  - Add to the `RegionRenderInputs(...)` construction (next to `insight_narrative=insight_narrative`):

```python
        stored_insight=stored_insight,
```

- [ ] **Step 4: thread the field + adapter ctx.** In `workspace_region_render.py`:
  - Add to `RegionRenderInputs` next to `insight_narrative: Any = None`:

```python
    stored_insight: Any = None
```

  - In `_build_chart_adapter_ctx`, in the `elif display_upper == "INSIGHT_SUMMARY":` branch (next to the `insight_narrative` line):

```python
        adapter_ctx["stored_insight"] = inputs.stored_insight
```

  - In `_context.py`, next to the `insight_narrative: Any` TypedDict key:

```python
    stored_insight: Any
```

- [ ] **Step 5:** `uv run pytest tests/unit/test_insight_stored_orchestration.py -q` → PASS; ruff + mypy clean.

- [ ] **Step 6: commit**

```bash
git add src/dazzle/http/runtime/workspace_region_orchestration.py src/dazzle/http/runtime/workspace_region_render.py src/dazzle/render/fragment/region/_context.py tests/unit/test_insight_stored_orchestration.py
git commit -m "feat(#1470): read stored insight into ctx (provider seam + fallback)"
```

---

## Task 3: Render — stored-vs-deterministic branch

**Files:**
- Modify: `src/dazzle/render/fragment/region/_builders_charts.py` (`_build_insight_summary`)
- Test: `tests/unit/test_insight_stored_render.py`

**Interfaces — Consumes:** `ctx["stored_insight"]` (Task 2), `ctx["insight_narrative"]` (Slice 1), `Text`/`Stack`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_stored_render.py
from dazzle.render.fragment.insight import InsightNarrative, StoredInsight
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self) -> None:
        self.name = "ins"
        self.title = "Team Insight"
        self.display = "insight_summary"
        self.empty_message = None


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


_DET = InsightNarrative(
    lines=("52 alerts across 6 teams.", "Platform is highest at 12 (23% of the total)."),
    citations=(("Platform", 12.0), ("ML", 1.0)),
    scope="across all teams",
)


def test_stored_overlay_with_grounding_and_confidence() -> None:
    stored = StoredInsight(
        prose=("Alert volume is concentrated in Platform; ML is unusually quiet.",),
        confidence="medium",
        generated_at="2026-06-25 14:00",
    )
    html = _render({"insight_narrative": _DET, "stored_insight": stored})
    assert "unusually quiet" in html  # the stored prose
    assert "Platform" in html and "12" in html  # the deterministic citations (grounding) beneath
    assert "medium" in html  # confidence
    assert "2026-06-25 14:00" in html  # as-of freshness
    assert 'data-dz-tone="warning"' in html  # medium -> warning tone


def test_fallback_to_deterministic_when_no_stored() -> None:
    html = _render({"insight_narrative": _DET, "stored_insight": None})
    assert "Platform is highest at 12" in html  # deterministic prose
    assert "Computed from live data" in html  # deterministic badge
    assert "data-dz-tone=" not in html or "warning" not in html  # no confidence badge


def test_stored_prose_escaped() -> None:
    stored = StoredInsight(prose=("<script>alert(1)</script>",), confidence="high", generated_at="t")
    html = _render({"insight_narrative": _DET, "stored_insight": stored})
    assert "<script>alert(1)</script>" not in html
```

- [ ] **Step 2:** run → FAIL (no stored branch).

- [ ] **Step 3: implement.** In `_builders_charts.py` `_build_insight_summary`, after computing the deterministic `nar = ctx.get("insight_narrative")` and its `lines` (and the existing empty-state guard), add a stored branch BEFORE the deterministic line-render. Add a module-level confidence-tone map near `_RAG_LABELS`/the insight helpers:

```python
_CONFIDENCE_TONE = {"high": "positive", "medium": "warning", "low": "neutral"}
```

Replace the body that builds `children` so it prefers the stored overlay:

```python
        stored = ctx.get("stored_insight")
        stored_prose = tuple(getattr(stored, "prose", ()) or ())
        citations = getattr(nar, "citations", ()) or ()
        scope = getattr(nar, "scope", "")

        if stored_prose:
            children: list[Fragment] = [Text(body=str(line)) for line in stored_prose]
            if citations:
                cite_str = " · ".join(f"{lbl} {_fmt_num(val)}" for lbl, val in citations)
                children.append(Text(body=f"Based on: {cite_str}", tone="muted"))
            conf = str(getattr(stored, "confidence", "") or "")
            tone = _CONFIDENCE_TONE.get(conf, "neutral")
            children.append(
                RawHTML(
                    f'<span class="dz-badge dz-badge-sm" data-dz-tone="{tone}" role="status" '
                    f'aria-label="Confidence: {_esc(conf)}">confidence: {_esc(conf)}</span>'
                )
            )
            children.append(
                Text(body=f"{scope} · as of {getattr(stored, 'generated_at', '')}".strip(" ·"), tone="muted")
            )
            return _wrap_surface(title, "report", Stack(children=tuple(children), gap="sm"))

        # deterministic path (Slice 1) — unchanged below
        children = [Text(body=str(line)) for line in lines]
        ...  # (keep the existing citation + scope + "Computed" badge code)
```

(`_esc` = `from html import escape as _esc` — add a local import in the helper, mirroring `_outlier_badge`. `RawHTML`, `Text`, `Stack` are imported in this file.)

- [ ] **Step 4:** run → PASS (3 cases). Then `uv run pytest tests/unit/test_insight_summary_render.py -q` → PASS (Slice-1 render unaffected — `stored_insight` absent → deterministic path).

- [ ] **Step 5:** ruff + mypy clean; `uv run pytest -m gate -q` (complexity — if `_build_insight_summary` exceeds CC 15, extract `_stored_insight_card(...)` / `_deterministic_card(...)` helpers).

- [ ] **Step 6: commit**

```bash
git add src/dazzle/render/fragment/region/_builders_charts.py tests/unit/test_insight_stored_render.py
git commit -m "feat(#1470): render stored-narrative overlay (prose + confidence + freshness over grounding)"
```

---

## Task 4: Catalogue stub + full suite + ship

**Files:**
- Modify: `src/dazzle/testing/ux_catalogue.py` (inject a stub provider so `cat_insight` shows the stored card)
- Modify: `docs/reference/ux-catalogue.md` (regen), `CHANGELOG.md`, version files (`/bump`)

- [ ] **Step 1: catalogue stub.** In `src/dazzle/testing/ux_catalogue.py`, before rendering `cat_insight` (in `render_catalogue_region`, or a small registration at module import / in `iter_catalogue_regions`), register a stub provider so the catalogue's insight card shows the stored-narrative shape. Simplest: in `render_catalogue_region`, when `ir_region.name == "cat_insight"`, set a stub provider for that render and reset after:

```python
        from dazzle.http.runtime.insight_store import reset_insight_provider, set_insight_provider
        from dazzle.render.fragment.insight import StoredInsight

        if ir_region.name == "cat_insight":
            set_insight_provider(
                lambda _r: StoredInsight(
                    prose=(
                        "Alert volume is concentrated in Platform, with ML unusually quiet — "
                        "worth checking whether ML's pipeline is reporting.",
                    ),
                    confidence="medium",
                    generated_at="2026-06-25 14:00 UTC",
                )
            )
        try:
            ... existing render ...
        finally:
            reset_insight_provider()
```

  (Keep the existing render call inside the try; the reset ensures no cross-region leakage. If the harness renders regions in a loop, the per-region set/reset keeps `cat_insight` showing the stored card and every other mode unaffected.)

- [ ] **Step 2:** regenerate the page: `uv run python scripts/gen_ux_catalogue.py`. Probe that the cat_insight section now shows the stored prose + confidence + "as of": `grep -c "unusually quiet\|confidence: medium\|as of 2026" docs/reference/ux-catalogue.md` → ≥ 1. Run `uv run pytest tests/unit/test_ux_catalogue.py -q` → PASS (the `cat_insight` marker `dz-stack` still holds; the card is now the stored variant).

- [ ] **Step 3: full suite:** `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 `test_fuzzer_oracle` pollution failures (confirm isolated). No golden-master / api-surface drift expected (no IR change) — if golden-master drifts, investigate (it shouldn't).

- [ ] **Step 4:** `uv run ruff check src/ tests/ && uv run mypy src/dazzle` clean.

- [ ] **Step 5:** `/bump patch` (6 version lines + `uv lock`). CHANGELOG `### Added` (Slice 2a — the stored-narrative overlay + provider seam + automatic deterministic fallback + confidence/freshness, generation stubbed) + `### Agent Guidance` (the provider seam + the always-grounding contract: deterministic citations render beneath any prose; that Slice 2b adds the real scheduled-process LLM generator with a ProcessRun subject per #1454).

- [ ] **Step 6: commit + tag + push**, then watch CI + the docs deploy green; confirm the catalogue's insight card now shows the stored-narrative shape (prose + confidence + as-of). Keep `git status` clean (commit `uv.lock`).

---

## Self-review

- **Spec coverage:** `StoredInsight` + provider seam (dict-in-place, no DB) → Task 1; orchestration read + None-on-error + ctx threading → Task 2; render stored-vs-deterministic branch with confidence/freshness over the deterministic grounding → Task 3; catalogue stub + ship → Task 4. All spec sections covered. No IR change (confirmed — `StoredInsight` is render-layer).
- **Type consistency:** `StoredInsight{prose, confidence, generated_at}` (Task 1) consumed unchanged by the orchestration (Task 2) + render (Task 3). `get_stored_insight(region_name) -> StoredInsight | None` (Task 1) wrapped by `_read_stored_insight` (Task 2). `ctx["stored_insight"]` is the one ctx key across Tasks 2/3.
- **Placeholder scan:** the Task 3 deterministic-path `...` keeps the *existing* Slice-1 code (the engineer reads the current `_build_insight_summary` and preserves its citation/scope/Computed-badge lines below the stored branch) — flagged explicitly, not a vague placeholder. The Task 1 mutable-globals note is a real gate to run.
- **Reuse:** the Slice-1 `InsightNarrative` + `_build_insight_summary` + chart ctx wiring + the catalogue harness — all reused; genuinely new code is `StoredInsight`, `insight_store.py`, `_read_stored_insight`, the render stored branch, and the catalogue stub.

## Notes

- **Grounding contract is structural:** the stored branch ALWAYS appends the deterministic `citations` beneath the prose — a 2b LLM that hallucinates is visibly contradicted by the real numbers. Do not let the stored path drop the citations.
- **Provider key = region name** (2a simplification; `WorkspaceRegionContext` has no workspace name). 2b's real store record can key by (app, workspace, region).
- **No DSL change, no IR change** — 2a is render-layer + a provider seam. Slice 2b adds the real generator (scheduled process, ProcessRun subject #1454, LLM over grounded buckets, grounding-enforcement check, store write, confidence derivation, refresh).
```
