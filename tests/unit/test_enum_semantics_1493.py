"""#1493 (UX-maturity 1b) — `semantic:` tone bindings on shared enums.

Slice 1: the declarative + validated core. A shared `enum` block may carry a
`semantic: value=tone, ...` line binding each value's lifecycle role to a tone
from the canonical palette (`positive` aliases `success`). Declared tones are
validated against the palette; value membership is enforced at parse time.

Slice 2 (part 1): the inline `enum[...]` field form gains the same `semantic:`
continuation line (`status: enum[...]` + an indented `semantic: v=tone, ...`),
populating `FieldType.enum_semantics`. The render/icon consumption is the
remaining slice-2 work.
"""

import pathlib

import pytest

from dazzle.core.errors import DazzleError
from dazzle.core.ir import ModuleIR
from dazzle.core.ir.tones import CANONICAL_TONES, normalize_tone
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_dsl


def _parse(dsl: str):
    _, _, _, _, _, frag = parse_dsl(dsl, pathlib.Path("test.dsl"))
    return frag


def _enum(frag, name: str):
    return next(e for e in frag.enums if e.name == name)


# ── tone normalisation / palette ──────────────────────────────────────────


def test_canonical_palette_is_the_five_css_tones() -> None:
    assert set(CANONICAL_TONES) == {"success", "info", "warning", "destructive", "neutral"}


def test_positive_aliases_success() -> None:
    assert normalize_tone("positive") == "success"


def test_normalize_is_case_insensitive() -> None:
    assert normalize_tone("WARNING") == "warning"


def test_unknown_tone_normalises_to_none() -> None:
    assert normalize_tone("turquoise") is None


# ── parser: shared enum `semantic:` line ──────────────────────────────────


def test_semantic_line_binds_values() -> None:
    frag = _parse(
        """module m
app a "A"
enum OrderStatus "Order Status":
  draft "Draft"
  pending "Pending"
  approved "Approved"
  rejected "Rejected"
  semantic: pending=warning, approved=positive, rejected=destructive, draft=neutral
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "OrderStatus").values}
    assert by_name == {
        "draft": "neutral",
        "pending": "warning",
        "approved": "positive",  # raw; normalises to success downstream
        "rejected": "destructive",
    }


def test_undeclared_values_keep_none_semantic() -> None:
    frag = _parse(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  semantic: a=success
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "S").values}
    assert by_name == {"a": "success", "b": None}


def test_semantic_line_may_precede_values() -> None:
    frag = _parse(
        """module m
app a "A"
enum S "S":
  semantic: a=success, b=destructive
  a "A"
  b "B"
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "S").values}
    assert by_name == {"a": "success", "b": "destructive"}


def test_semantic_binding_unknown_value_is_parse_error() -> None:
    with pytest.raises(DazzleError) as exc:
        _parse(
            """module m
app a "A"
enum S "S":
  draft "Draft"
  semantic: nonexistent=warning
"""
        )
    assert "E_SEMANTIC_VALUE_UNKNOWN" in str(exc.value)


# ── parser: inline `enum[...]` field `semantic:` continuation (slice 2) ────


def _field(frag, entity_name: str, field_name: str):
    entity = next(e for e in frag.entities if e.name == entity_name)
    return next(f for f in entity.fields if f.name == field_name)


def test_inline_enum_semantic_continuation_binds_tones() -> None:
    frag = _parse(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, in_review, done, blocked]
    semantic: open=neutral, in_review=warning, done=positive, blocked=destructive
"""
    )
    ft = _field(frag, "Task", "status").type
    assert ft.enum_semantics == {
        "open": "neutral",
        "in_review": "warning",
        "done": "positive",  # raw; normalises to success downstream
        "blocked": "destructive",
    }


def test_inline_enum_without_semantic_has_none() -> None:
    frag = _parse(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
"""
    )
    ft = _field(frag, "Task", "status").type
    assert ft.enum_semantics is None


def test_inline_enum_semantic_composes_with_default() -> None:
    # The continuation must not interfere with a same-line `=default` modifier.
    frag = _parse(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]=open
    semantic: done=positive
"""
    )
    field = _field(frag, "Task", "status")
    assert field.default == "open"
    assert field.type.enum_semantics == {"done": "positive"}


def test_inline_enum_semantic_unknown_value_is_parse_error() -> None:
    with pytest.raises(DazzleError) as exc:
        _parse(
            """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
    semantic: nonexistent=warning
"""
        )
    assert "E_SEMANTIC_VALUE_UNKNOWN" in str(exc.value)


def test_inline_enum_semantic_unknown_tone_is_validation_error() -> None:
    from dazzle.core.validation.ux import validate_enum_semantics

    appspec = _appspec(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
    semantic: done=turquoise
"""
    )
    errors, _ = validate_enum_semantics(appspec)
    assert any("E_SEMANTIC_TONE_UNKNOWN" in e and "turquoise" in e for e in errors)


# ── render consumption: resolve_status_tone (slice 2 part 2) ───────────────


def test_resolver_no_map_matches_name_guess() -> None:
    from dazzle.render.filters import _badge_tone_filter, resolve_status_tone

    # Byte-identical to the legacy name guess when no binding is supplied.
    for value in ["done", "blocked", "open", "totally_unknown", None, "In Progress"]:
        assert resolve_status_tone(value) == _badge_tone_filter(value)


def test_resolver_declared_binding_wins_over_name_guess() -> None:
    from dazzle.render.filters import resolve_status_tone

    # "open" name-guesses to "info"; a declared binding overrides it.
    assert resolve_status_tone("open") == "info"
    assert resolve_status_tone("open", {"open": "warning"}) == "warning"
    # `positive` alias normalises to `success`.
    assert resolve_status_tone("draft", {"draft": "positive"}) == "success"


