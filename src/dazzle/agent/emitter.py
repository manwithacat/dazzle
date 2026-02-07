"""
DSL Emitter: converts discovery proposals into valid Dazzle DSL code.

The emitter uses template-based generation for common proposal categories
(missing CRUD surfaces, field additions, workspace scaffolding) and validates
output through the Dazzle parser with a retry loop (max 3 attempts).

Input: Proposal from the NarrativeCompiler + existing DSL context
Output: EmitResult with generated DSL code and validation status
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .compiler import CATEGORY_LABELS, Proposal, infer_crud_action

logger = logging.getLogger("dazzle.agent.emitter")


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class EmitContext:
    """
    Context for DSL emission including existing DSL state.

    Provides the emitter with knowledge of what already exists so it can
    generate non-conflicting, additive DSL.
    """

    module_name: str
    existing_entities: list[str] = field(default_factory=list)
    existing_surfaces: list[str] = field(default_factory=list)
    existing_workspaces: list[str] = field(default_factory=list)
    entity_fields: dict[str, list[EntityFieldInfo]] = field(default_factory=dict)


@dataclass
class EntityFieldInfo:
    """Minimal field information for DSL generation."""

    name: str
    type_str: str  # e.g. "str(200)", "uuid", "bool"
    is_pk: bool = False
    is_required: bool = False


@dataclass
class EmitResult:
    """Result of a DSL emission attempt."""

    proposal_id: str
    dsl_code: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    attempts: int = 1
    category: str = ""
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "proposal_id": self.proposal_id,
            "dsl_code": self.dsl_code,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "attempts": self.attempts,
            "category": self.category,
            "description": self.description,
        }


# =============================================================================
# DSL Validation
# =============================================================================

MAX_ATTEMPTS = 3


def _validate_dsl(dsl_text: str, source_label: str = "<emitted>") -> tuple[list[str], list[str]]:
    """
    Validate DSL text by parsing it through the Dazzle parser.

    Returns (errors, warnings). Empty errors means the DSL is syntactically valid.
    """
    from dazzle.core.dsl_parser_impl import parse_dsl

    errors: list[str] = []
    warnings: list[str] = []

    try:
        parse_dsl(dsl_text, Path(source_label))
    except Exception as e:
        errors.append(str(e))

    return errors, warnings


def _sanitize_identifier(name: str) -> str:
    """Convert a name to a valid DSL identifier (snake_case, no spaces)."""
    # Replace non-alphanumeric chars with underscores
    result = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())
    # Collapse multiple underscores
    result = re.sub(r"_+", "_", result)
    # Strip leading/trailing underscores
    result = result.strip("_")
    return result or "unnamed"


# =============================================================================
# Template Generators
# =============================================================================


def _generate_surface_dsl(
    entity_name: str,
    surface_name: str,
    surface_title: str,
    mode: str,
    fields: list[EntityFieldInfo],
) -> str:
    """Generate a surface DSL block."""
    lines = [
        f'surface {surface_name} "{surface_title}":',
        f"  uses entity {entity_name}",
        f"  mode: {mode}",
        "",
    ]

    # Select fields based on mode
    display_fields = _select_fields_for_mode(fields, mode)

    if display_fields:
        section_title = _section_title_for_mode(mode, entity_name)
        lines.append(f'  section main "{section_title}":')
        for f in display_fields:
            label = f.name.replace("_", " ").title()
            lines.append(f'    field {f.name} "{label}"')

    return "\n".join(lines)


def _select_fields_for_mode(
    fields: list[EntityFieldInfo],
    mode: str,
) -> list[EntityFieldInfo]:
    """Select appropriate fields for a surface mode."""
    # Exclude auto-managed fields from create/edit forms
    auto_fields = {"created_at", "updated_at"}

    if mode == "list":
        # Show key identifying fields (skip PK, auto-timestamps)
        return [
            f
            for f in fields
            if not f.is_pk and f.name not in auto_fields and f.type_str not in ("text", "json")
        ][:6]  # Limit list columns

    if mode == "view":
        # Show all fields except raw PK
        return [f for f in fields if not f.is_pk]

    if mode in ("create", "edit"):
        # Show editable fields only
        return [f for f in fields if not f.is_pk and f.name not in auto_fields]

    return [f for f in fields if not f.is_pk]


def _section_title_for_mode(mode: str, entity_name: str) -> str:
    """Generate a section title based on mode."""
    titles = {
        "list": f"{entity_name}s",
        "view": f"{entity_name} Details",
        "create": f"New {entity_name}",
        "edit": f"Edit {entity_name}",
    }
    return titles.get(mode, entity_name)


def _emit_missing_crud(
    proposal: Proposal,
    context: EmitContext,
) -> str:
    """Generate DSL for a missing CRUD operation."""
    # Determine which entity and what CRUD action
    entity_name = _primary_entity(proposal)
    if not entity_name:
        return f"# TODO: Missing CRUD operation — {proposal.title}\n# Could not determine target entity"

    fields = context.entity_fields.get(entity_name, [])
    if not fields:
        return f"# TODO: Missing CRUD for {entity_name}\n# Entity fields not available in context"

    # Infer which modes are missing
    action = _infer_missing_action(proposal)
    mode_map = {
        "create": "create",
        "edit": "edit",
        "delete": None,  # No DSL surface mode for delete
        "view": "view",
        "list": "list",
        "CRUD": None,  # Generate multiple
    }

    mode = mode_map.get(action)

    if action == "CRUD":
        # Generate all missing standard surfaces
        return _emit_full_crud_set(entity_name, fields, context)

    if mode is None:
        # Delete or unknown — emit a comment with guidance
        return (
            f"# TODO: {proposal.title}\n"
            f"# Delete operations are handled via surface actions, not standalone surfaces.\n"
            f"# Add an action block to an existing {entity_name} view or list surface."
        )

    # Generate single surface
    safe_entity = _sanitize_identifier(entity_name)
    surface_name = f"{safe_entity}_{mode}"
    surface_title = f"{action.title()} {entity_name}"

    # Avoid conflicts with existing surfaces
    surface_name = _unique_name(surface_name, context.existing_surfaces)

    return _generate_surface_dsl(entity_name, surface_name, surface_title, mode, fields)


def _emit_full_crud_set(
    entity_name: str,
    fields: list[EntityFieldInfo],
    context: EmitContext,
) -> str:
    """Generate a full set of CRUD surfaces for an entity."""
    safe_entity = _sanitize_identifier(entity_name)
    blocks: list[str] = []

    for mode in ("list", "view", "create", "edit"):
        surface_name = f"{safe_entity}_{mode}"
        if surface_name in context.existing_surfaces:
            continue  # Already exists

        surface_name = _unique_name(surface_name, context.existing_surfaces)
        title_verb = {"list": "", "view": "", "create": "Create ", "edit": "Edit "}
        title = f"{title_verb[mode]}{entity_name}" if mode in ("create", "edit") else entity_name
        if mode == "list":
            title = f"{entity_name} List"
        elif mode == "view":
            title = f"{entity_name} Detail"

        blocks.append(_generate_surface_dsl(entity_name, surface_name, title, mode, fields))

    return "\n\n".join(blocks) if blocks else f"# All CRUD surfaces already exist for {entity_name}"


def _emit_ux_issue(
    proposal: Proposal,
    context: EmitContext,
) -> str:
    """Generate DSL for a UX improvement (ux: block additions)."""
    surfaces = proposal.affected_surfaces
    if not surfaces:
        return f"# TODO: UX improvement — {proposal.title}\n# No target surface identified"

    surface_name = surfaces[0]
    lines = [
        f"# UX improvement for {surface_name}",
        f"# Proposal: {proposal.title}",
        "#",
        f"# Add the following ux: block to surface {surface_name}:",
        "#",
        "#   ux:",
    ]

    # Suggest relevant UX properties based on the issue description
    desc_lower = (proposal.narrative + " " + proposal.title).lower()
    if "validation" in desc_lower or "required" in desc_lower:
        lines.append(f'#     purpose: "Complete {surface_name} with validation"')
    if "sort" in desc_lower:
        lines.append("#     sort: created_at desc")
    if "search" in desc_lower or "filter" in desc_lower:
        lines.append("#     search: name, title")
    if "empty" in desc_lower:
        lines.append('#     empty: "No items yet."')

    return "\n".join(lines)


def _emit_workflow_gap(
    proposal: Proposal,
    context: EmitContext,
) -> str:
    """Generate DSL stub for a workflow gap (state machine or process)."""
    entity_name = _primary_entity(proposal)
    if not entity_name:
        return f"# TODO: Workflow gap — {proposal.title}"

    lines = [
        f"# Workflow gap: {proposal.title}",
        f"# Consider adding a state machine to entity {entity_name}:",
        "#",
        f"# entity {entity_name}:",
        "#   ...",
        "#   status: enum[draft,active,completed]",
        "#",
        "#   state_machine:",
        "#     initial: draft",
        "#     transitions:",
        "#       activate: draft -> active",
        "#       complete: active -> completed",
    ]

    return "\n".join(lines)


def _emit_navigation_gap(
    proposal: Proposal,
    context: EmitContext,
) -> str:
    """Generate DSL for a navigation gap (workspace addition)."""
    entity_name = _primary_entity(proposal)
    surfaces = proposal.affected_surfaces or []

    if not entity_name and not surfaces:
        return f"# TODO: Navigation gap — {proposal.title}"

    # Try to get the actual workspace name from headless discovery metadata
    ws_name: str | None = None
    for obs in proposal.observations:
        ws_name = (obs.metadata or {}).get("default_workspace")
        if ws_name:
            break
    if not ws_name:
        ws_name = proposal.metadata.get("default_workspace")
    if not ws_name:
        # Fall back to deriving from entity/surface name
        safe_name = _sanitize_identifier(entity_name or surfaces[0] if surfaces else "main")
        ws_name = _unique_name(safe_name, context.existing_workspaces)

    ws_title = (entity_name or ws_name).replace("_", " ").title()

    lines = [
        f'workspace {ws_name} "{ws_title}":',
        f'  purpose: "Navigate {entity_name or "application"} features"',
    ]

    # Add regions for known surfaces
    for surface in surfaces[:4]:
        lines.append("")
        lines.append(f"  {surface}:")
        lines.append(f"    source: {entity_name or 'Unknown'}")
        lines.append("    display: list")

    return "\n".join(lines)


def _emit_generic(
    proposal: Proposal,
    context: EmitContext,
) -> str:
    """Generate a TODO comment for proposals that can't be templated."""
    cat_label = CATEGORY_LABELS.get(proposal.category, proposal.category)
    lines = [
        f"# TODO: [{cat_label}] {proposal.title}",
        f"# Priority: {proposal.priority} | Severity: {proposal.severity}",
    ]

    if proposal.affected_entities:
        lines.append(f"# Entities: {', '.join(proposal.affected_entities)}")
    if proposal.locations:
        lines.append(f"# Locations: {', '.join(proposal.locations)}")

    lines.append("#")
    # Include narrative as wrapped comment
    for line in proposal.narrative.split("\n"):
        lines.append(f"# {line}")

    return "\n".join(lines)


