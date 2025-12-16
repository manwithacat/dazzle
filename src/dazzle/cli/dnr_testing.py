"""
DNR Testing utilities.

This module contains test helper functions used by the `dazzle dnr test` command.
It includes API contract testing, E2E tests, benchmarks, and accessibility checks.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.core.strings import to_api_plural

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle_dnr_back.specs.backend import BackendSpec


def run_api_contract_tests(
    backend_spec: "BackendSpec",
    api_url: str,
    verbose: bool,
) -> dict[str, Any]:
    """Run API contract tests against the running server."""
    import json as json_module
    import urllib.error
    import urllib.request

    tests: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    def make_request(
        method: str, path: str, data: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any] | None]:
        """Make HTTP request and return status code and response."""
        url = f"{api_url}{path}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")

        body = None
        if data:
            body = json_module.dumps(data).encode("utf-8")

        try:
            with urllib.request.urlopen(req, body, timeout=10) as resp:
                response_data = json_module.loads(resp.read().decode())
                return resp.status, response_data
        except urllib.error.HTTPError as e:
            try:
                error_body = json_module.loads(e.read().decode())
            except Exception:
                error_body = None
            return e.code, error_body
        except Exception:
            return 0, None

    # Track created entities for ref field handling
    created_entities: dict[str, str] = {}

    # Test each entity's CRUD endpoints
    for entity in backend_spec.entities:
        plural_name = to_api_plural(entity.name)
        base_path = f"/{plural_name}"

        # Test LIST
        status, data = make_request("GET", base_path)
        test_result = {
            "entity": entity.name,
            "operation": "LIST",
            "path": base_path,
            "status": status,
            "passed": status == 200,
        }
        tests.append(test_result)
        if status == 200:
            passed += 1
            if verbose:
                typer.secho(f"  ✓ GET {base_path}", fg=typer.colors.GREEN)
        else:
            failed += 1
            if verbose:
                typer.secho(f"  ✗ GET {base_path} (status: {status})", fg=typer.colors.RED)

        # Test CREATE
        create_data = generate_test_data(entity, created_entities=created_entities)
        status, response = make_request("POST", base_path, create_data)
        test_result = {
            "entity": entity.name,
            "operation": "CREATE",
            "path": base_path,
            "status": status,
            "passed": status in (200, 201),
        }
        tests.append(test_result)

        created_id = None
        if status in (200, 201):
            passed += 1
            if response and "id" in response:
                created_id = response["id"]
                # Store for ref field handling
                created_entities[entity.name] = created_id
            if verbose:
                typer.secho(f"  ✓ POST {base_path}", fg=typer.colors.GREEN)
        else:
            failed += 1
            if verbose:
                error_msg = ""
                if response and "detail" in response:
                    error_msg = f" - {response['detail']}"
                typer.secho(
                    f"  ✗ POST {base_path} (status: {status}){error_msg}",
                    fg=typer.colors.RED,
                )

        # Test GET single (if we created one)
        if created_id:
            status, data = make_request("GET", f"{base_path}/{created_id}")
            test_result = {
                "entity": entity.name,
                "operation": "GET",
                "path": f"{base_path}/{{id}}",
                "status": status,
                "passed": status == 200,
            }
            tests.append(test_result)
            if status == 200:
                passed += 1
                if verbose:
                    typer.secho(f"  ✓ GET {base_path}/{{id}}", fg=typer.colors.GREEN)
            else:
                failed += 1
                if verbose:
                    typer.secho(
                        f"  ✗ GET {base_path}/{{id}} (status: {status})",
                        fg=typer.colors.RED,
                    )

            # Test UPDATE
            update_data = generate_test_data(entity, update=True, created_entities=created_entities)
            status, response = make_request("PATCH", f"{base_path}/{created_id}", update_data)
            test_result = {
                "entity": entity.name,
                "operation": "UPDATE",
                "path": f"{base_path}/{{id}}",
                "status": status,
                "passed": status == 200,
            }
            tests.append(test_result)
            if status == 200:
                passed += 1
                if verbose:
                    typer.secho(f"  ✓ PATCH {base_path}/{{id}}", fg=typer.colors.GREEN)
            else:
                failed += 1
                if verbose:
                    typer.secho(
                        f"  ✗ PATCH {base_path}/{{id}} (status: {status})",
                        fg=typer.colors.RED,
                    )

            # Test DELETE
            status, _ = make_request("DELETE", f"{base_path}/{created_id}")
            test_result = {
                "entity": entity.name,
                "operation": "DELETE",
                "path": f"{base_path}/{{id}}",
                "status": status,
                "passed": status in (200, 204),
            }
            tests.append(test_result)
            if status in (200, 204):
                passed += 1
                if verbose:
                    typer.secho(f"  ✓ DELETE {base_path}/{{id}}", fg=typer.colors.GREEN)
            else:
                failed += 1
                if verbose:
                    typer.secho(
                        f"  ✗ DELETE {base_path}/{{id}} (status: {status})",
                        fg=typer.colors.RED,
                    )

    return {"tests": tests, "passed": passed, "failed": failed}


def generate_test_data(
    entity: Any,
    update: bool = False,
    created_entities: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate minimal test data for an entity.

    Args:
        entity: The entity spec to generate data for
        update: If True, generate update data (different values)
        created_entities: Dict mapping entity names to created IDs for ref fields

    Returns:
        Dict with test data for the entity
    """
    import uuid as uuid_module

    from dazzle_dnr_back.specs.entity import ScalarType

    data: dict[str, Any] = {}
    created_entities = created_entities or {}

    # Generate a unique suffix for this test run to avoid UNIQUE constraint violations
    unique_suffix = uuid_module.uuid4().hex[:8]

    for field in entity.fields:
        # Skip auto-generated fields
        if field.name == "id" or field.name.endswith("_at"):
            continue

        # Skip non-required fields for create, include for update
        if not field.required and not update:
            continue

        # Handle ref fields (foreign keys)
        if field.type.kind == "ref":
            ref_entity_name = field.type.ref_entity
            if ref_entity_name and ref_entity_name in created_entities:
                data[field.name] = created_entities[ref_entity_name]
            else:
                # Skip ref fields if we don't have a referenced entity
                # This will cause validation errors but is better than crashing
                continue

        # Generate appropriate test value based on type
        scalar = field.type.scalar_type
        max_length = getattr(field.type, "max_length", None)

        if scalar in (ScalarType.STR, ScalarType.TEXT):
            # Use unique suffix for unique fields to avoid constraint violations
            if field.unique:
                value = f"t_{unique_suffix}" if not update else f"u_{unique_suffix}"
            else:
                value = f"test_{field.name}" if not update else f"upd_{field.name}"
            # Truncate to max_length if specified
            if max_length and len(value) > max_length:
                value = value[:max_length]
            data[field.name] = value
        elif scalar == ScalarType.EMAIL:
            # Email fields are often unique
            data[field.name] = (
                f"test_{unique_suffix}@example.com"
                if not update
                else f"upd_{unique_suffix}@example.com"
            )
        elif scalar == ScalarType.URL:
            data[field.name] = (
                f"https://example.com/{unique_suffix}"
                if not update
                else f"https://example.com/upd_{unique_suffix}"
            )
        elif scalar == ScalarType.INT:
            data[field.name] = 42 if not update else 43
        elif scalar == ScalarType.DECIMAL:
            data[field.name] = 3.14 if not update else 3.15
        elif scalar == ScalarType.BOOL:
            data[field.name] = True if not update else False
        elif scalar == ScalarType.UUID:
            data[field.name] = str(uuid_module.uuid4())
        elif scalar == ScalarType.DATETIME:
            data[field.name] = "2024-01-01T00:00:00Z"
        elif scalar == ScalarType.DATE:
            data[field.name] = "2024-01-01"
        elif field.type.kind == "enum" and field.type.enum_values:
            data[field.name] = field.type.enum_values[0]

    return data


