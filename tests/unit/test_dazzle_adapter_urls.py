"""Tests for DazzleAdapter.resolve_view_url (#469)."""

import pytest

from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter


@pytest.fixture
def adapter() -> DazzleAdapter:
    return DazzleAdapter(base_url="http://localhost:3000")


class TestResolveViewUrl:
    """Verify view IDs resolve to correct /app/ prefixed URLs."""

    def test_simple_entity_list(self, adapter: DazzleAdapter) -> None:
        assert adapter.resolve_view_url("trust_list") == "http://localhost:3000/app/trust"

    def test_compound_entity_list(self, adapter: DazzleAdapter) -> None:
        assert adapter.resolve_view_url("exam_board_list") == "http://localhost:3000/app/examboard"

    def test_compound_entity_create(self, adapter: DazzleAdapter) -> None:
        assert (
            adapter.resolve_view_url("exam_board_create")
            == "http://localhost:3000/app/examboard/create"
        )

    def test_simple_entity_detail(self, adapter: DazzleAdapter) -> None:
        assert adapter.resolve_view_url("task_detail") == "http://localhost:3000/app/task/{id}"

    def test_compound_entity_edit(self, adapter: DazzleAdapter) -> None:
        assert (
            adapter.resolve_view_url("mark_scheme_edit")
            == "http://localhost:3000/app/markscheme/{id}/edit"
        )

    def test_simple_entity_create(self, adapter: DazzleAdapter) -> None:
        assert adapter.resolve_view_url("task_create") == "http://localhost:3000/app/task/create"

    def test_review_mode(self, adapter: DazzleAdapter) -> None:
        assert (
            adapter.resolve_view_url("invoice_review")
            == "http://localhost:3000/app/invoice/review/{id}"
        )

    def test_dashboard_route(self, adapter: DazzleAdapter) -> None:
        """Non-mode view IDs fall back to slash-separated path."""
        url = adapter.resolve_view_url("admin_dashboard")
        assert url == "http://localhost:3000/app/admin/dashboard"
