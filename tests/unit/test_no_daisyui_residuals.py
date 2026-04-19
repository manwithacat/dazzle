"""Ban DaisyUI utility classes in user-facing Jinja templates.

Dazzle's design-system regime (v0.51+) replaces DaisyUI utility tokens
with `.dz-*` canonical classes + HSL-variable Tailwind arbitrary
values (e.g. ``bg-[hsl(var(--card))]``). DaisyUI CSS is still loaded
as a transitional fallback from `site_base.html` and `base.html`,
but no rendered template should ship DaisyUI class names. This test
fails CI on any reintroduction.

Synthesised in ux-cycle 271 gap doc:
    dev_docs/framework-gaps/2026-04-19-daisyui-residuals-in-
    uncontracted-templates.md
Scope: `src/dazzle_ui/templates/` excluding `reports/` (internal
dev artefact) and excluding any class name starting with `dz-`.

Run standalone:
    pytest tests/unit/test_no_daisyui_residuals.py -v
"""

import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"

# Directories / files exempt from the rule. Each entry is a path
# fragment (substring match against the full path). Add entries only
# with a written justification — every exemption is tracked here for
# auditability.
EXEMPT_PATH_FRAGMENTS: tuple[str, ...] = (
    # Internal dev artefact; the fitness/e2e journey report uses
    # DaisyUI vocabulary extensively (badge, card, stat-card, etc.)
    # but is not user-facing. Decision tracked as open question #1 in
    # dev_docs/framework-gaps/2026-04-19-daisyui-residuals-in-
    # uncontracted-templates.md — revisit when it becomes a friction
    # point.
    "templates/reports/",
)

# DaisyUI tokens banned inside rendered `class="..."` attributes.
# Every entry is a standalone word (matched with \b word boundaries)
# or a prefix followed by `-<suffix>`. The `dz-<word>` canonical
# markers are deliberately NOT in this list — they're the
# replacement, not the ban target. The lint skips any class name
# starting with `dz-`.
#
# Keep this list tight. False positives (HSL var names, URL
# fragments, data-* attribute values, Alpine expressions) are
# filtered before the match runs — see `_extract_class_tokens`.
BANNED_DAISYUI_TOKENS: tuple[str, ...] = (
    # Structural chrome
    "card",
    "card-body",
    "card-title",
    "card-actions",
    # Menus + navigation
    "menu",
    "menu-title",
    "navbar",
    "navbar-start",
    "navbar-center",
    "navbar-end",
    # Buttons
    "btn",
    # Alerts
    "alert",
    # Heros
    "hero",
    "hero-content",
    "hero-overlay",
    # Skeletons
    "skeleton",
    # Badges
    "badge",
    # Dividers + layout separators
    "divider",
    # Links (only the paired usage `link link-<tone>` is DaisyUI —
    # plain `link` is avoided entirely to prevent drift, since HTML
    # anchors don't need a `.link` class)
    "link",
    # Form inputs (bare "input" alone; variants like input-bordered
    # are covered by the input- prefix)
    "input",
    # Collapses (accordion predecessor — framework now uses native
    # <details>/<summary> per parking-lot-primitives contract).
    # Variants (collapse-arrow, collapse-plus) covered by prefix.
    "collapse",
    # Base theme tokens (DaisyUI's theme-aware utilities —
    # framework uses HSL vars directly). bare `text-base-content` +
    # variants `text-base-content/50`, `text-base-content/70`, etc.
    # are covered by the `text-base-content` prefix match.
    "text-base-content",
    # Legacy rounded-box
    "rounded-box",
)


# Variant-prefix tokens — anything starting with one of these and
# followed by a `-` is banned (e.g. `btn-primary`, `alert-warning`,
# `badge-sm`, `menu-horizontal`). Matched separately from the exact
# tokens above.
BANNED_DAISYUI_PREFIXES: tuple[str, ...] = (
    "btn-",
    "alert-",
    "badge-",
    "menu-",
    "card-",
    "hero-",
    "input-",
    "link-",
    "collapse-",
    "bg-base-",
    "text-base-content",
)


