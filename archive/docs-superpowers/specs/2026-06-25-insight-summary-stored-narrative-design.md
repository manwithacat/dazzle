# insight_summary Slice 2a — stored-narrative contract + fallback (#1470)

**Status:** Approved design — ready for implementation plan.
**Issue:** #1470 item 5, `insight_summary`. Slice 1 (deterministic narrative) shipped v0.86.27. This is **Slice 2a**: the stored-narrative read + fallback + trust-render contract, with generation **stubbed**. Slice 2b implements the real generator (a scheduled process → LLM → store).

## Goal

Let an `insight_summary` region render a **pre-computed/stored** narrative (richer prose + confidence + "as of" freshness) on top of the **always-present deterministic grounding**, falling back automatically to the deterministic Slice-1 narrative when no stored narrative exists (no LLM provider, nothing generated yet, CI). Generation is a stubbed provider in 2a.

## Why this shape (decided during brainstorm)

The runtime LLM path (`LLMExecutor.execute`) requires a subject per #1454 (entity instance or ProcessRun) — a region narrative summarizes many aggregated rows and has no entity-instance subject. The clean fit (Slice 2b) is a **scheduled process** (ProcessRun subject) that generates + stores the narrative; the region reads the stored value. Slice 2a builds that **read + fallback + trust-render contract** with a **stubbed provider**, so it is fully testable in CI without an LLM and 2b only has to add the real provider. The **deterministic computation (Slice 1) is always the grounding** — its citations (the real bucket values) render beneath any LLM prose, so a future hallucinating model is caught by the visible numbers.

## Design decisions (locked)

