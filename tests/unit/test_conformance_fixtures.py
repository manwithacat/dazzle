"""Tests for the conformance fixture engine."""

from __future__ import annotations

from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Re-usable SimpleNamespace helpers (same pattern as derivation tests)
# ---------------------------------------------------------------------------


def _permit(operation: str, personas: list[str], *, condition: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        operation=operation,
        effect="permit",
        personas=personas,
        require_auth=True,
        condition=condition,
    )


def _scope(
    operation: str,
    personas: list[str],
    *,
    condition: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        operation=operation,
        personas=personas,
        condition=condition,
    )


def _make_entity(
    name: str,
    permissions: list[SimpleNamespace] | None = None,
    scopes: list[SimpleNamespace] | None = None,
    fields: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    access = SimpleNamespace(
        permissions=permissions or [],
        scopes=scopes or [],
    )
    return SimpleNamespace(name=name, access=access, fields=fields or [])


def _make_appspec(entities: list[SimpleNamespace]) -> SimpleNamespace:
    domain = SimpleNamespace(entities=entities)
    return SimpleNamespace(domain=domain)


def _make_field(name: str, kind: str = "str") -> SimpleNamespace:
    """Build a field-like SimpleNamespace with type.kind."""
    return SimpleNamespace(name=name, type=SimpleNamespace(kind=kind))


# ---------------------------------------------------------------------------
# Fixtures tests
# ---------------------------------------------------------------------------


class TestFixtureEngine:
    def _build_scoped_appspec(self) -> SimpleNamespace:
        """Task entity with viewer (filtered) and admin (all) scopes."""
        entity = _make_entity(
            "Task",
            permissions=[
                _permit("list", ["viewer"]),
                _permit("list", ["admin"]),
            ],
            scopes=[
                _scope("list", ["viewer"], condition="owner = current_user"),
                _scope("list", ["admin"], condition=None),
            ],
        )
        return _make_appspec([entity])

    def test_users_created_per_persona(self) -> None:
        """2 users per persona (user_a and user_b) are created in fixtures.users."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        # Collect the real personas (exclude synthetic)
        domain_personas = {"viewer", "admin"}
        for persona in domain_personas:
            assert f"{persona}.user_a" in fixtures.users, f"Missing user_a for {persona}"
            assert f"{persona}.user_b" in fixtures.users, f"Missing user_b for {persona}"

    def test_entity_rows_created(self) -> None:
        """4 rows per entity that has scoped cases are added to entity_rows."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        assert "Task" in fixtures.entity_rows
        assert len(fixtures.entity_rows["Task"]) == 4

    def test_uuid_determinism(self) -> None:
        """Same appspec + cases always produce the same UUIDs."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases1 = derive_conformance_cases(appspec, auth_enabled=False)
        cases2 = derive_conformance_cases(appspec, auth_enabled=False)
        f1 = generate_fixtures(appspec, cases1)
        f2 = generate_fixtures(appspec, cases2)

        assert f1.users == f2.users
        assert f1.entity_rows == f2.entity_rows

    def test_expected_counts_all_rows(self) -> None:
        """Persona with scope:all gets expected_count = 4 (total row count)."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        assert fixtures.expected_counts[("admin", "Task")] == 4

    def test_expected_counts_filtered(self) -> None:
        """Persona with scope condition gets expected_count = 2."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        assert fixtures.expected_counts[("viewer", "Task")] == 2

    def test_expected_counts_scope_excluded(self) -> None:
        """Persona with no scope rule gets expected_count = 0."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        # editor has permit but no scope → SCOPE_EXCLUDED
        entity = _make_entity(
            "Task",
            permissions=[
                _permit("list", ["editor"]),
            ],
            scopes=[],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        assert fixtures.expected_counts[("editor", "Task")] == 0

    def test_cases_updated_with_resolved_counts(self) -> None:
        """Sentinel -1 is replaced with 4 and sentinel -2 is replaced with 2 on cases."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        generate_fixtures(appspec, cases)

        list_cases = {c.persona: c for c in cases if c.operation == "list" and c.entity == "Task"}
        # admin had -1 (ALL_ROWS) → should now be 4
        assert list_cases["admin"].expected_rows == 4, (
            f"Expected 4 for admin, got {list_cases['admin'].expected_rows}"
        )
        # viewer had -2 (FILTERED_ROWS) → should now be 2
        assert list_cases["viewer"].expected_rows == 2, (
            f"Expected 2 for viewer, got {list_cases['viewer'].expected_rows}"
        )

    def test_scope_excluded_cases_keep_zero(self) -> None:
        """Cases with expected_rows=0 (scope_excluded) are left at 0."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["editor"])],
            scopes=[],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        generate_fixtures(appspec, cases)

        editor_list = next(c for c in cases if c.persona == "editor" and c.operation == "list")
        assert editor_list.expected_rows == 0

    def test_ref_field_populated(self) -> None:
        """Entity rows have ref fields set to the owning user's UUID."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures
        from dazzle.conformance.models import conformance_uuid

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["viewer"])],
            scopes=[_scope("list", ["viewer"], condition="owner = current_user")],
            fields=[
                _make_field("id", "uuid"),
                _make_field("owner", "ref"),
            ],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        rows = fixtures.entity_rows["Task"]
        # Row 0 and Row 2 are owned by viewer.user_a
        expected_user_a_id = conformance_uuid("Task", "viewer.user_a")
        # Row 1 and Row 3 are owned by viewer.user_b
        expected_user_b_id = conformance_uuid("Task", "viewer.user_b")

        assert rows[0]["owner"] == expected_user_a_id
        assert rows[1]["owner"] == expected_user_b_id
        assert rows[2]["owner"] == expected_user_a_id
        assert rows[3]["owner"] == expected_user_b_id

    def test_entity_rows_have_deterministic_ids(self) -> None:
        """Each entity row has an 'id' field set via conformance_uuid."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures
        from dazzle.conformance.models import conformance_uuid

        appspec = self._build_scoped_appspec()
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        rows = fixtures.entity_rows["Task"]
        assert rows[0]["id"] == conformance_uuid("Task", "row.0")
        assert rows[1]["id"] == conformance_uuid("Task", "row.1")
        assert rows[2]["id"] == conformance_uuid("Task", "row.2")
        assert rows[3]["id"] == conformance_uuid("Task", "row.3")

    def test_no_rows_for_unprotected_entity(self) -> None:
        """Entity with no access spec does not get fixture rows generated."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        entity = SimpleNamespace(name="Tag", access=None, fields=[])
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        # Unprotected entities have no scopes to test against → no rows needed
        assert "Tag" not in fixtures.entity_rows

    def test_multiple_entities_independent(self) -> None:
        """Fixture rows are generated independently for each entity."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.fixtures import generate_fixtures

        entity_a = _make_entity(
            "Task",
            permissions=[_permit("list", ["viewer"])],
            scopes=[_scope("list", ["viewer"], condition="owner = current_user")],
        )
        entity_b = _make_entity(
            "Project",
            permissions=[_permit("list", ["admin"])],
            scopes=[_scope("list", ["admin"], condition=None)],
        )
        appspec = _make_appspec([entity_a, entity_b])
        cases = derive_conformance_cases(appspec, auth_enabled=False)
        fixtures = generate_fixtures(appspec, cases)

        assert len(fixtures.entity_rows["Task"]) == 4
        assert len(fixtures.entity_rows["Project"]) == 4
        # Row IDs are namespaced per entity so they differ
        assert fixtures.entity_rows["Task"][0]["id"] != fixtures.entity_rows["Project"][0]["id"]