def run_e2e_tests(
    manifest_path: Path,
    api_url: str,
    base_url: str,
    verbose: bool,
) -> dict[str, Any]:
    """Run E2E tests using existing test infrastructure."""
    import subprocess
    import sys

    tests: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    # Run dazzle test run command
    cmd = [
        sys.executable,
        "-m",
        "dazzle.cli",
        "test",
        "run",
        "-m",
        str(manifest_path),
        "--api-url",
        api_url,
        "--base-url",
        base_url,
        "--headless",
    ]

    if verbose:
        cmd.append("--verbose")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Parse output to count results
        for line in result.stdout.split("\n"):
            if "✓" in line:
                passed += 1
                flow_id = line.strip().replace("✓", "").strip()
                tests.append({"flow_id": flow_id, "passed": True})
            elif "✗" in line:
                failed += 1
                flow_id = line.strip().replace("✗", "").strip()
                tests.append({"flow_id": flow_id, "passed": False})

        if verbose and result.stdout:
            typer.echo(result.stdout)
        if verbose and result.stderr:
            typer.echo(result.stderr, err=True)

    except subprocess.TimeoutExpired:
        typer.echo("E2E tests timed out", err=True)
        failed += 1
        tests.append({"flow_id": "timeout", "passed": False, "error": "Timeout"})
    except FileNotFoundError:
        typer.echo("Could not run E2E tests - dazzle CLI not found", err=True)
        failed += 1
        tests.append({"flow_id": "error", "passed": False, "error": "CLI not found"})

    return {"tests": tests, "passed": passed, "failed": failed}


