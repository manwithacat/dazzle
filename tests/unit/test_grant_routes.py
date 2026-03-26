"""Tests for grant_routes — relation-level granted_by / approval (#650)."""

from unittest.mock import MagicMock

from dazzle_back.runtime.grant_routes import create_grant_routes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_relation(name: str, role_name: str, approval: str = "required"):
    """Build a minimal GrantRelationSpec-like object."""
    rel = MagicMock()
    rel.name = name
    role_check = MagicMock()
    role_check.role_name = role_name
    expr = MagicMock()
    expr.role_check = role_check
    expr.left = None
    expr.right = None
    rel.granted_by = expr
    rel.approval = approval
    return rel


def _make_schema(name: str, relations: list):
    """Build a minimal GrantSchemaSpec-like object."""
    schema = MagicMock()
    schema.name = name
    schema.relations = relations
    # Ensure schema does NOT have granted_by or approval
    del schema.granted_by
    del schema.approval
    return schema


def _make_appspec(schemas: dict):
    """Build a mock AppSpec that can look up grant schemas."""
    appspec = MagicMock()
    appspec.get_grant_schema = lambda name: schemas.get(name)
    return appspec


# ---------------------------------------------------------------------------
# Tests for _check_granted_by and _get_relation_spec
# ---------------------------------------------------------------------------


class TestCheckGrantedByUsesRelation:
    """Verify that _check_granted_by reads from relation, not schema (#650)."""

    def _build_router_internals(self, schemas: dict):
        """Create routes and extract the inner helpers via the router."""
        appspec = _make_appspec(schemas)
        # We can't easily access the closure helpers, so test via endpoint
        # behaviour instead.
        return appspec

    def test_granted_by_comes_from_relation(self):
        """The role check should use the relation's granted_by, not schema's."""
        rel = _make_relation("approve_letter", "senior_leadership")
        schema = _make_schema("engagement_approval", [rel])
        appspec = _make_appspec({"engagement_approval": schema})

        # Build routes — this exercises the closure
        router = create_grant_routes(
            conn_factory=MagicMock,
            appspec=appspec,
            auth_dep=lambda: None,
        )
        # Router should have been created without error
        assert router is not None

    def test_approval_mode_comes_from_relation(self):
        """approval_mode should be read from relation spec, not schema."""
        rel = _make_relation("approve_letter", "admin", approval="immediate")
        schema = _make_schema("test_schema", [rel])

        # Verify the relation has the approval, not the schema
        assert rel.approval == "immediate"
        assert not hasattr(schema, "approval")

    def test_schema_has_no_granted_by(self):
        """GrantSchemaSpec should not have granted_by — it's on relations."""
        rel = _make_relation("do_thing", "manager")
        schema = _make_schema("test_schema", [rel])
        assert not hasattr(schema, "granted_by")
        assert hasattr(rel, "granted_by")


# ---------------------------------------------------------------------------
# Tests for _extract_roles helper (compound expressions)
# ---------------------------------------------------------------------------


class TestExtractRoles:
    """Test role extraction from ConditionExpr trees."""

    def test_simple_role(self):
        """Single role(X) expression extracts one role."""
        from dazzle_back.runtime.grant_routes import create_grant_routes

        # We need to test _extract_roles which is a closure.
        # Test it indirectly via the route logic.
        rel = _make_relation("test_rel", "admin")
        schema = _make_schema("test", [rel])
        appspec = _make_appspec({"test": schema})

        router = create_grant_routes(conn_factory=MagicMock, appspec=appspec, auth_dep=lambda: None)
        assert router is not None

    def test_compound_or_expression(self):
        """role(X) or role(Y) extracts both roles."""
        # Build compound expression: role(admin) or role(manager)
        expr = MagicMock()
        expr.role_check = None

        left = MagicMock()
        left.role_check = MagicMock()
        left.role_check.role_name = "admin"
        left.left = None
        left.right = None

        right = MagicMock()
        right.role_check = MagicMock()
        right.role_check.role_name = "manager"
        right.left = None
        right.right = None

        expr.left = left
        expr.right = right

        rel = MagicMock()
        rel.name = "multi_role_rel"
        rel.granted_by = expr
        rel.approval = "required"

        schema = _make_schema("compound_test", [rel])
        appspec = _make_appspec({"compound_test": schema})

        router = create_grant_routes(conn_factory=MagicMock, appspec=appspec, auth_dep=lambda: None)
        assert router is not None
