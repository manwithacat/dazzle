"""
Drift gate for the DSL-constructs API surface (cycle 1 of #961).

The on-disk baseline at `docs/api-surface/dsl-constructs.txt` pins every
parser-dispatched DSL construct, the fragment field(s) it writes into, and
the required/optional fields of every IR class produced. Any deviation is
caught here.

To accept drift:
  1. Run: `dazzle inspect-api dsl-constructs --write`
  2. Review the diff
  3. Add a CHANGELOG entry under Added / Changed / Removed
  4. Commit the regenerated baseline
"""

from dazzle.api_surface import (
    BASELINE_PATH,
    diff_against_baseline,
    snapshot_dsl_constructs,
)


def test_baseline_exists():
    assert BASELINE_PATH.exists(), (
        f"Missing baseline at {BASELINE_PATH}. "
        "Run `dazzle inspect-api dsl-constructs --write` to create it."
    )


def test_dsl_constructs_match_baseline():
    """Live snapshot must match the committed baseline byte-for-byte."""
    diff = diff_against_baseline()
    assert not diff, (
        "DSL-constructs API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api dsl-constructs --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/dsl-constructs.txt\n"
    )


def test_snapshot_is_deterministic():
    """Two calls in the same process must return identical output."""
    a = snapshot_dsl_constructs()
    b = snapshot_dsl_constructs()
    assert a == b, "snapshot_dsl_constructs() is not deterministic"


def test_snapshot_includes_known_constructs():
    """Spot-check that load-bearing constructs appear in the snapshot."""
    snapshot = snapshot_dsl_constructs()
    for construct in ("entity", "surface", "workspace", "process", "story"):
        assert f"construct: {construct}\n" in snapshot, f"Missing construct: {construct}"
    for ir_class in ("EntitySpec", "SurfaceSpec", "WorkspaceSpec", "ProcessSpec", "StorySpec"):
        assert f"ir_class: {ir_class}\n" in snapshot, f"Missing ir_class: {ir_class}"
