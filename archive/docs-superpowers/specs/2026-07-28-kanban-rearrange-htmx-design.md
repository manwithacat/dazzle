# Kanban rearrange — Linear-class UX on HTMX/HM

**Status:** active implementation
**Date:** 2026-07-28
**Stem anchors:** `stems/hypermedia-ssr.md`, `packages/hatchi-maxchi/stems/morph-safe-hypermedia.md`, `stems/rbac-and-scope.md`

## Exemplar

**Primary product exemplar: Linear’s Project / Issue board.**

Linear is the best match for Dazzle’s domain: columns are **workflow states**,
moving a card is a **constrained status transition**, chrome is **permission-
aware**, cards remain **openable**, and the interaction is **fast but
server-authoritative**. Trello supplies the **gesture grammar** (drag, drop
zone, ghost, column counts) but not the free-for-all mutation model.

### Requirements extracted from Linear board UX

| # | Requirement | SPA technique | HTMX / HM recontextualisation |
|---|-------------|---------------|--------------------------------|
| R1 | Columns = declared workflow states | Client columns from issue status enum | SSR columns from SM states / enum (`compute_kanban_columns`) |
| R2 | Drag between columns = status change | Optimistic client store + API patch | Thin controller: validate drop → `PUT /api/{plural}/{id}` with status field → **GET-refresh** board region (`innerMorph` / region outerHTML) |
| R3 | Illegal edges not offered | Disable targets in DnD graph | Per-card `data-dz-allowed-to` from manual SM edges only; drop rejected client-side; server re-validates |
| R4 | Read-only personas: no rearrange | Hide drag handles from ACL | SSR gate: no rearrange attrs when UPDATE denied (queue chrome class, `gate_kanban_rearrange_for_principal`) |
| R5 | Card still opens for detail | Click vs drag threshold | Title hub drill (`data-dz-kanban-drill`); drag from card body / handle with movement threshold |
| R6 | Keyboard parity | `Cmd+Shift+…` move | Native `<select data-dz-kanban-move>` per card (same allowed set); no drag-only path |
| R7 | Counts update after move | Local count mutation | Server re-render of full board (column counts in markup) |
| R8 | Stable identity under morph | React keys = issue id | `id="dz-kanban-card-{id}"` + `data-dz-entity-id` |
| R9 | Fail closed on write | API 403/422 | Existing entity UPDATE + `validate_status_update`; guards still server-side |
| R10 | No second permission plane | Session ACL store | Reuse `_principal_can_op(UPDATE)` + scope (cards already scope-filtered) |

### Explicit non-goals (v1)

- Within-column rank / priority without a declared rank field
- Multi-select drag / bulk status via board
- Realtime multiplayer cursors
- Optimistic permanent layout without server settle
- Dashboard personal-layout drag (`card_drag` / dashboard-builder)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ SSR (permit + SM)                                           │
│  gate_kanban_rearrange → rearrange=none|status              │
│  per card: row_id, from_state, allowed_to[]                 │
└───────────────────────────┬─────────────────────────────────┘
                            │ dual-lock markup
┌───────────────────────────▼─────────────────────────────────┐
│ DOM contract                                                │
│  [data-dz-kanban-board][data-dz-kanban-rearrange=status]    │
│  [data-dz-kanban-card][data-dz-entity-id][data-dz-allowed-to]│
│  [data-dz-kanban-stack][data-dz-to-state]                   │
│  [data-dz-kanban-move] keyboard control                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ pointer / change
┌───────────────────────────▼─────────────────────────────────┐
│ dz-kanban.js (delegated)                                    │
│  1. drop/change → legal?                                    │
│  2. PUT api/{id}  {status_field: to_state}                  │
│  3. GET data-dz-kanban-src → morph closest [data-dz-region] │
└─────────────────────────────────────────────────────────────┘
```

### Why PUT-then-GET (not “PUT returns board HTML”)

Entity `PUT` already returns the **JSON model** + `HX-Redirect` /
`HX-Trigger` for toast/settle (queue buttons rely on redirect today). The
grid’s bulk-refresh pattern is cleaner for a board: mutation endpoint stays
CRUD; the **region endpoint** remains the sole owner of board HTML
(swap-identity stem).

## Contract surface

### Board root

| Attr | When |
|------|------|
| `data-dz-kanban-board` | always (region root) |
| `data-dz-kanban-rearrange="status"` | principal may UPDATE **and** group_by is SM status or free enum |
| `data-dz-kanban-status-field` | rearrange on |
| `data-dz-kanban-api` | API plural base, e.g. `/api/tasks` |
| `data-dz-kanban-src` | region refresh URL (host endpoint) |

### Card

| Attr | When |
|------|------|
| `data-dz-kanban-card` | always (dual-lock unit) |
| `data-dz-entity-id` | rearrange on + known id |
| `data-dz-from-state` | rearrange on |
| `data-dz-allowed-to` | space-separated legal targets (may be empty → no drag) |
| `draggable="true"` | allowed_to non-empty |
| `id="dz-kanban-card-{id}"` | stable morph key |

### Column stack

| Attr | When |
|------|------|
| `data-dz-kanban-stack` | always |
| `data-dz-to-state="{column}"` | rearrange on |

## Security

1. Chrome: pure-role UPDATE gate (field-conditioned rules leave chrome; write fails closed) — same class as `gate_queue_transitions_for_principal`.
2. Graph: only **manual** SM transitions from current state (AUTO edges never targets).
3. Write: existing UPDATE route + SM validation + scope pre-read.
4. Client `allowed_to` is a **hint**, never authority.

## Phases

| Phase | Deliverable |
|-------|-------------|
| **A** | Contract + SSR attrs + permit gate (this change) |
| **B** | `dz-kanban.js` + CSS + PUT-then-GET |
| **C** | Gallery mock exchange + agent docs |
| **D** | Walks / browser e2e / persona stills |

## Acceptance

- Mutator persona: cards with legal edges are draggable; drop moves status; board morphs with new column counts.
- Auditor / read-only: zero rearrange attrs; drills still work.
- Illegal edge: not in `allowed_to`; drop ignored; server 422 if forced.
- Keyboard Move control offers the same target set as drag.
- Dual-lock green; morph-safe region id ownership preserved.
