"""Unit tests for tenancy inference with actionable suggestions."""

from dazzle.core import ir
from dazzle.mcp.event_first_tools import infer_multi_tenancy


class TestTenancyInference:
    """Tests for multi-tenancy inference."""

    def test_single_tenant_no_signals(self) -> None:
        """Test that apps without tenancy signals are classified as single-tenant."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                            ir.FieldSpec(
                                name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR)
                            ),
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        assert result["recommendation"] == "single_tenant"
        assert result["signals"] == []
        assert result["suggested_actions"] == []

    def test_consider_multi_tenant_with_company_entity(self) -> None:
        """Test that Company entity triggers consider_multi_tenant."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Company",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                            ir.FieldSpec(name="name", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
                        ],
                    ),
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                            ir.FieldSpec(
                                name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR)
                            ),
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        assert result["recommendation"] == "consider_multi_tenant"
        assert result["tenant_entity"] == "Company"
        assert len(result["signals"]) == 1
        assert result["signals"][0]["type"] == "tenant_entity"

    def test_suggested_actions_include_dsl_snippets(self) -> None:
        """Test that suggested actions include DSL snippets."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Company",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                        ],
                    ),
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        assert len(result["suggested_actions"]) >= 1

        # Should suggest adding tenancy config
        config_action = next(
            (a for a in result["suggested_actions"] if a["action"] == "add_tenancy_config"),
            None,
        )
        assert config_action is not None
        assert "tenancy:" in config_action["dsl_snippet"]
        assert "shared_schema" in config_action["dsl_snippet"]

        # Should suggest adding tenant_id to Task
        field_action = next(
            (a for a in result["suggested_actions"] if a["action"] == "add_tenant_id_fields"),
            None,
        )
        assert field_action is not None
        assert "Task" in field_action["entities"]
        assert "tenant_id" in field_action["dsl_snippet"]

    def test_entities_with_tenant_id_not_flagged(self) -> None:
        """Test that entities already having tenant_id are not flagged for action."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Company",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                        ],
                    ),
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                            ir.FieldSpec(
                                name="tenant_id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)
                            ),
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        assert "Task" in result["entities_with_tenant_id"]

        # Task should not be in the list of entities needing tenant_id
        field_action = next(
            (a for a in result["suggested_actions"] if a["action"] == "add_tenant_id_fields"),
            None,
        )
        if field_action:
            assert "Task" not in field_action["entities"]

    def test_system_entities_excluded_from_suggestions(self) -> None:
        """Test that system-managed entities are excluded from tenant_id suggestions."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Company",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))
                        ],
                    ),
                    ir.EntitySpec(
                        name="AuditLog",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))
                        ],
                    ),
                    ir.EntitySpec(
                        name="SystemEvent",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))
                        ],
                    ),
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        field_action = next(
            (a for a in result["suggested_actions"] if a["action"] == "add_tenant_id_fields"),
            None,
        )
        assert field_action is not None
        # Task should need tenant_id, but not AuditLog or SystemEvent
        assert "Task" in field_action["entities"]
        assert "AuditLog" not in field_action["entities"]
        assert "SystemEvent" not in field_action["entities"]

    def test_suggest_create_tenant_entity_when_none_exists(self) -> None:
        """Test that we suggest creating a Tenant entity when none exists."""
        appspec = ir.AppSpec(
            name="test_app",
            version="0.1.0",
            domain=ir.DomainSpec(
                entities=[
                    ir.EntitySpec(
                        name="Task",
                        fields=[
                            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                            ir.FieldSpec(
                                name="tenant_id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)
                            ),
                        ],
                    ),
                ]
            ),
        )

        result = infer_multi_tenancy(appspec)

        # Should recommend multi-tenant due to tenant_id field
        # When >50% of entities have tenant_id, recommendation is shared_schema
        assert result["recommendation"] in ("consider_multi_tenant", "shared_schema")

        # Should suggest creating a Tenant entity
        create_action = next(
            (a for a in result["suggested_actions"] if a["action"] == "create_tenant_entity"),
            None,
        )
        assert create_action is not None
        assert "entity Tenant" in create_action["dsl_snippet"]