# =============================================================================
# Helpers
# =============================================================================


def _primary_entity(proposal: Proposal) -> str | None:
    """Extract the primary entity from a proposal."""
    for ent in proposal.affected_entities:
        # Skip surface references
        if not ent.startswith("surface:") and ent[0].isupper():
            return ent
    # Fallback: any entity
    return proposal.affected_entities[0] if proposal.affected_entities else None


def _infer_missing_action(proposal: Proposal) -> str:
    """Infer which CRUD action is missing from proposal text."""
    return infer_crud_action(proposal.title + " " + proposal.narrative)


def _unique_name(base: str, existing: list[str]) -> str:
    """Generate a unique name by appending a suffix if needed."""
    if base not in existing:
        return base
    for i in range(2, 100):
        candidate = f"{base}_{i}"
        if candidate not in existing:
            return candidate
    return f"{base}_new"


# =============================================================================
# DSL Emitter
# =============================================================================


# Map proposal categories to template generators
_CATEGORY_EMITTERS: dict[str, Any] = {
    "missing_crud": _emit_missing_crud,
    "ux_issue": _emit_ux_issue,
    "workflow_gap": _emit_workflow_gap,
    "navigation_gap": _emit_navigation_gap,
    "access_gap": _emit_generic,
    "data_gap": _emit_generic,
    "gap": _emit_generic,
}


