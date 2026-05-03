"""Continuous click-through fuzzer for the Dazzle dev server.

Ported from AegisMark (https://github.com/manwithacat/aegismark) where it
was used to surface htmx morph race conditions, Alpine listener leaks,
and console errors that structured per-surface tests don't see. Brought
upstream because the same race conditions live in the framework, and
this is the cheapest tool we have for finding them — token-efficient
because every iteration is one click + one settle, no LLM in the loop.

Different intent from sweep / regression tests:
  - structured tests : per-surface contracts, gate regressions
  - fuzz             : open-ended exploration, surface unknown unknowns

Loop:
  1. Pick a random surface from a curated seed list, load it.
  2. Inventory clickable elements: <a href> with same-origin URLs,
     buttons with hx-get / hx-post, list-rows with hx-get.
  3. Click one at random. Wait for settle.
  4. With probability 0.15, click a SECOND element before the first
     swap settles — this is the race-condition probe (forces overlapping
     htmx requests; if the framework's morph handler isn't reentrant
     the page goes wrong).
  5. With probability 0.10, hit the back button to test htmx history.
  6. Log every console error, htmx swap-error, network 4xx/5xx, page
     error, dialog popup. Findings stream to dev_docs/site-fuzz-
     findings.jsonl one JSON object per line — tail it live, or grep
     for high-severity issues.
  7. Repeat until --duration elapses, --max-iterations hits, or Ctrl-C.

Usage (against any running `dazzle serve` instance):
    python3 scripts/site_fuzz.py --base http://localhost:3000
    python3 scripts/site_fuzz.py --duration 600       # 10 min
    python3 scripts/site_fuzz.py --max-iterations 50
    python3 scripts/site_fuzz.py --browser webkit     # Safari engine
    python3 scripts/site_fuzz.py --no-race            # disable race probes
    python3 scripts/site_fuzz.py --headed             # watch the browser
    python3 scripts/site_fuzz.py --persona admin      # auth as a specific
                                                      #   dev persona via QA
                                                      #   magic-link

Auth:
    Uses the Dazzle dev server's `/qa/magic-link` endpoint (only
    mounted with --enable-test-mode). Pass --persona <email> to
    pick which dev persona logs in; defaults to the first persona
    in the AppSpec.

Seeds:
    Default seeds cover `/app/`, `/app/workspaces/<name>`, and
    common entity list URLs derived at startup from the running
    server's `/openapi.json`. Override with --seed-url repeated.

Findings JSONL fields:
    {"ts": iso, "iter": N, "url": str, "category": str, "severity": str,
     "message": str, "context": {...}}

Categories: console-error, console-warning, page-error, request-failed,
            slow-request, dialog, htmx-swap-error, htmx-response-error,
            morph-stuck, navigation-timeout.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINDINGS_PATH = ROOT / "dev_docs" / "site-fuzz-findings.jsonl"
DEFAULT_BASE = "http://localhost:3000"
# Default persona email — matches the first dev persona Dazzle's QA
# mode mounts (`<persona_id>@example.test`). Override with --persona.
DEFAULT_PERSONA_EMAIL = "admin@example.test"

# Default seed surfaces. Generic enough to land hits on any Dazzle
# app: `/app` is the workspace root, `/app/workspaces/...` covers
# explicit workspace surfaces. The fuzzer crawls outward from these
# by following clickables it discovers — actual entity / list URLs
# get hit on the second hop without the operator needing to enumerate
# them. Override with --seed-url repeated.
SEED_SURFACES = [
    "/app",
    "/app",  # weighted x2 — most race-condition surface lives here
    "/app",  # weighted x3 — even stronger bias toward the workspace shell
    "/",  # marketing — included so the fuzzer occasionally exercises the
    # public site routes too, but at 1-in-4 odds rather than 1-in-2
]

# Categories whose presence interrupts the loop (with --abort-on-error).
HIGH_SEVERITY = {
    "page-error",
    "htmx-swap-error",
    "htmx-response-error",
    "navigation-timeout",
    "dialog",
}


@dataclass
class Finding:
    iter: int
    url: str
    category: str
    severity: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


class Fuzzer:
    def __init__(
        self,
        base: str,
        email: str,
        browser_name: str,
        headed: bool,
        race_probability: float,
        back_probability: float,
        findings_path: Path,
        seed: int | None,
        seed_surfaces: list[str] | None = None,
    ):
        self.base = base.rstrip("/")
        # Dazzle authentication uses the dev-mode QA magic-link, not
        # password — see `_login` for details. Persona email selects
        # which dev persona logs in.
        self.email = email
        self.browser_name = browser_name
        self.headed = headed
        self.race_probability = race_probability
        self.back_probability = back_probability
        self.findings_path = findings_path
        self.seed_surfaces = seed_surfaces or list(SEED_SURFACES)
        self.rng = random.Random(seed)
        self.findings: list[Finding] = []
        self.iter = 0
        self.t0 = time.monotonic()
        self.findings_path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, f: Finding) -> None:
        """Append finding to the JSONL stream + remember in-memory."""
        self.findings.append(f)
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "iter": f.iter,
            "url": f.url,
            "category": f.category,
            "severity": f.severity,
            "message": f.message,
            "context": f.context,
        }
        with self.findings_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        # Live preview to stdout for the operator
        marker = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(f.severity, "·")
        print(f"  {marker} [{f.category}] {f.message[:140]}")

    def _attach_listeners(self, page: Page) -> dict:
        """Wire console / pageerror / response / dialog hooks. Returns a
        mutable bag the caller can drain after each click iteration."""
        bag: dict[str, list[Any]] = {
            "console_errors": [],
            "console_warnings": [],
            "page_errors": [],
            "failed_requests": [],
            "slow_requests": [],
            "dialogs": [],
            "htmx_errors": [],
            "session_cookie_events": [],  # every response with dazzle_session Set-Cookie
        }

        def on_console(msg):
            t = msg.type
            text = ""
            try:
                text = msg.text or ""
            except Exception:
                pass
            loc = ""
            try:
                location = msg.location
                if location:
                    loc = f"{location.get('url', '')}:{location.get('lineNumber', '')}"
            except Exception:
                pass
            entry = {"text": text, "location": loc}
            if t == "error":
                bag["console_errors"].append(entry)
            elif t == "warning":
                bag["console_warnings"].append(entry)

        def on_pageerror(err):
            bag["page_errors"].append(str(err))

        # Session-cookie kill detector: log EVERY response that emits a
        # Set-Cookie touching dazzle_session. The Pattern B diagnostic
        # showed session=GONE on every 403, but no clear-cookie on the
        # failed response — so something earlier in the chain clears it.
        # This catches it in the act.
        def on_session_cookie_event(resp):
            try:
                sc = resp.headers.get("set-cookie", "")
                if "dazzle_session" not in sc:
                    return
                # Detect: clear (Max-Age=0 / expires=Thu, 01 Jan 1970)
                # vs rotate (new value)
                cleared = (
                    "Max-Age=0" in sc
                    or "max-age=0" in sc
                    or "01 Jan 1970" in sc
                    or "expires=Thu," in sc.lower()
                )
                bag.setdefault("session_cookie_events", []).append(
                    {
                        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "url": resp.url,
                        "status": resp.status,
                        "cleared": cleared,
                        "set_cookie_excerpt": sc[:300],
                    }
                )
            except Exception:
                pass

        def on_response(resp):
            on_session_cookie_event(resp)
            try:
                if resp.status >= 400:
                    # COOKIE PROBE per dazzle#969: snapshot the browser
                    # cookie jar at the moment of the 4xx so we can answer
                    # "was dazzle_session still alive when /app/* 403'd?"
                    # YES → server-side validate_session race
                    # NO  → cookie cleared somehow
                    try:
                        all_cookies = page.context.cookies()
                        sess = next(
                            (c for c in all_cookies if c.get("name") == "dazzle_session"), None
                        )
                        csrf = next(
                            (c for c in all_cookies if c.get("name") == "dazzle_csrf"), None
                        )
                        cookie_state = {
                            "session_present": bool(sess and sess.get("value")),
                            "session_len": len(sess.get("value") or "") if sess else 0,
                            "session_head": (sess.get("value") or "")[:12] if sess else "",
                            "csrf_present": bool(csrf and csrf.get("value")),
                            "csrf_len": len(csrf.get("value") or "") if csrf else 0,
                        }
                    except Exception:
                        cookie_state = {"error": "snapshot failed"}
                    # Capture the headers htmx + the framework key off so
                    # the operator can tell preload XHRs from boost-clicks
                    # from region lazy-loads. CRITICAL for diagnosing the
                    # "/app/workspaces/X 403'd despite the user having
                    # access" pattern surfaced by the 20-min fuzz.
                    h = resp.request.headers
                    rh = resp.headers
                    # Millisecond ISO timestamp for cross-correlation with
                    # `heroku logs --tail` server-side, since Heroku doesn't
                    # echo the X-Request-ID back in responses (only logs it).
                    bag["failed_requests"].append(
                        {
                            "url": resp.url,
                            "status": resp.status,
                            "method": resp.request.method,
                            "ts_ms": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                            "hx_request": h.get("hx-request") == "true",
                            "hx_boosted": h.get("hx-boosted") == "true",
                            "hx_target": h.get("hx-target", ""),
                            "hx_trigger": h.get("hx-trigger", ""),
                            "purpose": h.get("purpose") or h.get("sec-purpose", ""),
                            "fetch_dest": h.get("sec-fetch-dest", ""),
                            # If the app/router echoes any of these we can
                            # cross-correlate without timestamps.
                            "via": rh.get("via", ""),
                            "cf_ray": rh.get("cf-ray", ""),
                            "set_cookie_csrf": "dazzle_csrf=" in (rh.get("set-cookie") or ""),
                            "set_cookie_session": "dazzle_session=" in (rh.get("set-cookie") or ""),
                            # Cookie state at moment of failure (the headline question
                            # for dazzle#969 Pattern B diagnosis)
                            "cookie_state": cookie_state,
                        }
                    )
            except Exception:
                pass

        def on_dialog(dialog):
            # Auto-dismiss but record — alerts/confirms during a fuzz run
            # are nearly always a regression (we never trigger them
            # deliberately).
            bag["dialogs"].append({"type": dialog.type, "message": dialog.message})
            try:
                dialog.dismiss()
            except Exception:
                pass

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)
        page.on("dialog", on_dialog)
        return bag

    def _drain_bag(self, bag: dict, page: Page, action_label: str) -> None:
        """Convert listener-bag entries into Finding records. Called
        after every interaction so the iter counter aligns with the
        click that triggered it."""
        url = page.url

        for e in bag["page_errors"]:
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category="page-error",
                    severity="high",
                    message=str(e)[:300],
                    context={"action": action_label},
                )
            )
        for e in bag["console_errors"]:
            text = e.get("text") or ""
            cat = "console-error"
            sev = "high"
            # Pattern-classify htmx errors so they show up distinctly.
            if "htmx:" in text and "swapError" in text:
                cat = "htmx-swap-error"
            elif "htmx:" in text and "responseError" in text:
                cat = "htmx-response-error"
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category=cat,
                    severity=sev,
                    message=text[:300],
                    context={"action": action_label, "location": e.get("location")},
                )
            )
        for e in bag["console_warnings"]:
            text = e.get("text") or ""
            # Alpine Expression Errors masquerade as warnings — promote.
            sev = "high" if "Alpine" in text or "Expression" in text else "low"
            cat = "console-warning"
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category=cat,
                    severity=sev,
                    message=text[:300],
                    context={"action": action_label, "location": e.get("location")},
                )
            )
        for r in bag["failed_requests"]:
            # NOTE: previously this dropped 401/403 on /app/ as noise.
            # That hid the actual signal we needed to diagnose the
            # workspace-403 pattern. Now we pass them through with the
            # request-context fields (hx_request, hx_boosted, purpose,
            # etc.) so the operator can see WHY each 4xx fired:
            #   - hx_boosted=true → user-triggered boost click
            #   - hx_request=true + hx_trigger=region-* → region eager-load
            #   - purpose=prefetch → speculative prefetch
            #   - none of the above + sec-fetch-dest=document → full nav
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category="request-failed",
                    severity="medium" if r["status"] in (401, 403) else "high",
                    message=f"{r['status']} {r['method']} {r['url']}",
                    context={
                        "action": action_label,
                        "ts_ms": r["ts_ms"],
                        "hx_request": r["hx_request"],
                        "hx_boosted": r["hx_boosted"],
                        "hx_target": r["hx_target"],
                        "hx_trigger": r["hx_trigger"],
                        "purpose": r["purpose"],
                        "fetch_dest": r["fetch_dest"],
                        "via": r["via"],
                        "cf_ray": r["cf_ray"],
                        "set_cookie_csrf_rotated": r["set_cookie_csrf"],
                        "set_cookie_session_rotated": r.get("set_cookie_session", False),
                        "cookie_state": r.get("cookie_state", {}),
                    },
                )
            )
        for d in bag["dialogs"]:
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category="dialog",
                    severity="high",
                    message=f"{d['type']}: {d['message']}",
                    context={"action": action_label},
                )
            )
        # Drain session-cookie events as informational findings so they
        # show up in the JSONL stream and can be correlated with 4xx by
        # timestamp. Non-clear events are 'low' (just rotation/refresh);
        # clear events are 'high' (the prime suspect for Pattern B).
        for ev in bag["session_cookie_events"]:
            sev = "high" if ev["cleared"] else "low"
            self._emit(
                Finding(
                    iter=self.iter,
                    url=url,
                    category="session-cookie-cleared"
                    if ev["cleared"]
                    else "session-cookie-rotated",
                    severity=sev,
                    message=f"{ev['status']} {ev['url']}",
                    context={
                        "action": action_label,
                        "ts_ms": ev["ts"],
                        "set_cookie_excerpt": ev["set_cookie_excerpt"],
                    },
                )
            )

        # Reset for next round.
        for k in bag:
            bag[k].clear()

    def _login(self, page: Page) -> None:
        """Establish a session via Dazzle's QA magic-link.

        Two-step flow:
          1. POST /qa/magic-link with {"persona_id": "<name>"} →
             returns {"url": "/auth/magic/<token>"}
          2. GET that URL → server validates token, sets
             dazzle_session cookie, redirects to /app

        The QA endpoint is only mounted when the dev server runs
        with --enable-test-mode (default in dev). Falls back to
        unauthenticated browsing when the endpoint is missing —
        public surfaces still get fuzzed; auth-gated surfaces
        will 401 and surface as findings.

        `--persona` accepts either a bare persona id (`admin`,
        `customer`) or a full email; we strip the `@example.test`
        suffix so both forms work.
        """
        persona_id = self.email.split("@", 1)[0]
        try:
            response = page.request.post(
                f"{self.base}/qa/magic-link",
                data={"persona_id": persona_id},
                timeout=10_000,
            )
            if not response.ok:
                print(
                    f"  ! /qa/magic-link returned {response.status} for "
                    f"persona_id={persona_id!r} — running unauthenticated"
                )
            else:
                # Step 2: redeem the magic link via page.goto so
                # the session cookie lands on the browser context
                # (page.request shares cookies, but go-via-page
                # also follows the auth redirect to /app).
                magic_url = response.json().get("url", "")
                if magic_url:
                    page.goto(
                        f"{self.base}{magic_url}",
                        wait_until="domcontentloaded",
                        timeout=15_000,
                    )
                    return
        except Exception as exc:
            print(f"  ! magic-link auth failed ({exc}) — running unauthenticated")
        # Fallback path: just land on /app and let any 4xx surface
        # as findings.
        try:
            page.goto(f"{self.base}/app", wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass  # /app may not exist if the project has no workspaces

    def _safe_clickables(self, page: Page) -> list[dict]:
        """Inventory clickable elements likely to navigate or fire htmx.
        Returns up to ~50 candidates (caps to avoid quadratic blowup on
        big lists). Filters destructive verbs (delete, logout)."""
        try:
            return page.evaluate(r"""
                () => {
                    const out = [];
                    const seen = new Set();
                    const push = (sel, label, kind) => {
                        const key = sel + '|' + label;
                        if (seen.has(key)) return;
                        seen.add(key);
                        out.push({ sel, label, kind });
                    };
                    // Anchors with internal hrefs
                    document.querySelectorAll('a[href]').forEach((a, i) => {
                        const href = a.getAttribute('href') || '';
                        const text = (a.textContent || '').trim().slice(0, 60);
                        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
                        if (href.startsWith('mailto:') || href.startsWith('tel:')) return;
                        if (a.target && a.target === '_blank') return;
                        // Skip explicit external + skip destructive verbs
                        if (/^https?:/.test(href) && !href.startsWith(location.origin)) return;
                        const lower = text.toLowerCase();
                        if (/log\s*out|sign\s*out|delete|remove/.test(lower)) return;
                        // Build a unique-ish selector via nth-of-type
                        const path = [];
                        let el = a;
                        while (el && el.nodeType === 1 && path.length < 4) {
                            const tn = el.tagName.toLowerCase();
                            const parent = el.parentElement;
                            if (!parent) break;
                            const idx = Array.from(parent.children).indexOf(el) + 1;
                            path.unshift(tn + ':nth-child(' + idx + ')');
                            el = parent;
                        }
                        push(path.join(' > '), text || href, 'link');
                    });
                    // List rows with hx-get (already nav-converted in our base.html)
                    document.querySelectorAll('.dz-list-row[hx-get], tr[hx-get]').forEach(r => {
                        const text = (r.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
                        const path = [];
                        let el = r;
                        while (el && el.nodeType === 1 && path.length < 4) {
                            const tn = el.tagName.toLowerCase();
                            const parent = el.parentElement;
                            if (!parent) break;
                            const idx = Array.from(parent.children).indexOf(el) + 1;
                            path.unshift(tn + ':nth-child(' + idx + ')');
                            el = parent;
                        }
                        push(path.join(' > '), text, 'row');
                    });
                    // Buttons with hx-get / hx-post (skip destructive ones)
                    document.querySelectorAll('button[hx-get], button[hx-post]').forEach(b => {
                        const text = (b.textContent || '').trim().slice(0, 60);
                        const lower = text.toLowerCase();
                        // CRITICAL: include logout/sign-out here — the
                        // anchor filter has it, but buttons go through
                        // this branch. Cycle 124 found the fuzzer was
                        // clicking the Logout BUTTON, destroying the
                        // session, and misattributing every subsequent
                        // 4xx to a phantom "Pattern B race". Hours of
                        // upstream investigation lost. Never again.
                        if (/log\s*out|sign\s*out|delete|remove|destroy|drop|reset/.test(lower)) return;
                        const path = [];
                        let el = b;
                        while (el && el.nodeType === 1 && path.length < 4) {
                            const tn = el.tagName.toLowerCase();
                            const parent = el.parentElement;
                            if (!parent) break;
                            const idx = Array.from(parent.children).indexOf(el) + 1;
                            path.unshift(tn + ':nth-child(' + idx + ')');
                            el = parent;
                        }
                        push(path.join(' > '), text, 'button');
                    });
                    return out.slice(0, 50);
                }
            """)
        except Exception:
            return []

    def _click_target(self, page: Page, target: dict, settle_ms: int = 1500) -> None:
        """Click via JS rather than playwright's locator so we don't get
        stalled by overlapping selectors. Settles by waiting for network
        idle (briefly) then a fixed pause."""
        sel = target["sel"]
        try:
            # Scroll into view first — htmx click handlers ignore off-screen.
            page.evaluate(
                "(s) => { const e = document.querySelector(s); if (e) e.scrollIntoView({block:'center'}); }",
                sel,
            )
            page.evaluate(
                "(s) => { const e = document.querySelector(s); if (e) e.click(); }",
                sel,
            )
        except Exception as e:
            self._emit(
                Finding(
                    iter=self.iter,
                    url=page.url,
                    category="navigation-timeout",
                    severity="medium",
                    message=f"click failed on {sel}: {e}",
                    context={"target": target},
                )
            )
            return

        try:
            page.wait_for_load_state("networkidle", timeout=settle_ms + 1000)
        except PlaywrightTimeoutError:
            # Some surfaces have permanent polling htmx (e.g. recent stacks
            # auto-refresh). networkidle never settles. That's OK —
            # forwards to a hard pause.
            pass
        page.wait_for_timeout(200)  # paint settle

    def _race_probe(self, page: Page, candidates: list[dict]) -> None:
        """Click two distinct candidates in quick succession to force an
        overlapping htmx request. If the framework's morph handler isn't
        reentrant, console errors / stuck DOM follow."""
        if len(candidates) < 2:
            return
        a, b = self.rng.sample(candidates, 2)
        try:
            page.evaluate(
                """([sa, sb]) => {
                    const ea = document.querySelector(sa);
                    const eb = document.querySelector(sb);
                    if (ea) { try { ea.scrollIntoView({block:'center'}); } catch (e) {} ea.click(); }
                    // Tiny gap so the two requests overlap rather than stack.
                    setTimeout(() => {
                        if (eb) { try { eb.scrollIntoView({block:'center'}); } catch (e) {} eb.click(); }
                    }, 30);
                }""",
                [a["sel"], b["sel"]],
            )
        except Exception as e:
            self._emit(
                Finding(
                    iter=self.iter,
                    url=page.url,
                    category="navigation-timeout",
                    severity="medium",
                    message=f"race probe failed: {e}",
                    context={"a": a, "b": b},
                )
            )
            return
        try:
            page.wait_for_load_state("networkidle", timeout=2500)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(300)

    def run(self, duration_s: float, max_iterations: int) -> int:
        with sync_playwright() as p:
            engine = getattr(p, self.browser_name, p.chromium)
            browser = engine.launch(headless=not self.headed)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 site-fuzz",
                ignore_https_errors=False,
            )
            page = ctx.new_page()
            bag = self._attach_listeners(page)
            self._login(page)
            self._drain_bag(bag, page, "login")

            current_url = self.base + self.rng.choice(self.seed_surfaces)
            page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
            self._drain_bag(bag, page, "seed-load")

            try:
                while True:
                    self.iter += 1
                    elapsed = time.monotonic() - self.t0
                    if duration_s and elapsed > duration_s:
                        print(f"\nDuration limit ({duration_s}s) reached.")
                        break
                    if max_iterations and self.iter > max_iterations:
                        print(f"\nIteration limit ({max_iterations}) reached.")
                        break

                    print(
                        f"[iter {self.iter} · {elapsed:5.0f}s · {len(self.findings)} findings] {page.url}"
                    )

                    candidates = self._safe_clickables(page)
                    if not candidates:
                        # Stuck on a dead-end surface. Re-seed.
                        target_url = self.base + self.rng.choice(self.seed_surfaces)
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                        except PlaywrightTimeoutError:
                            self._emit(
                                Finding(
                                    iter=self.iter,
                                    url=target_url,
                                    category="navigation-timeout",
                                    severity="high",
                                    message=f"goto timeout on {target_url}",
                                )
                            )
                        self._drain_bag(bag, page, "reseed")
                        continue

                    # Race probe? Only when we have plenty of candidates
                    # AND we're not on a write-y page (where overlapping
                    # mutations would be ambiguous).
                    if (
                        self.rng.random() < self.race_probability
                        and len(candidates) >= 4
                        and "/upload" not in page.url
                        and "/edit" not in page.url
                    ):
                        self._race_probe(page, candidates)
                        self._drain_bag(bag, page, "race-probe")
                        continue

                    # Back probe? Forces htmx history restore — historically
                    # buggy in Alpine + idiomorph mixes.
                    if self.rng.random() < self.back_probability:
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=8000)
                        except PlaywrightTimeoutError:
                            pass
                        self._drain_bag(bag, page, "back")
                        continue

                    target = self.rng.choice(candidates)
                    self._click_target(page, target)
                    self._drain_bag(bag, page, f"{target['kind']}: {target['label'][:40]}")

                    # Occasionally jump back to a seed to escape a deep
                    # path that's just bouncing between two adjacent
                    # views.
                    if self.iter % 25 == 0:
                        target_url = self.base + self.rng.choice(self.seed_surfaces)
                        page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                        self._drain_bag(bag, page, "periodic-reseed")
            except KeyboardInterrupt:
                print("\nInterrupted.")
            finally:
                browser.close()

        # Summary
        elapsed = time.monotonic() - self.t0
        print(f"\nFuzz run summary: {self.iter} iterations in {elapsed:.0f}s")
        print(f"  total findings: {len(self.findings)}")
        by_cat: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for f in self.findings:
            by_cat[f.category] = by_cat.get(f.category, 0) + 1
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        if by_cat:
            print("  by category:")
            for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
                print(f"    {cat:25s} {n}")
            print("  by severity:")
            for sev, n in sorted(by_sev.items(), key=lambda kv: -kv[1]):
                print(f"    {sev:10s} {n}")
        print(f"  Findings stream: {self.findings_path}")
        return 1 if any(f.severity == "high" for f in self.findings) else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Base URL of the running dazzle serve instance (default {DEFAULT_BASE})",
    )
    p.add_argument(
        "--persona",
        default=DEFAULT_PERSONA_EMAIL,
        help=(f"Dev persona email for QA magic-link auth (default {DEFAULT_PERSONA_EMAIL})"),
    )
    p.add_argument(
        "--seed-url",
        action="append",
        default=None,
        help="Override default seed surfaces (repeatable). Paths relative to --base.",
    )
    p.add_argument("--browser", default="chromium", choices=("chromium", "webkit", "firefox"))
    p.add_argument("--headed", action="store_true")
    p.add_argument(
        "--duration",
        type=float,
        default=0,
        help="seconds before stop (0 = forever; Ctrl-C any time)",
    )
    p.add_argument(
        "--max-iterations", type=int, default=0, help="cap on iterations (0 = unlimited)"
    )
    p.add_argument(
        "--race-probability",
        type=float,
        default=0.15,
        help="probability per iter of firing a race-condition probe",
    )
    p.add_argument("--no-race", action="store_true", help="alias for --race-probability=0")
    p.add_argument(
        "--back-probability",
        type=float,
        default=0.05,
        help="probability per iter of hitting back to test htmx history",
    )
    p.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS_PATH)
    p.add_argument("--seed", type=int, default=None, help="rng seed for reproducibility")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.no_race:
        args.race_probability = 0.0
    f = Fuzzer(
        base=args.base,
        email=args.persona,
        browser_name=args.browser,
        headed=args.headed,
        race_probability=args.race_probability,
        back_probability=args.back_probability,
        findings_path=args.findings,
        seed=args.seed,
        seed_surfaces=args.seed_url,
    )
    return f.run(duration_s=args.duration, max_iterations=args.max_iterations)


if __name__ == "__main__":
    sys.exit(main())
