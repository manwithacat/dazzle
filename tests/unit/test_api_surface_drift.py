"""
Drift gate for the framework's public API surface (#961).

Each on-disk baseline under `docs/api-surface/` pins one lens of the public
surface. Any deviation between live state and baseline is caught here.

To accept drift on any cycle:
  1. Run: `dazzle inspect-api <subcommand> --write`
  2. Review the diff
  3. Add a CHANGELOG entry under Added / Changed / Removed
  4. Commit the regenerated baseline
"""

from dazzle.api_surface import dsl_constructs_module as dsl_mod
from dazzle.api_surface import ir_types_module as ir_mod

# ───────────────────────── Cycle 1: DSL constructs ─────────────────────────


def test_dsl_constructs_baseline_exists():
    assert dsl_mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {dsl_mod.BASELINE_PATH}. "
        "Run `dazzle inspect-api dsl-constructs --write` to create it."
    )


def test_dsl_constructs_match_baseline():
    diff = dsl_mod.diff_against_baseline()
    assert not diff, (
        "DSL-constructs API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api dsl-constructs --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/dsl-constructs.txt\n"
    )


def test_dsl_constructs_snapshot_is_deterministic():
    a = dsl_mod.snapshot_dsl_constructs()
    b = dsl_mod.snapshot_dsl_constructs()
    assert a == b, "snapshot_dsl_constructs() is not deterministic"


def test_dsl_constructs_includes_known_constructs():
    snapshot = dsl_mod.snapshot_dsl_constructs()
    for construct in ("entity", "surface", "workspace", "process", "story"):
        assert f"construct: {construct}\n" in snapshot, f"Missing construct: {construct}"


# ───────────────────────── Cycle 2: IR types ─────────────────────────


def test_ir_types_baseline_exists():
    assert ir_mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {ir_mod.BASELINE_PATH}. "
        "Run `dazzle inspect-api ir-types --write` to create it."
    )


def test_ir_types_match_baseline():
    diff = ir_mod.diff_against_baseline()
    assert not diff, (
        "IR-types API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api ir-types --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/ir-types.txt\n"
    )


def test_ir_types_snapshot_is_deterministic():
    a = ir_mod.snapshot_ir_types()
    b = ir_mod.snapshot_ir_types()
    assert a == b, "snapshot_ir_types() is not deterministic"


def test_ir_types_includes_known_types():
    snapshot = ir_mod.snapshot_ir_types()
    for cls in ("EntitySpec", "SurfaceSpec", "WorkspaceSpec", "ProcessSpec", "StorySpec"):
        assert f"ir_class: {cls}\n" in snapshot, f"Missing ir_class: {cls}"
    for enum_name in ("FieldTypeKind", "ArchetypeKind"):
        assert f"enum: {enum_name}\n" in snapshot, f"Missing enum: {enum_name}"
