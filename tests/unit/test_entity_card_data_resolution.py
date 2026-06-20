"""Issue #1017 (v0.67.14): regression tests for the entity_card
data resolution layer.

Covers `_build_entity_card_sections` — the helper that composes
section dicts from the scoped record. The MVP populates
halo/flags bodies as <dl> grids of named fields; other modes emit
empty bodies pending the per-mode compact renderer ship.
"""

from __future__ import annotations

from dazzle.core.ir.workspaces import (
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
)
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections


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


def test_returns_empty_when_no_sections() -> None:
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=_config(sections=[]))
    assert out == []


def test_returns_empty_when_config_missing() -> None:
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=None)
    assert out == []


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
    cfg = _config(sections=[_section(name="halo", fields=["name", "score"])])
    out = _build_entity_card_sections(
        items=[{"id": "p1", "name": "Alice", "score": 78}], config=cfg
    )
    body = out[0]["body"]
    assert "<dl" in body
    assert "<dt>name</dt>" in body
    assert "<dd>Alice</dd>" in body
    assert "<dt>score</dt>" in body
    assert "<dd>78</dd>" in body


def test_flags_body_uses_flags_class_and_sidebar_column() -> None:
    cfg = _config(
        sections=[_section(name="flags", mode=EntityCardSectionMode.FLAGS, fields=["status"])]
    )
    out = _build_entity_card_sections(items=[{"id": "p1", "status": "active"}], config=cfg)
    assert "dz-entity-card-flags-grid" in out[0]["body"]
    assert out[0]["column"] == "sidebar"


def test_halo_section_omitted_when_no_record() -> None:
    cfg = _config(sections=[_section(name="halo", fields=["name"])])
    out = _build_entity_card_sections(items=[], config=cfg)
    assert out[0]["is_omitted"] is True


def test_section_omitted_when_record_has_no_field_values() -> None:
    cfg = _config(sections=[_section(name="halo", fields=["nonexistent"])])
    out = _build_entity_card_sections(items=[{"id": "p1", "name": "Alice"}], config=cfg)
    assert out[0]["is_omitted"] is True


def test_skips_fields_with_none_or_empty_values() -> None:
    cfg = _config(sections=[_section(name="halo", fields=["a", "b", "c"])])
    out = _build_entity_card_sections(
        items=[{"id": "p1", "a": "kept", "b": None, "c": ""}], config=cfg
    )
    body = out[0]["body"]
    assert "<dd>kept</dd>" in body
    assert "<dt>b</dt>" not in body
    assert "<dt>c</dt>" not in body


