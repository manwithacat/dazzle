# Stories and Scenes Operating Model

**Date:** 2026-03-11
**Status:** Draft
**Origin:** Cyfuture manifesto (`stories-and-scenes-operating-model.md`)
**Scope:** C-light — full operating model, advisory not enforcing

## Context

Cyfuture produced a manifesto describing stories and scenes as complementary instruments for modelling a domain. Stories model discrete capabilities (atomic, testable, stateless). Scenes model lived experience (temporal, contextual, composite). Together they form a complete model — stories drive implementation, scenes drive evaluation, and the gap between them is the roadmap.

Dazzle already has strong alignment: stories with Gherkin-style given/when/then, scenes nested within rhythm phases, and an explicit `story:` link from scenes to stories. This design incorporates the manifesto's remaining concepts: scene scoring dimensions, gap analysis, ambient utility, and the lifecycle workflow.

## Design Decisions

1. **Scene scoring dimensions live in evaluation output, not the DSL grammar.** The five dimensions (arrival, orientation, action, completion, confidence) are a diagnostic framework the evaluation agent applies uniformly. Authors don't need to declare what "good" looks like per dimension — the agent infers it from the scene's surface, actions, and expects fields.

2. **Phase `kind:` is a DSL construct.** Unlike scoring, phase kind is authorial intent — the person writing the rhythm declares whether a phase represents ambient check-ins, onboarding, etc. This is specification, not evaluation.

3. **Advisory, not enforcing.** The lifecycle operation reads state and recommends. It never blocks, refuses, or gates. Agents use it to orient themselves and are free to disagree with its recommendations.

## 1. DSL Grammar Changes

### Phase `kind:` field

New optional field on rhythm phases. Closed enum, parser-enforced.

```dsl
rhythm quarterly_review "Quarterly Review Cycle":
  persona: finance_director
  cadence: "quarterly"

  phase preparation:
    kind: periodic
    scene gather_reports "Gather Department Reports":
      on: report_list
      action: filter, review
      expects: "all_departments_visible"
      story: gather_dept_reports

  phase review:
    kind: active
    scene approve_budget "Approve Quarterly Budget":
      on: budget_approval
      action: submit
      entity: Budget
      expects: "budget_approved"
      story: approve_quarterly_budget

  phase between_quarters:
    kind: ambient
    scene check_trends "Check Financial Trends":
      on: finance_dashboard
      action: browse
      expects: "trend_indicators_visible"
```

**Enum values:**

| Value | Meaning |
|-------|---------|
| `onboarding` | First-time setup, orientation |
| `active` | Event-driven work |
| `periodic` | Recurring scheduled tasks |
| `ambient` | No trigger, proactive system value |
| `offboarding` | Wind-down, handoff, archival |

When `kind:` is omitted, the IR stores `None` (unspecified). Agents may infer `active` semantics for unspecified phases, but the IR does not assume — `None` means the author didn't declare intent.

No other grammar changes. Stories, scenes, and rhythms keep their current shape.

## 2. Evaluation Output Model

The rhythm `evaluate` operation gains scene-level dimension scoring as a second layer beyond structural validation.

### How scores are produced and stored

Scene dimension scores are **agent-produced, not computed**. The flow:

1. An evaluation agent walks a rhythm against a running app (or analyses DSL statically for a lighter check).
2. For each scene, the agent assesses the five dimensions and produces structured `SceneEvaluation` objects.
3. The agent calls the `evaluate` operation with `action: "submit_scores"`, passing the scored evaluations.
4. The operation validates the structure, classifies gap types from the scoring pattern, and persists to `.dazzle/evaluations/eval-{timestamp}.json`.
5. Subsequent calls to `evaluate` with `action: "evaluate"` (the existing structural check) now also load and return the most recent stored scores alongside structural results.

This means `evaluate` has two modes: **structural** (deterministic, existing behavior) and **scored** (agent-submitted, stored). The `gaps` and `lifecycle` operations consume stored scores when available and gracefully degrade to static analysis when not.

### Scene score structure