def run_benchmarks(
    backend_spec: "BackendSpec",
    api_url: str,
    verbose: bool,
) -> dict[str, Any]:
    """Run performance benchmarks against the running server."""
    import statistics
    import time
    import urllib.request

    results: dict[str, Any] = {
        "cold_start_ms": 0.0,
        "latency_p50_ms": 0.0,
        "latency_p95_ms": 0.0,
        "latency_p99_ms": 0.0,
        "throughput_rps": 0.0,
        "sample_count": 0,
        "latencies_ms": [],
    }

    # Find a list endpoint to benchmark
    list_endpoint = None
    for entity in backend_spec.entities:
        plural_name = to_api_plural(entity.name)
        list_endpoint = f"/{plural_name}"
        break

    if not list_endpoint:
        list_endpoint = "/health"

    # Measure cold start (time to first response after server start)
    # This is approximate since server is already running
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{api_url}{list_endpoint}", timeout=10):
            pass
    except Exception:
        pass
    cold_start = (time.perf_counter() - start) * 1000
    results["cold_start_ms"] = cold_start

    # Run latency benchmark (100 sequential requests)
    latencies: list[float] = []
    num_requests = 100

    if verbose:
        typer.echo(f"  Running {num_requests} sequential requests to {list_endpoint}...")

    for _ in range(num_requests):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(f"{api_url}{list_endpoint}", timeout=10):
                pass
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
        except Exception:
            pass

    if latencies:
        latencies.sort()
        results["sample_count"] = len(latencies)
        results["latencies_ms"] = latencies

        # Calculate percentiles
        results["latency_p50_ms"] = statistics.median(latencies)

        p95_idx = int(len(latencies) * 0.95)
        results["latency_p95_ms"] = latencies[min(p95_idx, len(latencies) - 1)]

        p99_idx = int(len(latencies) * 0.99)
        results["latency_p99_ms"] = latencies[min(p99_idx, len(latencies) - 1)]

        # Calculate throughput (requests per second)
        total_time_s = sum(latencies) / 1000
        if total_time_s > 0:
            results["throughput_rps"] = len(latencies) / total_time_s

    # Run concurrent throughput test if possible
    try:
        import concurrent.futures

        concurrent_requests = 50
        concurrent_latencies: list[float] = []

        def make_request() -> float:
            req_start = time.perf_counter()
            try:
                with urllib.request.urlopen(f"{api_url}{list_endpoint}", timeout=10):
                    pass
                return (time.perf_counter() - req_start) * 1000
            except Exception:
                return 0.0

        if verbose:
            typer.echo(f"  Running {concurrent_requests} concurrent requests...")

        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(concurrent_requests)]
            for future in concurrent.futures.as_completed(futures):
                latency = future.result()
                if latency > 0:
                    concurrent_latencies.append(latency)
        total_concurrent_time = time.perf_counter() - start

        if concurrent_latencies and total_concurrent_time > 0:
            # Concurrent throughput
            concurrent_rps = len(concurrent_latencies) / total_concurrent_time
            results["concurrent_throughput_rps"] = concurrent_rps
            if verbose:
                typer.echo(f"  Concurrent throughput: {concurrent_rps:.0f} req/s")

    except Exception as e:
        if verbose:
            typer.echo(f"  Concurrent test skipped: {e}")

    return results


