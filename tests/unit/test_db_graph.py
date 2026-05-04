"""Tests for dazzle.db.graph — entity dependency graph utilities."""

import pytest

from dazzle.db.graph import build_dependency_graph, get_ref_fields, leaves_first, parents_first


class TestBuildDependencyGraph:
    @pytest.mark.parametrize(
        ("entity_specs", "expected"),
        [
            ([], {}),
            ([("User", None), ("Config", None)], {"User": set(), "Config": set()}),
            ([("Employee", {"manager": "Employee"})], {"Employee": set()}),
            ([("Student", {"school": "School"})], {"Student": set()}),
        ],
        ids=[
            "test_empty_entities",
            "test_no_refs",
            "test_self_ref_excluded",
            "test_ref_to_external_entity_excluded",
        ],
    )
    def test_dependency_graph(self, make_entity, entity_specs, expected) -> None:
        entities = [
            make_entity(name, refs) if refs else make_entity(name) for name, refs in entity_specs
        ]
        graph = build_dependency_graph(entities)
        assert graph == expected

    def test_simple_ref(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        graph = build_dependency_graph([school, student])
        assert graph["Student"] == {"School"}
        assert graph["School"] == set()

    def test_has_many_excluded(self, make_entity) -> None:
        """has_many fields should NOT appear in the dependency graph."""
        from unittest.mock import MagicMock

        parent = make_entity("School")
        hm = MagicMock()
        hm.name = "students"
        hm.type = MagicMock()
        hm.type.kind = "has_many"
        hm.type.ref_entity = "Student"
        parent.fields.append(hm)

        student = make_entity("Student", {"school": "School"})
        graph = build_dependency_graph([parent, student])
        assert graph["School"] == set()
        assert graph["Student"] == {"School"}


class TestParentsFirst:
    def test_linear_chain(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})
        result = parents_first([school, student, exclusion])
        assert result.index("School") < result.index("Student")
        assert result.index("Student") < result.index("Exclusion")

    def test_circular_ref_returns_sorted(self, make_entity) -> None:
        a = make_entity("A", {"b": "B"})
        b = make_entity("B", {"a": "A"})
        result = parents_first([a, b])
        assert sorted(result) == ["A", "B"]


class TestLeavesFirst:
    def test_linear_chain(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})
        result = leaves_first([school, student, exclusion])
        assert result.index("Exclusion") < result.index("Student")
        assert result.index("Student") < result.index("School")


class TestGetRefFields:
    def test_returns_ref_fields_only(self, make_entity) -> None:
        student = make_entity("Student", {"school": "School", "tutor": "StaffMember"})
        refs = get_ref_fields(student)
        assert len(refs) == 2
        ref_names = {r.name for r in refs}
        assert ref_names == {"school", "tutor"}

    def test_excludes_has_many(self, make_entity) -> None:
        """has_many fields should NOT be returned."""
        from unittest.mock import MagicMock

        parent = make_entity("School")
        hm = MagicMock()
        hm.name = "students"
        hm.type = MagicMock()
        hm.type.kind = "has_many"
        hm.type.ref_entity = "Student"
        parent.fields.append(hm)
        assert get_ref_fields(parent) == []

    def test_no_refs(self, make_entity) -> None:
        config = make_entity("Config")
        assert get_ref_fields(config) == []
