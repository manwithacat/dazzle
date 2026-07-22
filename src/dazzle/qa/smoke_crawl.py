"""Mechanical browser smoke crawl for obvious functional bugs (#1625 L2.5).

Complements HTTP-only ``trial-coverage`` (misses 200 + empty main) and deep
``qa trial`` (wrong KPI for bug density). Drive rule: inventory URLs are OK
for the inventory phase; optional BFS only follows rendered same-origin
``/app`` links and primary controls.

Oracles (cheap, deterministic — not vision):

* document HTTP status ≥ 400
* title / body markers for 404 / 5xx / "Not Found"
* empty or near-empty ``main`` after settle
* ``pageerror`` / uncaught exceptions during the step
* nested ``[data-dz-refresh]`` / duplicate ``#region-*`` (structure)
* **landing** probe after magic-link (persona default route)
* **mutation** phase: open inventory create URLs + primary New CTAs

Emits trial-friction-compatible rows + ``auto_seed`` via
:func:`dazzle.qa.trial_friction.is_auto_seed_eligible`.
"""

from __future__ import annotations

import logging
import re
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from dazzle.qa.trial_friction import is_auto_seed_eligible, normalize_friction_entry
from dazzle.qa.trial_inventory import matrix_expected_deny

logger = logging.getLogger(__name__)

# Playwright settle failures (timeouts / closed targets) — keep narrow so the
# broad-exception swallow ratchet does not grow (see fitness/swallows.py).
# Note: playwright.sync_api.TimeoutError is NOT a subclass of builtins.TimeoutError
# (MRO: playwright._impl._errors.TimeoutError → Error → Exception).
# TYPE_CHECKING split avoids mypy no-redef / unused-ignore / assignment thrash
# when playwright is present in CI type-check but optional at runtime.
if TYPE_CHECKING:
    from playwright.sync_api import Error as _PlaywrightError
    from playwright.sync_api import TimeoutError as _PlaywrightTimeoutError
else:  # pragma: no cover — runtime bind; playwright optional
    try:
        from playwright.sync_api import Error as _PlaywrightError
        from playwright.sync_api import TimeoutError as _PlaywrightTimeoutError
    except ImportError:
        _PlaywrightError = RuntimeError
        _PlaywrightTimeoutError = TimeoutError

_SETTLE_EXC: tuple[type[BaseException], ...] = (
    TimeoutError,
    _PlaywrightTimeoutError,
    _PlaywrightError,
    OSError,
    RuntimeError,
)

# Main content shorter than this (after whitespace collapse) is "empty main".
EMPTY_MAIN_THRESHOLD = 48

# Titles / body snippets that indicate an error page rather than a thin shell.
_ERROR_TITLE_RE = re.compile(
    r"\b(404|not\s*found|500|502|503|internal\s+server\s+error|upstream\s+error|"
    r"bad\s+gateway|something\s+went\s+wrong)\b",
    re.I,
)
_ERROR_BODY_RE = re.compile(
    r"(page\s+not\s+found|not\s+found\s*\(?404\)?|internal\s+server\s+error|"
    r"upstream\s+(?:error|connect)|bad\s+gateway|traceback\s+\(most\s+recent)",
    re.I,
)

# BFS: skip these href prefixes / exacts (logout, auth bounce, external-ish).
_SKIP_HREF_RE = re.compile(
    r"(logout|sign[-_]?out|/auth/|/login|javascript:|mailto:|#)",
    re.I,
)

_DEFAULT_MAX_CLICKS = 20
_DEFAULT_TIMEOUT_MS = 12_000


@dataclass
class SmokeIssue:
    """One oracle failure on a single page visit."""

    code: str  # http_error | empty_main | error_marker | page_error
    detail: str
    ownership: str = "product"  # product | rbac_expected | harness | unclear
    severity: str = "high"  # low | medium | high


@dataclass
class SmokeHit:
    """Result of probing one URL (inventory or click-through)."""

    url: str
    name: str
    kind: str  # surface_list | workspace | click | …
    phase: str  # inventory | bfs
    ok: bool
    http_status: int | None = None
    title: str = ""
    main_text_len: int = 0
    main_text_head: str = ""
    issues: list[SmokeIssue] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    ownership_hint: str = "unclear"
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def evaluate_structure_oracles(
    *,
    duplicate_region_ids: list[str] | None = None,
    nested_refresh_count: int = 0,
) -> list[SmokeIssue]:
    """DOM structure oracles — nested region wrappers (queue double-wrap class)."""
    issues: list[SmokeIssue] = []
    dups = list(duplicate_region_ids or [])
    if dups:
        issues.append(
            SmokeIssue(
                code="structure",
                detail=f"duplicate region ids in DOM: {', '.join(dups[:8])}",
                ownership="framework",
                severity="medium",
            )
        )
    if nested_refresh_count > 0:
        issues.append(
            SmokeIssue(
                code="structure",
                detail=f"nested [data-dz-refresh] count={nested_refresh_count}",
                ownership="framework",
                severity="medium",
            )
        )
    return issues


