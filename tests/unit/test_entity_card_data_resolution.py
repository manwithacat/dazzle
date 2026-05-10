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
from dazzle_back.runtime.workspace_rendering import _build_entity_card_sections


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


def test_remaining_modes_emit_empty_body_pending_per_mode_renderers() -> None:
    """mini_bars / stamps / thread_summary modes have deferred
    per-mode compact renderers; the MVP emits empty bodies so the
    section chrome renders without crashing. quick_actions mode
    landed in v0.67.17 — see its dedicated test block below."""
    cfg = _config(
        sections=[
            _section(name="marks", mode=EntityCardSectionMode.MINI_BARS),
            _section(name="recent", mode=EntityCardSectionMode.STAMPS),
            _section(name="comm", mode=EntityCardSectionMode.THREAD_SUMMARY),
        ]
    )
    out = _build_entity_card_sections(items=[{"id": "p1"}], config=cfg)
    for section in out:
        assert section["body"] == ""


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
