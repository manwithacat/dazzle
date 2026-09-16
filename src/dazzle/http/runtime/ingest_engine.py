"""Apply declared ingest specs: fingerprint, upsert, HLESS observation (#1676).

A completed batch is an OBSERVATION record (HLESS): we observed a file or
collector payload. It is not a FACT — re-drops and late IoT samples are
expected. Row domain time (a key timestamp) is t_event; ingest time is t_log.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from typing import Any

from dazzle.core.ir.hless import IdempotencyType, RecordKind
from dazzle.core.ir.ingest import IngestSpec
from dazzle.http.runtime.event_bus import EntityEvent, EntityEventType

FINGERPRINT_TABLE = "_dazzle_ingest_fingerprint"


def canonical_fingerprint(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_json_rows(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        raise ValueError("JSON ingest must be an array of objects or {rows: [...]}")
    return [row for row in data if isinstance(row, dict)]


def _parse_csv_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [{k: v for k, v in row.items() if k} for row in reader]


def _parse_jsonl_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def parse_ingest_bytes(raw: bytes, filename: str | None = None) -> list[dict[str, Any]]:
    """JSON array, JSONL, or CSV (header row = field names)."""
    name = (filename or "").lower()
    text = raw.decode("utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith("[") or name.endswith(".json"):
        return _parse_json_rows(text)
    first = stripped.splitlines()[0] if stripped else ""
    if name.endswith(".csv") or "," in first:
        return _parse_csv_rows(text)
    return _parse_jsonl_rows(text)


def _parse_domain_dt(val: object) -> datetime | None:
    """Parse a key-field value as domain time (HLESS t_event, not t_log)."""
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=UTC)
    if not isinstance(val, str) or len(val) < 10:
        return None
    try:
        parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _t_event_from_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> str | None:
    """Earliest timestamp-like key value in the batch — domain time, not ingest time."""
    stamps: list[datetime] = []
    for row in rows:
        for key in key_fields:
            parsed = _parse_domain_dt(row.get(key))
            if parsed is not None:
                stamps.append(parsed)
                break
    if not stamps:
        return None
    return min(stamps).isoformat()


def ensure_ingest_fingerprint_table(cur: Any) -> None:
    """Create ``_dazzle_ingest_fingerprint`` (idempotent). Orchestrator + Alembic 0021.

    Content-hash idempotency for ingest OBSERVATION batches (#1676). Orchestrator-only
    — no request-path CREATE (non-owner production role, #1495).
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_ingest_fingerprint (
            ingest_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ingest_name, sha256)
        )
    """)


def _fingerprint_seen(db: Any, ingest_name: str, sha256: str) -> bool:
    sql = f"SELECT 1 FROM {FINGERPRINT_TABLE} WHERE ingest_name = %s AND sha256 = %s"
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, (ingest_name, sha256))  # nosemgrep
        return cur.fetchone() is not None


def _remember_fingerprint(db: Any, ingest_name: str, sha256: str) -> None:
    sql = (
        f"INSERT INTO {FINGERPRINT_TABLE} (ingest_name, sha256) "
        "VALUES (%s, %s) ON CONFLICT DO NOTHING"
    )
    with db.connection() as conn:
        conn.cursor().execute(sql, (ingest_name, sha256))  # nosemgrep


async def apply_ingest(
    *,
    spec: IngestSpec,
    rows: list[dict[str, Any]],
    repository: Any,
    fingerprint: str | None,
    source_kind: str | None = None,
    event_bus: Any | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Upsert rows; skip identical fingerprints; emit an OBSERVATION record."""
    db = repository.db
    t_log = datetime.now(UTC).isoformat()
    t_event = _t_event_from_rows(rows, spec.key)
    if fingerprint and _fingerprint_seen(db, spec.name, fingerprint):
        result = _observation_result(
            spec,
            outcome="duplicate",
            fingerprint=fingerprint,
            t_log=t_log,
            t_event=t_event,
        )
        await _emit_observation(event_bus, spec, result, user_id)
        return result

    protect_field = spec.protect.field if spec.protect else None
    protect_value = spec.protect.value if spec.protect else None
    inserted = updated = unchanged = protected = 0
    for row in rows:
        payload = dict(row)
        if source_kind and "source_kind" not in payload:
            payload["source_kind"] = source_kind
        _row, outcome = await repository.upsert(
            payload,
            key_fields=spec.key,
            protect_field=protect_field,
            protect_value=protect_value,
        )
        if outcome == "inserted":
            inserted += 1
        elif outcome == "updated":
            updated += 1
        elif outcome == "protected":
            protected += 1
        else:
            unchanged += 1

    if fingerprint:
        _remember_fingerprint(db, spec.name, fingerprint)

    result = _observation_result(
        spec,
        outcome="applied",
        fingerprint=fingerprint,
        t_log=t_log,
        t_event=t_event,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        protected=protected,
    )
    await _emit_observation(event_bus, spec, result, user_id)
    return result


def _observation_result(
    spec: IngestSpec,
    *,
    outcome: str,
    fingerprint: str | None,
    t_log: str,
    t_event: str | None,
    inserted: int = 0,
    updated: int = 0,
    unchanged: int = 0,
    protected: int = 0,
) -> dict[str, Any]:
    """HLESS OBSERVATION envelope: record_kind, t_event, t_log, content-hash idempotency."""
    return {
        "ingest": spec.name,
        "record_kind": RecordKind.OBSERVATION.value,
        "idempotency": IdempotencyType.CONTENT_HASH.value,
        "outcome": outcome,
        "fingerprint": fingerprint,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "protected": protected,
        "t_log": t_log,
        "t_event": t_event,
    }


async def _emit_observation(
    event_bus: Any | None, spec: IngestSpec, result: dict[str, Any], user_id: str | None
) -> None:
    if event_bus is None:
        return
    event = EntityEvent(
        event_type=EntityEventType.INGEST_BATCH_APPLIED,
        entity_name=spec.entity,
        entity_id=result.get("fingerprint") or spec.name,
        data=result,
        user_id=user_id,
    )
    await event_bus.emit(event)
