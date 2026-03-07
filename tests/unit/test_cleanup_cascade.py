"""Tests for cascade-delete during test cleanup (#407)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.testing.test_runner import DazzleClient


@pytest.fixture
def client() -> DazzleClient:
    return DazzleClient(api_url="http://localhost:8000", ui_url="http://localhost:3000")


# ── FK reverse map ──────────────────────────────────────────────────────


class TestBuildFkReverseMap:
    def test_empty_spec(self, client: DazzleClient) -> None:
        client.get_spec = MagicMock(return_value=None)  # type: ignore[method-assign]
        assert client._build_fk_reverse_map() == {}

    def test_entities_at_top_level(self, client: DazzleClient) -> None:
        """Spec with entities at the top level (list endpoint format)."""
        client.get_spec = MagicMock(
            return_value={  # type: ignore[method-assign]
                "entities": [
                    {
                        "name": "PropertyIncome",
                        "fields": [
                            {"name": "id", "type": {"kind": "uuid"}},
                            {"name": "owner", "type": {"kind": "ref", "ref_entity": "SoleTrader"}},
                        ],
                    },
                    {
                        "name": "SoleTrader",
                        "fields": [
                            {"name": "id", "type": {"kind": "uuid"}},
                            {"name": "name", "type": {"kind": "str"}},
                        ],
                    },
                ]
            }
        )
        fk_map = client._build_fk_reverse_map()
        assert "SoleTrader" in fk_map
        assert ("PropertyIncome", "owner") in fk_map["SoleTrader"]
        assert "PropertyIncome" not in fk_map

    def test_entities_in_domain(self, client: DazzleClient) -> None:
        """Spec with entities under domain.entities (full spec format)."""
        client.get_spec = MagicMock(
            return_value={  # type: ignore[method-assign]
                "domain": {
                    "entities": [
                        {
                            "name": "Invoice",
                            "fields": [
                                {"name": "id", "type": {"kind": "uuid"}},
                                {
                                    "name": "customer",
                                    "type": {"kind": "ref", "ref_entity": "Customer"},
                                },
                            ],
                        },
                    ]
                }
            }
        )
        fk_map = client._build_fk_reverse_map()
        assert fk_map == {"Customer": [("Invoice", "customer")]}

    def test_multiple_children(self, client: DazzleClient) -> None:
        """Multiple entities referencing the same parent."""
        client.get_spec = MagicMock(
            return_value={  # type: ignore[method-assign]
                "entities": [
                    {
                        "name": "PropertyIncome",
                        "fields": [
                            {"name": "owner", "type": {"kind": "ref", "ref_entity": "SoleTrader"}},
                        ],
                    },
                    {
                        "name": "TaxLoss",
                        "fields": [
                            {"name": "owner", "type": {"kind": "ref", "ref_entity": "SoleTrader"}},
                        ],
                    },
                    {
                        "name": "DividendIncome",
                        "fields": [
                            {"name": "owner", "type": {"kind": "ref", "ref_entity": "SoleTrader"}},
                        ],
                    },
                ]
            }
        )
        fk_map = client._build_fk_reverse_map()
        children = fk_map["SoleTrader"]
        assert len(children) == 3
        child_names = {c[0] for c in children}
        assert child_names == {"PropertyIncome", "TaxLoss", "DividendIncome"}


# ── Cascade delete ──────────────────────────────────────────────────────


class TestCascadeDeleteChildren:
    def test_no_children(self, client: DazzleClient) -> None:
        """Entity with no FK references has nothing to cascade."""
        deleted = client._cascade_delete_children("SoleTrader", "abc-123", {})
        assert deleted == 0

    def test_deletes_matching_children(self, client: DazzleClient) -> None:
        """Deletes child records whose FK matches the parent ID."""
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client.get_entities = MagicMock(
            return_value=[  # type: ignore[method-assign]
                {"id": "pi-1", "owner": "st-1", "amount": 1000},
                {"id": "pi-2", "owner": "st-2", "amount": 2000},  # different parent
            ]
        )
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted = client._cascade_delete_children("SoleTrader", "st-1", fk_map)
        assert deleted == 1
        client.delete_entity.assert_called_once_with("PropertyIncome", "pi-1")

    def test_matches_fk_field_with_id_suffix(self, client: DazzleClient) -> None:
        """Also matches field_id pattern (e.g. owner_id instead of owner)."""
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client.get_entities = MagicMock(
            return_value=[  # type: ignore[method-assign]
                {"id": "pi-1", "owner_id": "st-1", "amount": 1000},
            ]
        )
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted = client._cascade_delete_children("SoleTrader", "st-1", fk_map)
        assert deleted == 1

    def test_recursive_grandchildren(self, client: DazzleClient) -> None:
        """Cascades into grandchildren (child of child)."""
        fk_map = {
            "Company": [("Department", "company")],
            "Department": [("Employee", "department")],
        }

        def mock_get_entities(entity_name: str) -> list[dict]:
            if entity_name == "Department":
                return [{"id": "dept-1", "company": "co-1"}]
            if entity_name == "Employee":
                return [{"id": "emp-1", "department": "dept-1"}]
            return []

        client.get_entities = MagicMock(side_effect=mock_get_entities)  # type: ignore[method-assign]
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted = client._cascade_delete_children("Company", "co-1", fk_map)
        assert deleted == 2  # employee + department
        # Employee deleted before Department (grandchild before child)
        calls = client.delete_entity.call_args_list
        assert calls[0].args == ("Employee", "emp-1")
        assert calls[1].args == ("Department", "dept-1")

    def test_handles_delete_failure_gracefully(self, client: DazzleClient) -> None:
        """Failed child deletion doesn't crash — just skips."""
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client.get_entities = MagicMock(
            return_value=[  # type: ignore[method-assign]
                {"id": "pi-1", "owner": "st-1"},
            ]
        )
        client.delete_entity = MagicMock(return_value=False)  # type: ignore[method-assign]

        # Doesn't raise, returns 0 (delete_entity returned False)
        deleted = client._cascade_delete_children("SoleTrader", "st-1", fk_map)
        assert deleted == 0

    def test_handles_get_entities_exception(self, client: DazzleClient) -> None:
        """Exception during child query doesn't crash."""
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client.get_entities = MagicMock(side_effect=Exception("Network error"))  # type: ignore[method-assign]

        deleted = client._cascade_delete_children("SoleTrader", "st-1", fk_map)
        assert deleted == 0


