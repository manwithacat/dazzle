"""Ingest IR — declared file/IoT upsert into entities (#1676).

HLESS: an ingest *batch* is an OBSERVATION record (something was
reported to us; retries and late arrivals are expected). Row payloads
may carry domain time in a key field (t_event); t_log is ingest time.
Do not call the batch a FACT — re-drops are not irreversible domain
truth. See docs/architecture/hless-deep-dive.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .hless import RecordKind


class IngestProtectSpec(BaseModel):
    """Skip upsert when the existing row matches this equality."""

    field: str
    value: str

    model_config = ConfigDict(frozen=True)


class IngestSpec(BaseModel):
    """Named ingest path: entity, natural key, optional protect predicate."""

    name: str
    entity: str
    key: tuple[str, ...]
    protect: IngestProtectSpec | None = None
    # HLESS kind of the *batch* (never FACT — re-drops are expected).
    record_kind: str = RecordKind.OBSERVATION.value

    model_config = ConfigDict(frozen=True)

    @property
    def key_fields(self) -> tuple[str, ...]:
        return self.key
