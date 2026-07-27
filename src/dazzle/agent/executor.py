"""
Executor backends for the Dazzle Agent.

Two implementations:
- PlaywrightExecutor: Browser interactions via Playwright (for testing)
- HttpExecutor: HTTP requests with HTMX support (for discovery)

Both execute AgentActions and return ActionResults.
"""

import asyncio
import hashlib
import logging
from typing import Any, Protocol, runtime_checkable

from .models import ActionResult, ActionType, AgentAction

logger = logging.getLogger(__name__)


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class Executor(Protocol):
    """Executes actions on a page."""

    async def execute(self, action: AgentAction) -> ActionResult:
        """Execute an action and return the result."""
        ...


# =============================================================================
# Playwright Executor
# =============================================================================


def _dom_hash(html: str) -> str:
    """16-char SHA256 prefix of page content for cheap state-change detection."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def _search_box_results_selector(target: str) -> str | None:
    """Map a search_box input selector to its results panel id.

    Inputs are ``#dz-search-results-<name>-input``; results live in
    ``#dz-search-results-<name>``. Returns None for non-search targets.
    """
    sel = (target or "").strip()
    if sel.startswith("#"):
        sel = sel[1:]
    # CSS id only — reject compound selectors
    if not sel or " " in sel or ">" in sel or "[" in sel:
        return None
    if sel.startswith("dz-search-results-") and sel.endswith("-input"):
        return f"#{sel[: -len('-input')]}"
    return None


# Playwright's TimeoutError is *not* a subclass of builtin TimeoutError
# (playwright._impl._errors.TimeoutError → Error → Exception). Catching only
# builtin TimeoutError lets settle/networkidle timeouts abort TYPE as hard
# errors and skip the state_changed snapshot — false "search broken" panels
# (contact_manager agent_acceptance, cycles 1332–1336).
_SETTLE_TIMEOUT_TYPES: tuple[type[BaseException], ...] = (TimeoutError, OSError, RuntimeError)
try:
    from playwright.async_api import TimeoutError as _PlaywrightTimeoutError

    _SETTLE_TIMEOUT_TYPES = (_PlaywrightTimeoutError, TimeoutError, OSError, RuntimeError)
except ImportError:  # pragma: no cover — playwright optional for HttpExecutor-only hosts
    pass


async def _search_box_results_summary(page: Any, results_sel: str) -> str:
    """Human-readable hit list for TYPE action messages (agent history).

    The A–Z directory list stays full by design; panels that only watch that
    list report search as broken. Surfacing the results-panel titles in the
    action line makes working FTS unmissable (cycle 1336).
    """
    try:
        summary = await page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return '';
                const count = el.querySelector('.dz-search-box-result-count');
                if (count && count.textContent) {
                    const titles = Array.from(
                        el.querySelectorAll('.dz-search-box-result-title')
                    )
                        .map((n) => (n.textContent || '').trim())
                        .filter(Boolean)
                        .slice(0, 5);
                    const tail = titles.length ? ': ' + titles.join(', ') : '';
                    return (count.textContent || '').trim() + tail;
                }
                const empty = el.querySelector('.dz-search-box-empty--no-results');
                if (empty && empty.textContent) {
                    return (empty.textContent || '').trim();
                }
                return '';
            }""",
            results_sel,
        )
    except Exception as exc:
        # Best-effort history enrichment only — never abort TYPE for a summary
        # miss. warning (not debug) so swallow ratchet stays green (cycle 1337).
        logger.warning(
            "search_box results summary failed for %s: %s",
            results_sel,
            exc,
            exc_info=True,
        )
        return ""
    if not isinstance(summary, str):
        return ""
    return summary.strip()[:200]