# ── Full cleanup integration ────────────────────────────────────────────


class TestCleanupCreatedEntities:
    def test_empty_list(self, client: DazzleClient) -> None:
        deleted, failed = client.cleanup_created_entities()
        assert deleted == 0
        assert failed == 0

    def test_cascades_before_parent_delete(self, client: DazzleClient) -> None:
        """Cleanup cascade-deletes children before attempting parent deletion."""
        client._created_entities = [("SoleTrader", "st-1")]

        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client._build_fk_reverse_map = MagicMock(return_value=fk_map)  # type: ignore[method-assign]
        client.get_entities = MagicMock(
            return_value=[  # type: ignore[method-assign]
                {"id": "pi-1", "owner": "st-1"},
                {"id": "pi-2", "owner": "st-1"},
            ]
        )
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted, failed = client.cleanup_created_entities()
        assert deleted == 3  # 2 children + 1 parent
        assert failed == 0

        # Children deleted before parent
        calls = [c.args for c in client.delete_entity.call_args_list]
        pi_calls = [c for c in calls if c[0] == "PropertyIncome"]
        st_calls = [c for c in calls if c[0] == "SoleTrader"]
        assert len(pi_calls) == 2
        assert len(st_calls) == 1
        # All PropertyIncome calls come before the SoleTrader call
        pi_indices = [i for i, c in enumerate(calls) if c[0] == "PropertyIncome"]
        st_index = next(i for i, c in enumerate(calls) if c[0] == "SoleTrader")
        assert all(pi_idx < st_index for pi_idx in pi_indices)

    def test_builds_fk_map_once(self, client: DazzleClient) -> None:
        """FK map is fetched once, not per entity."""
        client._created_entities = [("A", "1"), ("B", "2")]
        client._build_fk_reverse_map = MagicMock(return_value={})  # type: ignore[method-assign]
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        client.cleanup_created_entities()
        client._build_fk_reverse_map.assert_called_once()

    def test_multi_pass_on_failure(self, client: DazzleClient) -> None:
        """Entities that fail deletion are retried in subsequent passes."""
        client._created_entities = [("A", "1")]
        client._build_fk_reverse_map = MagicMock(return_value={})  # type: ignore[method-assign]

        # Fail first attempt, succeed on second
        client.delete_entity = MagicMock(side_effect=[False, True])  # type: ignore[method-assign]

        deleted, failed = client.cleanup_created_entities()
        assert deleted == 1
        assert failed == 0