```python
class SceneDimensionScore(BaseModel):
    dimension: Literal["arrival", "orientation", "action", "completion", "confidence"]
    score: Literal["pass", "partial", "fail", "skip"]
    evidence: str          # what the agent observed
    root_cause: str | None # only on partial/fail

class SceneEvaluation(BaseModel):
    scene_name: str
    phase_name: str
    dimensions: list[SceneDimensionScore]
    gap_type: Literal["capability", "surface", "workflow", "feedback", "none"]
    story_ref: str | None  # linked story, if any
```

`SceneEvaluation.gap_type` is a **per-scene classification** derived from dimension scores — it answers "what kind of problem does this scene have?" The `Gap.kind` enum in Section 3 is a broader taxonomy that includes structural observations (ambient, unmapped, orphan) that exist independent of scene evaluation. The two enums overlap intentionally: per-scene gap types feed into the broader gaps analysis but don't cover structural-only findings.

### Gap type classification

Derived from the scoring pattern:

| Pattern | Gap type | Meaning |
|---------|----------|---------|
| Arrival fails or partial | `surface` | Can't reach the surface |
| Orientation fails/partial, action passes | `surface` | Surface is confusing but functional |
| Action fails | `capability` | Missing story / unimplemented feature |
| Completion fails | `workflow` | Action works but outcome is wrong |
| Confidence fails/partial, others pass | `feedback` | Works but unclear to the user |
| All pass | `none` | Scene is coherent |

The agent produces scores. The operation structures them. Downstream tools consume the structured output.

## 3. Gaps Analysis

New `gaps` operation on the `rhythm` MCP tool. Always runs static analysis from AppSpec. When stored evaluation scores exist in `.dazzle/evaluations/`, automatically layers in evaluated gaps. No mode parameter needed — the operation discovers what data is available and uses all of it.

### Static gaps (no running app needed)

Deterministic analysis from AppSpec alone:

- Scenes with `story:` references pointing to non-existent or `DRAFT` stories → **explicit capability gap**
- Scenes with no `story:` reference → **unmapped scene** (advisory)
- Stories that no scene references → **orphan story** (advisory)
- Personas with rhythms but no `ambient` phase → **ambient utility gap**
- Personas with stories but no rhythm → **unscored persona** (no journey to evaluate capabilities against)

### Evaluated gaps (after `evaluate` run)

Layers in stored scene scores:

- Scenes that scored `fail` on action → **missing capability**
- Scenes that scored `fail` on arrival/orientation → **surface gap**
- Scenes that scored `fail` on completion → **workflow gap**
- Aggregate per-persona summary

### Output structure

```python
class Gap(BaseModel):
    kind: Literal["capability", "surface", "workflow", "feedback", "ambient", "unmapped", "orphan", "unscored"]
    severity: Literal["blocking", "degraded", "advisory"]
    scene: str | None
    phase: str | None
    rhythm: str
    persona: str
    story_ref: str | None
    surface_ref: str | None
    description: str

class GapsSummary(BaseModel):
    total: int
    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_persona: dict[str, int]

class GapsReport(BaseModel):
    gaps: list[Gap]
    summary: GapsSummary
    roadmap_order: list[Gap]  # gaps sorted: blocking > degraded > advisory, then by affected scene count
```

### Severity rules

