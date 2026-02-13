"""
Bootstrap handler - entry point for naive "build me an app" requests.

Scans for spec files, runs initial cognition pass, and returns a structured
mission briefing that programs the LLM agent's next steps.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..progress import ProgressContext
from ..progress import noop as _noop_progress
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
    progress: ProgressContext = arguments.get("_progress") or _noop_progress()
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
                "the refined specification, then proceed to DSL generation."
            ),
            "dsl_generation_rules": [
                "Use knowledge(operation='concept', term=<construct>) for syntax - not examples",
                "Generate incrementally: entities first, then surfaces, then workspaces",
                "After generating list surfaces, add ux blocks with sort/filter/search/empty",
                "Validate after each major section with dsl(operation='validate')",
                "Do NOT copy from example projects - generate from first principles",
            ],
        }
    else:
        return {
            "phase": "generation",
            "action": "generate_dsl",
            "steps": [
                "1. Create dsl/ directory if it doesn't exist",
                "2. Generate module header with app name and description",
                "3. Generate entity definitions based on analysis",
                "4. Add state machines for entities with lifecycles",
                "5. Generate surfaces (CRUD views) for each entity",
                (
                    "6. Add ux blocks to list surfaces: sort (default ordering), "
                    "filter (enum/bool/status fields), search (text fields users "
                    "would search by), empty messages. "
                    "Use knowledge(operation='concept', term='ux_block') for syntax"
                ),
                "7. Create workspaces for each persona",
                "8. Validate with dsl(operation='validate')",
                "9. Run dsl(operation='lint', extended=true) for quality check",
            ],
            "dsl_generation_rules": [
                "Use knowledge(operation='concept', term=<construct>) for syntax - not examples",
                "Generate incrementally and validate frequently",
                "Do NOT copy from example projects - generate from first principles",
            ],
        }
