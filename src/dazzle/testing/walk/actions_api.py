"""HTTP extension actions for scene walks (#1639).

Generic helpers used by CyFuture pilot walks (and any app) after SessionManager
auth. Not CyFuture-domain-specific except a best-effort hook for EL viewed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from dazzle.testing.walk.models import ActionSpec
from dazzle.testing.walk.results import ActionResult
from dazzle.testing.walk.results import render_template as _render


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize list endpoints: bare list, or {items|results|data: [...]}."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "rows"):
        val = payload.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    return []


def _field_get(row: dict[str, Any], field: str) -> Any:
    cur: Any = row
    for part in field.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _company_blob(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(k, "")) for k in ("company_name", "company", "name", "title", "display_name")
    )


def _row_matches(row: dict[str, Any], action: ActionSpec) -> bool:
    if action.where:
        for k, v in action.where.items():
            if _field_get(row, k) != v:
                return False
    if action.company_name_contains:
        if action.company_name_contains not in _company_blob(row):
            return False
    return True


def _prefer_key(row: dict[str, Any], prefer_status: str | None) -> tuple[int, str]:
    if prefer_status and str(row.get("status", "")) != prefer_status:
        return (1, str(row.get("id", "")))
    return (0, str(row.get("id", "")))


def _row_id(row: dict[str, Any]) -> str | None:
    for k in ("id", "uuid", "pk"):
        if row.get(k) is not None:
            return str(row[k])
    return None


async def _fetch_list_pages(
    client: httpx.AsyncClient, path: str, *, page_size: int = 50, max_pages: int = 20
) -> tuple[list[dict[str, Any]], ActionResult | None]:
    """GET paginated list; return (rows, error_or_none)."""
    all_rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        resp = await client.get(path, params={"page": page, "page_size": page_size})
        if resp.status_code >= 400:
            return [], ActionResult(
                "api_find", False, f"GET {path} page={page} → {resp.status_code}"
            )
        try:
            rows = _json_rows(resp.json())
        except Exception:
            return [], ActionResult("api_find", False, f"non-JSON response from {path}")
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
    return all_rows, None


async def api_find(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
) -> ActionResult:
    """GET list/search; pick first matching row; optional ``save_as`` id."""
    path = _render(action.path or "", vars_)
    if not path:
        return ActionResult("api_find", False, "api_find requires path:")

    rows, err = await _fetch_list_pages(client, path)
    if err is not None:
        return err
    candidates = [r for r in rows if _row_matches(r, action)]
    if not candidates:
        return ActionResult(
            "api_find",
            False,
            f"no row matched where={action.where!r} contains={action.company_name_contains!r}",
        )
    candidates.sort(key=lambda r: _prefer_key(r, action.prefer_status))
    chosen = candidates[0]
    rid = _row_id(chosen)
    if rid is None:
        return ActionResult("api_find", False, "matched row has no id/uuid/pk")
    if action.save_as:
        vars_[action.save_as] = rid
    return ActionResult(
        "api_find",
        True,
        f"found id={rid}" + (f" save_as={action.save_as}" if action.save_as else ""),
        {"id": rid, "save_as": action.save_as},
    )


async def api_ensure_status(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
) -> ActionResult:
    """PUT/PATCH entity so ``status`` matches (idempotent setup)."""
    path = _render(action.path_template or action.path or "", vars_)
    if not path or action.status is None:
        return ActionResult("api_ensure_status", False, "requires path_template/path and status:")
    get_resp = await client.get(path)
    if get_resp.status_code >= 400:
        return ActionResult("api_ensure_status", False, f"GET {path} → {get_resp.status_code}")
    try:
        body = get_resp.json()
    except Exception:
        body = {}
    current = body.get("status") if isinstance(body, dict) else None
    if current == action.status:
        return ActionResult(
            "api_ensure_status", True, f"already status={action.status}", {"path": path}
        )
    payload = {"status": action.status}
    resp = await client.patch(path, json=payload)
    if resp.status_code >= 400:
        resp = await client.put(path, json=payload)
    if resp.status_code >= 400:
        return ActionResult(
            "api_ensure_status",
            False,
            f"PATCH/PUT {path} → {resp.status_code}: {resp.text[:200]}",
        )
    return ActionResult(
        "api_ensure_status",
        True,
        f"set status {current!r} → {action.status!r}",
        {"path": path},
    )


async def api_assert_field(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
) -> ActionResult:
    """GET entity; assert JSON field equals expected."""
    path = _render(action.path_template or action.path or "", vars_)
    if not path or not action.field:
        return ActionResult("api_assert_field", False, "requires path_template + field")
    resp = await client.get(path)
    if resp.status_code >= 400:
        return ActionResult("api_assert_field", False, f"GET {path} → {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        return ActionResult("api_assert_field", False, "non-JSON response")
    if not isinstance(body, dict):
        return ActionResult("api_assert_field", False, "response is not an object")
    actual = _field_get(body, action.field)
    expected = action.equals
    ok = str(actual) == str(expected) if expected is not None else actual is not None
    return ActionResult(
        "api_assert_field",
        ok,
        f"{action.field}={actual!r}" if ok else f"{action.field}={actual!r} expected {expected!r}",
        {"path": path, "actual": actual, "expected": expected},
    )


def _render_json_body(raw: Any, vars_: dict[str, str]) -> Any:
    if not isinstance(raw, dict):
        return raw or {}
    return {k: _render(str(v), vars_) if isinstance(v, str) else v for k, v in raw.items()}


async def api_post(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
) -> ActionResult:
    """POST create; optional json body; optional save_as from response id."""
    path = _render(action.path or "", vars_)
    if not path:
        return ActionResult("api_post", False, "api_post requires path:")
    extra = action.model_extra or {}
    json_body = _render_json_body(extra.get("json") or extra.get("body") or action.where, vars_)
    resp = await client.post(path, json=json_body if json_body else None)
    if resp.status_code >= 400:
        return ActionResult(
            "api_post",
            False,
            f"POST {path} → {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except Exception:
        data = {}
    if action.save_as and isinstance(data, dict):
        rid = _row_id(data)
        if rid is not None:
            vars_[action.save_as] = rid
    return ActionResult(
        "api_post", True, f"POST {path} → {resp.status_code}", {"status": resp.status_code}
    )


def _resolve_file(raw: str, project_root: Path | None, vars_: dict[str, str]) -> Path | None:
    file_path = Path(_render(raw, vars_))
    if file_path.is_file():
        return file_path
    if project_root is not None:
        cand = project_root / file_path
        if cand.is_file():
            return cand
    return None


async def api_upload_file(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
    *,
    project_root: Path | None,
) -> ActionResult:
    """Multipart file upload."""
    path = _render(action.path_template or action.path or "", vars_)
    if not path:
        return ActionResult("api_upload_file", False, "requires path")
    extra = action.model_extra or {}
    file_field = str(extra.get("file_field") or extra.get("field") or "file")
    file_raw = extra.get("file") or extra.get("file_path") or action.name
    if not file_raw:
        return ActionResult("api_upload_file", False, "requires file: / file_path:")
    file_path = _resolve_file(str(file_raw), project_root, vars_)
    if file_path is None:
        return ActionResult("api_upload_file", False, f"file not found: {file_raw}")
    data_fields = _render_json_body(extra.get("data") or {}, vars_)
    with file_path.open("rb") as fh:
        resp = await client.post(
            path, data=data_fields or None, files={file_field: (file_path.name, fh)}
        )
    if resp.status_code >= 400:
        return ActionResult(
            "api_upload_file",
            False,
            f"POST {path} → {resp.status_code}: {resp.text[:200]}",
        )
    return ActionResult(
        "api_upload_file",
        True,
        f"uploaded {file_path.name} → {resp.status_code}",
        {"path": path},
    )


async def api_agent_ensure_el_viewed(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
) -> ActionResult:
    """App-domain hook — best-effort POST/PATCH {viewed: true}."""
    path = _render(action.path_template or action.path or "", vars_)
    if not path:
        return ActionResult(
            "api_agent_ensure_el_viewed",
            False,
            "app-specific: set path_template for POST {viewed:true}, "
            "or replace with api_ensure_status / api_post",
        )
    resp = await client.post(path, json={"viewed": True, "status": action.status or "viewed"})
    if resp.status_code >= 400:
        resp = await client.patch(path, json={"viewed": True})
    if resp.status_code >= 400:
        return ActionResult(
            "api_agent_ensure_el_viewed",
            False,
            f"POST/PATCH {path} → {resp.status_code} (rewrite YAML if domain-specific)",
        )
    return ActionResult(
        "api_agent_ensure_el_viewed", True, f"posted viewed on {path}", {"path": path}
    )


_HANDLERS = {
    "api_find": lambda c, a, v, pr: api_find(c, a, v),
    "api_ensure_status": lambda c, a, v, pr: api_ensure_status(c, a, v),
    "api_assert_field": lambda c, a, v, pr: api_assert_field(c, a, v),
    "api_post": lambda c, a, v, pr: api_post(c, a, v),
    "api_upload_file": lambda c, a, v, pr: api_upload_file(c, a, v, project_root=pr),
    "api_agent_ensure_el_viewed": lambda c, a, v, pr: api_agent_ensure_el_viewed(c, a, v),
}


async def dispatch_api_action(
    client: httpx.AsyncClient,
    action: ActionSpec,
    vars_: dict[str, str],
    *,
    project_root: Path | None,
) -> ActionResult:
    """Route one api_* action to its handler."""
    name = action.type.value
    handler = _HANDLERS.get(name)
    if handler is None:
        return ActionResult(name, False, f"unknown extension action {name!r}")
    return await handler(client, action, vars_, project_root)
