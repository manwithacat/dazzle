"""Demo data tool handlers.

Handles demo blueprint proposal, saving, loading, and data generation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

logger = logging.getLogger("dazzle.mcp")

NATO_PREFIXES = [
    "Alpha",
    "Bravo",
    "Charlie",
    "Delta",
    "Echo",
    "Foxtrot",
    "Golf",
    "Hotel",
    "India",
    "Juliet",
    "Kilo",
    "Lima",
]


def _infer_domain_suffix(domain_description: str) -> str:
    """Infer a domain suffix from the description."""
    desc_lower = domain_description.lower()

    # Domain patterns
    if any(w in desc_lower for w in ["solar", "renewable", "energy", "battery"]):
        return "Solar Ltd"
    elif any(w in desc_lower for w in ["property", "letting", "estate", "rental"]):
        return "Lettings Ltd"
    elif any(w in desc_lower for w in ["account", "finance", "tax", "bookkeep"]):
        return "Finance Ltd"
    elif any(w in desc_lower for w in ["task", "project", "todo"]):
        return "Tasks Ltd"
    elif any(w in desc_lower for w in ["crm", "client", "customer"]):
        return "Services Ltd"
    else:
        return "Ltd"


def _infer_field_strategy(
    field_name: str, field_type: str, entity_name: str, is_enum: bool = False
) -> tuple[str, dict[str, Any]]:
    """Infer a field strategy from field name and type."""
    name_lower = field_name.lower()

    # Primary key / ID fields
    if name_lower == "id" or name_lower.endswith("_id") and "uuid" in field_type.lower():
        return "uuid_generate", {}

    # Foreign key fields
    if name_lower.endswith("_id"):
        target = field_name[:-3]  # Remove _id suffix
        return "foreign_key", {"target_entity": target.title(), "target_field": "id"}

    # Person name patterns
    if any(w in name_lower for w in ["name", "full_name", "first_name", "last_name"]):
        return "person_name", {"locale": "en_GB"}

    # Company name patterns
    if any(w in name_lower for w in ["company", "organization", "business"]):
        return "company_name", {}

    # Email patterns
    if "email" in name_lower:
        return "email_from_name", {"source_field": "full_name", "domains": ["example.test"]}

    # Username patterns
    if "username" in name_lower:
        return "username_from_name", {"source_field": "full_name"}

    # Password patterns
    if "password" in name_lower:
        return "hashed_password_placeholder", {"plaintext_demo_password": "Demo1234!"}

    # Boolean patterns
    if (
        field_type.lower() == "bool"
        or name_lower.startswith("is_")
        or name_lower.startswith("has_")
    ):
        return "boolean_weighted", {"true_weight": 0.3}

    # Date patterns
    if any(w in name_lower for w in ["date", "created", "updated", "at"]):
        return "date_relative", {"anchor": "today", "min_offset_days": -365, "max_offset_days": 0}

    # Currency/amount patterns
    if any(w in name_lower for w in ["amount", "price", "total", "cost", "value"]):
        return "currency_amount", {"min": 10, "max": 10000, "decimals": 2}

    # Numeric patterns
    if field_type.lower() in ["int", "integer"]:
        return "numeric_range", {"min": 1, "max": 100}

    # Enum fields
    if is_enum:
        return "enum_weighted", {"enum_values": [], "weights": []}

    # Text patterns
    if any(w in name_lower for w in ["description", "notes", "comments", "text"]):
        return "free_text_lorem", {"min_words": 5, "max_words": 20}

    # Title patterns
    if any(w in name_lower for w in ["title", "subject", "heading"]):
        return "free_text_lorem", {"min_words": 3, "max_words": 8}

    # Default to lorem text
    return "free_text_lorem", {"min_words": 2, "max_words": 5}


def propose_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze DSL and propose a Demo Data Blueprint."""
    from dazzle.core.ir.demo_blueprint import (
        DemoDataBlueprint,
        EntityBlueprint,
        FieldPattern,
        FieldStrategy,
        PersonaBlueprint,
        TenantBlueprint,
    )

    domain_description = args.get("domain_description", "")
    tenant_count = args.get("tenant_count", 2)
    filter_entities = args.get("entities")  # v0.14.2: Optional entity filter for chunking
    include_metadata = args.get(
        "include_metadata", True
    )  # v0.14.2: Skip tenants/personas for batches
    quick_mode = args.get("quick_mode", False)  # v0.14.2: Minimal demo data generation

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # v0.14.2: Warn about large projects
        total_entities = len(app_spec.domain.entities)
        warnings: list[str] = []
        if total_entities > 15 and not filter_entities:
            warnings.append(
                f"Large project detected ({total_entities} entities). "
                f"Consider using 'entities' parameter to generate in batches of 10-15 to avoid truncation."
            )

        # Generate tenant blueprints (only if include_metadata)
        tenants = []
        if include_metadata:
            domain_suffix = _infer_domain_suffix(domain_description)
            for i in range(min(tenant_count, len(NATO_PREFIXES))):
                prefix = NATO_PREFIXES[i]
                slug = f"{prefix.lower()}-{domain_suffix.replace(' ', '-').lower()}"
                tenants.append(
                    TenantBlueprint(
                        name=f"{prefix} {domain_suffix}",
                        slug=slug,
                        notes=f"Demo tenant {i + 1}" if i == 0 else None,
                    )
                )

        # Generate persona blueprints from DSL personas (only if include_metadata)
        personas = []
        if include_metadata:
            for persona in app_spec.personas:
                personas.append(
                    PersonaBlueprint(
                        persona_name=persona.label or persona.id,
                        description=persona.description or f"{persona.label or persona.id} user",
                        default_role=f"role_{persona.id.lower()}",
                        default_user_count=2 if persona.id.lower() in ["staff", "user"] else 1,
                    )
                )

            # Default personas if none defined
            if not personas:
                personas = [
                    PersonaBlueprint(
                        persona_name="Staff",
                        description="Regular staff users",
                        default_role="role_staff",
                        default_user_count=3,
                    ),
                ]

        # v0.14.2: Filter entities if specified
        dsl_entities = app_spec.domain.entities
        if filter_entities:
            filter_set = set(filter_entities)
            dsl_entities = [e for e in dsl_entities if e.name in filter_set]
            if len(dsl_entities) < len(filter_entities):
                found = {e.name for e in dsl_entities}
                missing = filter_set - found
                warnings.append(f"Entities not found in DSL: {', '.join(sorted(missing))}")

        # v0.14.2: Quick mode - prioritize entities with surfaces
        if quick_mode and not filter_entities:
            # Find entities referenced by surfaces
            surface_entities = {s.entity_ref for s in app_spec.surfaces if s.entity_ref}
            # Also include entities referenced by those entities (one level)
            ref_entities: set[str] = set()
            for entity in app_spec.domain.entities:
                if entity.name in surface_entities:
                    for field in entity.fields:
                        if field.type.ref_entity:
                            ref_entities.add(field.type.ref_entity)

            priority_entities = surface_entities | ref_entities
            if priority_entities:
                dsl_entities = [e for e in dsl_entities if e.name in priority_entities]
                warnings.append(
                    f"Quick mode: Selected {len(dsl_entities)} entities with surfaces/references "
                    f"(skipped {total_entities - len(dsl_entities)} others)"
                )

        # Generate entity blueprints
        entities = []
        for entity in dsl_entities:
            # Check for tenant_id field
            tenant_scoped = any(f.name == "tenant_id" for f in entity.fields)

            # Generate field patterns
            field_patterns = []
            for field in entity.fields:
                # Detect field type
                field_type_str = field.type.kind.value if field.type and field.type.kind else "str"
                is_enum = bool(field.type and field.type.kind and field.type.kind.value == "enum")

                strategy, params = _infer_field_strategy(
                    field.name, field_type_str, entity.name, is_enum
                )

                # Add enum values if applicable
                if is_enum and field.type.enum_values:
                    params["enum_values"] = field.type.enum_values
                    params["weights"] = [1.0 / len(field.type.enum_values)] * len(
                        field.type.enum_values
                    )

                field_patterns.append(
                    FieldPattern(
                        field_name=field.name,
                        strategy=FieldStrategy(strategy),
                        params=params,
                    )
                )

            # Determine row count based on entity type
            if quick_mode:
                # v0.14.2: Quick mode uses minimal row counts
                row_count = 5
                if entity.name.lower() in ["user", "tenant"]:
                    row_count = 0  # Generated from personas/tenants
            else:
                row_count = 20
                if entity.name.lower() in ["user", "tenant"]:
                    row_count = 0  # Generated from personas/tenants
                elif entity.name.lower() in ["invoice", "order", "transaction"]:
                    row_count = 100
                elif entity.name.lower() in ["client", "customer", "contact"]:
                    row_count = 30

            entities.append(
                EntityBlueprint(
                    name=entity.name,
                    row_count_default=row_count,
                    notes=entity.title,
                    tenant_scoped=tenant_scoped,
                    field_patterns=field_patterns,
                )
            )

        # Create blueprint
        blueprint = DemoDataBlueprint(
            project_id=manifest.name or project_root.name,
            domain_description=domain_description,
            seed=42,
            tenants=tenants,
            personas=personas,
            entities=entities,
        )

        # Convert to JSON
        blueprint_data = blueprint.model_dump(mode="json")

        # v0.14.2: Build response with warnings and chunking info
        response: dict[str, Any] = {
            "status": "proposed",
            "project_path": str(project_root),
            "total_dsl_entities": total_entities,
            "included_entities": len(entities),
            "tenant_count": len(tenants),
            "persona_count": len(personas),
        }

        # Add chunking guidance for large projects
        if filter_entities:
            response["note"] = (
                f"Generated blueprint for {len(entities)} of {total_entities} entities. "
                f"Merge with existing blueprint using save_demo_blueprint."
            )
        else:
            response["note"] = "Review and adjust, then call save_demo_blueprint to persist."

        if warnings:
            response["warnings"] = warnings

        # v0.14.2: List all entity names for chunking guidance
        if total_entities > 15 and not filter_entities:
            all_entity_names = [e.name for e in app_spec.domain.entities]
            response["all_entity_names"] = all_entity_names
            response["chunking_suggestion"] = {
                "batch_size": 10,
                "batch_count": (total_entities + 9) // 10,
                "example_call": {
                    "entities": all_entity_names[:10],
                    "include_metadata": True,
                },
            }

        response["blueprint"] = blueprint_data

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save a Demo Data Blueprint to .dazzle/demo_data/blueprint.json."""
    from dazzle.core.demo_blueprint_persistence import load_blueprint, save_blueprint
    from dazzle.core.ir.demo_blueprint import DemoDataBlueprint

    blueprint_data = args.get("blueprint")
    merge_entities = args.get("merge", False)  # v0.14.2: Merge with existing blueprint
    validate_coverage = args.get("validate", True)  # v0.14.2: Validate against DSL

    if not blueprint_data:
        return json.dumps({"error": "blueprint parameter required"})

    try:
        # Validate and create blueprint
        new_blueprint = DemoDataBlueprint.model_validate(blueprint_data)
        warnings: list[str] = []

        # v0.14.2: Merge with existing blueprint if requested
        if merge_entities:
            existing = load_blueprint(project_root)
            if existing:
                # Merge entities (new ones override existing)
                existing_entity_names = {e.name for e in existing.entities}
                new_entity_names = {e.name for e in new_blueprint.entities}

                merged_entities = list(new_blueprint.entities)
                for entity in existing.entities:
                    if entity.name not in new_entity_names:
                        merged_entities.append(entity)

                # Use existing tenants/personas if new blueprint doesn't have them
                tenants = new_blueprint.tenants if new_blueprint.tenants else existing.tenants
                personas = new_blueprint.personas if new_blueprint.personas else existing.personas

                new_blueprint = DemoDataBlueprint(
                    project_id=new_blueprint.project_id or existing.project_id,
                    domain_description=new_blueprint.domain_description
                    or existing.domain_description,
                    seed=new_blueprint.seed or existing.seed,
                    tenants=tenants,
                    personas=personas,
                    entities=merged_entities,
                )

                added_count = len(new_entity_names - existing_entity_names)
                warnings.append(
                    f"Merged {added_count} new entities with {len(existing_entity_names)} existing"
                )

        # v0.14.2: Validate coverage against DSL
        if validate_coverage:
            try:
                manifest = load_manifest(project_root / "dazzle.toml")
                dsl_files = discover_dsl_files(project_root, manifest)
                modules = parse_modules(dsl_files)
                app_spec = build_appspec(modules, manifest.project_root)

                dsl_entity_names = {e.name for e in app_spec.domain.entities}
                blueprint_entity_names = {e.name for e in new_blueprint.entities}

                # Check for missing entities
                missing = dsl_entity_names - blueprint_entity_names
                if missing:
                    warnings.append(
                        f"Blueprint missing {len(missing)} DSL entities: {', '.join(sorted(missing)[:5])}"
                        + (f"... and {len(missing) - 5} more" if len(missing) > 5 else "")
                    )

                # Check for entities with no field patterns
                empty_patterns = [e.name for e in new_blueprint.entities if not e.field_patterns]
                if empty_patterns:
                    warnings.append(
                        f"{len(empty_patterns)} entities have no field_patterns: {', '.join(empty_patterns[:3])}"
                        + (
                            f"... and {len(empty_patterns) - 3} more"
                            if len(empty_patterns) > 3
                            else ""
                        )
                    )

            except Exception as e:
                warnings.append(f"Could not validate against DSL: {e}")

        # Save blueprint
        blueprint_file = save_blueprint(project_root, new_blueprint)

        response: dict[str, Any] = {
            "status": "saved",
            "file": str(blueprint_file),
            "project_id": new_blueprint.project_id,
            "tenant_count": len(new_blueprint.tenants),
            "persona_count": len(new_blueprint.personas),
            "entity_count": len(new_blueprint.entities),
        }

        if warnings:
            response["warnings"] = warnings

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load the current Demo Data Blueprint."""
    from dazzle.core.demo_blueprint_persistence import get_blueprint_file, load_blueprint

    try:
        blueprint = load_blueprint(project_root)
        blueprint_file = get_blueprint_file(project_root)

        if blueprint is None:
            return json.dumps(
                {
                    "status": "not_found",
                    "file": str(blueprint_file),
                    "message": "No blueprint found. Use propose_demo_blueprint to create one.",
                }
            )

        return json.dumps(
            {
                "status": "loaded",
                "file": str(blueprint_file),
                "blueprint": blueprint.model_dump(mode="json"),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def generate_demo_data_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate demo data files from the blueprint."""
    from dazzle.core.demo_blueprint_persistence import load_blueprint
    from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator

    output_format = args.get("format", "csv")
    output_dir = args.get("output_dir", "demo_data")
    filter_entities = args.get("entities")

    try:
        blueprint = load_blueprint(project_root)
        if blueprint is None:
            return json.dumps(
                {
                    "status": "no_blueprint",
                    "message": "No blueprint found. Use propose_demo_blueprint first.",
                }
            )

        # v0.14.2: Pre-generation diagnostics
        warnings: list[str] = []
        diagnostics: dict[str, Any] = {}

        # Check for entities with no field patterns
        empty_pattern_entities = [e.name for e in blueprint.entities if not e.field_patterns]
        if empty_pattern_entities:
            warnings.append(
                f"{len(empty_pattern_entities)} entities have no field_patterns and will generate empty files: "
                f"{', '.join(empty_pattern_entities[:5])}"
                + (
                    f"... and {len(empty_pattern_entities) - 5} more"
                    if len(empty_pattern_entities) > 5
                    else ""
                )
            )
            diagnostics["empty_pattern_entities"] = empty_pattern_entities

        # Check for entities with 0 row_count
        zero_row_entities = [
            e.name
            for e in blueprint.entities
            if e.row_count_default == 0 and e.name.lower() not in ["user", "tenant"]
        ]
        if zero_row_entities:
            warnings.append(
                f"{len(zero_row_entities)} entities have row_count_default=0: {', '.join(zero_row_entities[:5])}"
            )

        # Create generator
        generator = BlueprintDataGenerator(blueprint)

        # Generate data
        output_path = project_root / output_dir
        files = generator.generate_all(
            output_path,
            format=output_format,
            entities=filter_entities,
        )

        # v0.14.2: Post-generation diagnostics
        total_rows = sum(generator.row_counts.values())
        entities_with_data = [name for name, count in generator.row_counts.items() if count > 0]
        entities_without_data = [name for name, count in generator.row_counts.items() if count == 0]

        if entities_without_data:
            warnings.append(
                f"{len(entities_without_data)} entities generated 0 rows: {', '.join(entities_without_data[:5])}"
                + (
                    f"... and {len(entities_without_data) - 5} more"
                    if len(entities_without_data) > 5
                    else ""
                )
            )

        if total_rows == 0:
            warnings.append(
                "No data was generated! Check that field_patterns are defined for entities. "
                "Re-run propose_demo_blueprint with specific entities to regenerate patterns."
            )

        # Get login matrix
        login_matrix = generator.get_login_matrix()
        login_file = output_path / "login_matrix.md"
        login_file.write_text(login_matrix, encoding="utf-8")

        response: dict[str, Any] = {
            "status": "generated",
            "output_dir": str(output_path),
            "format": output_format,
            "files": {name: str(path) for name, path in files.items()},
            "login_matrix": str(login_file),
            "total_rows": total_rows,
            "row_counts": generator.row_counts,
            "entities_with_data": len(entities_with_data),
            "entities_without_data": len(entities_without_data),
        }

        if warnings:
            response["warnings"] = warnings

        if diagnostics:
            response["diagnostics"] = diagnostics

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
