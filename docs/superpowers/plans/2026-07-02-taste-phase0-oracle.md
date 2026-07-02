# Taste Phase 0+1: Oracle & Artifact — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the blind vision-judge parity gate (oracle), baseline all 12 example apps against shadcn/Vercel-dialect references, and write the canonical `docs/reference/taste.md` artifact.

**Architecture:** A pure rubric module in `core/` (single source of truth for taste dimensions), a `qa/taste_panel.py` module that assembles a blind pool of screenshots (Dazzle fleet manifest + gitignored reference captures), scores them with N independent vision-LLM judges, measures judge noise, and computes a parity verdict; a `dazzle qa taste-panel` CLI; opt-in taste dimensions in `composition analyze`. The committed baseline is the "before" record for Phases 2–4 (separate plans, written after this one lands).

**Tech Stack:** Python 3.12, Playwright (async, existing `BrowserGate`), `anthropic` vision API (existing pattern in `core/composition_visual.py`), PIL, pytest.

**Spec:** `docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md`

## Global Constraints

- Type hints required on all public functions (mypy-enforced); Pydantic for cross-module data shapes is the norm, but this feature follows the existing `qa/` + `composition_*` convention of frozen dataclasses.
- No new singletons (ADR-0005); explicit dependencies.
- Reference screenshots are NEVER committed — they live under `.dazzle/composition/references/taste/` which is already gitignored (`.gitignore:76-77`). Commit scripts, not pixels.
- Judge model default: `DEFAULT_JUDGMENT_MODEL` from `dazzle.core.model_defaults` (currently `claude-sonnet-4-6`), always overridable via `--model`.
- Rubric dimensions are phrased as generic design quality, never "resemblance to shadcn" (Goodhart guard, spec §Phase 1).
- Run the FULL unit suite before shipping, not `-k` filtered (IR-drift lesson): `pytest -n auto --dist loadgroup -m "not e2e" tests/`.
- Every push: `ruff check src/ tests/ --fix && ruff format src/ tests/`, `mypy src/dazzle`, version bump, clean worktree.
- Layer rule: `core/` must not import from `qa/`; `qa/` may import from `core/`.

---

### Task 1: Taste rubric module (single source of truth)

**Files:**
- Create: `src/dazzle/core/taste_rubric.py`
- Test: `tests/unit/test_taste_rubric.py`

**Interfaces:**
- Produces: `TasteDimension` (frozen dataclass: `key: str`, `title: str`, `question: str`, `anchors: tuple[tuple[int, str], ...]`, `applies_to: str` — one of `"light" | "dark" | "both"`), `TASTE_DIMENSIONS: tuple[TasteDimension, ...]` (6 entries), `dimensions_for_theme(theme: str) -> tuple[TasteDimension, ...]`, `build_judge_prompt(dimensions: Sequence[TasteDimension]) -> str`.
- Consumed by: Task 4/5 (`qa/taste_panel.py`), Task 7 (`composition_visual.py`), Task 9 (doc drift gate).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_taste_rubric.py
"""Taste rubric — single source of truth for judged aesthetic dimensions."""

from dazzle.core.taste_rubric import (
    TASTE_DIMENSIONS,
    TasteDimension,
    build_judge_prompt,
    dimensions_for_theme,
)

EXPECTED_KEYS = [
    "typographic_hierarchy",
    "spatial_rhythm",
    "color_discipline",
    "state_completeness",
    "dark_mode_integrity",
    "perceived_craft",
]


def test_dimension_keys_are_the_spec_six() -> None:
    assert [d.key for d in TASTE_DIMENSIONS] == EXPECTED_KEYS


def test_dimensions_are_frozen_and_complete() -> None:
    for d in TASTE_DIMENSIONS:
        assert isinstance(d, TasteDimension)
        assert d.title and d.question
        # Anchors at 2, 5, 8 give judges a calibrated 1-10 scale.
        assert [score for score, _ in d.anchors] == [2, 5, 8]
        assert all(text for _, text in d.anchors)
        assert d.applies_to in ("light", "dark", "both")


def test_dark_mode_integrity_only_applies_to_dark() -> None:
    (dark_dim,) = [d for d in TASTE_DIMENSIONS if d.key == "dark_mode_integrity"]
    assert dark_dim.applies_to == "dark"


def test_dimensions_for_theme_filters() -> None:
    light = dimensions_for_theme("light")
    dark = dimensions_for_theme("dark")
    assert "dark_mode_integrity" not in [d.key for d in light]
    assert "dark_mode_integrity" in [d.key for d in dark]
    assert len(light) == 5
    assert len(dark) == 6


def test_judge_prompt_contains_every_dimension_and_no_dialect_names() -> None:
    prompt = build_judge_prompt(TASTE_DIMENSIONS)
    for d in TASTE_DIMENSIONS:
        assert d.key in prompt
        assert d.question in prompt
    # Goodhart guard: the rubric never names the dialect it competes with.
    for banned in ("shadcn", "Tailwind", "Vercel", "React"):
        assert banned.lower() not in prompt.lower()
    assert "JSON" in prompt  # response-format instruction present
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_taste_rubric.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.taste_rubric'`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/core/taste_rubric.py
"""Taste rubric — the judged dimensions of the Dazzle house aesthetic.

Single source of truth consumed by the blind judge panel
(``dazzle.qa.taste_panel``), the composition pipeline (opt-in ``taste``
focus), and the drift gate on ``docs/reference/taste.md``.

Dimensions are phrased as generic design quality. They MUST NOT name or
allude to any specific framework, library, or company aesthetic — the
parity target is perceived quality, not resemblance (spec: Goodhart guard).
"""

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TASTE_DIMENSIONS",
    "TasteDimension",
    "build_judge_prompt",
    "dimensions_for_theme",
]


@dataclass(frozen=True)
class TasteDimension:
    """One judged dimension of visual taste."""

    key: str
    title: str
    question: str
    # (score, description) calibration anchors at 2 / 5 / 8 on a 1-10 scale.
    anchors: tuple[tuple[int, str], ...]
    applies_to: str  # "light" | "dark" | "both"


