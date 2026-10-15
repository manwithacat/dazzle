"""
Bootstrap handler - entry point for naive "build me an app" requests.

Scans for spec files, runs initial cognition pass, and returns a structured
mission briefing that programs the LLM agent's next steps.
"""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.representation import decide_representation

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
                        "bootstrap(spec_path='spec.md') to continue."
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
            return path.read_text(encoding="utf-8"), str(path)
        return None, None

    # Scan for spec files
    for candidate in SPEC_FILE_CANDIDATES:
        path = work_dir / candidate
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
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

    # #1249 — pattern recogniser pass. Walks spec_text against
    # patterns.toml trigger lists (positive proposals) and inference_kb
    # modeling-guidance triggers (anti-pattern flags). Surfaces "your
    # spec mentions X; consider declaring `temporal:` on Employment" so
    # the agent picks the canonical idiom on the first try instead of
    # discovering it via compile errors.
    patterns_raw = handle_spec_analyze(
        {
            "operation": "propose_patterns",
            "spec_text": spec_text,
        }
    )
    patterns_result = json.loads(patterns_raw)

    # #1617 — representation ladder (decide) so agents pick exclusive FKs /
    # poly_ref / JSON hatches before dual-locking Rails poly.
    representation_decision = _representation_decision_for_spec(spec_text)

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
            # #1249 — pattern proposals + anti-pattern flags
            "pattern_proposals": patterns_result.get("pattern_proposals", []),
            "antipattern_flags": patterns_result.get("antipattern_flags", []),
            # #1617 S1 — representation hatch choice
            "representation_decision": representation_decision,
            # #1631 — offline extract is draft
            "extract_mode": entities_result.get("extract_mode", "offline_deterministic"),
        },
        "clarification_needed": has_questions,
        "questions": questions,
        "warnings": [
            (
                "bootstrap_pollution: analysis.entities is untrusted draft. "
                "Close open questions with the founder → hand-author DSL from the brief's "
                "own vocabulary → validate. Counter-prior: bootstrap_pollution."
            ),
            "Do not invent chrome entities (Optional, Field, Display, …).",
        ],
        "agent_instructions": _build_instructions(
            has_questions, questions, representation_decision
        ),
        "preferred_next": [
            "Ask the founder the questions below — do not guess answers",
            "Hand-author DSL from nouns and roles the founder actually uses",
            "knowledge(operation='concept') for entity/persona/workspace syntax",
            "dsl.validate loop — never trust bootstrap entities as SSOT",
        ],
    }

    return json.dumps(briefing, indent=2)


def _representation_decision_for_spec(spec_text: str) -> dict[str, Any]:
    """Run the #1617 decide ladder on free-text / bootstrap spec."""
    try:
        return decide_representation(text=spec_text or "")
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _representation_instruction_bits(
    representation_decision: dict[str, Any] | None,
) -> list[str]:
    """#1617 S1 — inject hatch choice into generation workflow."""
    if not representation_decision or not representation_decision.get("ok"):
        return [
            (
                "4b. Data shape: run `dazzle representation decide --text <spec>` "
                "before modeling multi-parent or attachable domains. Use pattern IDs "
                "(rel.exclusive_fks, rel.poly_ref, …) — never hand-rolled subject_type+id."
            ),
        ]
    pid = representation_decision.get("pattern_id") or "rel.explicit_ref"
    return [
        (
            f"4b. Data shape (#1617): analysis.representation_decision chose **{pid}**. "
            f"Author DSL per that sketch; reject list is binding. After entities+open-via, "
            f"run `dazzle agent wall` (its Representation line is the prove). "
            f"Playbook: agent(operation=playbook, name=domain_data_shape)."
        ),
    ]


