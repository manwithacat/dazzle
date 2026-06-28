# Framework UX-maturity rubric

A rubric that scores **Dazzle the framework**, not a screen. The question is not
"does this screen answer the user's question?" — that's instance evaluation
(`dazzle ux verify`, the `/ux-pass` story walk). The question here is:

> **Does Dazzle make the data-right UI the DEFAULT?**

Instance screens are *evidence*; the verdict is about the framework's primitives
and their zero-effort defaults. The output is a defensible maturity index plus a
**prioritised list of framework primitives worth building**, keyed to the
framework version so regressions are attributable.

> **Naming.** "maturity" is overloaded in this codebase — `fitness/maturity.py`
> (project lifecycle: mvp/beta/stable) and the agent-command `[maturity]` gate
> (command applicability) are unrelated. This rubric is always **`ux maturity`**.

## The one capability

Three UX principles converge, at the framework altitude, on a single capability:
**choosing — from the data and context — rather than by hand.**

- **Data drives the UI** → choose the **form** from the data's shape (temporal →
  trend/timeline; ordered-state → board; categorical → chips/colour; grouped
  quantity → chart — *not* table-by-default).
- **Progressive disclosure** → choose **how much** to show from what the user
  needs to act (answer-first; depth one cheap click away, never forced up front).
- **Negative space / strategic concealment** → choose **whether** to show from
  role, entity state, and frequency (rare-but-important features present but not
  routinely rendered; affordances appear only when they apply).

Form / amount / whether are *inference* problems the framework is better placed
to solve than the author — which is why maturity tops out at **adaptive**, not
**configurable**.

## The five lenses (human-readable spine)

Per workspace/region, the rubric asks (after AegisMark `strategy.md`):

1. **Question** — what decision is this persona here to make?
2. **Answer-first?** — does the surface lead with the answer/anomaly, or a raw
   table the user must compute from?
3. **Shape** — is the representation right for the question (trend for
   "improving?", comparison for "who's behind?", heatmap for "which dimension?"),
   or a generic list?
4. **Cost** — ≤3 actions for a basic info need, surfaced where the user lands.
5. **Honesty** — human values, not raw data (no UUID / unrounded float / `True`);
   for AI outputs, confidence + evidence shown.

The 13 criteria below are these lenses made measurable at the framework altitude.

## The maturity ladder (0–4, scored per criterion)

| Level | Name | Meaning |
|---|---|---|
| 0 | Absent | the capability does not exist in any form |
| 1 | Escape-hatch | achievable only via `mode: custom` / a custom renderer / hand HTML |
| 2 | Declarative-manual | a primitive exists **but** the author must hand-specify it and the **default is wrong** for the common case |
| 3 | Good-defaults | exists **and** the zero-effort default is right for the common case |
| 4 | Adaptive | the framework **infers** the right treatment from data shape / semantics / usage |

**Target:** most criteria ≥3; none at 0–1 for a common case. **RAG:** 0–1 red,
2 amber, 3–4 green. **Overall index** = mean criterion level; **per-principle
index** = mean of that principle's criteria.

**Level-4 is real, not aspirational** — Dazzle already exhibits it in three
places, which anchor the top of the ladder:
- a chart `display:` compiles to **one scope-aware `GROUP BY`** (the framework
  infers the aggregation + the row filter);
- **transitions** are offered from the **state graph** (the framework infers
  which actions are available in the current state);
- **`scope:`** compiles to predicate algebra + RLS, so rows the user can't act on
  are **never rendered** (concealment inferred from the predicate).

## The 13 criteria

Revised from the 11-criterion starting set for how Dazzle actually models
surfaces/displays/visibility (see "Revisions", below).

### Data drives the UI — choose the *form*
- **1a — region form inference.** Does a **workspace region** infer its form from
  the source data shape (temporal → timeline/trend, ordered-state → board,
  grouped quantity → chart), or default to a list? *Entity `mode:` surfaces are
  exempt — a list/detail CRUD surface is correctly tabular (R1).*
