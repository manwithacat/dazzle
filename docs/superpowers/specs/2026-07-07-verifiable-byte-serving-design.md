# Verifiable byte-serving: streaming reads as a provable access boundary (#1551 item 5)

**Status**: Design approved (2026-07-07)
**Issue**: #1551 (item 5 — the last open item; items 1–4 shipped v0.93.129–132)
**Depends on**: the gated access core (#1422), `content_disposition` (#1551 item 3,
v0.93.132), the audit trail (`log_decision`), the claim ledger + `dazzle rbac prove`
(WP-0/1/2/7, v0.90.0–0.91.0)

## Problem

`FileService.download` loads a whole file into memory per request; the P1
document route and `/files/{id}/download` buffer full bytes, so a range-heavy
viewer (PDF.js) or a large asset amplifies memory per request. That is the
literal item-5 ask. But the maximal treatment reframes it: the byte-serving
surface must be a **provable access-control boundary** — every stored byte
served under an entity scope predicate, audited, and *statically guaranteed* to
have no bypass — so the framework can demonstrate verifiable RBAC and compliance
(ISO 27001 / SOC 2) over document access, not merely bounded memory.

Two residual holes from items 1–4 make the proof impossible today and are closed
here: ID-keyed `/files/{id}` reads are entity-UNSCOPED for any authenticated
user, and upload metadata triples are client-asserted (unverified).

## Decisions (locked during brainstorming)

1. **Maximal scope** — one range-aware streaming core; every server byte path
   memory-bounded; the PDF.js client half is a separate follow-up slice.
2. **All three verification surfaces** — claim ledger + static route proof +
   runtime audit completeness.
3. **Retire ID-keyed reads + owner-gated upload window** — every stored byte is
   served under the owning record's scope predicate OR to its uploader during
   the attach window; no other path exists.
4. **Coalesced audit** — one `log_decision` row per (user, document) access
   window; the scope check still runs on every request.

## Architecture

**Approach A — one byte-serving core behind the gate.** A single
`byte_serving` module every byte route calls. Enforcement stays upstream (the
gated access core); the core is pure Range-transport + audit and **cannot be
invoked without an access decision** (a required, non-optional parameter). That
single choke point is what makes the static proof mechanical.

Rejected: gate-in-place per route (N implementations = how the `/files` holes
happened); presigned/storage-native URLs (bytes escape the RBAC boundary and the
audit trail the moment the URL is minted — structurally unable to satisfy
verifiability; already ruled out by the hx-pdf spec).

### Section 1 — Storage adapter: `read_range`

`StorageBackend` gains:

```python
async def read_range(
    self, storage_key: str, start: int, end: int | None
) -> AsyncIterator[bytes]:
    """Yield bytes [start, end] inclusive; end=None means to EOF."""
```

- **Local**: `seek(start)` + 64KB chunks with a byte budget (stop at `end`).
- **S3**: `Range: bytes=start-end` on `get_object`, stream `iter_chunks`.
- The existing whole-file `stream()` becomes `read_range(key, 0, None)` — one
  primitive, no duplicate read paths.
- `metadata.size` is the length oracle (written at upload). The local backend
  cross-checks `stat().st_size` once per open and **fails loud** on a
  metadata/disk size mismatch rather than serving a wrong Content-Length
  (served-truncation hazard).

### Section 2 — The byte-serving core

New module `src/dazzle/http/runtime/byte_serving.py`, one entry point:

```python
async def serve_bytes(
    *,
    decision: AccessDecision,        # REQUIRED, non-optional — the proof hinges on this
    storage: StorageBackend,
    metadata: FileMetadata,
    range_header: str | None,
    disposition_kind: str,           # "inline" | "attachment"
    audit: AuditEmitter,
) -> Response:
    ...
```

