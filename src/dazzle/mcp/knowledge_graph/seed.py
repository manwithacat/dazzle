"""
Framework knowledge seeder for the unified Knowledge Graph.

Reads semantic KB TOML files and inference KB TOML, converts them
to graph entities/relations/aliases, and writes them into the KG.

TOML files remain the source of truth — this module reads them
at seed time, not query time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.app_spec import AppSpec

    from .store import KnowledgeGraph

logger = logging.getLogger(__name__)

# Bump this when the mapping logic changes to trigger a re-seed
SEED_SCHEMA_VERSION = 8  # v8: capability discovery KG entries


def compute_seed_version() -> str:
    """Compute a composite seed version from dazzle version + schema version."""
    try:
        from dazzle._version import get_version

        dazzle_version = get_version()
    except Exception:
        dazzle_version = "unknown"
    return f"{dazzle_version}.{SEED_SCHEMA_VERSION}"


def ensure_seeded(graph: KnowledgeGraph) -> bool:
    """
    Check if the graph needs (re-)seeding and seed if so.

    Returns True if seeding was performed, False if already up-to-date.
    """
    current_version = compute_seed_version()
    stored_version = graph.get_seed_meta("seed_version")

    if stored_version == current_version:
        return False

    logger.info(
        "Seeding framework knowledge (stored=%s, current=%s)",
        stored_version,
        current_version,
    )
    seed_framework_knowledge(graph)
    return True


def seed_framework_knowledge(graph: KnowledgeGraph) -> dict[str, int]:
    """
    Seed the knowledge graph with framework knowledge from TOML files.

    Idempotent: deletes existing framework entities before re-seeding.
    FK enforcement is disabled during the delete-recreate cycle to
    prevent constraint errors from partially-deleted intermediate states.

    If seeding fails for any reason, the error is logged and an empty
    stats dict is returned — KG seeding is non-critical (#443).

    Returns stats dict with counts of what was created.
    """
    stats: dict[str, int] = {
        "concepts": 0,
        "patterns": 0,
        "inference_entries": 0,
        "changelog_entries": 0,
        "aliases": 0,
        "relations": 0,
    }

    try:
        # Disable FK enforcement during the full delete-recreate cycle.
        # The entire graph is being rebuilt from scratch — FK constraints
        # during this window are meaningless and can cause spin loops (#443).
        conn = graph._get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
        finally:
            graph._close_connection(conn)

        # Clean out old framework data
        graph.delete_by_metadata_key("source", "framework")
        graph.clear_aliases()

        # Load and seed semantic KB (concepts + patterns)
        _seed_semantic_kb(graph, stats)

        # Load and seed inference KB
        _seed_inference_kb(graph, stats)

        # Load and seed changelog guidance
        _seed_changelog(graph, stats)

        # Write seed version
        graph.set_seed_meta("seed_version", compute_seed_version())

        logger.info(
            "Seeded framework knowledge: %d concepts, %d patterns, "
            "%d inference entries, %d changelog entries, %d aliases, %d relations",
            stats["concepts"],
            stats["patterns"],
            stats["inference_entries"],
            stats["changelog_entries"],
            stats["aliases"],
            stats["relations"],
        )
    except Exception:
        logger.exception("KG seeding failed — skipping (non-critical)")
    finally:
        # Re-enable FK enforcement
        conn = graph._get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        finally:
            graph._close_connection(conn)

    return stats


def _seed_semantic_kb(graph: KnowledgeGraph, stats: dict[str, int]) -> None:
    """Seed concepts, patterns, and aliases from the semantic KB TOML files."""
    from pathlib import Path

    from dazzle.mcp.semantics_kb import ALIASES, TOML_FILES, _load_toml_file

    kb_dir = Path(__file__).parent.parent / "semantics_kb"

    concepts: dict[str, Any] = {}
    patterns: dict[str, Any] = {}

    for filename in TOML_FILES:
        filepath = kb_dir / filename
        if not filepath.exists():
            continue

        data = _load_toml_file(filepath)

        if "concepts" in data:
            concepts.update(data["concepts"])
        if "patterns" in data:
            patterns.update(data["patterns"])

    # Seed concepts as entities
    for name, concept_data in concepts.items():
        entity_id = f"concept:{name}"
        metadata: dict[str, Any] = {
            "source": "framework",
            "category": concept_data.get("category", ""),
            "definition": concept_data.get("definition", ""),
            "syntax": concept_data.get("syntax", ""),
            "example": concept_data.get("example", ""),
        }
        # Version tracking fields (optional)
        if "since_version" in concept_data:
            metadata["since_version"] = concept_data["since_version"]
        if "changed_in" in concept_data:
            metadata["changed_in"] = concept_data["changed_in"]

        graph.create_entity(
            entity_id=entity_id,
            name=name,
            entity_type="concept",
            metadata=metadata,
        )
        stats["concepts"] += 1

        # Create related_concept relations
        related = concept_data.get("related", [])
        for related_name in related:
            # Target might be a concept or pattern; create the relation
            # with auto-create so the target gets created if it doesn't exist yet
            target_id = f"concept:{related_name}"
            graph.create_relation(
                source_id=entity_id,
                target_id=target_id,
                relation_type="related_concept",
                metadata={"source": "framework"},
            )
            stats["relations"] += 1

    # Seed patterns as entities
    for name, pattern_data in patterns.items():
        entity_id = f"pattern:{name}"
        graph.create_entity(
            entity_id=entity_id,
            name=name,
            entity_type="pattern",
            metadata={
                "source": "framework",
                "description": pattern_data.get("description", ""),
                "example": pattern_data.get("example", ""),
            },
        )
        stats["patterns"] += 1

        # Create exemplifies relations from pattern to related concepts
        related = pattern_data.get("related", [])
        for related_name in related:
            target_id = f"concept:{related_name}"
            graph.create_relation(
                source_id=entity_id,
                target_id=target_id,
                relation_type="exemplifies",
                metadata={"source": "framework"},
            )
            stats["relations"] += 1

    # Seed aliases
    for alias_term, canonical_name in ALIASES.items():
        # Canonical name could be a concept or pattern; try concept first
        canonical_id = f"concept:{canonical_name}"
        # Check if the concept exists; if not, check pattern
        if graph.get_entity(canonical_id) is None:
            pattern_id = f"pattern:{canonical_name}"
            if graph.get_entity(pattern_id) is not None:
                canonical_id = pattern_id
            # else: point to concept anyway (it may get created by related_concept auto-create)

        graph.create_alias(alias_term, canonical_id)
        stats["aliases"] += 1


def seed_scene_story_relations(graph: KnowledgeGraph, app_spec: AppSpec) -> int:
    """Populate scene_exercises_story relations from rhythm scene story: refs.

    Returns the number of relations created.
    """
    count = 0
    for rhythm in app_spec.rhythms:
        for phase in rhythm.phases:
            for scene in phase.scenes:
                if scene.story:
                    source_id = f"scene:{rhythm.name}.{scene.name}"
                    target_id = f"story:{scene.story}"
                    graph.create_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type="scene_exercises_story",
                        metadata={"rhythm": rhythm.name, "phase": phase.name},
                    )
                    count += 1
    return count


def _seed_inference_kb(graph: KnowledgeGraph, stats: dict[str, int]) -> None:
    """Seed inference entries from the inference KB TOML file."""
    import tomllib
    from pathlib import Path

    kb_path = Path(__file__).parent.parent / "inference_kb.toml"
    if not kb_path.exists():
        return

    with open(kb_path, "rb") as f:
        kb = tomllib.load(f)

    # Categories and their trigger/indicator field names
    categories = [
        ("field_patterns", "triggers"),
        ("entity_archetypes", "indicators"),
        ("relationship_patterns", "triggers"),
        ("spec_language", None),  # uses "phrase" field, no triggers list
        ("domain_entities", "triggers"),
        ("workflow_templates", "triggers"),
        ("sitespec_section_inference", "triggers"),
        ("surface_inference", "triggers"),
        ("workspace_inference", "triggers"),
        ("tool_suggestions", "triggers"),
        ("modeling_guidance", "triggers"),
    ]

    for category, trigger_field in categories:
        entries = kb.get(category, [])
        for entry in entries:
            entry_id = entry.get("id") or entry.get("name") or entry.get("phrase", "")
            if not entry_id:
                continue

            # Build a unique graph ID
            safe_id = entry_id.lower().replace(" ", "_").replace("-", "_")
            entity_id = f"inference:{category}.{safe_id}"

            # Collect triggers for search
            triggers: list[str] = []
            if trigger_field and trigger_field in entry:
                triggers = entry[trigger_field]
            elif category == "spec_language":
                phrase = entry.get("phrase", "")
                if phrase:
                    triggers = [phrase]

            graph.create_entity(
                entity_id=entity_id,
                name=entry_id,
                entity_type="inference",
                metadata={
                    "source": "framework",
                    "category": category,
                    "triggers": triggers,
                    **{k: v for k, v in entry.items() if k not in ("id",)},
                },
            )
            stats["inference_entries"] += 1


def _seed_changelog(graph: KnowledgeGraph, stats: dict[str, int]) -> None:
    """Seed Agent Guidance entries from CHANGELOG.md into the KG."""
    from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance

    entries = parse_changelog_guidance(limit=50)

    for entry in entries:
        version = entry["version"]
        entity_id = f"changelog:v{version}"
        graph.create_entity(
            entity_id=entity_id,
            name=f"v{version}",
            entity_type="changelog",
            metadata={
                "source": "framework",
                "version": version,
                "guidance": entry["guidance"],
            },
        )
        stats["changelog_entries"] += 1
