"""Gate: an orchestrator DDL change ships an incremental framework revision (#1850).

Production runs no boot-time DDL (#1462) and the squashed root ``0019`` reaches only
fresh databases, so an object added to ``_ensure_framework_schema_ddl`` reaches an
existing production database only through a new Alembic revision (ADR-0044, amended).

The orchestrator's statements are captured with a recording cursor (no database),
whitespace-normalised and hashed. The framework head revision declares the hash as
``ORCHESTRATOR_DDL_SHA256``. A changed orchestrator fails here until a NEW head
revision — whose idempotent DDL brings an already-stamped database to the new shape —
carries the new hash. Rewriting the constant on an existing revision defeats the
gate; the uniqueness check below at least refuses two revisions with one hash.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.gate

_VERSIONS = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "alembic" / "versions"


class _RecordingCursor:
    """A psycopg-cursor stand-in that records every statement it is asked to run."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: Any, params: Any = None) -> None:
        self.statements.append((str(sql), params))


def orchestrator_ddl_fingerprint() -> str:
    from dazzle.http.runtime.framework_schema import _ensure_framework_schema_ddl

    cur = _RecordingCursor()
    _ensure_framework_schema_ddl(cur)
    lines = [
        re.sub(r"\s+", " ", sql).strip() + ("" if params is None else f" -- {params!r}")
        for sql, params in cur.statements
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_fw_rev_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revisions() -> dict[str, ModuleType]:
    return {m.revision: m for m in (_load(p) for p in sorted(_VERSIONS.glob("0*.py")))}


def _head(revisions: dict[str, ModuleType]) -> str:
    parents = {m.down_revision for m in revisions.values()}
    heads = [rev for rev in revisions if rev not in parents]
    assert len(heads) == 1, f"framework chain must have one head, found {heads}"
    return heads[0]


def test_head_revision_pins_the_orchestrator_ddl() -> None:
    revisions = _revisions()
    head = _head(revisions)
    pinned = getattr(revisions[head], "ORCHESTRATOR_DDL_SHA256", None)
    current = orchestrator_ddl_fingerprint()
    assert pinned == current, (
        f"The orchestrator's DDL (_ensure_framework_schema_ddl) no longer matches the "
        f"fingerprint on the framework head {head!r} (pinned {pinned!r}, now {current!r}).\n"
        "Production runs no boot-time DDL, so add an incremental framework revision under "
        "src/dazzle/http/alembic/versions whose idempotent DDL brings an existing database "
        f"to the new shape, and declare on it ORCHESTRATOR_DDL_SHA256 = {current!r} "
        "(ADR-0044 as amended for #1850). Do not edit the constant on an existing revision."
    )


def test_fingerprints_are_unique_across_revisions() -> None:
    pinned = [
        (rev, m.ORCHESTRATOR_DDL_SHA256)
        for rev, m in _revisions().items()
        if hasattr(m, "ORCHESTRATOR_DDL_SHA256")
    ]
    hashes = [h for _, h in pinned]
    assert len(hashes) == len(set(hashes)), (
        f"two revisions pin the same orchestrator fingerprint: {pinned}"
    )


def test_fingerprint_reacts_to_a_ddl_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fingerprint covers delegated DDL, not only statements inline in the module."""
    from dazzle.http.runtime import framework_schema

    before = orchestrator_ddl_fingerprint()

    def _changed(cur: Any) -> None:
        cur.execute("CREATE TABLE IF NOT EXISTS _dazzle_usage_events (id BIGINT)")

    monkeypatch.setattr(framework_schema, "ensure_usage_events_table", _changed)
    assert orchestrator_ddl_fingerprint() != before
