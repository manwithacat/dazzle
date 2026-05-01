"""Stateless Playwright driver for cycle 198's subagent-driven explore path.

Each invocation is a one-shot subprocess: launch browser, load
storage_state from ``<state_dir>/state.json``, navigate to the last known
URL, perform one action, save state, exit. Session persists across calls
because the storage_state file holds cookies + localStorage.

Usage::

    python -m dazzle.agent.playwright_helper --state-dir DIR login <api_url> <persona_id>
    python -m dazzle.agent.playwright_helper --state-dir DIR observe
    python -m dazzle.agent.playwright_helper --state-dir DIR navigate <path_or_url>
    python -m dazzle.agent.playwright_helper --state-dir DIR click '<css_selector>'
    python -m dazzle.agent.playwright_helper --state-dir DIR type '<selector>' '<text>'
    python -m dazzle.agent.playwright_helper --state-dir DIR select '<selector>' '<value>'
    python -m dazzle.agent.playwright_helper --state-dir DIR wait '<selector>'

All output is a single JSON object on stdout. Errors include an ``error``
field with the exception message and ``error_type`` with the class name.

Design notes (cycle 198):

- The helper is a module-entry (``python -m``) not a script so it imports
  cleanly alongside the rest of the dazzle package. The subagent driving
  it via Bash doesn't need to know an absolute file path.

- State lives in a caller-provided ``--state-dir`` instead of a hardcoded
  ``/tmp`` path so concurrent explore runs against different examples (or
  different personas on the same example) can coexist without clobbering
  each other's cookies.

- The ``login`` action is special: it POSTs ``/qa/magic-link``, follows the
  resulting redirect to create a session cookie, then saves the context as
  the run's storage_state. After login, subsequent actions reuse the saved
  state.

- The ``wait`` action was added in cycle 198 — the spike didn't need it,
  but exploration missions that observe loading states will.

- The ``select`` action was added in cycle 202 after cycle 201's edge_cases
  run surfaced the gap: the subagent couldn't drive ``<select>`` elements,
  which blocked root-causing the support_tickets silent-submit bug
  (findings EX-007). ``select`` uses Playwright's ``select_option`` which
  accepts either a value string or a visible label.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

INTERACTIVE_ELEMENT_LIMIT = 40
VISIBLE_TEXT_LIMIT = 2000
ELEMENT_TEXT_LIMIT = 100
DEFAULT_TIMEOUT_MS = 5000


def _paths(state_dir: Path) -> tuple[Path, Path, Path]:
    """Return (state_path, base_url_path, last_url_path) for a given state_dir."""
    return (
        state_dir / "state.json",
        state_dir / "base_url.txt",
        state_dir / "last_url.txt",
    )


async def _launch(state_dir: Path, timeout_ms: int) -> tuple[Any, Any, Any, Any]:
    """Launch Chromium, load storage_state if present, restore last URL."""
    from playwright.async_api import async_playwright

    state_path, base_url_path, last_url_path = _paths(state_dir)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)

    base_url = base_url_path.read_text().strip() if base_url_path.exists() else None
    ctx_kwargs: dict[str, Any] = {}
    if base_url:
        ctx_kwargs["base_url"] = base_url
    if state_path.exists():
        ctx_kwargs["storage_state"] = str(state_path)

    ctx = await browser.new_context(**ctx_kwargs)
    page = await ctx.new_page()

    # Restore last known URL so subagent actions continue from where
    # they left off. First-call (post-login) case: last_url_path holds
    # the URL set by login(); every subsequent call reads it.
    if last_url_path.exists():
        last = last_url_path.read_text().strip()
        if last:
            # Stale URL — leave page at default if nav fails (#smells-1.1)
            with suppress(Exception):
                await page.goto(last)
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)

    return pw, browser, ctx, page


async def _teardown(
    pw: Any,
    browser: Any,
    ctx: Any,
    page: Any,
    state_dir: Path,
    *,
    save_state: bool = True,
) -> None:
    state_path, _, last_url_path = _paths(state_dir)
    if save_state:
        # Best-effort persistence — these run during cleanup, after the
        # action has already produced its effect. Failures here don't
        # invalidate the action; suppress and continue. (#smells-1.1)
        with suppress(Exception):
            await ctx.storage_state(path=str(state_path))
        with suppress(Exception):
            last_url_path.write_text(page.url)
    await ctx.close()
    await browser.close()
    await pw.stop()


async def action_login(
    api_url: str, persona_id: str, state_dir: Path, timeout_ms: int
) -> dict[str, Any]:
    """POST /qa/magic-link, consume the redirect, save storage_state."""
    from playwright.async_api import async_playwright

    state_path, base_url_path, last_url_path = _paths(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    base_url_path.write_text(api_url)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(base_url=api_url)
    page = await ctx.new_page()

    try:
        response = await page.request.post(
            f"{api_url}/qa/magic-link",
            data=json.dumps({"persona_id": persona_id}),
            headers={"Content-Type": "application/json"},
        )
        if not response.ok:
            return {
                "error": f"magic-link POST failed: HTTP {response.status}",
                "persona": persona_id,
            }
        payload = await response.json()
        magic_path = payload.get("url")
        if not magic_path:
            return {"error": "magic-link response missing 'url' field"}
        await page.goto(f"{api_url}{magic_path}?next=/")
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)

        # Sanity check: didn't bounce to /auth/login
        from urllib.parse import urlparse

        final_path = urlparse(page.url).path
        if final_path in ("/auth/login", "/login"):
            return {
                "error": "login rejected — final URL on /auth/login",
                "final_url": page.url,
            }

        await ctx.storage_state(path=str(state_path))
        last_url_path.write_text(page.url)
        return {"status": "logged_in", "url": page.url, "persona": persona_id}
    finally:
        await ctx.close()
        await browser.close()
        await pw.stop()


async def action_observe(state_dir: Path, timeout_ms: int) -> dict[str, Any]:
    """Snapshot current page: URL, title, interactive elements, visible text."""
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        title = await page.title()
        elements = await page.evaluate(
            """(limit) => {
                const all = Array.from(document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"]'
                ));
                return all.slice(0, limit).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || null,
                    text: ((el.innerText || el.value || el.placeholder || '').trim()).slice(0, 100),
                    id: el.id || null,
                    className: el.className || null,
                    href: el.getAttribute('href') || null,
                    name: el.getAttribute('name') || null,
                }));
            }""",
            INTERACTIVE_ELEMENT_LIMIT,
        )
        visible = await page.evaluate(
            "(limit) => (document.body ? document.body.innerText : '').slice(0, limit)",
            VISIBLE_TEXT_LIMIT,
        )
        return {
            "url": page.url,
            "title": title,
            "interactive_elements": elements,
            "visible_text": visible,
        }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_navigate(target: str, state_dir: Path, timeout_ms: int) -> dict[str, Any]:
    _, base_url_path, _ = _paths(state_dir)
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        before_url = page.url
        if target.startswith("http"):
            dest = target
        else:
            base = base_url_path.read_text().strip() if base_url_path.exists() else ""
            dest = base.rstrip("/") + (target if target.startswith("/") else f"/{target}")
        await page.goto(dest)
        # networkidle is best-effort — pages with long-poll connections
        # never settle. Timeout here is fine; the navigation already
        # succeeded. (#smells-1.1)
        with suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return {"status": "navigated", "from": before_url, "to": page.url}
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_click(selector: str, state_dir: Path, timeout_ms: int) -> dict[str, Any]:
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        before_url = page.url
        try:
            locator = page.locator(selector)
            await locator.first.click(timeout=timeout_ms)
            # networkidle best-effort — see action_navigate above (#smells-1.1)
            with suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return {
                "status": "clicked",
                "selector": selector,
                "from": before_url,
                "to": page.url,
                "state_changed": before_url != page.url,
            }
        except Exception as e:
            return {
                "error": str(e),
                "error_type": type(e).__name__,
                "selector": selector,
            }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_type(selector: str, text: str, state_dir: Path, timeout_ms: int) -> dict[str, Any]:
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        try:
            locator = page.locator(selector)
            await locator.first.fill(text, timeout=timeout_ms)
            return {
                "status": "typed",
                "selector": selector,
                "text_length": len(text),
                "url": page.url,
            }
        except Exception as e:
            return {
                "error": str(e),
                "error_type": type(e).__name__,
                "selector": selector,
            }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_select(
    selector: str, value: str, state_dir: Path, timeout_ms: int
) -> dict[str, Any]:
    """Pick an option in a ``<select>`` element.

    ``value`` is tried first as an option ``value`` attribute, then as a
    visible label. This lets callers drive selects whether they know the
    exact ``<option value="...">`` or only the user-visible text.
    """
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        try:
            locator = page.locator(selector)
            # Playwright's select_option accepts a string (interpreted as
            # option value) or a dict with {"label": ...}. Try value first;
            # on failure, retry with label semantics.
            try:
                chosen = await locator.first.select_option(value=value, timeout=timeout_ms)
                matched_by = "value"
            except Exception:
                chosen = await locator.first.select_option(label=value, timeout=timeout_ms)
                matched_by = "label"
            return {
                "status": "selected",
                "selector": selector,
                "value": value,
                "matched_by": matched_by,
                "chosen_values": chosen,
                "url": page.url,
            }
        except Exception as e:
            return {
                "error": str(e),
                "error_type": type(e).__name__,
                "selector": selector,
                "value": value,
            }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_form_submit(
    url: str,
    fields_json: str,
    submit_selector: str,
    state_dir: Path,
    timeout_ms: int,
) -> dict[str, Any]:
    """Navigate to a form, fill multiple fields, submit, and observe the result — all in one subprocess.

    Added in cycle 229 after EX-039 investigation revealed that the
    per-call ``action_type`` + ``action_click`` pattern does not work for
    form submission: each subprocess starts a fresh browser, reloads
    from ``storage_state`` (cookies only, no in-page form state), so
    values typed via a prior ``action_type`` call have already
    evaporated by the time a subsequent ``action_click`` fires. Empty
    forms get blocked by HTML5 ``required`` validation before any
    HTMX request is emitted, producing the "silent submit" symptom the
    subagent observed in cycles 201/217/222/223.

    This combined action accepts the whole form state (URL + dict of
    field selectors → values + submit-button selector) and runs all
    steps in a single browser lifetime, so form state persists
    through the submit event.

    Args:
        url: The form page URL (absolute or path — path is resolved
            against ``base_url``).
        fields_json: JSON-encoded dict mapping CSS selector → value.
            For ``<select>`` elements use an option value or visible
            label. For ``<input>``/``<textarea>`` use the raw text.
        submit_selector: CSS selector for the submit button.
        state_dir: Standard state-dir path.
        timeout_ms: Per-action timeout.

    Returns:
        Dict with ``status``, ``from_url``, ``to_url``, ``state_changed``,
        and ``visible_error_text`` — the innerText of any
        ``[data-dazzle-error]`` element on the post-submit page (empty
        string if none, which is the happy path).
    """
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError as exc:
        return {
            "error": f"invalid fields JSON: {exc}",
            "error_type": "ValueError",
        }
    if not isinstance(fields, dict):
        return {
            "error": "fields must be a JSON object of selector → value",
            "error_type": "ValueError",
        }

    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        # Resolve URL — accept absolute or path-relative.
        base_url_path = state_dir / "base_url.txt"
        if url.startswith("http"):
            target = url
        elif base_url_path.exists():
            base = base_url_path.read_text().strip()
            target = base.rstrip("/") + url if url.startswith("/") else base + "/" + url
        else:
            return {
                "error": "cannot resolve relative URL without base_url.txt",
                "error_type": "RuntimeError",
            }

        try:
            await page.goto(target, wait_until="networkidle", timeout=timeout_ms)
        except Exception as exc:
            return {
                "error": f"navigation failed: {exc}",
                "error_type": type(exc).__name__,
                "target": target,
            }

        before_url = page.url

        # Fill every field in one session. For <select>, use select_option;
        # otherwise fall back to fill().
        for selector, value in fields.items():
            try:
                locator = page.locator(selector).first
                tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    try:
                        await locator.select_option(value=str(value), timeout=timeout_ms)
                    except Exception:
                        await locator.select_option(label=str(value), timeout=timeout_ms)
                else:
                    await locator.fill(str(value), timeout=timeout_ms)
            except Exception as exc:
                return {
                    "error": f"failed to fill {selector!r}: {exc}",
                    "error_type": type(exc).__name__,
                    "selector": selector,
                }

        # Click submit.
        try:
            await page.locator(submit_selector).first.click(timeout=timeout_ms)
        except Exception as exc:
            return {
                "error": f"submit click failed: {exc}",
                "error_type": type(exc).__name__,
                "submit_selector": submit_selector,
            }

        # Wait for the submit to settle. Two phases:
        # 1. Network idle — for non-HTMX full-page submits, redirects, etc.
        # 2. Short explicit wait for HTMX ajax to complete AND the swap
        #    to run. HTMX emits ``htmx:afterSwap`` once the response is
        #    rendered into the target; we wait for either that or a URL
        #    change, whichever comes first. ``networkidle`` alone isn't
        #    reliable for HTMX because the ajax round-trip may complete
        #    before networkidle kicks in AND the swap runs on the JS
        #    thread after the response settles.
        # All four cleanups below are best-effort post-submit observation —
        # failures here just mean we don't have richer diagnostics to
        # return, not that the action itself failed (#smells-1.1).
        with suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        # Give HTMX a beat to run its swap handler. 250ms is generous
        # for any local-network response.
        with suppress(Exception):
            await page.wait_for_timeout(250)

        # Harvest any post-submit error banner so the caller doesn't need
        # a second observe call to see it (a second call would trigger
        # a fresh page.goto which would discard the swapped-in error
        # content — see cycle 229 investigation).
        visible_error_text = ""
        with suppress(Exception):
            error_el = page.locator("[data-dazzle-error]").first
            if await error_el.count() > 0:
                visible_error_text = (await error_el.inner_text()).strip()

        # Also snapshot the inner HTML of #form-errors if present — this
        # is the target container for HTMX 422 swaps and gives us a
        # second diagnostic window even if the [data-dazzle-error]
        # selector didn't match (e.g. if the error fragment wrapped
        # differently than expected).
        form_errors_inner = ""
        with suppress(Exception):
            target_el = page.locator("#form-errors").first
            if await target_el.count() > 0:
                form_errors_inner = (await target_el.inner_text()).strip()

        after_url = page.url
        return {
            "status": "form_submitted",
            "from_url": before_url,
            "to_url": after_url,
            "state_changed": before_url != after_url,
            "visible_error_text": visible_error_text,
            "form_errors_inner": form_errors_inner,
            "fields_filled": list(fields.keys()),
        }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


async def action_wait(selector: str, state_dir: Path, timeout_ms: int) -> dict[str, Any]:
    """Wait for an element to appear — useful for async content loads."""
    pw, browser, ctx, page = await _launch(state_dir, timeout_ms)
    try:
        try:
            locator = page.locator(selector)
            await locator.first.wait_for(timeout=timeout_ms)
            return {"status": "found", "selector": selector, "url": page.url}
        except Exception as e:
            return {
                "error": str(e),
                "error_type": type(e).__name__,
                "selector": selector,
            }
    finally:
        await _teardown(pw, browser, ctx, page, state_dir)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m dazzle.agent.playwright_helper",
        description="Stateless Playwright driver for subagent-driven explore cycles.",
    )
    p.add_argument(
        "--state-dir",
        required=True,
        type=Path,
        help="Directory holding state.json, base_url.txt, last_url.txt.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_MS,
        help=f"Playwright action timeout in milliseconds (default: {DEFAULT_TIMEOUT_MS}).",
    )
    sub = p.add_subparsers(dest="action", required=True)

    login = sub.add_parser("login", help="Log in via QA magic-link endpoint.")
    login.add_argument("api_url")
    login.add_argument("persona_id")

    sub.add_parser("observe", help="Snapshot current page state.")

    navigate = sub.add_parser("navigate", help="Navigate to a URL or path.")
    navigate.add_argument("target")

    click = sub.add_parser("click", help="Click an element by CSS selector.")
    click.add_argument("selector")

    type_cmd = sub.add_parser("type", help="Type text into an input by selector.")
    type_cmd.add_argument("selector")
    type_cmd.add_argument("text")

    select_cmd = sub.add_parser("select", help="Pick a <select> option by value or visible label.")
    select_cmd.add_argument("selector")
    select_cmd.add_argument("value")

    wait_cmd = sub.add_parser("wait", help="Wait for an element to appear.")
    wait_cmd.add_argument("selector")

    # form_submit — navigate, fill many fields, click submit, observe errors,
    # all in ONE subprocess. Added in cycle 229 after EX-039 investigation
    # revealed that action_type values evaporate between subprocess calls
    # (storage_state only persists cookies, not in-page form state). For
    # form-submit flows, subagents should use this command instead of
    # chaining type/click across multiple invocations.
    form_submit = sub.add_parser(
        "form_submit",
        help="Navigate, fill fields, submit, observe — all in one subprocess.",
    )
    form_submit.add_argument("url", help="Form page URL or path.")
    form_submit.add_argument(
        "fields",
        help="JSON object of {selector: value} pairs.",
    )
    form_submit.add_argument(
        "submit_selector",
        help="CSS selector for the submit button.",
    )

    return p


async def _run(args: argparse.Namespace) -> int:
    state_dir: Path = args.state_dir
    timeout_ms: int = args.timeout

    try:
        if args.action == "login":
            result: dict[str, Any] = await action_login(
                args.api_url, args.persona_id, state_dir, timeout_ms
            )
        elif args.action == "observe":
            result = await action_observe(state_dir, timeout_ms)
        elif args.action == "navigate":
            result = await action_navigate(args.target, state_dir, timeout_ms)
        elif args.action == "click":
            result = await action_click(args.selector, state_dir, timeout_ms)
        elif args.action == "type":
            result = await action_type(args.selector, args.text, state_dir, timeout_ms)
        elif args.action == "select":
            result = await action_select(args.selector, args.value, state_dir, timeout_ms)
        elif args.action == "wait":
            result = await action_wait(args.selector, state_dir, timeout_ms)
        elif args.action == "form_submit":
            result = await action_form_submit(
                args.url,
                args.fields,
                args.submit_selector,
                state_dir,
                timeout_ms,
            )
        else:
            result = {"error": f"unknown action: {args.action}"}
    except Exception as e:
        result = {"error": str(e), "error_type": type(e).__name__}

    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 1


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
