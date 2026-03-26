"""Tests for conformance Role 2: executor and HTTP runner (#601).

These tests validate the executor and runner logic using mocks —
no real PostgreSQL or FastAPI app needed. Integration tests requiring
a database are left for the conformance marker tests.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.conformance.executor import CaseResult, ConformanceExecutor
from dazzle.conformance.http_runner import _build_headers, _pick_row_id
from dazzle.conformance.models import ConformanceCase, ConformanceFixtures, ScopeOutcome

# =============================================================================
# CaseResult tests
# =============================================================================


class TestCaseResult:
    """CaseResult should capture pass/fail status and diagnostics."""

    def test_pass_result(self) -> None:
        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=4,
            scope_type=ScopeOutcome.ALL,
        )
        result = CaseResult(case=case, passed=True, actual_status=200, actual_rows=4)
        assert result.passed
        assert result.actual_status == 200
        assert result.actual_rows == 4
        assert "PASS" in repr(result)

    def test_fail_result(self) -> None:
        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=4,
            scope_type=ScopeOutcome.ALL,
        )
        result = CaseResult(
            case=case,
            passed=False,
            actual_status=403,
            error="Expected status 200, got 403",
        )
        assert not result.passed
        assert "FAIL" in repr(result)
        assert result.error is not None


# =============================================================================
# _build_headers tests
# =============================================================================


class TestBuildHeaders:
    """_build_headers should include auth cookie when token exists."""

    def test_with_token(self) -> None:
        headers = _build_headers("viewer", {"viewer": "tok123"})
        assert headers["Cookie"] == "dazzle_session=tok123"
        assert headers["Accept"] == "application/json"

    def test_without_token(self) -> None:
        headers = _build_headers("unauthenticated", {})
        assert "Cookie" not in headers
        assert headers["Accept"] == "application/json"

    def test_missing_persona(self) -> None:
        headers = _build_headers("unknown", {"viewer": "tok123"})
        assert "Cookie" not in headers


# =============================================================================
# _pick_row_id tests
# =============================================================================


class TestPickRowId:
    """_pick_row_id should select the correct fixture row."""

    def _fixtures_with_rows(self) -> ConformanceFixtures:
        return ConformanceFixtures(
            entity_rows={
                "Task": [
                    {"id": "row-0-id", "realm": "a"},
                    {"id": "row-1-id", "realm": "b"},
                    {"id": "row-2-id", "realm": "b"},
                    {"id": "row-3-id", "realm": "a"},
                ],
            },
        )

    def test_own_picks_row_0(self) -> None:
        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="own",
        )
        assert _pick_row_id(case, self._fixtures_with_rows()) == "row-0-id"

    def test_other_picks_row_1(self) -> None:
        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="other",
        )
        assert _pick_row_id(case, self._fixtures_with_rows()) == "row-1-id"

    def test_no_target_picks_row_0(self) -> None:
        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
        )
        assert _pick_row_id(case, self._fixtures_with_rows()) == "row-0-id"

    def test_missing_entity_returns_none(self) -> None:
        case = ConformanceCase(
            entity="Missing",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="own",
        )
        assert _pick_row_id(case, self._fixtures_with_rows()) is None


# =============================================================================
# ConformanceExecutor tests (mocked)
# =============================================================================


class TestConformanceExecutor:
    """ConformanceExecutor should orchestrate setup/run/teardown."""

    def test_init_defaults(self) -> None:
        cases = [
            ConformanceCase(
                entity="Task",
                persona="viewer",
                operation="list",
                expected_status=200,
                scope_type=ScopeOutcome.ALL,
            ),
        ]
        fixtures = ConformanceFixtures()
        executor = ConformanceExecutor(
            project_root="/tmp/test",
            cases=cases,
            fixtures=fixtures,
            database_url="postgresql://localhost/test_db",
        )
        assert executor.database_url == "postgresql://localhost/test_db"
        assert len(executor.cases) == 1

    def test_no_database_url_raises(self) -> None:
        executor = ConformanceExecutor(
            project_root="/tmp/test",
            cases=[],
            fixtures=ConformanceFixtures(),
        )
        executor.database_url = ""
        with pytest.raises(RuntimeError, match="No database URL"):
            import asyncio

            asyncio.run(executor.setup())


# =============================================================================
# run_case integration tests (mocked HTTP)
# =============================================================================


class TestRunCase:
    """run_case should make correct HTTP calls and check results."""

    @pytest.mark.asyncio
    async def test_list_success(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=4,
            scope_type=ScopeOutcome.ALL,
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"items": [1, 2, 3, 4], "total": 4}
        client.get = AsyncMock(return_value=resp)

        result = await run_case(client, case, {"viewer": "tok"}, ConformanceFixtures())
        assert result.passed
        assert result.actual_status == 200
        assert result.actual_rows == 4

    @pytest.mark.asyncio
    async def test_list_wrong_status(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=4,
            scope_type=ScopeOutcome.ALL,
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 403
        client.get = AsyncMock(return_value=resp)

        result = await run_case(client, case, {}, ConformanceFixtures())
        assert not result.passed
        assert "Expected status 200, got 403" in (result.error or "")

    @pytest.mark.asyncio
    async def test_list_wrong_row_count(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
            expected_rows=4,
            scope_type=ScopeOutcome.ALL,
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"items": [1, 2], "total": 2}
        client.get = AsyncMock(return_value=resp)

        result = await run_case(client, case, {"viewer": "tok"}, ConformanceFixtures())
        assert not result.passed
        assert "Expected 4 rows, got 2" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_success(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="editor",
            operation="create",
            expected_status=201,
            scope_type=ScopeOutcome.ALL,
        )
        fixtures = ConformanceFixtures(
            entity_rows={"Task": [{"id": "r1", "title": "Test"}]},
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 201
        client.post = AsyncMock(return_value=resp)

        result = await run_case(client, case, {"editor": "tok"}, fixtures)
        assert result.passed

    @pytest.mark.asyncio
    async def test_read_own_row(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="read",
            expected_status=200,
            row_target="own",
            scope_type=ScopeOutcome.FILTERED,
        )
        fixtures = ConformanceFixtures(
            entity_rows={"Task": [{"id": "own-id"}, {"id": "other-id"}]},
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        client.get = AsyncMock(return_value=resp)

        result = await run_case(client, case, {"viewer": "tok"}, fixtures)
        assert result.passed
        client.get.assert_called_once()
        call_url = client.get.call_args[0][0]
        assert "own-id" in call_url

    @pytest.mark.asyncio
    async def test_delete_denied(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="delete",
            expected_status=403,
            row_target="own",
            scope_type=ScopeOutcome.ACCESS_DENIED,
        )
        fixtures = ConformanceFixtures(
            entity_rows={"Task": [{"id": "r1"}, {"id": "r2"}]},
        )
        client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 403
        client.delete = AsyncMock(return_value=resp)

        result = await run_case(client, case, {}, fixtures)
        assert result.passed

    @pytest.mark.asyncio
    async def test_unknown_operation(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="archive",
            expected_status=200,
        )
        result = await run_case(AsyncMock(), case, {}, ConformanceFixtures())
        assert not result.passed
        assert "Unknown operation" in (result.error or "")

    @pytest.mark.asyncio
    async def test_exception_handling(self) -> None:
        from dazzle.conformance.http_runner import run_case

        case = ConformanceCase(
            entity="Task",
            persona="viewer",
            operation="list",
            expected_status=200,
        )
        client = AsyncMock()
        client.get = AsyncMock(side_effect=ConnectionError("refused"))

        result = await run_case(client, case, {}, ConformanceFixtures())
        assert not result.passed
        assert "refused" in (result.error or "")
