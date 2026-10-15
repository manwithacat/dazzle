"""Issue #1017 (v0.67.14): regression tests for the entity_card
data resolution layer.

Covers `_build_entity_card_sections` — the helper that composes
section dicts from the scoped record. The MVP populates
halo/flags bodies as <dl> grids of named fields; other modes emit
empty bodies pending the per-mode compact renderer ship.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from dazzle.core.ir.workspaces import (
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections, _safe_fetch

_RECORD: list[dict[str, Any]] = [{"id": "p1"}]
_TS = "2026-05-10T09:00:00+00:00"
_SENT = "2026-05-10T15:00:00+00:00"
_THREAD_FIELDS = ["sent_at", "sender", "subject", "body"]


def _section(
    *,
    name: str,
    mode: EntityCardSectionMode = EntityCardSectionMode.HALO,
    fields: list[str] | None = None,
    actions: list[str] | None = None,
) -> EntityCardSection:
    return EntityCardSection(
        name=name,
        mode=mode,
        fields=fields or [],
        actions=actions or [],
    )


def _config(*, sections: list[EntityCardSection]) -> EntityCardConfig:
    return EntityCardConfig(sections=sections)


def _one(
    section: EntityCardSection,
    *,
    items: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a single-section card and return its section dict.

    `rows` is the per-section pre-fetched row list; None means the
    data-resolution layer has not fanned out (no `rows_per_section`)."""
    out = _build_entity_card_sections(
        items=_RECORD if items is None else items,
        config=_config(sections=[section]),
        rows_per_section=None if rows is None else {0: rows},
    )
    return out[0]


def _mini_bars(fields: list[str]) -> EntityCardSection:
    return _section(name="x", mode=EntityCardSectionMode.MINI_BARS, fields=fields)


def _stamps(fields: list[str]) -> EntityCardSection:
    return _section(name="x", mode=EntityCardSectionMode.STAMPS, fields=fields)


def _thread(fields: list[str]) -> EntityCardSection:
    return _section(name="x", mode=EntityCardSectionMode.THREAD_SUMMARY, fields=fields)


def _quick_actions(actions: list[str]) -> EntityCardSection:
    return _section(name="ops", mode=EntityCardSectionMode.QUICK_ACTIONS, actions=actions)


@pytest.mark.parametrize(
    "config",
    [
        pytest.param(_config(sections=[]), id="no-sections"),
        pytest.param(None, id="config-missing"),
    ],
)
def test_returns_empty_without_sections(config: EntityCardConfig | None) -> None:
    assert _build_entity_card_sections(items=[{"id": "p1"}], config=config) == []


def test_builds_one_section_dict_per_ir_section() -> None:
    cfg = _config(
        sections=[
            _section(name="halo", fields=["name", "score"]),
            _section(name="flags", mode=EntityCardSectionMode.FLAGS, fields=["status"]),
        ]
    )
    out = _build_entity_card_sections(
        items=[{"id": "p1", "name": "Alice", "score": 78, "status": "active"}],
        config=cfg,
    )
    assert len(out) == 2
    assert out[0]["section_id"] == "halo"
    assert out[1]["section_id"] == "flags"


def test_halo_body_renders_dl_grid_with_field_values() -> None:
    section = _section(name="halo", fields=["name", "score"])
    body = _one(section, items=[{"id": "p1", "name": "Alice", "score": 78}])["body"]
    assert "<dl" in body
    assert "<dt>Name</dt>" in body
    assert "<dd>Alice</dd>" in body
    assert "<dt>Score</dt>" in body
    assert "<dd>78</dd>" in body


def test_flags_body_uses_flags_class() -> None:
    section = _section(name="flags", mode=EntityCardSectionMode.FLAGS, fields=["status"])
    assert (
        "dz-entity-card-flags-grid"
        in _one(section, items=[{"id": "p1", "status": "active"}])["body"]
    )