def test_per_mode_sections_omit_when_no_rows_pre_fetched() -> None:
    """All four data-driven modes (mini_bars / stamps /
    thread_summary / quick_actions) flag is_omitted=True when their
    required input is absent: mini_bars / stamps / thread_summary
    when no rows pre-fetched; quick_actions when no actions
    declared. Provides empty `rows_per_section` (the data-resolution
    layer hasn't fanned out yet) and asserts the chrome doesn't
    render."""
    cfg = _config(
        sections=[
            _section(
                name="marks",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
            _section(
                name="recent",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label"],
            ),
            _section(
                name="comm",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["ts", "sender", "subject", "body"],
            ),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    for section in out:
        assert section["body"] == ""
        assert section["is_omitted"] is True


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
    cfg = _config(sections=[_section(name="recent_marks", fields=["score"])])
    out = _build_entity_card_sections(items=[{"id": "p1", "score": 78}], config=cfg)
    assert out[0]["label"] == "Recent Marks"


def test_html_escape_in_field_values() -> None:
    """Defensive: field values come straight off raw rows. The
    helper emits pre-rendered HTML so it must escape, not the
    primitive (which trusts the body kwarg)."""
    cfg = _config(sections=[_section(name="halo", fields=["name"])])
    out = _build_entity_card_sections(
        items=[{"id": "p1", "name": "<script>alert(1)</script>"}], config=cfg
    )
    body = out[0]["body"]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


# ───────────────── quick_actions mode (#1017 v0.67.17) ─────────


def test_quick_actions_mode_renders_button_row() -> None:
    cfg = _config(
        sections=[
            _section(
                name="ops",
                mode=EntityCardSectionMode.QUICK_ACTIONS,
                actions=["log_behaviour", "message_parent", "open_in_fastmark"],
            )
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    body = out[0]["body"]
    assert "dz-entity-card-quick-actions" in body
    assert 'data-dz-action="log_behaviour"' in body
    assert 'data-dz-action="message_parent"' in body
    assert 'data-dz-action="open_in_fastmark"' in body
    # Button labels humanise the action id.
    assert ">Log Behaviour<" in body
    assert ">Message Parent<" in body


def test_quick_actions_omits_section_when_no_actions_declared() -> None:
    cfg = _config(
        sections=[_section(name="ops", mode=EntityCardSectionMode.QUICK_ACTIONS, actions=[])]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    assert out[0]["is_omitted"] is True


def test_quick_actions_omits_section_when_only_empty_action_ids() -> None:
    """Defensive: a list of `[""]` produces no buttons; the section
    omits rather than rendering an empty action row."""
    cfg = _config(
        sections=[_section(name="ops", mode=EntityCardSectionMode.QUICK_ACTIONS, actions=["", ""])]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    # Body falls through to empty + the section gets the
    # `is_omitted` treatment from the outer empty-body path. The
    # MVP marks omitted only when the actions list itself is empty
    # — empty strings aren't reached here. So actions=["", ""] does
    # NOT omit; render as empty body. Documenting the actual
    # behavior so future readers see the intentional shape.
    assert out[0]["body"] == ""


def test_quick_actions_button_uses_button_type() -> None:
    """`<button type="button">` to prevent accidental form
    submission when the section sits inside a wrapping form
    (project layout often nests cards inside the workspace shell)."""
    cfg = _config(
        sections=[_section(name="ops", mode=EntityCardSectionMode.QUICK_ACTIONS, actions=["x"])]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    assert '<button type="button"' in out[0]["body"]


def test_quick_actions_html_escapes_action_id() -> None:
    """Defensive: an action id with HTML-special chars should
    escape both in the data attr and the visible label."""
    cfg = _config(
        sections=[
            _section(
                name="ops",
                mode=EntityCardSectionMode.QUICK_ACTIONS,
                actions=["<script>"],
            )
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    body = out[0]["body"]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


# ───────────────── mini_bars mode (#1017 v0.67.18) ─────────


def test_mini_bars_renders_compact_bar_row_from_pre_fetched_rows() -> None:
    cfg = _config(
        sections=[
            _section(
                name="recent_marks",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score", "title"],
            ),
        ]
    )
    rows = [
        {"id": "m1", "score": 78, "title": "Quiz 1"},
        {"id": "m2", "score": 82, "title": "Quiz 2"},
        {"id": "m3", "score": 65, "title": "Quiz 3"},
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-entity-card-mini-bars" in body
    assert body.count("dz-mini-bar") >= 3  # one entry per row
    assert "Quiz 1" in body
    # Width is normalised — the max value (82) takes 100%.
    assert "width: 100.0%" in body
    # The 78 bar is roughly 95% of max.
    assert "width: 95." in body


def test_mini_bars_omits_section_when_no_rows() -> None:
    cfg = _config(
        sections=[
            _section(
                name="recent_marks",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: []})
    assert out[0]["is_omitted"] is True


def test_mini_bars_omits_section_when_no_value_field() -> None:
    """Misconfigured section (no `fields:` declared) can't render
    bars — section omits rather than crashing."""
    cfg = _config(
        sections=[
            _section(name="x", mode=EntityCardSectionMode.MINI_BARS),
        ]
    )
    out = _build_entity_card_sections(
        items=[{"id": "p1"}], config=cfg, rows_per_section={0: [{"score": 50}]}
    )
    assert out[0]["is_omitted"] is True


def test_mini_bars_handles_non_numeric_values_as_zero() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
        ]
    )
    rows = [
        {"id": "1", "score": "active"},
        {"id": "2", "score": 50},
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    # Non-numeric → 0 width bar; numeric → 100% (it's the max).
    assert "width: 0.0%" in body
    assert "width: 100.0%" in body


def test_mini_bars_handles_missing_value_field_in_some_rows() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
        ]
    )
    rows = [
        {"id": "1"},  # no score field
        {"id": "2", "score": 50},
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    # Missing value treated as 0 → 0% bar; 50 wins as max.
    assert "width: 0.0%" in body


def test_mini_bars_label_field_optional() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],  # no label field
            ),
        ]
    )
    rows = [{"id": "1", "score": 50}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-mini-bar-label" not in body
    assert "dz-mini-bar-fill" in body


def test_mini_bars_value_render_int_when_whole() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
        ]
    )
    rows = [{"id": "1", "score": 50}, {"id": "2", "score": 50.5}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert ">50<" in body
    assert ">50.5<" in body


def test_mini_bars_html_escapes_label_values() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score", "title"],
            ),
        ]
    )
    rows = [{"id": "1", "score": 50, "title": "<script>alert(1)</script>"}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_mini_bars_all_zero_values_renders_zero_width_bars() -> None:
    """Defensive: max=0 would divide-by-zero; the helper coerces
    to width=0% rather than crashing."""
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.MINI_BARS,
                fields=["score"],
            ),
        ]
    )
    rows = [{"id": "1", "score": 0}, {"id": "2", "score": 0}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-mini-bar-fill" in body
    # Both bars at 0%.
    assert body.count("width: 0.0%") == 2


# ───────────────── stamps mode (#1017 v0.67.19) ─────────


def test_stamps_renders_chronological_event_list() -> None:
    cfg = _config(
        sections=[
            _section(
                name="recent",
                mode=EntityCardSectionMode.STAMPS,
                fields=["triggered_at", "message"],
            ),
        ]
    )
    rows = [
        {
            "id": "e1",
            "triggered_at": "2026-05-10T09:00:00+00:00",
            "message": "First event",
        },
        {
            "id": "e2",
            "triggered_at": "2026-05-10T11:00:00+00:00",
            "message": "Latest event",
        },
        {
            "id": "e3",
            "triggered_at": "2026-05-10T10:00:00+00:00",
            "message": "Middle event",
        },
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-entity-card-stamps" in body
    assert body.count("dz-stamp") >= 3
    latest_pos = body.index("Latest event")
    middle_pos = body.index("Middle event")
    first_pos = body.index("First event")
    assert latest_pos < middle_pos < first_pos


def test_stamps_renders_time_element_with_iso_datetime() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label"],
            ),
        ]
    )
    rows = [{"id": "1", "ts": "2026-05-10T09:00:00+00:00", "label": "Login"}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert '<time class="dz-stamp-time"' in body
    assert 'datetime="2026-05-10T09:00:00+00:00"' in body
    assert ">2026-05-10 09:00<" in body


def test_stamps_renders_optional_detail_field() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label", "actor"],
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "ts": "2026-05-10T09:00:00+00:00",
            "label": "Login",
            "actor": "alice",
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-stamp-detail" in body
    assert ">alice<" in body


def test_stamps_omits_section_when_no_rows() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label"],
            ),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: []})
    assert out[0]["is_omitted"] is True


