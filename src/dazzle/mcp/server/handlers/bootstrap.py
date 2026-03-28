"""
Bootstrap handler - entry point for naive "build me an app" requests.

Scans for spec files, runs initial cognition pass, and returns a structured
mission briefing that programs the LLM agent's next steps.
"""

import json
import logging
from pathlib import Path
from typing import Any

from .common import extract_progress
from .spec_analyze import handle_spec_analyze

logger = logging.getLogger(__name__)

# Files that might contain a spec (in priority order)
SPEC_FILE_CANDIDATES = [
    "spec.md",
    "SPEC.md",
    "spec.txt",
    "idea.md",
    "idea.txt",
    "requirements.md",
    "README.md",
    "readme.md",
]


def handle_bootstrap(arguments: dict[str, Any], project_path: Path | None = None) -> str:
    """
    Bootstrap a new app from a naive user request.

    Scans for spec files, runs cognition pass, returns mission briefing.
    """
    progress = extract_progress(arguments)
    # Determine working directory
    work_dir = project_path or Path.cwd()

    # Phase 1: Find or create spec
    progress.log_sync("Scanning for spec files...")
    spec_text, spec_source = _find_spec(work_dir, arguments)

    if not spec_text:
        # No spec found - return instructions to gather one
        return json.dumps(
            {
                "status": "needs_spec",
                "message": "No specification found. Need to gather requirements.",
                "agent_instructions": {
                    "step": 1,
                    "action": "gather_spec",
                    "prompt_user": (
                        "I'd like to understand what you want to build. "
                        "Please describe your app idea - who uses it, what they do, "
                        "and any key features you have in mind. Don't worry about "
                        "technical details, just explain it like you would to a friend."
                    ),
                    "on_response": (
                        "Write the user's response to spec.md, then call "
                        "bootstrap(operation='analyze') to continue."
                    ),
                },
            },
            indent=2,
        )

    # Phase 2: Run cognition pass
    # spec_source is always set when spec_text is set
    progress.log_sync("Running cognition pass...")
    return _run_cognition_pass(spec_text, spec_source or "unknown")


