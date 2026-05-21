# Agent Workflow Guide

How to build and evolve a Dazzle application using an AI agent: spec change →
agent edits DSL → validate → tests → human review → deploy.

---

## 1. Why a DSL Is Agent-Friendly

The central premise of Dazzle (formalised in
[ADR-0004](../adr/0004-dsl-agent-first.md)) is that AI agents are the primary
*authors* of DSL, and human developers are primarily *reviewers*. This shapes
every design decision in the grammar.

**The spec stays small.** A complete production application — entities, access
control, surfaces, workflows, events, multi-tenant scoping — lives in a handful
of `.dsl` files. An agent holds the full specification in context. It never has
to infer intent from a sprawling implicit codebase, because there is no implicit
codebase.

**The grammar is constrained by design.** Dazzle's DSL is deliberately
*anti-Turing*: no control flow, no function definitions, no procedural
shortcuts. The `--anti-turing` flag on `dazzle lint` enforces this mechanically.
A constrained grammar means fewer plausible-but-wrong edits. When an agent
cannot express an idea in the DSL, that is useful signal — not a failing of the
framework, but a prompt to consider whether the idea belongs in the spec at all
or whether a service block is the right vehicle.

**Validation is fast and structured.** `dazzle validate` runs in under a second
and returns structured errors keyed to the specific construct that failed — not
a stack trace from a runtime that had to boot first. An agent can iterate on DSL
edits in a tight loop: edit → validate → read error → edit again. No server
restarts, no migrations, no test fixtures required at this stage.

