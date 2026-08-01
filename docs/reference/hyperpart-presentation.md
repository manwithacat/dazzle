# Hyperpart presentation process

**Audience:** `/improve` framework-ux + example-apps agents
**Doctrine source:** antagonist `HYPERPART_PRESENTATION_PROCESS` (2026-08-01)
**Stills:** `examples/*/.dazzle/qa/screenshots` — stills beat claims
**Related:** #1626 · `product-maturity.md` · HM pick-a-surface (authoring, orthogonal)

Closed **role × host → Hyperpart density** matrix with one emit seam
(`dazzle.render.presentation.present`). Authoring picks region *modes*
(queue vs kanban); this process picks cell *presentation*.

---

## Philosophy (non-negotiable)

1. **Stills beat claims** — no residual-only credit without recapture.
2. **Semantic role beats field label** — `Assigned To` is chrome; the value is `person`.
3. **Host is first-class** — same person → Avatar density varies by host.
4. **One emit seam** — host-local `str(person)` is a defect.
5. **Closed matrix** — no invention on the polish path; miss → plain + residual.
6. **Framework-wide** over one-app hacks.
7. **Floors / residuals**, not human composite scores in CI.
8. **Catalogue discovery ≠ product selection** — HM pick-a-surface is authoring; this is emit.

---

## Vocabulary

| Role | Signals |
|------|---------|
| `person` | ref → User/Person/Contact…; keys assignee/author/owner/… |
| `money` | money/currency types |
| `status` | lifecycle badge enums |
| `color` | color / hex |
| `datetime` | date/time |
| `plain` | fallback |

| Host | Examples |
|------|----------|
| `list_cell` / `detail_cell` | Entity list / detail |
| `queue_meta` | Queue row secondary meta strip |
| `kanban_field` / `card_meta` / `timeline_meta` | Board / card / timeline |
| `metrics_tile` | KPI tiles (person **refused**) |

Density variants: `avatar_only`, `avatar_name`, `badge`, `swatch`, `money`, `plain`, `refuse`.

---

## Matrix v1 (normative)

| Role | Host | Emit |
|------|------|------|
| person | list_cell, detail_cell | `avatar_name` (existing user_chip) |
| person | **queue_meta** | **`avatar_only`** — no visible `Assigned To:` prose |
| person | kanban_field, card_meta, timeline_meta | `avatar_name` |
| person | metrics_tile | refuse |
| money | queue_meta / list / detail | money format (R1 fold currency) |
| status | list-like | badge |
| color | list-like | swatch (R5) |
| datetime | queue_meta | plain / relative |

Living code: `PRESENTATION_MATRIX` in `src/dazzle/render/presentation.py`.

### Queue meta person (product intent)

```text
[title]  [status badges]
[avatar SA]  ·  Created 2d ago
```

Not: `Assigned To: Support Agent · Created At: …`

---

## Agent loop (required order)

0. **Preflight** — `dazzle demo quality` / workspace health if recapturing
1. **OBSERVE** — hero still + `dazzle qa hyperpart-opportunities --app <app> --table`
2. **MAP** — field → role → hosts → current emit vs matrix
3. **SELECT** — matrix density only (or `matrix_miss` + plain)
4. **IMPLEMENT** — framework `present()` / matrix registration, not one-app CSS
5. **PROVE** — recapture; DOM has `.dz-avatar` on queue_meta; no `Assigned To: Name` prose
6. **RECORD** — matrix rows + still paths (no bake-off pass from residual alone)

---

## Residuals / opportunity statuses

| status | Meaning |
|--------|---------|
| `emit_covered` | Listed hosts use matrix hyperpart |
| `emit_partial` | Some hosts covered, some not |
| `author_action` | Product must change display mode / DSL |
| `matrix_miss` | No matrix row |

Suggested residual ids: `person_as_text`, `ref_as_repr`, `host_emit_skew`, `hyperpart_matrix_miss`, `person_in_metrics` (plus existing `label_glue`, `cta_add_double`).

**Machine residual (T2):** `product_quality` OCR-scans present hero stills (when
`tesseract` is available) for dict/UUID chrome (`ref_as_repr`) and queue pilot
`Assigned To:` prose (`person_as_text` on `ticket_queue_*`). Floors alone cannot
catch presentation honesty.

**Never** report full green for person refs while `queue_meta` still stringifies them.

---