class DslEmitter:
    """
    Converts discovery proposals into valid Dazzle DSL code.

    Uses template-based generation for common patterns (missing CRUD surfaces,
    UX improvements, workspace scaffolding) and validates output through the
    Dazzle parser with a retry loop.

    Usage:
        emitter = DslEmitter()
        context = EmitContext.from_appspec(appspec)
        result = emitter.emit(proposal, context)
    """

    def __init__(self, max_attempts: int = MAX_ATTEMPTS) -> None:
        self._max_attempts = max_attempts

    def emit(self, proposal: Proposal, context: EmitContext) -> EmitResult:
        """
        Generate DSL for a single proposal.

        Selects a template based on proposal category, generates DSL,
        validates through the parser, and retries with fixes on failure.
        """
        emitter_fn = _CATEGORY_EMITTERS.get(proposal.category, _emit_generic)
        dsl_code = emitter_fn(proposal, context)

        # If the result is purely comments/TODOs, skip validation
        if _is_comment_only(dsl_code):
            return EmitResult(
                proposal_id=proposal.id,
                dsl_code=dsl_code,
                valid=True,
                category=proposal.category,
                description=f"Guidance for: {proposal.title}",
            )

        # Wrap in minimal module context for validation
        wrapped = _wrap_for_validation(dsl_code, context)

        # Validate with retry loop
        errors: list[str] = []
        warnings: list[str] = []
        attempts = 0

        for attempt in range(1, self._max_attempts + 1):
            attempts = attempt
            errors, warnings = _validate_dsl(wrapped)

            if not errors:
                break

            # Try to fix common issues
            fixed = _attempt_fix(dsl_code, errors)
            if fixed == dsl_code:
                # No fix was applied, stop retrying
                break
            dsl_code = fixed
            wrapped = _wrap_for_validation(dsl_code, context)

        return EmitResult(
            proposal_id=proposal.id,
            dsl_code=dsl_code,
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            attempts=attempts,
            category=proposal.category,
            description=f"DSL for: {proposal.title}",
        )

    def emit_batch(
        self,
        proposals: list[Proposal],
        context: EmitContext,
    ) -> list[EmitResult]:
        """Generate DSL for multiple proposals."""
        return [self.emit(p, context) for p in proposals]

    def emit_report(self, results: list[EmitResult]) -> str:
        """Generate a markdown report of emission results."""
        if not results:
            return "# DSL Emission Report\n\nNo proposals to emit."

        valid_count = sum(1 for r in results if r.valid)
        total = len(results)

        lines = [
            "# DSL Emission Report",
            "",
            f"**Total:** {total} | **Valid:** {valid_count} | **Errors:** {total - valid_count}",
            "",
        ]

        # Valid emissions
        valid_results = [r for r in results if r.valid and not _is_comment_only(r.dsl_code)]
        if valid_results:
            lines.append("## Generated DSL")
            lines.append("")
            for r in valid_results:
                lines.append(f"### {r.proposal_id}: {r.description}")
                lines.append("")
                lines.append("```dsl")
                lines.append(r.dsl_code)
                lines.append("```")
                lines.append("")

        # Guidance-only results (comment blocks)
        guidance_results = [r for r in results if r.valid and _is_comment_only(r.dsl_code)]
        if guidance_results:
            lines.append("## Guidance (Manual Implementation Required)")
            lines.append("")
            for r in guidance_results:
                lines.append(f"### {r.proposal_id}: {r.description}")
                lines.append("")
                lines.append("```")
                lines.append(r.dsl_code)
                lines.append("```")
                lines.append("")

        # Failed emissions
        failed_results = [r for r in results if not r.valid]
        if failed_results:
            lines.append("## Failed Emissions")
            lines.append("")
            for r in failed_results:
                lines.append(f"### {r.proposal_id}: {r.description}")
                lines.append(f"**Attempts:** {r.attempts}")
                lines.append("")
                lines.append("Errors:")
                for err in r.errors:
                    lines.append(f"- {err}")
                lines.append("")
                lines.append("Generated (invalid) DSL:")
                lines.append("```dsl")
                lines.append(r.dsl_code)
                lines.append("```")
                lines.append("")

        return "\n".join(lines)