def run_accessibility_checks(
    ui_url: str,
    level: str,
    appspec: "ir.AppSpec",
    verbose: bool,
) -> dict[str, Any]:
    """
    Run WCAG accessibility checks using Playwright and axe-core.

    Args:
        ui_url: URL of the UI to check
        level: WCAG level to check (A, AA, AAA)
        appspec: Application specification for mapping
        verbose: Whether to show verbose output

    Returns:
        Dictionary with accessibility check results
    """
    import asyncio

    results: dict[str, Any] = {
        "passed": True,
        "violation_count": 0,
        "violations": [],
        "pages_checked": [],
        "level": level,
        "error": None,
    }

    async def run_checks() -> dict[str, Any]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            results["error"] = "Playwright not installed. Install with: pip install playwright"
            results["passed"] = True  # Don't fail if playwright not available
            return results

        try:
            from dazzle_e2e.accessibility import AccessibilityChecker, AxeResults  # noqa: F401
        except ImportError:
            results["error"] = "dazzle_e2e not available"
            results["passed"] = True
            return results

        all_violations: list[dict[str, Any]] = []
        pages_checked: list[str] = []

        async with async_playwright() as p:
            # Launch headless browser
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                checker = AccessibilityChecker(page)

                # Check the main page
                try:
                    if verbose:
                        typer.echo(f"  Checking {ui_url}...")

                    await page.goto(ui_url, wait_until="networkidle", timeout=30000)
                    pages_checked.append(ui_url)

                    # Run axe-core at specified level
                    axe_results: AxeResults = await checker.check_wcag_level(level)

                    # Map to Dazzle elements
                    axe_results = await checker.map_to_dazzle(axe_results)

                    # Collect violations
                    for v in axe_results.violations:
                        violation_data = {
                            "id": v.id,
                            "impact": v.impact,
                            "description": v.description,
                            "help": v.help,
                            "help_url": v.help_url,
                            "wcag_level": v.wcag_level,
                            "nodes": [
                                {
                                    "html": n.html[:200],  # Truncate long HTML
                                    "target": n.target,
                                    "entity": n.dazzle_entity,
                                    "field": n.dazzle_field,
                                    "view": n.dazzle_view,
                                }
                                for n in v.nodes[:5]  # Limit nodes
                            ],
                        }
                        all_violations.append(violation_data)

                    if verbose:
                        typer.echo(
                            f"    Found {len(axe_results.violations)} violations, "
                            f"{len(axe_results.passes)} passed rules"
                        )

                except Exception as e:
                    if verbose:
                        typer.echo(f"  Error checking {ui_url}: {e}")
                    results["error"] = str(e)

                # Try to check additional views/workspaces from spec
                views_to_check: list[str] = []

                # Get workspace routes
                for workspace in appspec.workspaces:
                    if hasattr(workspace, "routes") and workspace.routes:
                        for route in workspace.routes:
                            if hasattr(route, "path") and route.path:
                                views_to_check.append(route.path)

                # Check a few additional pages (limit to 5 to keep tests fast)
                for view_path in views_to_check[:5]:
                    url = f"{ui_url.rstrip('/')}{view_path}"
                    try:
                        if verbose:
                            typer.echo(f"  Checking {url}...")

                        await page.goto(url, wait_until="networkidle", timeout=15000)
                        pages_checked.append(url)

                        axe_results = await checker.check_wcag_level(level)
                        axe_results = await checker.map_to_dazzle(axe_results)

                        for v in axe_results.violations:
                            # Avoid duplicates
                            if not any(
                                existing["id"] == v.id and existing["help"] == v.help
                                for existing in all_violations
                            ):
                                violation_data = {
                                    "id": v.id,
                                    "impact": v.impact,
                                    "description": v.description,
                                    "help": v.help,
                                    "help_url": v.help_url,
                                    "wcag_level": v.wcag_level,
                                    "page": url,
                                    "nodes": [
                                        {
                                            "html": n.html[:200],
                                            "target": n.target,
                                            "entity": n.dazzle_entity,
                                            "field": n.dazzle_field,
                                            "view": n.dazzle_view,
                                        }
                                        for n in v.nodes[:3]
                                    ],
                                }
                                all_violations.append(violation_data)

                    except Exception as e:
                        if verbose:
                            typer.echo(f"    Skipped {url}: {e}")

            finally:
                await browser.close()

        results["violations"] = all_violations
        results["violation_count"] = len(all_violations)
        results["passed"] = len(all_violations) == 0
        results["pages_checked"] = pages_checked

        return results

    # Run the async checks
    return asyncio.get_event_loop().run_until_complete(run_checks())
