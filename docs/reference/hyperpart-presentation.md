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

Suggested residual ids: `person_as_text`, `host_emit_skew`, `hyperpart_matrix_miss`, `person_in_metrics` (plus existing `label_glue`, `cta_add_double`).

**Never** report full green for person refs while `queue_meta` still stringifies them.

---

## Relationship to other artefacts

| Artefact | Role |
|----------|------|
| HM pick-a-surface / work_surface_utility | Authoring region **mode** |
| `user_chip` + `present()` | Product **emit** |
| `qa hyperpart-opportunities` | Observe host coverage |
| `demo_fleet` / `product_quality` | Empty-hero floors; orthogonal to cell presentation |
| Mid-dot R1 separators | Between segments; not a substitute for Avatar |

---

## Prove (minimum stills)

| Still | Expect |
|-------|--------|
| `support_tickets/.../ticket_queue_agent_desktop_light.png` | Assignee as avatar/chip, not sole prose identity |
| `fieldtest_hub/.../issue_triage_*` | Person meta → chip if present |
| `simple_task` kanban | No regression |

CLI:

```bash
dazzle qa hyperpart-opportunities --app support_tickets --table
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps support_tickets
```
