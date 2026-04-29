"""Regression: any template that interpolates user-provided values into a JS
string literal inside an HTML attribute must use ``| tojson`` rather than
``| e`` followed by hand-quoting. ``| e`` only HTML-escapes apostrophes
(``'`` becomes ``&#39;``), and the browser HTML-decodes the entity back to
``'`` before Alpine sees the attribute value — terminating the surrounding
JS string literal mid-word and breaking the binding for any record whose
value contains an apostrophe (e.g. ``O'Brien``).

Surfaced when Aegismark's QA tester crawled teacher routes and observed JS
warnings on recommendation rows containing names like ``O'Brien``. The
inline-edit cell broke for those records because the ``:value`` binding
evaluated to ``'O'Brien'`` — a JS syntax error.

These tests are source-level grep assertions over the template files (no
rendering) so they don't depend on a Jinja runtime in the test process.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates"


# Files that interpolate dynamic per-record values into inline JS attributes
# and must use ``| tojson`` rather than ``'{{ X | e }}'`` for safety.
DYNAMIC_INLINE_JS_TEMPLATES = [
    "fragments/inline_edit.html",
    "macros/form_field.html",
]


def _read(template_relpath: str) -> str:
    return (TEMPLATES_DIR / template_relpath).read_text()


# Pattern: a single-quoted JS string literal containing an HTML-escaped
# Jinja interpolation — the broken pattern. Matches things like:
#   '{{ edit_value | e }}'
#   '{{ value | escape }}'
#   '{{ user.name | e }}'
_BROKEN_PATTERN = re.compile(
    r"'\{\{[^{}]*\|\s*(?:e|escape)\s*\}\}'",
    re.IGNORECASE,
)


class TestInlineJsQuoteSafety:
    @pytest.mark.parametrize("template_relpath", DYNAMIC_INLINE_JS_TEMPLATES)
    def test_no_html_escape_inside_js_string_literal(self, template_relpath):
        """Templates listed in ``DYNAMIC_INLINE_JS_TEMPLATES`` must not contain
        the ``'{{ X | e }}'`` anti-pattern. Use ``{{ X | tojson }}`` (no
        surrounding quotes — tojson includes them, properly JS-escaped) and
        switch the outer attribute to single-quoted to avoid clashing with
        tojson's ``"`` delimiters."""
        source = _read(template_relpath)
        matches = _BROKEN_PATTERN.findall(source)
        assert not matches, (
            f"{template_relpath} contains the broken JS-string interpolation "
            f"pattern. ``| e`` HTML-escapes apostrophes to ``&#39;``, which "
            f"the browser decodes back to ``'`` — terminating the JS string "
            f"and breaking Alpine bindings for any record whose value contains "
            f"an apostrophe (e.g. O'Brien). Use ``{{ X | tojson }}`` and a "
            f"single-quoted outer attribute. Matches: {matches}"
        )

    def test_inline_edit_uses_tojson_for_value(self):
        """inline_edit.html: both the text and date input branches must use
        ``| tojson`` for the :value binding — not the broken ``'{{ ... | e }}'``
        pattern that triggered the original report."""
        source = _read("fragments/inline_edit.html")
        # Two :value lines (text branch + date branch) — each must use tojson
        value_lines = [line for line in source.splitlines() if ":value" in line]
        assert len(value_lines) == 2, (
            f"Expected 2 :value lines in inline_edit.html (text + date branches); "
            f"found {len(value_lines)}: {value_lines}"
        )
        for line in value_lines:
            assert "tojson" in line, f"Expected `| tojson` in :value line, got: {line.strip()}"
            assert "| e }}" not in line, (
                f"Found legacy `| e` HTML-escape in JS-string position: {line.strip()}"
            )

    def test_search_select_wrapper_carries_widget_decorator(self):
        """Closes #878: the search_select fragment must stamp
        ``data-dz-widget="search_select"`` on its wrapper div so the fidelity
        scorer's `_iter_inputs_with_widget_context` can attribute the widget
        kind to the inner hidden input. Without this marker the structural
        check raises a false-positive INCORRECT_INPUT_TYPE for every str
        field rendered through `source=...`."""
        source = _read("fragments/search_select.html")
        assert 'data-dz-widget="search_select"' in source, (
            "fragments/search_select.html must carry the "
            'data-dz-widget="search_select" marker on its wrapper div — '
            "otherwise the fidelity scorer can't recognise the hidden+text "
            "composite as a search_select widget (see #878)."
        )

    def test_form_field_file_upload_uses_tojson_for_filename(self):
        """form_field.html file branch: x-init filename must be tojson-encoded
        so apostrophes in filenames don't break Alpine initialisation."""
        source = _read("macros/form_field.html")
        # Find x-init lines that set filename (file upload branch)
        filename_init_lines = [
            line for line in source.splitlines() if "x-init" in line and "filename" in line
        ]
        assert filename_init_lines, (
            "Could not find the file-upload x-init filename line; if the "
            "template was refactored, update the test to point at the new "
            "location."
        )
        for line in filename_init_lines:
            assert "tojson" in line, (
                f"Expected `| tojson` in file-upload filename x-init, got: {line.strip()}"
            )
