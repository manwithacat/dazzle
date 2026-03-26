"""HTTP assertion runner for conformance cases.

Translates each ``ConformanceCase`` into an HTTP request against the
live FastAPI app and checks status code + row count.
"""

import logging
from typing import Any

from .models import ConformanceCase, ConformanceFixtures

logger = logging.getLogger(__name__)


async def run_case(
    client: Any,
    case: ConformanceCase,
    auth_tokens: dict[str, str],
    fixtures: ConformanceFixtures,
) -> Any:
    """Execute a single conformance case and return a CaseResult.

    Args:
        client: httpx.AsyncClient pointed at the test app
        case: The conformance case to execute
        auth_tokens: Mapping of persona name → session token
        fixtures: Fixture data (for row IDs needed by read/update/delete)

    Returns:
        CaseResult with pass/fail status and actual values
    """
    from .executor import CaseResult

    entity_slug = case.entity.lower()
    headers = _build_headers(case.persona, auth_tokens)

    try:
        if case.operation == "list":
            return await _run_list(client, case, entity_slug, headers)
        elif case.operation == "create":
            return await _run_create(client, case, entity_slug, headers, fixtures)
        elif case.operation in ("read", "update", "delete"):
            return await _run_row_op(client, case, entity_slug, headers, fixtures)
        else:
            return CaseResult(
                case=case,
                passed=False,
                actual_status=0,
                error=f"Unknown operation: {case.operation}",
            )
    except Exception as exc:
        return CaseResult(
            case=case,
            passed=False,
            actual_status=0,
            error=str(exc),
        )


def _build_headers(persona: str, auth_tokens: dict[str, str]) -> dict[str, str]:
    """Build request headers including auth cookie if available."""
    headers: dict[str, str] = {"Accept": "application/json"}
    token = auth_tokens.get(persona)
    if token:
        headers["Cookie"] = f"dazzle_session={token}"
    return headers


async def _run_list(
    client: Any,
    case: ConformanceCase,
    entity_slug: str,
    headers: dict[str, str],
) -> Any:
    """Execute a LIST operation and check status + row count."""
    from .executor import CaseResult

    resp = await client.get(f"/{entity_slug}s", headers=headers)

    status_ok = resp.status_code == case.expected_status

    # Check row count for successful list responses
    actual_rows: int | None = None
    rows_ok = True
    if resp.status_code == 200 and case.expected_rows is not None:
        try:
            body = resp.json()
            actual_rows = body.get("total", len(body.get("items", [])))
            rows_ok = actual_rows == case.expected_rows
        except Exception:
            rows_ok = False

    passed = status_ok and rows_ok
    error = None
    if not status_ok:
        error = f"Expected status {case.expected_status}, got {resp.status_code}"
    elif not rows_ok:
        error = f"Expected {case.expected_rows} rows, got {actual_rows}"

    return CaseResult(
        case=case,
        passed=passed,
        actual_status=resp.status_code,
        actual_rows=actual_rows,
        error=error,
    )


async def _run_create(
    client: Any,
    case: ConformanceCase,
    entity_slug: str,
    headers: dict[str, str],
    fixtures: ConformanceFixtures,
) -> Any:
    """Execute a CREATE operation and check status."""
    from .executor import CaseResult

    # Build minimal create payload from fixture entity row schema
    payload = _build_create_payload(case.entity, fixtures)

    resp = await client.post(f"/{entity_slug}s", json=payload, headers=headers)

    passed = resp.status_code == case.expected_status
    error = None
    if not passed:
        error = f"Expected status {case.expected_status}, got {resp.status_code}"

    return CaseResult(
        case=case,
        passed=passed,
        actual_status=resp.status_code,
        error=error,
    )


async def _run_row_op(
    client: Any,
    case: ConformanceCase,
    entity_slug: str,
    headers: dict[str, str],
    fixtures: ConformanceFixtures,
) -> Any:
    """Execute a READ, UPDATE, or DELETE on a specific row."""
    from .executor import CaseResult

    row_id = _pick_row_id(case, fixtures)
    if row_id is None:
        return CaseResult(
            case=case,
            passed=False,
            actual_status=0,
            error=f"No fixture row found for {case.entity} target={case.row_target}",
        )

    url = f"/{entity_slug}s/{row_id}"

    if case.operation == "read":
        resp = await client.get(url, headers=headers)
    elif case.operation == "update":
        resp = await client.put(url, json={}, headers=headers)
    elif case.operation == "delete":
        resp = await client.delete(url, headers=headers)
    else:
        return CaseResult(case=case, passed=False, actual_status=0, error="Unreachable")

    passed = resp.status_code == case.expected_status
    error = None
    if not passed:
        error = f"Expected status {case.expected_status}, got {resp.status_code}"

    return CaseResult(
        case=case,
        passed=passed,
        actual_status=resp.status_code,
        error=error,
    )


def _pick_row_id(case: ConformanceCase, fixtures: ConformanceFixtures) -> str | None:
    """Select the appropriate fixture row ID based on row_target.

    ``row_target="own"`` picks row 0 (owned by user_a of primary persona).
    ``row_target="other"`` picks row 1 (owned by user_b).
    """
    rows = fixtures.entity_rows.get(case.entity, [])
    if not rows:
        return None

    if case.row_target == "own":
        return rows[0].get("id") if len(rows) > 0 else None
    elif case.row_target == "other":
        return rows[1].get("id") if len(rows) > 1 else None
    else:
        # Default to first row
        return rows[0].get("id")


def _build_create_payload(
    entity_name: str,
    fixtures: ConformanceFixtures,
) -> dict[str, Any]:
    """Build a minimal JSON payload for entity creation.

    Uses the first fixture row as a template, stripping internal keys.
    """
    rows = fixtures.entity_rows.get(entity_name, [])
    if rows:
        # Use first row as template, exclude id and internal keys
        return {k: v for k, v in rows[0].items() if k != "id" and not k.startswith("_")}
    return {}