- **1b — semantic-state binding.** Is a status/enum → colour/icon mapping
  **declared on the field and validated** against a semantic role, or derived
  from a name→theme convention? (R3: Dazzle has a validated palette
  `positive/warning/destructive`; the gap was *binding* it by declaration vs the
  `_STATUS_TONE_MAP` name fallback.) **#1493 closed the binding+consumption: a
  `semantic:` line on a shared `enum`/inline `enum[...]` field declares each
  value's tone, validated against the palette, and `resolve_status_tone` now
  consults it before the name guess on the list/table badge path (level 3). The
  remaining level-4 step is WCAG colour+icon+text on every badge surface +
  state-machine-terminal inference for undeclared values.**
- **1c — comparison context.** Are lone scalars avoided — is a number shown with
  trend / rank / distribution / outlier by default?
- **1d — raw-data honesty.** Are UUID / FK / ISO / float / JSON / bool
  unrenderable raw by default (resolved / rounded / humanised)?

### Progressive disclosure — choose the *amount*
- **2a — answer-first landing.** Does the persona land on a workspace that leads
  with the answer/anomaly, not raw CRUD?
- **2b — depth in ≤1 action.** Is detail one cheap click away (auto-drill list →
  detail), not hunted?
- **2c — action-proximate detail.** Is row-peek / inline-expand declarative and
  **on by default** where it helps (not a hand-set flag)?
- **2d — field economy.** Is column priority / hidden-by-default the **default**,
  so a wide entity doesn't dump every column?

### Negative space — choose *whether*
- **3a — frequency-weighted prominence.** Do rare actions default to overflow and
  common actions to primary, derived from usage/frequency, not hand-placed?
- **3b — role-gated affordance.** Is an affordance's visibility gated by **role**,
  declaratively and provably (not rendered-then-403)?
