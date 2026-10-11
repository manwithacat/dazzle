# Hyperpart emitters & scenario cognition — design

**Date:** 2026-08-07
**Status:** accepted direction (conversation); implementation phased
**Audience:** framework-ux, hm-convergence, example-apps /improve agents
**Question:** What does a DSL emitter look like? One emitter per hyperpart, or many?
What supports agent cognition and productive code generation?
**Related:**
- `docs/reference/hyperpart-presentation.md` (role × host → density; one `present()` seam)
- `packages/hatchi-maxchi/docs/agent/pick-a-surface.md` (control jobs)
- `packages/hatchi-maxchi/docs/agent/pick-a-work-surface.md` + `work_surface_utility.toml`
- `src/dazzle/qa/hyperpart_opportunity.py` (static opportunity scan)
- `tests/unit/test_hyperpart_fleet_coverage.py` (adoption ratchet; `KNOWN_GAPS`)
- `docs/superpowers/specs/2026-07-04-hyperpart-library-expansion-design.md`

---

## 1. Diagnosis (why residual is quiet)

| Layer | State today | Agent effect |
|-------|-------------|--------------|
| Fleet coverage | `KNOWN_GAPS = ∅` | No “part exists but no example mounts it” residual |
| Opportunity scan | Avatar + queue-name heuristic only | Flood of `emit_covered` avatar rows; rare `author_action` |
| Presentation residual | 0 | Still OCR immune system green on audited hosts |
| Gallery-only parts | ~24 `exempt: no Dazzle emitter yet` | Examples **cannot** adopt; improve correctly skips |
| Goal B / interesting_product | Ships depth on **already-wired** surfaces | Product quality, not new-hyperpart dogfood |

**Conclusion:** Progress is real on product honesty; the *new-hyperpart → example* funnel is empty because the bottleneck is **authoring path** (emitter + scenario ontology), not example laziness.

---

## 2. Vocabulary (do not collapse)

Agents thrash when these four words are treated as synonyms.

| Term | Meaning | One-liner |
|------|---------|-----------|
| **Hyperpart** | HM L1/L2 contract: DOM spine, CSS, optional controller, gallery demo | *What mounts* |
| **Job / recipe** | Operator intent in plain language (`single-select-form`, work-queue urgency, …) | *Why mount* |
| **Authoring surface (DSL emitter)** | Stable verb an author/agent writes so Dazzle *chooses* that hyperpart | *How intent is spelled* |
| **Runtime emit path** | Code that produces HTML (`present()`, region renderer, form widget, always-chrome) | *How HTML is born* |

```
  job / recipe  ──pick──►  hyperpart
       │                      ▲
       │                      │ mounts
       ▼                      │
  authoring surface  ──►  runtime emit path  ──►  HTML
  (DSL / default)         (framework)
```

Presentation doctrine already enforces **one runtime emit seam** for cell density
(`present()`). That is orthogonal to how many **authoring surfaces** can reach a part.

---

## 3. What a DSL emitter looks like (shapes that already work)

Not every hyperpart wants a new `display:` token. Match **shape to lifetime + exchange**.

| Authoring class | Emitter shape | When | Examples that work today |
|-----------------|---------------|------|---------------------------|
| **A. Default emit** | *No DSL* — type/role heuristics | Always-right for semantic roles | person ref → Avatar; money → currency; status enum → badge |
| **B. Region verb** | `display: <mode>` on workspace region | Whole region *is* the hyperpart job | `queue`, `kanban`, `status_list`, `activity_feed` |
| **C. Form widget** | `widget=<name>` on a field | Field lifetime, form POST | `combobox`, `tags`, `slider` |
| **D. Field type / source** | type or `source=pack.op` | Domain type carries UI | `money`, dotted `source` → search-select |
| **E. Surface mode / peek** | `mode:`, `peek: slide_over` | Page protocol, not cell chrome | drawer, create/edit sections |
| **F. Always chrome** | sitespec / shell; no per-app verb | Ubiquitous chrome | command palette, toast, toolbar overflow menu |
| **G. Auto chooser** | `display: auto` / unset | Data-shape inference | aggregate → bar_chart/summary; state machine → kanban |

### Minimal emitter package (when shipping a *new* path)

For an opt-in class B/C part, ship **together** (agents need the full loop):

