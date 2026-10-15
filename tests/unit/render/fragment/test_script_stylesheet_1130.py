"""#1130: typed ``Script`` and ``Stylesheet`` Fragment primitives.

Custom renderers used to emit client-side JS by stuffing
``<script>`` tags into ``RawHTML`` — bypassing the framework's
attribute-escaping AND any CSP-nonce policy in force. These tests
pin the typed-primitive replacement: safe rendering, mutual-
exclusion validation, CSP nonce injection, and ``</script>``
injection-resistance.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dazzle.render.fragment import (
    FragmentRenderer,
    RenderContext,
    Script,
    Stylesheet,
)


@pytest.mark.parametrize(
    ("ctor", "exc", "match"),
    [
        pytest.param(
            lambda: Script(src="/x.js", body="console.log(1)"),
            ValueError,
            "exactly one of src= or body=",
            id="script.both_src_and_body",
        ),
        pytest.param(
            Script, ValueError, "exactly one of src= or body=", id="script.neither_src_nor_body"
        ),
        pytest.param(
            lambda: Stylesheet(href="/x.css", body="body{}"),
            ValueError,
            "exactly one of href= or body=",
            id="stylesheet.both_href_and_body",
        ),
        pytest.param(
            Stylesheet,
            ValueError,
            "exactly one of href= or body=",
            id="stylesheet.neither_href_nor_body",
        ),
        pytest.param(
            lambda: Script(src=42),  # type: ignore[arg-type]
            TypeError,
            "Script.src expects str",
            id="script.non_str_src",
        ),
    ],
)
def test_rejects_invalid_construction(
    ctor: Callable[[], object], exc: type[Exception], match: str
) -> None:
    with pytest.raises(exc, match=match):
        ctor()


@pytest.mark.parametrize(
    ("fragment", "csp_nonce", "present", "absent"),
    [
        pytest.param(
            Script(src="/static/app.js"),
            None,
            ('type="module"', 'src="/static/app.js"'),
            ("nonce=",),
            id="script.src_emits_type_and_src_no_nonce",
        ),
        pytest.param(
            Script(body="console.log('hello');"),
            None,
            ("console.log('hello');", "<script ", "</script>"),
            ("nonce=",),
            id="script.body_inlined",
        ),
        # Attribute-context injection via src is neutralised by the escaper.
        pytest.param(
            Script(src='/x.js" onerror="alert(1)'),
            None,
            ("&quot;",),
            ('onerror="alert(1)"',),
            id="script.src_attribute_escaped",
        ),
        # `</script>` inside a JS string is escaped to `<\/script>`, which JS
        # parses identically but the HTML tokenizer ignores.
        pytest.param(
            Script(body="var s = '</script>';"),
            None,
            ("<\\/script>",),
            ("</script>'",),
            id="script.inline_close_tag_escaped",
        ),
        pytest.param(
            Script(src="/x.js", defer=True, async_=True),
            None,
            ("defer", "async"),
            (),
            id="script.defer_and_async_flags",
        ),
        pytest.param(
            Script(body="x", nonce="abc123"),
            None,
            ('nonce="abc123"',),
            (),
            id="script.explicit_nonce",
        ),
        # Strict-CSP projects thread the nonce through the render context.
        pytest.param(
            Script(body="x"),
            "from-ctx",
            ('nonce="from-ctx"',),
            (),
            id="script.nonce_inherited_from_context",
        ),
        # A per-primitive override is not steamrollered by the request default.
        pytest.param(
            Script(body="x", nonce="explicit"),
            "from-ctx",
            ('nonce="explicit"',),
            ("from-ctx",),
            id="script.explicit_nonce_wins_over_context",
        ),
        pytest.param(
            Stylesheet(href="/print.css", media="print"),
            None,
            ('media="print"',),
            (),
            id="stylesheet.media_emitted_when_non_default",
        ),
        pytest.param(
            Stylesheet(href="/x.css"),
            None,
            (),
            ("media=",),
            id="stylesheet.media_omitted_when_default_all",
        ),
        # "onerror=" may survive inside the escaped value; what matters is the
        # `"` is escaped so it cannot break out of the attribute context.
        pytest.param(
            Stylesheet(href='/x.css" onerror="alert(1)'),
            None,
            ("&quot;",),
            ('" onerror=',),
            id="stylesheet.href_attribute_escaped",
        ),
        pytest.param(
            Stylesheet(body=".x{content:'</style>'}"),
            None,
            ("<\\/style>",),
            ("</style>'",),
            id="stylesheet.inline_close_tag_escaped",
        ),
    ],
)
def test_renders(
    fragment: Script | Stylesheet,
    csp_nonce: str | None,
    present: tuple[str, ...],
    absent: tuple[str, ...],
) -> None:
    ctx = RenderContext(csp_nonce=csp_nonce) if csp_nonce else None
    out = (
        FragmentRenderer().render(fragment, ctx=ctx) if ctx else FragmentRenderer().render(fragment)
    )
    assert [s for s in present if s not in out] == []
    assert [s for s in absent if s in out] == []


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        pytest.param(
            Script(src="/static/app.js"),
            '<script type="module" src="/static/app.js"></script>',
            id="script.src",
        ),
        pytest.param(
            Stylesheet(href="/static/app.css"),
            '<link rel="stylesheet" href="/static/app.css">',
            id="stylesheet.href_link_tag",
        ),
        pytest.param(
            Stylesheet(body=".x { color: red; }"),
            "<style>.x { color: red; }</style>",
            id="stylesheet.body_style_tag",
        ),
    ],
)
def test_renders_exact_markup(fragment: Script | Stylesheet, expected: str) -> None:
    assert FragmentRenderer().render(fragment) == expected


@pytest.mark.parametrize(
    "fragment",
    [Script(body="x"), Stylesheet(body="x")],
    ids=["script", "stylesheet"],
)
def test_is_frozen(fragment: Script | Stylesheet) -> None:
    with pytest.raises((AttributeError, Exception)):
        fragment.body = "y"  # type: ignore[misc]
