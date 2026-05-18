"""#1136: ``Script`` primitive gains ``integrity`` + ``crossorigin``
for SRI-pinned external CDN scripts.

Pre-fix, renderers had to drop to ``RawHTML`` to attach SRI hashes,
defeating the typed primitive's escaping and lint-counting value.
These tests pin: round-trip emission, attribute escaping, and the
inline-body rejection (SRI on inline scripts is meaningless).
"""

from __future__ import annotations

import pytest

from dazzle.render.fragment import FragmentRenderer, RenderContext, Script


def _render(script: Script) -> str:
    return FragmentRenderer().render(script, RenderContext())


def test_script_emits_integrity_and_crossorigin() -> None:
    out = _render(
        Script(
            src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js",
            integrity="sha384-abc123",
            crossorigin="anonymous",
            defer=True,
        )
    )
    assert 'integrity="sha384-abc123"' in out
    assert 'crossorigin="anonymous"' in out
    assert 'src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"' in out
    assert "defer" in out


def test_script_omits_integrity_when_unset() -> None:
    out = _render(Script(src="/static/x.js"))
    assert "integrity" not in out
    assert "crossorigin" not in out


def test_script_integrity_attribute_value_is_html_escaped() -> None:
    """Integrity strings are caller-controlled but still flow through
    a quoted attribute; double-quotes / ampersands must escape so a
    pathological hash can't break out of the attribute."""
    out = _render(Script(src="/x.js", integrity='sha384-"><script>x'))
    assert '"><script>' not in out
    assert "&quot;&gt;" in out


def test_script_crossorigin_use_credentials() -> None:
    out = _render(Script(src="/x.js", crossorigin="use-credentials"))
    assert 'crossorigin="use-credentials"' in out


def test_script_rejects_integrity_on_inline_body() -> None:
    with pytest.raises(ValueError, match="integrity is only valid with src="):
        Script(body="console.log(1)", integrity="sha384-abc")


def test_script_rejects_crossorigin_on_inline_body() -> None:
    with pytest.raises(ValueError, match="crossorigin is only valid with src="):
        Script(body="console.log(1)", crossorigin="anonymous")


def test_script_rejects_invalid_crossorigin_value() -> None:
    with pytest.raises(ValueError, match="must be 'anonymous' or 'use-credentials'"):
        Script(src="/x.js", crossorigin="invalid")  # type: ignore[arg-type]


def test_script_rejects_non_str_integrity() -> None:
    with pytest.raises(TypeError, match="Script.integrity expects str"):
        Script(src="/x.js", integrity=42)  # type: ignore[arg-type]
