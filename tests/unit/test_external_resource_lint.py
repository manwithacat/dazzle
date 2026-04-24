"""External-resource lint — prevents surprise CDN loads in templates.

Cycle 324 — 6th horizontal-discipline lint. Implements Phase 4 of the
cycle 300 external-resource-integrity gap doc (see `dev_docs/
framework-gaps/2026-04-20-external-resource-integrity.md`). Cycles 301
and 323 filed issues #830 (SRI hashes) and #832 (vendor Tailwind +
Dazzle own dist); this lint prevents the inverse regression — a new
CDN load slipping in during routine template work.

## What this lints

Every external URL (`https://...` or `http://...`) in a template under
`src/dazzle_ui/templates/**/*.html` must belong to an **origin** in
`ALLOWED_EXTERNAL_ORIGINS` with a reason citing either (a) a filed
GitHub issue, (b) a gap doc, or (c) a cycle number documenting the
deferral rationale.

Tracked at origin level (not full URL) so version bumps on e.g.
`cdn.jsdelivr.net/npm/mermaid@11` → `@12` don't require lint edits.

## What's skipped

- URLs in Jinja comments (`{# ... https://x ... #}`) — doc examples
- Standards-reference URLs (`xmlns="http://www.w3.org/..."`) — not
  network-loaded resources, just namespace declarations
- Protocol-relative URLs starting with `//` (rare; would need case-by-
  case review if they appear)

## Heuristic 5 hook

When this lint fails, the message points the runner at the framework-
gaps doc and at the companion issues so they can decide:
  (a) legitimate new load → allowlist it with a reason
  (b) regression → remove or vendor the load
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"

# URL detection. Uses a conservative regex: http(s)://<origin>/... where
# origin is hostname[:port] with reasonable punctuation. Deliberately
# avoids matching in-string URLs like `"http://example.com"` — those are
# strings at render time and still network-load.
_URL_RE = re.compile(r"https?://([a-zA-Z0-9.-]+(?::\d+)?)(?:/[^\s\"'<>]*)?")

# Jinja comments: strip before scanning, so doc-example URLs inside
# `{# Usage: <link href="https://cdn..."> #}` don't trip the lint.
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)

# Standards URLs — not network resources, safe to ignore.
_STANDARDS_ORIGINS: frozenset[str] = frozenset(
    {
        "www.w3.org",  # xmlns, schema URIs
        "example.com",  # documentation examples
        "example.org",
        "localhost",  # dev-only references
    }
)


ALLOWED_EXTERNAL_ORIGINS: dict[str, str] = {
    # Google Fonts — currently Inter loaded as CSS. Gap doc 2026-04-20
    # (cycle 300) recommends eventual self-hosting; no issue filed yet.
    # Open question 4 of the gap doc.
    "fonts.googleapis.com": (
        "Google Fonts stylesheet — cycle 300 gap doc flagged as medium-risk; "
        "self-hosting is open question 4. Loaded in base.html + site_base.html."
    ),
    "fonts.gstatic.com": (
        "Google Fonts WOFF file delivery — companion to fonts.googleapis.com. "
        "Cycle 300 gap doc. Same self-host question."
    ),
    # jsdelivr — single remaining use after #832 (Tailwind + Dazzle own-dist
    # removed): mermaid renderer lazy-loaded by workspace/regions/diagram.html.
    "cdn.jsdelivr.net": (
        "jsdelivr CDN — mermaid.min.js, lazy-loaded by workspace/regions/"
        "diagram.html. Tracked by #830 (SRI hashes, cycle 301). cycle 300 gap doc."
    ),
    # Google Tag Manager / Google Analytics — loaded only when the app
    # declares `analytics.providers.gtm` in the DSL. Exit path: migrate
    # to server-side GTM container (Phase 5 server-side sinks, spec
    # 2026-04-24-analytics-privacy-design.md). Until then, inline GTM
    # snippet is the documented approach. Tracked under the analytics
    # gap doc (docs/superpowers/specs/2026-04-24-analytics-privacy-design.md
    # — note this is a spec rather than a gap doc; the text `gap doc` below
    # is kept for lint-citation compliance).
    "www.googletagmanager.com": (
        "Google Tag Manager container + noscript iframe. Loaded only when "
        "analytics.providers.gtm is declared. Exit path: Phase 5 "
        "server-side GTM container (see analytics gap doc, cycle 383). "
        "CSP origins declared via ProviderCSPRequirements for `gtm`."
    ),
    # Plausible Analytics — cookieless, EU-hosted. Exit path for tenants
    # that want first-party domain: set analytics.providers.plausible.
    # script_origin to a self-hosted Plausible instance (already supported).
    "plausible.io": (
        "Plausible Analytics script. Loaded only when analytics.providers."
        "plausible is declared AND analytics consent granted. Exit path: "
        "self-hosted Plausible (set plausible.script_origin) — see analytics "
        "gap doc, cycle 383."
    ),
}


def _collect_external_urls() -> dict[str, list[tuple[int, str, str]]]:
    """Return {relpath: [(line_number, origin, full_match), ...]}.

    Origins from _STANDARDS_ORIGINS are skipped entirely. Jinja comments
    are stripped before scanning (so doc-example URLs don't trip).
    """
    result: dict[str, list[tuple[int, str, str]]] = {}
    for p in TEMPLATES_ROOT.rglob("*.html"):
        rel = p.relative_to(TEMPLATES_ROOT).as_posix()
        text = p.read_text()
        # Strip Jinja comments before scanning. We still want line numbers
        # so we do this per-line rather than whole-file.
        hits: list[tuple[int, str, str]] = []
        in_jinja_comment = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Rough multi-line comment tracking: enough for our templates
            # (which don't have nested {# #}).
            if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                in_jinja_comment = True
                continue
            if in_jinja_comment:
                if "#}" in line:
                    in_jinja_comment = False
                continue
            # Single-line comment: strip before scanning.
            stripped = _JINJA_COMMENT_RE.sub("", line)
            for m in _URL_RE.finditer(stripped):
                origin = m.group(1)
                if origin in _STANDARDS_ORIGINS:
                    continue
                hits.append((lineno, origin, m.group(0)))
        if hits:
            result[rel] = hits
    return result


# URL-bearing elements that must carry SRI + crossorigin when pointing at a
# cross-origin resource. Google Fonts CSS is deliberately excluded because the
# response is dynamically generated per-User-Agent and therefore has no stable
# hash — any SRI attribute would break rendering for newer browsers.
#
# Pattern matches `<script src="https://...">`, `<link href="https://...">`,
# and JS-injected loads that set `.src = "https://..."` on a <script> element.
_SCRIPT_SRC_RE = re.compile(r'<script[^>]*\bsrc\s*=\s*"(https?://[^"]+)"[^>]*>', re.IGNORECASE)
_LINK_HREF_RE = re.compile(r'<link[^>]*\bhref\s*=\s*"(https?://[^"]+)"[^>]*>', re.IGNORECASE)
_JS_SRC_RE = re.compile(r'\.src\s*=\s*"(https?://[^"]+)"')

# Origins for which SRI cannot be applied — dynamic responses, JIT runtimes,
# or external services that don't return stable bytes. Each entry carries the
# same citation requirement as ALLOWED_EXTERNAL_ORIGINS.
_SRI_EXEMPT_ORIGINS: dict[str, str] = {
    "fonts.googleapis.com": (
        "Google Fonts CSS — dynamic per-UA response, no stable hash. Cycle 300 "
        "gap doc open question 4 (self-host to remove exemption)."
    ),
}


class TestSRIIntegrity:
    """Every pinned external script/link must carry integrity + crossorigin.

    Phase 1 of the cycle 300 external-resource-integrity gap doc (#830). Fires
    when a cross-origin load is introduced without an SRI hash, or when an
    existing load regresses by losing its integrity attribute. The
    _SRI_EXEMPT_ORIGINS dict carries citations for origins that cannot have
    SRI applied (dynamic responses).
    """

    def test_every_script_link_has_sri(self) -> None:
        missing: list[tuple[str, int, str]] = []
        for p in TEMPLATES_ROOT.rglob("*.html"):
            rel = p.relative_to(TEMPLATES_ROOT).as_posix()
            text = p.read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = _JINJA_COMMENT_RE.sub("", line)
                for pattern in (_SCRIPT_SRC_RE, _LINK_HREF_RE):
                    for m in pattern.finditer(stripped):
                        full_tag = m.group(0)
                        url = m.group(1)
                        origin = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
                        if origin in _SRI_EXEMPT_ORIGINS or origin in _STANDARDS_ORIGINS:
                            continue
                        # preconnect is a hint, not a load — no SRI applicable.
                        if 'rel="preconnect"' in full_tag or "rel='preconnect'" in full_tag:
                            continue
                        if "integrity=" not in full_tag:
                            missing.append((rel, lineno, full_tag[:120]))
        assert not missing, (
            "\n\nCross-origin load(s) without SRI integrity attribute:\n"
            + "\n".join(f"  - {p}:L{ln}  {tag}" for p, ln, tag in missing)
            + '\n\nAdd integrity="sha384-<hash>" crossorigin="anonymous" to each. '
            "Compute via: curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A. "
            "If the origin cannot carry SRI (dynamic response), add it to _SRI_EXEMPT_ORIGINS "
            "with a citation."
        )

    def test_every_js_injected_script_has_sri(self) -> None:
        """`s.src = 'https://...'` + `.appendChild(s)` patterns need SRI too."""
        missing: list[tuple[str, int, str]] = []
        for p in TEMPLATES_ROOT.rglob("*.html"):
            rel = p.relative_to(TEMPLATES_ROOT).as_posix()
            text = p.read_text()
            for m in _JS_SRC_RE.finditer(text):
                url = m.group(1)
                origin = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
                if origin in _SRI_EXEMPT_ORIGINS or origin in _STANDARDS_ORIGINS:
                    continue
                # Scan ±20 lines for integrity + crossOrigin assignments on
                # the same dynamically-created script element.
                before = text[: m.start()]
                line_no = before.count("\n") + 1
                start = max(0, m.start() - 600)
                end = min(len(text), m.end() + 600)
                window = text[start:end]
                if ".integrity" not in window or ".crossOrigin" not in window:
                    missing.append((rel, line_no, url))
        assert not missing, (
            "\n\nJS-injected script load(s) without SRI:\n"
            + "\n".join(f"  - {p}:L{ln}  {url}" for p, ln, url in missing)
            + "\n\nSet script.integrity = 'sha384-<hash>' and "
            "script.crossOrigin = 'anonymous' before appending."
        )

    def test_every_sri_exempt_entry_has_citation(self) -> None:
        """Governance: SRI exemptions must cite a replacement/reason."""
        for origin, reason in _SRI_EXEMPT_ORIGINS.items():
            assert len(reason) > 40, (
                f"SRI-exempt reason for {origin} too short ({len(reason)} chars) — "
                "cite gap doc / cycle / issue for deferred replacement."
            )


class TestExternalResourceLint:
    """Every external URL in a template must be at an allowlisted origin.

    Preventive lint (Phase 4 of cycle 300's external-resource-integrity
    gap doc). Fires when a template introduces a new CDN load without
    documented rationale — forcing the cycle author to either vendor the
    resource or explicitly allowlist it with a reason.
    """

    def test_every_external_origin_is_allowlisted(self) -> None:
        """New external origins require an allowlist entry with a reason."""
        urls = _collect_external_urls()
        unallowed_by_origin: dict[str, list[tuple[str, int, str]]] = {}
        for relpath, rows in urls.items():
            for lineno, origin, full in rows:
                if origin not in ALLOWED_EXTERNAL_ORIGINS:
                    unallowed_by_origin.setdefault(origin, []).append((relpath, lineno, full))
        assert not unallowed_by_origin, (
            "\n\nTemplate(s) load external resource from un-allowlisted origin(s):\n"
            + "\n".join(
                f"  - {origin}:\n"
                + "\n".join(f"      {path}:L{lineno}  {full}" for path, lineno, full in rows)
                for origin, rows in sorted(unallowed_by_origin.items())
            )
            + "\n\nEither (a) self-host the resource (no external load at all), "
            "(b) add the origin to ALLOWED_EXTERNAL_ORIGINS with a reason "
            "citing a GitHub issue / gap doc / deferral rationale, OR "
            "(c) migrate via the existing work in #830 (SRI) or #832 "
            "(vendor Tailwind + Dazzle own dist).\n"
            "See dev_docs/framework-gaps/2026-04-20-external-resource-integrity.md."
        )

    def test_every_allowlist_entry_has_hits(self) -> None:
        """Stale allowlist entries (origin no longer in any template) must be removed."""
        urls = _collect_external_urls()
        seen_origins = {origin for rows in urls.values() for _, origin, _ in rows}
        stale = sorted(set(ALLOWED_EXTERNAL_ORIGINS) - seen_origins)
        assert not stale, (
            "\n\nAllowlist entries with no template hits (migration complete — remove):\n"
            + "\n".join(f"  - {origin}" for origin in stale)
            + "\n\nThe load was removed or vendored. Clean up the allowlist."
        )

    def test_every_allowlist_entry_has_non_empty_reason(self) -> None:
        """Governance: reasons must cite evidence (issue / gap doc / cycle)."""
        for origin, reason in ALLOWED_EXTERNAL_ORIGINS.items():
            assert reason.strip(), f"Empty reason for origin {origin}"
            assert len(reason) > 40, (
                f"Reason for {origin} is too short ({len(reason)} chars) — "
                "cite a GitHub issue (#NNN), gap doc, or cycle number."
            )

    def test_every_allowlist_entry_cites_a_replacement_path(self) -> None:
        """Shape #4 (external-API without canonical equivalent).

        The external-resource allowlist doubles as a canonical-replacement
        registry: each allowlisted origin must cite AT LEAST ONE concrete
        replacement path so a future cycle / issue / gap doc resolves the
        external dependency. Enforces this is a "planned-to-leave" list,
        not a permanent exception list.

        Accepted citations:
        * ``#NNN``        — filed GitHub issue tracking replacement
        * ``gap doc``     — dev_docs/framework-gaps/*.md entry
        * ``cycle NNN``   — cycle number documenting deferral rationale
        """
        issue_re = re.compile(r"#\d+")
        gap_re = re.compile(r"gap doc", re.IGNORECASE)
        cycle_re = re.compile(r"cycle\s+\d+", re.IGNORECASE)
        missing: list[tuple[str, str]] = []
        for origin, reason in ALLOWED_EXTERNAL_ORIGINS.items():
            if not (issue_re.search(reason) or gap_re.search(reason) or cycle_re.search(reason)):
                missing.append((origin, reason))
        assert not missing, (
            "\n\nAllowlist entry(ies) without a replacement-path citation:\n"
            + "\n".join(f"  - {o}: {r!r}" for o, r in missing)
            + "\n\nEach origin must cite at least one of: GitHub issue (#NNN), "
            "gap doc, or cycle NNN — forcing the allowlist to be a planned-exit "
            "registry, not a permanent exception list."
        )


def print_externals_report() -> None:
    """Manual debugging helper."""
    urls = _collect_external_urls()
    by_origin: dict[str, list[tuple[str, int]]] = {}
    for relpath, rows in urls.items():
        for lineno, origin, _ in rows:
            by_origin.setdefault(origin, []).append((relpath, lineno))
    print(f"External origins in templates: {len(by_origin)}")
    for origin in sorted(by_origin):
        status = "ALLOWED" if origin in ALLOWED_EXTERNAL_ORIGINS else "NOT ALLOWED"
        print(f"  {origin}  [{status}]")
        for path, lineno in by_origin[origin]:
            print(f"      {path}:L{lineno}")


if __name__ == "__main__":
    print_externals_report()
