"""#996 — `dazzle validate` must error on unresolved `source=<pack>.<op>`
field options.

Pre-#996 the runtime resolved field source references lazily and
silently swallowed `ImportError` / `pack not found` exceptions —
typos rendered the field as a plain `<input type="text">` with no
autocomplete and no warning. The fuzz sweep that landed v0.64.5
caught a suspected case in fieldtest_hub (which turned out to be a
false positive — the pack and op both exist), but the validator gap
itself was real: a typo would have shipped silently. This test pins
the new gate.
"""

from __future__ import annotations

from typing import Any

import dazzle.api_kb  # noqa: F401 — #1438: importing api_kb registers the pack-ops

# provider into core's validation registry (core ↛ api_kb), which the source= typo
# check reads. The check is best-effort and self-disables without a provider, so this
# import is what makes the gate active in this direct-call test (was: a lazy
# `from dazzle.api_kb import list_packs` inside validate_surfaces).
from dazzle.core import ir
from dazzle.core.validator import validate_surfaces


def _surface(field_name: str, source_ref: str) -> ir.SurfaceSpec:
    """Minimal surface holding a single field with a source= option."""
    element = ir.SurfaceElement(field_name=field_name, options={"source": source_ref})
    section = ir.SurfaceSection(name="main", title="Main", elements=[element])
    return ir.SurfaceSpec(
        name="probe",
        title="Probe",
        entity_ref=None,  # validator only checks source refs here
        mode=ir.SurfaceMode.CREATE,
        sections=[section],
    )


def _appspec_with(surfaces: list[ir.SurfaceSpec]) -> Any:
    """Stub AppSpec — `validate_surfaces` only reads `.surfaces`."""
    from types import SimpleNamespace

    return SimpleNamespace(surfaces=surfaces, get_entity=lambda _ref: None)


class TestSourceRefValidation:
    def test_known_pack_known_op_passes(self) -> None:
        """Real reference (companies_house_lookup.search_companies) is
        clean — fieldtest_hub's existing usage must keep validating."""
        spec = _appspec_with([_surface("manufacturer", "companies_house_lookup.search_companies")])
        errors, _ = validate_surfaces(spec)
        unresolved = [e for e in errors if "companies_house_lookup" in e]
        assert unresolved == [], f"clean ref errored: {unresolved}"

    def test_unknown_pack_errors(self) -> None:
        """Typo in pack name should fail validate, not just render
        a broken field at runtime."""
        spec = _appspec_with([_surface("supplier", "no_such_pack.find_thing")])
        errors, _ = validate_surfaces(spec)
        assert any("no_such_pack" in e and "no API pack" in e for e in errors), (
            f"unknown pack should error, got: {errors}"
        )

    def test_unknown_op_on_known_pack_errors(self) -> None:
        """Typo in operation name should fail validate."""
        spec = _appspec_with([_surface("manufacturer", "companies_house_lookup.no_such_op")])
        errors, _ = validate_surfaces(spec)
        assert any("no_such_op" in e and "is not defined on pack" in e for e in errors), (
            f"unknown op should error, got: {errors}"
        )

    def test_no_source_option_skips_check(self) -> None:
        """Fields without a source= option don't trip the gate."""
        element = ir.SurfaceElement(field_name="title", options={})
        section = ir.SurfaceSection(name="main", title="Main", elements=[element])
        surface = ir.SurfaceSpec(
            name="t", title="T", mode=ir.SurfaceMode.CREATE, sections=[section]
        )
        errors, _ = validate_surfaces(_appspec_with([surface]))
        assert not any("source" in e for e in errors)
