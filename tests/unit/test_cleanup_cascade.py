"""Tests for dependency-safe cleanup during test runs (#407, #410)."""

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


# ── Topological sort for delete ─────────────────────────────────────────


class TestTopoSortForDelete:
    def test_no_fk_relations(self, client: DazzleClient) -> None:
        """Without FK relations, returns reverse creation order (LIFO)."""
        client._created_entities = [("A", "1"), ("B", "2"), ("C", "3")]
        result = client._topo_sort_for_delete({})
        assert result == [("C", "3"), ("B", "2"), ("A", "1")]

    def test_children_before_parents(self, client: DazzleClient) -> None:
        """Child entity types are sorted before parent entity types."""
        client._created_entities = [
            ("SoleTrader", "st-1"),
            ("PropertyIncome", "pi-1"),
        ]
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        result = client._topo_sort_for_delete(fk_map)
        names = [name for name, _id in result]
        assert names.index("PropertyIncome") < names.index("SoleTrader")

    def test_grandchildren_before_children(self, client: DazzleClient) -> None:
        """Three-level hierarchy: grandchild → child → parent."""
        client._created_entities = [
            ("Company", "co-1"),
            ("Department", "dept-1"),
            ("Employee", "emp-1"),
        ]
        fk_map = {
            "Company": [("Department", "company")],
            "Department": [("Employee", "department")],
        }
        result = client._topo_sort_for_delete(fk_map)
        names = [name for name, _id in result]
        assert names.index("Employee") < names.index("Department")
        assert names.index("Department") < names.index("Company")

    def test_unrelated_types_preserve_lifo(self, client: DazzleClient) -> None:
        """Types not in the FK graph keep their LIFO order."""
        client._created_entities = [
            ("Alpha", "a-1"),
            ("Beta", "b-1"),
            ("Gamma", "g-1"),
        ]
        # No FK relations among these
        result = client._topo_sort_for_delete({})
        assert result == [("Gamma", "g-1"), ("Beta", "b-1"), ("Alpha", "a-1")]

    def test_only_sorts_tracked_types(self, client: DazzleClient) -> None:
        """FK map entries for untracked types are ignored."""
        client._created_entities = [("A", "1")]
        # B references A but B is not tracked
        fk_map = {"A": [("B", "a_ref")]}
        result = client._topo_sort_for_delete(fk_map)
        assert result == [("A", "1")]

    def test_mixed_tracked_and_fk(self, client: DazzleClient) -> None:
        """Only tracked child types are reordered."""
        client._created_entities = [
            ("Parent", "p-1"),
            ("Child", "c-1"),
            ("Unrelated", "u-1"),
        ]
        fk_map = {"Parent": [("Child", "parent_ref")]}
        result = client._topo_sort_for_delete(fk_map)
        names = [name for name, _id in result]
        assert names.index("Child") < names.index("Parent")


# ── Full cleanup integration ────────────────────────────────────────────


class TestCleanupCreatedEntities:
    def test_empty_list(self, client: DazzleClient) -> None:
        deleted, failed = client.cleanup_created_entities()
        assert deleted == 0
        assert failed == 0

    def test_deletes_children_before_parents(self, client: DazzleClient) -> None:
        """Cleanup deletes child entities before parents using topo sort."""
        client._created_entities = [
            ("SoleTrader", "st-1"),
            ("PropertyIncome", "pi-1"),
            ("PropertyIncome", "pi-2"),
        ]
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client._build_fk_reverse_map = MagicMock(return_value=fk_map)  # type: ignore[method-assign]
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted, failed = client.cleanup_created_entities()
        assert deleted == 3
        assert failed == 0

        # Children deleted before parent
        calls = [c.args for c in client.delete_entity.call_args_list]
        pi_calls = [c for c in calls if c[0] == "PropertyIncome"]
        st_calls = [c for c in calls if c[0] == "SoleTrader"]
        assert len(pi_calls) == 2
        assert len(st_calls) == 1
        pi_indices = [i for i, c in enumerate(calls) if c[0] == "PropertyIncome"]
        st_index = next(i for i, c in enumerate(calls) if c[0] == "SoleTrader")
        assert all(pi_idx < st_index for pi_idx in pi_indices)

    def test_no_api_queries_for_children(self, client: DazzleClient) -> None:
        """Cleanup does NOT call get_entities — only deletes tracked entities."""
        client._created_entities = [("SoleTrader", "st-1"), ("PropertyIncome", "pi-1")]
        fk_map = {"SoleTrader": [("PropertyIncome", "owner")]}
        client._build_fk_reverse_map = MagicMock(return_value=fk_map)  # type: ignore[method-assign]
        client.get_entities = MagicMock(return_value=[])  # type: ignore[method-assign]
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        client.cleanup_created_entities()
        # get_entities should NOT be called during cleanup (was the #410 bug)
        client.get_entities.assert_not_called()

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

    def test_deduplicates_tracked_entities(self, client: DazzleClient) -> None:
        """Same entity tracked twice is only deleted once."""
        client._created_entities = [("A", "1"), ("A", "1")]
        client._build_fk_reverse_map = MagicMock(return_value={})  # type: ignore[method-assign]
        client.delete_entity = MagicMock(return_value=True)  # type: ignore[method-assign]

        deleted, failed = client.cleanup_created_entities()
        assert deleted == 1
        assert failed == 0
        client.delete_entity.assert_called_once_with("A", "1")
