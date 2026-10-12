# Demo Identity & Cognition

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Agent-facing priors for commercial demos: STABLE persona identities, reset-and-load, empty-desk false greens, and version cognition. Companion to counter-priors under `docs/counter-priors/`. Issues #1626–#1630.

---

## Demo Identity

How demo principals, emails, and assignment seeds share UUIDs so persona desks
populate after seed. The closed map is STABLE_PERSONA_USER_IDS
(`dazzle.core.demo_identity`, read by the framework test routes).

**Keys (persona *id*, not display title):** member, manager, admin, agent,
customer, requester, approver, finance, auditor, user, designer, reviewer,
tester, engineer, ops_engineer, employee, hr_admin, tenant_admin, finance_admin.

**Email domain:** `{role}@demo.dazzle.local`

**UUID range:** a1000000-0000-4000-8000-… reserved for these principals only.

**Order:** serve → re-read runtime.json → `dazzle demo reset-and-load -y` →
authenticate with `role=` *after* reset → open default_workspace (browser +
HTMX settle). Never authenticate before reset.

**Seeds:** prefer `dsl/seeds/demo_data/*.jsonl` (STABLE FKs). Generated
`.dazzle/demo_data` faker is last resort (counter-prior
`faker_seed_over_story_spine`). Multi-tenant apps: keep User.jsonl rows that
carry `tenant_id` — auth mirror cannot placeholder required refs.

### Syntax

```dsl
persona requester "Promoter":    # id = STABLE key; title free
  default_workspace: my_holds

# seeds reference a1000000-… requester id on assignment FKs
```

### Example

```dsl
# Good — STABLE id + human title
persona approver "Booker":
  default_workspace: booker_desk

# Bad — free id; role=promoter will not match STABLE seed UUIDs
persona promoter "Promoter":
  default_workspace: my_holds
```

### Best Practices

- Persona *id* must be a STABLE key for assignment-aware demos
- Display title can be domain language (Promoter, Booker)
- Authenticate with role= only after reset-and-load
- Do not re-seed scalar-only User rows at STABLE UUIDs (reset mirrors them)
- Do keep multi-tenant User.jsonl with tenant_id when domain User requires it
- MCP: status(operation=demo_world); knowledge concept demo_identity
- Counter-priors: free_persona_id_not_stable, reseed_stable_users, faker_seed_over_story_spine

**Related:** [Stable Personas](demo.md#stable-personas), [Empty Desk False Green](demo.md#empty-desk-false-green), [First Principles Demo](demo.md#first-principles-demo), [Workspace Region Filters](workspaces.md#workspace-region-filters)

---

## Stable Personas

Alias of demo_identity focused on the closed STABLE principal map used by
`/__test__/authenticate` and assignment-aware seeds. See demo_identity.

### Best Practices

- Use knowledge(concept='demo_identity') for the full map and order

**Related:** [Demo Identity](demo.md#demo-identity), [Empty Desk False Green](demo.md#empty-desk-false-green)

---

## Empty Desk False Green

**False green:** validate green while a persona default workspace is empty
under session. Static checks read seed assignment vs filter *text*; they do
not prove live RBAC (`as:` roles), STABLE principal bind, or region filter
runtime.

**live_desk probe:** tries list/queue sources on the default workspace until
one has rows. An empty satellite entity (e.g. PaymentAttempt with no story
seed) is not residual if a sibling list/queue (Invoice) is populated.

**Stills:** hero floors are local under gitignored `.dazzle/qa/screenshots`.
CI residual does not prove stills — re-run recapture after seed changes.

**Verify for real:**
1. `reset-and-load` report `live_desk_residual` (if present)
2. Authenticate `role=` after reset; open default workspace with browser/HTMX settle
3. `dazzle qa capture` (curl HTML is skeleton only — regions `hx-trigger=load`)
4. On empty: check scope `as:` tokens, STABLE persona ids, region filters, story seeds

### Best Practices

- Never treat residual=0 alone as demo ready
- Counter-prior: empty_desk_false_green

**Related:** [Demo Identity](demo.md#demo-identity), [Workspace Region Filters](workspaces.md#workspace-region-filters), [First Principles Demo](demo.md#first-principles-demo)

---

## First Principles Demo

Closed-loop workflow from cold project to persona stills without tribal SQL.

**Steps:**
1. Read the founder brief; `bootstrap` / `spec_analyze` output is an untrusted draft
2. Close open questions with the founder; no chrome invents
3. Hand-author DSL from the brief's vocabulary (STABLE persona ids)
4. `dazzle validate` — fix errors; heed #1630 warns on as:/STABLE
5. `dazzle serve` (test mode) — writes `.dazzle/runtime.json`
6. **Re-read runtime.json** (ports/secret/database_url may change)
7. `dazzle demo reset-and-load --project <app> -y` (story seeds / demo_spine)
8. Authenticate with `role=<stable_id>` **after** reset
9. Browser open default_workspace with HTMX settle; or `dazzle qa capture`
10. `status(operation=demo_world)` for the world model

**MCP:** knowledge, status demo_world.
**CLI writes:** serve, reset-and-load, capture.
**Do not** use bootstrap entities as SSOT (bootstrap_pollution).

### Syntax

```dsl
# hand-author DSL from the founder brief, then:
dazzle validate -p ./app
dazzle serve --project ./app
dazzle demo reset-and-load --project ./app -y
```

### Best Practices

- workflow: knowledge(operation='workflow', workflow='first_principles_demo')
- Always load demo_ops from agent context or status(demo_world)
- close founder questions before entity blocks
- ignore bootstrap analysis.entities as SSOT

**Related:** [Demo Identity](demo.md#demo-identity), [Empty Desk False Green](demo.md#empty-desk-false-green), [Workspace Region Filters](workspaces.md#workspace-region-filters), [Bootstrap Pollution](demo.md#bootstrap-pollution)

---

## Bootstrap Pollution

Do **not** use bootstrap / analyze-spec / discover_entities as the default
SPEC→DSL path. Prefer founder brief → close open questions →
hand-author DSL → validate. Treat bootstrap analysis.entities as untrusted.
Counter-prior: bootstrap_pollution.

### Best Practices

- Rank bootstrap below hand-authoring + validate loop
- knowledge counter_prior bootstrap_pollution

**Related:** [First Principles Demo](demo.md#first-principles-demo), [Demo Identity](demo.md#demo-identity)

---

## Metric Current User Lie

When workspace metrics use count(... = current_user) and sibling lists for
the same persona have rows, trust **lists and stills over KPI tiles** (F10).
Counter-prior: metric_current_user_lie.

### Best Practices

- Trust order: list/queue → stills → metrics last
- knowledge counter_prior metric_current_user_lie

**Related:** [Empty Desk False Green](demo.md#empty-desk-false-green), [Demo Identity](demo.md#demo-identity)

---

## Version Cognition

Version decisions need three fields, not the CLI banner alone:

1. **installed** — package version (`dazzle version` / status.mcp.version)
2. **project_pin** — dazzle.toml `framework_version` (tilde minor pin)
3. **compatible** — whether installed satisfies pin

Init stamps `framework_version = "~{{major.minor}}"` from installed package.
status.mcp exposes `version_cognition`. Counter-prior: version_pin_distrust.

### Best Practices

- Do not invent pins from banner folklore
- status(operation=mcp) → version_cognition

**Related:** [First Principles Demo](demo.md#first-principles-demo)

---