def evaluate_page_oracles(
    *,
    http_status: int | None,
    title: str,
    main_text: str,
    page_errors: list[str] | None = None,
    expected_rbac_deny: bool | None = None,
    duplicate_region_ids: list[str] | None = None,
    nested_refresh_count: int = 0,
) -> list[SmokeIssue]:
    """Pure oracle evaluation — unit-tested without Playwright."""
    issues: list[SmokeIssue] = []
    main = _collapse_ws(main_text)
    title_s = (title or "").strip()
    errs = list(page_errors or [])
    issues.extend(
        evaluate_structure_oracles(
            duplicate_region_ids=duplicate_region_ids,
            nested_refresh_count=nested_refresh_count,
        )
    )

    if http_status is not None and http_status >= 400:
        if http_status in (401, 403):
            if expected_rbac_deny is False:
                issues.append(
                    SmokeIssue(
                        code="http_error",
                        detail=f"HTTP {http_status} but matrix allows — unexpected deny",
                        ownership="product",
                        severity="high",
                    )
                )
            else:
                # True or None (workspace / no matrix entity): treat as expected deny.
                detail = (
                    f"HTTP {http_status} (matrix DENY — expected)"
                    if expected_rbac_deny is True
                    else f"HTTP {http_status} (auth/RBAC deny)"
                )
                issues.append(
                    SmokeIssue(
                        code="http_error",
                        detail=detail,
                        ownership="rbac_expected",
                        severity="low",
                    )
                )
        elif http_status == 404:
            own = "rbac_expected" if expected_rbac_deny is True else "product"
            sev = "low" if own == "rbac_expected" else "high"
            issues.append(
                SmokeIssue(
                    code="http_error",
                    detail=f"HTTP {http_status}",
                    ownership=own,
                    severity=sev,
                )
            )
        elif http_status >= 500:
            issues.append(
                SmokeIssue(
                    code="http_error",
                    detail=f"HTTP {http_status}",
                    ownership="product",
                    severity="high",
                )
            )
        else:
            issues.append(
                SmokeIssue(
                    code="http_error",
                    detail=f"HTTP {http_status}",
                    ownership="unclear",
                    severity="medium",
                )
            )

    if _ERROR_TITLE_RE.search(title_s):
        issues.append(
            SmokeIssue(
                code="error_marker",
                detail=f"error-like title: {title_s[:120]!r}",
                ownership="product",
                severity="high",
            )
        )
    elif main and _ERROR_BODY_RE.search(main[:800]):
        issues.append(
            SmokeIssue(
                code="error_marker",
                detail=f"error-like body: {main[:160]!r}",
                ownership="product",
                severity="high",
            )
        )

    # Empty main: only flag when we got a "success" status (or unknown) so
    # we don't double-count a 404 body that is short by design.
    status_ok = http_status is None or 200 <= http_status < 400
    if status_ok and len(main) < EMPTY_MAIN_THRESHOLD:
        word_count = len(main.split()) if main else 0
        # Skeleton / lazy IO often leaves "Loading…" — treat as harness.
        if re.search(r"\b(loading|please wait|skeleton)\b", main, re.I):
            issues.append(
                SmokeIssue(
                    code="empty_main",
                    detail=f"main text len={len(main)} looks like loading shell",
                    ownership="harness",
                    severity="low",
                )
            )
        elif word_count >= 4 and len(main) >= 20:
            # Short chrome / nav label strip (e.g. workspace switcher text in
            # main) — not a white screen. Leave unflagged.
            pass
        else:
            issues.append(
                SmokeIssue(
                    code="empty_main",
                    detail=(
                        f"main text len={len(main)} < {EMPTY_MAIN_THRESHOLD} (head={main[:80]!r})"
                    ),
                    ownership="product",
                    severity="high",
                )
            )

    for pe in errs[:10]:
        text = str(pe)
        # Nested Playwright resource thrash is a known harness class.
        if re.search(r"ERR_INSUFFICIENT_RESOURCES|net::ERR_", text):
            issues.append(
                SmokeIssue(
                    code="page_error",
                    detail=text[:240],
                    ownership="harness",
                    severity="low",
                )
            )
        else:
            issues.append(
                SmokeIssue(
                    code="page_error",
                    detail=text[:240],
                    ownership="product",
                    severity="medium",
                )
            )

    return _dedupe_issues(issues)