def _find_spec(work_dir: Path, arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    """Find a spec file or extract from arguments."""
    # Check if spec provided directly
    if spec_text := arguments.get("spec_text"):
        return spec_text, "provided_directly"

    # Check if spec path provided
    if spec_path := arguments.get("spec_path"):
        path = Path(spec_path)
        if path.exists():
            return path.read_text(), str(path)
        return None, None

    # Scan for spec files
    for candidate in SPEC_FILE_CANDIDATES:
        path = work_dir / candidate
        if path.exists():
            content = path.read_text().strip()
            # Skip near-empty files or template READMEs
            if len(content) > 100 and not _is_template_readme(content):
                return content, str(path)

    return None, None


def _is_template_readme(content: str) -> bool:
    """Check if content looks like a template README rather than a spec."""
    template_markers = [
        "# Project Title",
        "## Installation",
        "## Getting Started",
        "npm install",
        "pip install",
        "## License",
    ]
    matches = sum(1 for marker in template_markers if marker in content)
    return matches >= 3


def _run_cognition_pass(spec_text: str, spec_source: str) -> str:
    """Run the full cognition pass and return mission briefing."""
    # Run all analysis operations
    entities_raw = handle_spec_analyze({"operation": "discover_entities", "spec_text": spec_text})
    entities_result = json.loads(entities_raw)

    personas_raw = handle_spec_analyze({"operation": "extract_personas", "spec_text": spec_text})
    personas_result = json.loads(personas_raw)

    lifecycles_raw = handle_spec_analyze(
        {
            "operation": "identify_lifecycles",
            "spec_text": spec_text,
            "entities": [e["name"] for e in entities_result.get("entities", [])],
        }
    )
    lifecycles_result = json.loads(lifecycles_raw)

    rules_raw = handle_spec_analyze({"operation": "surface_rules", "spec_text": spec_text})
    rules_result = json.loads(rules_raw)

    questions_raw = handle_spec_analyze(
        {
            "operation": "generate_questions",
            "spec_text": spec_text,
            "entities": [e["name"] for e in entities_result.get("entities", [])],
        }
    )
    questions_result = json.loads(questions_raw)

    # Build mission briefing
    questions = questions_result.get("questions", [])
    has_questions = len(questions) > 0

    # Dedupe and clean entities
    seen_names: set[str] = set()
    clean_entities = []
    for e in entities_result.get("entities", []):
        name = e.get("name", "")
        if name and name not in seen_names and len(name) > 2:
            seen_names.add(name)
            clean_entities.append(e)

    briefing = {
        "status": "analyzed",
        "spec_source": spec_source,
        "analysis": {
            "entities": clean_entities[:15],  # Cap at reasonable number
            "personas": personas_result.get("personas", []),
            "lifecycles": lifecycles_result.get("lifecycles", []),
            "business_rules": rules_result.get("business_rules", []),
            "detected_actions": entities_result.get("actions", []),
        },
        "clarification_needed": has_questions,
        "questions": questions,
        "agent_instructions": _build_instructions(has_questions, questions),
    }

    return json.dumps(briefing, indent=2)


def _build_instructions(has_questions: bool, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the agent instruction block."""
    if has_questions:
        # Format questions for the agent to ask
        question_texts = [q.get("question", "") for q in questions[:5]]  # Max 5 questions

        return {
            "phase": "clarification",
            "action": "ask_questions",
            "questions_to_ask": question_texts,
            "present_as": (
                "Before I generate the app, I have a few questions to make sure "
                "I build exactly what you need:"
            ),
            "on_answers": (
                "Once the user answers, call spec_analyze(operation='refine_spec', "
                "spec_text=<original_spec>, answers=<user_answers_dict>) to produce "
                "the refined specification, then follow the generation steps below."
            ),
            "generation_steps": [
                "Follow the same 18-step generation workflow as the direct-generation phase:",
                "Structure (1-3) → Data model (4-6) → Access control (7a-7b) → UI (8-10) → ",
                "Validation (11-13) → Security verification (14-16) → Coverage (17)",
                "See the generation phase 'steps' array for exact instructions per step.",
            ],
            "dsl_generation_rules": [
                "Use knowledge(operation='concept', term=<construct>) for syntax - not examples",
                "Generate incrementally: entities first, then surfaces, then workspaces",
                (
                    "EVERY entity MUST have permit: blocks (role-only checks) AND scope: blocks "
                    "(field conditions with for: clauses). No field conditions inside permit: — "
                    "that is a parser error. After all entities are defined, run "
                    "policy(operation='access_matrix') to verify zero PERMIT_UNPROTECTED cells."
                ),
                "After generating list surfaces, add ux blocks with sort/filter/search/empty",
                "Validate after each major section with dsl(operation='validate')",
                (
                    "After validation, run sentinel(operation='findings') and "
                    "semantics(operation='tenancy') as security gates."
                ),
                "Do NOT copy from example projects - generate from first principles",
            ],
        }
    else:
        return {
            "phase": "generation",
            "action": "generate_dsl",
            "steps": [
                # --- Structure ---
                "1. Create dsl/ directory if it doesn't exist",
                "2. Generate module header with app name and description",
                "3. Define personas with descriptions and default_workspace assignments",
                # --- Data model ---
                "4. Generate entity definitions based on analysis",
                "5. Add state machines for entities with lifecycles",
                (
                    "6. If spec mentions third-party services (payments, email, identity, etc.), "
                    "call api_pack(operation='search', query=<vendor>) to check for existing "
                    "integration packs before writing integration DSL blocks."
                ),
                # --- Access control (mandatory) ---
                (
                    "7a. Add permit: blocks to EVERY entity — these are authorization gates. "
                    "permit: rules MUST contain ONLY role() checks (e.g. 'list: role(admin)'). "
                    "Field conditions (e.g. 'owner = current_user') are a parser error inside "
                    "permit: and will fail validation. Every role that needs access to an entity "
                    "must appear in a permit: block. Default-deny: roles not listed are blocked. "
                    "Use forbid: for separation-of-duty constraints. "
                    "Use knowledge(operation='concept', term='access_rules') for syntax."
                ),
                (
                    "7b. Add scope: blocks for row filtering — these control what rows each role "
                    "sees, not whether they may access the endpoint. Use field conditions with "
                    "a for: clause: 'scope: for role(teacher): school = current_user.school'. "
                    "Every role permitted in step 7a MUST have a matching scope: rule unless "
                    "the intent is to grant unrestricted row access, in which case use "
                    "'scope: for role(admin): all'. The '*' wildcard grants all rows to all "
                    "permitted roles when no per-role scoping is needed. "
                    "scope: and permit: are separate DSL blocks — never mix them."
                ),
                # --- UI ---
                "8. Generate surfaces (CRUD views) for each entity",
                (
                    "8a. If the app has auth enabled, add `feedback_widget: enabled` after "
                    "the app declaration. This creates a human→agent feedback loop — users "
                    "report issues via an in-app widget, agents read and resolve them via "
                    "the feedback MCP tool."
                ),
                (
                    "9. Add ux blocks to list surfaces: sort (default ordering), "
                    "filter (enum/bool/status fields), search (text fields users "
                    "would search by), empty messages. "
                    "Use knowledge(operation='concept', term='ux_block') for syntax"
                ),
                "10. Create workspaces for each persona with access: persona() declarations",
                # --- Validation gates ---
                "11. Validate with dsl(operation='validate')",
                "12. Run dsl(operation='lint', extended=true) for quality check",
                (
                    "12a. Review the 'Relevant capabilities' section of the lint output. "
                    "Consider whether any surfaced capabilities (widgets, layout modes, "
                    "components) are applicable to your generated DSL and incorporate them "
                    "before proceeding."
                ),
                (
                    "13. Run dsl(operation='fidelity') to verify each surface has all "
                    "fields the entity defines. Fix any missing fields."
                ),
                # --- Security verification ---
                (
                    "14. Run policy(operation='access_matrix') to verify the RBAC model. "
                    "Check that: no entity shows PERMIT_UNPROTECTED, sensitive entities "
                    "are DENY for unauthorized roles, and the matrix matches the intended "
                    "access policy. Fix any gaps before proceeding."
                ),
                (
                    "15. Run sentinel(operation='findings') to check for SaaS failure "
                    "modes: missing audit fields, unsafe state transitions, exposed PII. "
                    "Fix any high-severity findings."
                ),
                (
                    "16. Run semantics(operation='tenancy') to verify multi-tenant data "
                    "isolation is correctly scoped. Run semantics(operation='compliance') "
                    "if the app handles user data or regulated fields."
                ),
                # --- Coverage verification ---
                (
                    "17. If stories or processes were defined, run story(operation='coverage') "
                    "and process(operation='coverage') to verify the generated app covers them."
                ),
            ],
            "dsl_generation_rules": [
                "Use knowledge(operation='concept', term=<construct>) for syntax - not examples",
                "Generate incrementally and validate frequently",
                (
                    "EVERY entity MUST have permit: blocks (role-only checks) AND scope: blocks "
                    "(field conditions with for: clauses). Field conditions inside permit: are a "
                    "parser error. After all entities are defined, run "
                    "policy(operation='access_matrix') — zero PERMIT_UNPROTECTED cells required."
                ),
                "Do NOT copy from example projects - generate from first principles",
                (
                    "After validation, run sentinel(operation='findings') and "
                    "semantics(operation='tenancy') as security gates."
                ),
            ],
        }
