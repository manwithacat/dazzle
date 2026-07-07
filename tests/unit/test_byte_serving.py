# tests/unit/test_byte_serving.py
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.byte_serving import AccessDecision, serve_bytes


def _decision():
    return AccessDecision(
        user_id="u1",
        entity="Attachment",
        record_id="r1",
        field="file",
        matched_policy="scope:list",
        verb="read",
    )


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
        decision=_decision(),
        file_service=svc,
        metadata=_meta(size=1024),
        range_header=None,
        disposition_kind="inline",
        audit=None,
    )
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_satisfiable_range_206_content_range():
    svc = _FakeService(bytes(range(256)) * 4)
    resp = await serve_bytes(
        decision=_decision(),
        file_service=svc,
        metadata=_meta(size=1024),
        range_header="bytes=0-99",
        disposition_kind="inline",
        audit=None,
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-99/1024"


@pytest.mark.asyncio
async def test_unsatisfiable_range_416():
    svc = _FakeService(bytes(4))
    resp = await serve_bytes(
        decision=_decision(),
        file_service=svc,
        metadata=_meta(size=4),
        range_header="bytes=99-",
        disposition_kind="inline",
        audit=None,
    )
    assert resp.status_code == 416
    assert resp.headers["content-range"] == "bytes */4"


@pytest.mark.asyncio
async def test_unsafe_content_type_forced_attachment():
    svc = _FakeService(b"<html>")
    resp = await serve_bytes(
        decision=_decision(),
        file_service=svc,
        metadata=_meta(size=6, ct="text/html", name="x.html"),
        range_header=None,
        disposition_kind="inline",
        audit=None,
    )
    assert resp.headers["content-disposition"].startswith("attachment")


def test_serve_bytes_requires_a_decision():
    import inspect

    sig = inspect.signature(serve_bytes)
    p = sig.parameters["decision"]
    assert p.default is inspect.Parameter.empty  # decision is non-optional
