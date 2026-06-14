"""#1391 — declarative live-refresh / polling primitive for regions.

A region may declare ``refresh: every Ns`` to have its dashboard card poll
the existing region-fetch endpoint every N seconds. This rides entirely on
the HTMX trigger already emitted by ``_emit_dashboard_card`` — the knob just
appends ``, every Ns`` to that trigger.

This module pins three layers:

  1. Parser — ``refresh: every 30s`` / ``every 30`` / ``30s`` / ``30`` all
     resolve to ``WorkspaceRegion.refresh_interval`` in seconds; sub-5s and
     non-second units are directed parse errors (the load/cost floor).
  2. Renderer — ``DashboardCard.refresh_interval`` appends ``, every Ns`` to
     the ``hx-trigger`` and composes with the lazy/eager + SSE clauses.
  3. Default — absent ``refresh:`` leaves the trigger untouched (legacy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.module import ModuleFragment
from dazzle.render.fragment import DashboardCard, FragmentRenderer

_BASE_DSL = """module t
app t "Test"
entity Score:
  id: uuid pk
  ao: enum[ao1,ao2,ao3]
  confidence: float
workspace dash "Dash":
  recent:
    source: Score
    display: list
"""


def _parse(extra: str) -> ModuleFragment:
    return parse_dsl(_BASE_DSL + extra, Path("test.dsl"))[5]


def _region(extra: str) -> object:
    return _parse(extra).workspaces[0].regions[0]


def _render(card: DashboardCard) -> str:
    return FragmentRenderer().render(card)


def _make_card(*, refresh_interval: int | None = None) -> DashboardCard:
    return DashboardCard(
        card_id="card-0",
        name="recent",
        title="Recent",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/api/workspaces/dash/regions/recent",
        eager=True,
        refresh_interval=refresh_interval,
    )


# ───────────────────────────── parser ──────────────────────────────


class TestLiveRefreshParser:
    def test_every_seconds_suffix(self) -> None:
        assert _region("    refresh: every 30s\n").refresh_interval == 30

    def test_every_bare_number_is_seconds(self) -> None:
        assert _region("    refresh: every 30\n").refresh_interval == 30

    def test_bare_seconds_suffix_without_every(self) -> None:
        assert _region("    refresh: 30s\n").refresh_interval == 30

    def test_bare_number_without_every(self) -> None:
        assert _region("    refresh: 15\n").refresh_interval == 15

    def test_absent_refresh_is_none(self) -> None:
        assert _region("").refresh_interval is None

    def test_below_floor_rejected(self) -> None:
        with pytest.raises(ParseError, match="at least 5s"):
            _region("    refresh: every 2s\n")

    def test_exactly_floor_accepted(self) -> None:
        assert _region("    refresh: 5s\n").refresh_interval == 5

    def test_minutes_unit_rejected_with_seconds_hint(self) -> None:
        # `5m` lexes as a DURATION_LITERAL (m = months) — directed to seconds.
        with pytest.raises(ParseError, match="expressed in seconds"):
            _region("    refresh: every 5m\n")

    def test_duration_literal_rejected_with_seconds_hint(self) -> None:
        with pytest.raises(ParseError, match="expressed in seconds"):
            _region("    refresh: 30min\n")

    def test_hours_unit_rejected_with_seconds_hint(self) -> None:
        # `30h` lexes as a DURATION_LITERAL — directed to seconds.
        with pytest.raises(ParseError, match="expressed in seconds"):
            _region("    refresh: 30h\n")

    def test_junk_identifier_unit_rejected(self) -> None:
        # A unit that lexes as NUMBER + IDENTIFIER (not a duration literal)
        # hits the explicit non-`s` branch.
        with pytest.raises(ParseError, match="not supported"):
            _region("    refresh: 30x\n")


# ───────────────────────────── renderer ────────────────────────────


class TestLiveRefreshRenderer:
    def test_polling_clause_appended(self) -> None:
        html = _render(_make_card(refresh_interval=30))
        assert 'hx-trigger="load, every 30s"' in html

    def test_no_clause_when_absent(self) -> None:
        html = _render(_make_card(refresh_interval=None))
        assert "every" not in html
        assert 'hx-trigger="load"' in html

    def test_default_is_none(self) -> None:
        assert _make_card().refresh_interval is None

    def test_composes_with_lazy_trigger(self) -> None:
        card = DashboardCard(
            card_id="card-1",
            name="recent",
            title="Recent",
            display="LIST",
            col_span=6,
            row_order=3,
            hx_endpoint="/api/workspaces/dash/regions/recent",
            eager=False,
            refresh_interval=45,
        )
        html = _render(card)
        assert 'hx-trigger="intersect once, every 45s"' in html
