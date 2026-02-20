"""Tests for integration manual trigger buttons on entity detail pages (#338)."""

from __future__ import annotations

from dazzle.core.ir import AppSpec, DomainSpec, EntitySpec, FieldSpec, FieldType
from dazzle.core.ir.integrations import (
    IntegrationMapping,
    IntegrationSpec,
    MappingTriggerSpec,
    MappingTriggerType,
)
from dazzle_ui.runtime.page_routes import _inject_integration_actions
from dazzle_ui.runtime.template_context import (
    DetailContext,
    FieldContext,
    IntegrationActionContext,
    PageContext,
)


def _make_appspec_with_manual_trigger(
    entity_name: str = "Company",
    integration_name: str = "companieshouse",
    mapping_name: str = "verify_company",
    label: str = "Verify Company",
) -> AppSpec:
    entity = EntitySpec(
        name=entity_name,
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
        ],
    )
    integration = IntegrationSpec(
        name=integration_name,
        mappings=[
            IntegrationMapping(
                name=mapping_name,
                entity_ref=entity_name,
                triggers=[
                    MappingTriggerSpec(
                        trigger_type=MappingTriggerType.MANUAL,
                        label=label,
                    ),
                ],
            ),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test",
        domain=DomainSpec(entities=[entity]),
        integrations=[integration],
    )


def _make_detail_page_context(entity_name: str = "Company") -> dict[str, PageContext]:
    return {
        "company_detail": PageContext(
            page_title=f"{entity_name} Details",
            template="components/detail_view.html",
            detail=DetailContext(
                entity_name=entity_name,
                title=f"{entity_name} Details",
                fields=[FieldContext(name="name", label="Name", type="text")],
            ),
        ),
    }


class TestInjectIntegrationActions:
    """Test _inject_integration_actions populates detail contexts."""

    def test_manual_trigger_injected(self) -> None:
        appspec = _make_appspec_with_manual_trigger()
        contexts = _make_detail_page_context()

        _inject_integration_actions(appspec, contexts)

        detail = contexts["company_detail"].detail
        assert detail is not None
        assert len(detail.integration_actions) == 1
        action = detail.integration_actions[0]
        assert action.label == "Verify Company"
        assert action.integration_name == "companieshouse"
        assert action.mapping_name == "verify_company"
        assert "{id}" in action.api_url

    def test_no_integrations_no_actions(self) -> None:
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[]),
        )
        contexts = _make_detail_page_context()

        _inject_integration_actions(appspec, contexts)

        detail = contexts["company_detail"].detail
        assert detail is not None
        assert len(detail.integration_actions) == 0

    def test_non_manual_trigger_ignored(self) -> None:
        entity = EntitySpec(
            name="Company",
            fields=[FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True)],
        )
        integration = IntegrationSpec(
            name="ch",
            mappings=[
                IntegrationMapping(
                    name="auto_sync",
                    entity_ref="Company",
                    triggers=[
                        MappingTriggerSpec(trigger_type=MappingTriggerType.ON_CREATE),
                    ],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            integrations=[integration],
        )
        contexts = _make_detail_page_context()

        _inject_integration_actions(appspec, contexts)

        detail = contexts["company_detail"].detail
        assert detail is not None
        assert len(detail.integration_actions) == 0

    def test_label_defaults_to_mapping_name(self) -> None:
        """When trigger has no label, mapping name is title-cased."""
        appspec = _make_appspec_with_manual_trigger(label="")
        # Clear the label to test default
        appspec.integrations[0].mappings[0].triggers[0] = MappingTriggerSpec(
            trigger_type=MappingTriggerType.MANUAL,
            label=None,
        )
        contexts = _make_detail_page_context()

        _inject_integration_actions(appspec, contexts)

        action = contexts["company_detail"].detail.integration_actions[0]
        assert action.label == "Verify Company"  # from mapping name

    def test_multiple_mappings(self) -> None:
        entity = EntitySpec(
            name="Company",
            fields=[FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True)],
        )
        integration = IntegrationSpec(
            name="ch",
            mappings=[
                IntegrationMapping(
                    name="verify",
                    entity_ref="Company",
                    triggers=[
                        MappingTriggerSpec(trigger_type=MappingTriggerType.MANUAL, label="Verify"),
                    ],
                ),
                IntegrationMapping(
                    name="fetch_filings",
                    entity_ref="Company",
                    triggers=[
                        MappingTriggerSpec(
                            trigger_type=MappingTriggerType.MANUAL, label="Fetch Filings"
                        ),
                    ],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            integrations=[integration],
        )
        contexts = _make_detail_page_context()

        _inject_integration_actions(appspec, contexts)

        assert len(contexts["company_detail"].detail.integration_actions) == 2

    def test_entity_mismatch_not_injected(self) -> None:
        """Actions for Contact should not appear on Company detail page."""
        appspec = _make_appspec_with_manual_trigger(entity_name="Contact")
        contexts = _make_detail_page_context("Company")

        _inject_integration_actions(appspec, contexts)

        assert len(contexts["company_detail"].detail.integration_actions) == 0


class TestIntegrationActionContext:
    """Test IntegrationActionContext model."""

    def test_fields(self) -> None:
        action = IntegrationActionContext(
            label="Look up",
            integration_name="ch",
            mapping_name="lookup",
            api_url="/companys/{id}/integrations/ch/lookup",
        )
        assert action.label == "Look up"
        assert action.integration_name == "ch"
        assert action.mapping_name == "lookup"