class PlaywrightExecutor:
    """
    Execute actions via Playwright page interactions.

    Use for testing where you need real browser behavior (JS execution,
    CSS rendering, network interception).
    """

    # Cap samples kept per action-window (team_overview HTMX thrash can emit
    # 10k+ identical ERR_INSUFFICIENT_RESOURCES lines). Total count is tracked
    # separately so history can still report the real storm size.
    _CONSOLE_SAMPLE_CAP = 32

    def __init__(self, page: Any) -> None:
        self._page = page
        # Cycle 197 — console error buffer for action-window attribution
        self._console_errors_buffer: list[str] = []
        self._console_error_total: int = 0
        page.on("console", self._on_console)

    def _on_console(self, msg: Any) -> None:
        """Buffer console error messages for action-window diff-slicing.

        Diagnostic capture — a malformed console message must never crash
        the executor (#smells-1.1).
        """
        try:
            if msg.type == "error":
                self._console_error_total += 1
                buf = self._console_errors_buffer
                if len(buf) < self._CONSOLE_SAMPLE_CAP:
                    buf.append(msg.text)
                else:
                    # Ring: keep newest samples so action windows still have a
                    # representative first error after early thrash fills the cap.
                    buf.pop(0)
                    buf.append(msg.text)
        except Exception:
            logger.debug("Malformed console message; skipping", exc_info=True)

    def _console_window(self, count_before: int) -> tuple[list[str], int]:
        """Return (capped samples, total count) for the action window."""
        n = max(0, self._console_error_total - count_before)
        if n <= 0:
            return [], 0
        # Samples are a rolling window of recent errors — take min(n, cap).
        samples = list(self._console_errors_buffer[-min(n, self._CONSOLE_SAMPLE_CAP) :])
        return samples, n

    def _resolve_locator(self, selector: str) -> Any:
        """Resolve a selector to a Playwright locator.

        Supports ``role=<role>[name="<name>"]`` syntax (matching Playwright's
        accessibility locator API) as well as standard CSS/Playwright selectors.
        """
        if selector.startswith("role="):
            import re

            m = re.match(r'role=(\w+)(?:\[name="(.+)"\])?$', selector)
            if m:
                role = m.group(1)
                name = m.group(2)
                if name:
                    return self._page.get_by_role(role, name=name)
                return self._page.get_by_role(role)
        return self._page.locator(selector)

    async def execute(self, action: AgentAction) -> ActionResult:
        # Capture "before" state for actions that interact with the page.
        # TOOL / DONE bypass — they don't touch the page.
        capture_state = action.type not in (ActionType.TOOL, ActionType.DONE)
        from_url: str | None = None
        from_hash: str | None = None
        search_box_settled = False
        if capture_state:
            from_url = self._page.url
            from_hash = _dom_hash(await self._page.content())
        console_count_before = self._console_error_total

        try:
            if action.type == ActionType.CLICK:
                locator = self._resolve_locator(action.target or "")
                await locator.click(timeout=5000)
                # networkidle wait timeout is benign here — long-poll/SSE keeps the
                # network busy on some apps; click already succeeded (#smells-1.1).
                try:
                    await self._page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    logger.debug("networkidle timeout after click %s", action.target, exc_info=True)
                base = ActionResult(message=f"Clicked {action.target}")

            elif action.type == ActionType.TYPE:
                locator = self._resolve_locator(action.target or "")
                await locator.fill(action.value or "", timeout=5000)
                # HTMX search_box / filter inputs use delay:250ms (or longer).
                # fill() dispatches input but without a settle wait the agent
                # snapshots "NO state change" before results swap — false
                # search-broken friction in qa trial (contact_manager panel).
                # Prefer waiting on the results panel when the target is a
                # search_box input: networkidle often never settles under
                # SSE/lazy regions, so a fixed 400ms race still mis-scores
                # working FTS as broken (cycle 1332 panel).
                results_summary = ""
                try:
                    target_sel = action.target or ""
                    results_sel = _search_box_results_selector(target_sel)
                    if results_sel:
                        await self._page.wait_for_timeout(300)  # HTMX debounce
                        try:
                            await self._page.wait_for_function(
                                """(sel) => {
                                    const el = document.querySelector(sel);
                                    if (!el) return false;
                                    return !!el.querySelector(
                                      '.dz-search-box-result-count,'
                                      + ' .dz-search-box-result-list,'
                                      + ' .dz-search-box-empty--no-results'
                                    );
                                }""",
                                arg=results_sel,
                                timeout=5000,
                            )
                            search_box_settled = True
                            results_summary = await _search_box_results_summary(
                                self._page, results_sel
                            )
                        except _SETTLE_TIMEOUT_TYPES:
                            logger.debug(
                                "search_box results settle timeout for %s",
                                target_sel,
                                exc_info=True,
                            )
                    else:
                        await self._page.wait_for_timeout(400)
                    await self._page.wait_for_load_state("networkidle", timeout=5000)
                except _SETTLE_TIMEOUT_TYPES:
                    # Playwright TimeoutError is not builtin TimeoutError —
                    # must catch both so settle success still reaches the
                    # state_changed snapshot (cycle 1336).
                    logger.debug(
                        "networkidle timeout after type into %s",
                        action.target,
                        exc_info=True,
                    )
                msg = f"Typed '{action.value}' into {action.target}"
                if search_box_settled and results_summary:
                    msg += f" — search results panel: {results_summary}"
                elif search_box_settled:
                    msg += " — search results panel updated (A–Z list stays full by design)"
                base = ActionResult(message=msg)

            elif action.type == ActionType.SELECT:
                locator = self._resolve_locator(action.target or "")
                await locator.select_option(action.value, timeout=5000)
                base = ActionResult(message=f"Selected '{action.value}' in {action.target}")

            elif action.type == ActionType.NAVIGATE:
                target = action.target or "/"
                if not target.startswith("http"):
                    base_parts = self._page.url.split("/")[0:3]
                    target = "/".join(base_parts) + target
                # domcontentloaded (not default "load"/networkidle): workspace
                # pages keep HTMX region fetches + optional SSE open, so a
                # strict load wait can hang past Playwright's 30s default and
                # abort qa trials (design_studio reviewer cold-start).
                await self._page.goto(target, wait_until="domcontentloaded", timeout=60_000)
                try:
                    await self._page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    logger.debug("networkidle timeout after navigate to %s", target, exc_info=True)
                base = ActionResult(message=f"Navigated to {target}")

            elif action.type == ActionType.WAIT:
                locator = self._resolve_locator(action.target or "")
                await locator.wait_for(timeout=10000)
                base = ActionResult(message=f"Found {action.target}")

            elif action.type == ActionType.ASSERT:
                try:
                    locator = self._resolve_locator(action.target or "")
                    await locator.wait_for(timeout=3000)
                    base = ActionResult(message=f"Assertion passed: {action.target} is visible")
                except Exception:
                    if await self._page.locator(f"text={action.target}").count() > 0:
                        base = ActionResult(
                            message=f"Assertion passed: text '{action.target}' found"
                        )
                    else:
                        base = ActionResult(
                            message="",
                            error=f"Assertion failed: {action.target} not found",
                        )

            elif action.type == ActionType.SCROLL:
                await self._page.evaluate("window.scrollBy(0, 300)")
                base = ActionResult(message="Scrolled down")

            elif action.type == ActionType.DONE:
                base = ActionResult(message="Agent completed mission")

            elif action.type == ActionType.TOOL:
                # Tool actions are handled by the agent core, not the executor
                base = ActionResult(message=f"Tool invocation: {action.target}")

            else:
                base = ActionResult(message="", error=f"Unknown action type: {action.type}")

        except Exception as e:
            # Error path: capture available state but leave state_changed=None
            err_samples, err_n = self._console_window(console_count_before)
            return ActionResult(
                message="",
                error=str(e),
                from_url=from_url,
                to_url=self._page.url if capture_state else None,
                state_changed=None,
                console_errors_during_action=err_samples,
                console_error_count=err_n,
            )

        # Happy path: compute after state and populate the new fields
        if capture_state:
            to_url = self._page.url
            to_hash = _dom_hash(await self._page.content())
            base.from_url = from_url
            base.to_url = to_url
            if action.type == ActionType.SCROLL:
                base.state_changed = True  # optimistic
            elif action.type == ActionType.ASSERT:
                base.state_changed = False  # optimistic
            elif search_box_settled:
                # FTS results panel updated — never report NO state change when
                # the settle predicate already saw hits/empty (cycle 1336).
                base.state_changed = True
            else:
                base.state_changed = (from_url != to_url) or (from_hash != to_hash)
        # else: TOOL / DONE leave state fields at None defaults

        samples, n_console = self._console_window(console_count_before)
        base.console_errors_during_action = samples
        base.console_error_count = n_console
        return base