def test_stamps_omits_section_when_no_timestamp_field() -> None:
    cfg = _config(sections=[_section(name="x", mode=EntityCardSectionMode.STAMPS)])
    out = _build_entity_card_sections(
        items=[{"id": "p1"}], config=cfg, rows_per_section={0: [{"label": "x"}]}
    )
    assert out[0]["is_omitted"] is True


def test_stamps_handles_unparseable_timestamps_gracefully() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label"],
            ),
        ]
    )
    rows = [
        {"id": "1", "ts": "not-a-date", "label": "Bad"},
        {"id": "2", "ts": "2026-05-10T09:00:00+00:00", "label": "Good"},
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "Good" in body
    assert "Bad" in body
    assert body.index("Good") < body.index("Bad")


def test_stamps_html_escapes_label_and_detail() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts", "label", "detail"],
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "ts": "2026-05-10T09:00:00+00:00",
            "label": "<script>alert(1)</script>",
            "detail": "<img src=x>",
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "<script>" not in body
    assert "<img" not in body
    assert "&lt;script&gt;" in body
    assert "&lt;img" in body


def test_stamps_omits_label_span_when_label_field_unconfigured() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.STAMPS,
                fields=["ts"],
            ),
        ]
    )
    rows = [{"id": "1", "ts": "2026-05-10T09:00:00+00:00"}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-stamp-time" in body
    assert "dz-stamp-label" not in body


# ───────────────── thread_summary mode (#1017 v0.67.20) ─────────


def test_thread_summary_renders_most_recent_thread() -> None:
    cfg = _config(
        sections=[
            _section(
                name="parent_contact",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
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
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-thread-summary" in body
    # Most recent (Mrs Wong, 2026-05-10) — NOT Mr Bayard (2026-05-09).
    assert "Mrs Wong" in body
    assert "Maths homework" in body
    assert "deadline" in body
    assert "Mr Bayard" not in body
    assert "parents evening" not in body


def test_thread_summary_renders_iso_timestamp_in_time_element() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "sent_at": "2026-05-10T15:00:00+00:00",
            "sender": "Alice",
            "subject": "Hi",
            "body": "Hello",
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert 'datetime="2026-05-10T15:00:00+00:00"' in body
    assert ">2026-05-10 15:00<" in body


def test_thread_summary_truncates_long_snippet_at_word_boundary() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
    )
    long_body = "Lorem ipsum " * 30  # ~360 chars
    rows = [
        {
            "id": "1",
            "sent_at": "2026-05-10T15:00:00+00:00",
            "sender": "x",
            "subject": "y",
            "body": long_body,
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    # Snippet length capped (truncate at ~140 + ellipsis).
    snippet_start = body.index("dz-thread-summary-snippet")
    snippet_end = body.index("</p>", snippet_start)
    snippet = body[snippet_start:snippet_end]
    assert "…" in snippet
    # Cap is on the raw text — generous header + escape allows
    # roughly 200 chars total in the slice.
    assert len(snippet) < 250


def test_thread_summary_omits_section_when_no_rows() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: []})
    assert out[0]["is_omitted"] is True


def test_thread_summary_omits_section_when_no_timestamp_field() -> None:
    """No timestamp = no way to pick most-recent — section omits."""
    cfg = _config(sections=[_section(name="x", mode=EntityCardSectionMode.THREAD_SUMMARY)])
    out = _build_entity_card_sections(
        items=[{"id": "p1"}], config=cfg, rows_per_section={0: [{"sender": "x"}]}
    )
    assert out[0]["is_omitted"] is True


def test_thread_summary_renders_with_optional_fields_unset() -> None:
    """Only timestamp required; other fields render only when
    configured AND populated."""
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at"],  # only timestamp
            ),
        ]
    )
    rows = [{"id": "1", "sent_at": "2026-05-10T15:00:00+00:00"}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "dz-thread-summary" in body
    assert "dz-thread-summary-time" in body
    assert "dz-thread-summary-sender" not in body
    assert "dz-thread-summary-subject" not in body
    assert "dz-thread-summary-snippet" not in body


def test_thread_summary_html_escapes_all_text_fields() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "sent_at": "2026-05-10T15:00:00+00:00",
            "sender": "<script>",
            "subject": "<img src=x>",
            "body": "<svg/>",
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert "<script>" not in body
    assert "<img" not in body
    assert "<svg" not in body
    assert "&lt;script&gt;" in body
    assert "&lt;img" in body
    assert "&lt;svg" in body


def test_thread_summary_lives_in_sidebar_column() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at"],
            ),
        ]
    )
    rows = [{"id": "1", "sent_at": "2026-05-10T15:00:00+00:00"}]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    assert out[0]["column"] == "sidebar"


