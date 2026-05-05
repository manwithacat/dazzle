from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import (
    CardSafetyError,
    FragmentError,
    HtmxBindingError,
)
from dazzle.render.fragment.tokens import CardTokens, Tokens


def test_render_context_default_tokens() -> None:
    ctx = RenderContext()
    assert isinstance(ctx.tokens, Tokens)


def test_render_context_explicit_tokens() -> None:
    custom = Tokens(card=CardTokens(radius="lg"))
    ctx = RenderContext(tokens=custom)
    assert ctx.tokens.card.radius == "lg"


def test_render_context_html_escape() -> None:
    ctx = RenderContext()
    assert ctx.escape("<script>") == "&lt;script&gt;"
    assert ctx.escape("safe text") == "safe text"


def test_card_safety_error_is_fragment_error() -> None:
    assert issubclass(CardSafetyError, FragmentError)
    assert issubclass(HtmxBindingError, FragmentError)