def test_resolver_unknown_declared_tone_falls_back_to_neutral() -> None:
    from dazzle.render.filters import resolve_status_tone

    # A non-palette tone in the map resolves to neutral (not the name guess) —
    # the binding is authoritative; validation catches the typo separately.
    assert resolve_status_tone("done", {"done": "turquoise"}) == "neutral"


def test_resolver_undeclared_value_with_map_uses_name_guess() -> None:
    from dazzle.render.filters import resolve_status_tone

    # A value not in the (partial) map still falls through to the name guess
    # ("done" → success), not neutral.
    assert resolve_status_tone("done", {"open": "warning"}) == "success"


def test_badge_html_consumes_semantic_map() -> None:
    from dazzle.render.fragment.region._shared import _render_status_badge_html

    # Without a map, "open" → info; with a declared binding, → warning.
    assert 'data-dz-tone="info"' in _render_status_badge_html("open")
    assert 'data-dz-tone="warning"' in _render_status_badge_html(
        "open", semantic_map={"open": "warning"}
    )


def test_column_semantic_map_populated_from_shared_enum() -> None:
    # The col-build site resolves a shared enum's `semantic:` into ColumnContext.
    # A shared enum binds an inline `enum[...]` field by value-set match (the same
    # mechanism `_infer_filter_type` uses to recover titles).
    from dazzle.page.converters.template_compiler import _build_columns

    appspec = _appspec(
        """module m
app a "A"
enum TaskStatus "Task Status":
  open "Open"
  done "Done"
  semantic: open=warning, done=positive
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
surface tasks "Tasks":
  uses entity Task
  mode: list
  section main:
    field status "Status"
"""
    )
    entity = next(e for e in appspec.domain.entities if e.name == "Task")
    surface = next(s for s in appspec.surfaces if s.name == "tasks")
    cols = _build_columns(surface, entity, surface.ux, list(appspec.enums))
    status_col = next(col for col in cols if col.key == "status")
    assert status_col.type == "badge"
    assert status_col.semantic_map == {"open": "warning", "done": "positive"}


def test_column_semantic_map_from_inline_field_binding() -> None:
    # An inline `semantic:` on the field itself populates the column map too.
    from dazzle.page.converters.template_compiler import _build_columns

    appspec = _appspec(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
    semantic: open=warning, done=positive
surface tasks "Tasks":
  uses entity Task
  mode: list
  section main:
    field status "Status"
"""
    )
    entity = next(e for e in appspec.domain.entities if e.name == "Task")
    surface = next(s for s in appspec.surfaces if s.name == "tasks")
    cols = _build_columns(surface, entity, surface.ux, list(appspec.enums))
    status_col = next(col for col in cols if col.key == "status")
    assert status_col.semantic_map == {"open": "warning", "done": "positive"}


def test_htmx_workspace_columns_carry_semantic_map() -> None:
    # The HTMX tbody column path (workspace_columns) is the dominant list-row
    # render; it must carry the declared binding too.
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    appspec = _appspec(
        """module m
app a "A"
enum TaskStatus "Task Status":
  open "Open"
  done "Done"
  semantic: open=warning, done=positive
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
surface tasks "Tasks":
  uses entity Task
  mode: list
  section main:
    field status "Status"
"""
    )
    entity = next(e for e in appspec.domain.entities if e.name == "Task")
    surface = next(s for s in appspec.surfaces if s.name == "tasks")
    cols = build_surface_columns(entity, surface, list(appspec.enums))
    status_col = next(c for c in cols if c["key"] == "status")
    assert status_col["type"] == "badge"
    assert status_col["semantic_map"] == {"open": "warning", "done": "positive"}


def test_htmx_workspace_columns_omit_key_when_undeclared() -> None:
    # No declared semantic: the key is absent (byte-identical col dicts).
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    appspec = _appspec(
        """module m
app a "A"
entity Task "Task":
  id: uuid pk
  status: enum[open, done]
surface tasks "Tasks":
  uses entity Task
  mode: list
  section main:
    field status "Status"
"""
    )
    entity = next(e for e in appspec.domain.entities if e.name == "Task")
    surface = next(s for s in appspec.surfaces if s.name == "tasks")
    cols = build_surface_columns(entity, surface, list(appspec.enums))
    status_col = next(c for c in cols if c["key"] == "status")
    assert "semantic_map" not in status_col


def test_probe_1b_reports_level_4() -> None:
    from dazzle.qa.ux_maturity import CRITERIA

    crit_1b = next(c for c in CRITERIA if c.id == "1b")
    # Level 4 (#1493 slice 2 complete): render consumption + WCAG colour+icon+text
    # + state-machine-terminal inference. The probe asserts all three.
    assert crit_1b.declared == 4
    assert crit_1b.probe().ok  # probe agrees with the declared level (no drift)


# ── validator: tone palette ───────────────────────────────────────────────


def _appspec(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, pathlib.Path("t.dsl"))
    root = n or "t"
    return build_appspec(
        [
            ModuleIR(
                name=root,
                file=pathlib.Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        root,
    )


def test_validator_accepts_canonical_and_alias_tones() -> None:
    from dazzle.core.validation.ux import validate_enum_semantics

    appspec = _appspec(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  c "C"
  semantic: a=success, b=positive, c=neutral
"""
    )
    errors, _ = validate_enum_semantics(appspec)
    assert errors == []


def test_validator_rejects_unknown_tone() -> None:
    from dazzle.core.validation.ux import validate_enum_semantics

    appspec = _appspec(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  semantic: a=success, b=turquoise
"""
    )
    errors, _ = validate_enum_semantics(appspec)
    assert any("E_SEMANTIC_TONE_UNKNOWN" in e and "turquoise" in e for e in errors)
