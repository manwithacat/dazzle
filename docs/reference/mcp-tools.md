# MCP Tool Inventory

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Live inventory of the MCP tools exposed by `dazzle mcp run`. Generated from the tool registry — every operation, parameter, and description below comes straight from `dazzle.mcp.server.tools_consolidated.get_all_consolidated_tools()` at build time. Run `dazzle docs generate` to refresh after adding, renaming, or removing tools or operations. The drift gate at `tests/unit/test_api_surface_drift.py` (mcp_tools baseline) catches surface changes that didn't update the docs.

**Live count:** 18 tools, 92 operations. Regenerated from the registry every time `dazzle docs generate` runs.

Each tool is a single MCP entry point that dispatches on the `operation` argument. The Bootstrap tool (`bootstrap`) is the exception — it takes free-form spec text, not an operation enum, and is the canonical entry point for "build me an app" requests.

## Tool index

| Tool | Operations | Summary |
|------|------------|---------|
| [`agent`](#agent) | 3 | Agent closed-loop control plane (#1605): context (brownfield map + runtime |
| [`bootstrap`](#bootstrap) | — | Entry point for 'build me an app' requests |
| [`compliance`](#compliance) | 5 | Compliance documentation operations |
| [`conformance`](#conformance) | 4 | DSL conformance testing operations |
| [`db`](#db) | 2 | Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection) |
| [`discovery`](#discovery) | 1 | Capability discovery operations: coherence (persona-by-persona authenticated UX coherence score) |
| [`dsl`](#dsl) | 10 | DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec |
| [`feedback`](#feedback) | 5 | Feedback operations: list, get, summarise, triage, resolve |
| [`guide`](#guide) | 4 | Inspect declared onboarding guides |
| [`knowledge`](#knowledge) | 9 | Knowledge lookup: concept, examples, cli_help, workflow, inference, changelog, counter_prior, get_spec, search_commands |
| [`policy`](#policy) | 6 | Policy analysis operations for RBAC access control |
| [`rhythm`](#rhythm) | 3 | Rhythm operations: get, list, coverage |
| [`semantics`](#semantics) | 5 | Semantic analysis: extract, tenancy, compliance, analytics, extract_guards |
| [`sentinel`](#sentinel) | 4 | Sentinel operations: findings (get findings from latest/specific scan), status (available agents and last scan), history (list recent scans), fuzz_summary (run a small mutation fuzz campaign and return the markdown report) |
| [`sitespec`](#sitespec) | 14 | SiteSpec operations: get, validate, scaffold, coherence, review, advise |
| [`spec_analyze`](#spec_analyze) | 6 | Low-level narrative analysis (untrusted draft) |
| [`status`](#status) | 7 | Status operations: mcp, logs, active_project, telemetry, activity, demo_world (alias: runtime) |
| [`story`](#story) | 4 | Story operations: get, composition, coverage, scope_fidelity |

## Per-tool detail

### `agent`

Agent closed-loop control plane (#1605): context (brownfield map + runtime.truth + next_steps), prove (static binding evidence), playbook (domain_logic map→bind→scaffold→prove). Does NOT write files — use CLI `dazzle scaffold` / `dazzle agent prove`. For data-shape judgement (exclusive FKs / poly_ref / JSONB) use CLI `dazzle representation decide` (#1617).

**Operations (3):** `context`, `prove`, `playbook`

**Parameters:**

- `story_id` *(string)* — Story id for prove (optional; default all accepted)
- `name` *(string)* — Playbook name (default: domain_logic)
- `mode` *(string)* — Proof kind (for prove). static: target exists in DSL/host map. runtime: host-module readiness. journey: surface hub / open-via hop coherence. Default: static.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `bootstrap`

Entry point for 'build me an app' requests. Scans for spec files, runs cognition pass, and returns a mission briefing with agent instructions. Call this first when a user wants to build an app. Returns structured guidance for the next steps: either questions to ask the user, or instructions for DSL generation. The workflow includes mandatory RBAC: every entity must have permit:/forbid: access rules, verified via policy(operation='access_matrix') before the app is considered complete.

**Parameters:**

- `spec_text` *(string)* — Optional: spec text if provided directly by user
- `spec_path` *(string)* — Optional: path to spec file
- `project_path` *(string)* — Optional: project directory to scan for specs

---

### `compliance`

Compliance documentation operations. compile: compile taxonomy + evidence into AuditSpec. evidence: extract DSL evidence summary. gaps: list controls with gaps or partial evidence. summary: quick compliance posture summary. review: generate review data for gap remediation.

**Operations (5):** `compile`, `evidence`, `gaps`, `summary`, `review`

**Parameters:**

- `framework` *(string)* — Framework ID: iso27001 or soc2 (default: iso27001)
- `status_filter` *(array)* — Control states to include (for gaps). Default: [gap, partial].
- `tier_filter` *(array)* — Control tiers to include (for gaps), e.g. [1, 2] for the controls that matter most.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `conformance`

DSL conformance testing operations. summary: run derivation pipeline and return coverage metrics (total cases, per-entity counts, scope types). cases: return all conformance cases for a specific entity (requires entity_name). gaps: find entities that have permit rules but no scope blocks (authorization without row filtering). monitor_status: return current runtime conformance monitor state (observations collected).

**Operations (4):** `summary`, `cases`, `gaps`, `monitor_status`

**Parameters:**

- `entity_name` *(string)* — Entity name (required for cases)
- `auth_enabled` *(boolean)* — Include unauthenticated (401) cases (default: true)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `db`

Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection).

**Operations (2):** `status`, `verify`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `discovery`

Capability discovery operations: coherence (persona-by-persona authenticated UX coherence score).

**Operations (1):** `coherence`

**Parameters:**

- `persona` *(string)* — Persona id to score (for coherence). Omit to score every persona.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `dsl`

DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec. NOTE: export_frontend_spec produces a LARGE output intended for human developers migrating away from Dazzle — always use 'sections' and/or 'entities' filters to avoid flooding context. Prefer inspect_entity/inspect_surface for LLM queries.

**Operations (10):** `validate`, `list_modules`, `inspect_entity`, `inspect_surface`, `analyze`, `lint`, `get_spec`, `fidelity`, `list_fragments`, `export_frontend_spec`

**Parameters:**

- `name` *(string)* — Entity or surface name (for inspect_entity/inspect_surface)
- `extended` *(boolean)* — Run extended checks (for lint)
- `suppress_relevance` *(boolean)* — Drop the capability-relevance appendix from lint output (for lint). The appendix is what most of the payload; omit it when you only need errors and warnings.
- `entity_names` *(array)* — Entity names to fetch full details for (for get_spec). Omit for summary.
- `surface_names` *(array)* — Surface names to fetch full details for (for get_spec). Omit for summary.
- `surface_filter` *(string)* — Filter to a specific surface name (for fidelity)
- `gaps_only` *(boolean)* — Omit surfaces with fidelity=1.0 (for fidelity)
- `format` *(string)* — Output format (for export_frontend_spec, default: markdown)
- `sections` *(array)* — Filter to specific sections (for export_frontend_spec). Options: typescript_interfaces, route_map, component_inventory, state_machines, api_contract, workspace_layouts, test_criteria
- `entities` *(array)* — Filter to specific entity names (for export_frontend_spec)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `feedback`

Feedback operations: list, get, summarise, triage, resolve. Query and manage user-submitted feedback reports and review notes. Use 'list' to see open feedback (grouped by review_session when the notes carry one), 'get' for one report with its anchor and context, 'summarise' for open notes grouped by surface then severity, 'triage' to mark as triaged, 'resolve' to close. Targets the local `dazzle serve` by default; set DAZZLE_FEEDBACK_URL (base URL) and DAZZLE_FEEDBACK_COOKIE (name=value session cookie) to read a deployed app.

**Operations (5):** `list`, `get`, `summarise`, `triage`, `resolve`

**Parameters:**

- `id` *(string)* — Feedback report ID (required for get/triage/resolve)
- `status` *(string)* — Filter by status; comma list, e.g. 'new,triaged' (list/summarise; summarise defaults to new,triaged)
- `category` *(string)* — Filter by category (list only)
- `severity` *(string)* — Filter by severity (list only)
- `surface` *(string)* — Filter by the surface the note was left on (list only)
- `review_session` *(string)* — Filter by review session, e.g. '2026-10-25-ab12' (list only)
- `page_url` *(string)* — Filter by the page URL the note was left on (list only)
- `since` *(string)* — Only reports created at or after this ISO 8601 timestamp (list/summarise)
- `limit` *(integer)* — Max results (list default 20, summarise default 200)
- `agent_notes` *(string)* — Agent notes (triage/resolve)
- `agent_classification` *(string)* — Classification (triage only)
- `assigned_to` *(string)* — Assign to (triage only)
- `resolved_by` *(string)* — Who resolved (resolve only)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `guide`

Inspect declared onboarding guides. Stateless reads only; writes (mark step complete/dismissed) stay on the HTTP routes. Operations: list (every guide with audience + step count), get (full IR for one guide by name), concordance (run the linker's concordance check in isolation — verifies target / completion / cta refs resolve against the DSL), narrate (linear ordered narrative of one guide's steps — agent-readable equivalent of the rendered overlay sequence).

**Operations (4):** `list`, `get`, `concordance`, `narrate`

**Parameters:**

- `name` *(string)* — Guide name (for 'get' / 'narrate')
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `knowledge`

Knowledge lookup: concept, examples, cli_help, workflow, inference, changelog, counter_prior, get_spec, search_commands. counter_prior surfaces entries from docs/counter-priors/ — corpus pathologies Dazzle inoculates against. Call before emitting non-trivial user-app Python, raw SQL, or shell scripts. Note: Static content also available via MCP Resources.

**Operations (9):** `concept`, `examples`, `cli_help`, `workflow`, `inference`, `changelog`, `counter_prior`, `get_spec`, `search_commands`

**Parameters:**

- `term` *(string)* — Concept/pattern name (for concept)
- `features` *(array)* — Features to search (for examples)
- `complexity` *(string)* — Complexity level (for examples)
- `command` *(string)* — CLI command (for cli_help)
- `workflow` *(string)* — Workflow name (for workflow)
- `query` *(string)* — Search query (for inference or counter_prior text-trigger match)
- `detail` *(string)* — Detail level (for inference)
- `list_all` *(boolean)* — List all triggers (for inference / counter_prior)
- `since` *(string)* — Version filter (for changelog, e.g. '0.48.0')
- `id` *(string)* — Counter-prior id (for counter_prior direct fetch — returns full body)
- `code_shape` *(string)* — Description of code about to be written, or a code fragment — matched against triggers_code regexes with triggers_text fallback (for counter_prior)
- `layer` *(string)* — Substrate layer filter for list_all (for counter_prior)
- `summary_only` *(boolean)* — Return spec file metadata instead of full content (for get_spec). Default: false.
- `include_sources` *(boolean)* — Include source provenance with the spec (for get_spec). Default: true.

---

### `policy`

Policy analysis operations for RBAC access control. Operations: analyze (find entities without access rules), conflicts (detect contradictory permit/forbid rules), coverage (permission matrix: persona x entity x operation), simulate (trace which rules fire for a given persona + entity + operation), access_matrix (full RBAC access matrix from rbac module), verify_status (summary of last `dazzle rbac verify` run)

**Operations (6):** `analyze`, `conflicts`, `coverage`, `simulate`, `access_matrix`, `verify_status`

**Parameters:**

- `entity_names` *(array)* — Filter to specific entity names (optional)
- `persona` *(string)* — Persona ID (required for simulate)
- `operation_kind` *(string)* — CRUD operation to simulate (required for simulate)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `rhythm`

Rhythm operations: get, list, coverage. Rhythms are longitudinal persona journey maps through the app, organized into temporal phases containing scenes (actions on surfaces).

**Operations (3):** `get`, `list`, `coverage`

**Parameters:**

- `name` *(string)* — Rhythm name (for get)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `semantics`

Semantic analysis: extract, tenancy, compliance, analytics, extract_guards

**Operations (5):** `extract`, `tenancy`, `compliance`, `analytics`, `extract_guards`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `sentinel`

Sentinel operations: findings (get findings from latest/specific scan), status (available agents and last scan), history (list recent scans), fuzz_summary (run a small mutation fuzz campaign and return the markdown report). Deterministic static analysis of the IR — no source code scanning.

**Operations (4):** `findings`, `status`, `history`, `fuzz_summary`

**Parameters:**

- `agent` *(string)* — Filter findings by agent ID (for findings).
- `severity` *(string)* — Minimum severity to include (for findings). Default: info.
- `scan_id` *(string)* — Specific scan ID (for findings).
- `limit` *(integer)* — Max scans to return (for history). Default: 10.
- `samples` *(integer)* — Samples per layer for fuzz_summary. Default: 10.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `sitespec`

SiteSpec operations: get, validate, scaffold, coherence, review, advise. Copy operations: get_copy, scaffold_copy, review_copy. Use 'coherence' to check if the site feels like a real website (navigation, CTAs, content completeness). Use 'review' for page-by-page comparison of spec vs rendering status. Use 'advise' to get proactive layout improvement suggestions. Theme operations: get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts.

**Operations (14):** `get`, `validate`, `scaffold`, `get_copy`, `scaffold_copy`, `review_copy`, `coherence`, `review`, `get_theme`, `scaffold_theme`, `validate_theme`, `generate_tokens`, `generate_imagery_prompts`, `advise`

**Parameters:**

- `use_defaults` *(boolean)* — Use defaults when missing (for get, get_theme)
- `check_content_files` *(boolean)* — Check content files (for validate)
- `product_name` *(string)* — Product name (for scaffold, scaffold_copy)
- `overwrite` *(boolean)* — Overwrite existing (for scaffold, scaffold_copy, scaffold_theme)
- `business_context` *(string)* — Business type hint for coherence check (saas, marketplace, agency, ecommerce)
- `brand_hue` *(number)* — Brand hue 0-360 on OKLCH wheel (for scaffold_theme)
- `brand_chroma` *(number)* — Brand chroma 0-0.4 (for scaffold_theme)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `spec_analyze`

Low-level narrative analysis (untrusted draft). Operations: discover_entities (extract nouns/relationships), identify_lifecycles (find state transitions), extract_personas (identify user roles), surface_rules (extract business rules), generate_questions (surface ambiguities), refine_spec (produce structured spec from all analyses). Counter-prior: bootstrap_pollution.

**Operations (6):** `discover_entities`, `identify_lifecycles`, `extract_personas`, `surface_rules`, `generate_questions`, `refine_spec`

**Parameters:**

- `spec_text` *(string)* — The narrative spec text to analyze
- `entities` *(array)* — Entity names (for identify_lifecycles, generate_questions)
- `answers` *(object)* — Answers to generated questions (for refine_spec)

---

### `status`

Status operations: mcp, logs, active_project, telemetry, activity, demo_world (alias: runtime). demo_world = agent-readable serve ports, test_secret present?, masked DB URL, STABLE persona ids (#1629). activity = real-time MCP tool invocations (cursor polling).

**Operations (7):** `mcp`, `logs`, `active_project`, `telemetry`, `activity`, `demo_world`, `runtime`

**Parameters:**

- `reload` *(boolean)* — Reload modules (for mcp)
- `include_changelog` *(boolean)* — For mcp: include full new_since_last_check CHANGELOG text (default false — compact count only; #1629 G6)
- `count` *(integer)* — Number of entries (for logs, telemetry, activity)
- `level` *(string)* — Filter by level (for logs)
- `errors_only` *(boolean)* — Show only errors (for logs)
- `tool_name` *(string)* — Filter by tool name (for telemetry)
- `since_minutes` *(integer)* — Only show invocations from the last N minutes (for telemetry)
- `stats_only` *(boolean)* — Only return aggregate stats, no individual invocations (for telemetry)
- `cursor_seq` *(integer)* — Sequence number to read after (for activity, 0 = from start)
- `cursor_epoch` *(integer)* — Epoch for staleness detection (for activity). Echo back the cursor.epoch you were given; 0 means you hold no cursor yet. stale=true means the sequence id no longer refers to this history and the read has restarted.
- `format` *(string)* — Response format (for activity): 'structured' (JSON, default) or 'formatted' (human-readable text)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `story`

Story operations: get, composition, coverage, scope_fidelity. Use get with view='wall' for a founder-friendly board grouped by implementation status (working/needs polish/not started). composition maps the story⇄rhythm graph — which phase composes a story (and whether it is active), and which stories are declared but composed into no journey. scope_fidelity checks that implementing processes exercise all entities in story scope.

**Operations (4):** `get`, `composition`, `coverage`, `scope_fidelity`

**Parameters:**

- `status_filter` *(string)* — Filter by status (for get)
- `story_ids` *(array)* — Story IDs (for get: fetch full details; for composition: focus on these stories)
- `view` *(string)* — View mode for get operation. 'wall' groups stories by implementation status (working/needs polish/not started)
- `persona` *(string)* — Filter stories by persona/actor name (for get with view=wall)
- `limit` *(integer)* — Max items per page (for coverage, scope_fidelity). Default: 50.
- `offset` *(integer)* — Items to skip (for coverage, scope_fidelity). Default: 0.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---
