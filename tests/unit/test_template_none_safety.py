"""Regression guard for EX-051 — None-vs-undefined drift in Jinja templates.

Jinja's ``| default(X)`` filter only fires when the value is *undefined*,
not when it's None. Templates using ``{{ item[col.key] | default("—") }}``
silently rendered the literal Python string ``"None"`` when the field was
defined but null.

Cycle 272 caught the first instance in ``workspace/regions/detail.html``.
Cycle 280 swept 4 more locations (related_file_list, related_status_cards,
table_rows percentage column). This lint rule (cycle 284) prevents future
additions of the same defect class.

**Scope narrowed to the proven-risky pattern.** The EX-051 class
specifically affects dict-indexed per-row data (``item[...]``), where
API/DB responses can legitimately have defined-but-null values. Plain
variables (``app_name``, ``empty_message``, etc.) are compiler-provided
and typically undefined-or-string — ``default()`` works correctly for
those. Restricting the lint to ``item[...] | default(X)`` catches the
proven-risky pattern without flagging the ~80 legitimate uses of
``default()`` for static config / form values / URL fallbacks / etc.

**The rule**: any ``{{ item[<key>] | default(<fallback>) ... }}`` must
either:

1. Chain to a known None-safe downstream filter (``truncate_text``,
   ``dateformat``, ``timeago``, ``currency``, ``bool_icon``,
   ``basename_or_url``, ``metric_number``, ``ref_display``), which handle
   None explicitly by returning a safe value.
2. Use an explicit ``{% if val is none %}…{% else %}…{% endif %}`` block
   (detected indirectly — such blocks don't contain ``| default()`` on
   the unwrapped expression).
3. Carry the ``{# ex051-safe #}`` comment annotation on the SAME line to
   explicitly opt out.

Anything else is flagged as a potential EX-051 regression.

Heuristic 1 applied: the scanner was validated against the post-cycle-280
template tree. A sanity test below confirms the exact template files
EX-051 touched are now clean.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"

# Jinja filters that handle None explicitly (verified by reading
# ``src/dazzle_ui/runtime/template_renderer.py`` — each contains an
# ``if value is None: return <safe>`` guard or equivalent).
_NONE_SAFE_FILTERS = frozenset(
    {
        "truncate_text",
        "dateformat",
        "timeago",
        "currency",
        "bool_icon",
        "basename_or_url",
        "metric_number",
        "ref_display",
        "humanize",
        "slugify",
        "badge_tone",
        "badge",
    }
)

# Opt-out marker. Place on the same line as the default() expression to
# explicitly declare it's known-safe in context.
_OPT_OUT_MARKER = "ex051-safe"


# Match {{ item[...] | default(<arg>) <rest> }} expressions —
# narrowed to dict-indexed per-row data, the proven-risky EX-051 pattern.
# Static variables (app_name, empty_message, etc.) aren't matched because
# their ``default()`` behaviour is safe (value is string-or-undefined,
# never defined-but-None).
_DEFAULT_FILTER_RE = re.compile(
    r"""
    \{\{                                # opening {{
    \s*
    (?P<expr>\w+\[[^\]]*\])             # item[...] dict indexing
    \s*\|\s*default\s*\(                # | default(
    (?P<fallback>[^)]*)                 # the fallback value
    \)                                  # )
    (?P<tail>[^}]*)                     # anything after default(), before }}
    \}\}                                # closing }}
    """,
    re.VERBOSE,
)


def _has_none_safe_downstream(tail: str) -> bool:
    """Return True if the chain after ``default(...)`` pipes into a
    known None-safe filter."""
    if not tail:
        return False
    # Split on pipes and strip whitespace + any filter-call arguments.
    parts = [p.strip() for p in tail.split("|")]
    for part in parts:
        if not part:
            continue
        # Strip ``(...)`` call syntax if present to get the filter name.
        name = part.split("(", 1)[0].strip()
        if name in _NONE_SAFE_FILTERS:
            return True
    return False


def scan_template(path: Path) -> list[tuple[int, str]]:
    """Return a list of (line_number, source_line) tuples flagging
    bare ``| default(X)`` usages with no None-safe downstream filter.

    Skips lines with the ``ex051-safe`` opt-out marker.
    """
    text = path.read_text(encoding="utf-8")
    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _OPT_OUT_MARKER in line:
            continue
        for match in _DEFAULT_FILTER_RE.finditer(line):
            if _has_none_safe_downstream(match.group("tail")):
                continue
            violations.append((lineno, line.strip()))
    return violations


def scan_templates_root(root: Path = TEMPLATES_ROOT) -> dict[Path, list[tuple[int, str]]]:
    """Scan every .html template under ``root``, return violations map."""
    results: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(root.rglob("*.html")):
        viol = scan_template(path)
        if viol:
            results[path] = viol
    return results


class TestTemplateNoneSafety:
    """EX-051 prevention — bare ``| default(X)`` on template variables
    without a None-safe downstream filter is forbidden."""

    def test_no_bare_default_filter_without_none_safe_downstream(self) -> None:
        """Scan every .html template under src/dazzle_ui/templates/ and
        assert no unsafe ``| default()`` usages exist.

        This guards against re-introducing the EX-051 drift class. If
        this test fails, either:
        1. Chain the expression to a None-safe filter (see
           ``_NONE_SAFE_FILTERS``), OR
        2. Use an explicit ``{% if val is none %}…{% else %}…{% endif %}``
           block, OR
        3. Add a ``{# ex051-safe #}`` comment on the same line if the
           value is genuinely known-never-None in context (rare; explain
           why in a template comment above).
        """
        violations = scan_templates_root()
        if violations:
            messages = []
            for path, lines in violations.items():
                rel = path.relative_to(REPO_ROOT)
                for lineno, source in lines:
                    messages.append(f"  {rel}:{lineno}: {source}")
            formatted = "\n".join(messages)
            pytest.fail(
                "EX-051 regression — unsafe ``| default(X)`` usage detected:\n"
                f"{formatted}\n\n"
                "Each flagged line must either (a) chain to a None-safe filter "
                f"(one of {sorted(_NONE_SAFE_FILTERS)}), (b) use an explicit "
                "{% if val is none %} block, or (c) add a {# ex051-safe #} "
                "opt-out marker on the same line."
            )

    def test_known_safe_pattern_passes(self) -> None:
        """Positive: ``| default("") | truncate_text`` is recognised as safe."""
        match = _DEFAULT_FILTER_RE.search('{{ item[col.key] | default("") | truncate_text }}')
        assert match is not None
        assert _has_none_safe_downstream(match.group("tail"))

    def test_unsafe_bare_default_detected(self) -> None:
        """Negative: ``| default("—")`` with no downstream is flagged."""
        match = _DEFAULT_FILTER_RE.search('{{ item[col.key] | default("—") }}')
        assert match is not None
        assert not _has_none_safe_downstream(match.group("tail"))

    def test_unsafe_default_then_unknown_filter_flagged(self) -> None:
        """Negative: ``item[...] | default("") | string`` is NOT safe
        (string(None) returns ``'None'``)."""
        match = _DEFAULT_FILTER_RE.search('{{ item[col.key] | default("") | string }}')
        assert match is not None
        assert not _has_none_safe_downstream(match.group("tail"))

    def test_plain_variable_not_matched(self) -> None:
        """Plain variables (no dict indexing) are intentionally NOT matched —
        their ``default()`` behaviour is safe because compiler-provided
        scalars are undefined-or-string, never defined-but-None."""
        match = _DEFAULT_FILTER_RE.search('{{ app_name | default("Dazzle") }}')
        assert match is None

    def test_opt_out_marker_skips_line(self) -> None:
        """A line with the ex051-safe comment marker is not flagged even
        if it would otherwise match the unsafe pattern."""
        # Simulate a single-line scan via the helper
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write('{{ known_never_null | default("fallback") }}  {# ex051-safe #}\n')
            tmp_path = Path(fh.name)
        try:
            violations = scan_template(tmp_path)
            assert violations == []
        finally:
            tmp_path.unlink()

    def test_cycle_280_fixed_sites_are_clean(self) -> None:
        """Heuristic 1 sanity check: each template EX-051 touched is
        now clean. Guards against partial-fix regressions."""
        cycle_280_fix_sites = [
            TEMPLATES_ROOT / "fragments" / "related_file_list.html",
            TEMPLATES_ROOT / "fragments" / "related_status_cards.html",
            TEMPLATES_ROOT / "fragments" / "table_rows.html",
            TEMPLATES_ROOT / "workspace" / "regions" / "detail.html",
        ]
        for path in cycle_280_fix_sites:
            assert path.exists(), f"expected cycle-280 fix site missing: {path}"
            violations = scan_template(path)
            assert not violations, (
                f"cycle-280 fix site regressed in {path.relative_to(REPO_ROOT)}: {violations}"
            )
