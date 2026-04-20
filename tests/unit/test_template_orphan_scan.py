"""Template orphan scan — prevents dormant templates accumulating silently.

Cycle 302 — promotes the `orphan_lint_rule` candidate raised in cycle
287's `PR #600 dormant Alpine primitives` gap doc. Walks every template
in `src/dazzle_ui/templates/`, builds the set of statically-referenced
paths (via `{% include %}`, `{% extends %}`, `{% import %}`,
`{% from %}`, and Python `render_template` / `get_template` /
string-literal references), and asserts that any unreferenced template
appears in an explicit allowlist.

This scanner SURFACES orphans early. The allowlist is the
single-source-of-truth for "dormant by design" vs. "regression".
Adding a new orphan without allowlisting it will fail this test. Old
allowlist entries that become referenced (reason goes stale) must be
removed — the test also catches that.

Dynamic-dispatch whole-directory exemptions:
- `site/sections/` — rendered via `{% include [prefix + section.type + suffix] %}`
  in `site/page.html:15,18`. Every section template is reachable this
  way; listing individually would be noise.
- `reports/` — rendered via `env.get_template("reports/<name>.html")`
  in `src/dazzle/agent/journey_reporter.py`.

Individually-allowlisted orphans carry a one-line reason + cross-ref.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"
DAZZLE_UI_ROOT = REPO_ROOT / "src" / "dazzle_ui"
DAZZLE_BACK_ROOT = REPO_ROOT / "src" / "dazzle_back"
DAZZLE_CORE_ROOT = REPO_ROOT / "src" / "dazzle"


# Whole directories whose templates are loaded via dynamic-dispatch
# from a documented consumer. Templates under these prefixes are
# EXCLUDED from orphan reporting entirely.
DYNAMIC_DIRECTORY_EXEMPTIONS: dict[str, str] = {
    "site/sections/": (
        "Dynamic-dispatch include in site/page.html:15,18,26 — "
        "'site/sections/' + section.type + '.html'"
    ),
    "reports/": ("Dynamic get_template() in src/dazzle/agent/journey_reporter.py:23"),
}

# Specific files that are genuinely unreferenced but intentionally
# shipped — dormant primitives, orphans with pending investigations,
# or framework scaffolding without production consumers.
#
# Each entry MUST include a reason citing a gap doc, EX row, or
# contract. If an entry's reason goes stale (the template BECOMES
# referenced), this test fails and forces removal.
INDIVIDUAL_ALLOWLIST: dict[str, str] = {
    # Dormant Alpine primitives from PR #600 — awaiting user direction.
    # See dev_docs/framework-gaps/2026-04-20-pr600-dormant-alpine-primitives.md
    # (cycles 286+287 discovery).
    "components/alpine/confirm_dialog.html": (
        "Dormant Alpine primitive; PR #600; cycle 287 gap doc"
    ),
    # Dormant building-blocks with ux-architect contracts but no
    # production consumer. Same class as the PR #600 primitives.
    "components/modal.html": (
        "Dormant building-block with contract (modal.md); no production consumer"
    ),
    "components/island.html": (
        "Dormant building-block with contract (island.md, UX-059); "
        "IslandContext dataclass wired but no template include"
    ),
    # 2FA page templates — NO Python route renders these as HTML pages.
    # Only /auth/2fa/* JSON API endpoints exist in routes_2fa.py.
    # Surfaced cycle 302 orphan_lint scan. Filing EX-055 for
    # finding_investigation to determine: is the feature broken at the
    # page level, OR is there a mechanism the scan missed?
    "site/auth/2fa_challenge.html": "EX-055 (cycle 302) — no page route found",
    "site/auth/2fa_setup.html": "EX-055 (cycle 302) — no page route found",
    "site/auth/2fa_settings.html": "EX-055 (cycle 302) — no page route found",
}


def _collect_all_templates() -> set[str]:
    """Every .html file under templates/ as a relative path."""
    return {p.relative_to(TEMPLATES_ROOT).as_posix() for p in TEMPLATES_ROOT.rglob("*.html")}


_INCLUDE_RE = re.compile(r'{%\s*(?:include|extends|import|from)\s+["\']([^"\']+)["\']')
_PY_TEMPLATE_STRING_RE = re.compile(r'["\']([a-zA-Z_][a-zA-Z0-9_/]*\.html)["\']')


def _collect_referenced_paths() -> set[str]:
    """Scan all template + Python sources for template path references.

    Recognises:
    - `{% include/extends/import/from "path" %}` in templates
    - `'path.html'` or `"path.html"` string literals in Python

    Does NOT attempt to resolve dynamic string concatenation — the
    `DYNAMIC_DIRECTORY_EXEMPTIONS` table covers those cases.
    """
    referenced: set[str] = set()
    # Scan templates
    for p in TEMPLATES_ROOT.rglob("*.html"):
        text = p.read_text()
        for m in _INCLUDE_RE.finditer(text):
            referenced.add(m.group(1))
    # Scan Python across all three src subtrees
    for root in (DAZZLE_UI_ROOT, DAZZLE_BACK_ROOT, DAZZLE_CORE_ROOT):
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            text = p.read_text()
            for m in _PY_TEMPLATE_STRING_RE.finditer(text):
                referenced.add(m.group(1))
    return referenced


def _under_dynamic_dir(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in DYNAMIC_DIRECTORY_EXEMPTIONS)


def _compute_orphans() -> set[str]:
    all_templates = _collect_all_templates()
    referenced = _collect_referenced_paths()
    # An orphan is a template that:
    #   (a) is not directly referenced
    #   (b) is not under a dynamic-dispatch directory
    return {t for t in all_templates if t not in referenced and not _under_dynamic_dir(t)}


class TestTemplateOrphanScan:
    """Surface orphaned templates; pin the allowlist as source-of-truth.

    Two gates: (1) every orphan is allowlisted; (2) every allowlist
    entry IS an orphan (no stale reasons).
    """

    def test_every_orphan_is_allowlisted(self) -> None:
        """New orphans require an allowlist entry with a documented reason."""
        orphans = _compute_orphans()
        unallowed = orphans - INDIVIDUAL_ALLOWLIST.keys()
        assert not unallowed, (
            "\n\nTemplate(s) with no production consumer found:\n"
            + "\n".join(f"  - {t}" for t in sorted(unallowed))
            + "\n\nEither wire them up in a template/Python consumer, "
            "OR add them to INDIVIDUAL_ALLOWLIST with a reason citing "
            "a gap doc, EX row, or contract."
        )

    def test_every_allowlist_entry_is_still_orphaned(self) -> None:
        """Stale allowlist entries (now referenced) must be removed."""
        orphans = _compute_orphans()
        stale = INDIVIDUAL_ALLOWLIST.keys() - orphans
        # Also check templates that moved under a dynamic-dispatch directory
        # — those shouldn't be in the allowlist either.
        stale_dynamic = {t for t in INDIVIDUAL_ALLOWLIST if _under_dynamic_dir(t)}
        stale = stale | stale_dynamic
        assert not stale, (
            "\n\nAllowlist entries that are now referenced (reason is stale):\n"
            + "\n".join(f"  - {t}  # was: {INDIVIDUAL_ALLOWLIST[t]}" for t in sorted(stale))
            + "\n\nRemove these from INDIVIDUAL_ALLOWLIST — they're no longer orphaned."
        )

    def test_allowlist_entries_exist_as_template_files(self) -> None:
        """Allowlist must point at real templates, not hypothetical paths."""
        all_templates = _collect_all_templates()
        nonexistent = INDIVIDUAL_ALLOWLIST.keys() - all_templates
        assert not nonexistent, (
            "\n\nAllowlist entries that don't exist as templates:\n"
            + "\n".join(f"  - {t}" for t in sorted(nonexistent))
        )

    def test_dynamic_directory_exemptions_are_real_directories(self) -> None:
        """Every dynamic-dir prefix must correspond to at least one real template."""
        all_templates = _collect_all_templates()
        for prefix in DYNAMIC_DIRECTORY_EXEMPTIONS:
            matching = [t for t in all_templates if t.startswith(prefix)]
            assert matching, (
                f"DYNAMIC_DIRECTORY_EXEMPTIONS[{prefix!r}] matches zero templates; remove it."
            )

    def test_every_allowlist_entry_has_non_empty_reason(self) -> None:
        """Governance: reasons cite evidence, not vibes."""
        for path, reason in INDIVIDUAL_ALLOWLIST.items():
            assert reason.strip(), f"Empty reason for allowlist entry {path}"
            # Lightweight sanity: reason should reference some evidence
            assert len(reason) > 20, (
                f"Reason for {path} is too short ({len(reason)} chars) — "
                f"cite a gap doc, EX row, contract, or cycle number"
            )


# Informational helper for manual debugging (not a test itself)
def print_orphan_report() -> None:
    """Print human-readable orphan report — useful when extending the allowlist."""
    all_templates = _collect_all_templates()
    referenced = _collect_referenced_paths()
    orphans = _compute_orphans()
    dynamic_dir_templates = {t for t in all_templates if _under_dynamic_dir(t)}
    print(f"total templates:       {len(all_templates)}")
    print(f"referenced (direct):   {len(all_templates & referenced)}")
    print(f"covered by dyn-dir:    {len(dynamic_dir_templates)}")
    print(f"orphans (unallowed):   {len(orphans - INDIVIDUAL_ALLOWLIST.keys())}")
    print(f"orphans (allowed):     {len(orphans & INDIVIDUAL_ALLOWLIST.keys())}")
    unallowed = sorted(orphans - INDIVIDUAL_ALLOWLIST.keys())
    if unallowed:
        print("\nUnallowed orphans:")
        for t in unallowed:
            print(f"  {t}")


if __name__ == "__main__":
    # Manual debugging: `python tests/unit/test_template_orphan_scan.py`
    print_orphan_report()