def _generation_steps(
    rep_bits: list[str],
) -> list[str]:
    """Brief-first DSL authoring — analysis is an untrusted draft; DSL is SSOT."""
    return [
        # --- Founder brief (before DSL) ---
        (
            "0a. Re-read the founder brief. analysis.entities is untrusted draft — "
            "do not author DSL from it (counter-prior bootstrap_pollution)."
        ),
        (
            "0b. Close open questions with the founder (owners, lifecycles, who sees "
            "what). Never invent chrome nouns."
        ),
        # --- Structure ---
        "1. Create dsl/ directory if it doesn't exist",
        "2. Generate module header with app name and description",
        (
            "3. Define personas from the roles the brief names (STABLE ids + human "
            "title) with default_workspace = the desk each role works from"
        ),
        # --- Data model ---
        ("4. Author entities for nouns the brief grounds (never analysis.entities chrome)"),
        *rep_bits,
        "5. Add state machines where analysis.lifecycles matches the brief",
        (
            "6. If spec mentions third-party services (payments, email, identity, etc.), "
            "check for an existing integration pack (built-in packs live in "
            "dazzle.api_kb; project packs in .dazzle/api_packs/) and run "
            "`dazzle api-pack generate-dsl <pack>` before writing integration DSL blocks."
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
            "an as: clause naming the persona(s) the rule binds to: "
            "'scope: school = current_user.school as: teacher'. "
            "Bind current_user to the owner field the founder confirmed. "
            "Every role permitted in step 7a MUST have a matching scope: rule unless "
            "the intent is to grant unrestricted row access, in which case use "
            "'scope: all as: admin'. The '*' wildcard grants all rows to all "
            "permitted personas when no per-persona scoping is needed. "
            "scope: and permit: are separate DSL blocks — never mix them. "
            "(`as:` was renamed from `for:` in #998.)"
        ),
        # --- UI ---
        "8. Generate surfaces (CRUD views) for each grounded entity",
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
        (
            "10. Create workspaces/desks per persona job with "
            "access: persona() and filters using the owner field + current_user"
        ),
        # --- Seeds ---
        (
            "10b. Seed the brief's core stories under dsl/seeds/demo_data using "
            "STABLE_PERSONA_USER_IDS (knowledge concept demo_identity)"
        ),
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
        # --- Coverage + demo loop ---
        (
            "17. If stories or processes were defined, run story(operation='coverage') "
            "to verify the generated app covers them."
        ),
        (
            "18. Demo close: dazzle serve → re-read runtime.json → "
            "demo reset-and-load -y → auth role= after reset → "
            "status(demo_world). Workflow: knowledge first_principles_demo."
        ),
    ]


def _dsl_generation_rules() -> list[str]:
    return [
        "SSOT chain: founder brief → hand-author DSL (runtime)",
        "Use knowledge(operation='concept', term=<construct>) for syntax - not examples",
        "Generate only from nouns the brief grounds — "
        "never analysis.entities (bootstrap_pollution)",
        "Generate incrementally and validate frequently",
        (
            "EVERY entity MUST have permit: blocks (role-only checks) AND scope: blocks "
            "(field conditions with as: clauses binding the rule to one or more personas). "
            "Field conditions inside permit: are a parser error. "
            "After all entities are defined, run "
            "policy(operation='access_matrix') — zero PERMIT_UNPROTECTED cells required."
        ),
        "Do NOT copy from example projects - generate from first principles",
        (
            "After validation, run sentinel(operation='findings') and "
            "semantics(operation='tenancy') as security gates."
        ),
        (
            "Data representation: honour analysis.representation_decision pattern_id; "
            "never dual-lock open-via or invent subject_type+subject_id pairs."
        ),
    ]


def _build_instructions(
    has_questions: bool,
    questions: list[dict[str, Any]],
    representation_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the agent instruction block (brief-first)."""
    rep_bits = _representation_instruction_bits(representation_decision)
    steps = _generation_steps(rep_bits)
    rules = _dsl_generation_rules()
    setup = {
        "action": "Run `dazzle agent sync` to install autonomous development commands",
        "description": (
            "Installs agent commands (/improve, /qa, /ship, etc.) that "
            "enable autonomous quality improvement and development workflows."
        ),
        "when": "after_first_successful_validate",
    }
    if has_questions:
        question_texts = [q.get("question", "") for q in questions[:5]]

        return {
            "phase": "clarification",
            "action": "ask_questions",
            "questions_to_ask": question_texts,
            "present_as": (
                "Before I author DSL, I need to close a few questions so the "
                "model stays grounded in your brief:"
            ),
            "on_answers": (
                "Record answers in the founder brief — not into bootstrap entities. "
                "Optionally refine_spec for founder prose only. Then follow generation steps."
            ),
            "generation_steps": steps,
            "representation_decision": representation_decision,
            "dsl_generation_rules": rules,
            "agent_commands_setup": setup,
        }
    return {
        "phase": "generation",
        "action": "generate_dsl",
        "representation_decision": representation_decision,
        "steps": steps,
        "dsl_generation_rules": rules,
        "agent_commands_setup": setup,
    }
