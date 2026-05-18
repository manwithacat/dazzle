"""Escape-hatch primitives — the explicit way out of the typed system.

`RawHTML` accepts an arbitrary HTML string and emits it verbatim. Used for
Jinja interop (Plan 3) and for the rare "this is too custom to model" case.
A lint count of `RawHTML(...)` occurrences per surface tracks migration
progress; downstream apps that have not migrated will have many, fully-
migrated example apps will have zero.

`Slot` names a hole in a Fragment tree that is filled later. Used by the
renderer for delayed/streamed content. Not a free-form escape — the slot
name must match the substitution map at render time.

`Script` and `Stylesheet` (#1130) are typed asset primitives for custom
renderers that need to ship client-side JS or CSS. They emit safely-
escaped ``<script>`` / ``<style>`` / ``<link>`` tags and integrate with
the renderer's optional CSP-nonce machinery — replacing the
``RawHTML("<script>…</script>")`` pattern that bypassed escaping AND
nonce injection on every page render.
"""

import html as _html_module
import re
from dataclasses import dataclass
from typing import Literal

CrossOrigin = Literal["anonymous", "use-credentials"]

_VALID_SLOT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class RawHTML:
    """Verbatim HTML emission. The audit-visible escape hatch.

    WARNING: bypasses HTML escaping. The caller is responsible for ensuring
    `html` is safe to inject — never construct from untrusted input (user-
    supplied strings, request data, DB content rendered as HTML). Prefer
    typed Fragment primitives; reserve RawHTML for trusted pre-rendered
    output (Jinja interop, static assets).

    Occurrences are lint-counted per surface as a migration-progress metric;
    fully Fragment-native surfaces have zero RawHTML uses.
    """

    html: str

    def __post_init__(self) -> None:
        if not isinstance(self.html, str):
            raise TypeError(f"RawHTML expects str, got {type(self.html).__name__}")


@dataclass(frozen=True, slots=True)
class Slot:
    """A named hole filled at render time."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f"Slot expects str name, got {type(self.name).__name__}")
        if not _VALID_SLOT_NAME.match(self.name):
            raise ValueError(f"invalid slot name {self.name!r}")


@dataclass(frozen=True, slots=True)
class Script:
    """Typed ``<script>`` primitive for custom renderers (#1130).

    Exactly one of ``src`` (external URL) or ``body`` (inline JS) must
    be set — ``__post_init__`` enforces this. The renderer's emit pass
    HTML-escapes ``src`` attribute values and the inline body so a
    renderer can build ``Script(body=user_supplied_data)`` without
    self-XSS — but the **caller still owns the trust boundary**: if
    ``body`` is genuinely user-controllable JS source, no amount of
    escaping makes that safe. The primitive's job is preventing
    accidental injection via attribute interpolation, not auditing
    intent.

    The ``nonce`` field, when set, auto-injects a CSP nonce attribute
    on the rendered tag. ``None`` leaves the attribute off — projects
    on a strict CSP can set it from their auth/CSP middleware before
    handing the Fragment tree to the renderer.

    Attributes:
        src: External JS URL. Mutually exclusive with ``body``.
        body: Inline JS source. Mutually exclusive with ``src``.
        type: Script MIME / module marker. Defaults to ``"module"``.
        defer: Emit the ``defer`` attribute.
        async_: Emit the ``async`` attribute. Named with trailing
            underscore to avoid the Python keyword collision.
        nonce: Optional CSP nonce; rendered as ``nonce="..."`` when set.
        integrity: Subresource integrity hash (e.g. ``"sha384-..."``).
            Only valid with ``src=`` — SRI on inline scripts is
            meaningless. The primitive passes the string through
            verbatim; the caller owns hash format validation.
        crossorigin: CORS mode for external scripts. Only valid with
            ``src=``. Must be ``"anonymous"`` or ``"use-credentials"``
            when set.
    """

    src: str | None = None
    body: str | None = None
    type: str = "module"
    defer: bool = False
    async_: bool = False
    nonce: str | None = None
    integrity: str | None = None
    crossorigin: CrossOrigin | None = None

    def __post_init__(self) -> None:
        has_src = self.src is not None
        has_body = self.body is not None
        if has_src == has_body:
            raise ValueError(
                "Script requires exactly one of src= or body=; "
                f"got src={self.src!r}, body={'<...>' if has_body else None}"
            )
        if self.src is not None and not isinstance(self.src, str):
            raise TypeError(f"Script.src expects str, got {type(self.src).__name__}")
        if self.body is not None and not isinstance(self.body, str):
            raise TypeError(f"Script.body expects str, got {type(self.body).__name__}")
        # #1136: integrity + crossorigin only meaningful on external
        # scripts. Reject early so a renderer can't silently drop a
        # SRI hash by attaching it to an inline <script>.
        if has_body and self.integrity is not None:
            raise ValueError("Script.integrity is only valid with src= (not inline body=)")
        if has_body and self.crossorigin is not None:
            raise ValueError("Script.crossorigin is only valid with src= (not inline body=)")
        if self.integrity is not None and not isinstance(self.integrity, str):
            raise TypeError(f"Script.integrity expects str, got {type(self.integrity).__name__}")
        if self.crossorigin is not None and self.crossorigin not in (
            "anonymous",
            "use-credentials",
        ):
            raise ValueError(
                f"Script.crossorigin must be 'anonymous' or 'use-credentials'; "
                f"got {self.crossorigin!r}"
            )


@dataclass(frozen=True, slots=True)
class Stylesheet:
    """Typed ``<link rel="stylesheet">`` / ``<style>`` primitive (#1130).

    Exactly one of ``href`` (external) or ``body`` (inline CSS) must be
    set. External hrefs emit ``<link rel="stylesheet" href="...">``;
    inline bodies emit a ``<style>...</style>`` block. The optional
    ``media`` query is rendered as the ``media`` attribute when not
    the default ``"all"``.

    Attributes:
        href: External stylesheet URL. Mutually exclusive with ``body``.
        body: Inline CSS source. Mutually exclusive with ``href``.
        media: Media query. Default ``"all"``.
    """

    href: str | None = None
    body: str | None = None
    media: str = "all"

    def __post_init__(self) -> None:
        has_href = self.href is not None
        has_body = self.body is not None
        if has_href == has_body:
            raise ValueError(
                "Stylesheet requires exactly one of href= or body=; "
                f"got href={self.href!r}, body={'<...>' if has_body else None}"
            )
        if self.href is not None and not isinstance(self.href, str):
            raise TypeError(f"Stylesheet.href expects str, got {type(self.href).__name__}")
        if self.body is not None and not isinstance(self.body, str):
            raise TypeError(f"Stylesheet.body expects str, got {type(self.body).__name__}")


def _attr_escape(value: str) -> str:
    """HTML-escape a string for use inside a double-quoted attribute."""
    return _html_module.escape(value, quote=True)


def _close_script_tag_safe(body: str) -> str:
    """Protect against ``</script>`` injection in inline JS bodies.

    The HTML spec terminates the ``<script>`` element at the first
    ``</script>`` sequence — even inside a string literal in the JS.
    Replace with the backslash-escaped form that JS parses identically
    but the HTML tokenizer doesn't see as a close tag.
    """
    return body.replace("</script>", "<\\/script>")
