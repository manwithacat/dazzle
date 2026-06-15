"""Custom-renderer conformance harness (#1392 slice 2).

Renders every custom-renderer surface in an appspec against a *stub* context
and asserts the framework's output guarantees — non-blank, well-formed, and
inner-HTML-only — so downstream projects stop hand-rolling this check.

Why a shipped helper:

- The non-blank / well-formed guarantee is enforced at **runtime** by
  ``dazzle.render.dispatch._assert_custom_render_output`` (slice 1, on by
  default). But that only fires when a request actually hits the surface — a
  custom surface that's blank only on the empty-data path can ship green and
  reveal the blank 200 in production (the AegisMark "passes render, blank
  screen" failure class).
- This harness is the **test-time oracle**: it exercises every custom surface
  against the empty-data path (``stub_ctx={}``) with no live DB or HTTP server,
  proving the renderer degrades to a visible empty state rather than a blank
  body, and adds the **inner-HTML-only** check (a surface renderer must return a
  fragment, never a full ``<!doctype>``/``<html>`` document — that bypasses the
  app chrome).

Usage::

    from dazzle.testing.custom_renderer_conformance import (
        check_custom_renderer_conformance,
    )

    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    failures = [r for r in results if not r.ok]
    assert not failures, "\\n".join(r.reason or "" for r in failures)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.core.renderer_registry import default_renderer_names
from dazzle.render.dispatch import _assert_custom_render_output
from dazzle.render.fragment.errors import FragmentError

# A surface renderer must emit inner HTML (a fragment); a full document bypasses
# the app shell (sidebar/topbar/chrome). These root markers flag that breach.
_DOCUMENT_ROOT_MARKERS: tuple[str, ...] = ("<!doctype", "<html", "<head", "<body")


@dataclass(frozen=True)
class RendererConformanceResult:
    """One custom surface's conformance verdict.

    ``ok`` is True only when the renderer produced non-blank, well-formed,
    inner-HTML-only output against the stub context. ``reason`` names the
    breach (and remediation) when ``ok`` is False.
    """

    surface: str
    renderer: str
    ok: bool
    reason: str | None = None


def check_custom_renderer_conformance(
    *,
    appspec: Any,
    services: Any,
    stub_ctx: dict[str, Any] | None = None,
) -> list[RendererConformanceResult]:
    """Render every custom-renderer surface in *appspec* with a stub context
    and grade its output against the framework guarantees.

    A surface is "custom" when its ``render`` name is set and is not a framework
    default (``default_renderer_names()`` — today just ``fragment``). For each:

    1. the renderer must be registered on ``services.renderer_registry``;
    2. it must not raise against the stub context (a renderer reads ctx keys
       defensively and degrades, never raising on sparse data);
    3. its output must be non-blank + well-formed (the slice-1 runtime probe);
    4. its output must be inner-HTML-only (no document root element).

    Returns one :class:`RendererConformanceResult` per custom surface (empty
    list when the app declares none). Never raises — every breach becomes a
    structured ``ok=False`` result so the caller can report them together.
    """
    defaults = default_renderer_names()
    stub: dict[str, Any] = {} if stub_ctx is None else stub_ctx
    results: list[RendererConformanceResult] = []

    for surface in getattr(appspec, "surfaces", []) or []:
        renderer_name = getattr(surface, "render", None)
        if not renderer_name or renderer_name in defaults:
            continue
        surface_name = getattr(surface, "name", "<unknown>")

        handler = services.renderer_registry.resolve(renderer_name)
        if handler is None:
            registered = sorted(services.renderer_registry.registered_names())
            results.append(
                RendererConformanceResult(
                    surface=surface_name,
                    renderer=renderer_name,
                    ok=False,
                    reason=(
                        f"surface {surface_name!r}: renderer {renderer_name!r} is declared "
                        f"but no runtime handler is registered (registered: {registered}). "
                        "Register it in your app factory / startup hook."
                    ),
                )
            )
            continue

        try:
            rendered = handler.render(surface, stub)
        except Exception as exc:  # noqa: BLE001 — any raise on stub ctx is a conformance breach
            results.append(
                RendererConformanceResult(
                    surface=surface_name,
                    renderer=renderer_name,
                    ok=False,
                    reason=(
                        f"surface {surface_name!r}: custom renderer {renderer_name!r} raised "
                        f"on a stub context ({type(exc).__name__}: {exc}). A renderer must read "
                        "ctx keys defensively and degrade to a visible empty state, never raise."
                    ),
                )
            )
            continue

        try:
            html = _assert_custom_render_output(rendered, surface_name, renderer_name)
        except FragmentError as exc:
            results.append(
                RendererConformanceResult(
                    surface=surface_name, renderer=renderer_name, ok=False, reason=str(exc)
                )
            )
            continue

        lowered = html.lower()
        doc_marker = next((m for m in _DOCUMENT_ROOT_MARKERS if m in lowered), None)
        if doc_marker is not None:
            results.append(
                RendererConformanceResult(
                    surface=surface_name,
                    renderer=renderer_name,
                    ok=False,
                    reason=(
                        f"surface {surface_name!r}: custom renderer {renderer_name!r} returned a "
                        f"full document (found {doc_marker!r}). A surface renderer must return "
                        "inner HTML only — the framework wraps it in the app chrome; a full "
                        "document bypasses the sidebar/topbar shell."
                    ),
                )
            )
            continue

        results.append(
            RendererConformanceResult(surface=surface_name, renderer=renderer_name, ok=True)
        )

    return results
