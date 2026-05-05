from dataclasses import dataclass

from dazzle.render.classes import classes_for


@dataclass(frozen=True)
class _Tokens:
    radius: str = "md"
    border: str = "subtle"


@dataclass(frozen=True)
class _CardLikeNode:
    kind: str = "card"


def test_classes_for_card_default_tokens() -> None:
    node = _CardLikeNode()
    tokens = _Tokens()
    classes = classes_for(node, tokens)
    assert "dz-card" in classes
    assert "dz-card--radius-md" in classes
    assert "dz-card--border-subtle" in classes


def test_classes_for_card_with_radius_override() -> None:
    node = _CardLikeNode()
    tokens = _Tokens(radius="lg")
    classes = classes_for(node, tokens)
    assert "dz-card--radius-lg" in classes
    assert "dz-card--radius-md" not in classes


def test_classes_for_returns_sorted_unique() -> None:
    node = _CardLikeNode()
    tokens = _Tokens()
    classes = classes_for(node, tokens)
    assert classes == sorted(set(classes))


def test_classes_for_unknown_kind_returns_base_only() -> None:
    """A kind not in _KIND_TOKENS gets only the base class — safe default."""

    @dataclass(frozen=True)
    class _UnknownKindNode:
        kind: str = "moonbeam"

    classes = classes_for(_UnknownKindNode(), _Tokens(radius="lg"))
    assert classes == ["dz-moonbeam"]


def test_classes_for_button_with_variant_and_size() -> None:
    @dataclass(frozen=True)
    class _ButtonLikeNode:
        kind: str = "button"

    @dataclass(frozen=True)
    class _ButtonTokens:
        variant: str = "primary"
        size: str = "lg"

    classes = classes_for(_ButtonLikeNode(), _ButtonTokens())
    assert "dz-button" in classes
    assert "dz-button--variant-primary" in classes
    assert "dz-button--size-lg" in classes