TASTE_DIMENSIONS: tuple[TasteDimension, ...] = (
    TasteDimension(
        key="typographic_hierarchy",
        title="Typographic hierarchy",
        question=(
            "Does type alone communicate what matters most on this screen? "
            "Judge scale contrast, weight discipline, line length/height, and "
            "whether headings, labels, values and captions are instantly "
            "distinguishable without relying on boxes or color."
        ),
        anchors=(
            (2, "Near-uniform text sizes; hierarchy only guessable from position."),
            (5, "Clear heading/body split but weak label/value/caption tiers."),
            (8, "Deliberate scale with confident weight contrast; every text role identifiable at a glance."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="spatial_rhythm",
        title="Spatial rhythm",
        question=(
            "Do gaps, padding and alignment follow a consistent rhythm? Judge "
            "whether spacing looks like it sits on a fixed scale, whether "
            "related items cluster and unrelated items separate, and whether "
            "density feels intentional rather than cramped or vacant."
        ),
        anchors=(
            (2, "Arbitrary gaps; misaligned edges; crowding next to dead space."),
            (5, "Mostly consistent spacing with occasional off-scale gaps or ragged alignment."),
            (8, "Even, confident rhythm; alignment lines are visible; density reads as designed."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="color_discipline",
        title="Color discipline",
        question=(
            "Is color used with restraint and meaning? Judge whether neutrals "
            "carry the structure, whether one accent is applied consistently to "
            "what matters, and whether semantic colors (success/warning/danger) "
            "appear only where they mean something."
        ),
        anchors=(
            (2, "Competing hues; decorative color; unclear what color signifies."),
            (5, "Restrained palette but accent applied inconsistently or semantics muddy."),
            (8, "Neutrals do the work; one accent, purposefully placed; color always means something."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="state_completeness",
        title="State completeness",
        question=(
            "Do the visible interactive elements look deliberately designed in "
            "their current state? Judge buttons, inputs, rows and empty regions: "
            "are affordances crisp (borders, fills, focus/selection cues), do "
            "empty states look designed rather than absent, and is there any "
            "browser-default styling showing through?"
        ),
        anchors=(
            (2, "Browser-default controls; empty areas look broken or unfinished."),
            (5, "Styled controls but flat affordances; empty states present but perfunctory."),
            (8, "Every visible control and empty state looks intentionally finished."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="dark_mode_integrity",
        title="Dark-mode integrity",
        question=(
            "Does this dark screen look designed as a dark material rather than "
            "an inverted light theme? Judge surface layering (does elevation "
            "read through lightness?), contrast comfort (no pure-black pits or "
            "glaring whites), and whether accents/semantic colors were "
            "recalibrated for the dark context."
        ),
        anchors=(
            (2, "Inverted-looking; harsh contrast; colors glow or vanish."),
            (5, "Serviceable dark theme; layering weak; some colors uncorrected."),
            (8, "Coherent dark material; elevation legible; recalibrated, comfortable palette."),
        ),
        applies_to="dark",
    ),
    TasteDimension(
        key="perceived_craft",
        title="Perceived craft",
        question=(
            "Overall, does this screen look like a design team sweated the "
            "details? Judge the gestalt: corner radii and border consistency, "
            "shadow/elevation quality, icon/text optical alignment, and the "
            "absence of anything that looks accidental."
        ),
        anchors=(
            (2, "Reads as unstyled scaffolding or template output."),
            (5, "Competent and clean but generic; nothing looks loved."),
            (8, "Polished and coherent; detail quality signals a strong design hand."),
        ),
        applies_to="both",
    ),
)


def dimensions_for_theme(theme: str) -> tuple[TasteDimension, ...]:
    """Return the dimensions applicable to *theme* ("light" or "dark")."""
    return tuple(d for d in TASTE_DIMENSIONS if d.applies_to in ("both", theme))


def build_judge_prompt(dimensions: Sequence[TasteDimension]) -> str:
    """Build the scoring prompt for one screenshot across *dimensions*.

    The judge sees ONE image and returns strict JSON:
    ``{"scores": {"<key>": int, ...}, "worst_detail": str}``.
    """
    lines = [
        "You are a senior product designer scoring a single UI screenshot.",
        "Score each dimension from 1 (worst) to 10 (best) using the anchors.",
        "Judge only what is visible. Do not guess at the technology used;",
        "score design quality, not style familiarity.",
        "",
    ]
    for d in dimensions:
        lines.append(f"## {d.key} — {d.title}")
        lines.append(d.question)
        for score, text in d.anchors:
            lines.append(f"  {score} = {text}")
        lines.append("")
    keys = ", ".join(f'"{d.key}": <1-10>' for d in dimensions)
    lines.append(
        "Respond with ONLY a JSON object, no prose, of the form: "
        f'{{"scores": {{{keys}}}, "worst_detail": "<one sentence naming the '
        'single weakest visible detail>"}'
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_taste_rubric.py -v`
Expected: 5 PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/core/taste_rubric.py tests/unit/test_taste_rubric.py --fix && ruff format src/dazzle/core/taste_rubric.py tests/unit/test_taste_rubric.py
mypy src/dazzle/core/taste_rubric.py
git add src/dazzle/core/taste_rubric.py tests/unit/test_taste_rubric.py
git commit -m "feat(taste): core taste rubric — 6 judged dimensions with calibration anchors"
```

---

### Task 2: Reference capture script

**Files:**
- Create: `scripts/taste/capture_references.py`

**Interfaces:**
- Produces: PNG files named `{name}_{theme}.png` in `.dazzle/composition/references/taste/` plus `references_manifest.json` of shape `{"captured_at": iso, "references": [{"name", "url", "theme", "screenshot"}]}`.
- Consumed by: Task 4 (`assemble_pool` reads `references_manifest.json`).

Note: this is a standalone operator script (not framework code, no unit test — the manual verification IS the test; it is exercised for real in Task 8). Third-party pixels land in `.dazzle/` which is gitignored; only the script is committed.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
# scripts/taste/capture_references.py
"""Capture shadcn/Vercel-dialect reference screenshots for the taste panel.

Screenshots are the parity references for the blind judge panel
(spec: docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md,
Phase 0). They are THIRD-PARTY content: written to .dazzle/ (gitignored),
never committed. Re-run this script to refresh; public pages drift and
that is fine — the panel is re-baselined per run.

Usage:
    python scripts/taste/capture_references.py            # capture all
    python scripts/taste/capture_references.py --list     # print targets
    python scripts/taste/capture_references.py --only shadcn_dashboard

Requires: playwright (`uv run playwright install chromium` if needed).
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

VIEWPORT = {"width": 1440, "height": 900}
OUT_DIR = Path(".dazzle/composition/references/taste")

# (name, url, themes) — themes via Playwright color-scheme emulation; the
# reference sites default to system preference so emulation flips them.
TARGETS: list[tuple[str, str, list[str]]] = [
    ("shadcn_dashboard", "https://ui.shadcn.com/examples/dashboard", ["light", "dark"]),
    ("shadcn_tasks", "https://ui.shadcn.com/examples/tasks", ["light", "dark"]),
    ("shadcn_cards", "https://ui.shadcn.com/examples/cards", ["light", "dark"]),
    ("shadcn_forms", "https://ui.shadcn.com/examples/forms", ["light", "dark"]),
    ("shadcn_music", "https://ui.shadcn.com/examples/music", ["light", "dark"]),
    ("vercel_home", "https://vercel.com", ["light", "dark"]),
    ("linear_home", "https://linear.app", ["dark"]),
    ("stripe_home", "https://stripe.com", ["light"]),
]


def capture(only: str | None) -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for name, url, themes in TARGETS:
            if only and name != only:
                continue
            for theme in themes:
                out = OUT_DIR / f"{name}_{theme}.png"
                try:
                    context = browser.new_context(
                        viewport=VIEWPORT, color_scheme=theme
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=45_000)
                    page.wait_for_timeout(1_500)  # settle fonts/animations
                    # Above-the-fold only: the panel judges a fixed 1440x900
                    # frame for every image, Dazzle and reference alike.
                    page.screenshot(path=str(out), full_page=False)
                    context.close()
                    entries.append(
                        {"name": name, "url": url, "theme": theme, "screenshot": str(out)}
                    )
                    print(f"  captured {out}")
                except Exception as exc:  # noqa: BLE001 — operator script, keep going
                    failures += 1
                    print(f"  FAILED {name} ({theme}): {exc}", file=sys.stderr)
        browser.close()

    manifest = {
        "captured_at": datetime.now(UTC).isoformat(),
        "viewport": VIEWPORT,
        "references": entries,
    }
    (OUT_DIR / "references_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(entries)} captured, {failures} failed → {OUT_DIR}")
    return 1 if failures and not entries else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print targets and exit")
    parser.add_argument("--only", help="capture a single named target")
    args = parser.parse_args()
    if args.list:
        for name, url, themes in TARGETS:
            print(f"{name}\t{url}\t{','.join(themes)}")
        return 0
    return capture(args.only)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the target list mode (offline check)**

Run: `python scripts/taste/capture_references.py --list`
Expected: 8 lines, tab-separated `name url themes`.

- [ ] **Step 3: Smoke one real capture**

Run: `python scripts/taste/capture_references.py --only shadcn_dashboard`
Expected: `captured .dazzle/composition/references/taste/shadcn_dashboard_light.png` and `..._dark.png`; `references_manifest.json` written. Open one PNG and confirm the dashboard rendered (not a cookie wall / blank).

- [ ] **Step 4: Confirm pixels are ignored, commit the script only**

```bash
git status --porcelain | grep -c ".dazzle" # Expected: 0
git add scripts/taste/capture_references.py
git commit -m "feat(taste): reference capture script — dialect screenshots for the blind panel (pixels gitignored)"
```

---

### Task 3: Dark/viewport/above-fold capture support in `qa capture`

**Files:**
- Modify: `src/dazzle/qa/capture.py` (`capture_screenshots` at line 98, `_capture_one` at line 201, `write_manifest` at line 152)
- Modify: `src/dazzle/qa/models.py` (`CapturedScreen`, line 9 — add `theme: str = "light"`)
- Modify: `src/dazzle/cli/qa.py` (`qa_capture`, line 872 — add `--dark`, `--viewport`, `--above-fold` options)
- Test: `tests/unit/test_qa_capture_options.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `capture_screenshots(..., viewport: str = "desktop", color_scheme: str = "light", full_page: bool = True)`; screenshot filenames become `{workspace}_{persona}_{viewport}_{scheme}.png`; manifest screen entries gain a `"theme"` key. `VIEWPORTS: dict[str, dict[str, int]] = {"desktop": {"width": 1440, "height": 900}, "mobile": {"width": 390, "height": 844}}` exported from `dazzle.qa.capture`.
- Downstream: the visual_tier2 strategy reads paths from the manifest (never hardcodes filenames), so the rename is safe; `write_manifest` already emits `viewport` per screen.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_qa_capture_options.py
"""qa capture: viewport/theme options and filename/manifest contract."""

import json
from pathlib import Path

from dazzle.qa.capture import VIEWPORTS, write_manifest
from dazzle.qa.models import CapturedScreen


def test_viewports_table() -> None:
    assert VIEWPORTS["desktop"] == {"width": 1440, "height": 900}
    assert VIEWPORTS["mobile"] == {"width": 390, "height": 844}


def test_captured_screen_carries_theme_default_light() -> None:
    s = CapturedScreen(
        persona="admin", workspace="main", url="http://x/app/workspaces/main",
        screenshot=Path("/tmp/x.png"),
    )
    assert s.theme == "light"


def test_write_manifest_includes_theme(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    screens = [
        CapturedScreen(
            persona="admin", workspace="main", url="u",
            screenshot=tmp_path / "main_admin_desktop_dark.png", theme="dark",
        )
    ]
    write_manifest(screens, app_name="ops_dashboard", manifest_path=manifest)
    data = json.loads(manifest.read_text())
    (app,) = data["apps"]
    assert app["screens"][0]["theme"] == "dark"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_capture_options.py -v`
Expected: FAIL — `ImportError: cannot import name 'VIEWPORTS'` (and `theme` unexpected kwarg).

- [ ] **Step 3: Implement**

In `src/dazzle/qa/models.py`, add to `CapturedScreen` after `viewport: str = "desktop"`:

```python
    theme: str = "light"
```

In `src/dazzle/qa/capture.py`, add after the `CaptureTarget` dataclass:

```python
VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
```

Change `capture_screenshots` signature (line 98) to:

```python
async def capture_screenshots(
    targets: list[CaptureTarget],
    site_url: str,
    api_url: str,
    project_dir: Path,
    *,
    output_dir: Path | None = None,
    viewport: str = "desktop",
    color_scheme: str = "light",
    full_page: bool = True,
) -> list[CapturedScreen]:
```

and thread the three new kwargs through the `_capture_one(...)` call. Change `_capture_one` to accept them:

```python
async def _capture_one(
    target: CaptureTarget,
    browser: Any,
    site_url: str,
    session_manager: SessionManager,
    output_dir: Path,
    *,
    viewport: str = "desktop",
    color_scheme: str = "light",
    full_page: bool = True,
) -> CapturedScreen | None:
```

with the filename (line 220) becoming:

```python
    screenshot_path = output_dir / f"{target.workspace}_{target.persona}_{viewport}_{color_scheme}.png"
```

the context creation (line 235) becoming:

```python
        context = await browser.new_context(
            viewport=VIEWPORTS[viewport], color_scheme=color_scheme
        )
```

the screenshot call (line 250) becoming:

```python
                await page.screenshot(path=str(screenshot_path), full_page=full_page)
```

and the returned record gaining the two fields:

```python
                return CapturedScreen(
                    persona=target.persona,
                    workspace=target.workspace,
                    url=full_url,
                    screenshot=screenshot_path,
                    viewport=viewport,
                    theme=color_scheme,
                )
```

In `write_manifest` (line 185), add `"theme": s.theme,` alongside `"viewport": s.viewport,`.

In `src/dazzle/cli/qa.py::qa_capture` (line 872), add options:

```python
    dark: bool = typer.Option(False, "--dark", help="Capture with dark color-scheme emulation"),
    viewport: str = typer.Option("desktop", "--viewport", help="desktop | mobile"),
    above_fold: bool = typer.Option(
        False, "--above-fold", help="Viewport-height screenshot instead of full page"
    ),
```

and pass them through the `capture_screenshots(...)` call (line 944):

```python
            capture_screenshots(
                targets,
                site_url=connection.site_url,
                api_url=connection.api_url,
                project_dir=project_dir,
                viewport=viewport,
                color_scheme="dark" if dark else "light",
                full_page=not above_fold,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_capture_options.py tests/unit -k "qa_capture or captured_screen or manifest" -v`
Expected: new tests PASS; then run the full qa-adjacent selection to catch old filename assumptions: `pytest tests/unit -k "qa" -q` — all PASS (fix any test pinning the old `{workspace}_{persona}.png` name by updating it to the new contract).

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/qa/ src/dazzle/cli/qa.py tests/unit/test_qa_capture_options.py --fix && ruff format src/dazzle/qa/ src/dazzle/cli/qa.py tests/unit/test_qa_capture_options.py
mypy src/dazzle
git add -A src/dazzle/qa src/dazzle/cli/qa.py tests/unit/test_qa_capture_options.py
git commit -m "feat(qa): capture viewport/color-scheme/above-fold options — taste-panel inputs"
```

---

### Task 4: Taste panel — pool assembly and pure math

**Files:**
- Create: `src/dazzle/qa/taste_panel.py`
- Test: `tests/unit/test_taste_panel.py`

**Interfaces:**
- Consumes: `dazzle.core.taste_rubric` (Task 1); fleet manifest JSON (Task 3 shape: `{"apps": [{"app", "screens": [{"persona","workspace","url","screenshot","viewport","theme"}]}]}`); references manifest JSON (Task 2 shape).
- Produces (all consumed by Tasks 5–6):
  - `PanelImage` frozen dataclass: `image_id: str`, `source: str` ("dazzle"|"reference"), `label: str` (app or reference name — for the report, never shown to judges), `path: Path`, `theme: str`
  - `assemble_pool(fleet_manifest: Path, references_manifest: Path) -> list[PanelImage]`
  - `blind_order(pool: list[PanelImage], seed: int) -> list[PanelImage]`
  - `aggregate_scores(scores: list[JudgeScore], *, sources: dict[str, str]) -> dict[str, dict[str, float]]` — `{dimension: {"dazzle": mean, "reference": mean}}`; *sources* maps `image_id` → source
  - `noise_sd(scores: list[JudgeScore]) -> dict[str, float]` — per-dimension pooled SD across repeat scores of the same image
  - `parity_verdict(means: dict[str, dict[str, float]], noise: dict[str, float], *, floor: float = 0.5) -> dict[str, dict[str, float | bool]]` — per dimension: `{"dazzle", "reference", "margin", "gap", "parity"}` where `margin = max(floor, 2 * noise_sd)` and `parity = dazzle >= reference - margin`
  - `JudgeScore` frozen dataclass: `image_id: str`, `dimension: str`, `score: int`, `judge: int`, `repeat: int = 0`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_taste_panel.py
"""Blind taste panel — pool assembly, blinding, aggregation, parity math."""

import json
from pathlib import Path

import pytest

from dazzle.qa.taste_panel import (
    JudgeScore,
    PanelImage,
    aggregate_scores,
    assemble_pool,
    blind_order,
    noise_sd,
    parity_verdict,
)


def _write_manifests(tmp_path: Path) -> tuple[Path, Path]:
    shots = tmp_path / "shots"
    shots.mkdir()
    for name in ("a.png", "b.png", "r.png"):
        (shots / name).write_bytes(b"\x89PNG fake")
    fleet = tmp_path / "fleet.json"
    fleet.write_text(json.dumps({
        "apps": [{
            "app": "ops_dashboard",
            "screens": [
                {"persona": "admin", "workspace": "main", "url": "u",
                 "screenshot": str(shots / "a.png"), "viewport": "desktop", "theme": "light"},
                {"persona": "admin", "workspace": "main", "url": "u",
                 "screenshot": str(shots / "b.png"), "viewport": "desktop", "theme": "dark"},
            ],
        }],
    }))
    refs = tmp_path / "refs.json"
    refs.write_text(json.dumps({
        "captured_at": "2026-07-02T00:00:00+00:00",
        "references": [
            {"name": "shadcn_dashboard", "url": "u", "theme": "light",
             "screenshot": str(shots / "r.png")},
        ],
    }))
    return fleet, refs


def test_assemble_pool_merges_sources_and_tags_theme(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    pool = assemble_pool(fleet, refs)
    assert len(pool) == 3
    sources = sorted(p.source for p in pool)
    assert sources == ["dazzle", "dazzle", "reference"]
    assert {p.theme for p in pool} == {"light", "dark"}
    # image_ids are opaque and unique — no filenames leak to judges
    assert len({p.image_id for p in pool}) == 3
    for p in pool:
        assert "png" not in p.image_id
        assert "shadcn" not in p.image_id and "ops_dashboard" not in p.image_id


def test_assemble_pool_skips_missing_files(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    data = json.loads(fleet.read_text())
    data["apps"][0]["screens"].append(
        {"persona": "x", "workspace": "gone", "url": "u",
         "screenshot": str(tmp_path / "missing.png"), "viewport": "desktop", "theme": "light"}
    )
    fleet.write_text(json.dumps(data))
    pool = assemble_pool(fleet, refs)
    assert len(pool) == 3  # missing file skipped, not crashed


def test_blind_order_is_deterministic_and_shuffled(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    pool = assemble_pool(fleet, refs)
    assert blind_order(pool, seed=7) == blind_order(pool, seed=7)
    assert {p.image_id for p in blind_order(pool, seed=7)} == {p.image_id for p in pool}


def test_aggregate_scores_means_by_source() -> None:
    scores = [
        JudgeScore(image_id="d1", dimension="perceived_craft", score=4, judge=0),
        JudgeScore(image_id="d1", dimension="perceived_craft", score=6, judge=1),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0),
    ]
    sources = {"d1": "dazzle", "r1": "reference"}
    means = aggregate_scores(scores, sources=sources)
    assert means["perceived_craft"]["dazzle"] == pytest.approx(5.0)
    assert means["perceived_craft"]["reference"] == pytest.approx(8.0)


def test_noise_sd_pooled_over_repeats() -> None:
    scores = [
        JudgeScore(image_id="d1", dimension="perceived_craft", score=5, judge=0, repeat=0),
        JudgeScore(image_id="d1", dimension="perceived_craft", score=7, judge=0, repeat=1),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0, repeat=0),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0, repeat=1),
    ]
    sd = noise_sd(scores)
    # d1 sample-SD = sqrt(2), r1 sample-SD = 0 → pooled = sqrt((2+0)/2) = 1.0
    assert sd["perceived_craft"] == pytest.approx(1.0)


def test_parity_verdict_margin_floor_and_gap() -> None:
    means = {"perceived_craft": {"dazzle": 6.4, "reference": 7.0}}
    verdict = parity_verdict(means, {"perceived_craft": 0.1}, floor=0.5)
    v = verdict["perceived_craft"]
    assert v["margin"] == pytest.approx(0.5)      # floor beats 2*0.1
    assert v["gap"] == pytest.approx(0.6)
    assert v["parity"] is False                    # 6.4 < 7.0 - 0.5
    verdict2 = parity_verdict(means, {"perceived_craft": 0.4}, floor=0.5)
    assert verdict2["perceived_craft"]["margin"] == pytest.approx(0.8)
    assert verdict2["perceived_craft"]["parity"] is True   # 6.4 >= 7.0 - 0.8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_taste_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.qa.taste_panel'`

- [ ] **Step 3: Implement the pure layer**

```python
# src/dazzle/qa/taste_panel.py
"""Blind vision-judge taste panel (spec Phase 0).

Assembles a pool of screenshots — Dazzle fleet captures plus dialect
references — strips identity, and scores each image with N independent
vision-LLM judges against ``dazzle.core.taste_rubric``. Judge noise is
measured by repeat-scoring a subset; the parity margin per dimension is
``max(floor, 2 * noise_sd)`` so the gate can never be tighter than the
judges' own repeatability.
"""

from __future__ import annotations

import json
import logging
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "JudgeScore",
    "PanelImage",
    "aggregate_scores",
    "assemble_pool",
    "blind_order",
    "noise_sd",
    "parity_verdict",
]


@dataclass(frozen=True)
class PanelImage:
    """One screenshot in the blind pool. ``label`` is for the report only —
    judges see nothing but pixels and an opaque ``image_id``."""

    image_id: str
    source: str  # "dazzle" | "reference"
    label: str
    path: Path
    theme: str  # "light" | "dark"


@dataclass(frozen=True)
class JudgeScore:
    """One dimension score from one judge pass over one image."""

    image_id: str
    dimension: str
    score: int
    judge: int
    repeat: int = 0


def assemble_pool(fleet_manifest: Path, references_manifest: Path) -> list[PanelImage]:
    """Merge the Dazzle fleet manifest and the references manifest into a pool.

    Missing screenshot files are skipped with a warning. ``image_id`` is an
    opaque ``img-NN`` assigned in merge order — no filename or app name leaks.
    """
    entries: list[tuple[str, str, Path, str]] = []  # (source, label, path, theme)

    fleet = json.loads(fleet_manifest.read_text(encoding="utf-8"))
    for app in fleet.get("apps", []):
        for screen in app.get("screens", []):
            entries.append(
                (
                    "dazzle",
                    f"{app['app']}/{screen['workspace']}/{screen['persona']}",
                    Path(screen["screenshot"]),
                    screen.get("theme", "light"),
                )
            )

    refs = json.loads(references_manifest.read_text(encoding="utf-8"))
    for ref in refs.get("references", []):
        entries.append(
            ("reference", ref["name"], Path(ref["screenshot"]), ref.get("theme", "light"))
        )

    pool: list[PanelImage] = []
    for source, label, path, theme in entries:
        if not path.exists():
            logger.warning("taste-panel: missing screenshot %s (%s) — skipped", path, label)
            continue
        pool.append(
            PanelImage(
                image_id=f"img-{len(pool):02d}",
                source=source,
                label=label,
                path=path,
                theme=theme,
            )
        )
    return pool


def blind_order(pool: list[PanelImage], seed: int) -> list[PanelImage]:
    """Deterministically shuffle the pool so sources interleave."""
    ordered = list(pool)
    random.Random(seed).shuffle(ordered)
    return ordered


def aggregate_scores(
    scores: list[JudgeScore], *, sources: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Mean score per dimension per source: ``{dim: {"dazzle": m, "reference": m}}``.

    Every (judge, repeat) pass contributes equally; *sources* maps
    ``image_id`` → ``"dazzle" | "reference"``.
    """
    buckets: dict[str, dict[str, list[int]]] = {}
    for s in scores:
        source = sources[s.image_id]
        buckets.setdefault(s.dimension, {}).setdefault(source, []).append(s.score)
    return {
        dim: {source: statistics.fmean(vals) for source, vals in by_source.items()}
        for dim, by_source in buckets.items()
    }


def noise_sd(scores: list[JudgeScore]) -> dict[str, float]:
    """Pooled per-dimension sample-SD across repeat passes of the same image.

    Only (image, dimension) groups with >= 2 observations contribute.
    Pooling: sqrt(mean of per-image variances).
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for s in scores:
        groups.setdefault((s.image_id, s.dimension), []).append(s.score)

    variances: dict[str, list[float]] = {}
    for (_, dim), vals in groups.items():
        if len(vals) >= 2:
            variances.setdefault(dim, []).append(statistics.variance(vals))

    return {
        dim: statistics.fmean(vs) ** 0.5 for dim, vs in variances.items()
    }


def parity_verdict(
    means: dict[str, dict[str, float]],
    noise: dict[str, float],
    *,
    floor: float = 0.5,
) -> dict[str, dict[str, float | bool]]:
    """Per-dimension parity: dazzle_mean >= reference_mean - margin.

    ``margin = max(floor, 2 * noise_sd)`` — the gate can never be tighter
    than judge repeatability (spec: "otherwise the gate is theater").
    """
    verdict: dict[str, dict[str, float | bool]] = {}
    for dim, by_source in means.items():
        dazzle = by_source.get("dazzle")
        reference = by_source.get("reference")
        if dazzle is None or reference is None:
            continue
        margin = max(floor, 2.0 * noise.get(dim, 0.0))
        verdict[dim] = {
            "dazzle": round(dazzle, 2),
            "reference": round(reference, 2),
            "margin": round(margin, 2),
            "gap": round(reference - dazzle, 2),
            "parity": dazzle >= reference - margin,
        }
    return verdict
```

Note: `noise_sd` intentionally pools variances via `mean of variances` then square-roots — matches the test's `sqrt((2+0)/2)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_taste_panel.py -v`
Expected: 7 PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/qa/taste_panel.py tests/unit/test_taste_panel.py --fix && ruff format src/dazzle/qa/taste_panel.py tests/unit/test_taste_panel.py
mypy src/dazzle/qa/taste_panel.py
git add src/dazzle/qa/taste_panel.py tests/unit/test_taste_panel.py
git commit -m "feat(taste): blind panel pool assembly, blinding, aggregation, parity math"
```

---

### Task 5: Judge runner (vision LLM calls)

**Files:**
- Modify: `src/dazzle/qa/taste_panel.py` (append)
- Test: `tests/unit/test_taste_judge.py`

**Interfaces:**
- Consumes: `build_judge_prompt` / `dimensions_for_theme` (Task 1), `PanelImage`/`JudgeScore` (Task 4), `DEFAULT_JUDGMENT_MODEL` from `dazzle.core.model_defaults`.
- Produces:
  - `score_image(image: PanelImage, *, judge: int, repeat: int = 0, model: str = DEFAULT_JUDGMENT_MODEL, client: Any | None = None) -> list[JudgeScore]` — one API call, parses strict JSON, 2 retries on parse failure, raises `TastePanelError` after that.
  - `run_panel(pool: list[PanelImage], *, judges: int = 3, noise_runs: int = 2, noise_subset: int = 4, seed: int = 7, model: str = DEFAULT_JUDGMENT_MODEL, client: Any | None = None) -> PanelResult`
  - `PanelResult` dataclass: `scores: list[JudgeScore]`, `means: dict[str, dict[str, float]]`, `noise: dict[str, float]`, `verdict: dict[str, dict[str, float | bool]]`, `pool: list[PanelImage]`
  - `TastePanelError(RuntimeError)`
- The `client` injection point is how tests avoid real API calls; production callers pass `None` and the runner constructs `anthropic.Anthropic()` (env `ANTHROPIC_API_KEY`), following `core/composition_visual.py:306-315`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_taste_judge.py
"""Judge runner — vision call shaping, JSON parsing, retries, panel orchestration."""

import json
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.taste_rubric import dimensions_for_theme
from dazzle.qa.taste_panel import (
    PanelImage,
    TastePanelError,
    run_panel,
    score_image,
)

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcff9fa10e0002d20161e6b1c8be0000000049454e44ae426082"
)


class FakeMessages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]

        class Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class Msg:
            content = [Block(text)]
            usage = type("U", (), {"input_tokens": 1000, "output_tokens": 50})()

        return Msg()


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = FakeMessages(responses)


def _image(tmp_path: Path, theme: str = "light", source: str = "dazzle") -> PanelImage:
    p = tmp_path / f"{theme}.png"
    p.write_bytes(PNG_1PX)
    return PanelImage(image_id=f"img-{theme}", source=source, label="x", path=p, theme=theme)


def _valid_response(theme: str) -> str:
    dims = dimensions_for_theme(theme)
    return json.dumps({"scores": {d.key: 7 for d in dims}, "worst_detail": "flat buttons"})


def test_score_image_parses_scores_for_light_theme(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    client = FakeClient([_valid_response("light")])
    scores = score_image(img, judge=1, client=client)
    assert len(scores) == 5  # dark_mode_integrity excluded for light
    assert {s.dimension for s in scores} == {d.key for d in dimensions_for_theme("light")}
    assert all(s.score == 7 and s.judge == 1 and s.image_id == "img-light" for s in scores)
    # The request contained the image and no identity leak
    call = client.messages.calls[0]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert "x" not in json.dumps(content[1])  # label never sent


def test_score_image_dark_includes_dark_dimension(tmp_path: Path) -> None:
    img = _image(tmp_path, "dark")
    client = FakeClient([_valid_response("dark")])
    scores = score_image(img, judge=0, client=client)
    assert "dark_mode_integrity" in {s.dimension for s in scores}
    assert len(scores) == 6


def test_score_image_retries_then_raises_on_garbage(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    client = FakeClient(["not json", "still not json", "nope"])
    with pytest.raises(TastePanelError):
        score_image(img, judge=0, client=client)
    assert len(client.messages.calls) == 3  # initial + 2 retries


def test_score_image_clamps_out_of_range_scores(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    dims = dimensions_for_theme("light")
    bad = json.dumps({"scores": {d.key: 15 for d in dims}, "worst_detail": ""})
    client = FakeClient([bad])
    scores = score_image(img, judge=0, client=client)
    assert all(s.score == 10 for s in scores)


def test_run_panel_end_to_end_with_fake_client(tmp_path: Path) -> None:
    dz = _image(tmp_path, "light", source="dazzle")
    ref_path = tmp_path / "ref.png"
    ref_path.write_bytes(PNG_1PX)
    ref = PanelImage(image_id="img-ref", source="reference", label="r", path=ref_path, theme="light")
    # Every call returns 7s — enough responses for judges * images + noise repeats
    client = FakeClient([_valid_response("light")] * 50)
    result = run_panel([dz, ref], judges=2, noise_runs=2, noise_subset=2, seed=1, client=client)
    assert result.means["perceived_craft"]["dazzle"] == pytest.approx(7.0)
    assert result.verdict["perceived_craft"]["parity"] is True
    # judges * images = 4 base calls, + noise: subset(2) * (noise_runs) extra
    assert len(client.messages.calls) == 4 + 2 * 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_taste_judge.py -v`
Expected: FAIL with `ImportError: cannot import name 'TastePanelError'`

- [ ] **Step 3: Implement — append to `src/dazzle/qa/taste_panel.py`**

```python
# --- judge runner -----------------------------------------------------------

import base64  # noqa: E402  (module-section import, keep at this seam)

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL  # noqa: E402
from dazzle.core.taste_rubric import build_judge_prompt, dimensions_for_theme  # noqa: E402


class TastePanelError(RuntimeError):
    """A judge returned unusable output after retries."""


@dataclass
class PanelResult:
    """Full output of one panel run."""

    scores: list[JudgeScore]
    means: dict[str, dict[str, float]]
    noise: dict[str, float]
    verdict: dict[str, dict[str, float | bool]]
    pool: list[PanelImage]


def _make_client() -> Any:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - env-dependent
        raise TastePanelError(
            "anthropic package required for the taste panel. "
            "Install with: pip install anthropic"
        ) from e
    return anthropic.Anthropic()


def score_image(
    image: PanelImage,
    *,
    judge: int,
    repeat: int = 0,
    model: str = DEFAULT_JUDGMENT_MODEL,
    client: Any | None = None,
) -> list[JudgeScore]:
    """Score one image across its applicable dimensions with one judge pass.

    Sends ONLY pixels + rubric — no filename, label, or source hint (the
    blindness contract). Retries JSON parsing twice, then raises.
    """
    if client is None:
        client = _make_client()

    dims = dimensions_for_theme(image.theme)
    prompt = build_judge_prompt(dims)
    b64 = base64.standard_b64encode(image.path.read_bytes()).decode("ascii")

    last_error = "no attempts"
    for _attempt in range(3):
        message = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            payload = json.loads(text[start:end])
            raw_scores = payload["scores"]
            return [
                JudgeScore(
                    image_id=image.image_id,
                    dimension=d.key,
                    score=max(1, min(10, int(raw_scores[d.key]))),
                    judge=judge,
                    repeat=repeat,
                )
                for d in dims
            ]
        except (ValueError, KeyError, TypeError) as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "taste-panel: unparseable judge response for %s (attempt %d): %s",
                image.image_id,
                _attempt + 1,
                last_error,
            )
    raise TastePanelError(
        f"Judge {judge} returned unusable output for {image.image_id}: {last_error}"
    )


def run_panel(
    pool: list[PanelImage],
    *,
    judges: int = 3,
    noise_runs: int = 2,
    noise_subset: int = 4,
    seed: int = 7,
    model: str = DEFAULT_JUDGMENT_MODEL,
    client: Any | None = None,
) -> PanelResult:
    """Run the full blind panel: base passes, noise repeats, aggregate, verdict.

    Base: every image scored once per judge (order re-blinded per judge).
    Noise: the first *noise_subset* images of the seed order are re-scored
    *noise_runs* more times by judge 0; repeats feed ``noise_sd`` only after
    being pooled with their base pass (repeat=0).
    """
    if client is None:
        client = _make_client()

    all_scores: list[JudgeScore] = []
    for judge in range(judges):
        for image in blind_order(pool, seed=seed + judge):
            all_scores.extend(
                score_image(image, judge=judge, model=model, client=client)
            )

    subset = blind_order(pool, seed=seed)[:noise_subset]
    for repeat in range(1, noise_runs + 1):
        for image in subset:
            all_scores.extend(
                score_image(image, judge=0, repeat=repeat, model=model, client=client)
            )

    sources = {p.image_id: p.source for p in pool}
    # Noise pools ONLY judge-0 passes of the subset (base + repeats) so
    # inter-judge disagreement doesn't inflate the repeatability estimate.
    subset_ids = {p.image_id for p in subset}
    noise_scores = [
        s for s in all_scores if s.image_id in subset_ids and s.judge == 0
    ]
    means = aggregate_scores(
        [s for s in all_scores if s.repeat == 0], sources=sources
    )
    noise = noise_sd(noise_scores)
    verdict = parity_verdict(means, noise)
    return PanelResult(
        scores=all_scores, means=means, noise=noise, verdict=verdict, pool=pool
    )
```

Also move the `from typing import Any` import to the top of the module (it is now needed): add `from typing import Any` to the existing import block at the head of `taste_panel.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_taste_judge.py tests/unit/test_taste_panel.py -v`
Expected: 12 PASS (the Task 4 tests must still pass).

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/qa/taste_panel.py tests/unit/test_taste_judge.py --fix && ruff format src/dazzle/qa/taste_panel.py tests/unit/test_taste_judge.py
mypy src/dazzle/qa/taste_panel.py
git add src/dazzle/qa/taste_panel.py tests/unit/test_taste_judge.py
git commit -m "feat(taste): vision judge runner — blind scoring, noise repeats, panel orchestration"
```

---

### Task 6: `dazzle qa taste-panel` CLI + report writer

**Files:**
- Modify: `src/dazzle/qa/taste_panel.py` (append `build_report`)
- Modify: `src/dazzle/cli/qa.py` (new command after `qa_capture`, i.e. after line 968)
- Test: `tests/unit/test_taste_report.py`

**Interfaces:**
- Consumes: `PanelResult` (Task 5).
- Produces: `build_report(result: PanelResult) -> tuple[dict[str, Any], str]` — (JSON-serializable dict, markdown). CLI `dazzle qa taste-panel --manifest PATH [--references DIR] [--judges 3] [--noise-runs 2] [--seed 7] [--model M] [--out DIR]` writing `taste-panel.json` + `taste-panel.md` to `--out` (default `.dazzle/qa/taste/`). Exit code 0 if every dimension has parity, 1 otherwise (so the gate is scriptable).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_taste_report.py
"""Taste panel report builder."""

from pathlib import Path

from dazzle.qa.taste_panel import JudgeScore, PanelImage, PanelResult, build_report


def _result() -> PanelResult:
    pool = [
        PanelImage(image_id="img-00", source="dazzle", label="ops_dashboard/main/admin",
                   path=Path("/tmp/a.png"), theme="light"),
        PanelImage(image_id="img-01", source="reference", label="shadcn_dashboard",
                   path=Path("/tmp/r.png"), theme="light"),
    ]
    return PanelResult(
        scores=[JudgeScore("img-00", "perceived_craft", 5, 0)],
        means={"perceived_craft": {"dazzle": 5.0, "reference": 8.0}},
        noise={"perceived_craft": 0.3},
        verdict={"perceived_craft": {
            "dazzle": 5.0, "reference": 8.0, "margin": 0.6, "gap": 3.0, "parity": False,
        }},
        pool=pool,
    )


def test_build_report_json_shape() -> None:
    data, md = build_report(_result())
    assert data["parity"] is False
    assert data["verdict"]["perceived_craft"]["gap"] == 3.0
    assert data["pool"][0]["label"] == "ops_dashboard/main/admin"
    assert data["counts"] == {"dazzle": 1, "reference": 1}


def test_build_report_markdown_contains_verdict_table() -> None:
    data, md = build_report(_result())
    assert "# Taste Panel" in md
    assert "perceived_craft" in md
    assert "FAIL" in md  # parity=False renders as FAIL
    assert "5.0" in md and "8.0" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_taste_report.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_report'`

- [ ] **Step 3: Implement — append to `taste_panel.py`**

```python
# --- report -----------------------------------------------------------------


def build_report(result: PanelResult) -> tuple[dict[str, Any], str]:
    """Build the (json_dict, markdown) pair for a panel run."""
    overall = bool(result.verdict) and all(
        v["parity"] for v in result.verdict.values()
    )
    counts = {
        "dazzle": sum(1 for p in result.pool if p.source == "dazzle"),
        "reference": sum(1 for p in result.pool if p.source == "reference"),
    }
    data: dict[str, Any] = {
        "parity": overall,
        "counts": counts,
        "means": result.means,
        "noise_sd": result.noise,
        "verdict": result.verdict,
        "pool": [
            {
                "image_id": p.image_id,
                "source": p.source,
                "label": p.label,
                "theme": p.theme,
                "path": str(p.path),
            }
            for p in result.pool
        ],
        "scores": [
            {
                "image_id": s.image_id,
                "dimension": s.dimension,
                "score": s.score,
                "judge": s.judge,
                "repeat": s.repeat,
            }
            for s in result.scores
        ],
    }

    lines = [
        "# Taste Panel",
        "",
        f"**Overall parity: {'PASS' if overall else 'FAIL'}** "
        f"({counts['dazzle']} dazzle screens vs {counts['reference']} references)",
        "",
        "| Dimension | Dazzle | Reference | Gap | Margin | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for dim, v in sorted(result.verdict.items()):
        lines.append(
            f"| {dim} | {v['dazzle']} | {v['reference']} | {v['gap']} "
            f"| {v['margin']} | {'PASS' if v['parity'] else 'FAIL'} |"
        )
    lines += [
        "",
        "Margin = max(0.5, 2 × judge noise SD) per dimension. "
        "Parity = dazzle mean ≥ reference mean − margin.",
        "",
    ]
    return data, "\n".join(lines)
```

- [ ] **Step 4: Add the CLI command — insert in `src/dazzle/cli/qa.py` after `qa_capture` (line 968)**

```python
@qa_app.command("taste-panel")
def qa_taste_panel(
    manifest: Path = typer.Option(
        ..., "--manifest", "-m", help="Fleet manifest from `dazzle qa capture --manifest`"
    ),
    references: Path = typer.Option(
        Path(".dazzle/composition/references/taste/references_manifest.json"),
        "--references",
        help="References manifest from scripts/taste/capture_references.py",
    ),
    judges: int = typer.Option(3, "--judges", help="Independent judge passes per image"),
    noise_runs: int = typer.Option(2, "--noise-runs", help="Repeat passes for noise SD"),
    seed: int = typer.Option(7, "--seed", help="Blinding shuffle seed"),
    model: str | None = typer.Option(None, "--model", help="Override judge model"),
    out: Path = typer.Option(Path(".dazzle/qa/taste"), "--out", help="Report output dir"),
) -> None:
    """Run the blind taste panel: Dazzle fleet vs dialect references."""
    from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
    from dazzle.qa.taste_panel import assemble_pool, build_report, run_panel

    if not manifest.exists():
        typer.echo(f"Fleet manifest not found: {manifest}", err=True)
        raise typer.Exit(code=2)
    if not references.exists():
        typer.echo(
            f"References manifest not found: {references}\n"
            "Run: python scripts/taste/capture_references.py",
            err=True,
        )
        raise typer.Exit(code=2)

    pool = assemble_pool(manifest, references)
    dazzle_n = sum(1 for p in pool if p.source == "dazzle")
    ref_n = len(pool) - dazzle_n
    if not dazzle_n or not ref_n:
        typer.echo(f"Pool needs both sources (dazzle={dazzle_n}, reference={ref_n}).", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Panel: {len(pool)} images ({dazzle_n} dazzle, {ref_n} reference), {judges} judges…")
    result = run_panel(
        pool,
        judges=judges,
        noise_runs=noise_runs,
        seed=seed,
        model=model or DEFAULT_JUDGMENT_MODEL,
    )
    data, md = build_report(result)

    out.mkdir(parents=True, exist_ok=True)
    (out / "taste-panel.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (out / "taste-panel.md").write_text(md, encoding="utf-8")
    typer.echo(md)
    typer.echo(f"Reports: {out / 'taste-panel.json'}, {out / 'taste-panel.md'}")
    raise typer.Exit(code=0 if data["parity"] else 1)
```

(`json`, `Path`, `typer` are already imported at the top of `cli/qa.py`; verify and add any missing.)

- [ ] **Step 5: Run tests + CLI help**

Run: `pytest tests/unit/test_taste_report.py -v` — Expected: 2 PASS
Run: `dazzle qa taste-panel --help` — Expected: options render, no import errors.

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/dazzle/qa/taste_panel.py src/dazzle/cli/qa.py tests/unit/test_taste_report.py --fix && ruff format src/dazzle/qa/taste_panel.py src/dazzle/cli/qa.py tests/unit/test_taste_report.py
mypy src/dazzle
git add src/dazzle/qa/taste_panel.py src/dazzle/cli/qa.py tests/unit/test_taste_report.py
git commit -m "feat(qa): dazzle qa taste-panel — blind parity gate CLI with scriptable exit code"
```

---

### Task 7: Opt-in taste focus in `composition analyze`

**Files:**
- Modify: `src/dazzle/core/composition_visual.py` (DIMENSIONS block at ~line 57, prompt construction)
- Modify: `src/dazzle/mcp/server/handlers/composition.py` (`analyze_composition_handler` focus validation, line 174)
- Test: `tests/unit/test_composition_taste_focus.py`

**Interfaces:**
- Consumes: `TASTE_DIMENSIONS`, `build_judge_prompt` from `dazzle.core.taste_rubric` (Task 1 — core→core import, layer-clean).
- Produces: `TASTE_FOCUS_KEYS: list[str]` in `composition_visual` (the 6 rubric keys); `focus=["taste"]` or any individual rubric key accepted by `analyze`/`report`. Taste dimensions are NEVER in the default `DIMENSIONS` run — strictly opt-in (token cost, spec §gates).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_composition_taste_focus.py
"""Opt-in taste dimensions in the composition visual pipeline."""

from dazzle.core.composition_visual import (
    DIMENSIONS,
    TASTE_FOCUS_KEYS,
    resolve_focus_dimensions,
)
from dazzle.core.taste_rubric import TASTE_DIMENSIONS


def test_taste_keys_mirror_rubric_and_stay_out_of_defaults() -> None:
    assert TASTE_FOCUS_KEYS == [d.key for d in TASTE_DIMENSIONS]
    assert not set(TASTE_FOCUS_KEYS) & set(DIMENSIONS)


def test_resolve_focus_default_is_standard_dimensions() -> None:
    assert resolve_focus_dimensions(None) == list(DIMENSIONS)


def test_resolve_focus_taste_shorthand_expands() -> None:
    assert resolve_focus_dimensions(["taste"]) == TASTE_FOCUS_KEYS


def test_resolve_focus_mixed_and_invalid() -> None:
    got = resolve_focus_dimensions(["layout_overflow", "perceived_craft", "bogus"])
    assert got == ["layout_overflow", "perceived_craft"]
    assert resolve_focus_dimensions(["bogus"]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_composition_taste_focus.py -v`
Expected: FAIL with `ImportError: cannot import name 'TASTE_FOCUS_KEYS'`

- [ ] **Step 3: Implement**

In `src/dazzle/core/composition_visual.py`, after the `DIMENSIONS` list (line ~65), add:

```python
# Opt-in taste dimensions (spec: docs/superpowers/specs/
# 2026-07-02-taste-house-aesthetic-design.md). Never run by default —
# they cost LLM tokens and exist for explicit focus=["taste"] audits.
from .taste_rubric import TASTE_DIMENSIONS as _TASTE_DIMENSIONS

TASTE_FOCUS_KEYS: list[str] = [d.key for d in _TASTE_DIMENSIONS]

# Taste dimensions use standard full-color screenshots.
DIMENSION_PREPROCESSING.update(dict.fromkeys(TASTE_FOCUS_KEYS))


def resolve_focus_dimensions(focus: list[str] | None) -> list[str]:
    """Expand a focus request into concrete dimension keys.

    ``None`` → the standard DIMENSIONS. ``"taste"`` expands to all six
    rubric keys. Unknown names are dropped. Taste keys never run unless
    explicitly requested.
    """
    if focus is None:
        return list(DIMENSIONS)
    valid = set(DIMENSIONS) | set(TASTE_FOCUS_KEYS)
    expanded: list[str] = []
    for f in focus:
        if f == "taste":
            expanded.extend(TASTE_FOCUS_KEYS)
        elif f in valid:
            expanded.append(f)
    return expanded
```

Then find where each dimension's prompt is built inside `evaluate_captures`/its helpers (the per-dimension prompt selection around the `DIMENSIONS` dispatch — read the surrounding code first). For taste keys, source the prompt from the rubric:

```python
        from .taste_rubric import TASTE_DIMENSIONS, build_judge_prompt

        _taste_by_key = {d.key: d for d in TASTE_DIMENSIONS}
        if dimension in _taste_by_key:
            prompt = build_judge_prompt([_taste_by_key[dimension]])
```

In `src/dazzle/mcp/server/handlers/composition.py::analyze_composition_handler`, replace the focus filter (lines 172–178):

```python
    dimensions: list[str] | None = None
    if focus:
        from dazzle.core.composition_visual import resolve_focus_dimensions

        dimensions = resolve_focus_dimensions(focus)
        if not dimensions:
            return json.dumps(
                {
                    "error": (
                        f"No valid dimensions in focus: {focus}. "
                        f"Valid: {DIMENSIONS} or 'taste'"
                    )
                }
            )
```

Apply the same `resolve_focus_dimensions` swap in `_run_visual_pipeline` (line 441-443).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_composition_taste_focus.py tests/unit -k "composition" -q`
Expected: new tests PASS; existing composition tests still PASS.

- [ ] **Step 5: MCP surface check + commit**

The `composition` tool's op list is unchanged (no drift-gate impact — `focus` is an existing arg), but run the docs drift test to be sure: `pytest tests/unit/test_docs_drift.py -q` — PASS.

```bash
ruff check src/dazzle/core/composition_visual.py src/dazzle/mcp/server/handlers/composition.py tests/unit/test_composition_taste_focus.py --fix && ruff format src/dazzle/core/composition_visual.py src/dazzle/mcp/server/handlers/composition.py tests/unit/test_composition_taste_focus.py
mypy src/dazzle
git add src/dazzle/core/composition_visual.py src/dazzle/mcp/server/handlers/composition.py tests/unit/test_composition_taste_focus.py
git commit -m "feat(composition): opt-in taste focus — rubric dimensions in analyze/report"
```

---

### Task 8: Baseline run (real captures, real judges) — the "before" record

This task is procedural (operator work driving the tools built above); its gate is the committed baseline artifacts.

**Files:**
- Create: `dev_docs/taste/baseline-2026-07-02.md` (committed)
- Create: `dev_docs/taste/baseline-2026-07-02.json` (committed)

**Interfaces:**
- Consumes: everything from Tasks 2–6.
- Produces: the committed baseline + the measured parity margin per dimension, referenced by `taste.md` (Task 9) and by the Phase 2–4 plans.

- [ ] **Step 1: Capture references for real**

```bash
python scripts/taste/capture_references.py
```
Expected: ≥ 12 PNGs (8 targets, most with 2 themes) + `references_manifest.json`. Visually spot-check 2–3 PNGs (no cookie walls, no blank pages). If a target fails (site changed), note it and proceed — 10+ references is plenty.

- [ ] **Step 2: Capture the Dazzle fleet (light + dark, above-fold desktop)**

For each of the 12 examples (`simple_task contact_manager support_tickets ops_dashboard fieldtest_hub project_tracker design_studio llm_ticket_classifier acme_billing hr_records invoice_ops domain_join_co`):

```bash
dazzle e2e env start <app>       # note the printed URL, e.g. http://localhost:8981
dazzle qa capture --app <app> --url <URL> --above-fold --manifest .dazzle/qa/taste/fleet.json
dazzle qa capture --app <app> --url <URL> --above-fold --dark --manifest .dazzle/qa/taste/fleet.json
# stop the env before the next app (dazzle e2e env stop, or Ctrl-C the process)
```

CAUTION — `write_manifest` replaces an app's entry wholesale per call, so the `--dark` call would clobber the light screens. Check `write_manifest` behavior first; if it replaces, capture light+dark in one manifest by running the dark capture with `--manifest .dazzle/qa/taste/fleet-dark.json` and merging:

```bash
python - <<'EOF'
import json, pathlib
light = json.loads(pathlib.Path(".dazzle/qa/taste/fleet.json").read_text())
dark = json.loads(pathlib.Path(".dazzle/qa/taste/fleet-dark.json").read_text())
by_app = {a["app"]: a for a in light["apps"]}
for a in dark["apps"]:
    by_app.setdefault(a["app"], {"app": a["app"], "screens": []})["screens"].extend(a["screens"])
light["apps"] = list(by_app.values())
pathlib.Path(".dazzle/qa/taste/fleet.json").write_text(json.dumps(light, indent=2))
EOF
```

(Better: if this bites, file a small follow-up to add `--merge` to qa capture; do not expand scope here.)

To keep the panel affordable, limit to ≤ 3 screens per app per theme (pick the primary personas — use `--persona` if an app has many). Target ≈ 60 Dazzle images total.

- [ ] **Step 3: Run the panel**

```bash
export ANTHROPIC_API_KEY=...   # if not already set
dazzle qa taste-panel --manifest .dazzle/qa/taste/fleet.json --judges 3 --noise-runs 2
```
Expected: markdown verdict table on stdout; exit code 1 (we expect FAIL today — that is the point of a baseline). Sanity-check the noise SD values: if any dimension's noise SD > 1.5, judges are too erratic — raise `--judges` to 5 and re-run before trusting the margin.

- [ ] **Step 4: Commit the baseline**

```bash
mkdir -p dev_docs/taste
cp .dazzle/qa/taste/taste-panel.json dev_docs/taste/baseline-2026-07-02.json
cp .dazzle/qa/taste/taste-panel.md dev_docs/taste/baseline-2026-07-02.md
```

Append to `dev_docs/taste/baseline-2026-07-02.md` a short "Reading the baseline" section written by hand: the 3 widest-gap dimensions, the 2 worst-scoring example apps, judge noise per dimension, and the locked parity margins. These observations feed the TASTE-n rules in Task 9 and the Phase 2 plan.

```bash
git add dev_docs/taste/
git commit -m "docs(taste): baseline 2026-07-02 — fleet vs dialect references, parity margins locked"
```

---

### Task 9: `docs/reference/taste.md` + drift gate + ship

**Files:**
- Create: `docs/reference/taste.md`
- Test: `tests/unit/test_taste_doc_drift.py`
- Modify: `CHANGELOG.md`, `.claude/CLAUDE.md` (one pointer line in UI Invariants section)

**Interfaces:**
- Consumes: `TASTE_DIMENSIONS` (Task 1), baseline findings (Task 8).
- Produces: the canonical taste artifact; drift gate asserting doc ↔ rubric consistency.

- [ ] **Step 1: Write the failing drift test**

```python
# tests/unit/test_taste_doc_drift.py
"""docs/reference/taste.md must list exactly the live rubric dimensions."""

import re
from pathlib import Path

from dazzle.core.taste_rubric import TASTE_DIMENSIONS

DOC = Path(__file__).parents[2] / "docs" / "reference" / "taste.md"


def test_taste_doc_exists() -> None:
    assert DOC.exists(), "docs/reference/taste.md is the canonical taste artifact"


def test_taste_doc_lists_every_rubric_dimension_exactly() -> None:
    text = DOC.read_text(encoding="utf-8")
    # Rubric section rows: | `key` | ... |
    doc_keys = re.findall(r"^\| `([a-z_]+)` \|", text, flags=re.MULTILINE)
    assert doc_keys == [d.key for d in TASTE_DIMENSIONS]


def test_taste_doc_has_principles_and_rules() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Principles" in text and "## Rules" in text and "## Rubric" in text
    # Rules are numbered TASTE-n and at least 8 exist
    rules = re.findall(r"\*\*TASTE-(\d+)\*\*", text)
    assert len(rules) >= 8
    assert rules == [str(i) for i in range(1, len(rules) + 1)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_taste_doc_drift.py -v`
Expected: FAIL — doc missing.

- [ ] **Step 3: Write `docs/reference/taste.md`**

Structure (author the full prose during execution — principles are fixed by the spec; rules MUST cite baseline evidence from Task 8 where available):

```markdown
# HaTchi-MaXchi — the Dazzle House Aesthetic

Canonical, agent-readable definition of Dazzle's visual taste — the
**HaTchi-MaXchi** style (pronounced "hachi machi"; the capitals spell its
HTMX substrate).
Consumed by: framework CSS/token authors (now), the authoring agent and
the improve loop (follow-ons). Enforced by: the blind taste panel
(`dazzle qa taste-panel`), opt-in `composition analyze` taste focus, and
the gates listed per rule. Spec:
`docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md`.
Baseline: `dev_docs/taste/baseline-2026-07-02.md`.

## Principles

[The nine principles from the spec, verbatim headers + one paragraph each:
1 Semantic surface, expressive result · 2 Type does the hierarchy ·
3 One accent; neutrals do the work · 4 Depth is information ·
5 Motion confirms, never entertains · 6 Dark is a material, not an
inversion · 7 Density with rhythm · 8 Every state is designed ·
9 The structure is the style (the HaTchi-MaXchi signature: HTMX4 anatomy —
swap targets, hx-indicator lifecycle, boosted navigation — IS the design
material; motion/loading language derives from the htmx request lifecycle)]

## Rules

[Numbered **TASTE-1** … **TASTE-n** (≥ 8). Each rule: one-sentence
statement, the principle it serves, the baseline evidence that motivated
it, and its enforcement (a gate, the panel dimension it moves, or
"advisory until Phase 2/3"). Written during execution against the Task 8
baseline — e.g. if typographic_hierarchy shows the widest gap, TASTE-1..3
are type-scale rules with the gap numbers cited.]

## Rubric

The judged dimensions live in `src/dazzle/core/taste_rubric.py`
(single source of truth; this table is drift-gated by
`tests/unit/test_taste_doc_drift.py`).

| Key | Title | Applies to |
|---|---|---|
| `typographic_hierarchy` | Typographic hierarchy | both |
| `spatial_rhythm` | Spatial rhythm | both |
| `color_discipline` | Color discipline | both |
| `state_completeness` | State completeness | both |
| `dark_mode_integrity` | Dark-mode integrity | dark |
| `perceived_craft` | Perceived craft | both |

## The parity gate

How to run the panel, what the margins are (from the baseline), and the
stop condition for Phases 2–4.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_taste_doc_drift.py -v`
Expected: 3 PASS

- [ ] **Step 5: Cross-link + CHANGELOG + ship**

Add one line to `.claude/CLAUDE.md` under **UI Invariants**:

```markdown
- **Taste**: the house aesthetic is defined in `docs/reference/taste.md` (principles → TASTE-n rules → judged rubric). The blind parity gate is `dazzle qa taste-panel`; rubric source of truth is `src/dazzle/core/taste_rubric.py` (drift-gated).
```

CHANGELOG entry under the next version, including an `### Agent Guidance` bullet: "Before styling work in framework CSS, read `docs/reference/taste.md`; run `dazzle qa taste-panel` to judge changes against the dialect references."

```bash
pytest -n auto --dist loadgroup -m "not e2e" tests/   # FULL suite — no -k
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
```
Expected: all green. Then bump + ship per house discipline (`/bump patch`, commit, push, verify clean worktree).

- [ ] **Step 6: Hand off to Phase 2 planning**

Phases 2–4 get their own plans, written against the baseline evidence (this was locked in the spec's oracle-first architecture). Open the next planning session with: spec + `docs/reference/taste.md` + `dev_docs/taste/baseline-2026-07-02.md`.

---

## Execution notes

- Tasks 1–7 are independent of any live app or API key (all LLM calls mocked); Task 8 needs a real `ANTHROPIC_API_KEY`, Playwright chromium, and ~30–60 min of app boots; budget roughly 200–400k judge tokens for the full fleet panel.
- Task 3 renames capture output files — grep `tests/` for `"_admin.png"`-style assumptions before assuming the qa selection covers everything: `grep -rn "workspace}_{" tests/ src/dazzle` and `grep -rn "_desktop_light" tests/`.
- Order: 1 → (2, 3 in either order) → 4 → 5 → 6 → 7 → 8 → 9. Task 7 can run any time after 1.