# =============================================================================
# Validation Helpers
# =============================================================================


def _is_comment_only(dsl_code: str) -> bool:
    """Check if DSL code is only comments and whitespace."""
    for line in dsl_code.strip().split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return False
    return True


def _wrap_for_validation(dsl_code: str, context: EmitContext) -> str:
    """Wrap generated DSL in module context for parser validation."""
    # Build minimal entity stubs for referenced entities
    entity_stubs: list[str] = []
    for entity_name, fields in context.entity_fields.items():
        stub_lines = [f'entity {entity_name} "{entity_name}":']
        for f in fields:
            modifiers = ""
            if f.is_pk:
                modifiers += " pk"
            if f.is_required:
                modifiers += " required"
            stub_lines.append(f"  {f.name}: {f.type_str}{modifiers}")
        entity_stubs.append("\n".join(stub_lines))

    parts = [
        f"module {context.module_name}",
        f'app _emit_validation "{context.module_name}"',
    ]
    parts.extend(entity_stubs)
    parts.append("")
    parts.append(dsl_code)

    return "\n\n".join(parts)


def _attempt_fix(dsl_code: str, errors: list[str]) -> str:
    """
    Attempt to fix common DSL syntax errors.

    Returns the fixed DSL or the original if no fix was applied.
    """
    fixed = dsl_code

    for error in errors:
        error_lower = error.lower()

        # Fix: missing quotes around string titles
        if "expected string" in error_lower or "unterminated string" in error_lower:
            # Try to add missing quotes to titles
            fixed = re.sub(
                r"^(surface \w+) (\w[\w\s]+):",
                r'\1 "\2":',
                fixed,
                flags=re.MULTILINE,
            )

        # Fix: invalid identifier (spaces in names)
        if "invalid identifier" in error_lower or "expected identifier" in error_lower:
            # Replace spaces in identifiers with underscores
            fixed = re.sub(
                r"^(surface|workspace|entity) (\w+\s\w+)",
                lambda m: f"{m.group(1)} {_sanitize_identifier(m.group(2))}",
                fixed,
                flags=re.MULTILINE,
            )

        # Fix: indentation issues — normalize to 2-space indent
        if "indent" in error_lower:
            new_lines = []
            for line in fixed.split("\n"):
                if line and not line[0].isspace() and not line.startswith("#"):
                    new_lines.append(line)
                elif line.strip():
                    # Count leading whitespace and normalize
                    stripped = line.lstrip()
                    indent_level = (len(line) - len(stripped)) // 2
                    indent_level = max(1, min(indent_level, 4))
                    new_lines.append("  " * indent_level + stripped)
                else:
                    new_lines.append(line)
            fixed = "\n".join(new_lines)

    return fixed


