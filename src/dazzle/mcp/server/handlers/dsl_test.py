"""DSL test tool handlers.

Handles DSL test generation, execution, coverage analysis, and listing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .common import error_response, extract_progress, wrap_async_handler_errors, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


@wrap_handler_errors
def verify_story_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Verify a story by mapping it to entity tests, running them, and returning a verdict.

    Maps story → scope entities → test IDs, runs only those tests, and returns
    a per-story pass/fail verdict with test details.
    """
    try:
        from dazzle.core.stories_persistence import load_stories
        from dazzle.testing.dsl_test_generator import generate_tests_from_dsl
        from dazzle.testing.unified_runner import UnifiedTestRunner

        story_id = args.get("story_id")
        story_ids_list: list[str] = args.get("story_ids") or []
        if story_id:
            story_ids_list = [story_id]
        if not story_ids_list:
            return error_response("story_id or story_ids is required")

        base_url = args.get("base_url")

        if base_url:
            from .preflight import check_server_reachable

            preflight_err = check_server_reachable(base_url)
            if preflight_err:
                return preflight_err

        # Load all stories
        all_stories = load_stories(project_root)
        story_map = {s.story_id: s for s in all_stories}

        # Resolve requested stories
        requested = [story_map[sid] for sid in story_ids_list if sid in story_map]
        missing = [sid for sid in story_ids_list if sid not in story_map]

        if not requested:
            return json.dumps(
                {
                    "error": f"No stories found for IDs: {story_ids_list}",
                    "available": [s.story_id for s in all_stories[:20]],
                },
                indent=2,
            )

        # Generate test suite to find tests related to story entities
        test_suite = generate_tests_from_dsl(project_root)

        # Build entity→test mapping
        entity_to_tests: dict[str, list[dict[str, Any]]] = {}
        for design in test_suite.designs:
            for entity in design.get("entities", []):
                entity_to_tests.setdefault(entity, []).append(design)

        # For each story, find related tests via scope entities
        story_results: list[dict[str, Any]] = []

        # Create runner once (reuse for all stories)
        runner = UnifiedTestRunner(project_root, base_url=base_url)

        for story in requested:
            scope_entities = story.scope or []
            related_tests: list[dict[str, Any]] = []
            for entity in scope_entities:
                related_tests.extend(entity_to_tests.get(entity, []))
            # Deduplicate by test_id
            seen_ids: set[str] = set()
            unique_tests: list[dict[str, Any]] = []
            for t in related_tests:
                tid = t.get("test_id", "")
                if tid not in seen_ids:
                    seen_ids.add(tid)
                    unique_tests.append(t)

            if not unique_tests:
                story_results.append(
                    {
                        "story_id": story.story_id,
                        "title": story.title,
                        "entities": scope_entities,
                        "verdict": "NO_TESTS",
                        "message": f"No tests map to entities {scope_entities}",
                    }
                )
                continue

            # Run only the related tests by filtering entity
            # Use per-entity runs and aggregate
            passed: list[str] = []
            failed: list[dict[str, Any]] = []

            for entity in scope_entities:
                entity_result = runner.run_all(
                    generate=True,
                    entity=entity,
                )
                if entity_result.crud_result:
                    for tc in entity_result.crud_result.tests:
                        if tc.result.value == "passed":
                            passed.append(tc.test_id)
                        elif tc.result.value in ("failed", "error"):
                            fail_entry: dict[str, Any] = {
                                "test_id": tc.test_id,
                                "result": tc.result.value,
                                "error": tc.error_message,
                            }
                            failed.append(fail_entry)

            verdict = "PASS" if not failed else "FAIL"

            story_results.append(
                {
                    "story_id": story.story_id,
                    "title": story.title,
                    "status": story.status.value,
                    "entities": scope_entities,
                    "verdict": verdict,
                    "tests_passed": len(passed),
                    "tests_failed": len(failed),
                    "passed_ids": passed,
                    "failed_tests": failed if failed else None,
                }
            )

        response: dict[str, Any] = {
            "stories_verified": len(story_results),
            "stories_passed": sum(1 for r in story_results if r["verdict"] == "PASS"),
            "stories_failed": sum(1 for r in story_results if r["verdict"] == "FAIL"),
            "stories_no_tests": sum(1 for r in story_results if r["verdict"] == "NO_TESTS"),
            "results": story_results,
        }
        if missing:
            response["missing_story_ids"] = missing

        return json.dumps(response, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


@wrap_handler_errors
def generate_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate tests from DSL/AppSpec definitions."""
    try:
        fmt = args.get("format", "json")

        # Bash/curl smoke test generation
        if fmt == "bash":
            return _generate_bash_tests(project_root, args)

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
        if coverage.auth_personas_total > 0:
            result["coverage"]["auth"] = (
                f"{len(coverage.auth_personas_covered)}/{coverage.auth_personas_total}"
            )

        if save:
            result["saved_to"] = str(project_root / "dsl" / "tests")

        return json.dumps(result, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


def _generate_bash_tests(project_root: Path, args: dict[str, Any]) -> str:
    """Generate bash/curl smoke test script."""
    from dazzle.core.project import load_project
    from dazzle.testing.curl_test_generator import CurlTestGenerator

    appspec = load_project(project_root)
    base_url = args.get("base_url", "http://localhost:8000")
    generator = CurlTestGenerator(appspec, base_url=base_url, project_root=project_root)
    script = generator.generate()

    save = args.get("save", False)
    if save:
        output_dir = project_root / "dsl" / "tests"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "smoke_test.sh"
        output_file.write_text(script)
        output_file.chmod(0o755)
        return json.dumps(
            {
                "format": "bash",
                "saved_to": str(output_file),
                "script_lines": len(script.splitlines()),
            },
            indent=2,
        )

    return script


def _persist_test_results(
    result: Any,
    by_category: dict[str, dict[str, int]],
    failed_tests: list[dict[str, Any]],
    passed_tests: list[str],
    trigger: str = "manual",
) -> str | None:
    """Persist test run results to the knowledge graph. Returns run_id or None."""
    import time
    import uuid

    from ..state import get_knowledge_graph

    graph = get_knowledge_graph()
    if graph is None:
        return None

    from dazzle.mcp.knowledge_graph.failure_classifier import classify_failure

    run_id = str(uuid.uuid4())
    total = len(passed_tests) + len(failed_tests)
    passed_count = len(passed_tests)
    failed_count = len(failed_tests)
    success_rate = (passed_count / total * 100) if total > 0 else 0.0

    # Check previous run's dsl_hash
    previous_runs = graph.get_test_runs(project_name=result.project_name, limit=1)
    previous_dsl_hash = previous_runs[0]["dsl_hash"] if previous_runs else None

    now = time.time()
    graph.save_test_run(
        run_id=run_id,
        project_name=result.project_name,
        dsl_hash=result.dsl_hash,
        previous_dsl_hash=previous_dsl_hash,
        started_at=now,
        completed_at=now,
        total_tests=total,
        passed=passed_count,
        failed=failed_count,
        success_rate=success_rate,
        tests_generated=result.tests_generated,
        trigger=trigger,
    )

    # Build test case rows
    cases: list[dict[str, Any]] = []

    for test_id in passed_tests:
        cases.append(
            {
                "test_id": test_id,
                "title": test_id,
                "category": _infer_category(test_id),
                "result": "passed",
            }
        )

    for ft in failed_tests:
        failed_step = ft.get("failed_step")
        failure_type = classify_failure(
            test_id=ft.get("test_id", ""),
            category=ft.get("category", "other"),
            error_message=ft.get("error", ""),
            failed_step=failed_step,
        )
        cases.append(
            {
                "test_id": ft.get("test_id", ""),
                "title": ft.get("title", ft.get("test_id", "")),
                "category": ft.get("category", "other"),
                "result": ft.get("result", "failed"),
                "error_message": ft.get("error"),
                "failure_type": failure_type,
                "entities": ft.get("entities"),
                "failed_step_json": json.dumps(failed_step) if failed_step else None,
            }
        )

    if cases:
        graph.save_test_cases_batch(run_id, cases)

    return run_id


def _infer_category(test_id: str) -> str:
    """Infer test category from test_id prefix."""
    if test_id.startswith("CRUD_"):
        return "crud"
    if test_id.startswith("SM_"):
        return "state_machine"
    if test_id.startswith("VAL_"):
        return "validation"
    if test_id.startswith("ACL_"):
        return "persona"
    if test_id.startswith("WS_"):
        return "workspace"
    return "other"


@wrap_handler_errors
def run_all_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run ALL DSL-driven tests without filtering, returning a structured batch report.

    Designed for autonomous agent loops: single call, structured JSON output with
    by_category breakdown, failed test details, and overall summary.
    """
    try:
        from dazzle.testing.unified_runner import UnifiedTestRunner

        progress = extract_progress(args)
        base_url = args.get("base_url")

        if base_url:
            from .preflight import check_server_reachable

            progress.log_sync("Checking server reachability...")
            preflight_err = check_server_reachable(base_url)
            if preflight_err:
                return preflight_err

        regenerate = args.get("regenerate", False)

        progress.log_sync("Generating tests from DSL...")
        runner = UnifiedTestRunner(project_root, base_url=base_url)

        progress.log_sync("Running all tests...")
        result = runner.run_all(
            generate=True,
            force_generate=regenerate,
            on_progress=lambda msg: progress.log_sync(msg),
        )

        # Build structured response optimized for LLM consumption
        summary = result.get_summary()
        response: dict[str, Any] = {
            "project": result.project_name,
            "summary": summary,
            "dsl_hash": result.dsl_hash[:12],
            "tests_generated": result.tests_generated,
        }

        # Categorize results
        by_category: dict[str, dict[str, int]] = {}
        failed_tests: list[dict[str, Any]] = []
        passed_tests: list[str] = []

        if result.crud_result:
            for tc in result.crud_result.tests:
                # Determine category from tags
                cat = "other"
                if hasattr(tc, "tags"):
                    tags = tc.tags if isinstance(tc.tags, list) else []
                    cat = next(
                        (t for t in tags if t not in ("generated", "dsl-derived")),
                        "crud",
                    )
                else:
                    # Infer from test_id prefix
                    tid = tc.test_id or ""
                    if tid.startswith("CRUD_"):
                        cat = "crud"
                    elif tid.startswith("SM_"):
                        cat = "state_machine"
                    elif tid.startswith("VAL_"):
                        cat = "validation"
                    elif tid.startswith("ACL_"):
                        cat = "persona"
                    elif tid.startswith("WS_"):
                        cat = "workspace"

                if cat not in by_category:
                    by_category[cat] = {"passed": 0, "failed": 0, "total": 0}
                by_category[cat]["total"] += 1

                if tc.result.value in ("failed", "error"):
                    by_category[cat]["failed"] += 1
                    entry: dict[str, Any] = {
                        "test_id": tc.test_id,
                        "title": tc.title,
                        "category": cat,
                        "result": tc.result.value,
                        "error": tc.error_message,
                    }
                    for step in tc.steps:
                        if step.result.value in ("failed", "error"):
                            entry["failed_step"] = {
                                "action": step.action,
                                "target": step.target,
                                "message": step.message,
                            }
                            break
                    failed_tests.append(entry)
                elif tc.result.value == "passed":
                    by_category[cat]["passed"] += 1
                    passed_tests.append(tc.test_id)

        if result.event_result:
            cat = "event"
            if cat not in by_category:
                by_category[cat] = {"passed": 0, "failed": 0, "total": 0}
            for etc in result.event_result.tests:
                by_category[cat]["total"] += 1
                if etc.result.value in ("failed", "error"):
                    by_category[cat]["failed"] += 1
                    evt_entry: dict[str, Any] = {
                        "test_id": etc.test_id,
                        "title": etc.title,
                        "category": cat,
                        "result": etc.result.value,
                        "error": etc.error_message,
                    }
                    if etc.details:
                        evt_entry["details"] = etc.details[:3]
                    failed_tests.append(evt_entry)
                elif etc.result.value == "passed":
                    by_category[cat]["passed"] += 1
                    passed_tests.append(etc.test_id)

        response["by_category"] = by_category
        if failed_tests:
            response["failed_tests"] = failed_tests
        response["passed_count"] = len(passed_tests)

        # Persist test results to knowledge graph
        try:
            run_id = _persist_test_results(
                result, by_category, failed_tests, passed_tests, trigger="run_all"
            )
            if run_id:
                response["run_id"] = run_id
        except Exception:
            logger.warning("Failed to persist test results", exc_info=True)
            response["persistence_error"] = "Test results could not be saved to knowledge graph"

        return json.dumps(response, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


@wrap_handler_errors
def run_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run DSL-driven tests against a running DNR server."""
    try:
        from dazzle.testing.unified_runner import UnifiedTestRunner

        progress = extract_progress(args)
        regenerate = args.get("regenerate", False)
        base_url = args.get("base_url")

        if base_url:
            from .preflight import check_server_reachable

            progress.log_sync("Checking server reachability...")
            preflight_err = check_server_reachable(base_url)
            if preflight_err:
                return preflight_err

        category = args.get("category")
        entity = args.get("entity")
        test_id = args.get("test_id")
        persona = args.get("persona")

        filters = [f for f in [category, entity, test_id, persona] if f]
        progress.log_sync(
            f"Running tests{' (filtered: ' + ', '.join(filters) + ')' if filters else ''}..."
        )

        # Create runner and run all tests
        runner = UnifiedTestRunner(project_root, base_url=base_url)
        result = runner.run_all(
            generate=True,
            force_generate=regenerate,
            category=category,
            entity=entity,
            test_id=test_id,
            persona=persona,
            on_progress=lambda msg: progress.log_sync(msg),
        )

        # Return summary + individual test results for LLM agents
        response: dict[str, Any] = {
            "project": result.project_name,
            "summary": result.get_summary(),
            "dsl_hash": result.dsl_hash[:12],
            "tests_generated": result.tests_generated,
        }
        if persona:
            response["persona"] = persona

        # Include individual test results so agents can diagnose failures
        failed_tests: list[dict[str, Any]] = []
        passed_tests: list[str] = []

        if result.crud_result:
            for tc in result.crud_result.tests:
                if tc.result.value in ("failed", "error"):
                    entry: dict[str, Any] = {
                        "test_id": tc.test_id,
                        "title": tc.title,
                        "result": tc.result.value,
                        "error": tc.error_message,
                    }
                    # Include first failed step for context
                    for step in tc.steps:
                        if step.result.value in ("failed", "error"):
                            entry["failed_step"] = {
                                "action": step.action,
                                "target": step.target,
                                "message": step.message,
                            }
                            break
                    failed_tests.append(entry)
                elif tc.result.value == "passed":
                    passed_tests.append(tc.test_id)

        if result.event_result:
            for etc in result.event_result.tests:
                if etc.result.value in ("failed", "error"):
                    evt_entry: dict[str, Any] = {
                        "test_id": etc.test_id,
                        "title": etc.title,
                        "result": etc.result.value,
                        "error": etc.error_message,
                    }
                    if etc.details:
                        evt_entry["details"] = etc.details[:3]  # First 3 detail lines
                    failed_tests.append(evt_entry)
                elif etc.result.value == "passed":
                    passed_tests.append(etc.test_id)

        if failed_tests:
            response["failed_tests"] = failed_tests
        if passed_tests:
            response["passed_tests"] = passed_tests

        return json.dumps(response, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


@wrap_async_handler_errors
async def create_sessions_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Create authenticated sessions for all DSL-defined personas."""
    try:
        from dazzle.core.project import load_project
        from dazzle.testing.session_manager import SessionManager

        base_url = args.get("base_url", "http://localhost:8000")
        force = args.get("force", False)

        appspec = load_project(project_root)
        manager = SessionManager(project_root, base_url=base_url)
        manifest = await manager.create_all_sessions(appspec, force=force)

        return json.dumps(
            {
                "project": manifest.project_name,
                "base_url": manifest.base_url,
                "created_at": manifest.created_at,
                "personas": {
                    pid: {
                        "user_id": s.user_id,
                        "email": s.email,
                        "role": s.role,
                        "has_token": bool(s.session_token),
                    }
                    for pid, s in manifest.sessions.items()
                },
                "total_sessions": len(manifest.sessions),
            },
            indent=2,
        )

    except ImportError as e:
        return error_response(f"Session manager not available: {e}")


@wrap_async_handler_errors
async def diff_personas_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Compare route responses across personas."""
    try:
        from dazzle.testing.session_manager import SessionManager

        base_url: str = args.get("base_url", "http://localhost:8000")
        route: str | None = args.get("route")
        routes: list[str] | None = args.get("routes")
        persona_ids: list[str] | None = args.get("persona_ids")

        if not route and not routes:
            return json.dumps(
                {"error": "Either 'route' or 'routes' parameter is required"},
                indent=2,
            )

        manager = SessionManager(project_root, base_url=base_url)

        if route:
            result = await manager.diff_route(route, persona_ids)
            return json.dumps(result, indent=2)
        else:
            results = await manager.diff_routes(routes or [], persona_ids)
            return json.dumps({"diffs": results}, indent=2)

    except ImportError as e:
        return error_response(f"Session manager not available: {e}")


@wrap_handler_errors
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
            ("auth", coverage.auth_personas_total, len(coverage.auth_personas_covered)),
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
        return error_response(f"Testing module not available: {e}")


@wrap_handler_errors
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
        return error_response(f"Testing module not available: {e}")
