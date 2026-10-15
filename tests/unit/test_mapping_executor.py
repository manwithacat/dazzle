"""Tests for the integration mapping executor (v0.30.0)."""

import asyncio
import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef, Literal
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
from dazzle.http.runtime.mapping_body import resolve_expression
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


def _resp(status_code: int, json_body: Any, text: str) -> MagicMock:
    """A canned httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = text
    return resp


def _install_http(mock_client_cls: MagicMock, *responses: MagicMock) -> AsyncMock:
    """Make the patched ``httpx.AsyncClient`` answer with ``responses`` in order
    (one response is returned for every call)."""
    client = AsyncMock()
    if len(responses) == 1:
        client.request = AsyncMock(return_value=responses[0])
    else:
        client.request = AsyncMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = client
    return client


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


@pytest.mark.parametrize(
    ("rules", "response", "expected"),
    [
        pytest.param(
            [
                MappingRule(
                    target_field="company_name", source=Expression(path="response.company_name")
                ),
                MappingRule(
                    target_field="status", source=Expression(path="response.company_status")
                ),
            ],
            {"company_name": "Acme Ltd", "company_status": "active"},
            {"company_name": "Acme Ltd", "status": "active"},
            id="paths",
        ),
        pytest.param(
            [MappingRule(target_field="synced", source=Expression(literal=True))],
            {},
            {"synced": True},
            id="literal",
        ),
        pytest.param(
            [MappingRule(target_field="status", source=Expression(path="response.nonexistent"))],
            {"other": "data"},
            {"status": None},
            id="missing-field-is-none",
        ),
    ],
)
def test_response_mapping(
    rules: list[MappingRule], response: dict[str, Any], expected: dict[str, Any]
) -> None:
    executor = MappingExecutor(_make_appspec(), EntityEventBus())
    assert executor._apply_response_mapping(rules, response) == expected


# ---------------------------------------------------------------------------
# Auth Resolution
# ---------------------------------------------------------------------------


class TestAuthResolution:
    @pytest.mark.parametrize(
        ("auth_type", "credentials", "env", "expected"),
        [
            pytest.param(
                AuthType.API_KEY,
                ["MY_API_KEY"],
                {"MY_API_KEY": "secret-key-123"},
                "Token secret-key-123",
                id="api-key",
            ),
            pytest.param(
                AuthType.BEARER,
                ["MY_TOKEN"],
                {"MY_TOKEN": "bearer-token-123"},
                "Bearer bearer-token-123",
                id="bearer",
            ),
            pytest.param(
                AuthType.BASIC,
                ["USER", "PASS"],
                {"USER": "admin", "PASS": "secret"},
                "Basic " + base64.b64encode(b"admin:secret").decode(),
                id="basic",
            ),
        ],
    )
    def test_authorization_header(
        self, auth_type: AuthType, credentials: list[str], env: dict[str, str], expected: str
    ) -> None:
        integration = _make_integration(auth=AuthSpec(auth_type=auth_type, credentials=credentials))
        executor = MappingExecutor(_make_appspec(integration), EntityEventBus())

        with patch.dict("os.environ", env):
            headers = executor._resolve_auth_headers(integration)

        assert headers["Authorization"] == expected

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
        _install_http(
            mock_client_cls, _resp(200, {"id": "ext-1", "status": "created"}, '{"id": "ext-1"}')
        )

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
        _install_http(mock_client_cls, _resp(200, {}, "{}"))

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
        mock_client = _install_http(mock_client_cls, _resp(201, {"id": "new-1"}, '{"id": "new-1"}'))

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
    @pytest.mark.parametrize(
        ("action", "responses", "expected_calls", "expected_success"),
        [
            pytest.param(
                ErrorAction.IGNORE,
                [_resp(500, {"error": "internal"}, '{"error": "internal"}')],
                1,
                False,
                id="ignore-records-one-failed-result",
            ),
            # Retry attempts up to 3 times in total.
            pytest.param(
                ErrorAction.RETRY,
                [_resp(503, {"error": "unavailable"}, "unavailable")],
                3,
                False,
                id="retry-gives-up-after-three-attempts",
            ),
            pytest.param(
                ErrorAction.RETRY,
                [_resp(503, {}, "unavailable"), _resp(200, {"ok": True}, '{"ok": true}')],
                2,
                True,
                id="retry-succeeds-on-second-attempt",
            ),
        ],
    )
    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_failure_attempts_and_result(
        self,
        mock_client_cls: MagicMock,
        action: ErrorAction,
        responses: list[MagicMock],
        expected_calls: int,
        expected_success: bool,
    ) -> None:
        mock_client = _install_http(mock_client_cls, *responses)
        mapping = _make_mapping(on_error=ErrorStrategy(actions=[action]))
        executor = MappingExecutor(
            _make_appspec(_make_integration(mappings=[mapping])), EntityEventBus()
        )
        executor.register_all()

        # Patch sleep so retry back-off doesn't slow the test.
        with patch("dazzle.http.runtime.mapping_executor.asyncio.sleep", new_callable=AsyncMock):
            _run(executor.handle_event(_make_event()))

        assert mock_client.request.call_count == expected_calls
        assert len(executor.results) == 1
        assert executor.results[0].success is expected_success

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_set_fields_on_error(self, mock_client_cls: MagicMock) -> None:
        _install_http(
            mock_client_cls, _resp(422, {"error": "validation"}, '{"error": "validation"}')
        )

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
        _install_http(mock_client_cls, _resp(500, {}, "{}"))

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
        _install_http(
            mock_client_cls, _resp(200, {"company_name": "Acme"}, '{"company_name": "Acme"}')
        )

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
        _install_http(mock_client_cls, _resp(200, {}, "{}"))

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
    @pytest.mark.parametrize(
        ("expr", "ctx", "expected"),
        [
            pytest.param(
                Expression(path="self.name"), {"self": {"name": "Acme"}}, "Acme", id="path"
            ),
            pytest.param(Expression(literal=42), {}, 42, id="literal"),
            pytest.param(
                Expression(path="response.data.id"),
                {"response": {"data": {"id": "x-1"}}},
                "x-1",
                id="nested-path",
            ),
        ],
    )
    def test_resolves(self, expr: Expression, ctx: dict[str, Any], expected: Any) -> None:
        assert resolve_expression(expr, ctx) == expected

    def test_missing_path_returns_none(self) -> None:
        expr = Expression(path="response.missing.field")
        assert resolve_expression(expr, {"response": {}}) is None


# ---------------------------------------------------------------------------
# Condition Evaluation
# ---------------------------------------------------------------------------

_COMPANY_NUMBER_NOT_NULL = BinaryExpr(
    left=FieldRef(path=["company_number"]), op=BinaryOp.NE, right=Literal(value=None)
)


@pytest.mark.parametrize(
    ("condition", "data", "expected"),
    [
        pytest.param(None, {"name": "Test"}, True, id="no-condition-passes"),
        pytest.param(
            _COMPANY_NUMBER_NOT_NULL,
            {"company_number": "123"},
            True,
            id="ne-null-with-value-passes",
        ),
        pytest.param(
            _COMPANY_NUMBER_NOT_NULL, {"name": "Test"}, False, id="ne-null-without-value-fails"
        ),
    ],
)
def test_evaluate_condition(
    condition: BinaryExpr | None, data: dict[str, Any], expected: bool
) -> None:
    executor = MappingExecutor(_make_appspec(), EntityEventBus())
    trigger = MappingTriggerSpec(
        trigger_type=MappingTriggerType.ON_CREATE, condition_expr=condition
    )
    assert executor._evaluate_condition(trigger, data) is expected


# ---------------------------------------------------------------------------
# Nested Value Setting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("assignments", "expected"),
    [
        pytest.param([("name", "Test")], {"name": "Test"}, id="flat-key"),
        pytest.param([("info.name", "Test")], {"info": {"name": "Test"}}, id="dotted-key"),
        pytest.param([("a.b.c", 42)], {"a": {"b": {"c": 42}}}, id="deep-dotted-key"),
        pytest.param(
            [("otherGains.0.assetType", "other-property"), ("otherGains.1.assetType", "shares")],
            {"otherGains": [{"assetType": "other-property"}, {"assetType": "shares"}]},
            id="index-grows-a-list",
        ),
        pytest.param(
            [("rows.2.name", "third")],
            {"rows": [None, None, {"name": "third"}]},
            id="higher-index-leaves-a-hole",
        ),
    ],
)
def test_set_nested_value(assignments: list[tuple[str, Any]], expected: dict[str, Any]) -> None:
    d: dict[str, Any] = {}
    for key, value in assignments:
        MappingExecutor._set_nested_value(d, key, value)
    assert d == expected


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


# ---------------------------------------------------------------------------
# Write-backs into rich-text fields are sanitised (flense ship W)
# ---------------------------------------------------------------------------


class TestRichTextWriteBack:
    """External responses can carry HTML; a write-back into a field a surface
    renders with ``widget=rich_text`` goes through ``clean_rich_text`` first,
    like the create/update handlers. Other fields are written as received."""

    @staticmethod
    def _executor(update_fn: AsyncMock, cap: str | None = None) -> MappingExecutor:
        from types import SimpleNamespace

        options = {"widget": "rich_text"}
        if cap:
            options["rich_text_max_length"] = cap
        element = SimpleNamespace(field_name="bio", options=options)
        surface = SimpleNamespace(
            entity_ref="Company", sections=[SimpleNamespace(elements=[element])]
        )
        appspec = _make_appspec()
        appspec.surfaces = [surface]
        return MappingExecutor(appspec, EntityEventBus(), update_entity=update_fn)

    def test_rich_text_field_is_sanitised_other_fields_untouched(self) -> None:
        update_fn = AsyncMock()
        executor = self._executor(update_fn)
        fields = {"bio": '<p>ok</p><img src=x onerror="alert(1)">', "note": "<b>raw</b>"}
        _run(executor._write_back("Company", "abc-123", fields))
        update_fn.assert_awaited_once_with(
            "Company", "abc-123", {"bio": "<p>ok</p>", "note": "<b>raw</b>"}
        )
        assert fields["bio"].endswith('onerror="alert(1)">')  # caller's dict not mutated

    def test_other_entities_are_written_as_received(self) -> None:
        update_fn = AsyncMock()
        _run(self._executor(update_fn)._write_back("Other", "1", {"bio": "<script>x</script>"}))
        update_fn.assert_awaited_once_with("Other", "1", {"bio": "<script>x</script>"})

    def test_over_cap_value_is_not_written(self) -> None:
        from dazzle.http.runtime.richtext_field import RichTextTooLongError

        update_fn = AsyncMock()
        executor = self._executor(update_fn, cap="10")
        with pytest.raises(RichTextTooLongError):
            _run(executor._write_back("Company", "1", {"bio": "<p>" + "x" * 50 + "</p>"}))
        update_fn.assert_not_awaited()

    @patch("dazzle.http.runtime.mapping_executor.httpx.AsyncClient")
    def test_response_mapping_write_back_is_sanitised(self, mock_client_cls: MagicMock) -> None:
        _install_http(
            mock_client_cls, _resp(200, {"bio": "<p>hi</p><script>alert(1)</script>"}, "{}")
        )

        mapping = _make_mapping(
            response_mapping=[
                MappingRule(target_field="bio", source=Expression(path="response.bio")),
            ],
        )
        update_fn = AsyncMock()
        executor = self._executor(update_fn)
        executor._appspec.integrations = [_make_integration(mappings=[mapping])]
        executor.register_all()
        _run(executor.handle_event(_make_event(event_type=EntityEventType.CREATED)))
        update_fn.assert_awaited_once_with("Company", "abc-123", {"bio": "<p>hi</p>alert(1)"})
