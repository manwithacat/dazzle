"""CLI entry for ``dazzle ux verify --interactions``.

Runs the v1 INTERACTION_WALK harness against the current project:

1. Spawn ``dazzle serve --local`` via
   :func:`dazzle.testing.ux.interactions.server_fixture.launch_interaction_server`.
2. Open a sync Playwright browser.
3. Navigate to the workspace landing page.
4. Build a default walk (card_remove_reachable + card_drag +
   card_add) using the first card / first catalog region it finds.
5. Run the walk via :func:`dazzle.testing.ux.interactions.run_walk`.
6. Emit a report and exit 0 (pass) / 1 (regression) / 2 (setup).

Extraction rationale: ``src/dazzle/cli/ux.py`` already holds the
``verify_command`` entry point + ``--contracts``/``--browser`` routes.
Putting the --interactions logic in a sibling module keeps ux.py
focused on orchestration and makes this module independently
testable (_build_default_walk is a pure function).
"""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.testing.ux.interactions import (
    CardAddInteraction,
    CardDragInteraction,
    CardRemoveReachableInteraction,
    Interaction,
    InteractionResult,
    run_walk,
)
from dazzle.testing.ux.interactions.server_fixture import (
    InteractionServerError,
    launch_interaction_server,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


# Exit codes — mirror the design-doc contract.
EXIT_PASS = 0
EXIT_REGRESSION = 1
EXIT_SETUP_FAILURE = 2


def _default_workspace_path(page: Page) -> str:
    """Return the path of the first workspace we should drive.

    Reads ``window.location.pathname`` after ``goto("/")`` — typically
    redirects to the persona's default workspace. Falls back to
    ``/app`` if the redirect didn't happen.
    """
    current = page.evaluate("() => window.location.pathname")
    if isinstance(current, str) and current.startswith("/app"):
        return current
    return "/app"


def _layout_card_ids_and_catalog(page: Page) -> tuple[list[str], list[str]]:
    """Extract the workspace's card ids + catalog region names from
    the embedded ``#dz-workspace-layout`` JSON.

    Returns ``([], [])`` if the page isn't a workspace page.
    """
    layout = page.evaluate(
        """() => {
          const el = document.getElementById('dz-workspace-layout');
          if (!el) return null;
          try { return JSON.parse(el.textContent); } catch { return null; }
        }"""
    )
    if not isinstance(layout, dict):
        return [], []
    cards = layout.get("cards") or []
    catalog = layout.get("catalog") or []
    card_ids = [str(c["id"]) for c in cards if isinstance(c, dict) and c.get("id")]
    region_names = [str(c["name"]) for c in catalog if isinstance(c, dict) and c.get("name")]
    return card_ids, region_names


def _build_default_walk(card_ids: list[str], catalog_regions: list[str]) -> list[Interaction]:
    """Build the v1 walk from the discovered card ids + catalog.

    Pure function — no Page reference — so it's unit-testable without
    a live browser. Invoked from :func:`run_interaction_walk` after
    layout extraction.

    Returns ``[]`` if neither a card nor a catalog entry exists (the
    caller treats that as a setup failure, not a regression).
    """
    walk: list[Interaction] = []
    if card_ids:
        # card_remove_reachable and card_drag both need a card to
        # operate on. Prefer the first card — workspace layouts
        # order them deterministically.
        walk.append(CardRemoveReachableInteraction(card_id=card_ids[0]))
        walk.append(CardDragInteraction(card_id=card_ids[0]))
    if catalog_regions:
        # card_add picks a region from the catalog. Pick the first
        # one — if the dashboard shows the same region twice the
        # walk will still work (both cards get their own fetch).
        walk.append(CardAddInteraction(region=catalog_regions[0]))
    return walk


def _render_human_report(results: list[InteractionResult]) -> str:
    if not results:
        return "No interactions ran (layout had no cards and no catalog entries)."
    lines = ["INTERACTION_WALK report", "=" * 40]
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.name}")
        if not r.passed and r.reason:
            lines.append(f"         reason: {r.reason}")
        if r.evidence:
            ev = ", ".join(f"{k}={v}" for k, v in r.evidence.items())
            lines.append(f"         evidence: {ev}")
    return "\n".join(lines)