# =============================================================================
# HTTP Executor
# =============================================================================


class HttpExecutor:
    """
    Execute actions via HTTP requests.

    Use for discovery where you don't need a full browser. Follows
    HTMX patterns (hx-target, hx-swap) and maintains cookie state.
    """

    def __init__(self, client: Any, base_url: str, observer: Any = None):
        """
        Args:
            client: httpx.AsyncClient with cookies configured
            base_url: Base URL of the application
            observer: Optional HttpObserver to update after navigation
        """
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._observer = observer

    async def execute(self, action: AgentAction) -> ActionResult:
        try:
            if action.type == ActionType.NAVIGATE:
                return await self._navigate(action.target or "/")

            elif action.type == ActionType.CLICK:
                return await self._click(action)

            elif action.type == ActionType.TYPE:
                # HTTP executor stores form state; actual submission on CLICK/submit
                return ActionResult(
                    message=f"Set field {action.target} = '{action.value}'",
                    data={"field": action.target, "value": action.value},
                )

            elif action.type == ActionType.SELECT:
                return ActionResult(
                    message=f"Selected '{action.value}' for {action.target}",
                    data={"field": action.target, "value": action.value},
                )

            elif action.type == ActionType.ASSERT:
                # For HTTP executor, assert checks are based on last response content
                return ActionResult(
                    message=f"Assertion noted: {action.target}",
                    data={"assertion": action.target},
                )

            elif action.type == ActionType.WAIT:
                await asyncio.sleep(0.5)
                return ActionResult(message="Waited")

            elif action.type == ActionType.SCROLL:
                return ActionResult(message="Scroll (no-op for HTTP)")

            elif action.type == ActionType.DONE:
                return ActionResult(message="Agent completed mission")

            elif action.type == ActionType.TOOL:
                return ActionResult(message=f"Tool invocation: {action.target}")

            else:
                return ActionResult(message="", error=f"Unknown action type: {action.type}")

        except Exception as e:
            return ActionResult(message="", error=str(e))

    async def _navigate(self, url: str) -> ActionResult:
        """Navigate via HTTP GET."""
        if not url.startswith("http"):
            url = self._base_url + url
        response = await self._client.get(url, follow_redirects=True)
        if self._observer:
            self._observer._current_url = str(response.url)
            self._observer._last_html = response.text
        if response.status_code >= 400:
            return ActionResult(
                message=f"GET {url}",
                error=f"HTTP {response.status_code}",
            )
        return ActionResult(message=f"Navigated to {response.url}")

    async def _click(self, action: AgentAction) -> ActionResult:
        """Handle click by following href or hx-get/hx-post.

        The LLM typically sends a CSS selector as the target (e.g.
        ``a[href="/login"]``).  We extract the URL from the selector so
        the HTTP executor can follow the link instead of silently
        no-op-ing.
        """
        import re

        target = action.target or ""

        # If the target looks like a URL or path, navigate
        if target.startswith("/") or target.startswith("http"):
            return await self._navigate(target)

        # If value contains a URL/path, navigate to it
        if action.value and (action.value.startswith("/") or action.value.startswith("http")):
            return await self._navigate(action.value)

        # Extract href from CSS selector (e.g. a[href="/login"])
        href_match = re.search(r'href=["\']?([^"\')\]\s]+)', target)
        if href_match:
            return await self._navigate(href_match.group(1))

        # Extract hx-get from CSS selector
        hx_get_match = re.search(r'hx-get=["\']?([^"\')\]\s]+)', target)
        if hx_get_match:
            return await self._navigate(hx_get_match.group(1))

        # For hx-post targets, submit a POST
        if action.value and action.value.startswith("hx-post:"):
            post_url = action.value.replace("hx-post:", "")
            if not post_url.startswith("http"):
                post_url = self._base_url + post_url
            response = await self._client.post(post_url, follow_redirects=True)
            if self._observer:
                self._observer._current_url = str(response.url)
                self._observer._last_html = response.text
            return ActionResult(message=f"POST {post_url} -> {response.status_code}")

        # Extract hx-post from CSS selector
        hx_post_match = re.search(r'hx-post=["\']?([^"\')\]\s]+)', target)
        if hx_post_match:
            post_url = hx_post_match.group(1)
            if not post_url.startswith("http"):
                post_url = self._base_url + post_url
            response = await self._client.post(post_url, follow_redirects=True)
            if self._observer:
                self._observer._current_url = str(response.url)
                self._observer._last_html = response.text
            return ActionResult(message=f"POST {post_url} -> {response.status_code}")

        return ActionResult(
            message=f"Click on {target}",
            data={"note": "HTTP executor: click may need URL context"},
        )
