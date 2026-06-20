"""#1422: every create-handler variant exposes an in-process create invoker.

The experience-form POST mutates in-process via a registered `_inprocess_create`
invoker instead of self-fetching the REST create endpoint over loopback HTTP
(the #1421 tenant-Host-loss class). The cedar path's invoker is covered by the
PG scope oracle (`test_scope_runtime_pg.py`); this locks the two non-cedar
variants (auth, noauth) so *every* create route registers an invoker — the
precondition for deleting the proxy fallback.
"""

from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.audit_wrap import (
    _build_auth_handler,
    _build_noauth_handler,
)


def test_noauth_create_handler_exposes_inprocess_invoker_threading_body():
    """The no-auth create handler exposes `_inprocess_create`, and the invoker
    threads its pre-parsed body straight into the core handler (no re-parse)."""
    captured: dict[str, object] = {}

    async def fake_core(id_, request, **kwargs):
        captured["id"] = id_
        captured["kwargs"] = kwargs
        return {"id": "created"}

    handler = _build_noauth_handler(fake_core, is_create=True)

    invoker = getattr(handler, "_inprocess_create", None)
    assert invoker is not None, "noauth create handler must expose _inprocess_create"

    import asyncio

    body = {"title": "hello", "qty": None}
    request = MagicMock()
    result = asyncio.run(invoker(None, request, body=body))

    assert result == {"id": "created"}
    assert captured["id"] is None  # create => no resource id
    assert captured["kwargs"]["body"] is body  # body passed through unchanged
    assert captured["kwargs"]["current_user"] is None


def test_auth_create_handler_exposes_inprocess_invoker():
    """The auth (non-cedar) create handler exposes `_inprocess_create` with the
    uniform `(auth_context, request, *, body)` signature."""

    async def fake_core(id_, request, **kwargs):  # pragma: no cover - not invoked
        return {"id": "created"}

    handler = _build_auth_handler(
        fake_core,
        service=MagicMock(),
        auth_dep=lambda: None,
        operation="create",
        entity_name="Widget",
        audit_logger=None,
        include_field_changes=False,
        needs_pre_read=False,
        is_create=True,
    )

    invoker = getattr(handler, "_inprocess_create", None)
    assert invoker is not None, "auth create handler must expose _inprocess_create"


@pytest.mark.parametrize("is_create", [False])
def test_non_create_handlers_have_no_invoker(is_create):
    """Read/update/delete handlers (with-id) carry no create invoker."""

    async def fake_core(id_, request, **kwargs):  # pragma: no cover
        return None

    noauth = _build_noauth_handler(fake_core, is_create=is_create)
    assert getattr(noauth, "_inprocess_create", None) is None
