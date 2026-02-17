"""Tests for declarative integration mappings (v0.30.0)."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    AuthType,
    ErrorAction,
    HttpMethod,
    MappingTriggerType,
)
from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestIntegrationBaseUrl:
    """Tests for integration base_url parsing."""

    def test_base_url(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration companies_house "Companies House":
  base_url: "https://api.company-information.service.gov.uk"

  mapping fetch on Company:
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.name == "companies_house"
        assert integration.title == "Companies House"
        assert integration.base_url == "https://api.company-information.service.gov.uk"

    def test_no_base_url(self) -> None:
        dsl = """
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  name: str(100) required

integration external_api:
  mapping sync_items on Item:
    request: GET "/items"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.base_url is None


class TestIntegrationAuth:
    """Tests for integration auth parsing."""

    def test_api_key_auth(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  base_url: "https://api.company-information.service.gov.uk"
  auth: api_key from env("COMPANIES_HOUSE_API_KEY")

  mapping fetch on Company:
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.auth is not None
        assert integration.auth.auth_type == AuthType.API_KEY
        assert integration.auth.credentials == ["COMPANIES_HOUSE_API_KEY"]

    def test_oauth2_auth(self) -> None:
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  period_key: str(50) required

integration hmrc:
  base_url: "https://api.service.hmrc.gov.uk"
  auth: oauth2 from env("HMRC_CLIENT_ID"), env("HMRC_CLIENT_SECRET")

  mapping submit on VATReturn:
    request: POST "/organisations/vat/returns"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.auth is not None
        assert integration.auth.auth_type == AuthType.OAUTH2
        assert integration.auth.credentials == ["HMRC_CLIENT_ID", "HMRC_CLIENT_SECRET"]

    def test_bearer_auth(self) -> None:
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  title: str(100) required

integration my_api:
  auth: bearer from env("MY_API_TOKEN")

  mapping fetch on Record:
    request: GET "/records"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.auth is not None
        assert integration.auth.auth_type == AuthType.BEARER
        assert integration.auth.credentials == ["MY_API_TOKEN"]


class TestIntegrationMappingBlock:
    """Tests for mapping block parsing."""

    def test_simple_mapping(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  mapping fetch_company on Company:
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert len(integration.mappings) == 1
        mapping = integration.mappings[0]
        assert mapping.name == "fetch_company"
        assert mapping.entity_ref == "Company"
        assert mapping.request is not None
        assert mapping.request.method == HttpMethod.GET
        assert mapping.request.url_template == "/company/search"

    def test_multiple_mappings(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  mapping fetch_company on Company:
    request: GET "/company/search"

  mapping fetch_officers on Company:
    request: GET "/company/officers"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert len(integration.mappings) == 2
        assert integration.mappings[0].name == "fetch_company"
        assert integration.mappings[1].name == "fetch_officers"


class TestMappingTriggers:
    """Tests for mapping trigger parsing."""

    def test_manual_trigger(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  mapping fetch on Company:
    trigger: manual "Look up company"
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert len(mapping.triggers) == 1
        trigger = mapping.triggers[0]
        assert trigger.trigger_type == MappingTriggerType.MANUAL
        assert trigger.label == "Look up company"

    def test_on_create_trigger(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  mapping fetch on Company:
    trigger: on_create
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        trigger = fragment.integrations[0].mappings[0].triggers[0]
        assert trigger.trigger_type == MappingTriggerType.ON_CREATE
        assert trigger.condition_expr is None

    def test_on_create_with_condition(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  company_number: str(20)
  name: str(200) required

integration ch_api:
  mapping fetch on Company:
    trigger: on_create when company_number != null
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        trigger = fragment.integrations[0].mappings[0].triggers[0]
        assert trigger.trigger_type == MappingTriggerType.ON_CREATE
        assert trigger.condition_expr is not None
        assert isinstance(trigger.condition_expr, BinaryExpr)
        assert trigger.condition_expr.op == BinaryOp.NE
        assert isinstance(trigger.condition_expr.left, FieldRef)
        assert trigger.condition_expr.left.path == ["company_number"]

    def test_on_transition_trigger(self) -> None:
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  status: str(20) required

integration hmrc:
  mapping submit on VATReturn:
    trigger: on_transition reviewed -> submitted
    request: POST "/vat/returns"
"""
        fragment = _parse(dsl)
        trigger = fragment.integrations[0].mappings[0].triggers[0]
        assert trigger.trigger_type == MappingTriggerType.ON_TRANSITION
        assert trigger.from_state == "reviewed"
        assert trigger.to_state == "submitted"

    def test_multiple_triggers(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  company_number: str(20)
  name: str(200) required

integration ch_api:
  mapping fetch on Company:
    trigger: on_create when company_number != null
    trigger: manual "Look up company"
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert len(mapping.triggers) == 2
        assert mapping.triggers[0].trigger_type == MappingTriggerType.ON_CREATE
        assert mapping.triggers[1].trigger_type == MappingTriggerType.MANUAL


class TestHttpRequest:
    """Tests for HTTP request parsing."""

    def test_get_with_string_url(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration ch_api:
  mapping fetch on Company:
    request: GET "/company/{self.company_number}"
"""
        fragment = _parse(dsl)
        req = fragment.integrations[0].mappings[0].request
        assert req is not None
        assert req.method == HttpMethod.GET
        assert req.url_template == "/company/{self.company_number}"

    def test_post_method(self) -> None:
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  period_key: str(50) required

integration hmrc:
  mapping submit on VATReturn:
    request: POST "/organisations/vat/returns"
"""
        fragment = _parse(dsl)
        req = fragment.integrations[0].mappings[0].request
        assert req is not None
        assert req.method == HttpMethod.POST

    def test_unquoted_url_path(self) -> None:
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  title: str(100) required

integration my_api:
  mapping fetch on Record:
    request: GET /records/search
"""
        fragment = _parse(dsl)
        req = fragment.integrations[0].mappings[0].request
        assert req is not None
        assert req.url_template == "/records/search"


class TestResponseMapping:
    """Tests for response mapping parsing."""

    def test_simple_response_mapping(self) -> None:
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required
  company_type: str(50)

integration ch_api:
  mapping fetch on Company:
    request: GET "/company/search"
    map_response:
      name <- response.company_name
      company_type <- response.type
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert len(mapping.response_mapping) == 2
        assert mapping.response_mapping[0].target_field == "name"
        assert mapping.response_mapping[0].source.path == "response.company_name"
        assert mapping.response_mapping[1].target_field == "company_type"
        assert mapping.response_mapping[1].source.path == "response.type"

    def test_literal_in_response_mapping(self) -> None:
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  title: str(100) required
  synced: bool

integration my_api:
  mapping fetch on Record:
    request: GET "/records"
    map_response:
      synced <- true
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert len(mapping.response_mapping) == 1
        assert mapping.response_mapping[0].target_field == "synced"
        assert mapping.response_mapping[0].source.literal is True


class TestRequestMapping:
    """Tests for request mapping parsing."""

    def test_request_mapping(self) -> None:
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  period_key: str(50) required
  box1_amount: decimal(10,2) required

integration hmrc:
  mapping submit on VATReturn:
    request: POST "/vat/returns"
    map_request:
      periodKey <- self.period_key
      vatDueSales <- self.box1_amount
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert len(mapping.request_mapping) == 2
        assert mapping.request_mapping[0].target_field == "periodKey"
        assert mapping.request_mapping[0].source.path == "self.period_key"
        assert mapping.request_mapping[1].target_field == "vatDueSales"
        assert mapping.request_mapping[1].source.path == "self.box1_amount"


class TestErrorStrategy:
    """Tests for error strategy parsing."""

    def test_ignore_error(self) -> None:
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  title: str(100) required

integration my_api:
  mapping fetch on Record:
    request: GET "/records"
    on_error: ignore
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert mapping.on_error is not None
        assert ErrorAction.IGNORE in mapping.on_error.actions

    def test_multiple_error_actions(self) -> None:
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  title: str(100) required
  integration_status: str(20)

integration my_api:
  mapping fetch on Record:
    request: GET "/records"
    on_error: set integration_status = "failed", log_warning
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert mapping.on_error is not None
        assert mapping.on_error.set_fields == {"integration_status": "failed"}
        assert ErrorAction.LOG_WARNING in mapping.on_error.actions

    def test_revert_transition_error(self) -> None:
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  status: str(20) required

integration hmrc:
  mapping submit on VATReturn:
    trigger: on_transition reviewed -> submitted
    request: POST "/vat/returns"
    on_error: revert_transition
"""
        fragment = _parse(dsl)
        mapping = fragment.integrations[0].mappings[0]
        assert mapping.on_error is not None
        assert ErrorAction.REVERT_TRANSITION in mapping.on_error.actions


class TestFullIntegration:
    """Tests for complete integration declarations."""

    def test_companies_house_full(self) -> None:
        """Full Companies House integration from the issue proposal."""
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  company_number: str(20)
  company_name: str(200) required
  company_type: str(50)
  incorporation_date: date
  company_status: str(50)

integration companies_house:
  base_url: "https://api.company-information.service.gov.uk"
  auth: api_key from env("COMPANIES_HOUSE_API_KEY")

  mapping fetch_company on Company:
    trigger: on_create when company_number != null
    trigger: manual "Look up company"
    request: GET "/company/{self.company_number}"
    map_response:
      company_name <- response.company_name
      company_type <- response.type
      incorporation_date <- response.date_of_creation
      company_status <- response.company_status
    on_error: set company_status = "lookup_failed", log_warning

  mapping fetch_filings on Company:
    trigger: manual "Check filings"
    request: GET "/company/{self.company_number}/filing-history"
    on_error: ignore
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.name == "companies_house"
        assert integration.base_url == "https://api.company-information.service.gov.uk"
        assert integration.auth is not None
        assert integration.auth.auth_type == AuthType.API_KEY

        assert len(integration.mappings) == 2

        # First mapping: fetch_company
        m1 = integration.mappings[0]
        assert m1.name == "fetch_company"
        assert m1.entity_ref == "Company"
        assert len(m1.triggers) == 2
        assert m1.triggers[0].trigger_type == MappingTriggerType.ON_CREATE
        assert m1.triggers[0].condition_expr is not None
        assert m1.triggers[1].trigger_type == MappingTriggerType.MANUAL
        assert m1.triggers[1].label == "Look up company"
        assert m1.request is not None
        assert m1.request.method == HttpMethod.GET
        assert m1.request.url_template == "/company/{self.company_number}"
        assert len(m1.response_mapping) == 4
        assert m1.on_error is not None
        assert m1.on_error.set_fields == {"company_status": "lookup_failed"}
        assert ErrorAction.LOG_WARNING in m1.on_error.actions

        # Second mapping: fetch_filings
        m2 = integration.mappings[1]
        assert m2.name == "fetch_filings"
        assert m2.entity_ref == "Company"
        assert len(m2.triggers) == 1
        assert m2.triggers[0].trigger_type == MappingTriggerType.MANUAL
        assert m2.on_error is not None
        assert ErrorAction.IGNORE in m2.on_error.actions

    def test_mixed_legacy_and_new(self) -> None:
        """Integration can have both legacy actions and new mappings."""
        dsl = """
module test
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

integration mixed_api:
  uses service ExternalAPI

  action legacy_action:
    when surface company_search
    call service ExternalAPI
    call operation /search

  mapping new_mapping on Company:
    request: GET "/company/search"
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert len(integration.actions) == 1
        assert integration.actions[0].name == "legacy_action"
        assert len(integration.mappings) == 1
        assert integration.mappings[0].name == "new_mapping"

    def test_hmrc_vat_submission(self) -> None:
        """HMRC MTD VAT submission with request mapping."""
        dsl = """
module test
app test "Test"

entity VATReturn "VAT Return":
  id: uuid pk
  period_key: str(50) required
  box1_vat_due_sales: decimal(10,2) required
  hmrc_receipt_id: str(100)
  status: str(20)=draft

integration hmrc_mtd:
  base_url: "https://api.service.hmrc.gov.uk"
  auth: oauth2 from env("HMRC_CLIENT_ID"), env("HMRC_CLIENT_SECRET")

  mapping submit_vat_return on VATReturn:
    trigger: on_transition reviewed -> submitted
    request: POST "/organisations/vat/returns"
    map_request:
      periodKey <- self.period_key
      vatDueSales <- self.box1_vat_due_sales
    map_response:
      hmrc_receipt_id <- response.formBundleNumber
    on_error: revert_transition
"""
        fragment = _parse(dsl)
        integration = fragment.integrations[0]
        assert integration.name == "hmrc_mtd"
        assert integration.auth.auth_type == AuthType.OAUTH2
        assert len(integration.auth.credentials) == 2

        mapping = integration.mappings[0]
        assert mapping.name == "submit_vat_return"
        assert mapping.triggers[0].trigger_type == MappingTriggerType.ON_TRANSITION
        assert mapping.triggers[0].from_state == "reviewed"
        assert mapping.triggers[0].to_state == "submitted"
        assert mapping.request.method == HttpMethod.POST
        assert len(mapping.request_mapping) == 2
        assert len(mapping.response_mapping) == 1
        assert mapping.on_error is not None
        assert ErrorAction.REVERT_TRANSITION in mapping.on_error.actions