def _dedupe_issues(issues: list[SmokeIssue]) -> list[SmokeIssue]:
    seen: set[tuple[str, str]] = set()
    out: list[SmokeIssue] = []
    for iss in issues:
        key = (iss.code, iss.detail[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(iss)
    return out


def _worst_ownership(issues: list[SmokeIssue]) -> str:
    """Prefer product > framework > unclear > harness > rbac_expected."""
    if not issues:
        return "unclear"
    order = ("product", "framework", "unclear", "harness", "rbac_expected", "seed")
    ranks = {o: i for i, o in enumerate(order)}
    return min((i.ownership for i in issues), key=lambda o: ranks.get(o, 99))


def hit_to_friction(hit: SmokeHit) -> dict[str, Any] | None:
    """Map a failing hit to a trial friction entry (or None if ok)."""
    if hit.ok or not hit.issues:
        return None
    # Prefer product-facing issues for the friction row.
    productish = [i for i in hit.issues if i.ownership in ("product", "framework", "unclear")]
    primary = productish[0] if productish else hit.issues[0]
    sev = primary.severity
    if any(i.severity == "high" and i.ownership == "product" for i in hit.issues):
        sev = "high"
    codes = ", ".join(sorted({i.code for i in hit.issues}))
    return {
        "category": "bug",
        "severity": sev,
        "description": (f"Smoke crawl {hit.phase}/{hit.kind}: {codes} on {hit.name or hit.url}"),
        "url": hit.url,
        "evidence": (
            f"http_status={hit.http_status} title={hit.title!r} "
            f"main_len={hit.main_text_len} issues="
            + "; ".join(f"{i.code}:{i.detail}" for i in hit.issues)
        ),
        "blocks_pilot": primary.ownership == "product" and sev == "high",
        "ownership": hit.ownership_hint or primary.ownership,
    }


def build_smoke_report(
    *,
    app: str,
    persona: str,
    base_url: str,
    hits: list[SmokeHit],
    max_clicks: int,
) -> dict[str, Any]:
    frictions: list[dict[str, Any]] = []
    for h in hits:
        row = hit_to_friction(h)
        if row is not None:
            frictions.append(normalize_friction_entry(row))
    auto_seed = [f for f in frictions if is_auto_seed_eligible(f)]
    counts: dict[str, int] = {"ok": 0, "fail": 0}
    by_code: dict[str, int] = {}
    for h in hits:
        counts["ok" if h.ok else "fail"] = counts.get("ok" if h.ok else "fail", 0) + 1
        for iss in h.issues:
            by_code[iss.code] = by_code.get(iss.code, 0) + 1
    return {
        "schema_version": 1,
        "mode": "smoke_crawl",
        "app": app,
        "persona": persona,
        "base_url": base_url,
        "max_clicks": max_clicks,
        "counts": counts,
        "issue_codes": by_code,
        "hits": [h.to_json() for h in hits],
        "friction": frictions,
        "auto_seed": auto_seed,
    }


_MAIN_EVAL_JS = """() => {
  const main = document.querySelector(
    'main, [role="main"], #main, .dz-main, [data-dz-main], .app-main'
  );
  const el = main || document.body;
  const text = ((el && el.innerText) || '').replace(/\\s+/g, ' ').trim();
  // Structure: duplicate #region-* ids and nested data-dz-refresh (HTMX double-wrap).
  const regionEls = Array.from(document.querySelectorAll('[id^="region-"]'));
  const ids = regionEls.map((r) => r.id).filter(Boolean);
  const seen = new Set();
  const dups = [];
  for (const id of ids) {
    if (seen.has(id)) dups.push(id);
    else seen.add(id);
  }
  const refresh = Array.from(document.querySelectorAll('[data-dz-refresh]'));
  let nestedRefresh = 0;
  for (const el of refresh) {
    const parent = el.parentElement && el.parentElement.closest('[data-dz-refresh]');
    if (parent && parent !== el) nestedRefresh += 1;
  }
  return {
    title: document.title || '',
    main_text: text.slice(0, 2000),
    main_text_len: text.length,
    body_len: ((document.body && document.body.innerText) || '').trim().length,
    duplicate_region_ids: dups.slice(0, 20),
    nested_refresh_count: nestedRefresh,
  };
}"""

_COLLECT_LINKS_JS = """() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!href || seen.has(href)) continue;
    seen.add(href);
    const text = ((a.innerText || a.getAttribute('aria-label') || '').trim()).slice(0, 80);
    out.push({ href, text, tag: 'a' });
  }
  // Primary-ish buttons that look like create / new (href-less HTMX often uses hx-get).
  for (const el of document.querySelectorAll(
    'a[href*="/create"], button, [role="button"], [hx-get], [hx-post]'
  )) {
    const text = ((el.innerText || el.getAttribute('aria-label') || '').trim()).slice(0, 80);
    const hx = el.getAttribute('hx-get') || el.getAttribute('hx-post') || '';
    const href = el.getAttribute('href') || hx || '';
    if (!href && !/\\b(new|create|add)\\b/i.test(text)) continue;
    const key = href || text;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ href, text, tag: (el.tagName || '').toLowerCase() });
  }
  return out.slice(0, 80);
}"""


def _same_origin_app_path(base: str, href: str) -> str | None:
    """Resolve href to a path under /app on the same origin, or None."""
    if not href or _SKIP_HREF_RE.search(href):
        return None
    base_p = urlparse(base)
    if href.startswith("http"):
        p = urlparse(href)
        if p.netloc and p.netloc != base_p.netloc:
            return None
        path = p.path or "/"
    else:
        path = urlparse(urljoin(base.rstrip("/") + "/", href)).path
    if not path.startswith("/app"):
        return None
    return path


def run_smoke_crawl(
    *,
    base_url: str,
    persona: str,
    targets: list[Any],
    appspec: Any = None,
    headless: bool = True,
    max_clicks: int = _DEFAULT_MAX_CLICKS,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    enable_bfs: bool = True,
) -> list[SmokeHit]:
    """Live Playwright smoke crawl. Requires playwright + running app."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required for smoke-crawl. "
            "Install: pip install playwright && playwright install chromium"
        ) from exc

    import httpx

    base = base_url.rstrip("/")
    hits: list[SmokeHit] = []

    # Magic-link URL for Playwright navigation (same as trial-coverage).
    try:
        ml = httpx.post(
            f"{base}/qa/magic-link",
            json={"persona_id": persona},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach {base}: {exc}") from exc
    if ml.status_code != 200:
        raise RuntimeError(
            f"magic-link failed HTTP {ml.status_code} — need DAZZLE_QA_MODE=1 "
            f"and persona {persona!r}"
        )
    magic_path = (ml.json() or {}).get("url") or ""
    if not magic_path:
        raise RuntimeError("magic-link response missing url")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(base_url=base)
        page = context.new_page()
        page_errors: list[str] = []

        def _on_page_error(exc: Any) -> None:
            page_errors.append(str(exc)[:300])

        page.on("pageerror", _on_page_error)

        # Authenticate
        page.goto(urljoin(base + "/", magic_path.lstrip("/")), wait_until="domcontentloaded")
        with suppress(*_SETTLE_EXC):
            page.wait_for_load_state("networkidle", timeout=timeout_ms)

        visited: set[str] = set()

        # Landing probe: persona default route after magic-link (catches white screens).
        try:
            landing_url = page.url or ""
            landing_path = urlparse(landing_url).path or "/app"
        except (ValueError, TypeError, AttributeError):
            landing_path = "/app"
        with suppress(*_SETTLE_EXC):
            page.wait_for_timeout(200)
        # Re-snap landing without re-nav if already there.
        landing_hit = None

        def _probe(url_path: str, name: str, kind: str, phase: str, target: Any = None) -> SmokeHit:
            page_errors.clear()
            expected_deny: bool | None = None
            if target is not None and appspec is not None:
                expected_deny = matrix_expected_deny(appspec, persona, target)

            status: int | None = None
            try:
                resp = page.goto(
                    urljoin(base + "/", url_path.lstrip("/")),
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                if resp is not None:
                    status = resp.status
            except _SETTLE_EXC as exc:
                return SmokeHit(
                    url=url_path,
                    name=name,
                    kind=kind,
                    phase=phase,
                    ok=False,
                    http_status=None,
                    issues=[
                        SmokeIssue(
                            code="page_error",
                            detail=f"navigation failed: {exc}",
                            ownership="harness",
                            severity="medium",
                        )
                    ],
                    ownership_hint="harness",
                    detail=str(exc),
                )

            with suppress(*_SETTLE_EXC):
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
            # HTMX region settle beat
            with suppress(*_SETTLE_EXC):
                page.wait_for_timeout(200)

            try:
                snap = page.evaluate(_MAIN_EVAL_JS)
            except _SETTLE_EXC as exc:
                snap = {
                    "title": "",
                    "main_text": "",
                    "main_text_len": 0,
                }
                page_errors.append(f"evaluate failed: {exc}")

            title = str(snap.get("title") or "")
            main_text = str(snap.get("main_text") or "")
            main_len = int(snap.get("main_text_len") or len(_collapse_ws(main_text)))
            dups = [str(x) for x in (snap.get("duplicate_region_ids") or [])]
            nested = int(snap.get("nested_refresh_count") or 0)

            issues = evaluate_page_oracles(
                http_status=status,
                title=title,
                main_text=main_text,
                page_errors=list(page_errors),
                expected_rbac_deny=expected_deny,
                duplicate_region_ids=dups,
                nested_refresh_count=nested,
            )
            # Product/harness: empty_main + http 404 both "fail" for ok=False
            # only when something non-rbac/harness-low is present? Keep simple:
            # ok if no product/unclear/framework medium+ issues.
            failish = [
                i
                for i in issues
                if i.ownership in ("product", "framework", "unclear")
                and i.severity in ("medium", "high")
            ]
            own = _worst_ownership(issues) if issues else "unclear"
            return SmokeHit(
                url=url_path,
                name=name,
                kind=kind,
                phase=phase,
                ok=not failish,
                http_status=status,
                title=title,
                main_text_len=main_len,
                main_text_head=main_text[:120],
                issues=issues,
                page_errors=list(page_errors),
                ownership_hint=own,
            )

        # Landing after magic-link — catch blank persona home before inventory.
        if landing_path and landing_path not in visited:
            visited.add(landing_path)
            landing_hit = _probe(
                landing_path,
                name="landing",
                kind="landing",
                phase="landing",
            )
            hits.append(landing_hit)

        for t in targets:
            path = str(getattr(t, "url", "") or "")
            if not path or path in visited:
                continue
            visited.add(path)
            hit = _probe(
                path,
                name=str(getattr(t, "name", "") or path),
                kind=str(getattr(t, "kind", "inventory") or "inventory"),
                phase="inventory",
                target=t,
            )
            hits.append(hit)

        # Mutation phase: inventory create surfaces (gross write-path bugs).
        create_targets = [
            t
            for t in targets
            if "create" in str(getattr(t, "kind", "") or "").lower()
            or "/create" in str(getattr(t, "url", "") or "").lower()
        ]
        for t in create_targets[:8]:
            path = str(getattr(t, "url", "") or "")
            if not path or path in visited:
                continue
            visited.add(path)
            hits.append(
                _probe(
                    path,
                    name=str(getattr(t, "name", "") or path),
                    kind=str(getattr(t, "kind", "create") or "create"),
                    phase="mutation",
                    target=t,
                )
            )

        if enable_bfs and max_clicks > 0:
            # Seed BFS from /app (or first successful inventory hit).
            seed = "/app"
            if seed not in visited:
                hits.append(_probe(seed, name="app", kind="app_home", phase="bfs"))
                visited.add(seed)
            with suppress(*_SETTLE_EXC):
                page.goto(urljoin(base + "/", "app"), wait_until="domcontentloaded")
                page.wait_for_timeout(200)

            clicks = 0
            queue: list[tuple[str, str]] = []
            try:
                raw_links = page.evaluate(_COLLECT_LINKS_JS)
            except _SETTLE_EXC:
                raw_links = []
            for item in raw_links or []:
                href = str((item or {}).get("href") or "")
                text = str((item or {}).get("text") or href)
                # Use app_path (not path) so mypy does not collide with str path above.
                app_path = _same_origin_app_path(base, href)
                if app_path and app_path not in visited:
                    queue.append((app_path, text or app_path))

            while queue and clicks < max_clicks:
                bfs_path, text = queue.pop(0)
                if bfs_path in visited:
                    continue
                visited.add(bfs_path)
                clicks += 1
                hit = _probe(bfs_path, name=text[:60], kind="click", phase="bfs")
                hits.append(hit)
                if not hit.ok:
                    continue
                # Expand from current page
                try:
                    raw_links = page.evaluate(_COLLECT_LINKS_JS)
                except _SETTLE_EXC:
                    raw_links = []
                for item in raw_links or []:
                    href = str((item or {}).get("href") or "")
                    label = str((item or {}).get("text") or href)
                    npath = _same_origin_app_path(base, href)
                    if npath and npath not in visited:
                        queue.append((npath, label or npath))

        context.close()
        browser.close()

    return hits