- `blocking` — scene cannot complete (action/completion fail, or story doesn't exist)
- `degraded` — scene completes but poorly (orientation/confidence issues)
- `advisory` — structural observation, no failure (unmapped, orphan, missing ambient)

## 4. Lifecycle Operation

New `lifecycle` operation on the `rhythm` MCP tool. Inspects AppSpec and stored evaluation/gaps data, returns status against the manifesto's eight-step cycle.

### Output structure

```python
class LifecycleStep(BaseModel):
    step: int
    name: str
    status: Literal["complete", "partial", "not_started"]
    evidence: str
    suggestions: list[str]

class LifecycleReport(BaseModel):
    steps: list[LifecycleStep]
    current_focus: str
    maturity: Literal["new_domain", "building", "evaluating", "mature"]
```

### The eight steps

| Step | Name | Checks |
|------|------|--------|
| 1 | `model_domain` | Entities exist, have fields and relationships |
| 2 | `write_stories` | Stories exist, accepted vs draft ratio |
| 3 | `write_rhythms` | Rhythms exist, cover personas |
| 4 | `map_scenes_to_stories` | Scene→story references present, unmapped count |
| 5 | `build_from_stories` | Stories have generated tests, tests exist |
| 6 | `evaluate_from_scenes` | Evaluation scores exist in `.dazzle/evaluations/` |
| 7 | `find_gaps` | Gaps report exists, blocking count |
| 8 | `iterate` | Delta since last run — new stories, resolved gaps |

### Maturity classification

Determined by the highest step that has `status: "complete"`:

- `new_domain` — no step is `complete`, or only step 1 is `complete`
- `building` — steps 1-3 are `complete` (step 4+ may be `partial` or `not_started`)
- `evaluating` — steps 1-5 are `complete` (step 6+ may be `partial` or `not_started`)
- `mature` — steps 1-7 are `complete` (step 8 tracks iteration, always `partial`)

A step is `complete` when its primary check passes (e.g., step 2: at least one accepted story exists). `partial` means some evidence exists but the check isn't fully satisfied. `not_started` means no evidence.

### Key principle

This operation reads state. It never writes, blocks, or refuses. The manifesto's ordering insight (stories first for new domains, scenes first for mature) shows up in `current_focus`, but the agent is free to disagree.

## 5. Integration

### Parser changes

- `_parse_rhythm_phase()` gains optional `kind:` field parsing
- `PhaseSpec` gains `kind: PhaseKind | None` (note: `PhaseSpec` is frozen — `kind` must be passed at construction time)
- `PhaseKind` enum: `onboarding`, `active`, `periodic`, `ambient`, `offboarding`
- Story references in scenes (`story:` field) use story names as identifiers (e.g., `story: approve_vat_return`), consistent with the existing parser

### MCP handler changes

| Operation | Change |
|-----------|--------|
| `rhythm evaluate` | Enriched: new `submit_scores` action for agent-produced dimension scoring; existing `evaluate` action returns stored scores alongside structural results |
| `rhythm gaps` | **New.** Static and evaluated modes |
| `rhythm lifecycle` | **New.** Lifecycle status report |
| `rhythm propose` | Updated prompt: aware of phase kinds, suggests ambient phases |
| `rhythm coverage` | Updated: includes ambient coverage |
| `story propose` | Updated prompt: cross-references scenes for planning inversion |
| `pipeline run` | Updated: adds a `scene_gaps` quality step that runs static gaps analysis and includes the summary in pipeline output |

### Storage

- `.dazzle/evaluations/eval-{timestamp}.json` — scene evaluation scores
- `.dazzle/evaluations/gaps-{timestamp}.json` — gaps reports
- `.dazzle/stories/stories.json` — unchanged

### Knowledge graph

- New relation type: `scene_exercises_story` — connects `scene:{rhythm_name}.{scene_name}` → `story:{story_name}`, populated during linker phase from scene `story:` references
- New relation type: `gap_blocks_scene` — connects `gap:{kind}:{description_hash}` → `scene:{rhythm_name}.{scene_name}`, populated when gaps analysis runs. Metadata: `severity`, `kind`

### Files touched

| File | Change |
|------|--------|
| `src/dazzle/core/ir/rhythm.py` | `PhaseKind` enum, `kind` field, evaluation/gap/lifecycle models |
| `src/dazzle/core/dsl_parser_impl/rhythm.py` | Parse `kind:` in phases |
| `src/dazzle/mcp/server/handlers/rhythm.py` | `gaps`, `lifecycle` operations; enriched `evaluate` |
| `src/dazzle/mcp/server/handlers/stories.py` | Updated `propose` prompt |
| `src/dazzle/mcp/server/handlers/pipeline.py` | Gaps summary in audit |
| `src/dazzle/mcp/server/tools_consolidated.py` | Register new operations |
| `docs/reference/rhythms.md` | Phase kinds, gaps, lifecycle docs |
| `docs/reference/grammar.md` | `kind:` in rhythm phase grammar |
| Tests | Parser, IR, MCP handler tests |

### No changes to

Grammar structure (just additions), linker validation logic, code generation, runtime, UI, CLI commands, LSP.
