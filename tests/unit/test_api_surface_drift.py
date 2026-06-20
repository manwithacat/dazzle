"""
Drift gate for the framework's public API surface (#961).

Each on-disk baseline under `docs/api-surface/` pins one lens of the public
surface. Any deviation between live state and baseline is caught here.

To accept drift on any cycle:
  1. Run: `dazzle inspect api <subcommand> --write`
  2. Review the diff
  3. Add a CHANGELOG entry under Added / Changed / Removed
  4. Commit the regenerated baseline

(Renamed from `dazzle inspect-api` in #1120 — see `dazzle inspect --help` for
the full inspect command tree, which now also covers renderers / primitives /
routes / oauth-providers.)
"""

import pytest

from dazzle.api_surface import dsl_constructs_module as dsl_mod
from dazzle.api_surface import ir_types_module as ir_mod
from dazzle.api_surface import mcp_tools_module as mcp_mod
from dazzle.api_surface import public_helpers_module as helpers_mod
from dazzle.api_surface import runtime_urls_module as urls_mod

# ---------------------------------------------------------------------------
# Per-cycle module registry — drives the three uniform structural checks
# ---------------------------------------------------------------------------

_CYCLES = [
    pytest.param(dsl_mod, id="dsl_constructs"),
    pytest.param(ir_mod, id="ir_types"),
    pytest.param(mcp_mod, id="mcp_tools"),
    pytest.param(helpers_mod, id="public_helpers"),
    pytest.param(urls_mod, id="runtime_urls"),
]


@pytest.mark.parametrize("mod", _CYCLES)
def test_baseline_exists(mod) -> None:
    """Every API-surface module must have a committed baseline file."""
    assert mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {mod.BASELINE_PATH}. "
        f"Run `dazzle inspect api {mod.BASELINE_PATH.stem} --write` to create it."
    )


@pytest.mark.parametrize("mod", _CYCLES)
def test_surface_matches_baseline(mod) -> None:
    """Live API surface must exactly match the committed baseline."""
    diff = mod.diff_against_baseline()
    assert not diff, (
        f"API surface drifted from the baseline ({mod.BASELINE_PATH.name}).\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        f"  1. Run: dazzle inspect api {mod.BASELINE_PATH.stem} --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        f"  4. Commit the regenerated {mod.BASELINE_PATH}\n"
    )


@pytest.mark.parametrize(
    "mod,snapshot_fn",
    [
        pytest.param(dsl_mod, lambda: dsl_mod.snapshot_dsl_constructs(), id="dsl_constructs"),
        pytest.param(ir_mod, lambda: ir_mod.snapshot_ir_types(), id="ir_types"),
        pytest.param(mcp_mod, lambda: mcp_mod.snapshot_mcp_tools(), id="mcp_tools"),
        pytest.param(
            helpers_mod, lambda: helpers_mod.snapshot_public_helpers(), id="public_helpers"
        ),
        pytest.param(urls_mod, lambda: urls_mod.snapshot_runtime_urls(), id="runtime_urls"),
    ],
)
def test_snapshot_is_deterministic(mod, snapshot_fn) -> None:
    """Snapshot functions must be pure — two consecutive calls must return identical text."""
    a = snapshot_fn()
    b = snapshot_fn()
    assert a == b, f"snapshot function for {mod.BASELINE_PATH.stem} is not deterministic"


# ---------------------------------------------------------------------------
# Cycle 1: DSL constructs — content checks
# ---------------------------------------------------------------------------


def test_dsl_constructs_includes_known_constructs():
    snapshot = dsl_mod.snapshot_dsl_constructs()
    for construct in ("entity", "surface", "workspace", "process", "story"):
        assert f"construct: {construct}\n" in snapshot, f"Missing construct: {construct}"


# ---------------------------------------------------------------------------
# Cycle 2: IR types — content checks
# ---------------------------------------------------------------------------


def test_ir_types_includes_known_types():
    snapshot = ir_mod.snapshot_ir_types()
    for cls in ("EntitySpec", "SurfaceSpec", "WorkspaceSpec", "ProcessSpec", "StorySpec"):
        assert f"ir_class: {cls}\n" in snapshot, f"Missing ir_class: {cls}"
    for enum_name in ("FieldTypeKind", "ArchetypeKind"):
        assert f"enum: {enum_name}\n" in snapshot, f"Missing enum: {enum_name}"


# ---------------------------------------------------------------------------
# Cycle 3: MCP tools — content checks
# ---------------------------------------------------------------------------


def test_mcp_tools_includes_known_tools():
    snapshot = mcp_mod.snapshot_mcp_tools()
    for tool in ("dsl", "graph", "knowledge", "story", "rhythm", "discovery"):
        assert f"tool: {tool}\n" in snapshot, f"Missing tool: {tool}"


# ---------------------------------------------------------------------------
# Cycle 4: public helpers — content checks
# ---------------------------------------------------------------------------


def test_public_helpers_includes_known_packages():
    snapshot = helpers_mod.snapshot_public_helpers()
    for pkg in ("dazzle", "dazzle.http", "dazzle.page"):
        assert f"package: {pkg}\n" in snapshot, f"Missing package: {pkg}"
    for export in ("DazzleError", "ParseError", "UISpec"):
        assert export in snapshot, f"Missing export: {export}"


# ---------------------------------------------------------------------------
# Cycle 5: runtime URLs — content checks + format
# ---------------------------------------------------------------------------


def test_runtime_urls_includes_known_modules():
    snapshot = urls_mod.snapshot_runtime_urls()
    for module in ("admin_api_routes", "audit_routes", "search_routes"):
        assert f"module: {module}\n" in snapshot, f"Missing module: {module}"


def test_runtime_urls_includes_atomic_flow_dynamic_route():
    """The dynamically-registered atomic-flow surface (#1314) must be captured.

    `atomic_flow_routes.py` registers `POST /api/atomic/<flow>` via
    `add_api_route`, which the AST decorator walk can't see; the curated
    `_DYNAMIC_ROUTES` entry pins it as a `{flow_name}` pattern.
    """
    snapshot = urls_mod.snapshot_runtime_urls()
    assert "module: atomic_flow_routes\n" in snapshot, "Missing atomic_flow_routes module"
    assert "POST | /api/atomic/{flow_name}" in snapshot, "Missing atomic-flow pattern route"


def test_runtime_urls_no_trailing_whitespace():
    """Pre-commit strips trailing whitespace; the snapshot must match post-strip."""
    snapshot = urls_mod.snapshot_runtime_urls()
    for i, line in enumerate(snapshot.splitlines(), 1):
        assert line == line.rstrip(), f"Line {i} has trailing whitespace: {line!r}"
