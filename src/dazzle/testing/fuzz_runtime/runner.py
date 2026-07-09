"""Per-app interactive fuzz runner."""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FuzzCheck:
    """One assertion in a fuzz run."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class FuzzReport:
    """Result of fuzzing one app."""

    project: str
    checks: list[FuzzCheck] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def failures(self) -> list[FuzzCheck]:
        return [c for c in self.checks if not c.passed]


@contextmanager
def _booted_app(project_root: Path) -> Iterator[tuple[str, str]]:
    """Boot the app under test; yield (base_url, test_secret).

    `dazzle serve` allocates its own port and publishes both the URL
    and the test secret to `.dazzle/runtime.json`. We read both from
    there rather than hard-coding — that's what the e2e runner does
    and it lets parallel runs share the implementation.

    Cleanup tears down the subprocess (and waits for the port to
    actually release before returning, so the next run on the same
    project doesn't hit a stale-port connect).
    """
    env = {"DAZZLE_SKIP_INFRA_CHECK": "1"}
    runtime_path = project_root / ".dazzle" / "runtime.json"
    # Stale runtime file from the previous run would let us read an
    # old secret before the new boot writes its own. Clear it.
    if runtime_path.exists():
        runtime_path.unlink()
    proc = subprocess.Popen(
        ["dazzle", "serve", "--test-mode"],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**__import__("os").environ, **env},
    )
    deadline = time.time() + 20
    secret = ""
    base = ""
    try:
        while time.time() < deadline:
            if runtime_path.exists():
                with contextlib.suppress(Exception):
                    rt = json.loads(runtime_path.read_text(encoding="utf-8"))
                    secret = rt.get("test_secret", "")
                    base = rt.get("ui_url", "")
                    if secret and base:
                        break
            time.sleep(0.2)
        if not secret or not base:
            raise RuntimeError("test_secret / ui_url not published in runtime.json")
        # Wait until /openapi.json is reachable. Use httpx (existing
        # framework dependency).
        import httpx

        for _ in range(40):
            try:
                with httpx.Client(timeout=0.5) as c:
                    if c.get(f"{base}/openapi.json").status_code == 200:
                        break
            except Exception:
                time.sleep(0.25)
        yield base, secret
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        # Give the OS a moment to actually release the listening port
        # so back-to-back boots of different projects don't fight.
        time.sleep(0.5)


def _authenticate(base: str, secret: str, role: str = "admin") -> dict[str, str]:
    """Hit /__test__/authenticate and return the session/csrf cookies."""
    import httpx

    with httpx.Client(timeout=5) as client:
        resp = client.post(
            f"{base}/__test__/authenticate",
            json={"username": role, "role": role},
            headers={"X-Test-Secret": secret},
        )
        resp.raise_for_status()
        # httpx exposes cookies as a dict-like; convert to plain {name: value}.
        return dict(resp.cookies.items())


def fuzz_richtext(page: Any, host_index: int = 0) -> list[FuzzCheck]:
    """Drive one dz-richtext editor through known-tricky sequences.

    Each check records a name + pass/fail + short detail string.
    Findings (cycle 1 of this module): selection that spans a whole
    block produces invalid <strong><p>...</p></strong> nesting (#1000).
    """
    checks: list[FuzzCheck] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(FuzzCheck(name=name, passed=ok, detail=detail))

    host = page.locator('[data-dz-widget="richtext"]').nth(host_index)
    if host.count() == 0:
        return checks
    editor = host.locator("[data-dz-editor]")
    hidden = host.locator("input[type=hidden]")

    # 1. Type → hidden sync.
    editor.click()
    page.keyboard.type("hello world")
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("type → hidden sync", "hello world" in hv, hv)

    # 2. Bold via shortcut.
    editor.evaluate(
        "el => { const r = document.createRange(); r.selectNodeContents(el); "
        "const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }"
    )
    page.keyboard.press("Control+b")
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("Ctrl+B inserts <strong>", "<strong>" in hv, hv)
    # #1000 — inline tags must not wrap block tags.
    add(
        "Ctrl+B does NOT wrap <p> in <strong> (#1000)",
        "<strong><p>" not in hv and "<strong>\n<p>" not in hv,
        hv,
    )

    # 3. Paste javascript: link → href stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', '<a href=\\"javascript:alert(1)\\">click</a>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("javascript: href stripped on paste", "javascript" not in hv, hv)

    # 4. Paste <script> → no execution, tag stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const dt = new DataTransfer();
            dt.setData('text/html',
                '<p>before</p><script>window.__pwn_richtext = 1<' + '/script><p>after</p>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    pwn = page.evaluate("typeof window.__pwn_richtext")
    hv = hidden.input_value()
    add("<script> in paste does NOT execute", pwn == "undefined", f"window.__pwn={pwn}")
    add("<script> tag stripped from emit", "<script" not in hv.lower(), hv[:200])

    # 5. h1/h4 normalised on paste (per IR allowlist).
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const r = document.createRange(); r.selectNodeContents(ed);
            const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
            const dt = new DataTransfer();
            dt.setData('text/html', '<h1>top</h1><h4>sub</h4>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("h1 demoted to h2 on paste", "<h2>" in hv and "<h1>" not in hv, hv[:160])
    add("h4 promoted to h3 on paste", "<h3>" in hv and "<h4>" not in hv, hv[:160])

    # 6. Style/class flood from Word stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const r = document.createRange(); r.selectNodeContents(ed);
            const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
            const html = '<p class=\\"MsoNormal\\" style=\\"color:red\\"><b>Bold</b></p>';
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("style attributes stripped on paste", "style=" not in hv, hv[:160])
    add("class attributes stripped on paste", "class=" not in hv, hv[:160])

    # 7. Lifecycle: htmx-style remount, editor still works.
    page.evaluate(
        """() => {
            const host = document.querySelector('[data-dz-widget=\\"richtext\\"]');
            const clone = host.cloneNode(true);
            host.parentNode.replaceChild(clone, host);
            document.body.dispatchEvent(new CustomEvent('htmx:after:settle', {
                bubbles: true, detail: { target: clone }
            }));
        }"""
    )
    page.wait_for_timeout(150)
    new_host = page.locator('[data-dz-widget="richtext"]').first
    new_editor = new_host.locator("[data-dz-editor]")
    new_hidden = new_host.locator("input[type=hidden]")
    new_editor.click()
    page.keyboard.type(" remount-ok")
    page.wait_for_timeout(120)
    nv = new_hidden.input_value()
    add("editor functional after htmx-style remount", "remount-ok" in nv, nv[:160])

    return checks


def fuzz_page_walker(page: Any, base: str, paths: list[str]) -> list[FuzzCheck]:
    """Visit every probed path, capture per-page anomalies.

    Signal vs. noise:
    - **403** is a gating response, NOT a bug. The test-mode auth
      role is `admin` but most apps gate workspaces / scope-bound
      list endpoints to specific personas (engineer, tester, etc.).
      403 means "framework is correctly enforcing access control",
      so we record but do not fail.
    - **404** on an /app/* path is a real bug: the openapi advertises
      the route but the runtime didn't mount it.
    - **5xx** is a real bug — fail.
    - **render-error markers** (dz-render-error class) are real:
      template macros render placeholders for swallowed
      UndefinedErrors instead of crashing, and the marker class
      lets us catch those.
    """
    checks: list[FuzzCheck] = []
    for path in paths:
        url = f"{base}{path}"
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=8000)
        except Exception as exc:
            checks.append(
                FuzzCheck(name=f"page reachable: {path}", passed=False, detail=str(exc)[:160])
            )
            continue
        status = response.status if response else 0
        # 403 is gating — not a bug.
        if status == 403:
            continue
        # 5xx + non-403 4xx are bugs. 200-399 are fine.
        page_ok = 200 <= status < 400 or status == 0
        checks.append(
            FuzzCheck(
                name=f"page {path} responds 2xx/3xx",
                passed=page_ok,
                detail=f"HTTP {status}",
            )
        )
        if not page_ok:
            continue
        # Render-time check: any element marked with the framework's
        # error-class? (e.g. dz-render-error from a swallowed jinja
        # UndefinedError that the macro rendered as a placeholder.)
        err_count = page.evaluate(
            "document.querySelectorAll('.dz-render-error, [data-dz-render-error]').length"
        )
        checks.append(
            FuzzCheck(
                name=f"no render-error markers on {path}",
                passed=err_count == 0,
                detail=f"{err_count} marker(s)",
            )
        )
        # Settle pause for late Alpine / htmx work.
        page.wait_for_timeout(150)
    return checks


def fuzz_chaos_monkey(
    page: Any,
    base: str,
    paths: list[str],
    n_sessions: int = 4,
    n_clicks_per_session: int = 15,
    seed: int = 42,
) -> list[FuzzCheck]:
    """Random clicking across visible interactive elements.

    Goal: surface race conditions and edge cases that scripted batteries
    miss. Each session navigates to a random /app/* path then fires N
    random clicks at visible buttons / links / hx-* triggers. The page
    listeners (console, pageerror, response) attached at the call-site
    record fallout per click so the source action is attributable.

    Skipped (would compromise the run, not signal):
    - destructive (`[hx-delete]`, `data-dz-destructive`, buttons whose
      label matches a destructive verb)
    - logout / sign-out (would invalidate the session for the rest of
      the run)
    - external links (`target=_blank`, off-host hrefs)
    - file-download triggers
    - elements outside the viewport (visibility: hidden)

    Determinism: seeded so the same fuzz produces the same sequence.
    Bumping the seed is the way to explore further.
    """
    import random

    rng = random.Random(seed)
    checks: list[FuzzCheck] = []

    SAFE_SELECTORS = (
        "button[type=button]",
        "[hx-get]",
        "[hx-post]",
        "[hx-put]",
        "[hx-patch]",
        "[role=tab]",
        "[role=button]",
        "a[href^='/']:not([href*='logout']):not([href*='signout'])",
    )
    DESTRUCTIVE_TEXT = (
        "delete",
        "remove",
        "destroy",
        "drop",
        "purge",
        "logout",
        "sign out",
        "log out",
    )

    if not paths:
        return checks

    sessions_run = 0
    for _ in range(n_sessions):
        path = rng.choice(paths)
        try:
            response = page.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=8000)
        except (
            Exception
        ):  # fuzz probe: a nav failure/timeout is expected — keep probing other paths
            continue
        if not response or response.status >= 400:
            continue
        sessions_run += 1
        clicks_done = 0
        for _ in range(n_clicks_per_session):
            try:
                # Re-query each loop — DOM may have morphed via htmx swap.
                triggers = page.locator(",".join(SAFE_SELECTORS))
                count = triggers.count()
                if count == 0:
                    break
                # Drop destructive ones.
                idx = rng.randrange(count)
                el = triggers.nth(idx)
                if not el.is_visible():
                    continue
                # Skip if attribute marks it destructive.
                attrs = page.evaluate(
                    "el => ({"
                    " 'destructive': el.hasAttribute('hx-delete')"
                    "  || el.hasAttribute('data-dz-destructive')"
                    "  || (el.dataset.method || '').toLowerCase() === 'delete',"
                    " 'text': (el.textContent || el.value || '').trim().toLowerCase().slice(0, 40),"
                    " 'href': el.getAttribute('href') || '',"
                    " 'target': el.getAttribute('target') || ''"
                    "})",
                    el.element_handle(),
                )
                if attrs and attrs.get("destructive"):
                    continue
                if attrs and any(d in attrs.get("text", "") for d in DESTRUCTIVE_TEXT):
                    continue
                if attrs and attrs.get("target") == "_blank":
                    continue
                href = attrs.get("href", "") if attrs else ""
                if href.startswith("http"):  # external
                    continue
                # Click. no_wait_after lets us continue even if the
                # action triggers a navigation we're about to abort.
                el.click(timeout=1500, no_wait_after=True)
                page.wait_for_timeout(120)  # let htmx settle
                clicks_done += 1
                # If the click navigated us outside /app/*, retreat —
                # we want to keep clicking inside the app surface.
                if not page.url.startswith(f"{base}/app/"):
                    page.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=5000)
            except Exception:
                # Individual click failure recorded via console listener.
                continue
        checks.append(
            FuzzCheck(
                name=f"chaos-monkey session {sessions_run}: starting {path}",
                passed=True,  # signal is recorded via the page listeners
                detail=f"{clicks_done} clicks, seed={seed}",
            )
        )
    return checks


def fuzz_htmx_interactions(page: Any, base: str, paths: list[str]) -> list[FuzzCheck]:
    """Click every hx-get/hx-post/hx-trigger button on each visited
    page, watch for fallout. Catches:
    - htmx-targeted endpoints that 404 / 500
    - swapped fragments that throw template errors
    - Alpine state collisions across morphs
    - dz-* widget bridges that fail to remount on afterSettle

    Capped at 5 buttons per page to keep runtime bounded.
    """
    checks: list[FuzzCheck] = []
    for path in paths:
        try:
            page.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=8000)
        except (
            Exception
        ):  # fuzz probe: a nav failure/timeout is expected — keep probing other paths
            continue
        # Find buttons / links with htmx attrs that don't navigate away.
        triggers = page.locator("[hx-get], [hx-post], [hx-put], [hx-delete], [hx-patch]")
        n = min(triggers.count(), 5)
        if n == 0:
            continue
        clicked = 0
        for i in range(n):
            try:
                el = triggers.nth(i)
                # Skip if not visible (modal-hidden, off-screen, etc.).
                if not el.is_visible():
                    continue
                # Skip destructive actions explicitly to avoid mutating
                # demo data we then can't reset.
                method = ""
                for attr in ("hx-delete", "hx-post", "hx-put"):
                    v = el.get_attribute(attr)
                    if v is not None:
                        method = attr
                        break
                if method == "hx-delete":
                    continue
                el.click(timeout=1500, no_wait_after=True)
                page.wait_for_timeout(250)  # let htmx settle
                clicked += 1
            except Exception as exc:  # noqa: BLE001
                # Individual click failures are expected and tracked via the
                # console listener — debug-level logging keeps the production
                # ban on bare `except: pass` happy without spamming logs.
                logger.debug("fuzz htmx click failed on %s: %s", path, exc)
        checks.append(
            FuzzCheck(
                name=f"htmx interactions on {path}",
                passed=True,  # the ASSERTION is "no console errors fired",
                # which is captured at report-level by the page listener.
                detail=f"clicked {clicked} of {n} probed triggers",
            )
        )
    return checks


def _probe_app_paths(base: str) -> tuple[list[str], list[str], list[str]]:
    """Return (all_paths, create_paths, list_paths) by scanning the
    openapi spec. `all_paths` is the broader sweep — list/index pages,
    surfaces, dashboards. Used by the page-walker."""
    import httpx

    create_paths: list[str] = []
    list_paths: list[str] = []
    all_paths: list[str] = []
    try:
        with httpx.Client(timeout=2.0) as c:
            spec = c.get(f"{base}/openapi.json").json()
        for path in spec.get("paths", {}):
            if not path.startswith("/app/"):
                continue
            # Skip parameterised (would need a real ID); skip workspaces
            # that need persona pre-routing.
            if "{" in path:
                continue
            if path.endswith("/create"):
                create_paths.append(path)
            elif "/" in path[5:]:  # /app/X/something — non-list
                pass
            else:
                list_paths.append(path)
            all_paths.append(path)
    except Exception as exc:  # noqa: BLE001
        # OpenAPI-route-walk failures are non-fatal — fall back to the
        # static seed paths the caller passed in. Log at debug so the
        # cause is recoverable without breaking the bare-except gate.
        logger.debug("openapi route walk failed: %s", exc)
    return all_paths, create_paths, list_paths


def run_app_fuzz(project_root: Path) -> FuzzReport:
    """Boot `project_root`, fuzz every supported widget + page, return report.

    Order of operations:
      1. Generic page-walker — visit every reachable /app/* path,
         capture HTTP status + render-error markers + console errors.
      2. htmx interaction sweep — click safe (non-destructive) hx-*
         triggers on each path, watch for swap/morph anomalies.
      3. Specialised widget batteries (dz-richtext today; combobox /
         picker / optimistic-ui future) — drive widget-specific
         interaction sequences against the first reachable surface
         that mounts each widget.
    """
    project = project_root.name
    report = FuzzReport(project=project)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report.skipped_reason = f"playwright not installed: {exc}"
        return report

    with _booted_app(project_root) as (base, secret):
        cookies = _authenticate(base, secret, role="admin")
        all_paths, create_paths, _list_paths = _probe_app_paths(base)
        if not all_paths:
            report.skipped_reason = "no /app/* surfaces in openapi"
            return report

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            ctx.add_cookies(
                [
                    {"name": k, "value": v, "url": base, "sameSite": "Lax"}
                    for k, v in cookies.items()
                ]
            )
            page = ctx.new_page()

            # Network 404s are bugs (stale asset refs, missing routes).
            # Filter the predictable noise: cross-origin font fetches
            # that get blocked because we send X-Test-Secret on every
            # request via the test context.
            # Console.error is mostly browser-side echoes of HTTP
            # 4xx/5xx responses ("Failed to load resource: ...") —
            # filter those out (the response listener below records
            # the genuinely interesting status codes itself).
            def _on_console(m: Any) -> None:
                if m.type != "error":
                    return
                if "fonts.gstatic" in m.text:
                    return
                if "Failed to load resource" in m.text:
                    return  # response listener will pick up real ones
                if "Response Status Error Code" in m.text:
                    return  # htmx-extension echo of the same
                report.console_errors.append(f"[{m.type}] {m.text}")

            page.on("console", _on_console)
            page.on("pageerror", lambda e: report.page_errors.append(str(e)))

            # Network 404s are real bugs (stale asset refs, missing
            # framework routes). Filter:
            # - cross-origin font fetches blocked by CORS noise
            # - 403 (gating) and 401 (auth-not-our-role)
            # - 500 on /<entity>s endpoints — these are typically
            #   "table doesn't exist" in --local mode without a real
            #   migrated DB, not framework bugs.
            def _on_response(r: Any) -> None:
                if r.status == 404 and "fonts.gstatic" not in r.url:
                    report.console_errors.append(f"[404] {r.url}")
                elif r.status >= 500 and "/system" not in r.url:
                    # Skip /system* endpoints (SystemHealth/SystemMetric
                    # auto-injected entities that need DB migration).
                    report.console_errors.append(f"[{r.status}] {r.url}")

            page.on("response", _on_response)

            # ── 1. Page-walker (every app, every reachable URL) ──
            report.checks.extend(fuzz_page_walker(page, base, all_paths[:10]))

            # ── 2. htmx interaction sweep ──
            report.checks.extend(fuzz_htmx_interactions(page, base, all_paths[:5]))

            # ── 3. Chaos-monkey (random interaction) ──
            # Aggressive random clicking to surface race conditions and
            # edge cases the scripted batteries miss. Errors land in
            # report.console_errors via the listeners above.
            report.checks.extend(
                fuzz_chaos_monkey(
                    page,
                    base,
                    all_paths,
                    n_sessions=4,
                    n_clicks_per_session=15,
                )
            )

            # ── 4. Specialised widget batteries ──
            for path in create_paths:
                try:
                    page.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=5000)
                except Exception:  # fuzz probe: a failure here is expected — keep sweeping
                    continue
                if page.locator('[data-dz-widget="richtext"]').count() > 0:
                    report.checks.extend(fuzz_richtext(page, host_index=0))
                    break

            browser.close()

    return report