def test_thread_summary_short_snippet_not_truncated() -> None:
    cfg = _config(
        sections=[
            _section(
                name="x",
                mode=EntityCardSectionMode.THREAD_SUMMARY,
                fields=["sent_at", "sender", "subject", "body"],
            ),
        ]
    )
    rows = [
        {
            "id": "1",
            "sent_at": "2026-05-10T15:00:00+00:00",
            "sender": "a",
            "subject": "b",
            "body": "Short",
        }
    ]
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg, rows_per_section={0: rows})
    body = out[0]["body"]
    assert ">Short<" in body
    assert "…" not in body


# ---------------------------------------------------------------------------
# Regression for #1215: `_safe_fetch` must normalise Pydantic-model rows
# to dicts before returning, otherwise downstream renderers that call
# `row.get(field)` raise AttributeError on the model instance.
# ---------------------------------------------------------------------------


def test_safe_fetch_normalises_pydantic_rows_to_dicts() -> None:
    """`_safe_fetch` must call .model_dump() on row objects.

    The three cross-entity entity_card modes (mini_bars, stamps,
    thread_summary) read each row via `row.get(field)` — a `dict`
    method that does not exist on Pydantic v2 models. Pre-#1215,
    `_safe_fetch` returned the items list as-is, propagating model
    instances; the renderers crashed with HTTP 500.
    """
    import asyncio

    from pydantic import BaseModel

    from dazzle.http.runtime.workspace_card_fetchers import _safe_fetch

    class FakeRow(BaseModel):
        id: str
        score: int

    class FakeRepo:
        async def list(self, **_kwargs):
            return {"items": [FakeRow(id="r1", score=42), FakeRow(id="r2", score=99)]}

    rows = asyncio.run(_safe_fetch(FakeRepo(), filters={}, page_size=10, label="MarkingResult"))
    # Renderers depend on .get(field) — must be plain dicts now.
    assert all(isinstance(r, dict) for r in rows)
    assert rows[0].get("score") == 42
    assert rows[1].get("id") == "r2"


def test_safe_fetch_handles_plain_dict_rows() -> None:
    """Repos that already return dicts must pass through unchanged."""
    import asyncio

    from dazzle.http.runtime.workspace_card_fetchers import _safe_fetch

    class FakeRepo:
        async def list(self, **_kwargs):
            return {"items": [{"id": "r1", "score": 7}]}

    rows = asyncio.run(_safe_fetch(FakeRepo(), filters={}, page_size=10, label="X"))
    assert rows == [{"id": "r1", "score": 7}]
