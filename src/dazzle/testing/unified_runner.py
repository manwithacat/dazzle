"""
DAZZLE Unified Test Runner

A comprehensive test harness that:
1. Generates tests directly from DSL/AppSpec
2. Runs CRUD and state machine tests
3. Runs event flow tests
4. Runs temporal workflow tests
5. Tracks coverage across DSL changes
6. Provides stability as new features are added

Usage:
    python -m dazzle.testing.unified_runner <project_path> [--generate] [--run] [--all-examples]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .dsl_test_generator import (
    DSLTestGenerator,
    GeneratedTestSuite,
    TestCoverage,
    save_generated_tests,
)
from .event_test_runner import (
    EventTestRunner,
    EventTestRunResult,
    generate_event_tests_from_appspec,
)
from .test_runner import TestRunner, TestRunResult


@dataclass
class UnifiedTestResult:
    """Combined result from all test types."""

    project_name: str
    started_at: datetime
    completed_at: datetime | None = None

    # Results by type
    crud_result: TestRunResult | None = None
    event_result: EventTestRunResult | None = None

    # Coverage tracking
    dsl_hash: str = ""
    previous_dsl_hash: str = ""
    coverage_stable: bool = True

    # Generation info
    tests_generated: int = 0
    tests_from_cache: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dsl_hash": self.dsl_hash,
            "previous_dsl_hash": self.previous_dsl_hash,
            "coverage_stable": self.coverage_stable,
            "tests_generated": self.tests_generated,
            "tests_from_cache": self.tests_from_cache,
            "summary": self.get_summary(),
        }

    def get_summary(self) -> dict[str, Any]:
        total_tests = 0
        passed = 0
        failed = 0
        skipped = 0

        if self.crud_result:
            total_tests += self.crud_result.total
            passed += self.crud_result.passed
            failed += self.crud_result.failed
            skipped += self.crud_result.skipped

        if self.event_result:
            total_tests += len(self.event_result.tests)
            passed += self.event_result.passed
            failed += self.event_result.failed

        # Calculate success rate based on tests that actually ran (not skipped)
        runnable = passed + failed
        success_rate = (
            (passed / runnable * 100) if runnable > 0 else (100.0 if total_tests == 0 else 0.0)
        )

        return {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "success_rate": success_rate,
        }


class UnifiedTestRunner:
    """
    Unified test runner that orchestrates all test types.

    Key features:
    1. DSL-driven test generation with change detection
    2. Combined CRUD + Event + Process testing
    3. Coverage stability tracking
    4. Automatic test regeneration on DSL changes
    """

    def __init__(
        self,
        project_path: Path,
        server_timeout: int = 30,
        base_url: str | None = None,
    ):
        self.project_path = project_path.resolve()
        self.designs_path = self.project_path / "dsl" / "tests" / "dsl_generated_tests.json"
        self.cache_path = self.project_path / ".dazzle" / "test_cache.json"
        self._server_process: subprocess.Popen[bytes] | None = None
        self.api_port = 8000
        self.ui_port = 3000
        self.server_timeout = server_timeout
        self.base_url = base_url
        self.api_url: str | None = None
        self.ui_url: str | None = None
        if base_url:
            self.api_url, self.ui_url = self._parse_base_url(base_url)

    def _parse_base_url(self, base_url: str) -> tuple[str, str]:
        """Parse base_url into (api_url, ui_url).

        For local dev (explicit port 8000), assumes UI on port 3000.
        For remote/production URLs (no port or non-8000 port), assumes
        API and UI are on the same origin.
        """
        from urllib.parse import urlparse

        url = base_url.rstrip("/")
        parsed = urlparse(url)
        api_url = url

        if parsed.port == 8000:
            # Local dev: API on 8000, UI on 3000
            ui_url = f"{parsed.scheme}://{parsed.hostname}:3000"
        elif parsed.port is not None:
            # Explicit non-8000 port: same origin for both
            ui_url = url
        else:
            # No explicit port (remote deploy): same origin for both
            ui_url = url

        return api_url, ui_url

    def generate_tests(self, force: bool = False) -> GeneratedTestSuite:
        """
        Generate tests from DSL.

        Uses caching to avoid regeneration if DSL hasn't changed.
        """
        from dazzle.core.project import load_project

        print(f"Loading DSL from {self.project_path}...")
        appspec = load_project(self.project_path)

        # Check if regeneration is needed
        from .dsl_test_generator import compute_dsl_hash

        current_hash = compute_dsl_hash(appspec)

        if not force and self._check_cache(current_hash):
            print(f"DSL unchanged (hash: {current_hash[:8]}), using cached tests")
            return self._load_cached_suite()

        print(f"Generating tests for DSL hash: {current_hash[:8]}")
        generator = DSLTestGenerator(appspec)
        suite = generator.generate_all()

        # Save to both locations
        save_generated_tests(self.project_path, suite)
        self._save_cache(suite)

        return suite

    def _check_cache(self, current_hash: str) -> bool:
        """Check if cache is valid for current DSL hash."""
        if not self.cache_path.exists():
            return False

        try:
            with open(self.cache_path) as f:
                cache = json.load(f)
            return bool(cache.get("dsl_hash") == current_hash)
        except Exception:
            return False

    def _load_cached_suite(self) -> GeneratedTestSuite:
        """Load test suite from cache."""
        from .dsl_test_generator import GeneratedTestSuite, TestCoverage

        with open(self.designs_path) as f:
            data = json.load(f)

        coverage = TestCoverage()
        coverage_data = data.get("coverage", {})
        coverage.entities_covered = set(coverage_data.get("entities", []))
        coverage.state_machines_covered = set(coverage_data.get("state_machines", []))
        coverage.personas_covered = set(coverage_data.get("personas", []))
        coverage.workspaces_covered = set(coverage_data.get("workspaces", []))
        coverage.events_covered = set(coverage_data.get("events", []))
        coverage.processes_covered = set(coverage_data.get("processes", []))

        return GeneratedTestSuite(
            version=data.get("version", "2.0"),
            dsl_hash=data.get("dsl_hash", ""),
            generated_at=data.get("generated_at", ""),
            project_name=data.get("project_name", ""),
            designs=data.get("designs", []),
            coverage=coverage,
        )

    def _save_cache(self, suite: GeneratedTestSuite) -> None:
        """Save test suite metadata to cache."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(
                {
                    "dsl_hash": suite.dsl_hash,
                    "generated_at": suite.generated_at,
                    "test_count": len(suite.designs),
                },
                f,
            )

    def start_server(self, timeout: int | None = None) -> bool:
        """Start the DNR server.

        Args:
            timeout: Seconds to wait for server startup. Defaults to self.server_timeout.
        """
        if timeout is None:
            timeout = self.server_timeout

        print(f"Starting server for {self.project_path.name} (timeout: {timeout}s)...")

        # Find available port
        self.api_port = self._find_port(8000)
        self.ui_port = self._find_port(3000)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.project_path.parent.parent / "src")

        self._server_process = subprocess.Popen(
            [sys.executable, "-m", "dazzle", "dazzle", "serve", "--local"],
            cwd=self.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )

        # Wait for server to start and capture ports
        import re

        start_time = time.time()
        backend_ready = False
        frontend_ready = False
        stdout = self._server_process.stdout

        while time.time() - start_time < timeout:
            if self._server_process.poll() is not None:
                return False

            try:
                assert stdout is not None
                line = stdout.readline().decode()
                if "API Port:" in line:
                    self.api_port = int(line.split()[-1])
                elif "Backend:" in line and "http://" in line:
                    # Extract port from URL like [Dazzle] Backend: http://localhost:8000
                    match = re.search(r":(\d+)", line)
                    if match:
                        self.api_port = int(match.group(1))
                    backend_ready = True
                elif "Frontend:" in line and "http://" in line:
                    # Extract port from URL like [Dazzle] Frontend: http://localhost:3000
                    match = re.search(r":(\d+)", line)
                    if match:
                        self.ui_port = int(match.group(1))
                    frontend_ready = True

                # Server is ready when both are up, or when we see Press Ctrl+C
                if "Press Ctrl+C" in line or (backend_ready and frontend_ready):
                    time.sleep(1)  # Give it a moment to fully initialize
                    return True
            except Exception:
                pass

            time.sleep(0.1)

        return True

    def stop_server(self) -> None:
        """Stop the DNR server."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

        # Kill any orphaned processes
        subprocess.run(["pkill", "-f", "dazzle serve"], capture_output=True)

    def _find_port(self, start: int) -> int:
        """Find an available port."""
        import socket

        for port in range(start, start + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", port)) != 0:
                    return port
        return start

    def _authenticate_persona(self, persona: str) -> None:
        """Pre-authenticate as a persona using the session manager."""
        from .session_manager import SessionManager

        base_url = self.base_url or f"http://localhost:{self.api_port}"
        manager = SessionManager(self.project_path, base_url=base_url)
        session = manager.load_session(persona)
        if session:
            print(f"  Using stored session for persona '{persona}'")
        else:
            print(f"  Creating session for persona '{persona}'...")
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None:
                # Already in an async context (e.g. MCP handler) — run in a
                # separate thread with its own event loop to avoid nesting.
                import concurrent.futures

                def _create_in_thread() -> None:
                    asyncio.run(manager.create_session(persona))

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(_create_in_thread).result()
            else:
                asyncio.run(manager.create_session(persona))
            print(f"  Session created for '{persona}'")

    def run_crud_tests(
        self,
        suite: GeneratedTestSuite,
        category: str | None = None,
        entity: str | None = None,
        test_id: str | None = None,
        persona: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> TestRunResult:
        """Run CRUD and state machine tests."""

        runner = TestRunner(
            self.project_path,
            self.api_port,
            self.ui_port,
            api_url=self.api_url,
            ui_url=self.ui_url,
            persona=persona,
        )

        # Merge generated tests with existing tests
        all_designs = suite.designs.copy()

        # Load any hand-written tests
        existing_path = self.project_path / "dsl" / "tests" / "designs.json"
        if existing_path.exists():
            try:
                with open(existing_path) as f:
                    existing = json.load(f)
                    existing_designs = existing.get("designs", [])
                    # Add existing tests that aren't duplicates
                    existing_ids = {d["test_id"] for d in all_designs}
                    for design in existing_designs:
                        if design["test_id"] not in existing_ids:
                            all_designs.append(design)
            except Exception:
                pass

        # Apply filters
        if test_id:
            all_designs = [d for d in all_designs if d.get("test_id") == test_id]
        if category:
            all_designs = [d for d in all_designs if category in d.get("tags", [])]
        if entity:
            all_designs = [d for d in all_designs if entity in d.get("entities", [])]

        # Filter to accepted tests
        accepted = [d for d in all_designs if d.get("status") == "accepted"]

        _log = on_progress or (lambda _msg: None)
        _log(f"Executing {len(accepted)} CRUD/state-machine tests...")

        result = runner.run_tests_from_designs(accepted, on_progress=on_progress)
        return result

    def run_event_tests(self) -> EventTestRunResult | None:
        """Run event flow tests if events are defined."""
        from dazzle.core.project import load_project

        appspec = load_project(self.project_path)

        # Check if there are events to test
        if not appspec.event_model or not appspec.event_model.events:
            print("  No events defined, skipping event tests")
            return None

        test_cases = generate_event_tests_from_appspec(appspec)
        if not test_cases:
            return None

        print(f"  Running {len(test_cases)} event flow tests...")

        api_url = self.api_url or f"http://localhost:{self.api_port}"
        runner = EventTestRunner(api_url)
        try:
            return runner.run_all(test_cases)
        finally:
            runner.close()

    def run_all(
        self,
        generate: bool = True,
        force_generate: bool = False,
        category: str | None = None,
        entity: str | None = None,
        test_id: str | None = None,
        persona: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> UnifiedTestResult:
        """Run all tests."""
        _log = on_progress or (lambda _msg: None)
        result = UnifiedTestResult(
            project_name=self.project_path.name,
            started_at=datetime.now(),
        )

        try:
            # Generate tests if requested
            if generate:
                _log("Generating test designs from DSL...")
                suite = self.generate_tests(force=force_generate)
                result.dsl_hash = suite.dsl_hash
                result.tests_generated = len(suite.designs)
                _log(f"Generated {len(suite.designs)} test designs (hash: {suite.dsl_hash[:8]})")
            else:
                suite = (
                    self._load_cached_suite()
                    if self.designs_path.exists()
                    else GeneratedTestSuite(
                        version="2.0",
                        dsl_hash="",
                        generated_at="",
                        project_name=self.project_path.name,
                        designs=[],
                        coverage=TestCoverage(),
                    )
                )

            # Start server only if no external URL provided
            if not self.base_url:
                _log("Starting local server...")
                if not self.start_server():
                    print("  ERROR: Failed to start server")
                    result.completed_at = datetime.now()
                    return result
            else:
                _log(f"Using external server: {self.base_url}")

            # Authenticate as persona if requested, or auto-authenticate
            # when targeting an external server (remote servers require auth)
            if persona:
                _log(f"Authenticating as persona '{persona}'...")
                self._authenticate_persona(persona)
            elif self.base_url:
                _log("Auto-authenticating for remote server...")
                self._authenticate_persona("admin")

            # Run CRUD tests
            _log("Running CRUD / state-machine tests...")
            result.crud_result = self.run_crud_tests(
                suite,
                category=category,
                entity=entity,
                test_id=test_id,
                persona=persona,
                on_progress=on_progress,
            )
            crud_count = len(result.crud_result.tests) if result.crud_result else 0
            crud_passed = (
                sum(1 for t in result.crud_result.tests if t.result.value == "passed")
                if result.crud_result
                else 0
            )
            _log(f"CRUD tests: {crud_passed}/{crud_count} passed")

            # Run event tests
            _log("Running event flow tests...")
            result.event_result = self.run_event_tests()
            if result.event_result:
                evt_count = len(result.event_result.tests)
                evt_passed = sum(1 for t in result.event_result.tests if t.result.value == "passed")
                _log(f"Event tests: {evt_passed}/{evt_count} passed")
            else:
                _log("No event tests to run")

        finally:
            # Stop server only if we started it
            if not self.base_url:
                self.stop_server()
            result.completed_at = datetime.now()

        return result


def format_unified_report(result: UnifiedTestResult) -> str:
    """Format unified test results."""
    lines = []
    lines.append("=" * 70)
    lines.append("UNIFIED TEST REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Project: {result.project_name}")
    lines.append(f"DSL Hash: {result.dsl_hash[:16] if result.dsl_hash else 'N/A'}")
    lines.append(f"Tests Generated: {result.tests_generated}")
    lines.append("")

    summary = result.get_summary()
    lines.append(f"Total Tests: {summary['total_tests']}")
    lines.append(f"Passed: {summary['passed']}")
    lines.append(f"Failed: {summary['failed']}")
    lines.append(f"Success Rate: {summary['success_rate']:.1f}%")
    lines.append("")

    # CRUD Results
    if result.crud_result:
        lines.append("-" * 40)
        lines.append("CRUD/State Machine Tests:")
        lines.append(f"  Passed: {result.crud_result.passed}")
        lines.append(f"  Failed: {result.crud_result.failed}")

        failed = [t for t in result.crud_result.tests if t.result.value == "failed"]
        if failed:
            lines.append("  Failed Tests:")
            for t in failed:
                lines.append(f"    - {t.test_id}: {t.error_message}")
        lines.append("")

    # Event Results
    if result.event_result:
        lines.append("-" * 40)
        lines.append("Event Flow Tests:")
        lines.append(f"  Passed: {result.event_result.passed}")
        lines.append(f"  Failed: {result.event_result.failed}")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def run_all_examples(base_path: Path, generate: bool = True) -> list[UnifiedTestResult]:
    """Run tests for all example projects."""
    examples_dir = base_path / "examples"
    results: list[UnifiedTestResult] = []

    if not examples_dir.exists():
        print(f"Examples directory not found: {examples_dir}")
        return results

    for project_dir in sorted(examples_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        if not (project_dir / "dazzle.toml").exists():
            continue
        if project_dir.name.startswith("."):
            continue

        print(f"\n{'=' * 60}")
        print(f"Testing: {project_dir.name}")
        print(f"{'=' * 60}")

        runner = UnifiedTestRunner(project_dir)
        try:
            result = runner.run_all(generate=generate)
            results.append(result)

            summary = result.get_summary()
            status = "✓ PASS" if summary["failed"] == 0 else "✗ FAIL"
            print(f"\n{status}: {summary['passed']}/{summary['total_tests']} tests passed")

        except Exception as e:
            print(f"ERROR: {e}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DAZZLE Unified Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and run tests for a project
  python -m dazzle.testing.unified_runner ./my-project

  # Force regenerate tests even if DSL unchanged
  python -m dazzle.testing.unified_runner ./my-project --force-generate

  # Run tests for all example projects
  python -m dazzle.testing.unified_runner --all-examples

  # Generate tests without running them
  python -m dazzle.testing.unified_runner ./my-project --generate-only
        """,
    )
    parser.add_argument("project_path", nargs="?", help="Path to the project to test")
    parser.add_argument(
        "--all-examples", action="store_true", help="Run tests for all example projects"
    )
    parser.add_argument(
        "--generate-only", action="store_true", help="Generate tests without running them"
    )
    parser.add_argument(
        "--force-generate", action="store_true", help="Force regenerate tests even if DSL unchanged"
    )
    parser.add_argument(
        "--no-generate", action="store_true", help="Skip test generation, use existing tests"
    )

    args = parser.parse_args()

    if args.all_examples:
        # Find the base path (parent of src/)
        base_path = Path(__file__).parent.parent.parent.parent
        results = run_all_examples(base_path, generate=not args.no_generate)

        # Print summary
        total = sum(r.get_summary()["total_tests"] for r in results)
        passed = sum(r.get_summary()["passed"] for r in results)
        failed = sum(r.get_summary()["failed"] for r in results)

        print(f"\n{'=' * 60}")
        print("OVERALL SUMMARY")
        print(f"{'=' * 60}")
        print(f"Projects: {len(results)}")
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed / total * 100):.1f}%" if total > 0 else "N/A")

        sys.exit(0 if failed == 0 else 1)

    if not args.project_path:
        parser.error("project_path is required unless --all-examples is specified")

    project_path = Path(args.project_path).resolve()
    if not project_path.exists():
        print(f"Project not found: {project_path}")
        sys.exit(1)

    runner = UnifiedTestRunner(project_path)

    if args.generate_only:
        suite = runner.generate_tests(force=args.force_generate)
        print(f"\nGenerated {len(suite.designs)} tests")
        print(f"DSL Hash: {suite.dsl_hash}")
        sys.exit(0)

    result = runner.run_all(generate=not args.no_generate, force_generate=args.force_generate)

    print(format_unified_report(result))

    summary = result.get_summary()
    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
