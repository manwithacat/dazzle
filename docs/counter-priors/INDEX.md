# Counter-Prior Catalogue

Each file in this directory documents one **corpus pathology** — a pattern LLM training data biases models toward — and Dazzle's counter-prior: the right shape, why the wrong shape is load-bearing-bad, and which substrate layer enforces the fix.

The three substrate layers (see `dev_docs/2026-05-25-substrate-audit.md` and the project memory `project_prior_correction_substrate.md` for the framing):

- **Grammar (layer 1)** — the DSL excludes the bad shape by construction. Strongest counter-prior.
- **Inference (layer 2)** — agent instructions / KB entries injected at the right moment. This catalogue.
- **Filter (layer 3)** — drift gates / conformance / fitness that catch what the first two layers let through.

Each entry's frontmatter declares which layer it primarily belongs to, plus triggers (natural-language fragments and code-shape regexes) that the bootstrap and `knowledge counter_prior` MCP path use to surface it at relevant moments.

Entries are agent-scannable: each row is a counter-prior that prevents a wrong emission.

These entries correct **corpus priors** — bad shapes humans wrote at scale, now in
training data. Agentic *production* has its own predictable failure modes; the
mechanism for discovering and validating those agent-era counter-priors (without
naively importing human critique of AI code as ground truth) is
[Agent self-reflection](../architecture/agent-self-reflection.md).

## Active entries

- [custom-route-undeclared-response](custom-route-undeclared-response.md) — A `routes/*.py` override that returns HTML with no `# dazzle:returns` (can't be chromed → escapes the shell) and/or touches an entity with no `# dazzle:implements` (bypasses RBAC). Chrome/shape = declared choice (novel UI welcome via `page`); RBAC = the mandatory line (#1392/#1420).
- [domain-coupled-keywords](domain-coupled-keywords.md) — Naming DSL keywords / field names after the source spec's domain (`pupil_card`, `customer_id`). Domain values belong at the adapter layer; the grammar stays generic.
- [duplicated-parent-fields](duplicated-parent-fields.md) — Copying a parent's field onto a child alongside the `ref`. The Repository auto-includes ref data; the copy goes stale, the framework can't keep it in sync.
- [exceptions-as-control-flow](exceptions-as-control-flow.md) — `try`/`except: pass` / fallback control flow / EAFP misused. Counters silent failures in user app code.
- [god-entities](god-entities.md) — Single-entity-spans-everything modelling. Decompose through refs so RBAC, scope, and lifecycle match conceptual boundaries.
- [hand-rolled-soft-delete](hand-rolled-soft-delete.md) — Manual `deleted_at` column + per-surface `scope: deleted_at = null`. Use the `soft_delete:` keyword (#1218); the substrate filters tombstones centrally.
- [hand-rolled-temporal](hand-rolled-temporal.md) — Manual `start_date`/`end_date` + per-surface current-row scopes + custom as-of handlers. Use `temporal:` (#1223); keyword wires auto-filtering, uniqueness, URL param, and `latest_one` traversal.
- [magic-string-typing](magic-string-typing.md) — bare `str` for identifier classes (`user_id: str`), status discriminators, or lookup keys. Pairs with `dazzle.types.NewType`, `enum.StrEnum`, and `PA-LLM-10`.
- [n-plus-one-in-user-code](n-plus-one-in-user-code.md) — Naive ORM-shaped loops over related rows in `app/` code. Framework paths aggregate centrally; user code re-introduces N+1 unless explicitly batched.
- [optional-instead-of-result](optional-instead-of-result.md) — `def f(...) -> T | None` collapsing multiple distinct failure modes into a single None sentinel. Pairs with `dazzle.result` and `PA-LLM-09`.
- [polymorphic-associations](polymorphic-associations.md) — Rails-style `belongs_to :commentable, polymorphic: true` and `(subject_type, subject_id)` discriminator pairs. Closed by ADR-0027; pairs with the four-question interrogation.
- [reinvented-capability](reinvented-capability.md) — *(agent-era)* Re-implementing an invariant-equivalent capability that already exists (a keyword, a helper) because bounded context didn't surface it. The general form of the hand-rolled-* cluster; discover before you write. Surfaced + validated via [agent self-reflection](../architecture/agent-self-reflection.md).
- [assert-on-mock](assert-on-mock.md) — *(agent-era)* A test whose assertions verify the mock, not the behaviour — green by construction, stays green when the real behaviour breaks. Mock boundaries, assert on what the real code produced. Surfaced + validated via [agent self-reflection](../architecture/agent-self-reflection.md).
- [raw-sql-string-building](raw-sql-string-building.md) — f-string / `+` SQL in user code. Framework paths parameterise by construction; raw SQL bypasses the predicate algebra and re-introduces injection class.
- [raw-db-in-custom-route](raw-db-in-custom-route.md) — A custom route handler (`routes/*.py` override) reaching the DB directly (raw SQL / hand-built `Repository`) bypasses the entity's permit/scope — the RBAC-bypass cousin of raw-sql-string-building. Bind via `# dazzle:implements <Entity>.<op>` or call `check_entity_op`; `scan_handler_for_raw_db` flags it. ADR-0040 / #1420 Slice 3.
- [regex-in-dsl-parser](regex-in-dsl-parser.md) — `re.compile` in parser code. A regex on a DSL shape signals a missing IR type. ADR-0024 + drift gate; allowlist sits at zero.
- [shell-without-strict-mode](shell-without-strict-mode.md) — Shell scripts missing `set -euo pipefail`. Silent continuation past failed commands is the corpus shape and the highest-leverage one-line fix in the catalogue.
- [stringly-typed-refs](stringly-typed-refs.md) — `customer_email: str` instead of `customer: ref Customer`. The FK graph + scope predicate algebra depend on typed refs.
- [subtype-polymorphism-default](subtype-polymorphism-default.md) — `subtype_of:` reached for reflexively whenever a spec mentions "variants of X." Walk the three alternatives (separate entities, state machine, nullable fields) first.

## Adding a new entry

1. Write `docs/counter-priors/<id-in-kebab-case>.md` with YAML frontmatter (see existing entries for the schema).
2. The four sections `## The corpus prior` / `## Wrong shape` / `## Right shape` / `## Why this matters here` are mandatory — the drift test enforces them.
3. Bump `SEED_SCHEMA_VERSION` in `src/dazzle/mcp/knowledge_graph/seed.py` so deployed KGs re-seed.
4. Add a one-line entry to this index.
5. The drift test (`tests/unit/test_counter_priors_drift.py`) will fail until every file is well-formed and every KG row maps back to a markdown file.