- Takes an **already-granted** decision; never makes one (enforcement is the
  caller's, upstream).
- Parses/validates Range against `metadata.size` per RFC 9110 (the rules already
  in `document_routes`): satisfiable → 206 + Content-Range; unsatisfiable → 416
  + `Content-Range: bytes */size`; malformed/multipart → ignored (whole body,
  200).
- Streams via `storage.read_range` (never `download`).
- Sets shared headers: `X-Content-Type-Options: nosniff`, `Accept-Ranges:
  bytes`, `Cache-Control: private, max-age=0`, RFC 6266 disposition via the
  promoted `content_disposition`, inline restricted to the viewer-safe safelist.
- Calls `audit` with the decision on every request (the coalescer decides
  whether a row is written — Section 4).

`AccessDecision` is a frozen dataclass carrying `(user_id, entity, record_id,
field, matched_policy, verb)`. `serve_bytes` cannot be called without one — a
missing decision is a type error, reinforced by a test asserting the parameter
is non-optional.

### Section 3 — Enforcement + the retire/owner-window model

Every byte route resolves its decision *before* calling the core:

- **`/_dazzle/documents/{entity}/{id}/{field}/file|download`** — `gated_read` on
  the owning record (unchanged from P1); the decision carries the record's
  resolved scope/permit.
- **ID-keyed `/files/{id}/download|stream|thumbnail`** — **retired.** The
  file-field cell emitter re-points hrefs to the scoped document route (single
  change site; we own the emitter).
- **Upload-attach window** — a just-uploaded, not-yet-attached file is servable
  ONLY to its uploader:
  - uploads record `uploaded_by` from the **session** (not client input);
  - a new `GET /_dazzle/documents/pending/{file_id}` route grants iff
    `metadata.uploaded_by == current_user.id`, gated + audited + time-boxed
    (window = upload TTL);
  - once the file's triple is attached to a committed record, the pending route
    404s and the scoped record route takes over.
- **Attach-time triple verification** — when a record is written with a
  file-field value, the framework verifies the file's metadata triple matches
  the owning `(entity, id, field)` server-side; a mismatch is a loud validation
  error, not a silent accept. This closes the client-chosen-metadata hole
  (items 1–3 residual).

**Proof statement:** *every stored byte is served either under its owning
record's scope predicate, or to its uploader during the attach window — no other
path exists.*

### Section 4 — Audit coalescing

`serve_bytes` calls the audit layer with the decision on every request; a
coalescer decides whether a row is *written*:

- Key = `(user_id, entity, record_id, field)`. First access in a 15-minute
  window writes the full `log_decision` row (`operation="document_access"`,
  `matched_policy`, verb, range-or-full, disposition). Subsequent accesses
  within the window under the same key ride it — no new row.
- The **scope check runs on every request regardless** — coalescing touches only
  audit-row emission, never enforcement (a testable invariant).
- Window state is in-process (per-worker dict, monotonic-time TTL sweep).
  Multi-worker → at-most-N duplicate first-rows; acceptable (at-least-once
  evidence). No shared store, no new dependency.
- **416 / denied are never coalesced** — denials are the security-interesting
  rows; a flood of 416s is a signal, not noise.

### Section 5 — The three verification surfaces

1. **Claim (states it).** New `claims.toml` entry — *"Every stored file byte is
   served through an entity-scoped, audited access boundary; no route exposes
   stored bytes without an access decision."* — with a detector in
   `detectors.py` that activates only when (a) all byte routes route through
   `serve_bytes` and (b) no `uploaded_by`-less upload path exists. `evidence`
   command: `dazzle rbac byte-routes --strict`.

2. **Static proof (keeps it true).** New `dazzle rbac byte-routes --strict` +
   CI gate: AST-walk every `*_routes.py` for `StreamingResponse` / `FileResponse`
   / `Response(content=…)` whose content derives from a storage read; assert each
   is inside `serve_bytes` or calls it. A byte route that bypasses the core fails
   CI (the WP-3-flavour structural proof — makes the claim
   unfalsifiable-by-drift). **Load-bearing.**

3. **Runtime audit (demonstrates it happened).** The coalesced `log_decision`
   rows are the evidence artifact; `dazzle compliance evidence --control
   byte-access` surfaces them for an ISO 27001 / SOC 2 request (who accessed
   which document, when, under which policy). The audit-completeness test asserts
   every non-coalesced byte access produces a row.

### Section 6 — Testing

The proof is only as real as its tests.

- **Storage `read_range`** — both backends: exact range, suffix range, to-EOF,
  size-drift-fails-loud. S3 mock-backed (moto / existing shim); local real FS.
- **`serve_bytes`** — RFC 9110 matrix (206/416/200-on-malformed);
  decision-required (non-optional parameter + a test); streaming-not-buffering
  (assert `StreamingResponse` and that `read_range`, not `download`, is
  exercised).
- **Enforcement** — retired routes 404; pending route grants uploader-only,
  denies others, expires; attach-time triple verification rejects a forged
  triple (real-PG, scope_runtime_pg precedent).
- **Audit coalescing** — first-access writes, second-within-window doesn't,
  denial always writes, and the scope check ran both times (the
  enforcement-vs-audit separation invariant).
- **Static proof** — a deliberately-planted bypassing route makes
  `dazzle rbac byte-routes --strict` fail RED (the gate's own proof).

## Client half (separate follow-up slice)

Flip dz-pdf to range-based loading (`disableAutoFetch`, `disableStream: false`,
`rangeChunkSize`) so large PDFs open on first-page bytes rather than whole-file.
Ships AFTER the server core: it changes client fetch patterns and must re-verify
against the 47 pdf gates + the coalescing behaviour. The server design must not
assume it, but must not preclude it.

## Out of scope (YAGNI)

- Watermarking / server-generated view-variants (hx-pdf §19, already deferred).
- Presigned direct-S3 mode.
- Cross-worker shared coalesce state.
- Audit-row retention / rotation policy (an ops concern).

## Build order

1. Storage `read_range` (both backends) + size-drift guard.
2. `byte_serving.serve_bytes` core + the RFC 9110 matrix.
3. Repoint the document route(s) onto the core; retire ID-keyed reads; repoint
   the cell emitter.
4. Upload `uploaded_by` (session-sourced) + pending route + attach-time triple
   verification.
5. Audit coalescer.
6. The three verification surfaces (claim + `dazzle rbac byte-routes` static gate
   + `compliance evidence --control byte-access`).
7. (Separate slice) PDF.js range loading in dz-pdf.
