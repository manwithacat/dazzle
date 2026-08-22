"""List/queue temperature cells must not dump a unitless decimal (oral #174)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.page.converters.template_compiler import _field_type_to_column_type
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.temperature_cell import (
    clerk_temperature_cell_html,
    clerk_temperature_display,
    clerk_temperature_unit,
    temperature_field_name,
)


def _session_temperature_field():
    spec = load_project(Path("examples/fieldtest_hub"))
    session = spec.get_entity("TestSession")
    assert session is not None
    temperature = next(f for f in session.fields if f.name == "temperature")
    surface = next(s for s in spec.surfaces if s.name == "test_session_list")
    return spec, session, temperature, surface


def test_test_session_list_temperature_is_temperature_cell() -> None:
    spec, session, temperature, surface = _session_temperature_field()
    assert temperature_field_name("temperature")
    assert field_kind_to_col_type(temperature, session) == "temperature"
    assert _field_type_to_column_type(temperature, "temperature") == "temperature"
    col = next(
        c for c in build_surface_columns(session, surface, spec.enums) if c["key"] == "temperature"
    )
    assert col["type"] == "temperature"


def test_generic_decimal_is_not_a_temperature_cell() -> None:
    assert not temperature_field_name("humidity")
    assert not temperature_field_name("amount")
    assert not temperature_field_name("score")
    assert not temperature_field_name("template")
    assert not temperature_field_name("attempt")
    assert not temperature_field_name("duration_minutes")
    assert temperature_field_name("temp_c")
    assert temperature_field_name("ambient_temperature")
    assert temperature_field_name("oven_temp_f")


def test_clerk_temperature_split_leftover_and_empty() -> None:
    assert clerk_temperature_unit("temperature") == "°C"
    assert clerk_temperature_unit("temp_f") == "°F"
    assert clerk_temperature_display(22.5, "temperature") == "22.5°C"
    assert clerk_temperature_display(22.0, "temperature") == "22°C"
    assert clerk_temperature_display(28.5, "temperature") == "28.5°C"
    assert clerk_temperature_display(-10, "temp_c") == "-10°C"
    assert clerk_temperature_display(72, "temp_f") == "72°F"
    assert clerk_temperature_display("zzz", "temperature") == "zzz"
    assert clerk_temperature_display("1e2", "temperature") == "1e2"
    assert clerk_temperature_display("", "temperature") == ""
    assert clerk_temperature_display(None, "temperature") == ""
    assert format_cell(22.5, "temperature") == "22.5°C"
    assert format_cell("zzz", "temperature") == "zzz"


def test_list_html_renders_unit_not_bare_decimal() -> None:
    html = _render_cell_display(
        {"key": "temperature", "label": "Temperature", "type": "temperature"},
        28.5,
    )
    assert "dz-temperature" in html
    assert "28.5°C" in html
    leftover = _render_cell_display({"key": "temperature", "type": "temperature"}, "zzz")
    assert "zzz" in leftover
    assert "dz-temperature" not in leftover
    assert "°C" not in leftover
    assert clerk_temperature_cell_html("") == ""
    assert _render_cell_display({"key": "temperature", "type": "temperature"}, "") == "—"


def test_workspace_typed_value_renders_unit() -> None:
    frag = _render_typed_value(
        {"temperature": 22.0},
        {"key": "temperature", "label": "Temperature", "type": "temperature"},
    )
    html = getattr(frag, "html", str(frag))
    assert "dz-temperature" in html
    assert "22°C" in html
    leftover = _render_typed_value(
        {"temperature": "zzz"},
        {"key": "temperature", "type": "temperature"},
    )
    leftover_html = getattr(leftover, "html", str(leftover))
    assert "zzz" in leftover_html
    assert "dz-temperature" not in leftover_html


def test_csv_temperature_has_unit_not_bare_decimal() -> None:
    col = {"key": "temperature", "label": "Temperature", "type": "temperature"}
    assert _csv_cell({"temperature": 28.5}, col) == "28.5°C"
    assert _csv_cell({"temperature": 22.0}, col) == "22°C"
    assert _csv_cell({"temperature": "zzz"}, col) == "zzz"
    assert _csv_cell({"temperature": ""}, col) == ""
    fahrenheit = {"key": "temp_f", "label": "Temp", "type": "temperature"}
    assert _csv_cell({"temp_f": 72}, fahrenheit) == "72°F"
