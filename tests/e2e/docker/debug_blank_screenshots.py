#!/usr/bin/env python3
"""
Debug script to investigate blank screenshots in E2E tests.

This script starts the DNR server and uses Playwright to navigate to routes
while capturing browser console output to diagnose rendering issues.

Usage:
    cd /Volumes/SSD/Dazzle
    python tests/e2e/docker/debug_blank_screenshots.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def start_server(example_dir: Path) -> subprocess.Popen:
    """Start the DNR server for the given example."""
    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dazzle.cli",
            "dnr",
            "serve",
            "--test-mode",
        ],
        cwd=str(example_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to start
    time.sleep(8)
    return proc


def main():
    example_name = sys.argv[1] if len(sys.argv) > 1 else "simple_task"
    example_dir = Path("/Volumes/SSD/Dazzle/examples") / example_name

    if not example_dir.exists():
        print(f"Example directory not found: {example_dir}")
        sys.exit(1)

    print(f"=== Debugging blank screenshots for: {example_name} ===")
    print(f"Example directory: {example_dir}")

    # Start the server
    print("\n--- Starting DNR server ---")
    server = start_server(example_dir)

    try:
        # Test server is running
        import urllib.request
        try:
            response = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
            print(f"Server health: {response.read().decode()}")
        except Exception as e:
            print(f"Server not responding: {e}")
            print("Server stdout:", server.stdout.read().decode()[:1000])
            print("Server stderr:", server.stderr.read().decode()[:1000])
            return

        print("\n--- Starting Playwright browser ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()

            # Track console messages
            console_messages = []
            page_errors = []

            def on_console(msg):
                loc = msg.location
                entry = {
                    "type": msg.type,
                    "text": msg.text,
                    "url": loc.get("url", ""),
                    "line": loc.get("lineNumber", 0),
                }
                console_messages.append(entry)
                print(f"  CONSOLE {msg.type.upper():8} [{loc.get('url', 'unknown')}:{loc.get('lineNumber', 0)}] {msg.text[:150]}")

            def on_page_error(error):
                page_errors.append(str(error))
                print(f"  PAGE ERROR: {error}")

            page.on("console", on_console)
            page.on("pageerror", on_page_error)

            # Routes to test
            routes = [
                ("Dashboard", "http://localhost:3000/"),
                ("List View", "http://localhost:3000/task/list"),
                ("Create Form", "http://localhost:3000/task/create"),
            ]

            screenshot_dir = Path("/tmp/debug_screenshots")
            screenshot_dir.mkdir(exist_ok=True)

            for route_name, url in routes:
                print(f"\n{'='*60}")
                print(f"=== Testing route: {route_name} ({url}) ===")
                print(f"{'='*60}")

                console_messages.clear()
                page_errors.clear()

                try:
                    # Navigate and wait for network idle
                    page.goto(url, wait_until="networkidle", timeout=30000)

                    # Wait a bit for any JS rendering
                    time.sleep(2)

                    # Check what's on the page
                    html = page.content()
                    body_text = page.locator("body").inner_text()

                    print(f"\n--- Page content length: {len(html)} bytes ---")
                    print(f"--- Body text length: {len(body_text)} chars ---")
                    print(f"--- Body text preview: {body_text[:500]}...")

                    # Check for data-dazzle attributes
                    dazzle_elements = page.locator("[data-dazzle-surface]").count()
                    print(f"--- data-dazzle-surface elements: {dazzle_elements}")

                    # Take screenshot
                    screenshot_path = screenshot_dir / f"{example_name}_{route_name.lower().replace(' ', '_')}.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshot_size = screenshot_path.stat().st_size
                    print(f"--- Screenshot saved: {screenshot_path} ({screenshot_size} bytes)")

                    if screenshot_size < 10000:
                        print("  ⚠️  WARNING: Screenshot appears blank (< 10KB)")

                except Exception as e:
                    print(f"ERROR navigating to {url}: {e}")

                # Print console summary
                if console_messages:
                    print(f"\n--- Console messages ({len(console_messages)} total) ---")
                    errors = [m for m in console_messages if m["type"] == "error"]
                    warnings = [m for m in console_messages if m["type"] == "warning"]
                    if errors:
                        print(f"  ERRORS: {len(errors)}")
                        for e in errors:
                            print(f"    {e['text'][:200]}")
                    if warnings:
                        print(f"  WARNINGS: {len(warnings)}")

                if page_errors:
                    print(f"\n--- Page errors ({len(page_errors)} total) ---")
                    for e in page_errors:
                        print(f"  {e[:200]}")

            browser.close()

    finally:
        print("\n--- Stopping server ---")
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
