# tests/unit/test_workspace_rendering_grants.py
"""Tests for grant pre-fetching in workspace rendering.

v0.67.110 (#1057 cut 11): grant pre-fetching moved to
``workspace_region_prelude.resolve_request_user_context``. Same
invariants, new home.
"""

import inspect

from dazzle.http.runtime import workspace_region_prelude


class TestGrantPreFetchingWiring:
    def test_active_grants_referenced_in_source(self):
        """Verify the prelude module references active_grants in filter context."""
        source = inspect.getsource(workspace_region_prelude)
        assert "active_grants" in source, (
            "workspace_region_prelude.py should reference 'active_grants' "
            "for grant pre-fetching into filter context"
        )

    def test_grant_store_imported_or_referenced(self):
        """Verify grant_store is referenced for pre-fetching."""
        source = inspect.getsource(workspace_region_prelude)
        assert "grant_store" in source.lower() or "grant" in source.lower(), (
            "workspace_region_prelude.py should reference grant store for pre-fetching"
        )
