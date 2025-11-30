#!/usr/bin/env python3
"""Generate screenshots for DAZZLE example projects.

This script starts each example's DNR server, captures screenshots of key routes,
and saves them to docs/examples/<example>/screenshots/.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Try to import playwright
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Install with: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)


# Example configurations: name -> (routes to screenshot, seed data)
EXAMPLES = {
    "simple_task": {
        "routes": ["/", "/task/list", "/task/create"],
        "seed": [
            {
                "entity": "Task",
                "data": {
                    "title": "Review Q4 Reports",
                    "description": "Review quarterly financial reports",
                    "status": "in_progress",
                    "priority": "high",
                },
            },
            {
                "entity": "Task",
                "data": {
                    "title": "Update Documentation",
                    "description": "Update API docs for v2.0",
                    "status": "todo",
                    "priority": "medium",
                },
            },
            {
                "entity": "Task",
                "data": {
                    "title": "Deploy to Staging",
                    "description": "Deploy latest changes to staging environment",
                    "status": "done",
                    "priority": "high",
                },
            },
        ],
    },
    "contact_manager": {
        "routes": ["/", "/contact/list", "/contact/create"],
        "seed": [
            {
                "entity": "Contact",
                "data": {
                    "first_name": "Alice",
                    "last_name": "Johnson",
                    "email": "alice@example.com",
                    "phone": "+1-555-0101",
                    "company": "Acme Corp",
                    "job_title": "Senior Engineer",
                },
            },
            {
                "entity": "Contact",
                "data": {
                    "first_name": "Bob",
                    "last_name": "Smith",
                    "email": "bob@example.com",
                    "phone": "+1-555-0102",
                    "company": "TechStart Inc",
                    "job_title": "Product Manager",
                },
            },
        ],
    },
    "uptime_monitor": {
        "routes": ["/", "/service/list"],
        "seed": [
            {
                "entity": "Service",
                "data": {
                    "name": "API Gateway",
                    "endpoint": "https://api.example.com/health",
                    "status": "up",
                    "uptime_percentage": "99.95",
                },
            },
            {
                "entity": "Service",
                "data": {
                    "name": "Database Cluster",
                    "endpoint": "https://db.example.com/health",
                    "status": "up",
                    "uptime_percentage": "99.99",
                },
            },
            {
                "entity": "Service",
                "data": {
                    "name": "Auth Service",
                    "endpoint": "https://auth.example.com/health",
                    "status": "degraded",
                    "uptime_percentage": "98.50",
                },
            },
        ],
    },
    "inventory_scanner": {
        "routes": ["/", "/product/list"],
        "seed": [
            {
                "entity": "Product",
                "data": {
                    "name": "Widget Pro X",
                    "sku": "WPX-001",
                    "quantity": 150,
                    "price": "29.99",
                },
            },
            {
                "entity": "Product",
                "data": {
                    "name": "Gadget Plus",
                    "sku": "GP-002",
                    "quantity": 75,
                    "price": "49.99",
                },
            },
        ],
    },
    "email_client": {
        "routes": ["/", "/email/list"],
        "seed": [
            {
                "entity": "Email",
                "data": {
                    "subject": "Weekly Report",
                    "sender": "reports@company.com",
                    "preview": "Here is your weekly summary...",
                    "is_read": False,
                },
            },
            {
                "entity": "Email",
                "data": {
                    "subject": "Meeting Tomorrow",
                    "sender": "calendar@company.com",
                    "preview": "Reminder: Team sync at 10am",
                    "is_read": True,
                },
            },
        ],
    },
    "ops_dashboard": {
        "routes": ["/"],
        "seed": [
            {
                "entity": "Server",
                "data": {
                    "name": "prod-web-01",
                    "status": "healthy",
                    "cpu_usage": "45.5",
                    "memory_usage": "62.3",
                },
            },
            {
                "entity": "Server",
                "data": {
                    "name": "prod-db-01",
                    "status": "healthy",
                    "cpu_usage": "78.2",
                    "memory_usage": "85.1",
                },
            },
        ],
    },
}


def wait_for_server(port: int, timeout: int = 30) -> bool:
    """Wait for server to be ready."""
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def seed_data(fixtures: list, port: int = 8000) -> None:
    """Seed test data via the test API."""
    import urllib.request

    seed_request = {"fixtures": [{"id": f"fixture_{i}", **f} for i, f in enumerate(fixtures)]}

    req = urllib.request.Request(
        f"http://localhost:{port}/__test__/seed",
        data=json.dumps(seed_request).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Warning: Failed to seed data: {e}")


def capture_screenshots(example: str, config: dict, output_dir: Path) -> list:
    """Capture screenshots for an example."""
    screenshots = []
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        for route in config["routes"]:
            # Normalize route name for filename
            route_name = route.replace("/", "_").strip("_") or "home"
            filename = f"{route_name}.png"
            filepath = output_dir / filename

            try:
                page.goto(f"http://localhost:3000{route}", wait_until="networkidle", timeout=10000)
                page.wait_for_timeout(500)  # Let signals settle
                page.screenshot(path=str(filepath), full_page=False)
                screenshots.append(filename)
                print(f"    Captured: {filename}")
            except Exception as e:
                print(f"    Failed to capture {route}: {e}")

        browser.close()

    return screenshots


def main():
    repo_root = Path(__file__).parent.parent
    examples_dir = repo_root / "examples"
    docs_examples_dir = repo_root / "docs" / "examples"

    # Process each example
    for example_name, config in EXAMPLES.items():
        example_path = examples_dir / example_name
        if not example_path.exists():
            print(f"Skipping {example_name}: not found")
            continue

        print(f"\nProcessing {example_name}...")
        output_dir = docs_examples_dir / example_name / "screenshots"

        # Start server
        print(f"  Starting DNR server...")
        server_proc = subprocess.Popen(
            ["dazzle", "dnr", "serve", "--test-mode"],
            cwd=str(example_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )

        try:
            if not wait_for_server(8000):
                print(f"  Failed to start server for {example_name}")
                continue

            # Seed data
            if config.get("seed"):
                print(f"  Seeding test data...")
                seed_data(config["seed"])

            # Capture screenshots
            print(f"  Capturing screenshots...")
            screenshots = capture_screenshots(example_name, config, output_dir)
            print(f"  Captured {len(screenshots)} screenshots")

        finally:
            # Kill server process group
            try:
                os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

            # Cleanup any remaining processes
            subprocess.run(["pkill", "-f", "dazzle dnr serve"], capture_output=True)
            time.sleep(1)

    print("\nDone! Screenshots saved to docs/examples/*/screenshots/")


if __name__ == "__main__":
    main()
