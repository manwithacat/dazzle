"""Profile workspace render performance.

Measures two layers:

1. **Server-side Jinja render** — how long does it take to render the
   `workspace/_content.html` template for a workspace with N regions?
   This is pure CPU; it stresses Jinja's iteration + string-concat
   path. Run with N=4 (small dashboard), N=18 (AegisMark
   teacher_workspace), N=50 (admin pathological case).

2. **Client-side first paint** — how long until the browser paints
   the first frame of a server-rendered workspace? Driven via
   Playwright against the static `test-dashboard.html` harness so
   we don't need a live DB. Captures FCP / LCP / DOMContentLoaded /
   load events from the Performance API.

Run locally: `python scripts/perf_profile_workspace.py`

Results are printed; nothing is written to disk. Compare against
the baseline section in the printed output to spot regressions.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _make_workspace_ctx(n_regions: int):
    """Build a synthetic WorkspaceContext with N regions for profiling."""
    from dazzle_ui.runtime.workspace_renderer import RegionContext, WorkspaceContext

    regions = []
    for i in range(n_regions):
        # Mirror the shape AegisMark uses — a mix of features per region
        # to avoid measuring an unrealistically minimal case.
        notice = (
            {"title": "Heads up", "body": "Status as of last sync", "tone": "neutral"}
            if i % 5 == 0
            else None
        )
        regions.append(
            RegionContext(
                name=f"region_{i}",
                title=f"Region {i}",
                source="Item",
                col_span=6 if i % 2 == 0 else 4,
                eyebrow=f"Section {i // 4}" if i % 3 == 0 else "",
                notice=notice or {},
                css_class="action-band" if i % 7 == 0 else "",
            )
        )
    return WorkspaceContext(
        name=f"profile_ws_{n_regions}",
        title=f"Profile Workspace ({n_regions} regions)",
        regions=regions,
    )


def _bench_jinja_render(n_regions: int, iterations: int = 20) -> dict:
    """Render `workspace/_content.html` `iterations` times with `n_regions`
    regions and return timing stats."""
    from dazzle_ui.runtime.template_renderer import render_fragment

    ws = _make_workspace_ctx(n_regions)
    fold_count = min(3, n_regions)

    # Warm the template cache so the first iteration's compilation
    # doesn't dominate.
    render_fragment(
        "workspace/_content.html",
        workspace=ws,
        fold_count=fold_count,
        primary_actions=[],
    )

    durations_ms: list[float] = []
    sizes_bytes: list[int] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        html = render_fragment(
            "workspace/_content.html",
            workspace=ws,
            fold_count=fold_count,
            primary_actions=[],
        )
        durations_ms.append((time.perf_counter() - t0) * 1000)
        sizes_bytes.append(len(html.encode("utf-8")))

    return {
        "n_regions": n_regions,
        "iterations": iterations,
        "p50_ms": statistics.median(durations_ms),
        "p95_ms": sorted(durations_ms)[int(0.95 * len(durations_ms))],
        "min_ms": min(durations_ms),
        "max_ms": max(durations_ms),
        "mean_ms": statistics.mean(durations_ms),
        "size_kb": sizes_bytes[0] / 1024.0,
    }


def _bench_static_harness(port: int = 8767) -> dict | None:
    """Run Playwright against the static dashboard harness and capture
    paint/load timings. Returns None if Playwright isn't available."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    static_dir = REPO_ROOT / "src/dazzle_ui/runtime/static"
    proc = subprocess.Popen(
        [
            "python3",
            "-m",
            "http.server",
            str(port),
            "--directory",
            str(static_dir),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Run 10 iterations to get a stable reading. Each iteration
            # opens a fresh page so DNS/keep-alive doesn't bias the
            # results.
            samples = []
            for _ in range(10):
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(f"http://localhost:{port}/test-dashboard.html")
                page.wait_for_function(
                    "typeof Alpine !== 'undefined' "
                    "&& document.querySelector('[data-card-id]') !== null",
                    timeout=10000,
                )
                metrics = page.evaluate(
                    """() => {
                        const t = performance.timing;
                        const paints = performance.getEntriesByType('paint');
                        const fcp = paints.find(p => p.name === 'first-contentful-paint');
                        const fp = paints.find(p => p.name === 'first-paint');
                        return {
                            ttfb_ms: t.responseStart - t.navigationStart,
                            response_ms: t.responseEnd - t.responseStart,
                            domContentLoaded_ms: t.domContentLoadedEventEnd - t.navigationStart,
                            load_ms: t.loadEventEnd - t.navigationStart,
                            firstPaint_ms: fp ? fp.startTime : null,
                            firstContentfulPaint_ms: fcp ? fcp.startTime : null,
                            domNodes: document.getElementsByTagName('*').length,
                        };
                    }"""
                )
                samples.append(metrics)
                page.close()

            browser.close()
    finally:
        proc.terminate()
        proc.wait()

    def _agg(key: str) -> dict:
        vals = [s[key] for s in samples if s.get(key) is not None]
        if not vals:
            return {}
        return {
            "p50": statistics.median(vals),
            "p95": sorted(vals)[int(0.95 * len(vals))] if len(vals) > 1 else vals[0],
            "min": min(vals),
            "max": max(vals),
        }

    return {
        "iterations": len(samples),
        "ttfb_ms": _agg("ttfb_ms"),
        "response_ms": _agg("response_ms"),
        "domContentLoaded_ms": _agg("domContentLoaded_ms"),
        "load_ms": _agg("load_ms"),
        "firstPaint_ms": _agg("firstPaint_ms"),
        "firstContentfulPaint_ms": _agg("firstContentfulPaint_ms"),
        "domNodes": samples[0]["domNodes"] if samples else None,
    }


def _print_jinja_results(results: list[dict]) -> None:
    print("=" * 78)
    print("Server-side Jinja render: workspace/_content.html")
    print("=" * 78)
    print(
        f"{'regions':>8} {'p50 ms':>10} {'p95 ms':>10} {'min ms':>10} {'max ms':>10} {'size KB':>10}"
    )
    print("-" * 78)
    for r in results:
        print(
            f"{r['n_regions']:>8} "
            f"{r['p50_ms']:>10.3f} "
            f"{r['p95_ms']:>10.3f} "
            f"{r['min_ms']:>10.3f} "
            f"{r['max_ms']:>10.3f} "
            f"{r['size_kb']:>10.1f}"
        )
    print()


def _print_browser_results(results: dict | None) -> None:
    if results is None:
        print("Client-side first-paint profile: SKIPPED (Playwright unavailable)")
        return
    print("=" * 78)
    print("Client-side first-paint profile: test-dashboard.html (4 cards, static)")
    print("=" * 78)
    print(f"Iterations: {results['iterations']}")
    print(f"DOM nodes: {results['domNodes']}")
    print(f"{'metric':>30} {'p50':>10} {'p95':>10} {'min':>10} {'max':>10}")
    print("-" * 78)
    for key in (
        "ttfb_ms",
        "response_ms",
        "firstPaint_ms",
        "firstContentfulPaint_ms",
        "domContentLoaded_ms",
        "load_ms",
    ):
        agg = results.get(key) or {}
        print(
            f"{key:>30} "
            f"{agg.get('p50', 'n/a'):>10} "
            f"{agg.get('p95', 'n/a'):>10} "
            f"{agg.get('min', 'n/a'):>10} "
            f"{agg.get('max', 'n/a'):>10}"
        )
    print()


def main() -> None:
    print()
    jinja_results = []
    for n in (4, 18, 50):
        jinja_results.append(_bench_jinja_render(n))
    _print_jinja_results(jinja_results)

    browser = _bench_static_harness()
    _print_browser_results(browser)


if __name__ == "__main__":
    main()
