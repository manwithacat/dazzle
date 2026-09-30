"""Anthropic Messages call sites must match the installed SDK's typed surface.

Why this exists
---------------
``anthropic`` 1.x **removed** ``temperature`` from ``Messages.create()``. Both
call sites passed it as a typed keyword, so on 1.x they raise::

    TypeError: Messages.create() got an unexpected keyword argument 'temperature'

Nothing caught it at runtime — the code only executes when the optional ``llm``
extra is installed and a call is actually made, so ``mypy`` on the default
environment passes and the failure surfaces as a 500 in the field. The typed
parameter is now forwarded through ``extra_body``, the SDK's documented escape
hatch, which keeps the documented ``temperature=0.0`` determinism and works on
both 0.x and 1.x.

What this catches
-----------------
A call site passing a keyword that the installed SDK no longer accepts, and a
silent loss of the temperature setting. Both are checked by *actually calling*
``Messages.create`` against a client that cannot authenticate, which fails
early with the real error type instead of a TypeError from argument binding.

How to satisfy it
-----------------
Forward unmodelled-but-valid parameters via ``extra_body``; drop parameters the
API no longer accepts. See ``dazzle.llm.api_client._call_anthropic``.

What this does NOT catch
------------------------
Wire-level rejection by the Anthropic API (a 400 for an unsupported parameter),
which needs a live key. This test only proves the call survives SDK argument
binding.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gate

anthropic = pytest.importorskip("anthropic", reason="requires the optional `llm` extra")


def _unauthed_client() -> object:
    return anthropic.Anthropic(api_key="sk-ant-not-a-real-key")


def _assert_reaches_api(call_kwargs: dict) -> None:
    """Call Messages.create and assert we got a *transport/auth* error.

    A TypeError here means the call shape is wrong for the installed SDK. Any
    other SDK error class means the arguments were accepted and the request was
    attempted.
    """
    with pytest.raises(Exception) as excinfo:  # noqa: B017 — we assert the type below
        _unauthed_client().messages.create(**call_kwargs)  # type: ignore[union-attr]

    assert not isinstance(excinfo.value, TypeError), (
        f"call shape rejected by anthropic {anthropic.__version__}: {excinfo.value}"
    )


def test_llm_api_client_call_shape_is_accepted() -> None:
    """`LLMAPIClient._call_anthropic` forwards temperature via extra_body.

    A dummy key is passed explicitly: the constructor raises when it cannot find
    one, so depending on the ambient environment made this pass locally and fail
    in CI with "API key not found for LLM client."
    """
    from dazzle.llm.api_client import LLMAPIClient

    client = LLMAPIClient(
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=8,
        api_key="sk-ant-not-a-real-key",
    )
    anthropic_client = _unauthed_client()
    client.client = anthropic_client

    with pytest.raises(Exception) as excinfo:
        client._call_anthropic("system", "user")
    assert not isinstance(excinfo.value, TypeError), (
        "LLMAPIClient._call_anthropic raises TypeError on anthropic "
        f"{anthropic.__version__}: {excinfo.value}"
    )


def test_composition_visual_call_shape_is_accepted() -> None:
    """`_call_vision_api` passes temperature=0.0 through extra_body too.

    The function does `import anthropic` *inside* its body, so the class in the
    real SDK module is patched rather than a module attribute on
    `composition_visual` — the local import would shadow that anyway.
    """
    import base64
    from unittest.mock import MagicMock, patch

    from dazzle.core import composition_visual

    messages = MagicMock()
    messages.create.side_effect = RuntimeError("stop-after-capture")
    fake_client = MagicMock()
    fake_client.messages = messages

    with (
        patch.object(anthropic, "Anthropic", return_value=fake_client),
        pytest.raises(RuntimeError, match="stop-after-capture"),
    ):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        composition_visual._call_vision_api([(png, "image/png")], "describe", api_key="k")

    kwargs = messages.create.call_args.kwargs
    assert "temperature" not in kwargs, (
        "anthropic 1.x removed the typed `temperature` parameter; it must go through extra_body"
    )
    assert kwargs.get("extra_body") == {"temperature": 0.0}


def test_typed_temperature_is_not_available_so_extra_body_is_required() -> None:
    """Document *why* extra_body is used, and fail loudly if that changes.

    If a future anthropic release restores the typed parameter, this assertion
    fails and prompts moving the value back to a normal keyword — at which point
    extra_body may no longer be needed.
    """
    import inspect

    params = inspect.signature(anthropic.resources.messages.Messages.create).parameters
    assert "temperature" not in params, (
        "anthropic now exposes a typed `temperature` parameter again; move it out "
        "of extra_body and drop the passthrough"
    )
    assert "extra_body" in params, (
        "extra_body is the documented passthrough; without it an unmodelled "
        "parameter cannot be forwarded at all"
    )
