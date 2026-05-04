"""Tests for DazzleAdapter.resolve_view_url (#469)."""

import pytest

from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter


@pytest.fixture
def adapter() -> DazzleAdapter:
    return DazzleAdapter(base_url="http://localhost:3000")


class TestResolveViewUrl:
    """Verify view IDs resolve to correct /app/ prefixed URLs."""

    @pytest.mark.parametrize(
        ("view_id", "expected_url"),
        [
            # Simple entity list.
            ("trust_list", "http://localhost:3000/app/trust"),
            # Compound entity list (snake_case → CamelCase slug).
            ("exam_board_list", "http://localhost:3000/app/examboard"),
            # Compound entity create.
            ("exam_board_create", "http://localhost:3000/app/examboard/create"),
            # Simple entity detail.
            ("task_detail", "http://localhost:3000/app/task/{id}"),
            # Compound entity edit.
            ("mark_scheme_edit", "http://localhost:3000/app/markscheme/{id}/edit"),
            # Simple entity create.
            ("task_create", "http://localhost:3000/app/task/create"),
            # Review mode.
            ("invoice_review", "http://localhost:3000/app/invoice/review/{id}"),
            # Non-mode view IDs fall back to slash-separated path.
            ("admin_dashboard", "http://localhost:3000/app/admin/dashboard"),
        ],
        ids=[
            "test_simple_entity_list",
            "test_compound_entity_list",
            "test_compound_entity_create",
            "test_simple_entity_detail",
            "test_compound_entity_edit",
            "test_simple_entity_create",
            "test_review_mode",
            "test_dashboard_route",
        ],
    )
    def test_resolve_view_url(
        self, adapter: DazzleAdapter, view_id: str, expected_url: str
    ) -> None:
        """View IDs resolve to correct /app/ prefixed URLs."""
        assert adapter.resolve_view_url(view_id) == expected_url
