"""#1567 slice 2 — validate_themespec hard-fails sub-AA generated palettes.

The deterministic floor of the new-property authoring path: a themespec whose
generated palette renders illegible text is not "done". Text pairs are errors;
the border-strong UI pair is a warning (hairline borders are the industry norm —
the scaffold defaults themselves sit ~2.6:1, so 3:1 as an error would block every
reasonable theme).
"""

import pytest

from dazzle.core.ir.themespec import ThemeSpecYAML
from dazzle.core.themespec_loader import validate_themespec

pytestmark = pytest.mark.gate


def test_default_themespec_passes_contrast() -> None:
    result = validate_themespec(ThemeSpecYAML())
    contrast_errors = [e for e in result.errors if "contrast" in e]
    assert contrast_errors == [], contrast_errors


def test_low_contrast_palette_fails_with_pair_named_errors(monkeypatch) -> None:
    import dazzle.core.themespec_loader as loader

    def bad_palette(*args, **kwargs):
        return {
            "text-primary": "oklch(0.700 0.0000 0.0)",
            "bg-primary": "oklch(0.990 0.0000 0.0)",
        }

    monkeypatch.setattr(loader, "generate_palette", bad_palette)
    result = validate_themespec(ThemeSpecYAML())
    joined = "\n".join(result.errors)
    assert "contrast" in joined and "text-primary/bg-primary" in joined
    assert "(light)" in joined and "(dark)" in joined


def test_border_strong_is_a_warning_not_error() -> None:
    result = validate_themespec(ThemeSpecYAML())
    # The scaffold defaults sit ~2.6:1 on border-strong/bg-primary — surfaced as
    # a warning, never an error (see module docstring).
    assert not any("border-strong" in e for e in result.errors)
    assert any("border-strong" in w for w in result.warnings)