- **3c — state-gated affordance.** Is it gated by **entity state** (an action
  absent when the state graph doesn't allow it, not disabled-then-blocked)?
- **3d — empty-state suppression.** Does an empty region **self-demote** (collapse
  / hide), or render dead scaffolding?
- **3e — scope concealment.** Are rows the user has no scope for **never
  rendered** (concealment by construction), not filtered client-side?

## Evidence + attribution (what makes it rigorous)

Score each criterion with **two kinds of evidence that must agree**:

- **Capability (static).** Inspect the DSL grammar + renderer: does the primitive
  exist, and what's the **default with zero author effort**? Default-wrong = 2;
  default-right = 3; only-via-escape-hatch = 1; inferred = 4. *This is the
  primary, CI-able framework score — it needs no running app.* (`dazzle ux
  maturity`.)
- **Rendered (dynamic).** Drive a real app in a browser and confirm the live UI
  exhibits it. *For attribution + drift only — it confirms the default actually
  renders and catches "capability says 3, real screen shows 2".* (the
  `/ux-maturity` agent command, reusing the `/ux-pass` walk.)

**Attribution rule (bridges instance → framework).** A failing screen is an
**authoring gap** if the right-by-default primitive existed and wasn't used; it's
a **framework gap** if it fails *despite* the author (missing / escape-hatch /
wrong-default). **Promote to the framework backlog only on repetition under
effort** — many screens failing the same criterion, several via custom renderers.
One screen is authoring; a *pattern* is the framework.

**Clumsiness flags → criterion map.** The rendered pass records per-screen flags
(from the `/ux-pass` vocabulary); a *pattern* of a flag attributes to a framework
criterion:

| Flag (rendered evidence) | Pattern attributes to |
|---|---|
| `raw_data` (UUID/FK/float shown raw) | 1d |
| `empty_on_path` (card empty though data exists) | 3d (+ scope/data-path bug) |
| `hunt` / `nav_only` (no in-context entry; fell back to nav) | 2a, 3a |
| `long_chain` (over action budget for a basic need) | 2a, 2b |
| `deadend` (looked right → 403/empty) | 3b, 3c (affordance shown when not applicable) |
| dense-table-scanned-for-outliers | 1a, 1c |

## Output schema

`dazzle ux maturity --json` (and the rendered pass) emit:

```json
{
  "framework_version": "0.87.11",
  "overall_index": 2.6,
  "rag": "amber",
  "principles": {
    "data_drives_ui":        { "index": 2.25, "criteria": ["1a", "1b", "1c", "1d"] },
    "progressive_disclosure": { "index": 2.5, "criteria": ["2a", "2b", "2c", "2d"] },
    "negative_space":        { "index": 3.0, "criteria": ["3a", "3b", "3c", "3d", "3e"] }
  },
  "criteria": {
    "1a": {
      "principle": "data_drives_ui",
      "name": "region form inference",
      "capability": 3,
      "rendered": null,
      "rag": "green",
      "evidence": "`display: auto` is the default for an unset `display:` (#1492); the form is inferred from the data shape",
      "attribution": null
    }
  },
  "framework_backlog": [
    {
      "criterion": "1b",
      "leverage": "high",
      "gap": "status->tone is a name convention (`_STATUS_TONE_MAP`), not a declared+validated binding",
      "evidence": ["_STATUS_TONE_MAP name fallback", "..."],
      "since_version": "0.87.11"
    }
  ]
}
```

The backlog is **keyed to `framework_version`**: a criterion dropping (e.g. 3 → 2)
between versions is an attributable **regression**; a criterion rising is the
primitive work landing. A drift gate keeps the declared capability levels honest —
a probe that contradicts its declared level fails CI.

## Turning the scorecard into work

Every criterion implies primitive work — see the
[UX-maturity primitive roadmap](../architecture/ux-maturity-primitive-roadmap.md)
(each criterion → its target primitive + how to build it, including which ones
htmx 4 now expresses directly so they're declarative wrappers, not custom JS).

## Discovery + distribution

One source, every Dazzle app, via Dazzle's existing agent-command channel:

- **`dazzle ux maturity`** — the static capability scan, shipped in the wheel.
  Deterministic, CI-gateable; emits the schema above. The spine.
- **`/ux-maturity`** — an agent-command definition
  (`services/agent_commands/definitions/ux_maturity.toml`) that runs `dazzle ux
  maturity` (static) then drives the app (rendered + attribution + roll-up).
  `dazzle agent sync` distributes it — and the CLAUDE.md / AGENTS.md pointers — to
  **every** consuming app.
- **`docs/reference/ux-maturity.md`** — this doc (the framework-neutral rubric).

## Revisions from the 11-criterion starting set

- **R1 — 1a scoped to regions, not entity surfaces.** A `mode: list` surface being
  tabular is correct (CRUD); penalising it is a false negative. Form-inference
  applies to workspace *regions*.
- **R2 — 3b split into role (3b) and state (3c).** Dazzle is strong on both via
  different mechanisms (provable RBAC matrix; state machine). One conflated
  criterion hid both a strength and a real "adaptive" example.
- **R3 — 1b reframed as *binding*, not *palette*.** Dazzle has a validated
  semantic palette already; the gap is declaring the status→tone binding on the
  field vs the name-convention fallback.
- **R4 — added 3e (scope concealment).** `scope:` → predicate algebra + RLS means
  unactionable rows are never rendered — negative-space by construction. Crediting
  it makes the rubric a fair scorecard, not a gap-list.
- **R5 — anchored level-4 to existing behaviour** (display→`GROUP BY`,
  transitions-from-state-graph, scope→RLS) so scorers calibrate "adaptive" against
  what already ships.

## How the AegisMark prototype relates

This rubric is the framework-altitude abstraction over AegisMark's
instance-level UX work: `strategy.md` (the "answer the question" synthesis →
"grow ~6 native primitives"), `target.md` / `scorecard.json` / `verdicts.json`
(the `/ux-pass` story walk), `ssr-htmx-ux-doctrine.md` (the SSR+htmx substrate
doctrine + operating rules). Those judge *AegisMark*; this judges *Dazzle*. Most
of the 6 primitives `strategy.md` called for have since shipped (#1470 comparison
/ outlier / heatmap / insight_summary, the format layer, sparkline/timeseries) —
so this rubric's job today is to **re-score and repoint at what's left**, which
is why the gaps now sit at *default + inference* (level 2) rather than *absent*
(level 0).