1. **IR + parser** — DisplayMode or widget token; refuse unknown with a good error.
2. **Runtime path** — one fragment primitive + region/form wiring that mounts the HM spine.
3. **Agent playbook row** — `pick-a-surface` or `pick-a-work-surface` Use / Do-not-use.
4. **Scenario signals** — `use_when` / `dsl_hints` / domain heuristics for the opportunity scanner.
5. **Fleet signal** — SIGNALS entry (regex or structural); drop `exempt`; `KNOWN_GAPS` until one example adopts.
6. **Example home** — one dogfood surface + still/unit pin.
7. **Gallery probe** (if interactive) — already required on HM side.

An emitter without (3)+(4) is invisible to agents. A gallery part without (1)+(2) is undogfoodable.

---

## 4. One emitter per hyperpart — or many?

### Thesis (agent cognition)

> **One canonical authoring surface per *job that should mount this hyperpart*.**
> **Not** “exactly one Python function and exactly one DSL token for all eternity.”
> **Not** “N freeform DSL synonyms that all spit the same HTML.”

Productive generation wants:

1. **Closed choice** when the job is named (pick matrix → one Use column).
2. **Zero choice** when the framework should always do the right thing (default emit).
3. **Honest refusal** when two jobs share a *visual shape* but not a protocol (combobox vs grid cell select).

### When **one** authoring surface is right

| Pattern | Why agents win |
|---------|----------------|
| Region hyperparts: `display: queue` → queue | One verb, one job, one residual close |
| Opt-in widgets: `widget=combobox` | Field-scoped; discoverable in form authoring |
| Progressive build: first emitter for an exempt part | Shrinks search space; fleet ratchet works |

**Progressive “one emitter per remaining hyperpart”** is a good *delivery order*, not a permanent ontology. Ship the first path that unlocks dogfood; add a second only when a *different job* appears.

### When **multiple paths** to the same hyperpart are right

| Multiplicity | Example | Why |
|--------------|---------|-----|
| Default emit + optional opt-out | Avatar from person ref; `avatar: false` | Agents must not litter DSL to get the default |
| Same part, different hosts (runtime only) | Avatar on `list_cell` vs `queue_meta` densities | Host belongs in presentation matrix, **not** second DSL verbs |
| Composition guest | Badge inside queue row meta | Parent region is the authoring unit; guest is role emit |
| Chart family sharing chrome | `line_chart` / `area_chart` → related time-series | Different **measure jobs**, shared visual family — keep distinct verbs if jobs differ |

### When multiple paths are **wrong** (harms cognition)

| Anti-pattern | Failure mode |
|--------------|--------------|
| Density as DSL (`display: avatar_only` vs `avatar_name`) | Agents invent polish modes; matrix is bypassed |
| Synonym verbs (`display: work_queue` ≈ `queue`) | Residual/scanner double-count; pick matrix forks |
| One mega-part with `data-mode=menu\|menubar\|nav` | Collapses distinct jobs (forbidden by pick-a-surface) |
| Second emitter that only differs by CSS class | One-app hacks; stills diverge from gallery contract |

### Same *shape*, different hyperpart (keep separate emitters)

Doctrine already settled (do not reverse):

```
actions from a button  → menu
free content under trigger → popover
File/Edit app chrome → menubar
product top nav → navigation-menu
left rail → app-shell sidebar
```

**Argument for different DSL emitters that map to the *same* hyperpart** only holds when:

- the **job/lifetime/exchange** still match that hyperpart’s contract, and
- agents would otherwise reimplement the part with local HTML.

**Argument for different hyperparts (and emitters)** holds when jobs differ even if screenshots rhyme.

### Practical rule of thumb

```
Ask: is the agent choosing a JOB or a DENSITY?

JOB → one authoring surface (or default emit) per job recipe
DENSITY → present() / matrix host, never a new display: verb
SHAPE without job change → refuse second emitter; fix the first path
SHAPE with job change → different hyperpart (and emitter), not modes on one part
```

---

## 5. Scenario cognition (proactive identification)

Today’s scanner answers a narrow question (“person refs + queue-ish names”).
We need a **scenario catalogue**: given domain + surface signals, recommend hyperparts.

### Scenario row schema (v1)

```toml
[[scenario]]
id = "person_ref_cell"
hyperpart = "avatar"
authoring = "default_emit"          # default_emit | display | widget | type | chrome
status_if_fit = "emit_covered"      # or author_action if product must opt in
use_when = ["field is ref to person-like entity on list/detail/queue host"]
refuse_when = ["form create/edit field", "metrics_tile host"]
example_homes = ["support_tickets.Ticket.assigned_to"]
residual_id = "person_as_text"      # optional product_quality / OCR residual
```

