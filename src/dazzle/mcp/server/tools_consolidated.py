"""
Consolidated MCP Server tool definitions.

This module reduces token budget by consolidating related tools into single
tools with enum-based operations. Each operation is explicitly listed in the
schema, preserving discoverability for LLMs.

Consolidation strategy:
- 66 original tools → 18 consolidated tools (+ 4 dev-mode project tools)
- Knowledge tools (5) → MCP Resources (no schema overhead)
- CRUD patterns unified: list/get/inspect → single tool with operation enum

Token savings: ~40-50% reduction in tool schema overhead.
"""

from mcp.types import Tool

from .state import is_dev_mode


def get_dev_mode_tools() -> list[Tool]:
    """Get tools specific to dev mode.

    Single `project` tool with an `operation` enum — matches the
    registry's dominant noun+ops pattern (`dsl validate`, `story get`,
    etc.). Replaces 4 method-named outliers in v0.67.151 (#1074).
    """
    return [
        Tool(
            name="project",
            description=(
                "Manage the active project and walk the project list. "
                "Operations: list (list available projects), get_active (current "
                "selection), select (choose one by name), validate_all (validate "
                "every project at once)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Operation to perform",
                        "enum": ["list", "get_active", "select", "validate_all"],
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the project (required for operation=select)",
                    },
                },
                "required": ["operation"],
            },
        ),
    ]


# Common schema for project_path parameter
PROJECT_PATH_SCHEMA = {
    "project_path": {
        "type": "string",
        "description": "Optional: Absolute path to project directory. If omitted, uses active project.",
    }
}


# =========================================================================
# Per-tool factory functions (private)
# =========================================================================


