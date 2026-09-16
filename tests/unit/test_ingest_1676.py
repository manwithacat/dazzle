"""Ingest DSL, validation, upsert, fingerprint, HTTP (#1676)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.ir.ingest import IngestProtectSpec, IngestSpec
from dazzle.core.lexer import tokenize
from dazzle.core.validation.ingest import validate_ingests
from dazzle.http.runtime.event_bus import EntityEventType
from dazzle.http.runtime.ingest_engine import (
    apply_ingest,
    canonical_fingerprint,
    parse_ingest_bytes,
)
from dazzle.http.runtime.ingest_routes import create_ingest_routes

pytestmark = pytest.mark.gate


def _parse_fragment(src: str):
    tokens = tokenize(src, "<test>")
    return Parser(tokens, file="<test>").parse()


def test_parse_ingest_block() -> None:
    frag = _parse_fragment(
        """
ingest readings_iot:
  entity: Reading
  key: [meter, taken_at]
  protect: source_kind = manual
"""
    )
    assert len(frag.ingests) == 1
    spec = frag.ingests[0]
    assert spec.name == "readings_iot"
    assert spec.entity == "Reading"
    assert spec.key == ("meter", "taken_at")
    assert spec.protect is not None
    assert spec.protect.field == "source_kind"
    assert spec.protect.value == "manual"
    assert spec.record_kind == "observation"


def test_validate_ingest_requires_unique_key() -> None:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.domain import DomainSpec, EntitySpec, FieldSpec
    from dazzle.core.ir.fields import FieldType, FieldTypeKind

    entity = EntitySpec(
        name="Reading",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="meter", type=FieldType(kind=FieldTypeKind.STR)),
        ],
    )
    appspec = AppSpec(
        name="t",
        title="t",
        domain=DomainSpec(entities=[entity]),
        ingests=[IngestSpec(name="r", entity="Reading", key=("meter",))],
    )
    errors, _ = validate_ingests(appspec)
    assert any("unique" in e for e in errors)


@pytest.mark.asyncio
async def test_apply_ingest_protect_and_fingerprint() -> None:
    spec = IngestSpec(
        name="r",
        entity="Reading",
        key=("meter",),
        protect=IngestProtectSpec(field="source_kind", value="manual"),
    )
    repo = MagicMock()
    repo.db = MagicMock()
    conn = MagicMock()
    repo.db.connection.return_value.__enter__.return_value = conn
    repo.db.connection.return_value.__exit__.return_value = False
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None  # fingerprint not seen

    outcomes = [
        (SimpleNamespace(id=uuid4(), meter="m1", source_kind="iot"), "inserted"),
        (SimpleNamespace(id=uuid4(), meter="m2", source_kind="manual"), "protected"),
    ]
    repo.upsert = AsyncMock(side_effect=outcomes)
    bus = MagicMock()
    bus.emit = AsyncMock()

    raw = json.dumps([{"meter": "m1"}, {"meter": "m2"}]).encode()
    fp = canonical_fingerprint(raw)
    result = await apply_ingest(
        spec=spec,
        rows=[{"meter": "m1"}, {"meter": "m2"}],
        repository=repo,
        fingerprint=fp,
        source_kind="iot",
        event_bus=bus,
    )
    assert result["inserted"] == 1
    assert result["protected"] == 1
    assert result["record_kind"] == "observation"
    assert result["idempotency"] == "content_hash"
    assert result["outcome"] == "applied"
    bus.emit.assert_awaited()
    event = bus.emit.await_args.args[0]
    assert event.event_type is EntityEventType.INGEST_BATCH_APPLIED
    assert event.data["record_kind"] == "observation"
    assert event.data["idempotency"] == "content_hash"


@pytest.mark.asyncio
async def test_apply_ingest_t_event_is_earliest_key_timestamp() -> None:
    """HLESS t_event is domain time (earliest key timestamp), not t_log."""
    spec = IngestSpec(name="r", entity="Reading", key=("meter", "taken_at"))
    repo = MagicMock()
    repo.db = MagicMock()
    conn = MagicMock()
    repo.db.connection.return_value.__enter__.return_value = conn
    repo.db.connection.return_value.__exit__.return_value = False
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    repo.upsert = AsyncMock(
        side_effect=[
            (SimpleNamespace(id=uuid4()), "inserted"),
            (SimpleNamespace(id=uuid4()), "inserted"),
        ]
    )
    result = await apply_ingest(
        spec=spec,
        rows=[
            {"meter": "m1", "taken_at": "2026-09-16T15:00:00Z"},
            {"meter": "m2", "taken_at": "2026-09-16T14:00:00Z"},
        ],
        repository=repo,
        fingerprint="abc",
    )
    assert result["t_event"].startswith("2026-09-16T14:00:00")
    assert result["t_log"]
    assert result["t_event"] != result["t_log"]
    assert result["record_kind"] == "observation"


def test_parse_jsonl_and_csv() -> None:
    jsonl = b'{"meter":"a"}\n{"meter":"b"}\n'
    assert [r["meter"] for r in parse_ingest_bytes(jsonl, "x.jsonl")] == ["a", "b"]
    csv_bytes = b"meter,value\nm1,1\n"
    rows = parse_ingest_bytes(csv_bytes, "x.csv")
    assert rows[0]["meter"] == "m1"


def test_ingest_http_json_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_INGEST_TOKEN", "secret-token")
    spec = IngestSpec(name="r", entity="Reading", key=("meter",))
    repo = MagicMock()
    repo.db = MagicMock()
    conn = MagicMock()
    repo.db.connection.return_value.__enter__.return_value = conn
    repo.db.connection.return_value.__exit__.return_value = False
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None
    repo.upsert = AsyncMock(return_value=(SimpleNamespace(id=uuid4(), meter="m1"), "inserted"))
    app = FastAPI()
    app.include_router(
        create_ingest_routes(ingests=[spec], repositories={"Reading": repo}, event_bus=None)
    )
    client = TestClient(app)
    resp = client.post(
        "/api/ingest/r",
        json={"rows": [{"meter": "m1"}], "source_kind": "iot"},
        headers={"X-Dazzle-Ingest-Token": "secret-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert body["record_kind"] == "observation"


def test_ingest_http_rejects_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DAZZLE_INGEST_TOKEN", raising=False)
    spec = IngestSpec(name="r", entity="Reading", key=("meter",))
    app = FastAPI()
    app.include_router(
        create_ingest_routes(ingests=[spec], repositories={"Reading": MagicMock()}, event_bus=None)
    )
    client = TestClient(app)
    resp = client.post("/api/ingest/r", json={"rows": []})
    assert resp.status_code == 401
