import pytest

from dazzle.render.fragment.tokens import (
    ButtonTokens,
    CardTokens,
    Palette,
    Spacing,
    TableTokens,
    Tokens,
)


def test_card_tokens_defaults() -> None:
    t = CardTokens()
    assert t.radius == "md"
    assert t.border == "subtle"
    assert t.padding == "normal"
    assert t.shadow == "none"


def test_card_tokens_invalid_radius() -> None:
    # Frozen dataclass with Literal types — mypy catches this at static time;
    # the runtime check in __post_init__ is the runtime safety net.
    with pytest.raises(ValueError, match="invalid radius"):
        CardTokens(radius="enormous")  # type: ignore[arg-type]


def test_button_tokens_defaults() -> None:
    t = ButtonTokens()
    assert t.variant == "secondary"
    assert t.size == "md"


def test_root_tokens_composes() -> None:
    t = Tokens()
    assert isinstance(t.card, CardTokens)
    assert isinstance(t.button, ButtonTokens)
    assert isinstance(t.table, TableTokens)
    assert isinstance(t.palette, Palette)
    assert isinstance(t.spacing, Spacing)


def test_tokens_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    t = Tokens()
    with pytest.raises(FrozenInstanceError):
        t.card = CardTokens(radius="lg")  # type: ignore[misc]
