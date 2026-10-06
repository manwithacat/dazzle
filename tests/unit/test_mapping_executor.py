"""Tests for the integration mapping executor (v0.30.0)."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.ir.integrations import (
    AuthSpec,
    AuthType,
    ErrorAction,
    ErrorStrategy,
    Expression,
    HttpMethod,
    HttpRequestSpec,
    IntegrationMapping,
    IntegrationSpec,
    MappingRule,
    MappingTriggerSpec,
    MappingTriggerType,
)
from dazzle.http.runtime.event_bus import EntityEvent, EntityEventBus, EntityEventType
from dazzle.http.runtime.mapping_executor import MappingExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mapping(
    name: str = "test_mapping",
    entity_ref: str = "Company",
    trigger_type: MappingTriggerType = MappingTriggerType.ON_CREATE,
    method: HttpMethod = HttpMethod.POST,
    url_template: str = "/resources",
    request_mapping: list[MappingRule] | None = None,
    response_mapping: list[MappingRule] | None = None,
    on_error: ErrorStrategy | None = None,
    triggers: list[MappingTriggerSpec] | None = None,
) -> IntegrationMapping:
    if triggers is None:
        triggers = [MappingTriggerSpec(trigger_type=trigger_type)]
    return IntegrationMapping(
        name=name,
        entity_ref=entity_ref,
        triggers=triggers,
        request=HttpRequestSpec(method=method, url_template=url_template),
        request_mapping=request_mapping or [],
        response_mapping=response_mapping or [],
        on_error=on_error,
    )


def _make_integration(
    name: str = "test_api",
    base_url: str = "https://api.example.com",
    mappings: list[IntegrationMapping] | None = None,
    auth: AuthSpec | None = None,
    transport: str | None = None,
) -> IntegrationSpec:
    return IntegrationSpec(
        name=name,
        base_url=base_url,
        auth=auth,
        mappings=mappings or [],
        transport=transport,
    )


def _make_appspec(*integrations: IntegrationSpec) -> MagicMock:
    spec = MagicMock()
    spec.integrations = list(integrations)
    return spec


def _make_event(
    entity_name: str = "Company",
    event_type: EntityEventType = EntityEventType.CREATED,
    entity_id: str = "abc-123",
    data: dict[str, Any] | None = None,
) -> EntityEvent:
    return EntityEvent(
        event_type=event_type,
        entity_name=entity_name,
        entity_id=entity_id,
        data=data or {"id": entity_id, "name": "Test Co"},
    )


def _run(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_auto_triggers(self) -> None:
        mapping = _make_mapping(trigger_type=MappingTriggerType.ON_CREATE)
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        assert "Company" in executor._mappings_by_entity
        assert len(bus._handlers) == 1

    def test_skip_manual_only_triggers(self) -> None:
        mapping = _make_mapping(
            triggers=[MappingTriggerSpec(trigger_type=MappingTriggerType.MANUAL, label="Run")]
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        assert "Company" not in executor._mappings_by_entity
        assert len(bus._handlers) == 0

    def test_register_mixed_triggers(self) -> None:
        """A mapping with both auto and manual triggers should be registered."""
        mapping = _make_mapping(
            triggers=[
                MappingTriggerSpec(trigger_type=MappingTriggerType.ON_CREATE),
                MappingTriggerSpec(trigger_type=MappingTriggerType.MANUAL, label="Run"),
            ]
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        assert "Company" in executor._mappings_by_entity

    def test_register_no_integrations(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        assert len(bus._handlers) == 0

    def test_register_multiple_entities(self) -> None:
        m1 = _make_mapping(name="m1", entity_ref="Company")
        m2 = _make_mapping(name="m2", entity_ref="Client")
        integration = _make_integration(mappings=[m1, m2])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        assert "Company" in executor._mappings_by_entity
        assert "Client" in executor._mappings_by_entity


# ---------------------------------------------------------------------------
# URL Interpolation
# ---------------------------------------------------------------------------


class TestUrlInterpolation:
    @pytest.mark.parametrize(
        ("template", "data", "expected"),
        [
            (
                "/company/{self.company_number}",
                {"company_number": "12345678"},
                "https://api.example.com/company/12345678",
            ),
            (
                "/org/{org_id}/user/{user_id}",
                {"org_id": "org-1", "user_id": "user-2"},
                "https://api.example.com/org/org-1/user/user-2",
            ),
            (
                "/company/{self.missing_field}",
                {"name": "Test"},
                "https://api.example.com/company/",
            ),
            (
                "/resources/search",
                {"name": "Test"},
                "https://api.example.com/resources/search",
            ),
        ],
        ids=[
            "test_simple_interpolation",
            "test_multiple_placeholders",
            "test_missing_field",
            "test_no_placeholders",
        ],
    )
    def test_interpolation(self, template: str, data: dict, expected: str) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)
        url = executor._interpolate_url("https://api.example.com", template, data)
        assert url == expected


# ---------------------------------------------------------------------------
# Request Mapping
# ---------------------------------------------------------------------------


class TestRequestMapping:
    def test_simple_mapping(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        rules = [
            MappingRule(
                target_field="externalUserId",
                source=Expression(path="self.id"),
            ),
            MappingRule(
                target_field="type",
                source=Expression(literal="individual"),
            ),
        ]

        body = executor._apply_request_mapping(rules, {"id": "abc-123", "name": "Test"})
        assert body == {"externalUserId": "abc-123", "type": "individual"}

    def test_nested_target_field(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        rules = [
            MappingRule(
                target_field="fixedInfo.firstName",
                source=Expression(path="self.first_name"),
            ),
            MappingRule(
                target_field="fixedInfo.lastName",
                source=Expression(path="self.last_name"),
            ),
        ]

        body = executor._apply_request_mapping(rules, {"first_name": "Alice", "last_name": "Smith"})
        assert body == {"fixedInfo": {"firstName": "Alice", "lastName": "Smith"}}


# ---------------------------------------------------------------------------
# Response Mapping
# ---------------------------------------------------------------------------


class TestResponseMapping:
    def test_simple_response_mapping(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        rules = [
            MappingRule(
                target_field="company_name",
                source=Expression(path="response.company_name"),
            ),
            MappingRule(
                target_field="status",
                source=Expression(path="response.company_status"),
            ),
        ]

        result = executor._apply_response_mapping(
            rules, {"company_name": "Acme Ltd", "company_status": "active"}
        )
        assert result == {"company_name": "Acme Ltd", "status": "active"}

    def test_literal_in_response(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        rules = [
            MappingRule(
                target_field="synced",
                source=Expression(literal=True),
            ),
        ]

        result = executor._apply_response_mapping(rules, {})
        assert result == {"synced": True}

    def test_missing_response_field(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        rules = [
            MappingRule(
                target_field="status",
                source=Expression(path="response.nonexistent"),
            ),
        ]

        result = executor._apply_response_mapping(rules, {"other": "data"})
        assert result == {"status": None}


# ---------------------------------------------------------------------------
# Auth Resolution
# ---------------------------------------------------------------------------


class TestAuthResolution:
    def test_api_key_auth(self) -> None:
        auth = AuthSpec(auth_type=AuthType.API_KEY, credentials=["MY_API_KEY"])
        integration = _make_integration(auth=auth)
        appspec = _make_appspec(integration)
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        with patch.dict("os.environ", {"MY_API_KEY": "secret-key-123"}):
            headers = executor._resolve_auth_headers(integration)

        assert headers["Authorization"] == "Token secret-key-123"

    def test_bearer_auth(self) -> None:
        auth = AuthSpec(auth_type=AuthType.BEARER, credentials=["MY_TOKEN"])
        integration = _make_integration(auth=auth)
        appspec = _make_appspec(integration)
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        with patch.dict("os.environ", {"MY_TOKEN": "bearer-token-123"}):
            headers = executor._resolve_auth_headers(integration)

        assert headers["Authorization"] == "Bearer bearer-token-123"

    def test_basic_auth(self) -> None:
        auth = AuthSpec(auth_type=AuthType.BASIC, credentials=["USER", "PASS"])
        integration = _make_integration(auth=auth)
        appspec = _make_appspec(integration)
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        with patch.dict("os.environ", {"USER": "admin", "PASS": "secret"}):
            headers = executor._resolve_auth_headers(integration)

        import base64

        expected = base64.b64encode(b"admin:secret").decode()
        assert headers["Authorization"] == f"Basic {expected}"

    def test_no_auth(self) -> None:
        integration = _make_integration()
        appspec = _make_appspec(integration)
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        headers = executor._resolve_auth_headers(integration)
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_declared_headers_are_added_and_cannot_replace_auth(self) -> None:
        auth = AuthSpec(auth_type=AuthType.BEARER, credentials=["MY_TOKEN"])
        mapping = _make_mapping(
            request_mapping=[],
        )
        mapping = mapping.model_copy(
            update={
                "request": HttpRequestSpec(
                    method=HttpMethod.GET,
                    url_template="/records",
                    headers={
                        "Accept": "application/vnd.hmrc.5.0+json",
                        "Authorization": "Bearer stolen",
                        "content-type": "text/plain",
                    },
                )
            }
        )
        integration = _make_integration(auth=auth, mappings=[mapping])
        executor = MappingExecutor(_make_appspec(integration), EntityEventBus())

        with patch.dict("os.environ", {"MY_TOKEN": "bearer-token-123"}):
            headers = executor._request_headers(integration, mapping)

        assert headers["Accept"] == "application/vnd.hmrc.5.0+json"
        assert headers["Authorization"] == "Bearer bearer-token-123"
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Base URL Resolution
# ---------------------------------------------------------------------------


class TestBaseUrlResolution:
    @pytest.mark.parametrize(
        ("name", "url", "env", "expected"),
        [
            ("test_api", "https://api.example.com", None, "https://api.example.com"),
            ("test_api", "https://api.example.com/", None, "https://api.example.com"),
            (
                "my_api",
                None,
                {"DAZZLE_API_MY_API_URL": "https://fallback.com"},
                "https://fallback.com",
            ),
            ("unknown", None, None, ""),
        ],
        ids=[
            "test_direct_base_url",
            "test_trailing_slash_stripped",
            "test_env_var_fallback",
            "test_no_url_returns_empty",
        ],
    )
    def test_resolve_base_url(
        self, name: str, url: str | None, env: dict | None, expected: str
    ) -> None:
        integration = _make_integration(name=name, base_url=url)
        appspec = _make_appspec(integration)
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)
        if env is not None:
            with patch.dict("os.environ", env):
                assert executor._resolve_base_url(integration) == expected
        else:
            assert executor._resolve_base_url(integration) == expected


# ---------------------------------------------------------------------------
# Event Handling (handle_event)
# ---------------------------------------------------------------------------


class TestEventHandling:
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_on_create_triggers_mapping(self, mock_client_cls: MagicMock) -> None:
        """Entity created event triggers an ON_CREATE mapping."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "ext-1", "status": "created"}
        mock_resp.text = '{"id": "ext-1"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            trigger_type=MappingTriggerType.ON_CREATE,
            method=HttpMethod.POST,
            url_template="/resources",
            response_mapping=[
                MappingRule(target_field="external_id", source=Expression(path="response.id")),
            ],
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        update_fn = AsyncMock()
        executor = MappingExecutor(appspec, bus, update_entity=update_fn)
        executor.register_all()

        event = _make_event(event_type=EntityEventType.CREATED)
        _run(executor.handle_event(event))

        assert len(executor.results) == 1
        assert executor.results[0].success is True
        assert executor.results[0].mapped_fields == {"external_id": "ext-1"}
        update_fn.assert_called_once()

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_on_update_triggers_mapping(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_resp.text = "{}"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            trigger_type=MappingTriggerType.ON_UPDATE,
            method=HttpMethod.PUT,
            url_template="/resources/{self.external_id}",
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        event = _make_event(
            event_type=EntityEventType.UPDATED,
            data={"id": "abc-123", "external_id": "ext-1"},
        )
        _run(executor.handle_event(event))

        assert len(executor.results) == 1
        assert executor.results[0].success is True

    def test_unmatched_entity_ignored(self) -> None:
        mapping = _make_mapping(entity_ref="Client")
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        # Fire event for a different entity
        event = _make_event(entity_name="Company")
        _run(executor.handle_event(event))

        assert len(executor.results) == 0

    def test_unmatched_trigger_type_ignored(self) -> None:
        mapping = _make_mapping(trigger_type=MappingTriggerType.ON_CREATE)
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        # Fire update event when only create is registered
        event = _make_event(event_type=EntityEventType.UPDATED)
        _run(executor.handle_event(event))

        assert len(executor.results) == 0


# ---------------------------------------------------------------------------
# Request Mapping in HTTP Call
# ---------------------------------------------------------------------------


class TestRequestMappingIntegration:
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_request_body_built_from_mapping(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "new-1"}
        mock_resp.text = '{"id": "new-1"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            method=HttpMethod.POST,
            url_template="/applicants",
            request_mapping=[
                MappingRule(target_field="externalUserId", source=Expression(path="self.id")),
                MappingRule(target_field="type", source=Expression(literal="individual")),
                MappingRule(
                    target_field="fixedInfo.firstName",
                    source=Expression(path="self.first_name"),
                ),
            ],
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        event = _make_event(
            data={"id": "abc-123", "first_name": "Alice"},
        )
        _run(executor.handle_event(event))

        # Check the request was made with correct body
        call_args = mock_client.request.call_args
        assert call_args[1]["json"] == {
            "externalUserId": "abc-123",
            "type": "individual",
            "fixedInfo": {"firstName": "Alice"},
        }


# ---------------------------------------------------------------------------
# Error Strategy
# ---------------------------------------------------------------------------


class TestErrorStrategy:
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_ignore_error(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "internal"}
        mock_resp.text = '{"error": "internal"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            on_error=ErrorStrategy(actions=[ErrorAction.IGNORE]),
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        event = _make_event()
        _run(executor.handle_event(event))

        assert len(executor.results) == 1
        assert executor.results[0].success is False

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_set_fields_on_error(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {"error": "validation"}
        mock_resp.text = '{"error": "validation"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            on_error=ErrorStrategy(
                actions=[ErrorAction.LOG_WARNING],
                set_fields={"kyc_status": "error"},
            ),
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        update_fn = AsyncMock()
        executor = MappingExecutor(appspec, bus, update_entity=update_fn)
        executor.register_all()

        event = _make_event()
        _run(executor.handle_event(event))

        assert executor.results[0].success is False
        # set_fields should have been applied
        update_fn.assert_called_once_with("Company", "abc-123", {"kyc_status": "error"})

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_revert_transition(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {}
        mock_resp.text = "{}"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            triggers=[
                MappingTriggerSpec(
                    trigger_type=MappingTriggerType.ON_TRANSITION,
                    from_state="reviewed",
                    to_state="submitted",
                )
            ],
            on_error=ErrorStrategy(actions=[ErrorAction.REVERT_TRANSITION]),
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        update_fn = AsyncMock()
        executor = MappingExecutor(appspec, bus)
        executor._update_entity = update_fn
        executor.register_all()

        event = _make_event(
            event_type=EntityEventType.UPDATED,
            data={
                "id": "abc-123",
                "_previous_state": "reviewed",
                "status": "submitted",
            },
        )
        _run(executor.handle_event(event))

        # Should revert status to previous state
        update_fn.assert_any_call("Company", "abc-123", {"status": "reviewed"})

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_retry_on_failure(self, mock_client_cls: MagicMock) -> None:
        """Retry should attempt up to 3 times."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {"error": "unavailable"}
        mock_resp.text = "unavailable"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            on_error=ErrorStrategy(actions=[ErrorAction.RETRY]),
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        # Patch sleep to speed up test
        with patch("dazzle.http.runtime.mapping_executor.asyncio.sleep", new_callable=AsyncMock):
            event = _make_event()
            _run(executor.handle_event(event))

        # Should have retried 3 times total
        assert mock_client.request.call_count == 3
        assert executor.results[0].success is False

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_retry_succeeds_on_second_attempt(self, mock_client_cls: MagicMock) -> None:
        fail_resp = MagicMock()
        fail_resp.status_code = 503
        fail_resp.json.return_value = {}
        fail_resp.text = "unavailable"

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {"ok": True}
        success_resp.text = '{"ok": true}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=[fail_resp, success_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            on_error=ErrorStrategy(actions=[ErrorAction.RETRY]),
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        with patch("dazzle.http.runtime.mapping_executor.asyncio.sleep", new_callable=AsyncMock):
            event = _make_event()
            _run(executor.handle_event(event))

        assert mock_client.request.call_count == 2
        assert executor.results[0].success is True


# ---------------------------------------------------------------------------
# No Base URL
# ---------------------------------------------------------------------------


class TestNoBaseUrl:
    def test_no_base_url_returns_error(self) -> None:
        mapping = _make_mapping()
        integration = _make_integration(name="missing", base_url=None, mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        event = _make_event()
        _run(executor.handle_event(event))

        assert len(executor.results) == 1
        assert executor.results[0].success is False
        assert "No base_url" in (executor.results[0].error or "")


# ---------------------------------------------------------------------------
# Manual Execution
# ---------------------------------------------------------------------------


class TestManualExecution:
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_execute_manual(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"company_name": "Acme"}
        mock_resp.text = '{"company_name": "Acme"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            name="lookup",
            triggers=[MappingTriggerSpec(trigger_type=MappingTriggerType.MANUAL, label="Look up")],
            method=HttpMethod.GET,
            url_template="/company/{self.company_number}",
            response_mapping=[
                MappingRule(target_field="name", source=Expression(path="response.company_name")),
            ],
        )
        integration = _make_integration(name="ch_api", mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        result = _run(executor.execute_manual("ch_api", "lookup", {"company_number": "12345678"}))

        assert result.success is True
        assert result.mapped_fields == {"name": "Acme"}

    def test_execute_manual_not_found(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        with pytest.raises(ValueError, match="not found"):
            _run(executor.execute_manual("nonexistent", "mapping", {}))


# ---------------------------------------------------------------------------
# Transition Triggers
# ---------------------------------------------------------------------------


class TestTransitionTrigger:
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_transition_match(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_resp.text = "{}"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        mapping = _make_mapping(
            triggers=[
                MappingTriggerSpec(
                    trigger_type=MappingTriggerType.ON_TRANSITION,
                    from_state="draft",
                    to_state="submitted",
                )
            ],
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        event = _make_event(
            event_type=EntityEventType.UPDATED,
            data={"_previous_state": "draft", "status": "submitted"},
        )
        _run(executor.handle_event(event))

        assert len(executor.results) == 1
        assert executor.results[0].success is True

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_transition_no_match(self, mock_client_cls: MagicMock) -> None:
        mapping = _make_mapping(
            triggers=[
                MappingTriggerSpec(
                    trigger_type=MappingTriggerType.ON_TRANSITION,
                    from_state="draft",
                    to_state="submitted",
                )
            ],
        )
        integration = _make_integration(mappings=[mapping])
        appspec = _make_appspec(integration)
        bus = EntityEventBus()

        executor = MappingExecutor(appspec, bus)
        executor.register_all()

        # Wrong transition — should not fire
        event = _make_event(
            event_type=EntityEventType.UPDATED,
            data={"_previous_state": "submitted", "status": "approved"},
        )
        _run(executor.handle_event(event))

        assert len(executor.results) == 0


# ---------------------------------------------------------------------------
# Expression Evaluation
# ---------------------------------------------------------------------------


class TestExpressionEvaluation:
    def test_path_resolution(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        expr = Expression(path="self.name")
        assert executor._evaluate_expression(expr, {"self": {"name": "Acme"}}) == "Acme"

    def test_literal_value(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        expr = Expression(literal=42)
        assert executor._evaluate_expression(expr, {}) == 42

    def test_nested_path(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        expr = Expression(path="response.data.id")
        ctx = {"response": {"data": {"id": "x-1"}}}
        assert executor._evaluate_expression(expr, ctx) == "x-1"

    def test_missing_path_returns_none(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        expr = Expression(path="response.missing.field")
        assert executor._evaluate_expression(expr, {"response": {}}) is None


# ---------------------------------------------------------------------------
# Condition Evaluation
# ---------------------------------------------------------------------------


class TestConditionEvaluation:
    def test_no_condition(self) -> None:
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        trigger = MappingTriggerSpec(trigger_type=MappingTriggerType.ON_CREATE)
        assert executor._evaluate_condition(trigger, {"name": "Test"}) is True

    def test_ne_null_condition_with_value(self) -> None:
        """When field is not null, condition should pass."""
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef, Literal

        condition = BinaryExpr(
            left=FieldRef(path=["company_number"]),
            op=BinaryOp.NE,
            right=Literal(value=None),
        )
        trigger = MappingTriggerSpec(
            trigger_type=MappingTriggerType.ON_CREATE,
            condition_expr=condition,
        )

        assert executor._evaluate_condition(trigger, {"company_number": "123"}) is True

    def test_ne_null_condition_without_value(self) -> None:
        """When field is null, condition should fail."""
        appspec = _make_appspec()
        bus = EntityEventBus()
        executor = MappingExecutor(appspec, bus)

        from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef, Literal

        condition = BinaryExpr(
            left=FieldRef(path=["company_number"]),
            op=BinaryOp.NE,
            right=Literal(value=None),
        )
        trigger = MappingTriggerSpec(
            trigger_type=MappingTriggerType.ON_CREATE,
            condition_expr=condition,
        )

        assert executor._evaluate_condition(trigger, {"name": "Test"}) is False


# ---------------------------------------------------------------------------
# Nested Value Setting
# ---------------------------------------------------------------------------


class TestSetNestedValue:
    def test_flat_key(self) -> None:
        d: dict[str, Any] = {}
        MappingExecutor._set_nested_value(d, "name", "Test")
        assert d == {"name": "Test"}

    def test_dotted_key(self) -> None:
        d: dict[str, Any] = {}
        MappingExecutor._set_nested_value(d, "info.name", "Test")
        assert d == {"info": {"name": "Test"}}

    def test_deep_dotted_key(self) -> None:
        d: dict[str, Any] = {}
        MappingExecutor._set_nested_value(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_index_grows_a_list(self) -> None:
        d: dict[str, Any] = {}
        MappingExecutor._set_nested_value(d, "otherGains.0.assetType", "other-property")
        MappingExecutor._set_nested_value(d, "otherGains.1.assetType", "shares")
        assert d == {
            "otherGains": [
                {"assetType": "other-property"},
                {"assetType": "shares"},
            ]
        }

    def test_higher_index_leaves_a_hole(self) -> None:
        d: dict[str, Any] = {}
        MappingExecutor._set_nested_value(d, "rows.2.name", "third")
        assert d == {"rows": [None, None, {"name": "third"}]}


# ---------------------------------------------------------------------------
# transport: app (#1769)
# ---------------------------------------------------------------------------


def _app_mapping() -> IntegrationMapping:
    mapping = _make_mapping(
        name="submit",
        entity_ref="VATReturn",
        method=HttpMethod.POST,
        url_template="/organisations/vat/{self.vrn}/returns",
        request_mapping=[
            MappingRule(target_field="periodKey", source=Expression(path="self.period_key")),
        ],
        response_mapping=[
            MappingRule(
                target_field="hmrc_receipt_id",
                source=Expression(path="response.formBundleNumber"),
            ),
        ],
    )
    return mapping.model_copy(
        update={
            "request": HttpRequestSpec(
                method=HttpMethod.POST,
                url_template="/organisations/vat/{self.vrn}/returns",
                headers={"Accept": "application/vnd.hmrc.1.0+json"},
            )
        }
    )


class _MemCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, scope: str, url: str) -> dict[str, Any] | None:
        return self.store.get((scope, url))

    async def put(self, scope: str, url: str, data: dict[str, Any], ttl: int = 0) -> None:
        self.store[(scope, url)] = data

    async def acquire_lock(self, scope: str, url: str) -> bool:
        return True

    async def release_lock(self, scope: str, url: str) -> None:
        return None


class TestAppTransport:
    def test_hook_receives_the_rendered_request_and_no_socket_opens(self) -> None:
        seen: list[Any] = []

        async def hook(request: Any) -> tuple[int, dict[str, str]]:
            seen.append(request)
            return 200, {"formBundleNumber": "bundle-1"}

        mapping = _app_mapping()
        auth = AuthSpec(auth_type=AuthType.BEARER, credentials=["HMRC_TOKEN"])
        integration = _make_integration(
            name="hmrc_mtd",
            base_url="https://api.service.hmrc.gov.uk/",
            auth=auth,
            mappings=[mapping],
            transport="app",
        )
        executor = MappingExecutor(
            _make_appspec(integration),
            EntityEventBus(),
            app_transport=hook,
        )

        with (
            patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient") as client,
            patch.dict("os.environ", {"HMRC_TOKEN": "secret-token"}),
        ):
            result = _run(
                executor.execute_manual(
                    "hmrc_mtd",
                    "submit",
                    {"vrn": "123456789", "period_key": "24A1"},
                )
            )

        client.assert_not_called()
        assert result.success is True
        assert result.status_code == 200
        assert result.mapped_fields == {"hmrc_receipt_id": "bundle-1"}
        assert len(seen) == 1
        request = seen[0]
        assert request.method == "POST"
        assert request.path == "/organisations/vat/123456789/returns"
        assert request.base_url == "https://api.service.hmrc.gov.uk/"
        assert request.headers == {"Accept": "application/vnd.hmrc.1.0+json"}
        assert "Authorization" not in request.headers
        assert "Content-Type" not in request.headers
        assert request.body == {"periodKey": "24A1"}
        assert request.integration == "hmrc_mtd"
        assert request.mapping == "submit"

    def test_missing_hook_errors_without_opening_a_socket(self) -> None:
        mapping = _app_mapping()
        integration = _make_integration(name="hmrc_mtd", mappings=[mapping], transport="app")
        executor = MappingExecutor(_make_appspec(integration), EntityEventBus())

        with patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient") as client:
            result = _run(executor.execute_manual("hmrc_mtd", "submit", {"vrn": "1"}))

        client.assert_not_called()
        assert result.success is False
        assert result.error is not None
        assert "integration_transport is missing" in result.error

    def test_retry_calls_the_hook_again(self) -> None:
        seen: list[int] = []

        async def hook(request: Any) -> tuple[int, dict[str, str]]:
            seen.append(1)
            if len(seen) == 1:
                return 503, {"error": "busy"}
            return 200, {"formBundleNumber": "bundle-2"}

        mapping = _app_mapping().model_copy(
            update={"on_error": ErrorStrategy(actions=[ErrorAction.RETRY])}
        )
        integration = _make_integration(name="hmrc_mtd", mappings=[mapping], transport="app")
        executor = MappingExecutor(
            _make_appspec(integration),
            EntityEventBus(),
            app_transport=hook,
        )

        with patch("dazzle.http.runtime.mapping_transport.asyncio.sleep", new_callable=AsyncMock):
            result = _run(executor.execute_manual("hmrc_mtd", "submit", {"vrn": "1"}))

        assert seen == [1, 1]
        assert result.success is True
        assert result.mapped_fields == {"hmrc_receipt_id": "bundle-2"}

    def test_without_retry_a_transient_status_is_one_call(self) -> None:
        seen: list[int] = []

        async def hook(request: Any) -> tuple[int, dict[str, str]]:
            seen.append(1)
            return 503, {"error": "busy"}

        mapping = _app_mapping()
        integration = _make_integration(name="hmrc_mtd", mappings=[mapping], transport="app")
        executor = MappingExecutor(
            _make_appspec(integration),
            EntityEventBus(),
            app_transport=hook,
        )
        result = _run(executor.execute_manual("hmrc_mtd", "submit", {"vrn": "1"}))

        assert seen == [1]
        assert result.success is False
        assert result.status_code == 503

    def test_get_cache_wraps_the_hook(self) -> None:
        seen: list[Any] = []

        async def hook(request: Any) -> tuple[int, dict[str, str]]:
            seen.append(request)
            return 200, {"formBundleNumber": "cached"}

        mapping = _make_mapping(
            name="lookup",
            method=HttpMethod.GET,
            url_template="/vat/{self.vrn}",
            response_mapping=[
                MappingRule(
                    target_field="hmrc_receipt_id",
                    source=Expression(path="response.formBundleNumber"),
                ),
            ],
        )
        integration = _make_integration(name="hmrc_mtd", mappings=[mapping], transport="app")
        cache = _MemCache()
        executor = MappingExecutor(
            _make_appspec(integration),
            EntityEventBus(),
            cache=cache,  # type: ignore[arg-type]
            app_transport=hook,
        )
        first = _run(executor.execute_manual("hmrc_mtd", "lookup", {"vrn": "9"}))
        second = _run(executor.execute_manual("hmrc_mtd", "lookup", {"vrn": "9"}))

        assert first.success is True
        assert second.cache_hit is True
        assert second.mapped_fields == {"hmrc_receipt_id": "cached"}
        assert len(seen) == 1

    def test_project_module_hook_is_used_when_none_is_injected(self) -> None:
        import sys
        import types

        seen: list[Any] = []

        async def integration_transport(request: Any) -> tuple[int, dict[str, bool]]:
            seen.append(request)
            return 204, {"ok": True}

        module = types.ModuleType("pipeline.serve.app_init")
        module.integration_transport = integration_transport  # type: ignore[attr-defined]
        sys.modules["pipeline.serve.app_init"] = module
        try:
            mapping = _app_mapping()
            integration = _make_integration(name="hmrc_mtd", mappings=[mapping], transport="app")
            executor = MappingExecutor(_make_appspec(integration), EntityEventBus())
            with patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient") as client:
                result = _run(executor.execute_manual("hmrc_mtd", "submit", {"vrn": "1"}))
            client.assert_not_called()
            assert result.success is True
            assert len(seen) == 1
            assert seen[0].integration == "hmrc_mtd"
        finally:
            sys.modules.pop("pipeline.serve.app_init", None)