def _tool_dsl() -> Tool:
    """DSL operations (replaces 7 tools)."""
    return Tool(
        name="dsl",
        description="DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec. NOTE: export_frontend_spec produces a LARGE output intended for human developers migrating away from Dazzle — always use 'sections' and/or 'entities' filters to avoid flooding context. Prefer inspect_entity/inspect_surface for LLM queries.",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "validate",
                        "list_modules",
                        "inspect_entity",
                        "inspect_surface",
                        "analyze",
                        "lint",
                        "get_spec",
                        "fidelity",
                        "list_fragments",
                        "export_frontend_spec",
                    ],
                    "description": "Operation to perform",
                },
                "name": {
                    "type": "string",
                    "description": "Entity or surface name (for inspect_entity/inspect_surface)",
                },
                "extended": {
                    "type": "boolean",
                    "description": "Run extended checks (for lint)",
                },
                "suppress_relevance": {
                    "type": "boolean",
                    "description": "Drop the capability-relevance appendix from lint output (for lint). The appendix is what most of the payload; omit it when you only need errors and warnings.",
                },
                "entity_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity names to fetch full details for (for get_spec). Omit for summary.",
                },
                "surface_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Surface names to fetch full details for (for get_spec). Omit for summary.",
                },
                "surface_filter": {
                    "type": "string",
                    "description": "Filter to a specific surface name (for fidelity)",
                },
                "gaps_only": {
                    "type": "boolean",
                    "description": "Omit surfaces with fidelity=1.0 (for fidelity)",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "Output format (for export_frontend_spec, default: markdown)",
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific sections (for export_frontend_spec). Options: typescript_interfaces, route_map, component_inventory, state_machines, api_contract, workspace_layouts, test_criteria",
                },
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific entity names (for export_frontend_spec)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_db() -> Tool:
    """DB operations (read-only)."""
    return Tool(
        name="db",
        description="Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection).",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["status", "verify"],
                    "description": "Operation to perform",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_story() -> Tool:
    """Stories (replaces 6 tools)."""
    return Tool(
        name="story",
        description="Story operations: get, composition, coverage, scope_fidelity. Use get with view='wall' for a founder-friendly board grouped by implementation status (working/needs polish/not started). composition maps the story⇄rhythm graph — which phase composes a story (and whether it is active), and which stories are declared but composed into no journey. scope_fidelity checks that implementing processes exercise all entities in story scope.",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get",
                        "composition",
                        "coverage",
                        "scope_fidelity",
                    ],
                    "description": "Operation to perform",
                },
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "accepted", "rejected", "draft"],
                    "description": "Filter by status (for get)",
                },
                "story_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Story IDs (for get: fetch full details; for composition: focus on these stories)",
                },
                "view": {
                    "type": "string",
                    "enum": ["wall"],
                    "description": (
                        "View mode for get operation. "
                        "'wall' groups stories by implementation status "
                        "(working/needs polish/not started)"
                    ),
                },
                "persona": {
                    "type": "string",
                    "description": "Filter stories by persona/actor name (for get with view=wall)",
                },
                # #1756 — pagination was implemented (and correct: it reports
                # total_stories, offset and has_more) but never declared, so no
                # agent could find it or tell a truncated page from the whole set.
                "limit": {
                    "type": "integer",
                    "description": "Max items per page (for coverage, scope_fidelity). Default: 50.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Items to skip (for coverage, scope_fidelity). Default: 0.",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_rhythm() -> Tool:
    """Rhythm operations."""
    return Tool(
        name="rhythm",
        description="Rhythm operations: get, list, coverage. Rhythms are longitudinal persona journey maps through the app, organized into temporal phases containing scenes (actions on surfaces).",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get",
                        "list",
                        "coverage",
                    ],
                    "description": "Operation to perform",
                },
                "name": {
                    "type": "string",
                    "description": "Rhythm name (for get)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_feedback() -> Tool:
    """Feedback — human-to-agent feedback loop."""
    return Tool(
        name="feedback",
        description=(
            "Feedback operations: list, get, triage, resolve. "
            "Query and manage user-submitted feedback reports. "
            "Use 'list' to see open feedback, 'get' for detail, "
            "'triage' to mark as triaged, 'resolve' to close."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "get", "triage", "resolve"],
                    "description": "Operation to perform",
                },
                "id": {
                    "type": "string",
                    "description": "Feedback report ID (required for get/triage/resolve)",
                },
                "status": {"type": "string", "description": "Filter by status (list only)"},
                "category": {"type": "string", "description": "Filter by category (list only)"},
                "severity": {"type": "string", "description": "Filter by severity (list only)"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (list only, default 20)",
                },
                "agent_notes": {
                    "type": "string",
                    "description": "Agent notes (triage/resolve)",
                },
                "agent_classification": {
                    "type": "string",
                    "description": "Classification (triage only)",
                },
                "assigned_to": {"type": "string", "description": "Assign to (triage only)"},
                "resolved_by": {"type": "string", "description": "Who resolved (resolve only)"},
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_sitespec() -> Tool:
    """SiteSpec (replaces 3 tools + copy + coherence operations)."""
    return Tool(
        name="sitespec",
        description="SiteSpec operations: get, validate, scaffold, coherence, review, advise. Copy operations: get_copy, scaffold_copy, review_copy. Use 'coherence' to check if the site feels like a real website (navigation, CTAs, content completeness). Use 'review' for page-by-page comparison of spec vs rendering status. Use 'advise' to get proactive layout improvement suggestions. Theme operations: get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts.",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "get",
                        "validate",
                        "scaffold",
                        "get_copy",
                        "scaffold_copy",
                        "review_copy",
                        "coherence",
                        "review",
                        "get_theme",
                        "scaffold_theme",
                        "validate_theme",
                        "generate_tokens",
                        "generate_imagery_prompts",
                        "advise",
                    ],
                    "description": "Operation to perform",
                },
                "use_defaults": {
                    "type": "boolean",
                    "description": "Use defaults when missing (for get, get_theme)",
                },
                "check_content_files": {
                    "type": "boolean",
                    "description": "Check content files (for validate)",
                },
                "product_name": {
                    "type": "string",
                    "description": "Product name (for scaffold, scaffold_copy)",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite existing (for scaffold, scaffold_copy, scaffold_theme)",
                },
                "business_context": {
                    "type": "string",
                    "description": "Business type hint for coherence check (saas, marketplace, agency, ecommerce)",
                },
                "brand_hue": {
                    "type": "number",
                    "description": "Brand hue 0-360 on OKLCH wheel (for scaffold_theme)",
                },
                "brand_chroma": {
                    "type": "number",
                    "description": "Brand chroma 0-0.4 (for scaffold_theme)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_semantics() -> Tool:
    """Semantics (replaces 5 tools)."""
    return Tool(
        name="semantics",
        description="Semantic analysis: extract, tenancy, compliance, analytics, extract_guards",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "extract",
                        "tenancy",
                        "compliance",
                        "analytics",
                        "extract_guards",
                    ],
                    "description": "Operation to perform",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_status() -> Tool:
    """Status (replaces 2 tools)."""
    return Tool(
        name="status",
        description=(
            "Status operations: mcp, logs, active_project, telemetry, activity, "
            "demo_world (alias: runtime). "
            "demo_world = agent-readable serve ports, test_secret present?, "
            "masked DB URL, STABLE persona ids (#1629). "
            "activity = real-time MCP tool invocations (cursor polling)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "mcp",
                        "logs",
                        "active_project",
                        "telemetry",
                        "activity",
                        "demo_world",
                        "runtime",
                    ],
                    "description": "Operation to perform",
                },
                "reload": {
                    "type": "boolean",
                    "description": "Reload modules (for mcp)",
                },
                "include_changelog": {
                    "type": "boolean",
                    "description": (
                        "For mcp: include full new_since_last_check CHANGELOG text "
                        "(default false — compact count only; #1629 G6)"
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "Number of entries (for logs, telemetry, activity)",
                },
                "level": {
                    "type": "string",
                    "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                    "description": "Filter by level (for logs)",
                },
                "errors_only": {
                    "type": "boolean",
                    "description": "Show only errors (for logs)",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Filter by tool name (for telemetry)",
                },
                "since_minutes": {
                    "type": "integer",
                    "description": "Only show invocations from the last N minutes (for telemetry)",
                },
                "stats_only": {
                    "type": "boolean",
                    "description": "Only return aggregate stats, no individual invocations (for telemetry)",
                },
                "cursor_seq": {
                    "type": "integer",
                    "description": "Sequence number to read after (for activity, 0 = from start)",
                },
                "cursor_epoch": {
                    "type": "integer",
                    "description": "Epoch for staleness detection (for activity). Echo back the cursor.epoch you were given; 0 means you hold no cursor yet. stale=true means the sequence id no longer refers to this history and the read has restarted.",
                },
                "format": {
                    "type": "string",
                    "enum": ["structured", "formatted"],
                    "description": "Response format (for activity): 'structured' (JSON, default) or 'formatted' (human-readable text)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_knowledge() -> Tool:
    """Knowledge (replaces 5 tools, now primarily via Resources)."""
    return Tool(
        name="knowledge",
        description=(
            "Knowledge lookup: concept, examples, cli_help, workflow, inference, "
            "changelog, counter_prior, get_spec, search_commands. "
            "counter_prior surfaces entries from docs/counter-priors/ — corpus "
            "pathologies Dazzle inoculates against. Call before emitting "
            "non-trivial user-app Python, raw SQL, or shell scripts. "
            "Note: Static content also available via MCP Resources."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "concept",
                        "examples",
                        "cli_help",
                        "workflow",
                        "inference",
                        "changelog",
                        "counter_prior",
                        "get_spec",
                        "search_commands",
                    ],
                    "description": "Operation to perform",
                },
                "term": {
                    "type": "string",
                    "description": "Concept/pattern name (for concept)",
                },
                "features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Features to search (for examples)",
                },
                "complexity": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                    "description": "Complexity level (for examples)",
                },
                "command": {
                    "type": "string",
                    "description": "CLI command (for cli_help)",
                },
                "workflow": {
                    "type": "string",
                    "description": "Workflow name (for workflow)",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for inference or counter_prior text-trigger match)",
                },
                "detail": {
                    "type": "string",
                    "enum": ["minimal", "full"],
                    "description": "Detail level (for inference)",
                },
                "list_all": {
                    "type": "boolean",
                    "description": "List all triggers (for inference / counter_prior)",
                },
                "since": {
                    "type": "string",
                    "description": "Version filter (for changelog, e.g. '0.48.0')",
                },
                "id": {
                    "type": "string",
                    "description": "Counter-prior id (for counter_prior direct fetch — returns full body)",
                },
                "code_shape": {
                    "type": "string",
                    "description": "Description of code about to be written, or a code fragment — matched against triggers_code regexes with triggers_text fallback (for counter_prior)",
                },
                "layer": {
                    "type": "string",
                    "enum": ["grammar", "inference", "filter"],
                    "description": "Substrate layer filter for list_all (for counter_prior)",
                },
                # #1756 — `get_spec` honours both; without them an agent cannot
                # ask for file metadata instead of the whole spec body.
                "summary_only": {
                    "type": "boolean",
                    "description": "Return spec file metadata instead of full content (for get_spec). Default: false.",
                },
                "include_sources": {
                    "type": "boolean",
                    "description": "Include source provenance with the spec (for get_spec). Default: true.",
                },
            },
            "required": ["operation"],
        },
    )


