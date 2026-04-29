"""
API surface introspection — for the breaking-change pass tooling (#961).

Each cycle adds a snapshotable lens on the framework's public surface. The
snapshots are committed to `docs/api-surface/`; drift between live state
and baseline is caught by `tests/unit/test_api_surface_drift.py`, forcing
every breaking change to be a conscious, CHANGELOG-recorded decision.

Cycles:
- Cycle 1 (`dsl_constructs`) — DSL constructs → IR class mapping
- Cycle 2 (`ir_types`) — every IR type re-exported from `dazzle.core.ir`
- Cycle 3+ — MCP tool schemas, public helpers, runtime URLs (open on #961)
"""

from . import dsl_constructs as dsl_constructs_module
from . import ir_types as ir_types_module
from . import mcp_tools as mcp_tools_module
from . import public_helpers as public_helpers_module
from . import runtime_urls as runtime_urls_module
from .dsl_constructs import (
    BASELINE_PATH,
    diff_against_baseline,
    snapshot_dsl_constructs,
)
from .ir_types import (
    snapshot_ir_types,
)
from .mcp_tools import (
    snapshot_mcp_tools,
)
from .public_helpers import (
    snapshot_public_helpers,
)
from .runtime_urls import (
    snapshot_runtime_urls,
)

__all__ = [
    "BASELINE_PATH",
    "diff_against_baseline",
    "dsl_constructs_module",
    "ir_types_module",
    "mcp_tools_module",
    "public_helpers_module",
    "runtime_urls_module",
    "snapshot_dsl_constructs",
    "snapshot_ir_types",
    "snapshot_mcp_tools",
    "snapshot_public_helpers",
    "snapshot_runtime_urls",
]
