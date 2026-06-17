# htmx 4 migration — browser-oracle baseline (htmx 2)

Date: 2026-06-17
Branch: `htmx4-eval`. Captured BEFORE any htmx 4 bundle swap, on current htmx 2.0.9.

Per `htmx4-evaluation.md`, the unit suite is server-side and htmx-version-agnostic — it cannot prove
the client migration works. The real oracle is playwright interaction walks (`dazzle ux verify
--interactions`, which runs JS in a real browser). This file records the **green baseline** that the
migration phases (vendor beta → JS rewrites → bridges) must not regress.

## Reproduction recipe

Prerequisites: local Postgres (per-app DBs already exist as `dazzle_<app>`, trust auth as `james`),
local Redis on 6379, playwright + chromium installed (`uv sync --extra e2e && playwright install
chromium`). Run from each app dir; `--interactions` spawns its own `dazzle serve`.

```bash
# from repo root, per app:
cd examples/<app>
DATABASE_URL='postgresql://james@localhost:5432/dazzle_<app>' \
REDIS_URL='redis://localhost:6379/0' \
dazzle ux verify --interactions --persona <persona>
# exit 0 = all interactions pass; 1 = a regression; 2 = setup failure
```

Boot needs BOTH `DATABASE_URL` and `REDIS_URL` (infra check fails otherwise), and the right
`--persona` (anon/wrong persona → 403 Access Denied, empty layout).

## Baseline results (htmx 2.0.9)

| App | Persona | DB | Exit | Interactions |
|---|---|---|---|---|
| `ops_dashboard` | `ops_engineer` | `dazzle_ops_dashboard` | **0** | card_drag PASS, card_add PASS |
| `support_tickets` | `agent` | `dazzle_support_tickets` | **0** | card_drag PASS, card_add PASS, context_select PASS |
| `design_studio` | `designer` | `dazzle_design_studio` | **1** | card_drag PASS, **card_add FAIL** |

### Known pre-existing failure (NOT a migration regression)

`design_studio` / `card_add` fails on **current htmx 2** with: *"card body text is 23 chars — likely
still a skeleton"* (`body_length=23`, `region_fetch_count=2`). The newly-added card's region fetch
fires but the body never replaces the skeleton. This is a current-code bug (plausibly the eval's
known design-studio post-create/region-load issue) — it is **red before any htmx 4 change**.

## Migration gate (use this, not "all green")

A migration phase is non-regressing iff:
- `ops_dashboard` interactions stay **exit 0**
- `support_tickets` interactions stay **exit 0**
- `design_studio` `card_drag` stays **PASS**; `card_add` may stay failing (pre-existing) but must not
  introduce *new* failure modes, and no other interaction may flip PASS→FAIL.

Re-run all three after each of: bundle swap, event renames, xhr→fetch, morph/Alpine, json-enc bridge.
Unit-suite green is a necessary floor, never sufficient proof.
