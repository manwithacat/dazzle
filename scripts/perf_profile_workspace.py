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


def _bench_browser_harness(
    harness_path: str, port: int = 8767, iterations: int = 10
) -> dict | None:
    """Run Playwright against a static harness and capture detailed
    paint / load / script-execution timings. Returns None if
    Playwright isn't available."""
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
            samples = []
            for _ in range(iterations):
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(f"http://localhost:{port}/{harness_path}")
                page.wait_for_function(
                    "typeof Alpine !== 'undefined' "
                    "&& document.querySelectorAll('[data-card-id]').length > 0",
                    timeout=10000,
                )
                metrics = page.evaluate(
                    """() => {
                        const t = performance.timing;
                        const paints = performance.getEntriesByType('paint');
                        const fcp = paints.find(p => p.name === 'first-contentful-paint');
                        const fp = paints.find(p => p.name === 'first-paint');
                        const marks = {};
                        for (const m of performance.getEntriesByType('mark')) {
                            marks[m.name] = m.startTime;
                        }
                        const dclStart = t.domContentLoadedEventStart - t.navigationStart;
                        const resources = performance.getEntriesByType('resource').map(r => ({
                            name: r.name.split('/').slice(-1)[0],
                            type: r.initiatorType,
                            duration: r.duration,
                            transferSize: r.transferSize,
                            startTime: r.startTime,
                            responseEnd: r.responseEnd,
                            isSync: r.initiatorType === 'script' && r.responseEnd < dclStart,
                        }));
                        const syncScripts = resources.filter(r => r.isSync);
                        const syncScriptDuration = syncScripts.reduce(
                            (s, r) => s + r.duration, 0
                        );
                        return {
                            ttfb_ms: t.responseStart - t.navigationStart,
                            domContentLoaded_ms: t.domContentLoadedEventEnd - t.navigationStart,
                            load_ms: t.loadEventEnd - t.navigationStart,
                            firstPaint_ms: fp ? fp.startTime : null,
                            firstContentfulPaint_ms: fcp ? fcp.startTime : null,
                            alpineInit_ms: marks['perf-harness:alpine-init'] || null,
                            cardsRendered_ms: marks['perf-harness:18-cards-rendered'] || null,
                            domNodes: document.getElementsByTagName('*').length,
                            cardCount: document.querySelectorAll('[data-card-id]').length,
                            syncScriptCount: syncScripts.length,
                            syncScriptDuration_ms: syncScriptDuration,
                            totalResourceCount: resources.length,
                            totalTransferKb: resources.reduce(
                                (s, r) => s + (r.transferSize || 0), 0
                            ) / 1024,
                            topResources: resources
                                .sort((a, b) => b.duration - a.duration)
                                .slice(0, 5)
                                .map(r => ({
                                    name: r.name,
                                    ms: r.duration,
                                    sizeKb: r.transferSize / 1024,
                                })),
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
            "p50": round(statistics.median(vals), 2),
            "p95": round(sorted(vals)[int(0.95 * len(vals))], 2)
            if len(vals) > 1
            else round(vals[0], 2),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
        }

    return {
        "harness": harness_path,
        "iterations": len(samples),
        "ttfb_ms": _agg("ttfb_ms"),
        "firstPaint_ms": _agg("firstPaint_ms"),
        "firstContentfulPaint_ms": _agg("firstContentfulPaint_ms"),
        "alpineInit_ms": _agg("alpineInit_ms"),
        "cardsRendered_ms": _agg("cardsRendered_ms"),
        "domContentLoaded_ms": _agg("domContentLoaded_ms"),
        "load_ms": _agg("load_ms"),
        "syncScriptDuration_ms": _agg("syncScriptDuration_ms"),
        "syncScriptCount": samples[0]["syncScriptCount"] if samples else None,
        "totalResourceCount": samples[0]["totalResourceCount"] if samples else None,
        "totalTransferKb": round(samples[0]["totalTransferKb"], 1) if samples else None,
        "domNodes": samples[0]["domNodes"] if samples else None,
        "cardCount": samples[0]["cardCount"] if samples else None,
        "topResources": samples[0]["topResources"] if samples else None,
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


def _print_browser_results(results: dict | None, label: str) -> None:
    if results is None:
        print(f"Browser profile [{label}]: SKIPPED (Playwright unavailable)")
        return
    print("=" * 78)
    print(f"Client-side profile: {label} ({results.get('cardCount')} cards)")
    print("=" * 78)
    print(f"Harness: {results['harness']}")
    print(f"Iterations: {results['iterations']}")
    print(f"DOM nodes: {results['domNodes']}")
    print(
        f"Resources: {results['totalResourceCount']} files, "
        f"{results['totalTransferKb']} KB total transfer"
    )
    print(f"Sync scripts blocking parser: {results['syncScriptCount']}")
    print()
    print(f"{'metric':>30} {'p50':>10} {'p95':>10} {'min':>10} {'max':>10}")
    print("-" * 78)
    for key in (
        "ttfb_ms",
        "firstPaint_ms",
        "firstContentfulPaint_ms",
        "alpineInit_ms",
        "cardsRendered_ms",
        "domContentLoaded_ms",
        "load_ms",
        "syncScriptDuration_ms",
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
    if results.get("topResources"):
        print("Top 5 longest resources:")
        for r in results["topResources"]:
            print(f"  {r['name']:40s} {r['ms']:>8.1f} ms  {r['sizeKb']:>7.1f} KB")
        print()


def main() -> None:
    print()
    jinja_results = []
    for n in (4, 18, 50):
        jinja_results.append(_bench_jinja_render(n))
    _print_jinja_results(jinja_results)

    # Realistic harness: full base.html script chain + 18 cards.
    browser_realistic = _bench_browser_harness("test-workspace-perf.html")
    _print_browser_results(browser_realistic, "realistic (full script chain, 18 cards)")

    # Minimal harness: just dashboard-builder.js + alpine, 4 cards.
    # Useful as a reference point for what's "irreducible" overhead.
    browser_minimal = _bench_browser_harness("test-dashboard.html")
    _print_browser_results(browser_minimal, "minimal (just Alpine + builder, 4 cards)")


if __name__ == "__main__":
    main()
