"""Source-level contract tests for the widget bridge (#940).

The dz-component-bridge mounts vendor instances on
``htmx:afterSettle`` and unmounts on ``beforeSwap``. When a node
*also* carries an Alpine ``x-data`` directive, three lifecycles
converge on it: idiomorph (DOM identity), Alpine (reactive state),
the vendor (DOM mutation). That's the wrapper-on-wrapper smell that
hit us at #927 and was removed at the source by #939. This test
prevents the pattern from re-appearing as new widgets are added.

The check is purely lexical — it scans every ``.html`` template in
``src/dazzle_ui/templates`` for any element that has BOTH
``data-dz-widget`` and ``x-data`` attributes. Either is fine on its
own; the framework just shouldn't run two reactive controllers over
the same DOM node.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates"

# Widget kinds that mount a *vendor* instance via the bridge —
# combining these with ``x-data`` on the same node is the lifecycle
# contention the contract forbids. The fidelity scorer also writes
# ``data-dz-widget`` on pure-Alpine markers like ``search_select`` for
# attribution purposes (no bridge handler), so the check needs a
# specific allowlist rather than matching the attribute as a whole.
#
# Update this set when ``dz-widget-registry.js`` registers a new
# vendor-mounting handler. Pure-Alpine markers (no
# ``registerWidget(...)`` call) stay out of the set.
_BRIDGE_MOUNTED_WIDGET_KINDS = frozenset(
    {
        "combobox",
        "multiselect",
        "tags",
        "datepicker",
        "daterange",
        "colorpicker",
        "richtext",
        "range-tooltip",
    }
)

# An "element opening tag" is `<` ... `>` with no nested `<` or `>`.
# We're searching for tags only — Jinja blocks like ``{% if … %}``
# don't appear inside an HTML attribute list because they'd terminate
# the tag string. This keeps the regex small and predictable.
_ELEMENT_TAG_RE = re.compile(r"<[a-zA-Z][^<>]*>", re.DOTALL)
_DATA_DZ_WIDGET_VALUE_RE = re.compile(r"""\bdata-dz-widget\s*=\s*['"]([^'"]+)['"]""")
_X_DATA_RE = re.compile(r"\bx-data\s*=")


def _find_dual_lifecycle_elements() -> list[tuple[Path, str, str]]:
    """Return every (template_path, widget_kind, opening_tag) where
    an element declares both ``x-data`` and a ``data-dz-widget`` whose
    kind mounts a vendor instance via the bridge."""
    findings: list[tuple[Path, str, str]] = []
    for template in sorted(TEMPLATES_DIR.rglob("*.html")):
        text = template.read_text(encoding="utf-8")
        for match in _ELEMENT_TAG_RE.finditer(text):
            tag = match.group(0)
            widget_match = _DATA_DZ_WIDGET_VALUE_RE.search(tag)
            if not widget_match:
                continue
            kind = widget_match.group(1)
            if kind not in _BRIDGE_MOUNTED_WIDGET_KINDS:
                continue
            if _X_DATA_RE.search(tag):
                findings.append((template, kind, tag))
    return findings


def test_no_widget_and_x_data_on_same_element() -> None:
    """An element with ``data-dz-widget`` mounts a vendor instance
    via the bridge; if that same element also has ``x-data``, Alpine
    and the vendor compete for DOM ownership and the lifecycle
    contract collapses (#927). Use one or the other on a given node;
    bind them with ``data-*`` attributes if they need to talk."""
    findings = _find_dual_lifecycle_elements()
    if findings:
        rendered = "\n\n".join(
            f"  {path.relative_to(TEMPLATES_DIR.parents[1])}  ({kind})\n    {tag}"
            for path, kind, tag in findings
        )
        raise AssertionError(
            "Found element(s) carrying BOTH a bridge-mounted "
            "`data-dz-widget` and `x-data` — the bridge mounts a "
            "vendor instance over a node Alpine is also driving, "
            "which contends for DOM ownership across "
            "htmx:afterSettle / beforeSwap. Pick one lifecycle per "
            "node (see #939, #940):\n\n"
            f"{rendered}"
        )


def test_bridge_kind_allowlist_matches_registry_handlers() -> None:
    """The allowlist above must mirror the kinds
    ``dz-widget-registry.js`` actually registers — otherwise a future
    handler addition silently bypasses the contract. Pinning the
    intersection here makes the failure obvious instead of latent."""
    registry_path = (
        Path(__file__).resolve().parents[2]
        / "src/dazzle_ui/runtime/static/js/dz-widget-registry.js"
    )
    source = registry_path.read_text(encoding="utf-8")
    register_call_re = re.compile(r"""bridge\.registerWidget\s*\(\s*['"]([^'"]+)['"]""")
    registered = set(register_call_re.findall(source))
    missing = registered - _BRIDGE_MOUNTED_WIDGET_KINDS
    extra = _BRIDGE_MOUNTED_WIDGET_KINDS - registered
    assert not missing, (
        f"dz-widget-registry.js registers {sorted(missing)} but the "
        "contract test's _BRIDGE_MOUNTED_WIDGET_KINDS doesn't. Add "
        "them so the dual-lifecycle check covers the new handler."
    )
    assert not extra, (
        f"_BRIDGE_MOUNTED_WIDGET_KINDS lists {sorted(extra)} that "
        "dz-widget-registry.js no longer registers. Drop them so the "
        "allowlist tracks reality."
    )
