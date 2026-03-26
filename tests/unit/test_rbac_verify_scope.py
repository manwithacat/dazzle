"""Tests for dazzle rbac verify-scope — scope fidelity verification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.cli.rbac import (
    ScopeCheckResult,
    ScopeVerificationReport,
    analyze_scope_targets,
    format_scope_report,
    run_scope_verification,
)
from dazzle.core.ir.conditions import Comparison, ComparisonOperator, ConditionExpr, ConditionValue
from dazzle.core.ir.domain import (
    AccessSpec,
    EntitySpec,
    PermissionKind,
    ScopeRule,
)
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_field(name: str = "id") -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=FieldTypeKind.UUID))


def _make_entity(
    name: str,
    scopes: list[ScopeRule] | None = None,
) -> EntitySpec:
    access = AccessSpec(scopes=scopes or []) if scopes else None
    return EntitySpec(name=name, fields=[_make_field()], access=access)


def _make_scope(
    operation: PermissionKind = PermissionKind.READ,
    condition: ConditionExpr | None = None,
    personas: list[str] | None = None,
) -> ScopeRule:
    return ScopeRule(
        operation=operation,
        condition=condition,
        personas=personas or [],
    )


def _make_condition(field: str = "owner_id", value: str = "current_user") -> ConditionExpr:
    return ConditionExpr(
        comparison=Comparison(
            field=field,
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal=value),
        )
    )


def _make_appspec(entities: list[EntitySpec]) -> MagicMock:
    appspec = MagicMock()
    domain = MagicMock()
    domain.entities = entities
    appspec.domain = domain
    return appspec


# ---------------------------------------------------------------------------
# analyze_scope_targets
# ---------------------------------------------------------------------------


class TestAnalyzeScopeTargets:
    def test_entity_without_access_ignored(self) -> None:
        entity = _make_entity("Task", scopes=None)
        appspec = _make_appspec([entity])
        assert analyze_scope_targets(appspec) == []

    def test_entity_with_no_scopes_ignored(self) -> None:
        entity = _make_entity("Task", scopes=[])
        appspec = _make_appspec([entity])
        assert analyze_scope_targets(appspec) == []

    def test_read_scope_with_condition(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["agent"],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 1
        assert targets[0].entity_name == "Task"
        assert targets[0].persona_id == "agent"
        assert targets[0].is_all is False

    def test_scope_all_detected(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.READ,
            condition=None,
            personas=["admin"],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 1
        assert targets[0].is_all is True

    def test_list_scope_included(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.LIST,
            condition=_make_condition(),
            personas=["viewer"],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 1

    def test_create_scope_excluded(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.CREATE,
            condition=_make_condition(),
            personas=["editor"],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        assert analyze_scope_targets(appspec) == []

    def test_wildcard_persona(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=[],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 1
        assert targets[0].persona_id == "*"

    def test_multiple_personas(self) -> None:
        scope = _make_scope(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["agent", "customer"],
        )
        entity = _make_entity("Task", scopes=[scope])
        appspec = _make_appspec([entity])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 2
        assert {t.persona_id for t in targets} == {"agent", "customer"}

    def test_multiple_entities(self) -> None:
        scope1 = _make_scope(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["agent"],
        )
        scope2 = _make_scope(
            operation=PermissionKind.READ,
            condition=None,
            personas=["admin"],
        )
        e1 = _make_entity("Task", scopes=[scope1])
        e2 = _make_entity("Ticket", scopes=[scope2])
        appspec = _make_appspec([e1, e2])
        targets = analyze_scope_targets(appspec)
        assert len(targets) == 2


# ---------------------------------------------------------------------------
# ScopeCheckResult
# ---------------------------------------------------------------------------


class TestScopeCheckResult:
    def test_pass_when_scoped(self) -> None:
        r = ScopeCheckResult("Task", "agent", admin_count=50, persona_count=12, is_all=False)
        assert r.status == "PASS"

    def test_fail_when_same_count(self) -> None:
        r = ScopeCheckResult("Task", "agent", admin_count=50, persona_count=50, is_all=False)
        assert r.status == "FAIL"
        assert "100%" in r.status_display

    def test_pass_scope_all(self) -> None:
        r = ScopeCheckResult("Task", "admin", admin_count=50, persona_count=50, is_all=True)
        assert r.status == "PASS"
        assert "scope: all" in r.status_display

    def test_skip_zero_rows(self) -> None:
        r = ScopeCheckResult("Task", "agent", admin_count=0, persona_count=0, is_all=False)
        assert r.status == "SKIP"

    def test_error(self) -> None:
        r = ScopeCheckResult(
            "Task", "agent", admin_count=0, persona_count=0, is_all=False, error="timeout"
        )
        assert r.status == "ERROR"
        assert "timeout" in r.status_display

    def test_fail_percentage(self) -> None:
        r = ScopeCheckResult("Task", "agent", admin_count=100, persona_count=75, is_all=False)
        assert r.status == "PASS"  # 75 < 100


# ---------------------------------------------------------------------------
# ScopeVerificationReport
# ---------------------------------------------------------------------------


class TestScopeVerificationReport:
    def test_aggregates(self) -> None:
        report = ScopeVerificationReport(
            results=[
                ScopeCheckResult("A", "x", 10, 5, False),
                ScopeCheckResult("B", "y", 10, 10, False),
                ScopeCheckResult("C", "z", 0, 0, False),
                ScopeCheckResult("D", "w", 0, 0, False, error="fail"),
            ]
        )
        assert report.passed == 1
        assert report.failed == 1
        assert report.skipped == 1
        assert report.errors == 1

    def test_to_json(self) -> None:
        report = ScopeVerificationReport(results=[ScopeCheckResult("Task", "agent", 50, 12, False)])
        data = report.to_json()
        assert len(data) == 1
        assert data[0]["entity"] == "Task"
        assert data[0]["status"] == "PASS"


# ---------------------------------------------------------------------------
# format_scope_report
# ---------------------------------------------------------------------------


class TestFormatScopeReport:
    def test_empty_report(self) -> None:
        report = ScopeVerificationReport()
        output = format_scope_report(report)
        assert "No entities with scope rules found" in output

    def test_table_output(self) -> None:
        report = ScopeVerificationReport(
            results=[
                ScopeCheckResult("Task", "agent", 50, 12, False),
                ScopeCheckResult("Task", "manager", 50, 50, True),
            ]
        )
        output = format_scope_report(report)
        assert "Scope Fidelity Verification" in output
        assert "Task" in output
        assert "agent" in output
        assert "manager" in output
        assert "PASS" in output
        assert "2 checks" in output

    def test_summary_line(self) -> None:
        report = ScopeVerificationReport(
            results=[
                ScopeCheckResult("Task", "agent", 50, 50, False),
            ]
        )
        output = format_scope_report(report)
        assert "1 failed" in output


# ---------------------------------------------------------------------------
# run_scope_verification (mocked HTTP)
# ---------------------------------------------------------------------------


class TestRunScopeVerification:
    @pytest.mark.asyncio
    async def test_pass_when_scoped(self) -> None:
        appspec = _make_appspec(
            [
                _make_entity(
                    "Task",
                    scopes=[
                        _make_scope(
                            operation=PermissionKind.READ,
                            condition=_make_condition(),
                            personas=["agent"],
                        )
                    ],
                )
            ]
        )

        mock_client = AsyncMock()

        # Admin login response
        admin_login_resp = MagicMock()
        admin_login_resp.status_code = 200
        admin_login_resp.cookies = {"session": "admin-cookie"}

        # Persona login response
        persona_login_resp = MagicMock()
        persona_login_resp.status_code = 200
        persona_login_resp.cookies = {"session": "persona-cookie"}

        # Admin query response (50 rows)
        admin_query_resp = MagicMock()
        admin_query_resp.status_code = 200
        admin_query_resp.json.return_value = {"total": 50, "items": []}

        # Persona query response (12 rows)
        persona_query_resp = MagicMock()
        persona_query_resp.status_code = 200
        persona_query_resp.json.return_value = {"total": 12, "items": []}

        mock_client.request = AsyncMock(
            side_effect=[admin_login_resp, admin_query_resp, persona_login_resp, persona_query_resp]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value = mock_client
            report = await run_scope_verification(
                appspec, "http://localhost:8000", "admin@example.com", "admin"
            )

        assert len(report.results) == 1
        assert report.results[0].status == "PASS"
        assert report.results[0].admin_count == 50
        assert report.results[0].persona_count == 12

    @pytest.mark.asyncio
    async def test_fail_when_not_scoped(self) -> None:
        appspec = _make_appspec(
            [
                _make_entity(
                    "Ticket",
                    scopes=[
                        _make_scope(
                            operation=PermissionKind.READ,
                            condition=_make_condition(),
                            personas=["agent"],
                        )
                    ],
                )
            ]
        )

        mock_client = AsyncMock()

        admin_login_resp = MagicMock()
        admin_login_resp.status_code = 200
        admin_login_resp.cookies = {"session": "admin-cookie"}

        persona_login_resp = MagicMock()
        persona_login_resp.status_code = 200
        persona_login_resp.cookies = {"session": "persona-cookie"}

        # Both return 30 rows — scope not filtering
        admin_query_resp = MagicMock()
        admin_query_resp.status_code = 200
        admin_query_resp.json.return_value = {"total": 30, "items": []}

        persona_query_resp = MagicMock()
        persona_query_resp.status_code = 200
        persona_query_resp.json.return_value = {"total": 30, "items": []}

        mock_client.request = AsyncMock(
            side_effect=[admin_login_resp, admin_query_resp, persona_login_resp, persona_query_resp]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value = mock_client
            report = await run_scope_verification(
                appspec, "http://localhost:8000", "admin@example.com", "admin"
            )

        assert len(report.results) == 1
        assert report.results[0].status == "FAIL"

    @pytest.mark.asyncio
    async def test_scope_all_skips_persona_query(self) -> None:
        appspec = _make_appspec(
            [
                _make_entity(
                    "Task",
                    scopes=[
                        _make_scope(
                            operation=PermissionKind.READ,
                            condition=None,
                            personas=["admin"],
                        )
                    ],
                )
            ]
        )

        mock_client = AsyncMock()

        admin_login_resp = MagicMock()
        admin_login_resp.status_code = 200
        admin_login_resp.cookies = {"session": "admin-cookie"}

        admin_query_resp = MagicMock()
        admin_query_resp.status_code = 200
        admin_query_resp.json.return_value = {"total": 50, "items": []}

        # Only one POST (admin login) + one GET — no persona login needed
        mock_client.request = AsyncMock(side_effect=[admin_login_resp, admin_query_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value = mock_client
            report = await run_scope_verification(
                appspec, "http://localhost:8000", "admin@example.com", "admin"
            )

        assert len(report.results) == 1
        assert report.results[0].status == "PASS"
        assert report.results[0].is_all is True
        # Admin login + admin query, no persona login
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_admin_login_failure(self) -> None:
        appspec = _make_appspec(
            [
                _make_entity(
                    "Task",
                    scopes=[
                        _make_scope(
                            operation=PermissionKind.READ,
                            condition=_make_condition(),
                            personas=["agent"],
                        )
                    ],
                )
            ]
        )

        mock_client = AsyncMock()
        admin_login_resp = MagicMock()
        admin_login_resp.status_code = 401
        mock_client.request = AsyncMock(return_value=admin_login_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value = mock_client
            report = await run_scope_verification(
                appspec, "http://localhost:8000", "admin@example.com", "admin"
            )

        assert len(report.results) == 1
        assert report.results[0].status == "ERROR"
        assert "Admin login failed" in (report.results[0].error or "")

    @pytest.mark.asyncio
    async def test_no_targets_returns_empty(self) -> None:
        appspec = _make_appspec([_make_entity("Task")])

        report = await run_scope_verification(
            appspec, "http://localhost:8000", "admin@example.com", "admin"
        )
        assert len(report.results) == 0

    @pytest.mark.asyncio
    async def test_403_treated_as_zero(self) -> None:
        appspec = _make_appspec(
            [
                _make_entity(
                    "Task",
                    scopes=[
                        _make_scope(
                            operation=PermissionKind.READ,
                            condition=_make_condition(),
                            personas=["restricted"],
                        )
                    ],
                )
            ]
        )

        mock_client = AsyncMock()

        admin_login_resp = MagicMock()
        admin_login_resp.status_code = 200
        admin_login_resp.cookies = {"session": "admin-cookie"}

        persona_login_resp = MagicMock()
        persona_login_resp.status_code = 200
        persona_login_resp.cookies = {"session": "persona-cookie"}

        admin_query_resp = MagicMock()
        admin_query_resp.status_code = 200
        admin_query_resp.json.return_value = {"total": 10, "items": []}

        persona_query_resp = MagicMock()
        persona_query_resp.status_code = 403

        mock_client.request = AsyncMock(
            side_effect=[admin_login_resp, admin_query_resp, persona_login_resp, persona_query_resp]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value = mock_client
            report = await run_scope_verification(
                appspec, "http://localhost:8000", "admin@example.com", "admin"
            )

        assert report.results[0].persona_count == 0
        assert report.results[0].status == "PASS"