1. **Provider-seam storage, no DB in 2a.** `get_stored_insight(workspace_name, region_name) -> StoredInsight | None`, backed by a settable in-memory provider. Default returns `None` (prod → deterministic fallback). Tests + the catalogue inject a stub. Slice 2b replaces the provider with a real one (process-written framework store).
2. **Deterministic citations are the always-present grounding.** Orchestration always computes the Slice-1 `InsightNarrative` (facts + citations); the stored narrative is a richer *overlay* of prose + confidence + freshness rendered **above the same citation block** — never a replacement.
3. **Categorical confidence** — `Literal["high","medium","low"]` (honest: LLMs can't produce calibrated floats).
4. **Automatic fallback** — stored present → stored prose + confidence + "as of"; else → deterministic prose + "Computed from live data". The grounding (citations) is identical either way.
5. **No new DSL grammar** — every `insight_summary` region attempts the stored read; the provider keys by `(workspace_name, region_name)`. (A generation-config keyword / intent ref is a 2b concern.)

## Non-goals (deferred to Slice 2b / later)

- The real generator: a scheduled process (ProcessRun subject) calling the LLM over the grounded buckets, with the grounding-enforcement check, writing to a framework store.
- Persistent storage (a framework entity / table) + refresh triggers / staleness invalidation.
- Author-configured intent ref / prompt / model per region.
- Clickable citations; per-claim confidence.

## Architecture — the contract; generation stubbed

### render/ — types (`src/dazzle/render/fragment/insight.py`)
- Add a frozen `StoredInsight` dataclass: `prose: tuple[str, ...]`, `confidence: Literal["high", "medium", "low"]`, `generated_at: str` (iso-ish display string). Lives beside `InsightNarrative` so render consumes it and orchestration imports it.

### http/runtime — provider seam (`src/dazzle/http/runtime/insight_store.py`, new)
- `get_stored_insight(workspace_name: str, region_name: str) -> StoredInsight | None` — calls the registered provider.
- `set_insight_provider(fn: Callable[[str, str], StoredInsight | None]) -> None` and `reset_insight_provider() -> None`.
- The registry is a **dict mutated in place** (`_REGISTRY = {"provider": _default_provider}`; `set_insight_provider` does `_REGISTRY["provider"] = fn`) — NOT a reassigned module global, to stay clear of the #1445 mutable-globals ratchet (same pattern as `docs_gen._AUTO_SOURCE_GENERATORS` / `core.validation.surfaces`'s pack-ops registry).
- `_default_provider(ws, rg)` returns `None`.

### http/orchestration (`workspace_region_orchestration.py`)
- In the existing `INSIGHT_SUMMARY` compute branch (which already builds the deterministic `insight_narrative`), also call `get_stored_insight(workspace_name, region_name)` and thread the result as `stored_insight` (or None) into `RegionRenderInputs` → the chart adapter ctx → the `RegionContext` TypedDict (a new `stored_insight` key, mirroring `insight_narrative`). The `workspace_name` is available on `ctx` (or via the region context); the `region_name` is `ctx.ir_region.name`.

### render (`region/_builders_charts.py::_build_insight_summary`)
- Branch: if `ctx["stored_insight"]` is a `StoredInsight` with non-empty prose →
  - render its `prose` lines (Text), then a trust footer = the deterministic narrative's **citations** (`Based on: …`) + scope + a **confidence** badge (`data-dz-tone` mapped: high→positive, medium→warning, low→muted/neutral) + `as of <generated_at>`.
  - else → the existing deterministic path (Slice 1) unchanged.
- All strings escaped at emit (the prose comes from the provider; for 2a the stub provides trusted canned text, but the render escapes it regardless — 2b's real LLM output MUST flow through the same escaping).

## Render detail — the stored-narrative trust card

- **Prose** lines (the richer narrative) as a `Stack` of `Text`.
- **Trust footer** (muted): the deterministic `citations` (`Based on: A 12 · B 1 …`) — the always-present grounding; the `scope`; a **confidence badge** (`● high` / `● medium` / `● low` with `data-dz-tone`); and `as of <generated_at>`. Confidence + freshness appear ONLY on the stored path; the deterministic path keeps the "Computed from live data" badge.

## Edge cases

- Provider returns `None` / raises → deterministic fallback (the orchestration wraps the provider call so a provider error never breaks render; logs + falls back).
- Stored narrative with empty `prose` → treated as absent → deterministic fallback.
- No `insight_narrative` at all (empty buckets) → the existing "No insight" empty state (unchanged).
- Unknown confidence string (defensive) → render the word with a neutral tone.

## Testing (TDD per layer)

1. **Types + provider seam** — `StoredInsight` round-trips; `get_stored_insight` returns the registered provider's value; default returns None; `set_insight_provider`/`reset_insight_provider` work; the dict-in-place registry passes the #1445 mutable-globals ratchet gate.
2. **Orchestration** — with a stub provider returning a `StoredInsight`, the `INSIGHT_SUMMARY` branch threads `stored_insight` into the inputs; with the default provider, `stored_insight` is None.
3. **Render** — stored path: the card shows the stored prose + a confidence badge (`data-dz-tone`) + "as of" + the deterministic citations; fallback path (no stored): the deterministic prose + "Computed" badge; HTML-escaping of prose preserved; empty-buckets → "No insight".
4. **Example + catalogue + ship** — inject a stub provider in the catalogue harness so `cat_insight` renders the stored-narrative card (prose + confidence + "as of") with the grounding beneath; regen the catalogue page; `dazzle validate` exit 0 (no DSL change, so likely no new drift); golden-master likely unchanged (no IR change — `StoredInsight` is render-layer, not IR); full `pytest -m "not e2e"` (ignore the 3 `test_fuzzer_oracle` pollution failures); ruff + bare `mypy src/dazzle` clean; `/bump patch` with CHANGELOG (`### Added` Slice 2a + `### Agent Guidance` on the provider seam + the always-grounding contract + that 2b adds the real generator); commit + tag + push; watch CI + docs deploy green.

## Complexity / risk notes (model-driven-failure-modes lens)

- **Traceability:** the rendered card traces to the deterministic computation (DSL `group_by`/`aggregate`) + the provider's stored value. No DSL change in 2a.
- **Grounding contract is structural:** the deterministic citations render beneath any prose — the answer to the AI "plausible-but-wrong" failure mode. A 2b LLM that hallucinates is visibly contradicted by the numbers.
- **Fallback / availability:** no LLM provider → `get_stored_insight` returns None → deterministic narrative. The feature degrades safely and is fully testable without an LLM.
- **No new IR, no new escape hatch in 2a** — render-layer types + a provider seam; deterministic, conformance-visible. The LLM dependency enters only in 2b, behind the provider.

## Deferred (Slice 2b and beyond)

- **Slice 2b:** the real provider — a scheduled process (ProcessRun subject, #1454) that renders the grounded-buckets prompt, calls `LLMExecutor.execute`, runs a grounding-enforcement check (the prose must not contradict the deterministic facts), derives confidence, and writes to a framework store; refresh triggers; staleness.
- Author-configured intent/prompt/model per region; clickable citations; per-claim confidence; multi-region narratives.