@pytest.mark.parametrize(
    ("section", "items", "rows", "column"),
    [
        pytest.param(
            _section(name="halo", fields=["name"]),
            [{"id": "p1", "name": "A"}],
            None,
            "main",
            id="halo",
        ),
        pytest.param(
            _section(name="flags", mode=EntityCardSectionMode.FLAGS, fields=["status"]),
            [{"id": "p1", "status": "active"}],
            None,
            "sidebar",
            id="flags",
        ),
        pytest.param(
            _thread(["sent_at"]),
            None,
            [{"id": "1", "sent_at": _SENT}],
            "sidebar",
            id="thread-summary",
        ),
    ],
)
def test_section_column_by_mode(
    section: EntityCardSection,
    items: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]] | None,
    column: str,
) -> None:
    assert _one(section, items=items, rows=rows)["column"] == column


@pytest.mark.parametrize(
    ("section", "items", "rows"),
    [
        pytest.param(_section(name="halo", fields=["name"]), [], None, id="halo-no-record"),
        pytest.param(
            _section(name="halo", fields=["nonexistent"]),
            [{"id": "p1", "name": "Alice"}],
            None,
            id="halo-record-has-no-field-values",
        ),
        pytest.param(_quick_actions([]), None, None, id="quick-actions-none-declared"),
        # The data-driven modes with no rows pre-fetched at all (the
        # data-resolution layer hasn't fanned out yet).
        pytest.param(
            _section(name="marks", mode=EntityCardSectionMode.MINI_BARS, fields=["score"]),
            None,
            None,
            id="mini-bars-not-fetched",
        ),
        pytest.param(_stamps(["ts", "label"]), None, None, id="stamps-not-fetched"),
        pytest.param(
            _thread(["ts", "sender", "subject", "body"]),
            None,
            None,
            id="thread-summary-not-fetched",
        ),
        # Fetched but empty.
        pytest.param(_mini_bars(["score"]), None, [], id="mini-bars-no-rows"),
        pytest.param(_stamps(["ts", "label"]), None, [], id="stamps-no-rows"),
        pytest.param(_thread(_THREAD_FIELDS), None, [], id="thread-summary-no-rows"),
        # Misconfigured: no `fields:` declared means no value / timestamp
        # column — the section omits rather than crashing (and thread_summary
        # has no way to pick the most recent).
        pytest.param(_mini_bars([]), None, [{"score": 50}], id="mini-bars-no-value-field"),
        pytest.param(_stamps([]), None, [{"label": "x"}], id="stamps-no-timestamp-field"),
        pytest.param(_thread([]), None, [{"sender": "x"}], id="thread-summary-no-timestamp-field"),
    ],
)
def test_section_omitted_when_its_input_is_absent(
    section: EntityCardSection,
    items: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]] | None,
) -> None:
    out = _one(section, items=items, rows=rows)
    assert out["body"] == ""
    assert out["is_omitted"] is True


def test_section_mode_lands_on_output_dict() -> None:
    cfg = _config(
        sections=[
            _section(name="m", mode=EntityCardSectionMode.MINI_BARS),
            _section(name="t", mode=EntityCardSectionMode.THREAD_SUMMARY),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    assert out[0]["mode"] == "mini_bars"
    assert out[1]["mode"] == "thread_summary"


def test_section_label_humanises_underscored_name() -> None:
    section = _section(name="recent_marks", fields=["score"])
    assert _one(section, items=[{"id": "p1", "score": 78}])["label"] == "Recent Marks"


@pytest.mark.parametrize(
    ("section", "items", "rows", "present", "absent"),
    [
        pytest.param(
            _section(name="halo", fields=["a", "b", "c"]),
            [{"id": "p1", "a": "kept item", "b": None, "c": ""}],
            None,
            ["<dd>kept item</dd>"],
            ["<dt>B</dt>", "<dt>C</dt>"],
            id="halo-skips-none-and-empty-values",
        ),
        pytest.param(
            _mini_bars(["score"]),
            None,
            [{"id": "1", "score": 50}],
            ["dz-mini-bar-fill"],
            ["dz-mini-bar-label"],
            id="mini-bars-label-field-unconfigured",
        ),
        pytest.param(
            _stamps(["ts"]),
            None,
            [{"id": "1", "ts": _TS}],
            ["dz-stamp-time"],
            ["dz-stamp-label"],
            id="stamps-label-field-unconfigured",
        ),
        pytest.param(
            _stamps(["ts", "label", "actor"]),
            None,
            [{"id": "1", "ts": _TS, "label": "Login", "actor": "alice"}],
            ["dz-stamp-detail", ">alice<"],
            [],
            id="stamps-detail-field-configured",
        ),
        # Only the timestamp is required for thread_summary.
        pytest.param(
            _thread(["sent_at"]),
            None,
            [{"id": "1", "sent_at": _SENT}],
            ["dz-thread-summary", "dz-thread-summary-time"],
            ["dz-thread-summary-sender", "dz-thread-summary-subject", "dz-thread-summary-snippet"],
            id="thread-summary-only-timestamp",
        ),
    ],
)
def test_optional_parts_render_only_when_configured_and_populated(
    section: EntityCardSection,
    items: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]] | None,
    present: list[str],
    absent: list[str],
) -> None:
    body = _one(section, items=items, rows=rows)["body"]
    for fragment in present:
        assert fragment in body
    for fragment in absent:
        assert fragment not in body


