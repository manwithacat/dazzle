"""DSL test tool handlers.

Handles DSL test generation, execution, coverage analysis, and listing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp")


def generate_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate tests from DSL/AppSpec definitions."""
    try:
        from dazzle.testing.dsl_test_generator import (
            generate_tests_from_dsl,
            save_generated_tests,
        )

        # Generate tests (function handles loading appspec internally)
        test_suite = generate_tests_from_dsl(project_root)

        # Optionally save
        save = args.get("save", False)
        if save:
            save_generated_tests(project_root, test_suite)

        # Build response
        coverage = test_suite.coverage
        categories: dict[str, int] = {}
        for design in test_suite.designs:
            tags = design.get("tags", [])
            cat = next((t for t in tags if t not in ("generated", "dsl-derived")), "other")
            categories[cat] = categories.get(cat, 0) + 1

        result: dict[str, Any] = {
            "project": test_suite.project_name,
            "total_tests": len(test_suite.designs),
            "dsl_hash": test_suite.dsl_hash[:12],
            "categories": categories,
            "coverage": {
                "entities": f"{len(coverage.entities_covered)}/{coverage.entities_total}",
                "state_machines": f"{len(coverage.state_machines_covered)}/{coverage.state_machines_total}",
                "personas": f"{len(coverage.personas_covered)}/{coverage.personas_total}",
                "workspaces": f"{len(coverage.workspaces_covered)}/{coverage.workspaces_total}",
            },
        }

        if coverage.events_total > 0:
            result["coverage"]["events"] = f"{len(coverage.events_covered)}/{coverage.events_total}"
        if coverage.processes_total > 0:
            result["coverage"]["processes"] = (
                f"{len(coverage.processes_covered)}/{coverage.processes_total}"
            )

        if save:
            result["saved_to"] = str(project_root / "dsl" / "tests")

        return json.dumps(result, indent=2)

    except ImportError as e:
        return json.dumps({"error": f"Testing module not available: {e}"}, indent=2)
    except Exception as e:
        logger.exception("Error generating DSL tests")
        return json.dumps({"error": f"Failed to generate tests: {e}"}, indent=2)


