"""DSL test tool handlers.

Handles DSL test generation, execution, coverage analysis, and listing.
"""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.manifest import resolve_api_url
from dazzle.core.project import load_project

from .common import error_response, extract_progress, wrap_handler_errors

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Impl functions — no MCP types, explicit params, return dicts
# ---------------------------------------------------------------------------


def dsl_test_generate_impl(
    project_root: Path,
    *,
    fmt: str = "json",
    save: bool = False,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Generate tests from DSL/AppSpec definitions.

    Returns a dict with generation summary (or raises on error).
    For ``fmt="bash"`` the dict contains ``{"script": <str>, ...}``.
    """
    if base_url is None:
        base_url = resolve_api_url()
    if fmt == "bash":
        from dazzle.testing.curl_test_generator import CurlTestGenerator

        appspec = load_project(project_root)
        generator = CurlTestGenerator(appspec, base_url=base_url, project_root=project_root)
        script = generator.generate()

        if save:
            output_dir = project_root / "dsl" / "tests"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "smoke_test.sh"
            output_file.write_text(script, encoding="utf-8")
            output_file.chmod(0o755)
            return {
                "format": "bash",
                "saved_to": str(output_file),
                "script_lines": len(script.splitlines()),
            }

        return {"format": "bash", "script": script}

    from dazzle.testing.dsl_test_generator import (
        generate_tests_from_dsl,
        save_generated_tests,
    )

    test_suite = generate_tests_from_dsl(project_root)

    if save:
        save_generated_tests(project_root, test_suite)

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

    return result


def dsl_test_run_all_impl(
    project_root: Path,
    *,
    base_url: str | None = None,
    regenerate: bool = False,
    on_progress: Any = None,
) -> dict[str, Any]:
    """Run ALL DSL-driven tests without filtering.

    Returns a structured batch report dict.
    """
    from dazzle.testing.unified_runner import UnifiedTestRunner

    runner = UnifiedTestRunner(project_root, base_url=base_url)
    result = runner.run_all(
        generate=True,
        force_generate=regenerate,
        on_progress=on_progress,
    )

    summary = result.get_summary()
    response: dict[str, Any] = {
        "project": result.project_name,
        "summary": summary,
        "dsl_hash": result.dsl_hash[:12],
        "tests_generated": result.tests_generated,
    }

    by_category: dict[str, dict[str, int]] = {}
    failed_tests: list[dict[str, Any]] = []
    passed_tests: list[str] = []

    if result.crud_result:
        for tc in result.crud_result.tests:
            cat = "other"
            if hasattr(tc, "tags"):
                tags = tc.tags if isinstance(tc.tags, list) else []
                cat = next(
                    (t for t in tags if t not in ("generated", "dsl-derived")),
                    "crud",
                )
            else:
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

    response["by_category"] = by_category
    if failed_tests:
        response["failed_tests"] = failed_tests
    response["passed_count"] = len(passed_tests)

    return response


def dsl_test_coverage_impl(
    project_root: Path,
    *,
    detailed: bool = False,
) -> dict[str, Any]:
    """Return test coverage for DSL constructs."""
    from dazzle.testing.dsl_test_generator import generate_tests_from_dsl

    test_suite = generate_tests_from_dsl(project_root)
    coverage = test_suite.coverage

    total_constructs = (
        coverage.entities_total
        + coverage.state_machines_total
        + coverage.personas_total
        + coverage.workspaces_total
        + coverage.processes_total
    )
    tested_constructs = (
        len(coverage.entities_covered)
        + len(coverage.state_machines_covered)
        + len(coverage.personas_covered)
        + len(coverage.workspaces_covered)
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

    categories = [
        ("entities", coverage.entities_total, len(coverage.entities_covered)),
        (
            "state_machines",
            coverage.state_machines_total,
            len(coverage.state_machines_covered),
        ),
        ("personas", coverage.personas_total, len(coverage.personas_covered)),
        ("workspaces", coverage.workspaces_total, len(coverage.workspaces_covered)),
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

    if detailed:
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

    return result


def dsl_test_verify_story_impl(
    project_root: Path,
    *,
    story_ids: list[str],
    base_url: str | None = None,
) -> dict[str, Any]:
    """Verify stories by mapping them to entity tests, running them, and returning verdicts."""
    from dazzle.testing.dsl_test_generator import generate_tests_from_dsl
    from dazzle.testing.unified_runner import UnifiedTestRunner

    from .common import load_project_appspec

    app_spec = load_project_appspec(project_root)
    all_stories = list(app_spec.stories) if app_spec.stories else []
    story_map = {s.story_id: s for s in all_stories}

    requested = [story_map[sid] for sid in story_ids if sid in story_map]
    missing = [sid for sid in story_ids if sid not in story_map]

    if not requested:
        return {
            "error": f"No stories found for IDs: {story_ids}",
            "available": [s.story_id for s in all_stories[:20]],
        }

    test_suite = generate_tests_from_dsl(project_root)

    entity_to_tests: dict[str, list[dict[str, Any]]] = {}
    for design in test_suite.designs:
        for entity in design.get("entities", []):
            entity_to_tests.setdefault(entity, []).append(design)

    story_results: list[dict[str, Any]] = []
    runner = UnifiedTestRunner(project_root, base_url=base_url)

    for story in requested:
        scope_entities = story.entities or []
        related_tests: list[dict[str, Any]] = []
        for entity in scope_entities:
            related_tests.extend(entity_to_tests.get(entity, []))

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

    return response


# ---------------------------------------------------------------------------
# Private helpers (unchanged)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MCP handler wrappers — delegate to impl functions
# ---------------------------------------------------------------------------


@wrap_handler_errors
def generate_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate tests from DSL/AppSpec definitions."""
    try:
        fmt = args.get("format", "json")
        save = args.get("save", False)
        base_url = args.get("base_url") or resolve_api_url()

        result = dsl_test_generate_impl(
            project_root,
            fmt=fmt,
            save=save,
            base_url=base_url,
        )

        # For bash format without save, the impl returns {"format": "bash", "script": <str>}
        # The original handler returned the raw script string — preserve that behaviour.
        if fmt == "bash" and not save and "script" in result:
            return str(result["script"])

        return json.dumps(result, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


@wrap_handler_errors
def run_all_dsl_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Run ALL DSL-driven tests without filtering, returning a structured batch report."""
    try:
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
        progress.log_sync("Running all tests...")

        result = dsl_test_run_all_impl(
            project_root,
            base_url=base_url,
            regenerate=regenerate,
            on_progress=lambda msg: progress.log_sync(msg),
        )

        passed_count = result.get("passed_count", 0)
        failed_count = len(result.get("failed_tests", []))
        progress.log_sync(f"Tests complete: {passed_count} passed, {failed_count} failed")

        return json.dumps(result, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")


@wrap_handler_errors
def get_dsl_test_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get test coverage for DSL constructs."""
    try:
        detailed = args.get("detailed", False)
        result = dsl_test_coverage_impl(project_root, detailed=detailed)
        return json.dumps(result, indent=2)

    except ImportError as e:
        return error_response(f"Testing module not available: {e}")