@pytest.mark.parametrize(
    ("section", "items", "rows", "raw", "escaped"),
    [
        # Field values come straight off raw rows. The helper emits
        # pre-rendered HTML so it must escape, not the primitive (which
        # trusts the body kwarg).
        pytest.param(
            _section(name="halo", fields=["name"]),
            [{"id": "p1", "name": "<script>alert(1)</script>"}],
            None,
            ["<script>"],
            ["&lt;script&gt;"],
            id="halo-field-values",
        ),
        # Both the data attr and the visible label.
        pytest.param(
            _quick_actions(["<script>"]),
            None,
            None,
            ["<script>"],
            ["&lt;script&gt;"],
            id="quick-actions-action-id",
        ),
        pytest.param(
            _mini_bars(["score", "title"]),
            None,
            [{"id": "1", "score": 50, "title": "<script>alert(1)</script>"}],
            ["<script>"],
            ["&lt;script&gt;"],
            id="mini-bars-label",
        ),
        pytest.param(
            _stamps(["ts", "label", "detail"]),
            None,
            [{"id": "1", "ts": _TS, "label": "<script>alert(1)</script>", "detail": "<img src=x>"}],
            ["<script>", "<img"],
            ["&lt;script&gt;", "&lt;img"],
            id="stamps-label-and-detail",
        ),
        pytest.param(
            _thread(_THREAD_FIELDS),
            None,
            [
                {
                    "id": "1",
                    "sent_at": _SENT,
                    "sender": "<script>",
                    "subject": "<img src=x>",
                    "body": "<svg/>",
                }
            ],
            ["<script>", "<img", "<svg"],
            ["&lt;script&gt;", "&lt;img", "&lt;svg"],
            id="thread-summary-all-text-fields",
        ),
    ],
)
def test_html_escapes_raw_values(
    section: EntityCardSection,
    items: list[dict[str, Any]] | None,
    rows: list[dict[str, Any]] | None,
    raw: list[str],
    escaped: list[str],
) -> None:
    body = _one(section, items=items, rows=rows)["body"]
    for fragment in raw:
        assert fragment not in body
    for fragment in escaped:
        assert fragment in body


# ───────────────── quick_actions mode (#1017 v0.67.17) ─────────


def test_quick_actions_mode_renders_button_row() -> None:
    section = _quick_actions(["log_behaviour", "message_parent", "open_in_fastmark"])
    body = _one(section)["body"]
    assert "dz-entity-card-quick-actions" in body
    assert 'data-dz-action="log_behaviour"' in body
    assert 'data-dz-action="message_parent"' in body
    assert 'data-dz-action="open_in_fastmark"' in body
    # Button labels humanise the action id.
    assert ">Log Behaviour<" in body
    assert ">Message Parent<" in body


def test_quick_actions_with_only_empty_action_ids_renders_empty_body() -> None:
    """A list of `[""]` produces no buttons. The MVP marks omitted only
    when the actions list itself is empty — empty strings aren't reached
    there. So actions=["", ""] does NOT omit; it renders as an empty body.
    Documenting the actual behavior so future readers see the shape."""
    assert _one(_quick_actions(["", ""]))["body"] == ""


def test_quick_actions_button_uses_button_type() -> None:
    """`<button type="button">` to prevent accidental form
    submission when the section sits inside a wrapping form
    (project layout often nests cards inside the workspace shell)."""
    assert '<button type="button"' in _one(_quick_actions(["x"]))["body"]


