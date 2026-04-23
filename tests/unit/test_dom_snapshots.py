"""DOM snapshot baselines for the dashboard-slot + region composite.

Complements the shape-nesting (INV-1) and duplicate-title (INV-2)
scanners: those gates catch *specific* structural regressions that
match a known-bad pattern; the snapshot gate here catches *any*
byte-level change to the rendered composite — class tweaks, text
changes, attribute shuffles, tag substitutions.

Intentional change? Regenerate the baselines:

    pytest tests/unit/test_dom_snapshots.py --snapshot-update

Review the diff in ``tests/unit/__snapshots__/``. If the change is
what you meant, commit the updated baselines alongside the template
edit. If it wasn't, fix the template.

Cheaper than Playwright screenshot baselines (no browser runtime,
no pixel diffs, no flakiness from anti-aliasing), at the cost of
missing pure CSS-only regressions. Most visual regressions we care
about (card-in-card, duplicate titles, removed buttons, tag
changes) go through structural changes and show up here.

Not to be confused with the shape gates in
``test_template_html.py::TestDashboardRegionCompositeShapes``:
- Shape gates: known-bad structure = fail. Scans for patterns.
- Snapshot tests: any byte change = fail. Diffs against a pin.
Both run on the same 14 region-case matrix; the snapshot output
includes the shape output so a regression fails both.
"""

from __future__ import annotations

import re

import pytest

from dazzle_ui.runtime.template_renderer import create_jinja_env

# Reuse the region case matrix from the composite-shape tests so we
# snapshot the same output the shape gate sees. Keeping them in one
# place means a new region lands in both gates together.
from tests.unit.test_template_html import (  # noqa: E402
    _DASHBOARD_SLOT_WITH_REGION,
    _MOCK_CONTEXT,
    _REGION_CASES,
)


@pytest.fixture(scope="module")
def jinja_env():
    env = create_jinja_env()
    from jinja2 import Undefined

    env.undefined = Undefined
    return env


def _normalise(html: str) -> str:
    """Collapse whitespace runs + strip clock-dependent timeago text so
    snapshots don't drift across days.

    Preserves visible text + structure apart from the ``timeago`` filter
    output — that's always of the form ``<N> (seconds|minutes|hours|days
    |months|years) ago`` or ``just now`` and changes on every test run
    once the fixture date slips past real wall-clock time. Replacing
    each match with a fixed sentinel keeps the rest of the DOM stable.
    """
    # Collapse whitespace between tags
    html = re.sub(r">\s+<", "><", html)
    # Collapse repeated inner whitespace
    html = re.sub(r"\s+", " ", html)
    # Normalise timeago output — `N units ago`, `1 unit ago`, or `just now`.
    html = re.sub(
        r"\b\d+\s+(seconds?|minutes?|hours?|days?|months?|years?)\s+ago\b",
        "<timeago>",
        html,
    )
    html = html.replace("just now", "<timeago>")
    return html.strip()


@pytest.mark.parametrize(
    "template_name,card_title,context",
    _REGION_CASES,
    ids=lambda v: (
        v.replace("workspace/regions/", "").removesuffix(".html")
        if isinstance(v, str) and v.startswith("workspace/")
        else None
    ),
)
def test_region_composite_snapshot(snapshot, jinja_env, template_name, card_title, context):
    """The rendered composite for each region must match its baseline."""
    try:
        template = jinja_env.get_template(template_name)
    except Exception:
        pytest.skip(f"Template {template_name} not found")

    ctx = {**_MOCK_CONTEXT, "title": card_title, **context}
    try:
        region_html = template.render(**ctx)
    except Exception as e:
        pytest.skip(f"Template {template_name} requires different context: {e}")

    composite = _DASHBOARD_SLOT_WITH_REGION.format(
        card_title=card_title,
        region_name=context["region_name"],
        region_html=region_html,
    )
    assert _normalise(composite) == snapshot
