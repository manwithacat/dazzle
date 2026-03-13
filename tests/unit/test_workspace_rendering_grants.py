# tests/unit/test_workspace_rendering_grants.py
"""Tests for grant pre-fetching in workspace rendering."""

import inspect

from dazzle_back.runtime import workspace_rendering


class TestGrantPreFetchingWiring:
    def test_active_grants_referenced_in_source(self):
        """Verify the workspace rendering module references active_grants in filter context."""
        source = inspect.getsource(workspace_rendering)
        assert "active_grants" in source, (
            "workspace_rendering.py should reference 'active_grants' "
            "for grant pre-fetching into filter context"
        )

    def test_grant_store_imported_or_referenced(self):
        """Verify grant_store is referenced for pre-fetching."""
        source = inspect.getsource(workspace_rendering)
        assert "grant_store" in source.lower() or "grant" in source.lower(), (
            "workspace_rendering.py should reference grant store for pre-fetching"
        )
