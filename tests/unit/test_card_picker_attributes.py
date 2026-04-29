"""Tests for #949 — workspace card-picker attribute quoting.

Cycle 1 of #948 introduced a regression: the picker's @click attribute
was emitted as `@click="addCard({{ item.name | tojson }})"`. With
`tojson` returning a JSON-quoted string (e.g. `"ingestion_journey"`),
the inner `"` terminated the surrounding double-quoted attribute and
the rest of the expression became a garbage attribute name.

Fix: single-quote the @click attribute so the inner double quotes
sit inside without conflict.

This module pins the contract source-side AND end-to-end via a
rendered-HTML check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PICKER_PATH = REPO_ROOT / "src/dazzle_ui/templates/workspace/_card_picker.html"


class TestPickerAttributeQuoting:
    def test_at_click_uses_single_quotes(self) -> None:
        """Inner `"` from `tojson` would otherwise terminate the
        attribute prematurely. Single-quoting is the framework's
        convention for Alpine attributes that may contain double
        quotes."""
        source = PICKER_PATH.read_text()
        assert "@click='addCard(" in source, (
            "Picker @click must be single-quoted to survive the "
            "double-quoted JSON from `tojson`. Pre-#949 used "
            '`@click="addCard({{ ... | tojson }})"` which emitted '
            "broken HTML."
        )

    def test_no_double_quoted_at_click_with_tojson(self) -> None:
        """The bug's source-side signature: a double-quoted attribute
        containing a `tojson` filter on the value side."""
        source = PICKER_PATH.read_text()
        # Search for the broken pattern; should not exist anywhere.
        broken = re.search(r'@click="[^"]*\|\s*tojson\s*\}\}', source)
        assert broken is None, (
            "Found a double-quoted @click that interpolates `tojson` "
            "— this is the #949 bug pattern. Switch to single quotes."
        )


class TestPickerRenderedHtml:
    """Render the picker against a fake catalog and verify the
    resulting attributes parse correctly. This catches the bug
    end-to-end the way the production browser sees it."""

    @pytest.fixture
    def jinja_env(self):
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        return create_jinja_env()

    def _render(self, jinja_env, catalog):
        tmpl = jinja_env.get_template("workspace/_card_picker.html")
        # Render an Alpine-like x-data wrapper so the @click attribute
        # appears in a complete document. The picker is normally
        # included from `_content.html` inside a `dzDashboardBuilder()`
        # root. For this test we just feed `catalog`; the @click
        # markup is what we check.
        return tmpl.render(catalog=catalog, showPicker=True)  # nosemgrep: direct-use-of-jinja2

    def test_at_click_attribute_is_complete(self, jinja_env) -> None:
        """The rendered HTML must have a complete @click attribute
        per button — no premature attribute termination, no garbage
        attribute names trailing the JSON value."""
        catalog = [
            {
                "name": "ingestion_journey",
                "title": "Ingestion Journey",
                "display": "LIST",
                "entity": "Manuscript",
            },
            {
                "name": "metrics",
                "title": "Metrics",
                "display": "METRICS",
                "entity": "Invoice",
            },
        ]
        html = self._render(jinja_env, catalog)

        # Each button should carry an @click whose value is a complete
        # `addCard("...")` expression. The pre-#949 bug emitted
        # `@click="addCard("` with the rest as garbage attributes.
        # Match on the single-quoted form, the post-fix shape.
        matches = re.findall(r"@click='(addCard\(\"[^\"]+\"\))'", html)
        assert len(matches) == len(catalog), (
            f"Expected {len(catalog)} complete @click expressions, got "
            f"{len(matches)}: {matches!r}\n\n"
            f"Rendered HTML:\n{html}"
        )

    def test_at_click_argument_matches_region_name(self, jinja_env) -> None:
        """The JSON-encoded argument must exactly match the catalog
        entry's name. If escaping is wrong the argument may be
        truncated or contain stray escape sequences."""
        catalog = [
            {
                "name": "ingestion_journey",
                "title": "Ingestion",
                "display": "LIST",
                "entity": "Manuscript",
            },
        ]
        html = self._render(jinja_env, catalog)
        assert 'addCard("ingestion_journey")' in html

    def test_no_garbage_attributes_after_at_click(self, jinja_env) -> None:
        """The pre-#949 bug emitted a fragment like
        `@click=\"addCard(\" ingestion_journey\")\" data-test-id=...`
        — the `ingestion_journey")"` substring landed as a malformed
        attribute name. Verify no such substring appears in the
        rendered output."""
        catalog = [
            {
                "name": "ingestion_journey",
                "title": "Ingestion",
                "display": "LIST",
                "entity": "Manuscript",
            },
        ]
        html = self._render(jinja_env, catalog)
        # The garbage-attribute signature: a literal region name
        # followed by `")"`. With the fix, the only place
        # `ingestion_journey")` appears is INSIDE the @click value.
        # The bug puts it OUTSIDE (as an attribute name).
        # Assert the literal pre-fix shape is absent:
        assert ' ingestion_journey")' not in html
        assert ' ingestion_journey")"' not in html
