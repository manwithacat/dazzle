"""FragmentRenderer — package facade.

This package was a single 3,784-line file (`renderer.py`) until v0.67.136.
The full implementation now lives in `_emit.py`; this `__init__.py`
preserves every existing import path by re-exporting the public surface.

External importers (current — keep this list in sync if you add more):

  src/dazzle/render/fragment/__init__.py
    → FragmentRenderer

  src/dazzle/http/runtime/exception_handlers.py
    → FragmentRenderer (2 lazy import sites)

  src/dazzle/http/runtime/site_routes.py
    → FragmentRenderer (11 lazy import sites)

  src/dazzle/http/runtime/renderers/page_builder.py
    → FragmentRenderer (lazy)

  src/dazzle/http/runtime/renderers/fragment.py
    → FragmentRenderer (module-level)

  src/dazzle/documents/api.py
    → FragmentRenderer

  tests/unit/test_*.py (multiple)
    → FragmentRenderer (and one test imports `_load_static`)

The decomposition into per-primitive-family modules (shell, layout,
interactive, tables, charts, forms, dashboard) happens in follow-up
PRs against issue #1064. Each subsequent PR moves one family out of
`_emit.py` into its own `_render_<family>.py` module.

Pattern mirrors `region_adapter` (#1065, completed in v0.67.135) —
mixins per family inherited by the dispatcher class, with public
re-exports here.
"""

from dazzle.render.fragment.renderer._emit import FragmentRenderer
from dazzle.render.fragment.renderer._render_shell import (
    _WORKSPACE_CONTEXT_SCRIPT_TEMPLATE,
    _WORKSPACE_DRAWER_HTML,
    _load_static,
)

__all__ = [
    "FragmentRenderer",
    "_WORKSPACE_CONTEXT_SCRIPT_TEMPLATE",
    "_WORKSPACE_DRAWER_HTML",
    "_load_static",
]