# ───────────────── mini_bars mode (#1017 v0.67.18) ─────────


def test_mini_bars_renders_compact_bar_row_from_pre_fetched_rows() -> None:
    section = _section(
        name="recent_marks",
        mode=EntityCardSectionMode.MINI_BARS,
        fields=["score", "title"],
    )
    rows = [
        {"id": "m1", "score": 78, "title": "Quiz 1"},
        {"id": "m2", "score": 82, "title": "Quiz 2"},
        {"id": "m3", "score": 65, "title": "Quiz 3"},
    ]
    body = _one(section, rows=rows)["body"]
    assert "dz-entity-card-mini-bars" in body
    assert body.count("dz-mini-bar") >= 3  # one entry per row
    assert "Quiz 1" in body
    # Width is normalised — the max value (82) takes 100%.
    assert "width: 100.0%" in body
    # The 78 bar is roughly 95% of max.
    assert "width: 95." in body


@pytest.mark.parametrize(
    "first_row",
    [
        pytest.param({"id": "1", "score": "active"}, id="non-numeric-value"),
        pytest.param({"id": "1"}, id="missing-value-field"),
    ],
)
def test_mini_bars_treat_unusable_values_as_zero(first_row: dict[str, Any]) -> None:
    body = _one(_mini_bars(["score"]), rows=[first_row, {"id": "2", "score": 50}])["body"]
    # Unusable value → 0 width bar; numeric 50 → 100% (it's the max).
    assert "width: 0.0%" in body
    assert "width: 100.0%" in body


def test_mini_bars_value_render_int_when_whole() -> None:
    rows = [{"id": "1", "score": 50}, {"id": "2", "score": 50.5}]
    body = _one(_mini_bars(["score"]), rows=rows)["body"]
    assert ">50<" in body
    assert ">50.5<" in body


def test_mini_bars_all_zero_values_renders_zero_width_bars() -> None:
    """Defensive: max=0 would divide-by-zero; the helper coerces
    to width=0% rather than crashing."""
    rows = [{"id": "1", "score": 0}, {"id": "2", "score": 0}]
    body = _one(_mini_bars(["score"]), rows=rows)["body"]
    assert "dz-mini-bar-fill" in body
    # Both bars at 0%.
    assert body.count("width: 0.0%") == 2


# ───────────────── stamps mode (#1017 v0.67.19) ─────────


def test_stamps_renders_chronological_event_list() -> None:
    section = _section(
        name="recent",
        mode=EntityCardSectionMode.STAMPS,
        fields=["triggered_at", "message"],
    )
    rows = [
        {"id": "e1", "triggered_at": "2026-05-10T09:00:00+00:00", "message": "First event"},
        {"id": "e2", "triggered_at": "2026-05-10T11:00:00+00:00", "message": "Latest event"},
        {"id": "e3", "triggered_at": "2026-05-10T10:00:00+00:00", "message": "Middle event"},
    ]
    body = _one(section, rows=rows)["body"]
    assert "dz-entity-card-stamps" in body
    assert body.count("dz-stamp") >= 3
    latest_pos = body.index("Latest event")
    middle_pos = body.index("Middle event")
    first_pos = body.index("First event")
    assert latest_pos < middle_pos < first_pos


@pytest.mark.parametrize(
    ("section", "row", "iso", "time_class"),
    [
        pytest.param(
            _stamps(["ts", "label"]),
            {"id": "1", "ts": _TS, "label": "Login"},
            _TS,
            '<time class="dz-stamp-time"',
            id="stamps",
        ),
        pytest.param(
            _thread(_THREAD_FIELDS),
            {"id": "1", "sent_at": _SENT, "sender": "Alice", "subject": "Hi", "body": "Hello"},
            _SENT,
            "dz-thread-summary-time",
            id="thread-summary",
        ),
    ],
)
def test_time_element_keeps_iso_and_shows_humanised_text(
    section: EntityCardSection, row: dict[str, Any], iso: str, time_class: str
) -> None:
    """Machine ISO stays on the datetime attr; visible text is humanised
    (local wall clock)."""
    body = _one(section, rows=[row])["body"]
    assert time_class in body
    assert f'datetime="{iso}"' in body
    assert "May 2026" in body
    assert f">{iso[:16]}" not in body


