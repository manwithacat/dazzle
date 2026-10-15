"""Goal B coat freeze: example desks may not regrow conversation/rail/focus/metric coats.

``scripts/goal_b_coat.py`` measures each example app's DSL (conversation sites,
document rails, widest focus list, metric keys, sibling trails, cartesian
slices). ``FREEZE`` is a ratchet that only falls when a distill lands; the
honest-grain thresholds flag a desk as a coat. The planner that read the
per-depth saturation detectors was an improve-loop instrument and went with it
(flense ship AX); the freeze is the live part.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.goal_b_coat import FREEZE, coat_residual, freeze_breaches, measure, showcase_apps

pytestmark = pytest.mark.gate


def test_examples_are_within_the_freeze_and_flag_no_coat() -> None:
    assert set(FREEZE) <= set(showcase_apps()), "FREEZE names an app that is not an example"
    assert freeze_breaches() == []
    assert coat_residual() == (0, None)
    for app in FREEZE:
        m = measure(app)
        assert m.conv_siblings <= 2, app
        assert m.slice_cartesian == 0, app


def test_freeze_detects_growth(tmp_path: Path) -> None:
    dsl = tmp_path / "support_tickets" / "dsl"
    dsl.mkdir(parents=True)
    (dsl / "app.dsl").write_text(
        "workspace ticket_queue:\n"
        "  ux:\n"
        "    as agent:\n"
        "      focus: a, b, c\n"
        "  live:\n"
        "    display: conversation\n",
        encoding="utf-8",
    )
    breaches = freeze_breaches(
        examples=tmp_path,
        freeze={"support_tickets": {"conversation_sites": 0, "max_focus": 10}},
    )
    assert breaches == ["support_tickets.conversation_sites=1>0"]
