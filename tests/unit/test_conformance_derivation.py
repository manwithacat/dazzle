"""Tests for conformance testing data models and derivation engine."""

from __future__ import annotations

from types import SimpleNamespace


class TestConformanceModels:
    def test_scope_outcome_values(self) -> None:
        from dazzle.conformance.models import ScopeOutcome

        assert ScopeOutcome.ALL == "all"
        assert ScopeOutcome.FORBIDDEN == "forbidden"
        assert ScopeOutcome.SCOPE_EXCLUDED == "scope_excluded"

    def test_conformance_case_test_id(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=1,
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-list-Task-filtered"

    def test_conformance_case_test_id_with_row_target(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="own",
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-read-Task-filtered-own"

    def test_conformance_uuid_deterministic(self) -> None:
        from dazzle.conformance.models import conformance_uuid

        a = conformance_uuid("Task", "user_a")
        b = conformance_uuid("Task", "user_a")
        c = conformance_uuid("Task", "user_b")
        assert a == b
        assert a != c

    def test_conformance_fixtures_defaults(self) -> None:
        from dazzle.conformance.models import ConformanceFixtures

        f = ConformanceFixtures()
        assert f.users == {}
        assert f.entity_rows == {}
        assert f.junction_rows == {}
        assert f.expected_counts == {}


# ---------------------------------------------------------------------------
# SimpleNamespace helpers for derivation tests
# ---------------------------------------------------------------------------


def _permit(operation: str, personas: list[str], *, condition: object = None) -> SimpleNamespace:
    """Build a permit PermissionRule-like SimpleNamespace."""
    return SimpleNamespace(
        operation=operation,
        effect="permit",
        personas=personas,
        require_auth=True,
        condition=condition,
    )


def _forbid(operation: str, personas: list[str]) -> SimpleNamespace:
    """Build a forbid PermissionRule-like SimpleNamespace."""
    return SimpleNamespace(
        operation=operation,
        effect="forbid",
        personas=personas,
        require_auth=True,
        condition=None,
    )


def _scope(
    operation: str,
    personas: list[str],
    *,
    condition: object = None,
) -> SimpleNamespace:
    """Build a ScopeRule-like SimpleNamespace. condition=None → all rows."""
    return SimpleNamespace(
        operation=operation,
        personas=personas,
        condition=condition,
    )


def _make_entity(
    name: str,
    permissions: list[SimpleNamespace] | None = None,
    scopes: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """Build an EntitySpec-like SimpleNamespace."""
    access = SimpleNamespace(
        permissions=permissions or [],
        scopes=scopes or [],
    )
    return SimpleNamespace(name=name, access=access)


def _make_entity_no_access(name: str) -> SimpleNamespace:
    """Entity with no access spec at all."""
    return SimpleNamespace(name=name, access=None)


def _make_appspec(entities: list[SimpleNamespace]) -> SimpleNamespace:
    domain = SimpleNamespace(entities=entities)
    return SimpleNamespace(domain=domain)


# ---------------------------------------------------------------------------
# Helper: collect cases as dicts keyed by (persona, operation, row_target)
# ---------------------------------------------------------------------------


def _index(cases: list) -> dict[tuple[str, str, str | None], object]:
    return {(c.persona, c.operation, c.row_target): c for c in cases}


class TestDerivationEngine:
    def test_unprotected_entity(self) -> None:
        """Entity with no access spec: unauthenticated→401, any real persona→200."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        appspec = _make_appspec([_make_entity_no_access("Task")])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)

        # unauthenticated list → 401
        unauth = idx[("unauthenticated", "list", None)]
        assert unauth.expected_status == 401
        assert unauth.scope_type == ScopeOutcome.UNAUTHENTICATED

        # unmatched_role list → 200 UNPROTECTED (no access spec)
        unmatched = idx[("unmatched_role", "list", None)]
        assert unmatched.expected_status == 200
        assert unmatched.scope_type == ScopeOutcome.UNPROTECTED

    def test_permit_deny(self) -> None:
        """viewer has list permit but not create → create returns 403 ACCESS_DENIED."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["viewer"])],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        create_case = idx[("viewer", "create", None)]
        assert create_case.expected_status == 403
        assert create_case.scope_type == ScopeOutcome.ACCESS_DENIED

    def test_scope_all(self) -> None:
        """admin has list permit + scope all → scope_type=ALL, expected_rows=-1."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["admin"])],
            scopes=[_scope("list", ["admin"], condition=None)],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("admin", "list", None)]
        assert c.expected_status == 200
        assert c.scope_type == ScopeOutcome.ALL
        assert c.expected_rows == -1

    def test_scope_filtered(self) -> None:
        """viewer has list permit + scope with condition → FILTERED, expected_rows=-2."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["viewer"])],
            scopes=[_scope("list", ["viewer"], condition="owner = current_user")],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("viewer", "list", None)]
        assert c.expected_status == 200
        assert c.scope_type == ScopeOutcome.FILTERED
        assert c.expected_rows == -2

    def test_scope_excluded_default_deny(self) -> None:
        """viewer has permit but no scope rule → SCOPE_EXCLUDED, expected_rows=0."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["viewer"])],
            scopes=[],  # no scope rule for viewer
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("viewer", "list", None)]
        assert c.expected_status == 200
        assert c.scope_type == ScopeOutcome.SCOPE_EXCLUDED
        assert c.expected_rows == 0

    def test_forbid_overrides_permit(self) -> None:
        """forbid + permit for same persona/op → 403 FORBIDDEN (forbid wins)."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[
                _permit("list", ["viewer"]),
                _forbid("list", ["viewer"]),
            ],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("viewer", "list", None)]
        assert c.expected_status == 403
        assert c.scope_type == ScopeOutcome.FORBIDDEN

    def test_wildcard_scope(self) -> None:
        """scope for: * → applies to all permitted personas."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[
                _permit("list", ["admin"]),
                _permit("list", ["viewer"]),
            ],
            scopes=[_scope("list", ["*"], condition=None)],  # wildcard
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        assert idx[("admin", "list", None)].scope_type == ScopeOutcome.ALL
        assert idx[("viewer", "list", None)].scope_type == ScopeOutcome.ALL

    def test_unmatched_role_denied(self) -> None:
        """unmatched_role always gets 403 on a protected entity."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["admin"])],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("unmatched_role", "list", None)]
        assert c.expected_status == 403
        assert c.scope_type == ScopeOutcome.ACCESS_DENIED

    def test_read_generates_two_cases(self) -> None:
        """READ produces own-row (200) and other-row (404) for scoped persona."""
        from dazzle.conformance.derivation import derive_conformance_cases

        entity = _make_entity(
            "Task",
            permissions=[_permit("read", ["viewer"])],
            scopes=[_scope("read", ["viewer"], condition="owner = current_user")],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        # filter to read cases for viewer
        read_cases = [c for c in cases if c.persona == "viewer" and c.operation == "read"]
        assert len(read_cases) == 2

        own = next(c for c in read_cases if c.row_target == "own")
        other = next(c for c in read_cases if c.row_target == "other")

        assert own.expected_status == 200
        assert other.expected_status == 404

    def test_read_scope_all_two_cases_both_200(self) -> None:
        """READ with scope:all produces two cases both expecting 200."""
        from dazzle.conformance.derivation import derive_conformance_cases

        entity = _make_entity(
            "Task",
            permissions=[_permit("read", ["admin"])],
            scopes=[_scope("read", ["admin"], condition=None)],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        read_cases = [c for c in cases if c.persona == "admin" and c.operation == "read"]
        assert len(read_cases) == 2
        assert all(c.expected_status == 200 for c in read_cases)

    def test_create_single_case(self) -> None:
        """CREATE produces exactly one case with status=201."""
        from dazzle.conformance.derivation import derive_conformance_cases

        entity = _make_entity(
            "Task",
            permissions=[_permit("create", ["admin"])],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        create_cases = [c for c in cases if c.persona == "admin" and c.operation == "create"]
        assert len(create_cases) == 1
        assert create_cases[0].expected_status == 201

    def test_auth_disabled_no_401(self) -> None:
        """When auth_enabled=False no unauthenticated cases are generated."""
        from dazzle.conformance.derivation import derive_conformance_cases

        appspec = _make_appspec([_make_entity_no_access("Task")])
        cases = derive_conformance_cases(appspec, auth_enabled=False)

        assert all(c.persona != "unauthenticated" for c in cases)

    def test_synthetic_personas_always_present(self) -> None:
        """unauthenticated and unmatched_role are always in the persona set."""
        from dazzle.conformance.derivation import derive_conformance_cases

        entity = _make_entity(
            "Task",
            permissions=[_permit("list", ["admin"])],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        personas = {c.persona for c in cases}
        assert "unauthenticated" in personas
        assert "unmatched_role" in personas

    def test_operation_enum_value(self) -> None:
        """Derivation works when operation is an enum-like object with .value."""
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        # operation as SimpleNamespace with .value attribute (simulates PermissionKind enum)
        perm = SimpleNamespace(
            operation=SimpleNamespace(value="list"),
            effect="permit",
            personas=["viewer"],
            require_auth=True,
            condition=None,
        )
        entity = SimpleNamespace(
            name="Task",
            access=SimpleNamespace(permissions=[perm], scopes=[]),
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        idx = _index(cases)
        c = idx[("viewer", "list", None)]
        assert c.expected_status == 200
        assert c.scope_type == ScopeOutcome.SCOPE_EXCLUDED
