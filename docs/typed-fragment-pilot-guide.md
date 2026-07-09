# Dazzle Typed-Fragment Pilot Guide

**Status:** Canonical guide for downstream consumers piloting the typed Fragment system.
**Last updated:** 2026-05-06 (v0.66.44)

This guide lives in the Dazzle repo so it tracks the framework's actual capabilities. When piloting the typed Fragment system on your own project, copy this file into your project and update the consumer-specific bits (paths, audit numbers, your project name).

---

!!! note "Status (2026-06-06): the migration is complete"
    When this guide was written, fragment and Jinja rendering cohabited during the
    flip. That migration is **done** — Jinja2 was fully retired in #1042 (v0.67.92)
    and is no longer a dependency ([ADR-0023](adr/0023-template-emission-patterns.md)).
    The typed Fragment substrate is the only rendering path; references below to a
    "legacy Jinja path" are migration-era context, not a path that still exists.

## What's being piloted

The Dazzle UI runtime has a **typed Fragment substrate** for HTML rendering — a frozen-dataclass primitive tree that replaces implicit Jinja-as-compiler templates. Surfaces declare `render: fragment` in DSL. (Historically, un-flipped surfaces stayed on a legacy Jinja path during the migration; that path no longer exists — see the status note above.)

**The substrate has 5 components you'll touch:**

1. **34 typed primitives** — `Surface`, `Region`, `Heading`, `Text`, `Table`, `FormStack`, `Field`, `Combobox`, `RefPicker`, etc. Each is a `@dataclass(frozen=True, slots=True)`.
2. **Fragment renderer** — match-dispatches over the primitive tree, emits HTML.
3. **`FragmentSurfaceAdapter`** — translates `SurfaceSpec` + render context into a primitive tree.
4. **`dazzle fragment-audit`** — CLI tool that walks any project and reports which surfaces the adapter can render and which are blocked (and why).
5. **`scripts/flip_to_fragment.py`** (in the dazzle repo) — idempotent helper that adds `render: fragment` to every flippable surface in a DSL file.

**The framework's own example apps are 78/78 honest coverage** (5 apps × ~16 surfaces each, all blockers closed).

**What's covered today (v0.66.44):**
- Modes: `list`, `view`, `create`, `edit`
- Field types: str, text, email, int, decimal, float, money, bool, date, datetime, url, enum, **ref** (typed RefPicker primitive), **uuid** (readonly text), **json** (textarea)
- Features: `related_groups`

**What's not yet covered:**
- Mode: `custom`
- Field type: `file`
- Surface features: `companions`, `search_fields`

---

## Prerequisite: DSL grammar update

Older Dazzle DSL uses `for:` for several persona-binding constructs. Dazzle PR #998 renamed them all to `as:` for grammatical disambiguation. **Three patterns** need renaming before the parser will accept the file:

| Pattern | Context | Parsed at |
|---|---|---|
| `<mode>: <expr>`<br>&nbsp;&nbsp;`for: <persona>` → `as: <persona>` | scope-rule persona binding | `dsl_parser_impl/__init__.py` (`_parse_construct_header`, expects `TokenType.AS`) |
| `for <persona>:` → `as <persona>:` | persona-variant block inside `ux:` and at surface level | `dsl_parser_impl/ux.py`, `dsl_parser_impl/surface.py` |
| `for persona <persona>:` → `as persona <persona>:` | per-persona scenario entry | `dsl_parser_impl/scenario.py` |

**Mechanical migration (run all three in this order):**

```bash
sed -i '' -E 's/^([[:space:]]+)for:/\1as:/'                dsl/app.dsl
sed -i '' -E 's/^([[:space:]]+)for ([a-z_]+):/\1as \2:/'    dsl/app.dsl
sed -i '' -E 's/^([[:space:]]+)for persona /\1as persona /' dsl/app.dsl
```

**As of v0.66.44** the parser raises an actionable error pointing at PR #998 with this sed snippet when an unmigrated `for` is encountered in a scenario body, so you won't get a misleading "Duplicate persona" linker error any more. (Earlier versions silently consumed the `for` token and re-dispatched the next token as a top-level construct.)

**Sanity check after the rename:**

```bash
cd /path/to/your/project
python -m dazzle validate            # parser must be clean
python -m dazzle fragment-audit .    # this is what the pilot exercises
```

**Audit JSON shape (so you know what to expect):**

```json
{
  "total": 225,
  "ready_count": 220,
  "blocked_count": 5,
  "surfaces": [
    {"name": "task_list", "mode": "LIST", "is_ready": true,
     "blockers": [], "source": "declared"},
    {"name": "_admin_health", "mode": "LIST", "is_ready": true,
     "blockers": [], "source": "framework_injected"},
    {"name": "document_create", "mode": "CREATE", "is_ready": false,
     "blockers": [{"kind": "unsupported_field_type", "detail": "file"}],
     "source": "declared"}
  ],
  "aggregated_blockers": [
    {"kind": "unsupported_field_type", "detail": "file", "count": 5}
  ]
}
```

**Field names:** `name` (not `id`), `is_ready` (not `ready`), `source` is `"declared"` or `"framework_injected"` (the latter for surfaces named `_admin_*` or `_platform_*` that Dazzle auto-injects).

---

## Pilot evaluation — what we'd like to learn

### 1. Audit accuracy (highest priority)

