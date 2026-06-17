"""WorkspaceRegion → Fragment primitive adapter — package facade.

This package was a single 2,871-line file (`region_adapter.py`) until v0.67.128.
The full implementation now lives in `_dispatcher.py`; this `__init__.py`
preserves every existing import path by re-exporting the public surface.

External importers (current — keep this list in sync if you add more):

  src/dazzle/back/runtime/workspace_region_render.py
    → WorkspaceRegionAdapter (lazy import)

  src/dazzle/render/fragment/renderer.py
    → _render_status_badge_html (4 lazy import sites)

  tests/unit/test_region_adapter.py
    → WorkspaceRegionAdapter

  tests/unit/render/fragment/test_coverage.py
    → WorkspaceRegionAdapter

The decomposition into per-display-family modules (cards, charts,
tables, timeline, metrics, misc) happens in follow-up PRs against
issue #1065. Each subsequent PR moves one family out of `_dispatcher.py`
into its own `_builders_<family>.py` module.
"""

from dazzle.render.fragment.region._dispatcher import (
    WorkspaceRegionAdapter,
)
from dazzle.render.fragment.region._shared import (
    _render_status_badge_html,
)

__all__ = [
    "WorkspaceRegionAdapter",
    "_render_status_badge_html",
]