# Match quoted class attribute values (both `class="..."` and
# single-quoted variants). The expression tolerates Jinja
# expressions inside the value (they get extracted and skipped).
_CLASS_ATTR_RE = re.compile(
    r"""
    \bclass \s* = \s*
    (?P<q>["'])          # opening quote
    (?P<body>[^"']*)     # body — up to the matching quote
    (?P=q)               # closing quote
    """,
    re.VERBOSE,
)

# Match Jinja {{ ... }} and {% ... %} blocks so we can strip them
# from the class-body before tokenising — token detection inside a
# Jinja expression is noise.
_JINJA_BLOCK_RE = re.compile(r"\{[{%].*?[%}]\}", re.DOTALL)


def _extract_class_tokens(class_body: str) -> list[str]:
    """Split a class-attribute body into individual class tokens.

    Strips Jinja expressions first (they may contain class-like
    substrings that aren't rendered literally), then splits on
    whitespace. Returns the tokens verbatim — no lowercasing.
    """
    stripped = _JINJA_BLOCK_RE.sub(" ", class_body)
    return [tok for tok in stripped.split() if tok]


def _iter_templates() -> list[Path]:
    """Return every `.html` under TEMPLATES_DIR that isn't exempt."""
    out: list[Path] = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        path_str = str(path).replace("\\", "/")
        if any(exempt in path_str for exempt in EXEMPT_PATH_FRAGMENTS):
            continue
        out.append(path)
    return out


def _token_is_banned(token: str) -> bool:
    """Return True if the class token is on the banned list.

    Tokens starting with `dz-` are explicitly allowed (they're the
    canonical replacement). `hsl(var(--*))` lookups inside
    Tailwind arbitrary-value brackets never split across whitespace
    so they can't appear as standalone tokens here — nothing to
    filter. Alpine `:class` bindings aren't caught either because
    they use the `:class` attribute name, not `class`.
    """
    if token.startswith("dz-"):
        return False
    # Exact matches
    if token in BANNED_DAISYUI_TOKENS:
        return True
    # Prefix matches (e.g. `btn-primary`, `badge-sm`)
    for prefix in BANNED_DAISYUI_PREFIXES:
        if token.startswith(prefix) and len(token) > len(prefix):
            return True
    return False


def _find_leaks(template: Path) -> list[tuple[int, str, str]]:
    """Scan a single template and return `(line_no, token, snippet)`
    for every banned class name found inside a `class="..."` attr.
    """
    text = template.read_text(encoding="utf-8")
    leaks: list[tuple[int, str, str]] = []
    for match in _CLASS_ATTR_RE.finditer(text):
        body = match.group("body")
        tokens = _extract_class_tokens(body)
        banned = [t for t in tokens if _token_is_banned(t)]
        if not banned:
            continue
        # 1-indexed line number of the match.
        line_no = text.count("\n", 0, match.start()) + 1
        snippet = f'class="{body[:80]}{"..." if len(body) > 80 else ""}"'
        for token in banned:
            leaks.append((line_no, token, snippet))
    return leaks


# =========================================================================
# Tests
# =========================================================================


def test_templates_dir_exists() -> None:
    """Sanity check: the templates directory can be found. Guards
    against a refactor that relocates `src/dazzle_ui/templates/`
    silently — the lint would otherwise pass trivially with zero
    files scanned."""
    assert TEMPLATES_DIR.is_dir(), f"Missing templates dir: {TEMPLATES_DIR}"
    assert len(list(TEMPLATES_DIR.rglob("*.html"))) > 0, (
        "Templates dir exists but contains no .html files — suspicious"
    )


