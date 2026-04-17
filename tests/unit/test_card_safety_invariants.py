"""Meta-test linking each card-safety invariant to its named enforcement.

The canonical spec is ``docs/reference/card-safety-invariants.md``.
This file asserts each invariant has a concrete, named test that
guards it — so the spec and the test suite can't silently drift
apart. If you rename a test referenced here, update the spec doc AND
this mapping in the same commit.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests" / "unit"

# Explicit allowlist of test modules that INVARIANT_ENFORCERS may
# reference. Each maps to a file path relative to ``tests/unit/``.
# We grep the source file for the named class/method — no import, no
# dynamic resolution, no user-input path. To add a new enforcer test,
# register its module file here.
_ALLOWED_MODULE_FILES: dict[str, str] = {
    "test_ux_contract_checker": "test_ux_contract_checker.py",
    "test_template_html": "test_template_html.py",
    "test_htmx_workspace_composite": "test_htmx_workspace_composite.py",
    "test_card_safety_invariants": "test_card_safety_invariants.py",
}


# INV-N → list of ``(test_module, test_class_name, test_name)`` tuples
# that enforce the invariant. The test_name lookup uses string
# comparison rather than attribute access so we don't depend on test
# internals — if pytest discovers the function, the name exists.
INVARIANT_ENFORCERS: dict[str, list[tuple[str, str, str]]] = {
    "INV-1: no nested card chrome": [
        (
            "test_ux_contract_checker",
            "TestFindNestedChromes",
            "test_detects_rounded_plus_border_nested",
        ),
        (
            "test_template_html",
            "TestDashboardRegionCompositeShapes",
            "test_composite_has_no_nested_chrome",
        ),
    ],
    "INV-2: no duplicate title within a card": [
        (
            "test_ux_contract_checker",
            "TestFindDuplicateTitlesInCards",
            "test_detects_duplicate_title_in_nested_cards",
        ),
        (
            "test_template_html",
            "TestDashboardRegionCompositeShapes",
            "test_composite_has_no_duplicate_titles",
        ),
    ],
    "INV-3: side borders are accents, not card edges": [
        ("test_ux_contract_checker", "TestFindNestedChromes", "test_side_border_is_not_chrome"),
    ],
    "INV-4: bg-only rounded is not chrome": [
        ("test_ux_contract_checker", "TestFindNestedChromes", "test_ignores_bg_only_rounded"),
    ],
    "INV-5: inline tags are never cards": [
        # The scanner's _CARD_CANDIDATE_TAGS frozenset excludes inline
        # tags by construction; coverage is implicit in every composite
        # test that contains inline tags with chrome-shaped classes
        # (status badges, buttons). The assertion below verifies the
        # set itself.
        (
            "test_card_safety_invariants",
            "TestCardSafetyInvariants",
            "test_inv5_scanner_excludes_inline_tags",
        ),
    ],
    "INV-6: region templates emit zero chrome": [
        (
            "test_template_html",
            "TestDashboardRegionCompositeShapes",
            "test_bare_region_card_macro_stays_bare",
        ),
        (
            "test_template_html",
            "TestDashboardRegionCompositeShapes",
            "test_composite_has_no_nested_chrome",
        ),
    ],
    "INV-7: region templates emit zero title": [
        (
            "test_template_html",
            "TestDashboardRegionCompositeShapes",
            "test_composite_has_no_duplicate_titles",
        ),
    ],
    "INV-8: tests must run on the composite": [
        (
            "test_htmx_workspace_composite",
            "TestAssembleWorkspaceComposite",
            "test_composite_catches_nested_chrome",
        ),
    ],
}


def _test_exists(module_name: str, class_name: str, test_name: str) -> bool:
    """Return True if the named test exists in the given module/class.

    We grep the test file for ``class {class_name}`` followed by
    ``def {test_name}`` (anywhere after, in the same file). This
    doesn't execute the test code and doesn't resolve any name
    dynamically — the file list is a static allowlist.
    """
    filename = _ALLOWED_MODULE_FILES.get(module_name)
    if filename is None:
        return False
    path = TESTS_DIR / filename
    if not path.is_file():
        return False
    text = path.read_text()
    class_marker = f"class {class_name}"
    class_idx = text.find(class_marker)
    if class_idx == -1:
        return False
    # Match the test method anywhere in the file after the class
    # heading. An intervening class definition could technically
    # shadow, but that's not a pattern we use — and pytest would
    # collect both anyway.
    return re.search(rf"\bdef\s+{re.escape(test_name)}\s*\(", text[class_idx:]) is not None


class TestCardSafetyInvariants:
    """Each invariant in docs/reference/card-safety-invariants.md must
    have at least one named test enforcing it. If an invariant is
    removed, drop it from INVARIANT_ENFORCERS AND the spec doc in
    the same commit.
    """

    def test_every_invariant_has_enforcing_tests(self) -> None:
        missing: list[tuple[str, str]] = []
        for invariant, enforcers in INVARIANT_ENFORCERS.items():
            for module_name, class_name, test_name in enforcers:
                full = f"{module_name}.{class_name}.{test_name}"
                if not _test_exists(module_name, class_name, test_name):
                    missing.append((invariant, full))
        assert not missing, (
            "Some invariants name tests that don't exist — the spec and "
            "the test suite have drifted. Fix by renaming the test back, "
            "updating the INVARIANT_ENFORCERS mapping, or removing the "
            "invariant from the spec.\n" + "\n".join(f"  - {inv}: {t}" for inv, t in missing)
        )

    def test_spec_doc_exists(self) -> None:
        spec = REPO_ROOT / "docs" / "reference" / "card-safety-invariants.md"
        assert spec.is_file(), (
            f"Card-safety spec missing at {spec}. Either restore it or "
            "delete this meta-test — the invariants are load-bearing."
        )

    def test_spec_doc_references_every_listed_invariant(self) -> None:
        spec_text = (REPO_ROOT / "docs" / "reference" / "card-safety-invariants.md").read_text()
        # The doc lists invariants as "### INV-N: ...". Every key in
        # INVARIANT_ENFORCERS must appear in an INV-N heading.
        missing_from_doc = []
        for invariant in INVARIANT_ENFORCERS:
            # invariant like "INV-1: no nested card chrome" — just the
            # ID prefix needs to appear in a heading.
            inv_id = invariant.split(":", 1)[0].strip()
            if f"### {inv_id}:" not in spec_text:
                missing_from_doc.append(inv_id)
        assert not missing_from_doc, (
            f"INVARIANT_ENFORCERS references invariants not documented "
            f"in the spec: {missing_from_doc}. Add them to "
            f"docs/reference/card-safety-invariants.md or remove from "
            f"the mapping."
        )

    def test_inv5_scanner_excludes_inline_tags(self) -> None:
        """INV-5 self-enforcer: the scanner's block-container set
        explicitly excludes inline tags. A status-badge span with
        chrome-shaped classes inside a card must not count as nested
        chrome.
        """
        from dazzle.testing.ux.contract_checker import (
            _NestedChromeScanner,
            find_nested_chromes,
        )

        # Block-container set must not leak inline tags.
        for inline in ("span", "button", "a", "input", "td", "label"):
            assert inline not in _NestedChromeScanner._CARD_CANDIDATE_TAGS, (
                f"Inline tag {inline!r} leaked into _CARD_CANDIDATE_TAGS — "
                f"pills and badges will now falsely count as cards. INV-5 broken."
            )

        # Positive behavioural check: a span with chrome classes inside
        # a chrome article must not register as a nested chrome pair.
        html = (
            '<article class="rounded-md border bg-white">'
            '<span class="rounded-full border bg-primary px-2">status</span>'
            "</article>"
        )
        assert find_nested_chromes(html) == []