**Run:** `python -m dazzle fragment-audit . --json > audit.json`

**Look at:**
- Total surface count: `audit.json["total"]`. Does this match the surface count you expect? (Filter `surfaces[*]` by `source == "declared"` to ignore framework noise.)
- `ready_count` vs `blocked_count`. Which surfaces are blocked?
- `aggregated_blockers` — the cross-surface count per blocker class. The largest count is the highest-leverage adapter gap to close next.

**Report back:**
- Any surface that the audit says is **ready** but you suspect won't render correctly.
- Any surface that the audit says is **blocked** but the listed blocker reason doesn't seem to match what's actually unsupported.
- Any field type or surface feature in your DSL that the audit doesn't mention at all (silent under-reporting — the worst failure mode).

### 2. Mass flip + smoke test

**Run:**

```bash
# Pick a single audit-ready surface to start; commit per surface.
# Or: bulk-flip every audit-ready surface using the helper from the dazzle repo.
python /path/to/dazzle/scripts/flip_to_fragment.py dsl/app.dsl
```

**Smoke test:**
- Boot the app: `dazzle serve` (or your normal dev flow).
- Click through CRUD on each flipped surface.
- Compare to the pre-flip Jinja-rendered version.

**Report back:**
- Any visual difference that's worse than the Jinja path.
- Any interactive behaviour (htmx, Alpine, sorting, filtering) that breaks.
- Any error in browser console or server log on a flipped surface.

### 3. RefPicker behaviour (specifically)

REF fields render via the `RefPicker` primitive — a `<select>` with `data-ref-api` + `x-init="dz.filterRefSelect($el)"`. The Alpine machinery is the same as the Jinja path's filter-bar ref selects (production-tested, but new context for forms).

**Report back:**
- EDIT forms: does the current FK value display in the select before the lazy fetch resolves? (RefPicker carries `initial_label` for this; if it's empty, you'll see the UUID until the fetch completes — visually noisy.)
- CREATE forms: does the dropdown populate with options after the fetch?
- Any case where the lazy fetch fails silently.

### 4. Architecture observations

The substrate's design choices we want to validate against a real codebase:

- **Distinct primitives over widening.** Combobox stayed enum-only; REF got its own RefPicker. Was this the right call from your side? Would a single "Picker" with options-or-ref-api modes have been better?
- **Static IR-level audit.** The audit doesn't invoke the renderer — it walks IR. Does this match what you'd want from a coverage tool, or do you need runtime feedback too?
- **Surface-level flip granularity.** The `render:` clause is per-surface. Would a per-region or per-field flip be more useful?

---

## How to provide feedback

Drop findings in any of:

1. **GitHub issues** on the Dazzle repo with the label `pilot:<your-project>`.
2. **Markdown notes** in your project's pilot doc under a `## Findings` section.
3. **Direct messages** if you have a faster channel.

For audit/render bugs, the most useful report includes:
- The DSL surface declaration (verbatim).
- The audit JSON entry for that surface.
- What you expected vs what rendered.
- Browser console output if interactive behaviour broke.

---

## Reference — primitives the renderer can emit

| Group | Primitive | Renders as |
|---|---|---|
| Layout | Stack, Row, Split, Grid | flex/grid containers |
| Containers | Surface, Card, Region, Toolbar, Drawer, Modal, Tabs | semantic content regions |
| Content | Text, Heading, Icon, Badge, EmptyState, Skeleton | inline content |
| Interactive | Button, Link, InlineEdit, Interactive | actions |
| Data | Table, KanbanBoard, CalendarGrid, Timeline, KPI, BarChart, PivotTable | data displays |
| Forms | FormStack, Field, Combobox, **RefPicker**, Submit | form inputs |
| Escape | RawHTML, Slot | controlled hatches |

CSS classes follow `dz-<primitive>` (e.g. `.dz-ref-picker`, `.dz-region--kind-form`). All bundled into the Dazzle CSS payload — no extra includes required on flipped surfaces.

---

## Reference — relevant files in the Dazzle repo

| Where | What |
|---|---|
| `src/dazzle/render/fragment/primitives/` | the 34 primitives, grouped by category |
| `src/dazzle/render/fragment/coverage.py` | the audit logic — capability matrix in `_SUPPORTED_MODES`, `_UNSUPPORTED_FEATURES`, `_UNSUPPORTED_FIELD_TYPES` |
| `src/dazzle/http/runtime/renderers/fragment_adapter.py` | `_field_to_primitive` — the type→primitive map |
| `src/dazzle/page/runtime/static/css/components/fragment-primitives.css` | per-primitive CSS rules |
| `scripts/flip_to_fragment.py` | the idempotent flip helper |
| `docs/superpowers/plans/migration-roadmap.md` | the framework's own migration history |
| `CHANGELOG.md` | per-release agent guidance |

---

## What success looks like for the pilot

1. **A complete audit JSON** — a single artefact we can compare against the framework's 78/78 to see if the audit logic generalises.
2. **One flipped surface that renders correctly** — proves the substrate works on a non-example codebase.
3. **One flipped surface that renders incorrectly** — surfaces the gap we hadn't anticipated. **This is the most valuable result of the pilot** — not a failure, the data we couldn't get from looking at our own examples.

The framework's stance: anything the pilot surfaces becomes a plan in the Dazzle repo. We expect surprises — that's the point of running it on a real consumer.