def _render_json_report(results: list[InteractionResult]) -> str:
    payload: dict[str, Any] = {
        "results": [asdict(r) for r in results],
        "passed": all(r.passed for r in results) if results else False,
        "count": len(results),
    }
    return json.dumps(payload, indent=2)


def run_interaction_walk(
    project_root: Path,
    *,
    headless: bool = True,
    json_output: bool = False,
    persona: str = "",
) -> int:
    """Execute the default interaction walk against ``project_root``.

    Returns an exit code (0/1/2) for the caller to raise via
    ``typer.Exit``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Install with: pip install 'dazzle-dsl[e2e]'",
            file=sys.stderr,
        )
        return EXIT_SETUP_FAILURE

    # Read the shared test-mode secret from runtime.json (written by
    # `dazzle serve` in test mode). The /__test__/authenticate
    # endpoint requires the X-Test-Secret header match this value,
    # otherwise it rejects with 403. See #790.
    from dazzle.cli.runtime_impl.ports import read_runtime_test_secret

    try:
        with launch_interaction_server(project_root) as conn:
            test_secret = read_runtime_test_secret(project_root) or ""
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context()
                try:
                    # Authenticate BEFORE the first goto so /app doesn't
                    # redirect us to /login. Most Dazzle apps gate the
                    # workspace dashboard behind auth; without this the
                    # harness lands on /login, sees no layout JSON, and
                    # reports "no cards" (false setup-failure).
                    if persona:
                        _authenticate_persona_on_context(
                            context, conn.site_url, persona, test_secret=test_secret
                        )

                    page = context.new_page()

                    # Capture page-level XHR + console output from the
                    # very first navigation so the harness diagnostics
                    # can see what the browser does on load. Useful
                    # when the Add-Card fetch never fires and we need
                    # to distinguish "HTMX never triggered for any
                    # card" from "HTMX triggered for initial cards
                    # but not the added one". Dumped when a walk
                    # fails — see CardAddInteraction.
                    page_xhr: list[str] = []
                    page_console: list[str] = []

                    def _on_page_request(request: object) -> None:
                        # Diagnostic capture only; never fail page load if a request
                        # object is missing the expected attributes (#smells-1.1).
                        with suppress(Exception):
                            page_xhr.append(getattr(request, "url", ""))

                    def _on_console(msg: object) -> None:
                        # Diagnostic capture only (#smells-1.1).
                        with suppress(Exception):
                            page_console.append(
                                f"{getattr(msg, 'type', '?')}: {getattr(msg, 'text', '')}"
                            )

                    page.on("request", _on_page_request)
                    page.on("console", _on_console)
                    page.goto(conn.site_url + "/app", timeout=15_000)
                    page.wait_for_load_state("networkidle", timeout=15_000)

                    # Summarise what the initial page fetched + logged
                    # so CI logs tell us whether HTMX actually fires
                    # for EXISTING cards on page load. If even those
                    # are missing, the regression is broader than just
                    # addCard's kickoff.
                    initial_api_urls = [u for u in page_xhr if "/api/" in u]
                    print(
                        f"[init] URL={page.url} "
                        f"initial_api_calls={len(initial_api_urls)} "
                        f"console_messages={len(page_console)}",
                        file=sys.stderr,
                    )
                    if initial_api_urls[:5]:
                        print(
                            f"[init] sample_api_urls={initial_api_urls[:5]}",
                            file=sys.stderr,
                        )
                    for msg in page_console[:30]:
                        print(f"[console] {msg}", file=sys.stderr)

                    card_ids, catalog = _layout_card_ids_and_catalog(page)
                    walk = _build_default_walk(card_ids, catalog)
                    if not walk:
                        # Diagnostic dump — walk builds against the
                        # #dz-workspace-layout JSON, so if that's not
                        # there the harness can't do anything. Print
                        # enough context to tell whether we're on a
                        # login page, a workspace with an empty
                        # layout, or somewhere unexpected.
                        current_url = page.url
                        has_layout = page.evaluate(
                            "() => !!document.getElementById('dz-workspace-layout')"
                        )
                        title = page.title() or "(no title)"
                        print(
                            "No interactions to run — the workspace has no "
                            "cards and no catalog entries.\n"
                            f"  current URL: {current_url}\n"
                            f"  page title:  {title}\n"
                            f"  layout JSON present: {has_layout}\n"
                            f"  layout cards: {card_ids!r}\n"
                            f"  layout catalog: {catalog!r}\n"
                            "If current URL ends in /login the persona auth "
                            "failed. If the layout JSON is absent but the URL "
                            "is /app/..., the workspace template didn't "
                            "render. If the JSON is present but empty, the "
                            "workspace has no regions or the user has no "
                            "default layout.",
                            file=sys.stderr,
                        )
                        return EXIT_SETUP_FAILURE

                    results = run_walk(page, walk)

                    # Post-walk console dump — surfaces any console
                    # messages (including targeted console.log output
                    # from addCard / other walk-triggered paths) that
                    # arrived after the initial page-load capture.
                    post_walk_msgs = page_console[len(page_console) - 50 :]
                    for msg in post_walk_msgs:
                        if "dz-" in msg or "error" in msg.lower():
                            print(f"[post-walk] {msg}", file=sys.stderr)
                finally:
                    context.close()
                    browser.close()
    except InteractionServerError as exc:
        print(f"Server setup failed: {exc}", file=sys.stderr)
        return EXIT_SETUP_FAILURE

    report = _render_json_report(results) if json_output else _render_human_report(results)
    print(report)

    return EXIT_PASS if all(r.passed for r in results) else EXIT_REGRESSION


def _authenticate_persona_on_context(
    context: Any, site_url: str, persona: str, test_secret: str = ""
) -> None:
    """Log the Playwright browser in as ``persona`` by installing the
    session cookie on the ``BrowserContext`` BEFORE any navigation.

    The test endpoint (``/__test__/authenticate``) is what
    ``HtmxClient.authenticate`` already uses for contract tests —
    reuse its protocol. Requires ``test_mode`` enabled on the server,
    which ``dazzle serve --local`` does by default.

    The endpoint also requires an ``X-Test-Secret`` header matching
    the server's generated per-run secret (#790). We read the value
    from ``runtime.json`` via
    :func:`dazzle.cli.runtime_impl.ports.read_runtime_test_secret`
    and pass it here. Without the header, the endpoint returns 403.

    Installing the cookie at the context level means the first
    ``page.goto("/app")`` is authenticated — avoiding the redirect to
    ``/login`` that leaves the harness staring at a non-workspace
    page.

    Prints a diagnostic to stderr on any failure path so a CI run
    tells us whether the endpoint returned non-200, returned 200 with
    no token, or just couldn't be reached. Silent failure was the
    original sin.
    """
    import httpx

    headers: dict[str, str] = {}
    if test_secret:
        headers["X-Test-Secret"] = test_secret

    try:
        with httpx.Client() as client:
            resp = client.post(
                f"{site_url}/__test__/authenticate",
                json={"role": persona, "username": persona},
                headers=headers,
                timeout=10,
            )
    except Exception as exc:
        print(
            f"[auth] POST {site_url}/__test__/authenticate raised {exc!r}. "
            "Is test-mode enabled on the server?",
            file=sys.stderr,
        )
        return

    if resp.status_code != 200:
        print(
            f"[auth] /__test__/authenticate returned HTTP {resp.status_code} "
            f"(body: {resp.text[:200]!r}). Persona {persona!r} may not be a "
            f"valid role, or test-mode may be disabled.",
            file=sys.stderr,
        )
        return
    data = resp.json()
    token = data.get("session_token", "") or data.get("token", "")

    if not token:
        print(
            f"[auth] /__test__/authenticate returned 200 but no session_token "
            f"(body keys: {list(data.keys())!r}).",
            file=sys.stderr,
        )
        return
    context.add_cookies(
        [
            {
                "name": "dazzle_session",
                "value": token,
                "url": site_url,
            }
        ]
    )
