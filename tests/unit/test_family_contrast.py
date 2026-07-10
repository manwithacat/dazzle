"""#1567 slice 2 — the 4 shipped HM aesthetic families must clear WCAG AA on the
canonical text pairs, in both modes. The framework holds its own curated
aesthetics to the same floor validate_themespec enforces on user themespecs.

UI pairs (border/ring vs background at 3:1) are deliberately NOT gated: hairline
borders are the industry norm (every family + shadcn sits ~1.3:1) — a check every
good design system fails is noise, not a gate. Text pairs are the floor.

Calibration 2026-07-10 found 8 genuine sub-AA text pairs across the 4 families
(mostly white-on-destructive button fills at 3.3-4.4:1); all were FIXED by minimal
lightness nudges (hue/sat identity preserved) rather than excused — so
KNOWN_EXCEPTIONS starts, and should stay, empty.
"""

from pathlib import Path

import pytest

from dazzle.core.contrast import FAMILY_PAIRS, check_pairs, parse_family_modes

pytestmark = pytest.mark.gate

_FAMILIES = sorted(
    (Path(__file__).parents[2] / "packages" / "hatchi-maxchi" / "families").glob("*.css")
)

# (family, mode, "fg/bg") triples excused with rationale. Keep tiny and explicit.
KNOWN_EXCEPTIONS: frozenset[tuple[str, str, str]] = frozenset()


def _cases():
    for path in _FAMILIES:
        for mode, tokens in parse_family_modes(path.read_text(encoding="utf-8")).items():
            yield pytest.param(path.name, mode, tokens, id=f"{path.stem}-{mode}")


@pytest.mark.parametrize(("family", "mode", "tokens"), list(_cases()))
def test_family_clears_aa_text_contrast(family, mode, tokens) -> None:
    failures = [
        f
        for f in check_pairs(tokens, FAMILY_PAIRS)
        if (family, mode, f.split(" ")[0]) not in KNOWN_EXCEPTIONS
    ]
    assert failures == [], f"{family} [{mode}]: {failures}"


def test_gate_covers_all_families_both_modes() -> None:
    # 4 families x both modes each; no silent parser failure.
    assert len(_FAMILIES) >= 4
    assert len(list(_cases())) >= 8
