"""Property test: every primitive emits HTML that parses without errors.

Uses html.parser (stdlib) — strict-but-not-comprehensive. Catches obvious
unclosed tags and malformed attributes."""

import typing
from html.parser import HTMLParser

import pytest

from dazzle.render.fragment import Fragment, Slot
from dazzle.render.fragment.renderer import FragmentRenderer
from tests.unit.render.fragment.test_fragment_exhaustiveness import _sample_for


class _Validator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void elements per HTML5 — don't push onto stack
        if tag not in {"input", "br", "hr", "img", "meta", "link"}:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.open_tags:
            self.errors.append(f"unexpected </{tag}> with no open tag")
            return
        if self.open_tags[-1] != tag:
            self.errors.append(f"close mismatch: expected </{self.open_tags[-1]}>, got </{tag}>")
        self.open_tags.pop()

    def error(self, message: str) -> None:  # type: ignore[override]
        self.errors.append(message)


def _all_primitive_types() -> list[type]:
    return list(typing.get_args(Fragment))


@pytest.mark.parametrize("ptype", _all_primitive_types(), ids=lambda t: t.__name__)
def test_primitive_emits_well_formed_html(ptype: type) -> None:
    r = FragmentRenderer()
    sample = _sample_for(ptype)
    if isinstance(sample, Slot):
        pytest.skip("Slot raises at render time by design")

    html = r.render(sample)  # type: ignore[arg-type]

    parser = _Validator()
    parser.feed(html)
    parser.close()

    if parser.open_tags:
        parser.errors.append(f"unclosed tags: {parser.open_tags}")
    assert not parser.errors, (
        f"{ptype.__name__} produced malformed HTML:\nerrors: {parser.errors}\noutput: {html!r}"
    )