def _tool_agent() -> Tool:
    """#1605 agent-first closed loop (read/report only — ADR-0002)."""
    return Tool(
        name="agent",
        description=(
            "Agent closed-loop control plane (#1605): context (brownfield map + "
            "runtime.truth + next_steps), prove (static binding evidence), "
            "playbook (domain_logic map→bind→scaffold→prove). "
            "Does NOT write files — use CLI `dazzle scaffold` / `dazzle agent prove`. "
            "For data-shape judgement (exclusive FKs / poly_ref / JSONB) use "
            "CLI `dazzle representation decide` (#1617)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["context", "prove", "playbook"],
                    "description": "Operation to perform",
                },
                "story_id": {
                    "type": "string",
                    "description": "Story id for prove (optional; default all accepted)",
                },
                "name": {
                    "type": "string",
                    "description": "Playbook name (default: domain_logic)",
                },
                # #1756 — `prove` picks its proof kind from this; it was read but
                # never declared, so an agent could only ever get `static`.
                "mode": {
                    "type": "string",
                    "enum": ["static", "runtime", "journey"],
                    "description": "Proof kind (for prove). static: target exists in DSL/host map. runtime: host-module readiness. journey: surface hub / open-via hop coherence. Default: static.",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_bootstrap() -> Tool:
    """Bootstrap (entry point for naive app requests)."""
    return Tool(
        name="bootstrap",
        description=(
            "Entry point for 'build me an app' requests. Scans for spec files, "
            "runs cognition pass, and returns a mission briefing with agent instructions. "
            "Call this first when a user wants to build an app. Returns structured "
            "guidance for the next steps: either questions to ask the user, or "
            "instructions for DSL generation. The workflow includes mandatory RBAC: "
            "every entity must have permit:/forbid: access rules, verified via "
            "policy(operation='access_matrix') before the app is considered complete."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "spec_text": {
                    "type": "string",
                    "description": "Optional: spec text if provided directly by user",
                },
                "spec_path": {
                    "type": "string",
                    "description": "Optional: path to spec file",
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional: project directory to scan for specs",
                },
            },
            "required": [],
        },
    )


def _tool_spec_analyze() -> Tool:
    """Spec analyze (individual cognition operations)."""
    return Tool(
        name="spec_analyze",
        description=(
            "Low-level narrative analysis (untrusted draft). Operations: "
            "discover_entities (extract nouns/relationships), "
            "identify_lifecycles (find state transitions), "
            "extract_personas (identify user roles), "
            "surface_rules (extract business rules), "
            "generate_questions (surface ambiguities), "
            "refine_spec (produce structured spec from all analyses). "
            "Counter-prior: bootstrap_pollution."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "discover_entities",
                        "identify_lifecycles",
                        "extract_personas",
                        "surface_rules",
                        "generate_questions",
                        "refine_spec",
                    ],
                    "description": "Operation to perform",
                },
                "spec_text": {
                    "type": "string",
                    "description": "The narrative spec text to analyze",
                },
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity names (for identify_lifecycles, generate_questions)",
                },
                "answers": {
                    "type": "object",
                    "description": "Answers to generated questions (for refine_spec)",
                },
            },
            "required": ["operation"],
        },
    )