# =============================================================================
# Context Builder
# =============================================================================


def build_emit_context(appspec: Any) -> EmitContext:
    """
    Build an EmitContext from an AppSpec.

    Extracts entity names, surface names, workspace names, and field info
    from the parsed AppSpec to provide full context for DSL emission.
    """
    entity_names: list[str] = []
    surface_names: list[str] = []
    workspace_names: list[str] = []
    entity_fields: dict[str, list[EntityFieldInfo]] = {}

    # Entities
    entities = appspec.domain.entities if hasattr(appspec.domain, "entities") else []
    for entity in entities:
        entity_names.append(entity.name)
        fields: list[EntityFieldInfo] = []
        for f in entity.fields:
            type_str = _field_type_to_str(f)
            fields.append(
                EntityFieldInfo(
                    name=f.name,
                    type_str=type_str,
                    is_pk=getattr(f, "pk", False) or "pk" in str(getattr(f, "constraints", "")),
                    is_required=getattr(f, "required", False)
                    or "required" in str(getattr(f, "constraints", "")),
                )
            )
        entity_fields[entity.name] = fields

    # Surfaces
    for surface in appspec.surfaces:
        surface_names.append(surface.name)

    # Workspaces
    for ws in appspec.workspaces:
        workspace_names.append(ws.name)

    # Module name
    module_name = getattr(appspec, "name", "app") or "app"

    return EmitContext(
        module_name=module_name,
        existing_entities=entity_names,
        existing_surfaces=surface_names,
        existing_workspaces=workspace_names,
        entity_fields=entity_fields,
    )


def _field_type_to_str(field_spec: Any) -> str:
    """Convert a field spec's type to its DSL string representation."""
    ft = getattr(field_spec, "type", None)
    if ft is None:
        return "str"

    kind = getattr(ft, "kind", str(ft))
    kind_str = str(kind).split(".")[-1].lower() if "." in str(kind) else str(kind).lower()

    # Handle parameterized types
    max_length = getattr(ft, "max_length", None)
    if max_length and kind_str == "str":
        return f"str({max_length})"

    precision = getattr(ft, "precision", None)
    scale = getattr(ft, "scale", None)
    if precision and kind_str == "decimal":
        return f"decimal({precision},{scale or 0})"

    enum_values = getattr(ft, "enum_values", None)
    if enum_values and kind_str == "enum":
        return f"enum[{','.join(enum_values)}]"

    ref_entity = getattr(ft, "ref_entity", None)
    if ref_entity and kind_str in ("ref", "has_many", "has_one", "embeds", "belongs_to"):
        return f"{kind_str} {ref_entity}"

    return kind_str
