"""#1493 (UX-maturity 1b) — `semantic:` tone bindings on shared enums.

Slice 1: the declarative + validated core. A shared `enum` block may carry a
`semantic: value=tone, ...` line binding each value's lifecycle role to a tone
from the canonical palette (`positive` aliases `success`). Declared tones are
validated against the palette; value membership is enforced at parse time.
(Inline `enum[...]` field bindings + the render/icon consumption land in slice 2.)
"""

import pathlib
import tempfile

import pytest

from dazzle.core.errors import DazzleError
from dazzle.core.ir import ModuleIR
from dazzle.core.ir.tones import CANONICAL_TONES, normalize_tone
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_dsl


def _parse(dsl: str):
    p = pathlib.Path(tempfile.mktemp(suffix=".dsl"))
    p.write_text(dsl)
    _, _, _, _, _, frag = parse_dsl(dsl, p)
    return frag


def _enum(frag, name: str):
    return next(e for e in frag.enums if e.name == name)


# ── tone normalisation / palette ──────────────────────────────────────────


def test_canonical_palette_is_the_five_css_tones() -> None:
    assert set(CANONICAL_TONES) == {"success", "info", "warning", "destructive", "neutral"}


def test_positive_aliases_success() -> None:
    assert normalize_tone("positive") == "success"


def test_normalize_is_case_insensitive() -> None:
    assert normalize_tone("WARNING") == "warning"


def test_unknown_tone_normalises_to_none() -> None:
    assert normalize_tone("turquoise") is None


# ── parser: shared enum `semantic:` line ──────────────────────────────────


def test_semantic_line_binds_values() -> None:
    frag = _parse(
        """module m
app a "A"
enum OrderStatus "Order Status":
  draft "Draft"
  pending "Pending"
  approved "Approved"
  rejected "Rejected"
  semantic: pending=warning, approved=positive, rejected=destructive, draft=neutral
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "OrderStatus").values}
    assert by_name == {
        "draft": "neutral",
        "pending": "warning",
        "approved": "positive",  # raw; normalises to success downstream
        "rejected": "destructive",
    }


def test_undeclared_values_keep_none_semantic() -> None:
    frag = _parse(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  semantic: a=success
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "S").values}
    assert by_name == {"a": "success", "b": None}


def test_semantic_line_may_precede_values() -> None:
    frag = _parse(
        """module m
app a "A"
enum S "S":
  semantic: a=success, b=destructive
  a "A"
  b "B"
"""
    )
    by_name = {v.name: v.semantic for v in _enum(frag, "S").values}
    assert by_name == {"a": "success", "b": "destructive"}


def test_semantic_binding_unknown_value_is_parse_error() -> None:
    with pytest.raises(DazzleError) as exc:
        _parse(
            """module m
app a "A"
enum S "S":
  draft "Draft"
  semantic: nonexistent=warning
"""
        )
    assert "E_SEMANTIC_VALUE_UNKNOWN" in str(exc.value)


# ── validator: tone palette ───────────────────────────────────────────────


def _appspec(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, pathlib.Path("t.dsl"))
    root = n or "t"
    return build_appspec(
        [
            ModuleIR(
                name=root,
                file=pathlib.Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        root,
    )


def test_validator_accepts_canonical_and_alias_tones() -> None:
    from dazzle.core.validation.ux import validate_enum_semantics

    appspec = _appspec(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  c "C"
  semantic: a=success, b=positive, c=neutral
"""
    )
    errors, _ = validate_enum_semantics(appspec)
    assert errors == []


def test_validator_rejects_unknown_tone() -> None:
    from dazzle.core.validation.ux import validate_enum_semantics

    appspec = _appspec(
        """module m
app a "A"
enum S "S":
  a "A"
  b "B"
  semantic: a=success, b=turquoise
"""
    )
    errors, _ = validate_enum_semantics(appspec)
    assert any("E_SEMANTIC_TONE_UNKNOWN" in e and "turquoise" in e for e in errors)