def test_no_daisyui_classes_in_user_facing_templates() -> None:
    """Fail on any banned DaisyUI class token inside a `class="..."`
    attribute in a user-facing template. See the module docstring
    and BANNED_DAISYUI_TOKENS for the ban list and rationale.
    """
    failures: list[str] = []
    for template in _iter_templates():
        for line_no, token, snippet in _find_leaks(template):
            rel = template.relative_to(TEMPLATES_DIR.parent.parent.parent)
            failures.append(f"  {rel}:{line_no}  `{token}`  {snippet}")

    if failures:
        message = (
            "DaisyUI class residuals found in user-facing templates.\n"
            "Each occurrence uses a banned token from the v0.51 design-system regime.\n"
            "Replace with `.dz-*` canonical markers or HSL-variable Tailwind classes:\n\n"
            + "\n".join(failures)
            + "\n\nSee dev_docs/framework-gaps/2026-04-19-daisyui-residuals-"
            "in-uncontracted-templates.md for context.\n"
        )
        pytest.fail(message)


def test_banned_tokens_and_prefixes_are_disjoint() -> None:
    """Sanity: a token listed as an exact ban should NOT also be a
    prefix ban. Otherwise the two lists duplicate coverage and
    future edits are error-prone."""
    prefix_words = {p.rstrip("-") for p in BANNED_DAISYUI_PREFIXES}
    overlap = set(BANNED_DAISYUI_TOKENS) & prefix_words
    # These tokens appear in BOTH lists deliberately: the bare token
    # AND the prefix-variant are each banned. E.g. both `card` (bare)
    # AND `card-body` (prefix match on `card-`) must fail. That's by
    # design — verify the intentional intersection is exactly these
    # tokens, so a future edit adding an unintended overlap would
    # fail this test.
    expected_overlap = {
        "card",
        "menu",
        "btn",
        "alert",
        "hero",
        "badge",
        "collapse",
        "input",
        "link",
        "text-base-content",
    }
    assert overlap == expected_overlap, (
        f"Unexpected overlap between BANNED_DAISYUI_TOKENS and "
        f"BANNED_DAISYUI_PREFIXES: {overlap - expected_overlap} vs "
        f"expected {expected_overlap}"
    )


def test_exempt_path_fragments_exist() -> None:
    """Sanity: every exempted path fragment actually matches a real
    file in the templates tree. A stale exemption would widen the
    blind spot silently."""
    for fragment in EXEMPT_PATH_FRAGMENTS:
        matches = [
            p for p in TEMPLATES_DIR.rglob("*.html") if fragment in str(p).replace("\\", "/")
        ]
        assert matches, (
            f"Exemption fragment {fragment!r} matches no files — "
            f"either remove the exemption or the referenced files have moved."
        )


def test_dz_prefixed_classes_are_always_allowed() -> None:
    """Sanity: `dz-<anything>` tokens must NOT be flagged, even if
    they happen to contain banned substrings (e.g. `dz-card-header`,
    `dz-menu-item`). Regression guard for the `_token_is_banned`
    prefix check ordering."""
    assert not _token_is_banned("dz-card")
    assert not _token_is_banned("dz-menu-item")
    assert not _token_is_banned("dz-btn-primary")
    assert not _token_is_banned("dz-alert-info")
    # Empty string isn't a token but should be safe.
    assert not _token_is_banned("")


def test_banned_tokens_fire() -> None:
    """Sanity: confirm the detector actually fires on the ban list.
    Catches a regression where the detection logic silently no-ops."""
    for token in ("card", "btn", "menu", "skeleton", "alert"):
        assert _token_is_banned(token), f"{token!r} should be banned"
    for token in ("btn-primary", "badge-sm", "alert-warning"):
        assert _token_is_banned(token), f"{token!r} should be banned"
    # Tailwind arbitrary-value HSL lookups must NOT fire — they're
    # never standalone tokens but verify anyway.
    assert not _token_is_banned("bg-[hsl(var(--card))]")
    assert not _token_is_banned("bg-[hsl(var(--muted))]")
    assert not _token_is_banned("rounded-[6px]")
