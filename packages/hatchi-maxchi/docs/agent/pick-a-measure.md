# Playbook: pick a content measure

**Goal:** Choose the app-shell **content measure** (how wide the product sits
on the stage) for a surface — not which Hyperpart, but how much viewport the
shell claims.

**Open when:** Authoring a list, form, detail, board, or dashboard page; an
agent asks “full width or card?”; fleet/humanqa flags pinching or sprawl.

**Do not open:** Picking a control (use `pick-a-surface.md`); inventing a new
layout primitive before exhausting these four tokens.

## Contract (design system)

| Token | DOM | Shell max-width (approx) | Stage (grey) |
|-------|-----|--------------------------|--------------|
| **`app`** | `data-dz-measure="app"` | `min(100%, 96rem)` soft ultrawide cap | Thin margins only on huge displays |
| **`product`** | `data-dz-measure="product"` | ~48rem content + sidebar | Clear card vs stage |
| **`wide`** | `data-dz-measure="wide"` | ~56rem content + sidebar | Intermediate |
| **`full`** | *(attribute omitted)* | unconstrained (100%) | No shell card edge |

CSS tokens (overridable on `:root` / theme):

- `--dz-content-measure` (product)
- `--dz-content-measure-wide`
- `--dz-content-measure-app`

**Center** (prose column primitive) is separate: `data-measure="prose|wide|full"`
on `.dz-center` for **in-page** reading width, not the whole app shell.

## Defaults (when author omits `ux.measure`)

| Surface mode | Default measure | Why |
|--------------|-----------------|-----|
| **list** (table / grid / board) | **`app`** | Tabular scan needs horizontal room |
| **create** / **edit** (forms) | **`product`** | Line length + focus for entry |
| **view** (detail) | **`product`** | Readable field stack; not a spreadsheet |
| Marketing / legal (sitespec) | prose / center | Not app-shell measure |

Inference also lives in `dazzle.render.dispatch` when `PageContext.table` /
`.form` / `.detail` is set.

## Author override (DSL)

```dsl
surface task_list for Task:
  mode: list
  ux:
    purpose: "Scan and open work"
    measure: app          # optional — list already defaults to app
    show: title, status, priority, due_date

surface task_create for Task:
  mode: create
  ux:
    purpose: "Capture a new task"
    measure: product      # optional — form default
```

Valid values: `app` | `product` | `wide` | `full`.

## Rubric (pick in order)

Answer **one sentence** for the primary job, then the first matching row:

| # | If the primary job is… | Choose | Do not choose |
|---|------------------------|--------|---------------|
| 1 | Scan / sort / filter **many columns** or a **board** | **`app`** | product (pinches tables) |
| 2 | Enter or edit **a single record** (wizard or long form) | **`product`** | app (lost focus, long lines) |
| 3 | **Read a record** (detail stack, related groups, few columns) | **`product`** (or **`wide`** if many related tables) | full without reason |
| 4 | **Ops dashboard** / multi-widget canvas that must use the monitor | **`app`** or **`full`** | product |
| 5 | **Prose** (policy, help, marketing body) | sitespec **center** `prose` / `wide` | app-shell product by accident |
| 6 | Author is unsure | Prefer **mode default** (list→app, form→product) | Invent a fifth token |

### Secondary checks

- **Ultrawide (≫1600px):** `app` still soft-caps; use `full` only if empty side
  gutters are *worse* than infinite row stretch.
- **Public kayfabe board** (anon list): still **`app`** — it is a work surface,
  not an article.
- **Settings / account:** **`product`**.
- **Do not** set measure per-column or per-region; it is **page/shell** chrome.

## Agent decision sketch

```
primary job?
  many columns / list / board     → measure: app   (or omit; list default)
  form entry / settings           → measure: product
  detail read                     → measure: product  (wide if dense related)
  dashboard fills the monitor     → measure: app | full
  long-form reading               → center prose (not shell measure)
```

## Stop conditions

- You are about to hard-code a pixel width on a table — stop; pick a measure.
- You want “a bit wider than product but not full” — use **`wide`**, do not invent `semi`.
- Two surfaces share a workspace but different jobs — set measure **per surface**, not once for the app.
- Changing CSS tokens for one customer app without a theme hook — prefer `ux.measure` first.

## Related

- Shell CSS: `packages/hatchi-maxchi/components/app-shell.css`
- Dispatch inference: `dazzle.render.dispatch`
- Control pick matrix: `docs/agent/pick-a-surface.md`
- Center (in-page measure): `site/agents/center.md`
