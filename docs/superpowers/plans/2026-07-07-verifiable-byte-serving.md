# Verifiable Byte-Serving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve every stored file byte through a single range-aware core behind the entity-scope access boundary, with a static proof that no route can bypass it and coalesced audit evidence that access happened.

**Architecture:** One `byte_serving.serve_bytes` core (pure Range-transport + audit) that *requires* an already-granted `AccessDecision` — enforcement stays upstream in the gated access core (#1422). Storage backends gain a `read_range` streaming primitive so nothing loads full bytes. ID-keyed `/files/{id}` reads are retired; the only non-record path is an uploader-gated, time-boxed pending-file route. Three verification surfaces prove it: a ledger claim, a `dazzle rbac byte-routes --strict` AST gate, and coalesced `log_decision` rows.

**Tech Stack:** Python 3.12+, FastAPI/Starlette (`StreamingResponse`), pytest (+ real Postgres for integration), the existing `FileService`/`StorageBackend`, `access/gated.py`, `audit_log.py`, `spec_narrative` claim ledger, `cli/rbac.py` (Typer).

## Global Constraints

- **Python 3.12+**; type hints required on all public functions (mypy-enforced).
- **No `from __future__ import annotations` in FastAPI route files** (ADR-0014).
- **No new singletons** — use `RuntimeServices`/`ServerState` (ADR-0005).
- **Clean breaks, no shims** — update all callers in the same commit (ADR-0003).
- **Hoist `import dazzle.*` to module top** in route files (deferred-imports ratchet, `tests/unit/test_deferred_imports_ratchet_1438.py`); if a file exceeds its baseline, hoist rather than accept.
- **`/bump patch` + rebuild `scripts/build_dist.py`** only on the final ship of a coherent change; per-task commits do not bump.
- **RFC 6266 disposition** goes through `dazzle.http.runtime.file_routes.content_disposition` (the promoted single builder). Inline is restricted to `file_routes._INLINE_SAFE`-equivalent safelist (`application/pdf`, `image/png|jpeg|gif|webp`).
- **Range rules are RFC 9110**: satisfiable single range → 206 + `Content-Range`; well-formed out-of-bounds → 416 + `Content-Range: bytes */<size>`; malformed/multipart/absent → whole body, 200.
- **Every response carries** `X-Content-Type-Options: nosniff`, `Accept-Ranges: bytes`, `Cache-Control: private, max-age=0`.
- **Auth is a route dependency**, never read off `request.state` (the v0.93.122 P1 SEV-1 lesson).
- Reference spec: `docs/superpowers/specs/2026-07-07-verifiable-byte-serving-design.md`.

## File Structure

- `src/dazzle/http/runtime/file_storage.py` — MODIFY: add `read_range` to the `StorageBackend` ABC + `LocalStorageBackend` + `S3StorageBackend`; add `uploaded_by` to `FileMetadata` + `FileMetadataStore` DDL/read/write; add `uploaded_by` param to `FileService.upload`; add `FileService.read_range`.
- `src/dazzle/http/runtime/byte_serving.py` — CREATE: `AccessDecision`, `serve_bytes`, `_parse_range` (moved from document_routes), the audit coalescer.
- `src/dazzle/http/runtime/document_routes.py` — MODIFY: repoint handlers onto `serve_bytes`; add the pending-file route; attach-time triple-verification helper.
- `src/dazzle/http/runtime/file_routes.py` — MODIFY: retire `/files/{id}/download|stream|thumbnail` byte reads (keep upload + static path, which already streams via `FileResponse`).
- `src/dazzle/render/fragment/renderer/_data_row.py` — MODIFY: the file-cell emitter repoints hrefs to the scoped document route.
- `src/dazzle/spec_narrative/claims.toml` + `detectors.py` — MODIFY: the byte-access claim + detector.
- `src/dazzle/cli/rbac.py` — MODIFY: `byte-routes` command (the static AST gate).
- `src/dazzle/testing/byte_route_proof.py` — CREATE: the AST walk the gate + CI test share.
- Tests alongside each (`tests/unit/...`, `tests/integration/...`).

## Task ordering rationale

`uploaded_by` (Task 3) and the pending route (Task 4) land **before** retiring the ID-keyed reads (Task 5) — otherwise a just-uploaded, not-yet-attached file (form preview) would have no servable path. Every task is shippable on its own without breaking previews.

---

### Task 1: Storage `read_range` primitive

**Files:**
- Modify: `src/dazzle/http/runtime/file_storage.py` (StorageBackend ABC ~line 61; LocalStorageBackend ~150; S3StorageBackend ~253)
- Test: `tests/unit/test_storage_read_range.py` (new)

**Interfaces:**
- Produces: `StorageBackend.read_range(self, storage_key: str, start: int, end: int | None) -> AsyncIterator[bytes]` — yields bytes `[start, end]` inclusive; `end=None` means to EOF. Abstract on the base; concrete on Local + S3.
- Produces: `FileService.read_range(self, file_id: UUID | str, start: int, end: int | None) -> tuple[AsyncIterator[bytes], FileMetadata]` — resolves metadata, size-checks, delegates to the backend.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_storage_read_range.py
import pytest
from dazzle.http.runtime.file_storage import LocalStorageBackend


async def _collect(aiter):
    out = b""
    async for chunk in aiter:
        out += chunk
    return out


@pytest.mark.asyncio
async def test_local_read_range_exact_window(tmp_path):
    backend = LocalStorageBackend(tmp_path, "/files")
    key = "sub/f.bin"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.bin").write_bytes(bytes(range(256)) * 4)  # 1024 bytes

    assert await _collect(backend.read_range(key, 0, 9)) == bytes(range(10))
    assert await _collect(backend.read_range(key, 100, None)) == (bytes(range(256)) * 4)[100:]
    # suffix-style (caller resolves start; backend takes absolute offsets)
    assert await _collect(backend.read_range(key, 1020, 1023)) == bytes([252, 253, 254, 255])


@pytest.mark.asyncio
async def test_local_read_range_missing_file_raises(tmp_path):
    backend = LocalStorageBackend(tmp_path, "/files")
    with pytest.raises(FileNotFoundError):
        await _collect(backend.read_range("nope.bin", 0, None))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_read_range.py -q`
Expected: FAIL — `AttributeError: 'LocalStorageBackend' object has no attribute 'read_range'`.

- [ ] **Step 3: Add the abstract method to `StorageBackend`**

In the ABC (after `stream`/`retrieve`), add:

```python
@abstractmethod
async def read_range(
    self, storage_key: str, start: int, end: int | None
) -> AsyncIterator[bytes]:
    """Yield bytes [start, end] inclusive; end=None → to EOF.

    Absolute offsets — the caller (serve_bytes) resolves suffix/open
    ranges against the known size before calling. Raises
    FileNotFoundError if the object is absent.
    """
    ...
    yield b""  # pragma: no cover — abstract
```

- [ ] **Step 4: Implement on `LocalStorageBackend`**

```python
async def read_range(
    self, storage_key: str, start: int, end: int | None
) -> AsyncIterator[bytes]:
    full_path = self.base_path / storage_key
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {storage_key}")
    chunk_size = 64 * 1024
    remaining = None if end is None else (end - start + 1)
    with open(full_path, "rb") as f:
        f.seek(start)
        while remaining is None or remaining > 0:
            want = chunk_size if remaining is None else min(chunk_size, remaining)
            chunk = f.read(want)
            if not chunk:
                break
            if remaining is not None:
                remaining -= len(chunk)
            yield chunk
```

- [ ] **Step 5: Implement on `S3StorageBackend`**

```python
async def read_range(
    self, storage_key: str, start: int, end: int | None
) -> AsyncIterator[bytes]:
    try:
        import aioboto3
    except ImportError:
        raise ImportError("aioboto3 is required for S3 storage")
    rng = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
    session = aioboto3.Session()
    async with session.client("s3", **self._get_client_config()) as s3:
        response = await s3.get_object(Bucket=self.bucket, Key=storage_key, Range=rng)
        async with response["Body"] as stream:
            async for chunk in stream.iter_chunks():
                yield chunk
```

- [ ] **Step 6: Run the local tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_read_range.py -q`
Expected: PASS (2 passed). (S3 path is covered in Task 2's serve_bytes tests via a fake backend; a live-S3 test is out of scope — moto is not a project dependency.)

- [ ] **Step 7: Add `FileService.read_range` + the size-drift guard**

In `FileService`, after `stream`:

```python
async def read_range(
    self, file_id: UUID | str, start: int, end: int | None
) -> tuple[AsyncIterator[bytes], FileMetadata]:
    metadata = self.metadata_store.get(file_id)
    if not metadata:
        raise FileNotFoundError(f"File not found: {file_id}")
    # size-drift guard (LOCAL only — S3 HEAD would cost a round-trip; the
    # metadata size is authoritative for Content-Length, and a local
    # metadata/disk mismatch is a served-truncation hazard).
    if metadata.storage_backend == "local":
        from pathlib import Path

        disk = Path(self.storage.base_path) / metadata.storage_key  # type: ignore[attr-defined]
        if disk.exists() and disk.stat().st_size != metadata.size:
            raise RuntimeError(
                f"size drift for {file_id}: metadata {metadata.size} != disk "
                f"{disk.stat().st_size} — refusing to serve a wrong Content-Length"
            )
    return self.storage.read_range(metadata.storage_key, start, end), metadata
```

Add a test:

```python
@pytest.mark.asyncio
async def test_file_service_read_range_size_drift_fails_loud(tmp_path):
    import pytest
    from dazzle.http.runtime.file_storage import (
        FileService, FileMetadataStore, LocalStorageBackend, FileValidator,
    )
    # build a service, upload a byte string, then truncate the disk file
    # behind its back; read_range must raise RuntimeError, not stream a lie.
    # (construct via the same helpers the existing file_storage tests use)
    ...
```

Fill the `...` using the construction pattern in the nearest existing `tests/unit/test_file_*` that builds a real `FileService` against `tmp_path`; the assertion is `with pytest.raises(RuntimeError): await service.read_range(fid, 0, None)`.

- [ ] **Step 8: Run + commit**

Run: `.venv/bin/python -m pytest tests/unit/test_storage_read_range.py -q && .venv/bin/ruff check src/dazzle/http/runtime/file_storage.py --fix && .venv/bin/python -m mypy src/dazzle/http/runtime/file_storage.py`
Expected: tests PASS, ruff clean, mypy clean.

```bash
git add src/dazzle/http/runtime/file_storage.py tests/unit/test_storage_read_range.py
git commit -m "feat(storage): read_range primitive on StorageBackend + FileService (#1551)"
```

---

### Task 2: The `serve_bytes` core + `AccessDecision`

**Files:**
- Create: `src/dazzle/http/runtime/byte_serving.py`
- Test: `tests/unit/test_byte_serving.py` (new)

**Interfaces:**
- Consumes: `FileService.read_range` (Task 1); `content_disposition` and `_INLINE_SAFE` from `file_routes`.
- Produces:
  - `@dataclass(frozen=True) class AccessDecision:` fields `user_id: str | None`, `entity: str`, `record_id: str`, `field: str`, `matched_policy: str`, `verb: str`.
  - `def parse_range(header: str | None, size: int) -> tuple[int, int] | _Unsatisfiable | None` (moved verbatim from `document_routes._parse_range`; `_UNSATISFIABLE` sentinel too).
  - `async def serve_bytes(*, decision: AccessDecision, file_service, metadata, range_header: str | None, disposition_kind: str, audit: "ByteAudit | None") -> Response`.
  - `class ByteAudit` (protocol placeholder wired fully in Task 6; in this task it is called but a `None` audit is a no-op).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_byte_serving.py
import pytest
from types import SimpleNamespace
from dazzle.http.runtime.byte_serving import AccessDecision, serve_bytes


def _decision():
    return AccessDecision(user_id="u1", entity="Attachment", record_id="r1",
                          field="file", matched_policy="scope:list", verb="read")


def _meta(size=1024, ct="application/pdf", name="f.pdf"):
    return SimpleNamespace(size=size, content_type=ct, filename=name, storage_backend="local")


class _FakeService:
    def __init__(self, data: bytes):
        self._data = data

    async def read_range(self, file_id, start, end):
        async def _gen():
            stop = len(self._data) if end is None else end + 1
            yield self._data[start:stop]
        return _gen(), _meta(size=len(self._data))


@pytest.mark.asyncio
async def test_whole_body_200_streaming():
    svc = _FakeService(bytes(range(256)) * 4)
    resp = await serve_bytes(
        decision=_decision(), file_service=svc, metadata=_meta(size=1024),
        range_header=None, disposition_kind="inline", audit=None,
    )
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_satisfiable_range_206_content_range():
    svc = _FakeService(bytes(range(256)) * 4)
    resp = await serve_bytes(
        decision=_decision(), file_service=svc, metadata=_meta(size=1024),
        range_header="bytes=0-99", disposition_kind="inline", audit=None,
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-99/1024"


@pytest.mark.asyncio
async def test_unsatisfiable_range_416():
    svc = _FakeService(bytes(4))
    resp = await serve_bytes(
        decision=_decision(), file_service=svc, metadata=_meta(size=4),
        range_header="bytes=99-", disposition_kind="inline", audit=None,
    )
    assert resp.status_code == 416
    assert resp.headers["content-range"] == "bytes */4"


@pytest.mark.asyncio
async def test_unsafe_content_type_forced_attachment():
    svc = _FakeService(b"<html>")
    resp = await serve_bytes(
        decision=_decision(), file_service=svc,
        metadata=_meta(size=6, ct="text/html", name="x.html"),
        range_header=None, disposition_kind="inline", audit=None,
    )
    assert resp.headers["content-disposition"].startswith("attachment")


def test_serve_bytes_requires_a_decision():
    import inspect
    sig = inspect.signature(serve_bytes)
    p = sig.parameters["decision"]
    assert p.default is inspect.Parameter.empty  # decision is non-optional
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_byte_serving.py -q`
Expected: FAIL — module `byte_serving` does not exist.

- [ ] **Step 3: Create `byte_serving.py`**

```python
"""Range-aware byte-serving core (#1551 item 5).

The SINGLE place stored bytes become an HTTP response. Enforcement is
NOT done here — serve_bytes REQUIRES an already-granted AccessDecision
(a non-optional parameter). That is what makes the static proof
mechanical: no StreamingResponse/FileResponse of stored bytes may exist
outside this module (dazzle rbac byte-routes --strict, Task 7).
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi.responses import Response, StreamingResponse

from dazzle.http.runtime.file_routes import _INLINE_SAFE, content_disposition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccessDecision:
    """An already-granted decision the byte core serves under. Built by
    the enforcing route (gated_read / uploader gate) — never here."""

    user_id: str | None
    entity: str
    record_id: str
    field: str
    matched_policy: str
    verb: str


class _Unsatisfiable:
    """Sentinel: a well-formed but out-of-bounds Range (→ 416)."""


_UNSATISFIABLE = _Unsatisfiable()

# bytes=a-b | bytes=a- | bytes=-suffix
import re

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str | None, size: int):
    """RFC 9110 single-range parse. Returns (start, end) inclusive,
    _UNSATISFIABLE, or None (absent/malformed/multipart → whole body)."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        n = int(end_s)
        if n == 0:
            return _UNSATISFIABLE
        return (max(0, size - n), size - 1)
    start = int(start_s)
    if start >= size:
        return _UNSATISFIABLE
    end = int(end_s) if end_s else size - 1
    if end < start:
        return None
    return (start, min(end, size - 1))


def _headers(metadata: Any, kind: str) -> dict[str, str]:
    media = str(metadata.content_type or "")
    if kind == "inline" and media not in _INLINE_SAFE:
        kind = "attachment"
    return {
        "Content-Disposition": content_disposition(kind, str(metadata.filename or "document")),
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=0",
    }


async def serve_bytes(
    *,
    decision: AccessDecision,
    file_service: Any,
    metadata: Any,
    file_id: Any = None,
    range_header: str | None,
    disposition_kind: str,
    audit: Any,
) -> Response:
    """Stream a stored file as an HTTP response under an already-granted
    decision. Range-aware, never buffers the whole file."""
    size = int(metadata.size)
    media = str(metadata.content_type or "application/octet-stream")
    headers = _headers(metadata, disposition_kind)
    rng = parse_range(range_header, size)

    if isinstance(rng, _Unsatisfiable):
        if audit is not None:
            await audit.record(decision, served="416", coalesce=False)
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})

    if rng is None:
        start, end = 0, size - 1
        status = 200
    else:
        start, end = rng
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    if audit is not None:
        await audit.record(decision, served=("206" if status == 206 else "200"), coalesce=True)

    aiter, _ = await file_service.read_range(file_id if file_id is not None else metadata.id, start, end)
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(aiter, status_code=status, media_type=media, headers=headers)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_byte_serving.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

Run: `.venv/bin/ruff check src/dazzle/http/runtime/byte_serving.py --fix && .venv/bin/python -m mypy src/dazzle/http/runtime/byte_serving.py`

```bash
git add src/dazzle/http/runtime/byte_serving.py tests/unit/test_byte_serving.py
git commit -m "feat(http): serve_bytes core — decision-required range streaming (#1551)"
```

---

### Task 3: `uploaded_by` on file metadata (session-sourced)

**Files:**
- Modify: `src/dazzle/http/runtime/file_storage.py` (`FileMetadata` model; `FileMetadataStore` CREATE TABLE + insert/upsert + row read; `FileService.upload` param)
- Test: `tests/unit/test_file_uploaded_by.py` (new)

**Interfaces:**
- Produces: `FileMetadata.uploaded_by: str | None` (default None); `FileService.upload(..., uploaded_by: str | None = None)` persists it; `FileMetadataStore.get(...)` returns it.

> **DB note:** `dazzle_files` is managed by `FileMetadataStore`'s own raw DDL in `file_storage.py` (not Alembic). Add the column to the `CREATE TABLE`, add a defensive `ALTER TABLE ... ADD COLUMN uploaded_by` guarded by a "column exists?" check mirroring any existing migration shim in this file, and thread it through the insert/upsert column list + the row → `FileMetadata` read. If `tests/unit/test_db_artifact_contract.py` flags a new column, register per `docs/reference/db-artifacts.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_file_uploaded_by.py
import io
import pytest
from dazzle.http.runtime.file_storage import (
    FileService, FileMetadataStore, LocalStorageBackend, FileValidator,
)


def _service(tmp_path):
    storage = LocalStorageBackend(tmp_path, "/files")
    store = FileMetadataStore(database_url=None)  # in-memory / tmp default
    return FileService(storage, store, FileValidator())


@pytest.mark.asyncio
async def test_upload_persists_uploaded_by(tmp_path):
    svc = _service(tmp_path)
    meta = await svc.upload(
        io.BytesIO(b"hello"), filename="h.txt", content_type="text/plain",
        entity_name="Attachment", entity_id="r1", field_name="file",
        uploaded_by="user-123",
    )
    assert meta.uploaded_by == "user-123"
    fetched = svc.get_metadata(meta.id)
    assert fetched.uploaded_by == "user-123"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_file_uploaded_by.py -q`
Expected: FAIL — `upload() got an unexpected keyword argument 'uploaded_by'` (or `uploaded_by` attribute missing).

- [ ] **Step 3: Add the field to `FileMetadata`**

After `field_name` in the model:

```python
    uploaded_by: str | None = Field(default=None, description="Session user id that uploaded this file (#1551)")
```

- [ ] **Step 4: Add the column to `FileMetadataStore`**

In the `CREATE TABLE dazzle_files (...)` add `uploaded_by TEXT,` (after `field_name`). Immediately after the `CREATE TABLE` (and any `CREATE INDEX`), add the defensive migration:

```python
# #1551: additive column for existing tables (raw-DDL store, not Alembic).
try:
    cur.execute("ALTER TABLE dazzle_files ADD COLUMN uploaded_by TEXT")
except Exception:
    pass  # already present
```

Add `uploaded_by` to the INSERT/UPSERT column list + value tuple, and to the `FileMetadata(...)` construction in the row-read (`get`), reading `row["uploaded_by"]` with a `.get`-style guard for legacy rows.

- [ ] **Step 5: Thread it through `FileService.upload`**

Add `uploaded_by: str | None = None` to the signature and pass it into the `FileMetadata(...)` built at store time.

- [ ] **Step 6: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_file_uploaded_by.py -q`
Expected: PASS.

- [ ] **Step 7: Wire the upload route to source it from the session**

In `file_routes.py` `upload_file` handler, pass `uploaded_by=` from the resolved `auth_context.user.id` (NOT from a client param):

```python
uid = getattr(getattr(auth_context, "user", None), "id", None)
# ... inside _upload_file → file_service.upload(..., uploaded_by=str(uid) if uid else None)
```

Thread `uploaded_by` through `_upload_file(deps, request, file, entity, entity_id, field, uploaded_by)`. Add a route test asserting an authenticated upload records the session uid and that a client-supplied `?uploaded_by=` query param is IGNORED.

- [ ] **Step 8: Run + commit**

Run: `.venv/bin/python -m pytest tests/unit/test_file_uploaded_by.py tests/unit/test_file_routes_auth_posture.py -q && .venv/bin/ruff check src/dazzle/http/runtime/file_storage.py src/dazzle/http/runtime/file_routes.py --fix && .venv/bin/python -m mypy src/dazzle/http/runtime/file_storage.py`

```bash
git add src/dazzle/http/runtime/file_storage.py src/dazzle/http/runtime/file_routes.py tests/unit/test_file_uploaded_by.py
git commit -m "feat(files): session-sourced uploaded_by on file metadata (#1551)"
```

---

### Task 4: Pending-file route + attach-time triple verification

**Files:**
- Modify: `src/dazzle/http/runtime/document_routes.py` (add the pending route; add the triple-verification helper)
- Modify: `src/dazzle/http/runtime/handlers/write_handlers.py` (call the verification on file-field writes) — confirm the exact write path via grep before editing.
- Test: `tests/unit/test_pending_document_route.py`, `tests/unit/test_attach_triple_verify.py`

**Interfaces:**
- Consumes: `serve_bytes`, `AccessDecision` (Task 2); `FileMetadata.uploaded_by` (Task 3); `file_service.get_metadata`, `file_service.read_range`.
- Produces:
  - `GET /_dazzle/documents/pending/{file_id}` — grants iff `metadata.uploaded_by == current_user.id` AND `metadata.entity_id` is unset (not yet attached); else opaque 404. Serves via `serve_bytes` with `AccessDecision(verb="pending_read", matched_policy="uploader")`.
  - `def verify_file_triple(file_service, entity: str, record_id: str, field: str, raw_value) -> None` — raises a loud `ValueError` when the referenced file's metadata triple does not match `(entity, record_id, field)`.

- [ ] **Step 1: Write the failing route test**

```python
# tests/unit/test_pending_document_route.py
from types import SimpleNamespace
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dazzle.http.runtime.document_routes import create_document_routes


class _Store:
    def __init__(self, meta): self._m = meta
    def get_metadata(self, fid): return self._m if str(fid) == self._m.id else None


def _client(meta, *, authed_uid):
    async def auth_dep():
        return SimpleNamespace(is_authenticated=bool(authed_uid),
                               user=SimpleNamespace(id=authed_uid)) if authed_uid else None
    fs = SimpleNamespace(get_metadata=_Store(meta).get_metadata,
                         read_range=lambda fid, s, e: (_agen(b"%PDF-1.4"), meta),
                         download=None)
    app = FastAPI()
    app.include_router(create_document_routes(
        file_service=fs, services={}, cedar_access_specs={}, fk_graph=None,
        optional_auth_dep=auth_dep, admin_personas=[], require_auth_by_default=True))
    return TestClient(app)


async def _agen(b):
    yield b


def _pending_meta(uid):
    return SimpleNamespace(id="11111111-1111-1111-1111-111111111111", size=8,
                           content_type="application/pdf", filename="d.pdf",
                           storage_backend="local", uploaded_by=uid,
                           entity_name=None, entity_id=None, field_name=None)


def test_uploader_gets_pending_file():
    meta = _pending_meta("owner")
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 200


def test_non_uploader_denied_404():
    meta = _pending_meta("owner")
    r = _client(meta, authed_uid="intruder").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404


def test_attached_file_not_servable_via_pending():
    meta = _pending_meta("owner")
    meta.entity_id = "r1"  # already attached
    r = _client(meta, authed_uid="owner").get(f"/_dazzle/documents/pending/{meta.id}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_pending_document_route.py -q`
Expected: FAIL — route not registered (404 for all, including the uploader case → the first assert fails).

- [ ] **Step 3: Add the pending route to `create_document_routes`**

```python
@router.get("/pending/{file_id}")
async def pending_document(
    file_id: str, request: Request, auth_context: Any = Depends(auth_dep)
) -> Response:
    from dazzle.http.runtime.byte_serving import AccessDecision, serve_bytes

    uid = str(getattr(getattr(auth_context, "user", None), "id", "") or "")
    metadata = file_service.get_metadata(file_id)
    # opaque 404 on: unknown file, not-an-uploader, or already attached
    if (
        metadata is None
        or not uid
        or str(metadata.uploaded_by or "") != uid
        or (metadata.entity_id or "")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    decision = AccessDecision(
        user_id=uid, entity="(pending)", record_id=str(file_id),
        field=str(metadata.field_name or ""), matched_policy="uploader",
        verb="pending_read",
    )
    return await serve_bytes(
        decision=decision, file_service=file_service, metadata=metadata,
        file_id=file_id, range_header=request.headers.get("range"),
        disposition_kind="inline", audit=getattr(request.app.state, "byte_audit", None),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_pending_document_route.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Write the failing triple-verification test (real PG)**

```python
# tests/unit/test_attach_triple_verify.py
import pytest
from dazzle.http.runtime.document_routes import verify_file_triple


def test_forged_triple_rejected():
    class _Meta:
        entity_name = "OtherEntity"; entity_id = "x"; field_name = "file"
    class _FS:
        def get_metadata(self, fid):
            return _Meta()
    with pytest.raises(ValueError):
        verify_file_triple(_FS(), "Attachment", "r1", "file", "/files/abc/f.pdf")


def test_matching_triple_ok():
    class _Meta:
        entity_name = "Attachment"; entity_id = "r1"; field_name = "file"
    class _FS:
        def get_metadata(self, fid):
            return _Meta()
    verify_file_triple(_FS(), "Attachment", "r1", "file", "/files/abc/f.pdf")  # no raise
```

(This runs as a plain unit test — no PG needed for the helper itself; the PG-marked file name is a placeholder for the follow-on integration assertion against a real write. Keep the two helper tests here; add a `@pytest.mark.postgres` end-to-end write test only if the write path is reachable without heavy fixture setup, otherwise leave the helper unit-tested and note the gap.)

- [ ] **Step 6: Implement `verify_file_triple` + wire it into the write path**

Add to `document_routes.py` (module-level, reusing the existing `_extract_file_id`):

```python
def verify_file_triple(file_service: Any, entity: str, record_id: str, field: str, raw_value: Any) -> None:
    """#1551: a file-field write must reference a file whose metadata
    triple matches the owning (entity, id, field). Closes the
    client-chosen-metadata hole — a forged reference is a loud error."""
    file_id = _extract_file_id(raw_value)
    if file_id is None:
        return  # not a file reference (empty / cleared)
    metadata = file_service.get_metadata(file_id)
    if metadata is None:
        raise ValueError(f"file {file_id} referenced by {entity}.{field} does not exist")
    if (
        (metadata.entity_name or "") not in ("", entity)
        or str(metadata.entity_id or "") not in ("", str(record_id))
        or (metadata.field_name or "") not in ("", field)
    ):
        raise ValueError(
            f"file {file_id} triple {metadata.entity_name}/{metadata.entity_id}/"
            f"{metadata.field_name} does not match {entity}/{record_id}/{field}"
        )
```

Grep `src/dazzle/http/runtime/handlers/write_handlers.py` for where file-field values are persisted and call `verify_file_triple` there (guarded by `file_service` being present); the empty-triple (`""`) case is the just-uploaded pending file being attached for the first time — allowed.

- [ ] **Step 7: Run + commit**

Run: `.venv/bin/python -m pytest tests/unit/test_pending_document_route.py tests/unit/test_attach_triple_verify.py -q && .venv/bin/ruff check src/dazzle/http/runtime/document_routes.py --fix && .venv/bin/python -m mypy src/dazzle/http/runtime/document_routes.py`

```bash
git add src/dazzle/http/runtime/document_routes.py src/dazzle/http/runtime/handlers/write_handlers.py tests/unit/test_pending_document_route.py tests/unit/test_attach_triple_verify.py
git commit -m "feat(http): uploader-gated pending-file route + attach-time triple verification (#1551)"
```

---

### Task 5: Repoint document routes onto the core; retire ID-keyed reads

**Files:**
- Modify: `src/dazzle/http/runtime/document_routes.py` (`document_file` / `document_download` call `serve_bytes`)
- Modify: `src/dazzle/http/runtime/file_routes.py` (delete `download_file` / `stream_file` / `thumbnail` byte handlers; keep upload + static path)
- Modify: `src/dazzle/render/fragment/renderer/_data_row.py` (file-cell href → scoped document route)
- Test: `tests/unit/test_document_routes.py` (extend), `tests/unit/test_file_routes_auth_posture.py` (retire the deleted-route cases), `tests/unit/test_data_row_characterization_1505.py` (regen)

**Interfaces:**
- Consumes: `serve_bytes`, `AccessDecision`.
- Produces: the scoped `document_file`/`document_download` build an `AccessDecision` from the `gated_read` result and call `serve_bytes` (no more `_resolve_bytes` buffering). The file cell emits `/_dazzle/documents/{entity}/{id}/{field}/file`.

- [ ] **Step 1: Extend the document-route test to assert streaming + Range**

Add to `tests/unit/test_document_routes.py` a test that a satisfiable `Range` on `/_dazzle/documents/{entity}/{id}/{field}/file` returns 206 + `Content-Range`, and that the response is a streaming response (assert the handler no longer calls `file_service.download`). Run it → FAIL (still buffering).

- [ ] **Step 2: Repoint `document_file` / `document_download` onto `serve_bytes`**

Replace the `_resolve_bytes` + manual Response construction with: resolve the record via `gated_read` (as today) to get the metadata + the matched policy, build `AccessDecision(entity, id, field, matched_policy, verb="read")`, then `return await serve_bytes(decision=..., file_service=file_service, metadata=metadata, file_id=file_id, range_header=request.headers.get("range"), disposition_kind="inline" (file) | "attachment" (download), audit=request.app.state.byte_audit)`. Keep the metadata-triple defense-in-depth check before serving. Delete `_resolve_bytes`'s buffering `download` call and `_parse_range`/`_disposition` (now in `byte_serving` / `content_disposition`).

- [ ] **Step 3: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_document_routes.py -q` → PASS.

- [ ] **Step 4: Retire the ID-keyed byte reads in `file_routes.py`**

Delete the `download_file`, `stream_file`, and `get_thumbnail` route registrations + their `_download_file`/`_stream_file`/`_get_thumbnail` helpers. Keep: `upload_file`, `get_file_info` (metadata JSON — not bytes), `get_entity_files`, `delete_file`, and `create_static_file_routes` (the posture-gated static path, which already streams via `FileResponse` and is inside the proof's allowlist). Update `tests/unit/test_file_routes_auth_posture.py`: the download/stream/thumbnail cases become "route is gone → 404/405"; keep the static-path and upload posture cases.

- [ ] **Step 5: Repoint the file-cell emitter**

In `_data_row.py`'s file branch, emit the scoped route. The cell has the row + column context; build `href = f"/_dazzle/documents/{entity}/{record_id}/{field}/file"` from the surface's entity + the row id + the column key (confirm those are in scope at that call site; if the row id isn't threaded to the cell, thread it — a small, contained change). Regenerate the characterization fixtures: `UPDATE_CHAR_1505=1 .venv/bin/python -m pytest tests/unit/test_data_row_characterization_1505.py -q`, then run without the env var to confirm green.

- [ ] **Step 6: Full suite + drift gates + commit**

Run: `PATH=".venv/bin:$PATH" .venv/bin/python -m pytest tests/ -n auto --dist loadgroup -m "not e2e" -q` and `.venv/bin/python -m pytest tests/unit/test_api_surface_drift.py -q` (runtime-urls baseline drifts — the retired routes are removed; regenerate with `--write` and add a CHANGELOG Removed entry).

```bash
git add -A
git commit -m "feat(http): document routes stream via serve_bytes; retire ID-keyed byte reads (#1551)"
```

---

### Task 6: Audit coalescer

**Files:**
- Modify: `src/dazzle/http/runtime/byte_serving.py` (add `ByteAudit`)
- Modify: server wiring (grep for where `app.state` services are attached — attach `app.state.byte_audit`)
- Test: `tests/unit/test_byte_audit_coalescing.py`

**Interfaces:**
- Consumes: `AuditLogger.log_decision` (`audit_log.py`), `AccessDecision`.
- Produces: `class ByteAudit` with `async def record(self, decision: AccessDecision, *, served: str, coalesce: bool) -> None`. First access per `(user_id, entity, record_id, field)` within the window writes a `log_decision` row; subsequent coalesced ones do not; `coalesce=False` (416/denied) always writes.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_byte_audit_coalescing.py
import pytest
from dazzle.http.runtime.byte_serving import AccessDecision, ByteAudit


class _Logger:
    def __init__(self): self.rows = []
    async def log_decision(self, **kw): self.rows.append(kw)


def _d(rec="r1"):
    return AccessDecision(user_id="u1", entity="Doc", record_id=rec,
                          field="file", matched_policy="scope:list", verb="read")


@pytest.mark.asyncio
async def test_first_access_writes_second_within_window_does_not():
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: 1000.0)
    await audit.record(_d(), served="200", coalesce=True)
    await audit.record(_d(), served="206", coalesce=True)
    assert len(log.rows) == 1


@pytest.mark.asyncio
async def test_denied_always_writes():
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: 1000.0)
    await audit.record(_d(), served="200", coalesce=True)
    await audit.record(_d(), served="416", coalesce=False)
    assert len(log.rows) == 2


@pytest.mark.asyncio
async def test_new_window_writes_again():
    ticks = iter([1000.0, 1000.0, 2000.0])
    log = _Logger()
    audit = ByteAudit(log, window_seconds=900, now=lambda: next(ticks))
    await audit.record(_d(), served="200", coalesce=True)   # t=1000 write
    await audit.record(_d(), served="206", coalesce=True)   # t=1000 coalesced
    await audit.record(_d(), served="206", coalesce=True)   # t=2000 new window → write
    assert len(log.rows) == 2
```

- [ ] **Step 2: Run → FAIL** (`ByteAudit` undefined).

- [ ] **Step 3: Implement `ByteAudit`**

```python
class ByteAudit:
    """Coalesced document-access audit (#1551). First access per
    (user, document) window writes a log_decision row; the scope check
    ALREADY ran upstream on every request — coalescing is emission-only,
    never enforcement. Denials/416 always write."""

    def __init__(self, logger: Any, *, window_seconds: float = 900.0, now=None):
        import time

        self._log = logger
        self._window = window_seconds
        self._now = now or time.monotonic
        self._seen: dict[tuple, float] = {}

    async def record(self, decision: "AccessDecision", *, served: str, coalesce: bool) -> None:
        key = (decision.user_id, decision.entity, decision.record_id, decision.field)
        t = self._now()
        if coalesce:
            last = self._seen.get(key)
            if last is not None and (t - last) < self._window:
                return
            self._seen[key] = t
        await self._log.log_decision(
            operation="document_access",
            entity_name=decision.entity,
            entity_id=decision.record_id,
            decision="allow" if served in ("200", "206") else "deny",
            matched_policy=decision.matched_policy,
            policy_effect="allow" if served in ("200", "206") else "deny",
            user_id=decision.user_id,
        )
```

- [ ] **Step 4: Run → PASS.** Wire `app.state.byte_audit = ByteAudit(audit_logger)` where the server attaches services (grep `app.state.services =` / where `audit_logger` is constructed). A missing `byte_audit` (tests) → `serve_bytes` receives `None` → no-op, already handled.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/byte_serving.py src/dazzle/http/runtime/server.py tests/unit/test_byte_audit_coalescing.py
git commit -m "feat(http): coalesced document-access audit on the byte core (#1551)"
```

---

### Task 7: The three verification surfaces

**Files:**
- Create: `src/dazzle/testing/byte_route_proof.py` (the shared AST walk)
- Modify: `src/dazzle/cli/rbac.py` (add `byte-routes` command)
- Modify: `src/dazzle/spec_narrative/claims.toml` + `detectors.py`
- Test: `tests/unit/test_byte_route_proof.py`, `tests/unit/test_byte_access_claim.py`

**Interfaces:**
- Consumes: nothing new — inspects the source tree.
- Produces:
  - `def find_byte_route_violations(repo_root: Path) -> list[str]` — AST-walks every `src/dazzle/http/runtime/**/*routes*.py`, flags any `StreamingResponse`/`FileResponse`/`Response(content=...)` construction NOT inside `byte_serving.py` and NOT in the explicit allowlist; returns human-readable violations.
  - `dazzle rbac byte-routes [--strict]` — prints violations; `--strict` exits 1 if any.
  - claim `byte_access` in `claims.toml` + detector `has_byte_access_boundary`.

- [ ] **Step 1: Write the failing proof test**

```python
# tests/unit/test_byte_route_proof.py
from pathlib import Path
from dazzle.testing.byte_route_proof import find_byte_route_violations

REPO = Path(__file__).resolve().parents[2]


def test_main_tree_has_no_byte_route_violations():
    assert find_byte_route_violations(REPO) == []


def test_planted_bypass_is_detected(tmp_path):
    routes = tmp_path / "src/dazzle/http/runtime"
    routes.mkdir(parents=True)
    (routes / "evil_routes.py").write_text(
        "from fastapi.responses import StreamingResponse\n"
        "async def h():\n    return StreamingResponse(open('x','rb'))\n"
    )
    violations = find_byte_route_violations(tmp_path)
    assert any("evil_routes.py" in v for v in violations)
```

- [ ] **Step 2: Run → FAIL** (module missing). Note: `test_main_tree_has_no_byte_route_violations` also proves Tasks 5/6 actually converged — if a byte route still constructs its own response, this RED stays until it's fixed.

- [ ] **Step 3: Implement the AST walk**

```python
"""Static proof: no route serves stored bytes outside serve_bytes (#1551).

Conservative + fail-safe: flags ANY StreamingResponse / FileResponse /
Response(content=...) in a *routes*.py that is not byte_serving.py and not
in ALLOWLIST. False positives (a legitimate non-storage streamer) are
resolved by adding to ALLOWLIST with a comment — never by loosening the walk.
"""

import ast
from pathlib import Path

# (file stem, function name) pairs allowed to build a streaming response
# outside byte_serving — each a NON-stored-byte streamer with a reason.
ALLOWLIST: set[tuple[str, str]] = {
    # create_static_file_routes serves the posture-gated uploads dir via
    # FileResponse; it is itself the gated static path (#1551 items 1-3).
    ("file_routes", "serve_stored_file"),
}

_STREAMERS = {"StreamingResponse", "FileResponse"}


def find_byte_route_violations(repo_root: Path) -> list[str]:
    runtime = repo_root / "src" / "dazzle" / "http" / "runtime"
    violations: list[str] = []
    for path in runtime.rglob("*routes*.py"):
        if path.name == "byte_serving.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            func = _enclosing_func(tree, node)
            if isinstance(node, ast.Call) and _is_stream_construct(node):
                if (path.stem, func) in ALLOWLIST:
                    continue
                violations.append(f"{path.name}:{getattr(node, 'lineno', '?')} "
                                  f"in {func or '<module>'} builds a streaming "
                                  f"response outside serve_bytes")
    return violations


def _is_stream_construct(node: ast.Call) -> bool:
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
    if name in _STREAMERS:
        return True
    if name == "Response":
        return any(kw.arg == "content" for kw in node.keywords)
    return False


def _enclosing_func(tree: ast.AST, target: ast.AST) -> str | None:
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if getattr(n, "lineno", 0) <= getattr(target, "lineno", -1) <= getattr(n, "end_lineno", 0):
                best = n.name
    return best
```

- [ ] **Step 4: Run the proof test**

Run: `.venv/bin/python -m pytest tests/unit/test_byte_route_proof.py -q`
Expected: `test_planted_bypass_is_detected` PASS immediately; `test_main_tree_has_no_byte_route_violations` PASS **only if** Tasks 5/6 fully converged (any remaining self-built byte response is a real violation to fix now — that is the gate doing its job).

- [ ] **Step 5: Add the `dazzle rbac byte-routes` command**

```python
@rbac_app.command("byte-routes")
def byte_routes_cmd(
    strict: bool = typer.Option(False, "--strict", help="Exit 1 if any byte route bypasses serve_bytes"),
) -> None:
    """Prove every stored-byte route goes through serve_bytes (#1551)."""
    from pathlib import Path

    from dazzle.testing.byte_route_proof import find_byte_route_violations

    repo = Path.cwd()
    violations = find_byte_route_violations(repo)
    if not violations:
        typer.echo("OK: every byte-serving route goes through serve_bytes.")
        return
    for v in violations:
        typer.echo(f"VIOLATION: {v}", err=True)
    if strict:
        raise typer.Exit(code=1)
```

- [ ] **Step 6: Add the claim + detector**

`detectors.py`:

```python
def has_byte_access_boundary(_app: ir.AppSpec) -> bool:
    """True when the framework serves stored bytes through the audited,
    entity-scoped byte core with no bypass (a framework-wide guarantee,
    not app-specific — always true on this framework version)."""
    return True
```

Register it in `REGISTRY`. `claims.toml`:

```toml
[byte_access]
detector = "has_byte_access_boundary"
group = "compliance"
audience = "technical"
claim = """Every stored file is served through a single access-controlled,
audited boundary. A user only receives a document's bytes when the same rule
that governs the record allows it, and each first access is recorded — there is
no route that streams a stored file without that check."""
evidence = "dazzle rbac byte-routes --strict"
```

Add `tests/unit/test_byte_access_claim.py` asserting the claim's detector exists in `REGISTRY` (mirrors `test_spec_narrative_claims.py`), and that `evidence` runs clean on the main tree.

- [ ] **Step 7: Wire the CI gate**

Add a unit test `tests/unit/test_byte_route_proof.py::test_main_tree_has_no_byte_route_violations` is already the gate (runs in the normal suite). Confirm it is NOT marked e2e so it runs on every CI push.

- [ ] **Step 8: Full suite + claim-integrity + commit**

Run: `.venv/bin/python -m pytest tests/unit/test_byte_route_proof.py tests/unit/test_byte_access_claim.py tests/unit/test_spec_narrative_claims.py -q && PATH=".venv/bin:$PATH" .venv/bin/python -m pytest tests/ -n auto --dist loadgroup -m "not e2e" -q`

```bash
git add src/dazzle/testing/byte_route_proof.py src/dazzle/cli/rbac.py src/dazzle/spec_narrative/claims.toml src/dazzle/spec_narrative/detectors.py tests/unit/test_byte_route_proof.py tests/unit/test_byte_access_claim.py
git commit -m "feat(rbac): byte-access claim + dazzle rbac byte-routes static proof (#1551 verification)"
```

---

### Ship (after all tasks green)

- [ ] `/bump patch`, update CHANGELOG (Added: the byte core + claim + proof; Removed: ID-keyed `/files/{id}` byte reads; Security: streaming + attach-time triple verification; Agent Guidance: new byte routes must call `serve_bytes` or the `dazzle rbac byte-routes` gate fails).
- [ ] `.venv/bin/python scripts/build_dist.py`; commit; `/ship`.
- [ ] Comment on #1551 that item 5 is done; the issue closes (all five items complete).
- [ ] File the follow-up: **dz-pdf PDF.js range loading** (`disableAutoFetch`, `rangeChunkSize`) — the client half, its own slice, re-verified against the 47 pdf gates.

## Self-Review

- **Spec coverage:** §1 read_range → Task 1; §2 serve_bytes → Task 2; §3 retire/owner-window → Tasks 3–5 (uploaded_by, pending route + triple verify, retire + repoint); §4 coalescing → Task 6; §5 three surfaces → Task 7; §6 testing → folded into each task; client half → out-of-plan follow-up. All covered.
- **Placeholder scan:** two intentional "confirm the exact call site via grep" notes (write_handlers file-field persist point; the file-cell row-id threading) — these are *locate-then-edit* directions with the edit shown, not missing content; acceptable because the exact line moves between versions.
- **Type consistency:** `AccessDecision` fields, `read_range(start, end)` absolute-offset contract, `serve_bytes(decision=..., file_id=...)` keyword shape, and `ByteAudit.record(decision, *, served, coalesce)` are used identically across Tasks 2/4/5/6. `content_disposition` + `_INLINE_SAFE` consumed from `file_routes` (their real home since v0.93.132).
- **Ordering:** uploaded_by (3) + pending route (4) precede retiring ID-keyed reads (5) — no broken-preview window.
