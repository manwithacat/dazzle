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
from dazzle.api_surface import mcp_tools_module as mcp_mod
from dazzle.api_surface import public_helpers_module as helpers_mod
from dazzle.api_surface import runtime_urls_module as urls_mod

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


# ───────────────────────── Cycle 3: MCP tools ─────────────────────────


def test_mcp_tools_baseline_exists():
    assert mcp_mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {mcp_mod.BASELINE_PATH}. "
        "Run `dazzle inspect-api mcp-tools --write` to create it."
    )


def test_mcp_tools_match_baseline():
    diff = mcp_mod.diff_against_baseline()
    assert not diff, (
        "MCP-tools API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api mcp-tools --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/mcp-tools.txt\n"
    )


def test_mcp_tools_snapshot_is_deterministic():
    a = mcp_mod.snapshot_mcp_tools()
    b = mcp_mod.snapshot_mcp_tools()
    assert a == b, "snapshot_mcp_tools() is not deterministic"


def test_mcp_tools_includes_known_tools():
    snapshot = mcp_mod.snapshot_mcp_tools()
    for tool in ("dsl", "graph", "knowledge", "story", "rhythm", "discovery"):
        assert f"tool: {tool}\n" in snapshot, f"Missing tool: {tool}"


# ───────────────────────── Cycle 4: public helpers ─────────────────────────


def test_public_helpers_baseline_exists():
    assert helpers_mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {helpers_mod.BASELINE_PATH}. "
        "Run `dazzle inspect-api public-helpers --write` to create it."
    )


def test_public_helpers_match_baseline():
    diff = helpers_mod.diff_against_baseline()
    assert not diff, (
        "Public-helpers API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api public-helpers --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/public-helpers.txt\n"
    )


def test_public_helpers_snapshot_is_deterministic():
    a = helpers_mod.snapshot_public_helpers()
    b = helpers_mod.snapshot_public_helpers()
    assert a == b, "snapshot_public_helpers() is not deterministic"


def test_public_helpers_includes_known_packages():
    snapshot = helpers_mod.snapshot_public_helpers()
    for pkg in ("dazzle", "dazzle_back", "dazzle_ui"):
        assert f"package: {pkg}\n" in snapshot, f"Missing package: {pkg}"
    for export in ("DazzleError", "ParseError", "UISpec"):
        assert export in snapshot, f"Missing export: {export}"


# ───────────────────────── Cycle 5: runtime URLs ─────────────────────────


def test_runtime_urls_baseline_exists():
    assert urls_mod.BASELINE_PATH.exists(), (
        f"Missing baseline at {urls_mod.BASELINE_PATH}. "
        "Run `dazzle inspect-api runtime-urls --write` to create it."
    )


def test_runtime_urls_match_baseline():
    diff = urls_mod.diff_against_baseline()
    assert not diff, (
        "Runtime-URLs API surface drifted from the baseline.\n\n"
        f"{diff}\n\n"
        "If this drift is intentional:\n"
        "  1. Run: dazzle inspect-api runtime-urls --write\n"
        "  2. Review the diff above\n"
        "  3. Add a CHANGELOG entry under Added / Changed / Removed\n"
        "  4. Commit the regenerated docs/api-surface/runtime-urls.txt\n"
    )


def test_runtime_urls_snapshot_is_deterministic():
    a = urls_mod.snapshot_runtime_urls()
    b = urls_mod.snapshot_runtime_urls()
    assert a == b, "snapshot_runtime_urls() is not deterministic"


def test_runtime_urls_includes_known_modules():
    snapshot = urls_mod.snapshot_runtime_urls()
    for module in ("admin_api_routes", "audit_routes", "search_routes"):
        assert f"module: {module}\n" in snapshot, f"Missing module: {module}"


def test_runtime_urls_no_trailing_whitespace():
    """Pre-commit strips trailing whitespace; the snapshot must match post-strip."""
    snapshot = urls_mod.snapshot_runtime_urls()
    for i, line in enumerate(snapshot.splitlines(), 1):
        assert line == line.rstrip(), f"Line {i} has trailing whitespace: {line!r}"
