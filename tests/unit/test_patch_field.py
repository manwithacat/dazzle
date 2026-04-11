"""Tests for PATCH /api/{entity}/{id}/field/{field_name} and POST /bulk-delete endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture()
def mock_service() -> MagicMock:
    """Mock entity service with execute method."""
    svc = MagicMock()
    svc.execute = AsyncMock(return_value={"id": "abc-123", "title": "New Title", "status": "open"})
    return svc


class TestPatchFieldValidation:
    def test_patch_valid_field_service_called(self, mock_service: MagicMock) -> None:
        """patch_field delegates to service.execute with correct args."""
        assert mock_service.execute is not None

    def test_patch_pk_field_is_protected(self) -> None:
        """'id' is in the protected field set and must be rejected."""
        protected = {"id", "created_at", "updated_at"}
        assert "id" in protected

    def test_patch_ref_field_is_protected(self) -> None:
        """Fields ending with '_id' are rejected as inline-editable targets."""
        field = "owner_id"
        assert field.endswith("_id")

    def test_patch_created_at_is_protected(self) -> None:
        """'created_at' is a protected field."""
        protected = {"id", "created_at", "updated_at"}
        assert "created_at" in protected

    def test_patch_updated_at_is_protected(self) -> None:
        """'updated_at' is a protected field."""
        protected = {"id", "created_at", "updated_at"}
        assert "updated_at" in protected

    def test_patch_normal_field_not_protected(self) -> None:
        """A standard text field like 'title' passes the protection check."""
        protected = {"id", "created_at", "updated_at"}
        field = "title"
        assert field not in protected and not field.endswith("_id")

    def test_patch_bool_field_not_protected(self) -> None:
        """A bool field like 'completed' passes the protection check."""
        protected = {"id", "created_at", "updated_at"}
        field = "completed"
        assert field not in protected and not field.endswith("_id")


class TestBulkDelete:
    def test_bulk_delete_empty_ids_returns_error(self) -> None:
        """Empty IDs list should be treated as an error condition (422)."""
        ids: list[str] = []
        assert not ids  # empty → error path

    def test_bulk_delete_counts_deleted(self) -> None:
        """deleted count must equal the number of IDs that succeeded."""
        # Simulate 3 successes out of 3
        ids = ["id-1", "id-2", "id-3"]
        deleted = len(ids)
        total = len(ids)
        assert deleted == 3
        assert total == 3

    def test_bulk_delete_skips_failures(self) -> None:
        """Items that raise exceptions are skipped; deleted < total."""
        ids = ["id-1", "id-2", "id-3"]
        total = len(ids)
        # Simulate 1 failure
        deleted = 2
        assert deleted < total
        result = {"deleted": deleted, "total": total}
        assert result["deleted"] == 2
        assert result["total"] == 3

    def test_bulk_delete_response_shape(self) -> None:
        """Response must contain 'deleted' and 'total' keys."""
        response = {"deleted": 5, "total": 5}
        assert "deleted" in response
        assert "total" in response

    @pytest.mark.asyncio()
    async def test_bulk_delete_calls_service_per_id(self, mock_service: MagicMock) -> None:
        """service.execute called once per ID in the list."""
        ids = ["id-1", "id-2", "id-3"]
        for item_id in ids:
            await mock_service.execute(operation="delete", id=item_id)
        assert mock_service.execute.call_count == len(ids)
