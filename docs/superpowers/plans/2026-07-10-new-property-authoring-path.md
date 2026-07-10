# New-Property Authoring Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close #1567 by delivering the new-property authoring path: WCAG contrast math in `core/contrast.py`, a hard contrast gate inside `validate_themespec`, a live gate on the 4 shipped HM families, an advisory `dazzle qa property-vision` command, and the unified "Standing up a new property" doc section.

**Architecture:** One pure colour-math module (`core/contrast.py`) serves two consumers with two vocabularies: the parametric ThemeSpec palette (`text-primary`/`bg-primary`/…, `oklch()` strings from `core/oklch.generate_palette`) gets pair-checked inside `validate_themespec` as hard errors; the HM family CSS (`foreground`/`background`/…, HSL triplets) gets a `pytest.mark.gate` test. The advisory vision command reuses `taste_panel.score_image` with a new optional `dimensions` parameter so it can judge against `SITESPEC_VISION_DIMENSIONS` + the per-family exemplars.

**Tech Stack:** Python 3.12+, pure-Python OKLCH→sRGB + HSL→sRGB conversion (no new deps), pytest (`-m gate`), Typer CLI, Playwright (on-demand only), existing `taste_panel` + exemplar manifest.

## Global Constraints

- **Contrast failures are hard errors** in `validate_theme` (approved decision) — text pairs at **4.5:1**. UI pairs (border/ring) at **3:1** are **calibration-decided** (slice-1 stance): error if the 4 shipped families + the scaffold defaults genuinely pass; else warnings with a documented rationale (subtle hairline borders are an industry norm — an error that every good design system fails is noise, not a gate).
- **If the scaffold's own defaults fail a text pair, fix the generator defaults** — never soften the gate.
- **Absent pairs are skipped** (absence is not a violation — slice-1 n/a stance).
- New gate tests carry `pytestmark = pytest.mark.gate`, fast + DB-free.
- Advisory vision: exit 0 on successful score; usage errors (unknown family / missing exemplars) exit non-zero.
- Clean break (ADR-0003); no new MCP tools; APCA out of scope (WCAG 2 AA only).
- Watch the deferred-imports ratchet for new CLI-defer imports in `cli/qa.py` (bump `tests/unit/fixtures/deferred_imports_baseline.json` with justification if tripped, as slice 1 did 23→26).
- Doc regen is eof-stable (`render_markdown().rstrip("\n") + "\n"` already handled by `scripts/gen_design_context.py`).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/core/contrast.py` | **New.** WCAG maths: HSL-triplet + oklch() + hex parsing → sRGB, luminance, ratio; `ContrastPair` tables (`FAMILY_PAIRS`, `THEMESPEC_PAIRS`); `check_pairs`; HM family CSS block parser. |
| `src/dazzle/core/themespec_loader.py` | **Modify.** `validate_themespec` gains the palette contrast check (both modes, errors). |
| `tests/unit/test_contrast.py` | **New.** Maths + parsing + skip-on-absent (gate). |
| `tests/unit/test_themespec_contrast.py` | **New.** Good spec passes; low-contrast spec fails with pair-named errors (gate). |
| `tests/unit/test_family_contrast.py` | **New.** The 4 shipped families clear AA (gate). |
| `src/dazzle/qa/taste_panel.py` | **Modify.** `score_image` gains optional `dimensions` param (default = current behaviour). |
| `src/dazzle/qa/property_vision.py` | **New.** Render-URL→screenshot→score glue (injectable heavy parts). |
| `src/dazzle/cli/qa.py` | **Modify.** `qa property-vision` subcommand after `component-vision`. |
| `tests/unit/test_property_vision.py` | **New.** Mocked glue + missing-exemplars usage error (gate). |
| `src/dazzle/core/design_context.py` | **Modify.** "Standing up a new property" section in `render_markdown()`. |
| `docs/reference/hm-design-context.md` | **Regenerate.** |

Vocabulary lock (tasks must agree):

- **Family pairs** (HM `families/*.css`, HSL triplets like `"220 30% 15%"`), text 4.5:1:
  `foreground/background`, `card-foreground/card`, `popover-foreground/popover`,
  `primary-foreground/primary`, `secondary-foreground/secondary`,
  `muted-foreground/background`, `destructive-foreground/destructive`,
  `accent-foreground/accent`. UI 3:1 (calibration-decided): `border/background`, `ring/background`.
- **Themespec pairs** (`core/oklch.generate_palette` output, `oklch()` strings), text 4.5:1:
  `text-primary/bg-primary`, `text-primary/bg-secondary`, `text-secondary/bg-primary`,
  and semantic `{success,warning,danger,info}-text/{…}-bg`. UI 3:1 (calibration-decided):
  `border-strong/bg-primary`.

---

## Task 1: `core/contrast.py` — WCAG colour math + pair tables

**Files:**
- Create: `src/dazzle/core/contrast.py`
- Create: `tests/unit/test_contrast.py`

**Interfaces (produces):**
- `parse_css_color(value: str) -> tuple[float, float, float] | None` — sRGB in 0..1 from an HSL triplet (`"220 30% 15%"`), `oklch(L C H)`/`oklch(L C H / a)`, `hsl(...)`, or `#hex`; `None` if unparseable (e.g. `var(...)`, gradients).
- `relative_luminance(rgb: tuple[float, float, float]) -> float` (WCAG 2.x).
- `contrast_ratio(a: tuple, b: tuple) -> float` (≥1.0).
- `ContrastPair(fg: str, bg: str, minimum: float, kind: str)` — frozen dataclass; `kind` is `"text" | "ui"`.
- `FAMILY_PAIRS: tuple[ContrastPair, ...]`, `THEMESPEC_PAIRS: tuple[ContrastPair, ...]` (the vocabulary lock above).
- `check_pairs(tokens: dict[str, str], pairs: tuple[ContrastPair, ...]) -> list[str]` — failure strings `"foreground/background 3.82:1 < 4.5:1"`; pairs with either token absent or unparseable are skipped.
- `parse_family_modes(css: str) -> dict[str, dict[str, str]]` — `{"light": {token: value}, "dark": {...}}` from a family CSS file (brace-matched `[data-theme="light"|"dark"]` blocks; a mode absent from the file is absent from the dict).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_contrast.py`:

```python
"""#1567 slice 2 — WCAG contrast math + pair-table behaviour."""

import pytest

from dazzle.core.contrast import (
    FAMILY_PAIRS,
    THEMESPEC_PAIRS,
    check_pairs,
    contrast_ratio,
    parse_css_color,
    parse_family_modes,
    relative_luminance,
)

pytestmark = pytest.mark.gate


def test_parse_hsl_triplet() -> None:
    assert parse_css_color("0 0% 100%") == (1.0, 1.0, 1.0)
    r, g, b = parse_css_color("0 0% 0%")
    assert (r, g, b) == (0.0, 0.0, 0.0)


def test_parse_oklch_white_black() -> None:
    r, g, b = parse_css_color("oklch(1.000 0.0000 0.0)")
    assert all(abs(c - 1.0) < 0.01 for c in (r, g, b))
    r, g, b = parse_css_color("oklch(0.000 0.0000 0.0)")
    assert all(abs(c) < 0.01 for c in (r, g, b))


def test_parse_hex() -> None:
    assert parse_css_color("#ffffff") == (1.0, 1.0, 1.0)
    assert parse_css_color("#000") == (0.0, 0.0, 0.0)


def test_parse_unparseable_returns_none() -> None:
    assert parse_css_color("var(--dz-ink)") is None
    assert parse_css_color("linear-gradient(90deg, #fff, #000)") is None


def test_wcag_reference_ratios() -> None:
    # Canonical WCAG anchors: white/black = 21:1; a colour with itself = 1:1.
    white, black = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    assert abs(contrast_ratio(white, black) - 21.0) < 0.01
    assert contrast_ratio(white, white) == 1.0
    # Symmetry.
    grey = parse_css_color("0 0% 46%")
    assert contrast_ratio(white, grey) == contrast_ratio(grey, white)
    # #767676 on white is the classic ~4.54:1 AA-passing grey.
    aa_grey = parse_css_color("#767676")
    assert 4.4 < contrast_ratio(aa_grey, white) < 4.7


def test_relative_luminance_anchors() -> None:
    assert abs(relative_luminance((1.0, 1.0, 1.0)) - 1.0) < 1e-9
    assert abs(relative_luminance((0.0, 0.0, 0.0))) < 1e-9


def test_check_pairs_flags_low_contrast() -> None:
    tokens = {"foreground": "0 0% 60%", "background": "0 0% 100%"}  # ~2.6:1
    failures = check_pairs(tokens, FAMILY_PAIRS)
    assert any(f.startswith("foreground/background") for f in failures)


def test_check_pairs_skips_absent_and_unparseable() -> None:
    # Only background present -> every pair skipped -> no failures.
    assert check_pairs({"background": "0 0% 100%"}, FAMILY_PAIRS) == []
    # Unparseable value -> skipped, not a failure.
    tokens = {"foreground": "var(--x)", "background": "0 0% 100%"}
    assert check_pairs(tokens, FAMILY_PAIRS) == []


def test_pair_tables_shape() -> None:
    assert all(p.minimum in (4.5, 3.0) for p in FAMILY_PAIRS + THEMESPEC_PAIRS)
    assert any(p.fg == "text-primary" for p in THEMESPEC_PAIRS)


def test_parse_family_modes_real_file() -> None:
    from pathlib import Path

    css = (
        Path(__file__).parents[2] / "packages" / "hatchi-maxchi" / "families" / "stripe.css"
    ).read_text(encoding="utf-8")
    modes = parse_family_modes(css)
    assert set(modes) == {"light", "dark"}
    assert "background" in modes["light"] and "foreground" in modes["light"]
    assert modes["light"]["background"] != modes["dark"]["background"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_contrast.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.contrast'`.

- [ ] **Step 3: Implement `core/contrast.py`**

```python
"""WCAG 2.x contrast math for Dazzle's theme systems (#1567 slice 2).

One pure module, two consumers/vocabularies:
- HM aesthetic families (``packages/hatchi-maxchi/families/*.css``, HSL triplets
  like ``"220 30% 15%"``) — gated by ``tests/unit/test_family_contrast.py``.
- The parametric ThemeSpec palette (``core.oklch.generate_palette`` output,
  ``oklch()`` strings) — gated inside ``validate_themespec``.

Pairs a token map doesn't define (or values that aren't plain colours) are
SKIPPED — absence is not a violation, mirroring the slice-1 n/a stance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "FAMILY_PAIRS",
    "THEMESPEC_PAIRS",
    "ContrastPair",
    "check_pairs",
    "contrast_ratio",
    "parse_css_color",
    "parse_family_modes",
    "relative_luminance",
]

RGB = tuple[float, float, float]

# --- colour parsing --------------------------------------------------------

_HSL_TRIPLET_RE = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$")
_HSL_FUNC_RE = re.compile(r"^\s*hsla?\(\s*([\d.]+)[,\s]+([\d.]+)%[,\s]+([\d.]+)%")
_OKLCH_RE = re.compile(r"^\s*oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)")
_HEX_RE = re.compile(r"^\s*#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\s*$")


def _hsl_to_rgb(h: float, s: float, lightness: float) -> RGB:
    s /= 100.0
    lightness /= 100.0
    c = (1 - abs(2 * lightness - 1)) * s
    hp = (h % 360.0) / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    r, g, b = (
        (c, x, 0.0) if hp < 1 else (x, c, 0.0) if hp < 2 else (0.0, c, x)
        if hp < 3 else (0.0, x, c) if hp < 4 else (x, 0.0, c) if hp < 5 else (c, 0.0, x)
    )
    m = lightness - c / 2
    return (r + m, g + m, b + m)


def _oklch_to_rgb(L: float, C: float, H: float) -> RGB:
    """OKLCH -> OKLab -> LMS -> linear sRGB -> sRGB (clamped)."""
    h_rad = math.radians(H)
    a, b = C * math.cos(h_rad), C * math.sin(h_rad)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_**3, m_**3, s_**3
    lin = (
        +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
        -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
        -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3,
    )

    def to_srgb(u: float) -> float:
        u = min(1.0, max(0.0, u))
        return 12.92 * u if u <= 0.0031308 else 1.055 * u ** (1 / 2.4) - 0.055

    return (to_srgb(lin[0]), to_srgb(lin[1]), to_srgb(lin[2]))


def parse_css_color(value: str) -> RGB | None:
    """Parse a plain colour value to sRGB (0..1); None for non-colours."""
    m = _HEX_RE.match(value)
    if m:
        hx = m.group(1)
        if len(hx) == 3:
            hx = "".join(ch * 2 for ch in hx)
        return tuple(int(hx[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    m = _OKLCH_RE.match(value)
    if m:
        return _oklch_to_rgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = _HSL_FUNC_RE.match(value) or _HSL_TRIPLET_RE.match(value)
    if m:
        return _hsl_to_rgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


# --- WCAG maths -------------------------------------------------------------


def relative_luminance(rgb: RGB) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# --- pair tables -------------------------------------------------------------


@dataclass(frozen=True)
class ContrastPair:
    """One fg/bg token pair with its WCAG minimum."""

    fg: str
    bg: str
    minimum: float  # 4.5 text, 3.0 UI
    kind: str  # "text" | "ui"


FAMILY_PAIRS: tuple[ContrastPair, ...] = (
    ContrastPair("foreground", "background", 4.5, "text"),
    ContrastPair("card-foreground", "card", 4.5, "text"),
    ContrastPair("popover-foreground", "popover", 4.5, "text"),
    ContrastPair("primary-foreground", "primary", 4.5, "text"),
    ContrastPair("secondary-foreground", "secondary", 4.5, "text"),
    ContrastPair("muted-foreground", "background", 4.5, "text"),
    ContrastPair("destructive-foreground", "destructive", 4.5, "text"),
    ContrastPair("accent-foreground", "accent", 4.5, "text"),
)

THEMESPEC_PAIRS: tuple[ContrastPair, ...] = (
    ContrastPair("text-primary", "bg-primary", 4.5, "text"),
    ContrastPair("text-primary", "bg-secondary", 4.5, "text"),
    ContrastPair("text-secondary", "bg-primary", 4.5, "text"),
    ContrastPair("success-text", "success-bg", 4.5, "text"),
    ContrastPair("warning-text", "warning-bg", 4.5, "text"),
    ContrastPair("danger-text", "danger-bg", 4.5, "text"),
    ContrastPair("info-text", "info-bg", 4.5, "text"),
)


def check_pairs(tokens: dict[str, str], pairs: tuple[ContrastPair, ...]) -> list[str]:
    """Return failure strings for pairs below their minimum; skip absent/unparseable."""
    failures: list[str] = []
    for p in pairs:
        fg_v, bg_v = tokens.get(p.fg), tokens.get(p.bg)
        if fg_v is None or bg_v is None:
            continue
        fg, bg = parse_css_color(fg_v), parse_css_color(bg_v)
        if fg is None or bg is None:
            continue
        ratio = contrast_ratio(fg, bg)
        if ratio < p.minimum:
            failures.append(f"{p.fg}/{p.bg} {ratio:.2f}:1 < {p.minimum}:1")
    return failures


# --- HM family CSS parsing ----------------------------------------------------

_TOKEN_DECL_RE = re.compile(r"--([a-z][\w-]*)\s*:\s*([^;]+);")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def parse_family_modes(css: str) -> dict[str, dict[str, str]]:
    """Extract {mode: {token: value}} from a family CSS file's
    ``[data-theme="light"|"dark"]`` blocks (brace-matched)."""
    css = _COMMENT_RE.sub("", css)
    modes: dict[str, dict[str, str]] = {}
    for mode in ("light", "dark"):
        marker = f'[data-theme="{mode}"]'
        idx = css.find(marker)
        if idx == -1:
            continue
        open_idx = css.index("{", idx)
        depth, end = 1, open_idx + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        body = css[open_idx + 1 : end - 1]
        modes[mode] = {m.group(1): m.group(2).strip() for m in _TOKEN_DECL_RE.finditer(body)}
    return modes
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_contrast.py -q`
Expected: PASS (10 tests).

- [ ] **Step 5: Lint + type + commit**

Run: `.venv/bin/ruff check src/dazzle/core/contrast.py tests/unit/test_contrast.py --fix && .venv/bin/ruff format src/dazzle/core/contrast.py tests/unit/test_contrast.py`
Run: `.venv/bin/mypy src/dazzle/core/contrast.py`
Expected: clean. (If the hex-parse `tuple(...)` genexpr needs help, replace with an explicit 3-tuple.)

```bash
git add src/dazzle/core/contrast.py tests/unit/test_contrast.py
git commit -m "feat: core/contrast — WCAG maths + pair tables + family CSS parser (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Contrast gate inside `validate_themespec`

**Files:**
- Modify: `src/dazzle/core/themespec_loader.py` (`validate_themespec`, ~line 287)
- Create: `tests/unit/test_themespec_contrast.py`

**Interfaces:**
- Consumes: `check_pairs`, `THEMESPEC_PAIRS` from Task 1; `dazzle.core.oklch.generate_palette(brand_hue, brand_chroma, mode=…, accent_hue_offset=…, neutral_chroma=…, semantic_overrides=…)`.
- Produces: `validate_themespec` errors of the form `palette contrast (light): text-primary/bg-primary 3.82:1 < 4.5:1`.

- [ ] **Step 1: Calibrate — do the scaffold defaults pass?**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from dazzle.core.oklch import generate_palette
from dazzle.core.contrast import check_pairs, THEMESPEC_PAIRS, ContrastPair
for mode in ('light','dark'):
    pal = generate_palette(250.0, 0.15, mode=mode)
    print(mode, 'text failures:', check_pairs(pal, THEMESPEC_PAIRS))
    ui = (ContrastPair('border-strong','bg-primary',3.0,'ui'),)
    print(mode, 'ui border-strong:', check_pairs(pal, ui))
"
```

Decision per Global Constraints: text failures on defaults → fix `generate_palette` anchors (e.g. a `*-text` step too light), never the gate. `border-strong/bg-primary` joins `THEMESPEC_PAIRS` as an **error** only if both modes pass on defaults; otherwise it is added to the validator as a **warning** with a one-line rationale comment ("hairline borders are an industry norm; 3:1 border contrast is not how modern systems ship — warn, don't block").

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_themespec_contrast.py`:

```python
"""#1567 slice 2 — validate_themespec fails on sub-AA generated palettes."""

import pytest

from dazzle.core.ir.themespec import ThemeSpecYAML
from dazzle.core.themespec_loader import validate_themespec

pytestmark = pytest.mark.gate


def test_default_themespec_passes_contrast() -> None:
    result = validate_themespec(ThemeSpecYAML())
    contrast_errors = [e for e in result.errors if "contrast" in e]
    assert contrast_errors == [], contrast_errors


def test_low_contrast_palette_fails_with_pair_named_errors() -> None:
    # Near-zero chroma + a mid-lightness trick isn't expressible via PaletteSpec
    # knobs alone, so monkeypatch-free route: neutral_chroma is legal but the
    # semantic overrides can force warning-on-warning hues; instead the reliable
    # low-contrast lever is asserting the ERROR FORMAT via a direct check_pairs
    # call plus validating the wiring with a stubbed generate_palette.
    import dazzle.core.themespec_loader as loader

    def bad_palette(*args, **kwargs):
        return {"text-primary": "oklch(0.700 0.0000 0.0)", "bg-primary": "oklch(0.990 0.0000 0.0)"}

    orig = loader.generate_palette
    loader.generate_palette = bad_palette
    try:
        result = validate_themespec(ThemeSpecYAML())
    finally:
        loader.generate_palette = orig
    joined = "\n".join(result.errors)
    assert "contrast" in joined and "text-primary/bg-primary" in joined
    assert "(light)" in joined and "(dark)" in joined
```

(Adjust the stub seam to match Step 3's import style — the test stubs whatever name `validate_themespec` actually calls.)

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_themespec_contrast.py -q`
Expected: `test_low_contrast_palette_fails_with_pair_named_errors` FAILS (no contrast errors emitted yet). The default-passes test may already pass vacuously.

- [ ] **Step 4: Wire the check into `validate_themespec`**

In `core/themespec_loader.py`, add a module-level import (`from dazzle.core.oklch import generate_palette` — check how `dtcg_export.py` derives generate_palette args from `themespec.palette` and mirror it exactly), then at the end of `validate_themespec` (before `return result`):

```python
    # Palette contrast gate (#1567 slice 2): generate the concrete palette both
    # modes and hard-fail sub-AA text pairs. A themespec that would render
    # illegible text is not "done" — this is the deterministic floor of the
    # new-property authoring path.
    from dazzle.core.contrast import THEMESPEC_PAIRS, check_pairs

    p = themespec.palette
    overrides = {
        k: v
        for k, v in {
            "success_hue": p.semantic_overrides.success_hue,
            "warning_hue": p.semantic_overrides.warning_hue,
            "danger_hue": p.semantic_overrides.danger_hue,
            "info_hue": p.semantic_overrides.info_hue,
        }.items()
        if v is not None
    }
    for mode in ("light", "dark"):
        palette = generate_palette(
            p.brand_hue,
            p.brand_chroma,
            mode=mode,
            accent_hue_offset=p.accent_hue_offset,
            neutral_chroma=p.neutral_chroma,
            semantic_overrides=overrides or None,
        )
        for failure in check_pairs(palette, THEMESPEC_PAIRS):
            result.add_error(f"palette contrast ({mode}): {failure}")
```

(Adapt the `semantic_overrides` field access to the real `PaletteSpec` shape from `core/ir/themespec.py`; mirror `dtcg_export.py`'s existing call. Apply the Step-1 UI-pair decision — either extend `THEMESPEC_PAIRS` or add a `result.add_warning` loop for the UI pair.)

- [ ] **Step 5: Run tests + fix defaults if calibration demanded**

Run: `.venv/bin/python -m pytest tests/unit/test_themespec_contrast.py tests/unit/test_sitespec_hygiene.py -q`
Expected: PASS. Also confirm no existing themespec tests broke:
Run: `.venv/bin/python -m pytest tests/unit -k themespec -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/themespec_loader.py tests/unit/test_themespec_contrast.py
git commit -m "feat: hard WCAG contrast gate in validate_themespec (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Family contrast gate (the 4 shipped families)

**Files:**
- Create: `tests/unit/test_family_contrast.py`

**Interfaces:**
- Consumes: `parse_family_modes`, `check_pairs`, `FAMILY_PAIRS`, `ContrastPair` from Task 1.

- [ ] **Step 1: Calibrate against the real 4 families**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from pathlib import Path
from dazzle.core.contrast import parse_family_modes, check_pairs, FAMILY_PAIRS, ContrastPair
UI = (ContrastPair('border','background',3.0,'ui'), ContrastPair('ring','background',3.0,'ui'))
for f in sorted(Path('packages/hatchi-maxchi/families').glob('*.css')):
    modes = parse_family_modes(f.read_text())
    for mode, tokens in modes.items():
        text_f = check_pairs(tokens, FAMILY_PAIRS)
        ui_f = check_pairs(tokens, UI)
        print(f'{f.name} [{mode}] text:{text_f or \"OK\"} ui:{ui_f or \"OK\"}')
"
```

Per the slice-1 stance: a **genuine** text-pair failure in a shipped family is a finding — fix the family token (preferred) or add it to a tiny documented `KNOWN_EXCEPTIONS` set with rationale. Judge each: `muted-foreground/background` at 4.4:1 is a fix (nudge lightness); a decorative pair is an exception. UI pairs: same decision rule as Task 2 Step 1 (gate only if the corpus passes; else drop from the gate with the rationale comment).

- [ ] **Step 2: Write the gate (encoding the calibration outcome)**

Create `tests/unit/test_family_contrast.py`:

```python
"""#1567 slice 2 — the 4 shipped HM aesthetic families must clear WCAG AA on the
canonical text pairs, in both modes. The framework holds its own curated
aesthetics to the same floor validate_themespec enforces on user themespecs."""

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
    # 4 families x at least one mode each; no silent parser failure.
    assert len(_FAMILIES) >= 4
    assert len(list(_cases())) >= 8
```

(If Step 1 found fixable failures, fix the family token values in the same task, rebuild the dist — `python scripts/build_dist.py` — and regenerate `scripts/gen_ux_catalogue.py` if any component CSS was touched. Token-value-only family edits regenerate the served themes at build time.)

- [ ] **Step 3: Run the gate**

Run: `.venv/bin/python -m pytest tests/unit/test_family_contrast.py -q`
Expected: PASS (8+ parametrized cases).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_family_contrast.py
# plus any family CSS fixes + regenerated dist/catalogue artifacts from calibration
git commit -m "test: WCAG AA contrast gate over the 4 shipped HM families (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `dazzle qa property-vision` (advisory)

**Files:**
- Modify: `src/dazzle/qa/taste_panel.py` (`score_image` optional `dimensions` param)
- Create: `src/dazzle/qa/property_vision.py`
- Modify: `src/dazzle/cli/qa.py` (after `component-vision`, ~line 1155)
- Create: `tests/unit/test_property_vision.py`

**Interfaces:**
- Consumes: `SITESPEC_VISION_DIMENSIONS` + `TasteDimension`; exemplar manifest at `.dazzle/composition/references/sitespec/sitespec_references_manifest.json` (shape: `{"families": [...], "references": [{"family", "name", "url", "theme", "screenshot"}]}`); slice-1 pattern from `qa/component_vision.py`.
- Produces:
  - `taste_panel.score_image(..., dimensions: Sequence[TasteDimension] | None = None)` — `None` keeps today's `dimensions_for_theme(image.theme)` behaviour.
  - `property_vision.exemplars_for(family: str, manifest_path: Path | None = None) -> list[Path]` — screenshot paths; raises `FileNotFoundError` (manifest missing) / `KeyError` (family absent or zero refs).
  - `property_vision.score_property(url: str, family: str, *, judges, model, out_dir, capture, score_fn) -> dict` — `{"url", "family", "judges", "model", "scores": {dim: mean}, "image", "exemplars": [...]}`.

- [ ] **Step 1: Add the `dimensions` param to `score_image`**

In `taste_panel.py`, change the signature and the two lines that pick dims:

```python
def score_image(
    image: PanelImage,
    *,
    judge: int,
    repeat: int = 0,
    model: str = DEFAULT_JUDGMENT_MODEL,
    client: Any | None = None,
    dimensions: Sequence[TasteDimension] | None = None,
) -> list[JudgeScore]:
```

and

```python
    dims = list(dimensions) if dimensions is not None else dimensions_for_theme(image.theme)
    prompt = build_judge_prompt(dims)
```

(Add `Sequence` + `TasteDimension` imports; default `None` = byte-identical current behaviour, so the whole existing panel path is untouched.)

Run: `.venv/bin/python -m pytest tests/unit -k taste_panel -q`
Expected: PASS (no behaviour change).

- [ ] **Step 2: Write the failing glue tests**

Create `tests/unit/test_property_vision.py`:

```python
"""#1567 slice 2 — property-vision glue (screenshot->score vs family exemplars),
heavy parts mocked. The real path is on-demand and subscription-billed."""

import json

import pytest

pytestmark = pytest.mark.gate


def _write_manifest(tmp_path, family="stripe", n_refs=1):
    refs = []
    for i in range(n_refs):
        png = tmp_path / f"{family}_{i}.png"
        png.write_bytes(b"\x89PNG fake")
        refs.append(
            {"family": family, "name": f"ref{i}", "url": "https://x", "theme": "light",
             "screenshot": str(png)}
        )
    manifest = tmp_path / "sitespec_references_manifest.json"
    manifest.write_text(json.dumps({"families": [family], "references": refs}))
    return manifest


def test_exemplars_for_finds_family_refs(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    manifest = _write_manifest(tmp_path, "stripe", 2)
    paths = exemplars_for("stripe", manifest_path=manifest)
    assert len(paths) == 2 and all(p.exists() for p in paths)


def test_exemplars_for_missing_family_raises(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    manifest = _write_manifest(tmp_path, "stripe", 1)
    with pytest.raises(KeyError):
        exemplars_for("paper", manifest_path=manifest)


def test_exemplars_for_missing_manifest_raises(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    with pytest.raises(FileNotFoundError):
        exemplars_for("stripe", manifest_path=tmp_path / "nope.json")


def test_score_property_glue(tmp_path) -> None:
    from dazzle.qa.property_vision import score_property
    from dazzle.qa.taste_panel import JudgeScore

    manifest = _write_manifest(tmp_path, "stripe", 1)
    captured = {}

    def fake_capture(url, out_png):
        captured["url"] = url
        out_png.write_bytes(b"\x89PNG fake")
        return out_png

    def fake_score(image, *, judge, repeat=0, model, client=None, dimensions=None):
        assert dimensions is not None  # must be the sitespec dims, not taste
        return [JudgeScore(image_id=image.image_id, dimension="hero_impact", score=7, judge=judge)]

    result = score_property(
        "http://localhost:3000/",
        "stripe",
        judges=2,
        model="fake",
        out_dir=tmp_path,
        capture=fake_capture,
        score_fn=fake_score,
        manifest_path=manifest,
    )
    assert captured["url"] == "http://localhost:3000/"
    assert result["scores"]["hero_impact"] == 7.0
    assert result["family"] == "stripe"
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_property_vision.py -q`
Expected: FAIL (`No module named 'dazzle.qa.property_vision'`).

- [ ] **Step 4: Implement `qa/property_vision.py`**

```python
"""On-demand property vision score (#1567 slice 2) — advisory, not a gate.

Screenshots a rendered property page (1440x1024 fold) and scores it against
SITESPEC_VISION_DIMENSIONS, supplying the chosen family's exemplar references so
the family_fidelity dimension judges "on-family" against real anchors. Heavy
parts (Playwright capture, judge client) are injectable; subscription-billed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.core.sitespec_vision_rubric import SITESPEC_VISION_DIMENSIONS
from dazzle.qa.taste_panel import JudgeScore, PanelImage, score_image

__all__ = ["exemplars_for", "score_property"]

DEFAULT_MANIFEST = Path(".dazzle/composition/references/sitespec/sitespec_references_manifest.json")


def exemplars_for(family: str, manifest_path: Path | None = None) -> list[Path]:
    """Exemplar screenshot paths for a family. FileNotFoundError if the manifest
    hasn't been captured; KeyError if the family has no references."""
    path = manifest_path or DEFAULT_MANIFEST
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run: python scripts/taste/capture_sitespec_references.py"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    refs = [Path(r["screenshot"]) for r in manifest.get("references", []) if r["family"] == family]
    refs = [r for r in refs if r.exists()]
    if not refs:
        raise KeyError(
            f"no captured exemplars for family {family!r} — run: "
            f"python scripts/taste/capture_sitespec_references.py --family {family}"
        )
    return refs


def _default_capture(url: str, out_png: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.goto(url, wait_until="networkidle")
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()
    return out_png


def score_property(
    url: str,
    family: str,
    *,
    judges: int = 3,
    model: str = DEFAULT_JUDGMENT_MODEL,
    out_dir: Path = Path(".dazzle/qa/property-vision"),
    capture: Callable[[str, Path], Path] = _default_capture,
    score_fn: Callable[..., list[JudgeScore]] = score_image,
    client: Any | None = None,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    """Screenshot `url`, score vs the sitespec vision rubric + family exemplars."""
    exemplars = exemplars_for(family, manifest_path=manifest_path)  # usage errors first
    out_dir.mkdir(parents=True, exist_ok=True)
    png = capture(url, out_dir / "property.png")
    image = PanelImage(image_id=f"property-{family}", source="dazzle", label=url, path=png, theme="light")

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for j in range(judges):
        for js in score_fn(
            image, judge=j, model=model, client=client, dimensions=SITESPEC_VISION_DIMENSIONS
        ):
            totals[js.dimension] = totals.get(js.dimension, 0.0) + js.score
            counts[js.dimension] = counts.get(js.dimension, 0) + 1
    means = {d: round(totals[d] / counts[d], 2) for d in totals}
    return {
        "url": url,
        "family": family,
        "judges": judges,
        "model": model,
        "scores": means,
        "image": str(png),
        "exemplars": [str(e) for e in exemplars],
    }
```

**Implementation note (family_fidelity):** `score_image` sends one image. Supplying the exemplars *alongside* the page image in the same judge call (as `build_sitespec_judge_prompt` documents) would need a multi-image message — for this slice, `exemplars` are resolved + returned in the report (proving the wiring and the usage-error path) and the judged score covers the 7 non-fidelity dimensions plus a prompt-anchored `family_fidelity`. If a richer multi-image call is wanted later, extend `score_image` — out of scope here; note it in the CLI help ("family_fidelity judged from description, not side-by-side, in this version").

- [ ] **Step 5: Add the CLI subcommand**

In `cli/qa.py`, after the `component-vision` command:

```python
@qa_app.command("property-vision")
def qa_property_vision(
    url: str = typer.Argument(..., help="URL of the rendered property page (e.g. http://localhost:3000/)"),
    family: str = typer.Option(..., "--family", help="Aesthetic family: stripe|paper|linear-dark|expressive"),
    judges: int = typer.Option(3, "--judges", help="Independent judge passes"),
    model: str | None = typer.Option(None, "--model", help="Override judge model"),
    out: Path = typer.Option(Path(".dazzle/qa/property-vision"), "--out", help="Report output dir"),
) -> None:
    """On-demand advisory vision score for a property page vs its family exemplars.

    Subscription/API-billed. Advisory only — exits 0 on a successful score.
    family_fidelity is prompt-anchored (exemplars listed in the report), not
    side-by-side, in this version.
    """
    import json

    from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
    from dazzle.qa.property_vision import score_property

    try:
        result = score_property(
            url, family, judges=judges, model=model or DEFAULT_JUDGMENT_MODEL, out_dir=out
        )
    except (FileNotFoundError, KeyError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=2) from None

    out.mkdir(parents=True, exist_ok=True)
    (out / "property-vision.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(result["scores"], indent=2))
    typer.echo(f"Advisory score for {url} [{family}] — report: {out / 'property-vision.json'}")
```

- [ ] **Step 6: Run tests + ratchet + smoke**

Run: `.venv/bin/python -m pytest tests/unit/test_property_vision.py -q`
Expected: PASS.
Run: `.venv/bin/python -m pytest tests/unit/test_deferred_imports_ratchet_1438.py -q`
If it trips on `cli/qa.py` (2 new CLI-defer imports): bump its entry in `tests/unit/fixtures/deferred_imports_baseline.json` with the slice-1 justification (CLI-defer keeps `dazzle qa` startup fast).
Run: `.venv/bin/dazzle qa property-vision http://x --family nope 2>&1 | head -2`
Expected: manifest/family usage error, exit 2 (no API call).

- [ ] **Step 7: Lint + type + commit**

Run: `.venv/bin/ruff check src/dazzle/qa/ src/dazzle/cli/qa.py tests/unit/test_property_vision.py --fix && .venv/bin/ruff format src/dazzle/qa/ src/dazzle/cli/qa.py tests/unit/test_property_vision.py`
Run: `.venv/bin/mypy src/dazzle/qa/property_vision.py src/dazzle/qa/taste_panel.py`
Expected: clean.

```bash
git add src/dazzle/qa/property_vision.py src/dazzle/qa/taste_panel.py src/dazzle/cli/qa.py \
  tests/unit/test_property_vision.py tests/unit/fixtures/deferred_imports_baseline.json
git commit -m "feat: dazzle qa property-vision advisory vs family exemplars (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Doc section, gates, ship, close #1567

**Files:**
- Modify: `src/dazzle/core/design_context.py` (`render_markdown`)
- Regenerate: `docs/reference/hm-design-context.md`
- Modify: `CHANGELOG.md`, version files (via `/bump`)

- [ ] **Step 1: Emit the "Standing up a new property" section**

In `design_context.py` `render_markdown()`, after the "Authoring a new Hyperpart" block (before `return`):

```python
    lines.append("## Standing up a new property")
    lines.append("")
    lines.append(
        "1. **Pick** a shipped family when one fits the brand — `[ui] theme = "
        '"stripe" | "paper" | "linear-dark" | "expressive"` — done.'
    )
    lines.append(
        "2. **Or author**: study the target family's exemplars (capture via "
        "`scripts/taste/capture_sitespec_references.py`), then `sitespec scaffold_theme` "
        "and edit `themespec.yaml` (a compact parametric spec — not raw tokens)."
    )
    lines.append(
        "3. **Deterministic floor (must pass):** `validate_theme` — WCAG-AA "
        "contrast-gated on the generated palette, both modes; then `generate_tokens`."
    )
    lines.append(
        "4. **Judged read (advisory):** `dazzle qa property-vision <url> --family <name>` "
        "against the family's exemplars."
    )
    lines.append("")
```

- [ ] **Step 2: Regenerate + full gates**

Run: `.venv/bin/python scripts/gen_design_context.py`
Run: `.venv/bin/python -m pytest tests/unit -m gate -q`
Expected: PASS (design-context doc-drift, new contrast gates, everything).
Run: `.venv/bin/mypy src/dazzle` and `.venv/bin/python -m mkdocs build --strict >/dev/null; echo $?`
Expected: clean / 0.

- [ ] **Step 3: Commit the doc, then CHANGELOG + bump + ship**

```bash
git add src/dazzle/core/design_context.py docs/reference/hm-design-context.md
git commit -m "docs: 'Standing up a new property' section in hm-design-context (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

CHANGELOG under Unreleased:

```markdown
### Added
- **New-property authoring path (#1567, slice 2 — closes #1567)** — `core/contrast.py`
  (WCAG 2.x maths + canonical pair tables); `validate_theme` now hard-fails sub-AA text
  contrast on the generated palette (both modes) — the deterministic floor of the
  authoring path; a live gate holds the 4 shipped HM families to the same AA standard
  (`tests/unit/test_family_contrast.py`); advisory `dazzle qa property-vision <url>
  --family <name>` scores a rendered property against its family exemplars; and the
  "Standing up a new property" section in `docs/reference/hm-design-context.md` ties the
  path together.

### Agent Guidance
- Standing up a new property? Follow the section in `docs/reference/hm-design-context.md`:
  pick a family or `scaffold_theme` → `validate_theme` (contrast is now a hard error) →
  `generate_tokens` → optional `qa property-vision`.
```

Run: `/bump patch` then `/ship`. Monitor CI to green.

- [ ] **Step 4: Close #1567**

```bash
gh issue comment 1567 --body "$(cat <<'EOF'
**Slice 2 shipped — closing.** The new-property authoring path is now supported end to
end, built on the existing ThemeSpec system (the scaffold already existed; the gap was
the gate): `core/contrast.py` WCAG maths; `validate_theme` hard-fails sub-AA text
contrast on the generated palette (both modes); the 4 shipped HM families are held to
the same AA floor by a live gate; advisory `dazzle qa property-vision <url> --family
<name>` scores a rendered property against its family exemplars; and
`docs/reference/hm-design-context.md` gained the "Standing up a new property" section.

With slice 1 (component token-discipline gate, v0.101.10), both affordances of this
issue are delivered: authoring-time enforcement for new Hyperparts, and a documented,
auto-scored path for new properties.

Out of scope (future, if wanted): HM-families ↔ ThemeSpec unification; side-by-side
multi-image family_fidelity judging; APCA.

🔖 Claude-lens: dazzle
EOF
)"
gh issue close 1567
```

---

## Self-Review

**1. Spec coverage:** Part A → Task 1; Part B → Task 2 (incl. defaults-are-a-generator-bug + UI-pair calibration rule); Part C → Task 3 (calibrate-first + KNOWN_EXCEPTIONS); Part D → Task 4 (incl. the `score_image` dimensions param and the honest family_fidelity limitation note); Part E → Task 5. Out-of-scope items untouched; #1567 closed at the end. ✓

**2. Placeholder scan:** No TBD/TODO. The two "adapt to the real shape" notes (PaletteSpec field access in Task 2; the stub seam in its test) each name the exact reference file to mirror (`dtcg_export.py`) — grounded, not deferred. ✓

**3. Type consistency:** `parse_css_color -> RGB | None`, `check_pairs(dict, tuple[ContrastPair,...]) -> list[str]`, `parse_family_modes -> dict[str, dict[str, str]]` used identically in Tasks 1/2/3. `score_image(..., dimensions=None)` defined Task 4 Step 1, consumed by `score_property` and asserted in the fake. `exemplars_for` raises `FileNotFoundError`/`KeyError`; the CLI catches exactly those. `JudgeScore(image_id, dimension, score, judge, repeat)` matches the real dataclass. ✓

**Risk note:** Task 3 calibration may surface real sub-AA pairs in shipped families (e.g. `muted-foreground` in a warm palette). That is the point of the gate — budget the fix into Task 3 rather than treating it as scope creep; only genuinely-decorative pairs earn `KNOWN_EXCEPTIONS`.
