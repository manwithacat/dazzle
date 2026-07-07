"""Range-aware byte-serving core (#1551 item 5).

The SINGLE place stored bytes become an HTTP response. Enforcement is
NOT done here — serve_bytes REQUIRES an already-granted AccessDecision
(a non-optional parameter). That is what makes the static proof
mechanical: no StreamingResponse/FileResponse of stored bytes may exist
outside this module (dazzle rbac byte-routes --strict, Task 7).
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from fastapi.responses import Response, StreamingResponse

from dazzle.http.runtime.file_routes import INLINE_SAFE_CONTENT_TYPES, content_disposition

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

# single-range form only: bytes=a-b | bytes=a- | bytes=-suffix
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str | None, size: int) -> "tuple[int, int] | _Unsatisfiable | None":
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
        # suffix range: last N bytes
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


class ByteAudit:
    """Protocol placeholder — fully wired in Task 6.

    Any audit object passed to serve_bytes must implement::

        async def record(self, decision: AccessDecision, *, served: str, coalesce: bool) -> None: ...
    """


def _headers(metadata: Any, kind: str) -> dict[str, str]:
    media = str(metadata.content_type or "")
    if kind == "inline" and media not in INLINE_SAFE_CONTENT_TYPES:
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

    fid = file_id if file_id is not None else getattr(metadata, "id", None)
    aiter, _ = await file_service.read_range(fid, start, end)
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(aiter, status_code=status, media_type=media, headers=headers)