```toml
[[scenario]]
id = "shared_urgency_pool"
hyperpart = "queue"
authoring = "display:queue"
status_if_fit = "author_action"
use_when = [
  "region name/title matches work-pool heuristics",
  "entity is claimable work with priority/SLA",
]
refuse_when = ["already display in {queue,kanban,task_inbox}"]
example_homes = ["support_tickets.ticket_queue.open_queue"]
```

```toml
[[scenario]]
id = "boolean_settings_toggle"
hyperpart = "switch"
authoring = "widget=switch"         # first emitter to ship
status_if_fit = "author_action"
use_when = [
  "boolean field on settings/preferences surface",
  "immediate on/off semantics (not multi-option)",
]
refuse_when = ["checkbox group of many flags (prefer controls)", "toolbar filter"]
example_homes = ["hr_records settings", "ops_dashboard alert mute"]
```

Extend `hyperpart_opportunity` (and MCP `presentation` / future `hyperpart_scenarios`)
to load this catalogue — not hard-code only avatar/queue.

### Residual / improve stimulation

| Signal | When it fires | Lane force |
|--------|---------------|------------|
| `author_action` opportunity rows with `auto_seed` | Scenario fit, wrong/missing authoring | example-apps (DSL) |
| `matrix_miss` / presentation residual | Role×host density wrong | framework-ux hyperpart_presentation |
| Fleet `KNOWN_GAPS` non-empty | Emitter exists; no example mounts | example-apps adopt once |
| `exempt` with scenario fit | Domain wants part; no emitter | framework-ux **emit first** (not example thrash) |
| `scenario_underused` (future) | Emitter exists, few apps, high scenario score | example-apps interesting_product / depth |

**Key stimulation rule:** never ask example-apps to adopt an exempt gallery part.
Force **framework-ux emitter package** first; then fleet gap; then one example home.

### How agents are stimulated to *use* emitters

1. **Closed pick matrices** (already strong for controls + work surfaces) — expand rows when emitters ship.
2. **Scenario residual > 0** in `improve_example_probes` / product_quality when `author_action` count > 0.
3. **Good parser errors** — “unknown display: carousel — did you mean …? gallery-only until widget/display lands.”
4. **Dig contracts** — map citation must name scenario id + Use column, not “looked at gallery.”
5. **Default emit** for high-confidence roles — the best stimulation is *no authoring required*.

---

## 6. Progressive emitter backlog (exempt inventory)

Priority = (scenario frequency in example fleet) × (gallery readiness) × (job clarity).

### Batch E1 — form widgets (class C) — highest agent leverage

| Hyperpart | First emitter | Scenario | First example home (candidate) |
|-----------|---------------|----------|--------------------------------|
| `switch` | `widget=switch` on boolean field | settings on/off | hr_records / ops preferences |
| `toggle-group` | `widget=toggle_group` closed enum (2–5) | view density / severity filter as field | support_tickets filters or design_studio |
| `accordion` | sectioned form disclosure **or** `display` companion | long create forms with optional blocks | invoice_ops / contact_manager engagement |

Ship one widget fully (IR → render → pick-a-surface row → scenario → one example) before the next.

### Batch E2 — conversation / media regions (class B)

| Hyperpart | First emitter | Scenario | Home |
|-----------|---------------|----------|------|
| `message-scroller` + `message` + `bubble` | **one** region mode e.g. `display: conversation` that **composes** all three | live thread / ticket comments | support_tickets (already has conversation Goal B — upgrade mount) |
| `carousel` | media region or asset field gallery | multi-image brand asset | design_studio Asset |

**Multiplicity note:** do **not** ship three independent `display: message|bubble|scroller` verbs first.
Ship **one job verb** that composes the three L1s (matches CONSUMER_MAP / composition doctrine).

### Batch E3 — chrome (class F / optional shell)

| Hyperpart | Emitter stance | Note |
|-----------|----------------|------|
| `kbd`, `separator` | default/chrome only | No DSL; document in pick matrix as chrome |
| `tooltip`, `popover` | host-local attrs / rare widget | Prefer composition guests over region verbs |
| `breadcrumb` | shell/sitespec trail | One app shell path, not per-region display |
| `menubar`, `navigation-menu` | shell chrome | Only if Dazzle sitespec grows top-nav products |
| `alert` | map to form-chrome / toast honestly | May stay non-emit if contracts differ |