**Scope rules are statically verified.** Row-level access control (`scope:`) is
compiled to a formal predicate algebra and validated against the FK graph at
`dazzle validate` time. An agent that writes an invalid scope rule (for example,
a field path that doesn't exist in the FK chain) gets a precise error before
anything runs. This makes access-control errors a class of problem the loop
catches early rather than discovering in production.

The [ROADMAP](../../ROADMAP.md) describes the growth model that emerges from
this design: agents build applications within the existing DSL vocabulary,
encounter friction at the grammar boundary when they need something the DSL
cannot yet express, and produce structured friction reports. That feedback loop
is how the framework evolves without becoming a general-purpose language.

---

## 2. The Loop

The core workflow is a tight cycle between the developer's intent, the agent's
DSL edits, and a deterministic validation + test gate before a human reviews and
deploys.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Requirement         Agent edits        dazzle validate        │
│      change     ───▶    DSL files   ───▶   dazzle lint    ──┐  │
│                                                              │  │
│                ◀──────────────────────────────────────────── ┘  │
│                        (fix and retry on failure)               │
│                                                                 │
│                             │ passes                           │
│                             ▼                                  │
│   dazzle rbac matrix    Tests pass?   dazzle test dsl-run ──┐  │
│   dazzle rbac verify  ──▶ suite   ──▶  dazzle e2e run      │  │
│                                                              │  │
│                ◀──────────────────────────────────────────── ┘  │
│                        (fix and retry on failure)               │
│                                                                 │
│                             │ passes                           │
│                             ▼                                  │
│                       Human review                             │
│                     (RBAC diff, migrations,                    │
│                      friction findings)                        │
│                                                                 │
│                             │ approved                         │
│                             ▼                                  │
│                dazzle db upgrade → dazzle serve                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Requirement change

The developer states what changed — a new entity, a new access rule, a workflow
step, a migration — as a natural-language requirement to the agent. The agent
does not improvise; it works from what the developer says. If the requirement is
ambiguous, the loop works best when the agent clarifies before editing rather
than after.

### Agent edits the DSL

The agent edits `.dsl` files directly: entities, surfaces, personas, workflow
definitions, event models, scope rules. All spec-level intent lives here. The
framework generates the runtime implementation from the DSL; the agent does not
write backend code, migration scripts (in the common case), or frontend
templates.

The files the agent typically touches:

| What changed | File |
|---|---|
| New entity / field change | `entities.dsl` or equivalent module |
| Access rule or persona | `personas.dsl` / `policies.dsl` |
| New surface or mode change | `surfaces.dsl` |
| Workflow or process step | `workflow.dsl` |
| Event model or projection | `events.dsl` |

### Validate

After each edit round, the agent runs:

```bash
dazzle validate
```

This parses all DSL modules, resolves cross-module dependencies, and validates
the merged AppSpec — including FK-graph checking of scope predicates. It
operates in the project directory (where `dazzle.toml` lives) and produces
human-readable errors by default.

A real error looks like:

```
ERROR: Entity 'Invoice' field 'supplier_id' — FK target 'Supplier' not found.
       Did you mean 'SupplierContact'? (module: entities.dsl, line 14)
```

The MCP `dsl` tool wraps the same validation for in-context use without leaving
the agent loop:

```
dsl { "operation": "validate" }
dsl { "operation": "lint", "extended": true }
```

Verified operations on the `dsl` MCP tool: `validate`, `list_modules`,
`inspect_entity`, `inspect_surface`, `analyze`, `lint`, `get_spec`, `fidelity`,
`list_fragments`, `export_frontend_spec`. See [section 3](#3-mcp--claude-code-setup)
for how to point an MCP client at the server.

For a more thorough pass — scope-warning completeness, anti-Turing compliance,
coverage checks — run:

```bash
dazzle lint
dazzle lint --anti-turing --strict   # fail on any Turing-complete construct
```

The agent iterates on validate + lint until both pass cleanly before moving to
tests.

### Tests

Once validation is clean, the agent runs the test layers in order of cost:

**Tier 1 — RBAC matrix + API tests (fast, no browser):**

```bash
dazzle rbac matrix      # generate static access matrix from DSL
dazzle rbac verify      # run dynamic verification against in-process app
dazzle test dsl-run     # API-based tests derived from stories
```

`dazzle rbac matrix` is entirely static — no server required. It derives the
access matrix from the DSL and writes it to a file the human reviewer will diff.
`dazzle rbac verify` (Layer 2) boots an in-process instance and exercises the
matrix against live HTTP responses.

What is auto-derived from the DSL: the RBAC matrix, Tier 1 API test flows from
`story` and `test-design` definitions, schema tests, scope predicate tests.

What must still be hand-authored: adversarial cross-tenant isolation tests,
business-logic edge cases that depend on runtime state, integration tests for
external services. The `examples/invoice_ops` test suite (see [section 4](#4-worked-example-how-invoice_ops-was-built-and-evolved))
includes hand-authored adversarial tests alongside the auto-derived ones — the
combination is what caught the cross-tenant leak.

**Tier 2 — scripted UI tests:**

```bash
dazzle test dsl-run          # Tier 1 API — no browser
dazzle test run              # Tier 2 Playwright scripted UI
dazzle test run-all          # all tiers
```

**Tier 3 — E2E with UX coverage tracking:**

```bash
dazzle e2e run               # E2E tests for the project
dazzle e2e coverage          # analyse E2E coverage
```

Tier 3 tests require a running app instance and are slower; they are run
selectively (after larger structural changes) rather than on every DSL edit.

### Human review

The review gate is the backstop for anything the mechanical checks cannot assess.
A reviewer inspects:

- **RBAC matrix diff** — `dazzle rbac matrix` output between the old and new
  spec. New `ALLOW` entries on sensitive entities need explicit sign-off.
- **Migration review** — the generated Alembic migration file under
  `.dazzle/migrations/versions/` for any schema change. Destructive migrations
  (column drops, renames, type changes) must be hand-edited in that file before
  they are applied; see [migrations guide](../reference/migrations.md).
- **Friction findings** — anything the agent logged as uncertain or the
  `dazzle lint` warnings flagged but didn't block on.
- **Business-logic correctness** — the loop verifies structural consistency, not
  domain correctness. A reviewer who understands the domain is the check.

The existence of this gate is not an apology for the loop. It is the design. See
[section 6](#6-the-verifiability-boundary) for what the loop does and does not
guarantee.

### Deploy

Once the human approves:

```bash
dazzle db upgrade    # apply pending migrations
dazzle serve         # start the app
```

See [deployment reference](../reference/deployment.md) and the [Heroku guide](heroku.md)
for environment-specific deployment instructions. This guide does not re-document
deployment.

---

## 3. MCP + Claude Code Setup

The Dazzle MCP server makes the `dsl` tool and the full knowledge-graph surface
available to any MCP-compatible AI agent without context-window tricks. The
agent calls tools directly rather than shelling out.

### Starting the MCP server

```bash
dazzle mcp run --working-dir /path/to/your/project
```

The server is stateless per request. It must be started from (or pointed at)
the project root where `dazzle.toml` lives.

### Registering with Claude Code

```bash
dazzle mcp setup
```

This registers the server in your Claude Code MCP configuration so the Dazzle
tools are available in all sessions automatically. Pass `--force` to overwrite
an existing registration.

For other MCP-compatible agents, add a server entry pointing to:

```bash
dazzle mcp run --working-dir /absolute/path/to/project
```

using whichever client configuration format your agent host expects.

### The `dsl` tool in the agent loop

The `dsl` MCP tool is the agent's primary introspection surface during the
edit-validate cycle. Verified operations (from `dazzle inspect api mcp-tools`):

| Operation | What it does |
|---|---|
| `validate` | Parse and validate the full DSL — same logic as `dazzle validate` |
| `lint` | Extended checks; pass `"extended": true` for all warning classes |
| `inspect_entity` | Full field/scope/permit details for one entity by name |
| `inspect_surface` | Surface definition and fragment inventory |
| `analyze` | Cross-cutting analysis of the AppSpec (entity relationships, coverage gaps) |
| `get_spec` | Full or filtered AppSpec summary; filter by entity or surface names |
| `list_modules` | List all DSL modules the parser resolved |
| `fidelity` | Per-surface fidelity score; `"gaps_only": true` to filter |
| `list_fragments` | List fragments available for a surface |
| `export_frontend_spec` | Export spec as TypeScript interfaces, route map, component inventory, etc. |

Typical agent loop for a DSL edit cycle in Claude Code:

1. `dsl { "operation": "validate" }` — confirm the edit is valid before testing.
2. `dsl { "operation": "inspect_entity", "name": "Invoice" }` — verify field
   names and types before referencing them in scope rules.
3. `dsl { "operation": "fidelity", "gaps_only": true }` — check whether new
   surfaces have coverage gaps.

The MCP server also exposes `graph`, `knowledge`, `policy`, `sentinel`, and
other tools for deeper introspection — run `dazzle inspect api mcp-tools` for
the full list.

---

## 4. Worked Example: How `invoice_ops` Was Built and Evolved

`examples/invoice_ops` is a production-grade accounts-payable system — invoices,
line items, supplier bank accounts, multi-step maker-checker approval, HLESS
event model, shared-schema tenancy, and a full RBAC matrix with four personas.
It was built entirely by this agent loop (SP1, v0.71.103) and then evolved
through six successive schema and DSL changes (SP2, v0.71.104) to exercise the
migration workflow.

### SP1: Building the app

The keystone build started from a blank scaffold and layered the spec in
discrete commits, each passing `dazzle validate` and the test suite before the
next:

| SHA | What the agent shipped |
|---|---|
| `c9223960` | Initial data + access model — entities, fields, scopes, personas |
| `4f9eaa14` | Shared-schema tenancy declaration |
| `2949db2a` | Maker-checker approval gates |
| `aa9fbc2d` | HLESS event model + status projection |
| `7d922509` | Surfaces including audit-export view |
| `6d841cb6` | Edit/create surfaces to make the app fully operable |

The RBAC isolation suite was hand-authored (not auto-derived from the DSL) as an
adversarial check. It caught a real problem:

| SHA | What the suite found |
|---|---|
| `f34c5a5b` | `admin_personas` included `tenant_admin` — a cross-tenant-visibility leak; removed |

This is the canonical example of why adversarial tests belong in the loop
alongside auto-derived ones. The DSL validated cleanly before this fix; the
isolation suite found what structural validation could not.

### SP2: Evolving the spec through migrations

Six successive changes exercised every migration class the loop must handle:

| SHA | Change | Migration class |
|---|---|---|
| `2672926d` | Add `Invoice.po_number` | Additive (auto-generated) |
| `add48eea` | Rename `bank_reference` field | Rename (hand-edited) |
| `956568a6` | Add `partially_paid` status | Enum evolution |
| `42af45a7` | Split `SupplierBankAccount` entity | Entity split + backfill script |
| `c560d6a1` | Event-schema retention + new field | Event-model change |
| `a79c1067` | Add `finance_admin` persona | DSL-only, no migration |

The companion artefact the loop produced is `docs/reference/migrations.md` —
the schema-evolution guide, written from the friction the agent encountered
running through these six changes. It documents which migration classes are safe
to auto-apply and which require hand-editing.

---

## 5. Failure Handling

### Validate fails

Read the error. `dazzle validate` names the construct, the module, and (where
possible) the line. Fix the DSL and re-run. Common patterns:

- **Unknown entity reference** — a scope rule or surface references an entity
  that does not exist in the merged spec. Check spelling; check that the module
  containing the entity is listed in `dazzle.toml`.
- **Invalid FK path** — a scope predicate traverses a relationship that doesn't
  exist in the FK graph. Use `dsl { "operation": "inspect_entity" }` to verify
  the field chain before writing the scope rule.
- **Duplicate surface name** — two surfaces share an identifier. Rename one; the
  error gives both locations.
- **Anti-Turing violation** — a construct contains control flow (`if`, `for`,
  etc.). Move the logic to a service block or remove it.

Iterate: edit → `dazzle validate` → read error → edit. Do not move to tests
until validate passes cleanly.

### A test fails

First, decide whether the test found a real problem or has a test issue.

**A correctly failing adversarial test has found a real bug.** The
`admin_personas` cross-tenant leak (SP1, `f34c5a5b`) was found this way. The
test was not wrong; the DSL was. Fix the DSL, re-run validate, re-run the test.

**A test that fails due to stale fixtures or seed data** is a test infrastructure
issue. The framework derives Tier 1 test flows from stories; if story definitions
diverge from the DSL, `dazzle test dsl-run` will error before running. Fix the
story or test-design definition, then retry.

**A migration-related test failure** (schema mismatch between what the app boots
with and what the test expects) means the migration sequence is incomplete. Run
`dazzle db current` to check the revision, then `dazzle db upgrade` to apply
pending migrations before re-running tests.

### The agent makes a wrong call

The human review gate is the backstop. When a reviewer inspects the RBAC matrix
diff and sees an unexpected `ALLOW` entry — or inspects a migration preview and
sees a destructive operation that should not be there — they stop the loop and
send the requirement back to the agent with a correction. The correction is a
new requirement change, and the loop restarts from the top.

The agent's wrong call is not a failure of the loop design. The loop is designed
to surface wrong calls cheaply, at the review gate, before they reach production.

### A migration needs hand-editing

Some schema changes cannot be expressed as auto-generated Alembic migrations:
column renames, type changes, entity splits with backfill logic. When the agent
encounters one of these:

1. Generate the migration with `dazzle db revision -m "description"`.
2. Open the generated file under `.dazzle/migrations/versions/` and add the
   hand-written SQL or SQLAlchemy operations.
3. Review the generated migration file and hand-edit it — rename, split, and
   type-change migrations need hand-written SQL (see [migrations.md](../reference/migrations.md)) —
   then apply with `dazzle db upgrade`.
4. Run `dazzle db verify` afterwards to confirm FK integrity.

See [migrations.md](../reference/migrations.md) for the full taxonomy of
migration classes and the patterns the SP2 exercise produced.

---

## 6. The Verifiability Boundary

The loop provides strong mechanical guarantees. It also has explicit limits. This
section is honest about both.

### What the loop checks mechanically

| Check | Tool | Guarantee |
|---|---|---|
| DSL is syntactically valid | `dazzle validate` | Every construct parses; no unknown keywords; cross-module references resolve |
| FK graph is consistent | `dazzle validate` | Every scope predicate's field path exists in the entity graph |
| Access matrix is correct by construction | `dazzle rbac matrix` | The static matrix matches the DSL's `permit:` / `scope:` / `as:` declarations |
| Access matrix is enforced at runtime | `dazzle rbac verify` | HTTP responses match the matrix for every persona / surface pair tested |
| Scope filters restrict data | `dazzle rbac verify-scope` | Row-level filters fire and are not bypassable via the tested routes |
| Schema migrations apply cleanly | `dazzle db upgrade` + `dazzle db verify` | Pending migrations apply without error; FK integrity holds afterwards |
| Anti-Turing compliance | `dazzle lint --anti-turing` | No control-flow constructs in DSL files |

### What still needs human judgment

- **Domain correctness.** The loop verifies structural consistency, not whether
  the entities and rules model the right domain concepts. A technically valid
  DSL can still model the wrong business logic.
- **Adversarial test design.** The loop auto-derives Tier 1 tests from stories.
  It does not auto-generate adversarial cross-tenant, privilege-escalation, or
  state-machine abuse tests. Those must be hand-authored.
- **Security claims.** The RBAC matrix is a necessary condition for the claims
  in [SECURITY_CLAIMS.md](../../SECURITY_CLAIMS.md), not a sufficient one.
  Evaluating those claims requires the full exercise described in
  [EVALUATION.md](../../EVALUATION.md).
- **Destructive migration review.** The generated migration file under
  `.dazzle/migrations/versions/` shows what will run. Whether it is *correct*
  for the domain — whether a column rename is safe, whether a backfill is
  complete — requires a reviewer who understands the data.
- **External integrations.** Service blocks declare contracts with external
  systems. The loop validates the DSL side of that contract; it cannot validate
  the external system.

**The loop reduces risk. It does not remove the need for human review.**

The review gate in the loop is not a formality or a concession to process. It is
the point at which domain judgment, adversarial thinking, and accountability
enter. An agent that produces a clean validation pass, a passing test suite, and
a correct RBAC matrix has done its job well. A human who reviews the result and
approves it is doing a different job — one the loop cannot do on their behalf.

---

*Related: [deployment reference](../reference/deployment.md) · [Heroku guide](heroku.md)
· [migrations guide](../reference/migrations.md) · [SECURITY_CLAIMS.md](../../SECURITY_CLAIMS.md)
· [EVALUATION.md](../../EVALUATION.md) · [ADR-0004](../adr/0004-dsl-agent-first.md)
· [ROADMAP](../../ROADMAP.md) · [AGENTS.md](../../AGENTS.md)*