def run_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run DSL-driven tests against a running DNR server."""
    try:
        from dazzle.testing.unified_runner import UnifiedTestRunner

        regenerate = args.get("regenerate", False)
        base_url = args.get("base_url")
        category = args.get("category")
        entity = args.get("entity")
        test_id = args.get("test_id")

        # Create runner and run all tests
        runner = UnifiedTestRunner(project_root, base_url=base_url)
        result = runner.run_all(
            generate=True,
            force_generate=regenerate,
            category=category,
            entity=entity,
            test_id=test_id,
        )

        # Return summary
        summary = result.get_summary()
        return json.dumps(
            {
                "project": result.project_name,
                "summary": summary,
                "dsl_hash": result.dsl_hash[:12],
                "tests_generated": result.tests_generated,
            },
            indent=2,
        )

    except ImportError as e:
        return json.dumps({"error": f"Testing module not available: {e}"}, indent=2)
    except Exception as e:
        logger.exception("Error running DSL tests")
        return json.dumps({"error": f"Failed to run tests: {e}"}, indent=2)


def get_dsl_test_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get test coverage for DSL constructs."""
    try:
        from dazzle.testing.dsl_test_generator import generate_tests_from_dsl

        # Generate tests (function handles loading appspec internally)
        test_suite = generate_tests_from_dsl(project_root)
        coverage = test_suite.coverage

        # Calculate overall coverage
        total_constructs = (
            coverage.entities_total
            + coverage.state_machines_total
            + coverage.personas_total
            + coverage.workspaces_total
            + coverage.events_total
            + coverage.processes_total
        )
        tested_constructs = (
            len(coverage.entities_covered)
            + len(coverage.state_machines_covered)
            + len(coverage.personas_covered)
            + len(coverage.workspaces_covered)
            + len(coverage.events_covered)
            + len(coverage.processes_covered)
        )
        overall_pct = (tested_constructs / total_constructs * 100) if total_constructs > 0 else 0

        result: dict[str, Any] = {
            "project": test_suite.project_name,
            "overall_coverage": f"{overall_pct:.1f}%",
            "total_constructs": total_constructs,
            "tested_constructs": tested_constructs,
            "total_tests": len(test_suite.designs),
            "dsl_hash": test_suite.dsl_hash[:12],
            "categories": {},
        }

        # Add category breakdown
        categories = [
            ("entities", coverage.entities_total, len(coverage.entities_covered)),
            (
                "state_machines",
                coverage.state_machines_total,
                len(coverage.state_machines_covered),
            ),
            ("personas", coverage.personas_total, len(coverage.personas_covered)),
            ("workspaces", coverage.workspaces_total, len(coverage.workspaces_covered)),
            ("events", coverage.events_total, len(coverage.events_covered)),
            ("processes", coverage.processes_total, len(coverage.processes_covered)),
        ]

        for name, total, tested in categories:
            if total > 0:
                pct = tested / total * 100
                result["categories"][name] = {
                    "total": total,
                    "tested": tested,
                    "coverage": f"{pct:.1f}%",
                }

        # Detailed breakdown if requested
        detailed = args.get("detailed", False)
        if detailed:
            # Entity breakdown
            entity_tests: dict[str, int] = {}
            for design in test_suite.designs:
                entities = design.get("entities", [])
                for entity in entities:
                    entity_tests[entity] = entity_tests.get(entity, 0) + 1

            result["entities_detail"] = {
                name: {
                    "test_count": entity_tests.get(name, 0),
                    "covered": name in coverage.entities_covered,
                }
                for name in coverage.entities_covered
            }

            # Persona breakdown
            if coverage.personas_covered:
                persona_tests: dict[str, int] = {}
                for design in test_suite.designs:
                    persona = design.get("persona")
                    if persona:
                        persona_tests[persona] = persona_tests.get(persona, 0) + 1

                result["personas_detail"] = {
                    persona_id: {
                        "test_count": persona_tests.get(persona_id, 0),
                        "covered": persona_id in coverage.personas_covered,
                    }
                    for persona_id in coverage.personas_covered
                }

        return json.dumps(result, indent=2)

    except ImportError as e:
        return json.dumps({"error": f"Testing module not available: {e}"}, indent=2)
    except Exception as e:
        logger.exception("Error getting DSL test coverage")
        return json.dumps({"error": f"Failed to get coverage: {e}"}, indent=2)


def list_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List available DSL-driven tests."""
    try:
        from dazzle.testing.dsl_test_generator import generate_tests_from_dsl

        # Generate tests (function handles loading appspec internally)
        test_suite = generate_tests_from_dsl(project_root)

        # Filter
        category = args.get("category")
        entity = args.get("entity")

        # Helper to extract category from tags
        def get_category(design: dict[str, Any]) -> str:
            tags = design.get("tags", [])
            return next((t for t in tags if t not in ("generated", "dsl-derived")), "other")

        # Helper to get entities from design
        def get_entities(design: dict[str, Any]) -> list[str]:
            entities = design.get("entities", [])
            return entities if isinstance(entities, list) else []

        designs = test_suite.designs
        if category:
            designs = [d for d in designs if get_category(d) == category]
        if entity:
            designs = [d for d in designs if entity in get_entities(d)]

        # Group by category
        by_category: dict[str, list[dict[str, Any]]] = {}
        for design in designs:
            cat = get_category(design)
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(
                {
                    "test_id": design.get("test_id", ""),
                    "title": design.get("title", ""),
                    "description": design.get("description", ""),
                    "entities": get_entities(design),
                }
            )

        # Get all categories and entities for available filters
        all_categories = {get_category(d) for d in test_suite.designs}
        all_entities: set[str] = set()
        for d in test_suite.designs:
            all_entities.update(get_entities(d))

        return json.dumps(
            {
                "project": test_suite.project_name,
                "total_tests": len(designs),
                "filters_applied": {
                    "category": category,
                    "entity": entity,
                },
                "available_categories": sorted(all_categories),
                "available_entities": sorted(all_entities),
                "tests_by_category": by_category,
            },
            indent=2,
        )

    except ImportError as e:
        return json.dumps({"error": f"Testing module not available: {e}"}, indent=2)
    except Exception as e:
        logger.exception("Error listing DSL tests")
        return json.dumps({"error": f"Failed to list tests: {e}"}, indent=2)