### Batch E4 — layout / anatomy (often never DSL)

| Hyperpart | Stance |
|-----------|--------|
| `center`, `item`, `aspect-ratio` | Fragment/layout only; blueprint/composition — skip DSL unless a real job appears |
| `master-detail` | Needs Dazzle mode/blueprint bridge; large; keep exempt until dual-pane story is productized |
| `progress` (determinate bar) | Distinct from `display: progress` StageBar — name carefully before emitter |
| `code` | Agent-pack / gallery; optional docs surface only |
| `marker` | Pair with map region when map job is dogfooded |

---

## 7. Implementation phases

### Phase 0 — cognition artifacts (this doc + catalogue seed)

- [x] Doctrine: emitter classes; one-job-one-surface; density ≠ DSL
- [x] Seed `packages/hatchi-maxchi/docs/agent/hyperpart_scenarios.toml` with rows for avatar, queue, money, badge, switch, conversation, carousel, toggle-group
- [x] Wire `scan_appspec` → scenario scanners (`planned_emitter` for switch) + catalogue snapshot on report (`schema_version` 3)
- [x] Unit pins in `tests/unit/test_qa/test_hyperpart_opportunity.py`

### Phase 1 — residual that forces the right lane

- [x] Report `residual.force_lane` (`framework-ux` if planned_emitter only; `example-apps` if author_action)
- [x] `hyperpart_scenarios` line in `scripts/improve_example_probes.py` (planned → residual + `force=framework-ux hyperpart_emitter`)
- [x] When scenario fit + hyperpart still planned → **framework-ux** (not auto_seed example densify)
- [x] When emitter green + fleet signal covered → example dogfood pin (simple_task)

### Phase 2 — first new emitter end-to-end (prove the package)

**Shipped 2026-08-07: `widget=switch`.**

Acceptance:

1. [x] Form field with `widget=switch` mounts HM switch spine (`data-dz-switch` + track).
2. [x] pick-a-surface row: boolean settings → switch.
3. [x] Scenario: emit_covered when widget present; author_action on formish bools without it.
4. [x] simple_task `user_edit` / `is_active`; fleet SIGNALS switch covered; KNOWN_GAPS empty.
5. [x] Unit pins: `test_form_widget_showcase_phase3`, `test_simple_task_switch_emitter`.
6. [x] Playbook: `improve/strategies/hyperpart_emitter.md`.

### Phase 3 — conversation composition emitter

- One `display: conversation` (name bikeshed OK) composing message-scroller/message/bubble.
- support_tickets conversation Goal B becomes the dogfood home (upgrade mount, not parallel UI).

### Phase 4 — expand catalogue + improve policy

- Campaign rotation may force `framework-ux hyperpart_emitter` when exempt+scenario > 0.
- Capability-sweep lists underused authoring verbs quarterly.

---

## 8. Answers (compressed)

### What do DSL emitters look like?

Typed **authoring classes** (default emit, `display:`, `widget=`, field type, shell chrome, auto), each with IR, runtime path, pick-matrix row, scenario signals, and fleet signal — not “a function named emit_X.”

### How do we stimulate agents to use them?

Closed pick matrices + scenario residuals that auto-seed the correct lane + default emit for high-confidence roles + fleet gaps after emitters land. Gallery alone does not stimulate product DSL.

### One and only one emitter per hyperpart?

**As a build queue: yes, ship one first path per remaining part.**
**As ontology: no — one authoring surface per *job*; default emit and host densities are not extra emitters; distinct jobs keep distinct hyperparts even when shapes rhyme.**

### Multiple DSL emitters → same hyperpart?

**Yes when jobs/lifetimes share the contract and agents would otherwise fork HTML.**
**No when the difference is density, synonym naming, or a different protocol wearing the same clothes.**

---

## 9. Non-goals

- Porting every shadcn name into `display:` space.
- Scoring human “beauty”; residuals stay machine-checkable.
- Requiring authors to name hyperparts in DSL for default-emit roles.
- Collapsing menu/menubar/navigation-menu into one emitter with modes.

---

## 10. Next concrete PR (suggested)

1. Add `hyperpart_scenarios.toml` seed (avatar, queue, money, badge, switch-planned).
2. Load in `hyperpart_opportunity.scan_appspec`; report `by_scenario` + keep CLI table.
3. Expose `author_action` count on probe status line.
4. Open framework issue / backlog row for **switch emitter package** (Phase 2).

No example densify while residual presentation/scenario is green and switch is still exempt.