## Relationship to other artefacts

| Artefact | Role |
|----------|------|
| HM pick-a-surface / work_surface_utility | Authoring region **mode** |
| `user_chip` + `present()` | Product **emit** |
| `qa hyperpart-opportunities` | Observe host coverage |
| `demo_fleet` / `product_quality` | Floors + **presentation residual** (OCR stills) |
| MCP `presentation` | cognition / opportunities / residual for agents |
| counter-prior `ref_as_repr` | KG inoculation vs dict/UUID chrome |
| Mid-dot R1 separators | Between segments; not a substitute for Avatar |

---

## Agent surfaces (find and apply)

Downstream Dazzle consumers and monorepo agents should **not** invent a second
presentation process. Use the published surfaces:

| Surface | How to find / invoke | What it answers |
|---------|----------------------|-----------------|
| Doctrine | `docs/reference/hyperpart-presentation.md` · KG doc page `hyperpart-presentation` | Rules + matrix |
| Improve strategy | `/improve framework-ux hyperpart_presentation` · playbook `improve/strategies/hyperpart_presentation.md` | OBSERVE→PROVE loop |
| Felt bar | CLI `dazzle demo quality` · MCP `product_quality(operation=score)` | residual_total + force path |
| Presentation tool | MCP `presentation(operation=cognition\|opportunities\|residual)` | Matrix honesty + still OCR residual |
| Opportunity scan | CLI `dazzle qa hyperpart-opportunities` · MCP `presentation(opportunities)` | Host emit coverage |
| Counter-prior | MCP `knowledge(operation=counter_prior, id=ref_as_repr)` | Wrong vs right shape |
| Recapture | `scripts/recapture_demo_fleet_1626.py --apps <app>` | Still proof after emit |

**Force routing:** when `product_quality` reports presentation residual, next force is
`framework-ux hyperpart_presentation` (framework emit fix). Use `example-apps
hyperpart_presentation` only for recapture/prove after emit is fixed.

**MCP + knowledge graph:** both support this goal. MCP exposes machine-checkable
ops for OBSERVE; the KG seeds the counter-prior + doc page so `knowledge` /
`graph` queries surface the doctrine without grepping the monorepo. Agents that
only have MCP (downstream apps) get the same ops as the monorepo improve loop.

---

## Prove (minimum stills)

| Still | Expect |
|-------|--------|
| `support_tickets/.../ticket_queue_agent_desktop_light.png` | Assignee as avatar/chip, not sole prose identity |
| `fieldtest_hub/.../issue_triage_*` | Person meta → chip if present |
| `simple_task` kanban | No regression |

CLI:

```bash
# From example app dir (cwd = examples/<app>):
dazzle qa hyperpart-opportunities --table
# JSON includes presentation_cognition (hosts audited vs matrix-only).
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps support_tickets
```

---

## Agent cognition (how to read the scan)

Opportunity reports are **schema_version 2** with `presentation_cognition`:

| Field | Meaning |
|-------|---------|
| `hosts_audited_by_scanner` | Static scan actually walks these hosts |
| `hosts_not_yet_audited` | Matrix rows exist; scan does not residual them yet |
| `hosts_wired_to_seam` | Emit calls `present()` or equivalent chip path |
| `person_rows_all_emit_covered` | True only for **audited** person rows |
| `caveat` | Do not treat all-green as fleet presentation done |
| `how_to_extend` | Legal creativity path for new matrix rows |

**Rule:** Open the hero still. Machine green + un-audited hosts → still read stills.

---

## Agent creativity (within the closed system)

Creativity is **not** inventing a fourth assignee widget.

| Allowed | Forbidden |
|---------|-----------|
| Map domain fields → roles; propose matrix row with still evidence | One-app HTML/CSS for person/money |
| Implement `present()` density + unit test + recapture | Second avatar class outside dual-lock |
| Extend scanner to a host once wired | Claiming `default_emit` / all-green while queue stringifies |
| Pick region **mode** via work_surface_utility | Bypassing matrix for “taste” |

Extension recipe (when stills show a gap):

1. Residual id `hyperpart_matrix_miss` (or host incompleteness note).
2. Add `PRESENTATION_MATRIX[(role, host)] = density`.
3. Implement density in `present()`.
4. Unit test + recapture hero still.
5. Optionally add host to `HOSTS_AUDITED_BY_SCANNER` when static residual exists.