def test_stamps_handles_unparseable_timestamps_gracefully() -> None:
    rows = [
        {"id": "1", "ts": "not-a-date", "label": "Bad"},
        {"id": "2", "ts": _TS, "label": "Good"},
    ]
    body = _one(_stamps(["ts", "label"]), rows=rows)["body"]
    assert "Good" in body
    assert "Bad" in body
    assert body.index("Good") < body.index("Bad")


# ───────────────── thread_summary mode (#1017 v0.67.20) ─────────


def test_thread_summary_renders_most_recent_thread() -> None:
    section = _section(
        name="parent_contact",
        mode=EntityCardSectionMode.THREAD_SUMMARY,
        fields=_THREAD_FIELDS,
    )
    rows = [
        {
            "id": "m1",
            "sent_at": "2026-05-09T10:00:00+00:00",
            "sender": "Mr Bayard",
            "subject": "Re: parents evening",
            "body": "Looking forward to chatting on Thursday.",
        },
        {
            "id": "m2",
            "sent_at": "2026-05-10T15:00:00+00:00",
            "sender": "Mrs Wong",
            "subject": "Maths homework",
            "body": "Could you confirm the deadline?",
        },
    ]
    body = _one(section, rows=rows)["body"]
    assert "dz-thread-summary" in body
    # Most recent (Mrs Wong, 2026-05-10) — NOT Mr Bayard (2026-05-09).
    assert "Mrs Wong" in body
    assert "Maths homework" in body
    assert "deadline" in body
    assert "Mr Bayard" not in body
    assert "parents evening" not in body


def test_thread_summary_truncates_long_snippet_at_word_boundary() -> None:
    long_body = "Lorem ipsum " * 30  # ~360 chars
    rows = [{"id": "1", "sent_at": _SENT, "sender": "x", "subject": "y", "body": long_body}]
    body = _one(_thread(_THREAD_FIELDS), rows=rows)["body"]
    # Snippet length capped (truncate at ~140 + ellipsis).
    snippet_start = body.index("dz-thread-summary-snippet")
    snippet_end = body.index("</p>", snippet_start)
    snippet = body[snippet_start:snippet_end]
    assert "…" in snippet
    # Cap is on the raw text — generous header + escape allows
    # roughly 200 chars total in the slice.
    assert len(snippet) < 250


def test_thread_summary_short_snippet_not_truncated() -> None:
    rows = [{"id": "1", "sent_at": _SENT, "sender": "a", "subject": "b", "body": "Short"}]
    body = _one(_thread(_THREAD_FIELDS), rows=rows)["body"]
    assert ">Short<" in body
    assert "…" not in body


# ---------------------------------------------------------------------------
# Regression for #1215: `_safe_fetch` must normalise Pydantic-model rows
# to dicts before returning, otherwise downstream renderers that call
# `row.get(field)` raise AttributeError on the model instance.
# ---------------------------------------------------------------------------


class _FakeRow(BaseModel):
    id: str
    score: int


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        # The three cross-entity entity_card modes (mini_bars, stamps,
        # thread_summary) read each row via `row.get(field)` — a `dict`
        # method that does not exist on Pydantic v2 models. Pre-#1215,
        # `_safe_fetch` returned model instances; the renderers crashed
        # with HTTP 500. (A model never compares equal to a dict, so the
        # equality also proves the rows are plain dicts.)
        pytest.param(
            [_FakeRow(id="r1", score=42), _FakeRow(id="r2", score=99)],
            [{"id": "r1", "score": 42}, {"id": "r2", "score": 99}],
            id="pydantic-rows-model-dumped-1215",
        ),
        # Repos that already return dicts pass through unchanged.
        pytest.param([{"id": "r1", "score": 7}], [{"id": "r1", "score": 7}], id="plain-dict-rows"),
    ],
)
def test_safe_fetch_returns_plain_dict_rows(
    items: list[Any], expected: list[dict[str, Any]]
) -> None:
    class FakeRepo:
        async def list(self, **_kwargs: Any) -> dict[str, Any]:
            return {"items": items}

    rows = asyncio.run(_safe_fetch(FakeRepo(), filters={}, page_size=10, label="MarkingResult"))
    assert rows == expected
    assert all(type(r) is dict for r in rows)
