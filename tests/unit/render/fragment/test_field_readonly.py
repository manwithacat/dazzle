"""Field.readonly — emitted as the readonly HTML attribute (Plan 15)."""

from dazzle.render.fragment import Field
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def test_field_readonly_default_false() -> None:
    f = Field(name="x", label="X")
    assert f.readonly is False
    assert "readonly" not in _render(f)


def test_field_readonly_true_emits_attr() -> None:
    f = Field(name="x", label="X", readonly=True)
    assert f.readonly is True
    assert "readonly" in _render(f)


def test_textarea_field_readonly_emits_attr() -> None:
    f = Field(name="x", label="X", kind="textarea", readonly=True)
    html = _render(f)
    assert "<textarea" in html
    assert "readonly" in html
