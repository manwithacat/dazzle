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