def _tool_discovery() -> Tool:
    """Discovery operations (capability discovery agent)."""
    return Tool(
        name="discovery",
        description=(
            "Capability discovery operations: "
            "coherence (persona-by-persona authenticated UX coherence score)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "coherence",
                    ],
                    "description": "Operation to perform",
                },
                # #1756 — read by the handler, absent from the schema, so the
                # "persona-by-persona" in the tool description was unreachable.
                "persona": {
                    "type": "string",
                    "description": "Persona id to score (for coherence). Omit to score every persona.",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_policy() -> Tool:
    """Policy analysis (RBAC access control)."""
    return Tool(
        name="policy",
        description=(
            "Policy analysis operations for RBAC access control. "
            "Operations: analyze (find entities without access rules), "
            "conflicts (detect contradictory permit/forbid rules), "
            "coverage (permission matrix: persona x entity x operation), "
            "simulate (trace which rules fire for a given persona + entity + operation), "
            "access_matrix (full RBAC access matrix from rbac module), "
            "verify_status (summary of last `dazzle rbac verify` run)"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "analyze",
                        "conflicts",
                        "coverage",
                        "simulate",
                        "access_matrix",
                        "verify_status",
                    ],
                    "description": "Operation to perform",
                },
                "entity_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific entity names (optional)",
                },
                "persona": {
                    "type": "string",
                    "description": "Persona ID (required for simulate)",
                },
                "operation_kind": {
                    "type": "string",
                    "enum": ["create", "read", "update", "delete", "list"],
                    "description": "CRUD operation to simulate (required for simulate)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_sentinel() -> Tool:
    """Sentinel (SaaS failure-mode detection)."""
    return Tool(
        name="sentinel",
        description=(
            "Sentinel operations: findings (get findings from latest/specific scan), "
            "status (available agents and last scan), "
            "history (list recent scans), "
            "fuzz_summary (run a small mutation fuzz campaign and return the markdown report). "
            "Deterministic static analysis of the IR — no source code scanning."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "findings",
                        "status",
                        "history",
                        "fuzz_summary",
                    ],
                    "description": "Operation to perform",
                },
                "agent": {
                    "type": "string",
                    "description": "Filter findings by agent ID (for findings).",
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                    "description": "Minimum severity to include (for findings). Default: info.",
                },
                "scan_id": {
                    "type": "string",
                    "description": "Specific scan ID (for findings).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max scans to return (for history). Default: 10.",
                },
                "samples": {
                    "type": "integer",
                    "description": "Samples per layer for fuzz_summary. Default: 10.",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_guide() -> Tool:
    """Guide (guided-onboarding introspection — v0.71.7)."""
    return Tool(
        name="guide",
        description=(
            "Inspect declared onboarding guides. Stateless reads only; "
            "writes (mark step complete/dismissed) stay on the HTTP "
            "routes. Operations: "
            "list (every guide with audience + step count), "
            "get (full IR for one guide by name), "
            "concordance (run the linker's concordance check in "
            "isolation — verifies target / completion / cta refs "
            "resolve against the DSL), "
            "narrate (linear ordered narrative of one guide's steps — "
            "agent-readable equivalent of the rendered overlay sequence)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "get", "concordance", "narrate"],
                    "description": "Operation to perform",
                },
                "name": {
                    "type": "string",
                    "description": "Guide name (for 'get' / 'narrate')",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_conformance() -> Tool:
    """Conformance (DSL conformance testing)."""
    return Tool(
        name="conformance",
        description=(
            "DSL conformance testing operations. "
            "summary: run derivation pipeline and return coverage metrics (total cases, per-entity counts, scope types). "
            "cases: return all conformance cases for a specific entity (requires entity_name). "
            "gaps: find entities that have permit rules but no scope blocks (authorization without row filtering). "
            "monitor_status: return current runtime conformance monitor state (observations collected)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["summary", "cases", "gaps", "monitor_status"],
                    "description": "Operation to perform",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Entity name (required for cases)",
                },
                "auth_enabled": {
                    "type": "boolean",
                    "description": "Include unauthenticated (401) cases (default: true)",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def _tool_compliance() -> Tool:
    """Compliance documentation operations."""
    return Tool(
        name="compliance",
        description=(
            "Compliance documentation operations. "
            "compile: compile taxonomy + evidence into AuditSpec. "
            "evidence: extract DSL evidence summary. "
            "gaps: list controls with gaps or partial evidence. "
            "summary: quick compliance posture summary. "
            "review: generate review data for gap remediation."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["compile", "evidence", "gaps", "summary", "review"],
                    "description": "Operation to perform",
                },
                "framework": {
                    "type": "string",
                    "description": "Framework ID: iso27001 or soc2 (default: iso27001)",
                },
                "status_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Control states to include (for gaps). Default: [gap, partial].",
                },
                "tier_filter": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Control tiers to include (for gaps), e.g. [1, 2] for the controls that matter most.",
                },
                **PROJECT_PATH_SCHEMA,
            },
            "required": ["operation"],
        },
    )


def get_consolidated_tools() -> list[Tool]:
    """
    Get consolidated tools (knowledge/query operations only).

    Process operations (dsl_test, e2e_test, pipeline, test-design) are
    available via CLI commands instead.

    Each tool uses an 'operation' enum to specify the action, preserving
    discoverability while reducing schema overhead.
    """
    return [
        _tool_dsl(),
        _tool_db(),
        _tool_story(),
        _tool_rhythm(),
        _tool_feedback(),
        _tool_sitespec(),
        _tool_semantics(),
        _tool_status(),
        _tool_knowledge(),
        _tool_bootstrap(),
        _tool_agent(),
        _tool_spec_analyze(),
        _tool_discovery(),
        _tool_policy(),
        _tool_sentinel(),
        _tool_guide(),
        _tool_conformance(),
        _tool_compliance(),
    ]


def get_all_consolidated_tools() -> list[Tool]:
    """Get all tools (dev mode + consolidated)."""
    tools = []

    if is_dev_mode():
        tools.extend(get_dev_mode_tools())

    tools.extend(get_consolidated_tools())

    return tools
