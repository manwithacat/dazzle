"""Replay committed fuzz regression seeds (#1342 fuzz-leverage #5).

Each `.dsl` under `fuzz_seeds/` is an input that once crashed the parser (raised a
non-`ParseError`, or a `ParseError` with no location) and was fixed during the
fuzz-leverage track. Replaying them on every run makes each catch a permanent regression:
the input must raise a **well-formed** `ParseError` (located + messaged), never a raw crash.

The nightly `dazzle sentinel fuzz --save-seeds` campaign writes new catches into a build
artifact; an operator/agent promotes worthwhile ones into THIS directory to lock them in."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError

_SEED_DIR = Path(__file__).parent / "fuzz_seeds"
_SEEDS = sorted(_SEED_DIR.glob("*.dsl"))


def test_seed_corpus_is_non_empty() -> None:
    assert _SEEDS, f"no fuzz regression seeds found under {_SEED_DIR}"


@pytest.mark.parametrize("seed", _SEEDS, ids=lambda p: p.name)
def test_seed_raises_well_formed_parse_error(seed: Path) -> None:
    with pytest.raises(ParseError) as ei:
        parse_dsl(seed.read_text(encoding="utf-8"), Path(seed.name))
    err = ei.value
    assert (err.message or "").strip(), f"{seed.name}: ParseError with empty message"
    ctx = getattr(err, "context", None)
    assert ctx is not None and getattr(ctx, "line", 0) >= 1, (
        f"{seed.name}: ParseError lacks a source location (context={ctx})"
    )
