# HM Icon System + Gallery Pedagogy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HM a canonical `.dz-icon` contract + a11y/fail-loud rigor, and make the Pages gallery teach icons via clean sprite-`<use>` snippets backed by one injected symbol sheet.

**Architecture:** Inline SVG stays the substrate (registry → inline `<svg>`). We (1) enrich the *existing* `.dz-icon` base contract, (2) add an accessibility escape hatch + build-time fail-loud on unknown names, (3) generate a `<symbol>` sprite sheet from the same registry and add a `sprite` render mode, and (4) rework the gallery so component snippets show `<svg class="icon"><use href="#name"/></svg>` with one hidden sheet injected into the layout, plus a dedicated Icon Hyperpart page. Dazzle's server render stays inline (sprite adoption there is a follow-on).

**Tech Stack:** Python 3.12 (stdlib only in the HM package), CSS cascade layers, static-site build (`packages/hatchi-maxchi/site/build_site.py`), pytest gates.

## Global Constraints

- **HM package is stdlib-only** — no third-party imports in `packages/hatchi-maxchi/`.
- **HM never imports `dazzle.*`** (gated: `packages/hatchi-maxchi/tests/test_boundary.py`).
- **Source CSS is authored WITH the `dz-` prefix.** `build_css("")` strips it (gallery = unprefixed `.icon`); `build_css("dz-")` keeps it (Dazzle = `.dz-icon`). Never hand-strip.
- **Keep `--size-sm/md/lg` names** — `src/dazzle/render/fragment/renderer/_render_layout.py:229` emits `dz-icon dz-icon--size-{i.size}`. Add `xs`/`xl`, never rename.
- **Registry is the single source** — `packages/hatchi-maxchi/icons/registry.py`; regenerate via `icons/gen_registry.py`, never hand-edit (`# AUTO-GENERATED`). Vendored twin `src/dazzle/render/fragment/icon_registry.py` stays byte-identical (gated: `tests/unit/test_icon_registry_drift.py`).
- **Rebuild committed artifacts** after any CSS/gallery change: `packages/hatchi-maxchi/dist/` and the committed gallery CSS/JS (gated: `test_contract.py::test_committed_dist_is_current`, `::test_committed_gallery_css_is_current`, `::test_gallery_regenerates_byte_identically`). On the Dazzle side rebuild `dist` via `scripts/build_dist.py` when the ingested bundle changes.
- **Ship discipline** — `/bump patch` + push per shippable phase; leave `git status` clean (commit rebuilt `dist/`).
- **Test command** — package: `pytest packages/hatchi-maxchi/tests/ -q`. Dazzle: `pytest -n auto --dist loadgroup -m "not e2e"`.

---

## Phase 1 — `.dz-icon` base contract (CSS-only, shippable alone)

Enrich the existing `.dz-icon` primitive into the full contract the Icon page will teach. Pure CSS; every existing icon still renders (context classes keep their explicit sizes). Value: one canonical base, `xs`/`xl`/`-solid` added, `currentColor`/`fill:none` centralized.

### Task 1: Extend the `.dz-icon` base + sizes + solid

**Files:**
- Modify: `packages/hatchi-maxchi/components/fragment-primitives.css:613-639`
- Test: `packages/hatchi-maxchi/tests/test_icon_contract.py` (create)

**Interfaces:**
- Produces: CSS classes `.dz-icon` (base), `.dz-icon--size-xs|sm|md|lg|xl`, `.dz-icon-solid`. Gallery-published (stripped) names: `.icon`, `.icon--size-*`, `.icon-solid`.

- [ ] **Step 1: Write the failing test** — assert the contract exists in the built CSS.

```python
# packages/hatchi-maxchi/tests/test_icon_contract.py
"""The .dz-icon base contract (Phase 1 of the icon-system plan)."""
import re
from pathlib import Path
import pytest
from build import build_css  # packages/hatchi-maxchi/ is on sys.path in the package test env

pytestmark = pytest.mark.gate


def _css(prefix: str = "dz-") -> str:
    return build_css(prefix)


def test_dz_icon_base_declares_the_full_contract():
    css = _css("dz-")
    # the base rule block for `.dz-icon` must carry the sizing+colour contract
    block = re.search(r"\.dz-icon\b[^{]*\{([^}]*)\}", css)
    assert block, ".dz-icon base rule missing"
    body = block.group(1)
    for decl in ("width: 1em", "height: 1em", "vertical-align: -0.125em",
                 "flex-shrink: 0", "stroke: currentColor", "fill: none"):
        assert decl in body, f".dz-icon base missing `{decl}`"


def test_dz_icon_size_scale_is_complete():
    css = _css("dz-")
    for size in ("xs", "sm", "md", "lg", "xl"):
        assert f".dz-icon--size-{size}" in css, f"missing .dz-icon--size-{size}"


def test_dz_icon_solid_variant_exists():
    assert ".dz-icon-solid" in _css("dz-")


def test_gallery_publishes_unprefixed_icon_contract():
    css = _css("")  # gallery default: dz- stripped
    assert ".icon--size-xl" in css and ".icon-solid" in css
    assert ".dz-icon" not in css  # fully stripped
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q`
Expected: FAIL (base lacks `width:1em`/`stroke:currentColor`; no `xs`/`xl`/`-solid`).

- [ ] **Step 3: Rewrite the `.dz-icon` block** at `fragment-primitives.css:613-639`. Replace the existing `.dz-icon,`/`.dz-icon--size-*`/`.dz-icon svg` rules with:

```css
/* Canonical icon contract — see the Icon Hyperpart page. Sized in `em` so an
   icon scales with its context's font-size; sizes below pin absolute sizes. */
.dz-icon,
.dz-task-inbox-item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  vertical-align: -0.125em;
  width: 1em;
  height: 1em;
  color: inherit;
  stroke: currentColor;
  fill: none;
}
.dz-icon-solid { fill: currentColor; stroke: none; }
.dz-icon--size-xs { width: 0.75rem;  height: 0.75rem;  }
.dz-icon--size-sm { width: 1rem;     height: 1rem;     }
.dz-icon--size-md { width: 1.25rem;  height: 1.25rem;  }
.dz-icon--size-lg { width: 1.5rem;   height: 1.5rem;   }
.dz-icon--size-xl { width: 2rem;     height: 2rem;     }
.dz-icon svg,
.dz-action-card-icon svg,
.dz-status-list-icon svg,
.dz-task-inbox-item-icon svg {
  width: 100%;
  height: 100%;
  display: block;
}
```

Note: `.dz-task-inbox-item-icon` keeps its own `width/height` rule at 622-626 (overrides the `1em` base) — leave that block untouched.

- [ ] **Step 4: Run to verify it passes**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Rebuild committed artifacts + full package suite**

Run:
```bash
cd packages/hatchi-maxchi
python build.py            # rebuild dist/
python site/build_site.py  # rebuild committed gallery css/js
python -m pytest tests/ -q
```
Expected: PASS (incl. `test_committed_dist_is_current`, `test_committed_gallery_css_is_current`).

- [ ] **Step 6: Verify Dazzle ingest + no visual regression**

Run: `cd /Volumes/SSD/Dazzle && python scripts/build_dist.py && pytest tests/unit/test_hm_boundary.py tests/unit/test_icon_inline_svg.py -q`
Expected: PASS (`.dz-icon` still present post-ingest; sized icons unchanged since `sm/md/lg` preserved).

- [ ] **Step 7: Commit**

```bash
git add packages/hatchi-maxchi/components/fragment-primitives.css packages/hatchi-maxchi/tests/test_icon_contract.py packages/hatchi-maxchi/dist packages/hatchi-maxchi/site src/dazzle/page/runtime/static
git commit -m "feat(taste): canonical .dz-icon contract — 1em base, xs/xl sizes, -solid"
```

**CHECKPOINT — visual review:** boot a demo app (`examples/ops_dashboard`) and eyeball nav/badge/empty-state/table icons at parity. `/bump patch` + push.

---

## Phase 2 — accessibility escape hatch + build-time fail-loud (shippable alone)

Add a `label` option (meaningful icons) to the helpers, and make **unknown icon names fail loud at gallery build time** and via a gate — *without* touching Dazzle's runtime `data-lucide` client fallback (that stays an intentional grow-the-registry path).

### Task 2: `label` a11y option on the HM + Dazzle helpers

**Files:**
- Modify: `packages/hatchi-maxchi/icons/html.py:32-41` (`lucide_svg_html`) and `:21-29` (`lucide_icon_html`)
- Modify (mirror, byte-identical logic): `src/dazzle/render/fragment/icon_html.py`
- Test: `packages/hatchi-maxchi/tests/test_icon_contract.py` (extend); `tests/unit/test_icon_inline_svg.py` (extend)

**Interfaces:**
- Consumes: registry `ICONS`.
- Produces: `lucide_svg_html(name, *, cls, fallback="inbox", label=None)` and `lucide_icon_html(name, *, cls, label=None)`. `label=None` → `aria-hidden="true"` (unchanged default). `label="X"` → `role="img" aria-label="X"`, no `aria-hidden`.

- [ ] **Step 1: Write the failing test**

```python
# append to packages/hatchi-maxchi/tests/test_icon_contract.py
from icons.html import lucide_svg_html, lucide_icon_html


def test_decorative_default_is_aria_hidden():
    out = lucide_svg_html("check", cls="dz-icon")
    assert 'aria-hidden="true"' in out and "role=" not in out


def test_label_makes_icon_meaningful():
    out = lucide_svg_html("trash-2", cls="dz-icon", label="Delete")
    assert 'role="img"' in out and 'aria-label="Delete"' in out
    assert "aria-hidden" not in out


def test_label_escapes():
    out = lucide_svg_html("check", cls="dz-icon", label='a"b')
    assert 'aria-label="a&quot;b"' in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q -k label or aria`
Expected: FAIL (`label` is not a parameter).

- [ ] **Step 3: Implement** — replace the two functions in `packages/hatchi-maxchi/icons/html.py`:

```python
def _a11y_attrs(label: str | None) -> str:
    if label is None:
        return ' aria-hidden="true"'
    return f' role="img" aria-label="{_html.escape(label, quote=True)}"'


def lucide_svg_html(name: str, *, cls: str, fallback: str = "inbox", label: str | None = None) -> str:
    """Bare ``<svg>`` for a registry name. Decorative by default; pass *label*
    to expose an accessible name (``role=img``)."""
    inner = ICONS.get(name) or ICONS[fallback]
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<svg{cls_attr} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round"{_a11y_attrs(label)}>{inner}</svg>'
    )


def lucide_icon_html(name: str, *, cls: str, label: str | None = None) -> str:
    """Icon *name* inside a ``<span class=cls>``. Decorative by default."""
    inner = ICONS.get(name)
    a11y = _a11y_attrs(label)
    if inner is not None:
        return f'<span class="{cls}"{a11y}>{_SVG_SHELL.format(inner=inner)}</span>'
    return f'<span class="{cls}" data-lucide="{_html.escape(name, quote=True)}"{a11y}></span>'
```

- [ ] **Step 4: Mirror into Dazzle** — apply the identical change to `src/dazzle/render/fragment/icon_html.py` (same `_a11y_attrs`, same two signatures). Keep the docstrings' Dazzle-specific wording.

- [ ] **Step 5: Run both suites**

Run:
```bash
cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q
cd /Volumes/SSD/Dazzle && pytest tests/unit/test_icon_inline_svg.py tests/unit/test_badge_wcag_icon_1493.py -q
```
Expected: PASS (existing decorative callers unchanged; `aria-hidden` default preserved).

- [ ] **Step 6: Commit**

```bash
git add packages/hatchi-maxchi/icons/html.py src/dazzle/render/fragment/icon_html.py packages/hatchi-maxchi/tests/test_icon_contract.py
git commit -m "feat(taste): icon label option — role=img/aria-label for meaningful icons"
```

### Task 3: Fail loud on unknown icon names (build-time + gate)

**Files:**
- Modify: `packages/hatchi-maxchi/site/build_site.py:41-96` (token expansion → raise on unknown)
- Test: `packages/hatchi-maxchi/tests/test_icon_contract.py` (extend); reuse Dazzle `tests/unit/test_nav_icons.py` pattern.

**Interfaces:**
- Produces: gallery build raises `KeyError`/`ValueError` naming an unknown `{icon:...}`/`{svg:...}` token instead of silently substituting `inbox`.

- [ ] **Step 1: Write the failing test**

```python
# append to packages/hatchi-maxchi/tests/test_icon_contract.py
import pytest as _pytest
from site.build_site import expand_icons  # adjust import to the actual module path


def test_unknown_icon_token_fails_loud():
    with _pytest.raises((KeyError, ValueError)) as exc:
        expand_icons('<i>{svg:definitely-not-an-icon}</i>')
    assert "definitely-not-an-icon" in str(exc.value)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q -k unknown_icon_token`
Expected: FAIL (currently substitutes `inbox` silently).

- [ ] **Step 3: Implement** — in `build_site.py`, before expansion, validate the token name against `ICONS` and raise a clear error:

```python
def _require(name: str) -> str:
    if name not in ICONS:
        raise ValueError(f"unknown icon token '{name}' — add it via icons/gen_registry.py")
    return name

# in the _ICON_RE / _SVG_RE substitutions, call _require(m.group(1)) first:
markup = _ICON_RE.sub(lambda m: lucide_icon_html(_require(m.group(1)), cls="dz-icon dz-icon--size-sm"), markup)
markup = _SVG_RE.sub(lambda m: lucide_svg_html(_require(m.group(1)), cls=""), markup)
```

- [ ] **Step 4: Run to verify it passes + full build still green**

Run:
```bash
cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q && python site/build_site.py
```
Expected: test PASS; build succeeds (all existing tokens are valid names).

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/site/build_site.py packages/hatchi-maxchi/tests/test_icon_contract.py
git commit -m "feat(taste): gallery build fails loud on unknown icon token"
```

**CHECKPOINT.** `/bump patch` + push. (Dazzle runtime `data-lucide` fallback deliberately unchanged — noted in Non-goals.)

---

## Phase 3 — sprite sheet generation + `sprite` render mode

Emit a `<symbol>` sheet from the registry and add a sprite renderer. Nothing consumes it yet (Phase 4 does), so this ships as pure capability.

### Task 4: Generate the symbol sheet from the registry

**Files:**
- Modify: `packages/hatchi-maxchi/icons/gen_registry.py` (add sheet emission to `write_outputs()`)
- Create: `packages/hatchi-maxchi/icons/sprite.py` (pure builder: registry dict → sheet string)
- Test: `packages/hatchi-maxchi/tests/test_icon_contract.py` (extend)

**Interfaces:**
- Produces: `build_symbol_sheet(icons: dict[str,str]) -> str` returning `<svg ... style="display:none"><symbol id="{name}" viewBox="0 0 24 24">{inner}</symbol>...</svg>`; `sprite_use_html(name, *, cls="icon") -> str` returning `<svg class="{cls}" aria-hidden="true"><use href="#{name}"/></svg>`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_icon_contract.py
from icons.sprite import build_symbol_sheet, sprite_use_html
from icons.registry import ICONS


def test_sheet_has_a_symbol_per_icon():
    sheet = build_symbol_sheet(ICONS)
    assert sheet.startswith("<svg") and "display:none" in sheet
    for name in ("check", "circle-check", "trash-2"):
        assert f'<symbol id="{name}" viewBox="0 0 24 24">' in sheet


def test_sprite_use_is_short_and_decorative():
    out = sprite_use_html("circle-check")
    assert out == '<svg class="icon" aria-hidden="true"><use href="#circle-check"/></svg>'
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q -k sheet or sprite_use`
Expected: FAIL (module `icons.sprite` missing).

- [ ] **Step 3: Implement `packages/hatchi-maxchi/icons/sprite.py`**

```python
"""Sprite-sheet delivery for the icon registry (stdlib only).

The same registry that renders inline SVG also emits one <symbol> sheet;
`<use href="#name">` references it same-document (renders on file:// and
Pages — only external-file <use> breaks on file://)."""

def build_symbol_sheet(icons: dict[str, str]) -> str:
    symbols = "".join(
        f'<symbol id="{name}" viewBox="0 0 24 24">{inner}</symbol>'
        for name, inner in sorted(icons.items())
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
        f'fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{symbols}</svg>'
    )


def sprite_use_html(name: str, *, cls: str = "icon") -> str:
    return f'<svg class="{cls}" aria-hidden="true"><use href="#{name}"/></svg>'
```

- [ ] **Step 4: Wire sheet emission into `gen_registry.py`** — in `write_outputs()`, after writing the registries, also write the sheet to a committed asset the gallery build reads (e.g. `packages/hatchi-maxchi/icons/sprite_sheet.svg`):

```python
from icons.sprite import build_symbol_sheet  # local import to keep gen stdlib
sheet_path = HERE / "sprite_sheet.svg"
sheet_path.write_text(build_symbol_sheet(icons), encoding="utf-8")
```

(Use whatever `icons` dict variable `write_outputs` already holds; `HERE` = the icons dir Path already defined in the module.)

- [ ] **Step 5: Run + regenerate**

Run:
```bash
cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q && python icons/gen_registry.py --sync
```
Expected: PASS; `icons/sprite_sheet.svg` written; drift gate still green.

- [ ] **Step 6: Commit**

```bash
git add packages/hatchi-maxchi/icons/sprite.py packages/hatchi-maxchi/icons/gen_registry.py packages/hatchi-maxchi/icons/sprite_sheet.svg packages/hatchi-maxchi/tests/test_icon_contract.py
git commit -m "feat(taste): symbol-sheet + sprite-use helpers from the icon registry"
```

**CHECKPOINT.** `/bump patch` + push.

---

## Phase 4 — gallery pedagogy (the payload)

Rework the gallery so component snippets show the quiet sprite form, inject one sheet so demos render, add the Setup include note, and add the Icon Hyperpart page.

### Task 5: Inject the sheet + render component snippets as sprite `<use>`

**Files:**
- Modify: `packages/hatchi-maxchi/site/build_site.py` (head/layout ~376-412; token expansion ~41-96; `expand_icons` ~329)
- Test: `packages/hatchi-maxchi/tests/test_contract.py` (extend) or `test_icon_contract.py`

**Interfaces:**
- Consumes: `build_symbol_sheet`, `sprite_use_html` (Task 4).
- Produces: gallery `index.html` carries one hidden sheet in `<body>`; `{icon:...}`/`{svg:...}` tokens expand to `sprite_use_html(name)` for the snippet+demo string.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_icon_contract.py
from site.build_site import build_gallery_html  # or the function that returns the page string


def test_gallery_injects_one_symbol_sheet():
    html = build_gallery_html()
    assert html.count('style="display:none"') >= 1
    assert '<symbol id="circle-check"' in html


def test_component_snippets_use_sprite_reference():
    html = build_gallery_html()
    assert '<use href="#' in html          # sprite form present
    # a component snippet must NOT inline full path data for its icons
    assert html.count("<use href=\"#") >= 3
```

(Adjust `build_gallery_html` to the real page-string entrypoint found in `build()`.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q -k sheet or sprite_reference`
Expected: FAIL (tokens currently expand to inline SVG; no sheet injected).

- [ ] **Step 3: Switch token expansion to sprite form** — in `build_site.py` change the two substitutions so snippet+demo use `sprite_use_html`:

```python
markup = _ICON_RE.sub(lambda m: sprite_use_html(_require(m.group(1)), cls="icon icon--size-sm"), markup)
markup = _SVG_RE.sub(lambda m: sprite_use_html(_require(m.group(1)), cls="icon"), markup)
```

Note: gallery is unprefixed, so `cls="icon ..."` (not `dz-icon`). The copy/check button icons (lines 310-311) may stay inline `lucide_svg_html` (chrome, not a taught snippet) — or convert for consistency; keep them inline to avoid depending on the sheet for chrome.

- [ ] **Step 4: Inject the sheet into the layout** — in `build()` where the page `<body>` is assembled (~385), prepend the sheet once:

```python
from icons.sprite import build_symbol_sheet
from icons.registry import ICONS
sheet = build_symbol_sheet(ICONS)   # unprefixed ids; symbols are namespace-neutral
# insert `sheet` immediately after <body> opens, before .hm-wrap
```

- [ ] **Step 5: Run + rebuild + full suite**

Run:
```bash
cd packages/hatchi-maxchi && python -m pytest tests/test_icon_contract.py -q && python site/build_site.py && python -m pytest tests/ -q
```
Expected: PASS (incl. `test_committed_gallery_*` after rebuild).

- [ ] **Step 6: Browser verify** — open `packages/hatchi-maxchi/dist/index.html` (or the built gallery) via `file://`; confirm icons render (same-document `<use>` works on file://) and snippets read as `<use href="#...">`.

- [ ] **Step 7: Commit**

```bash
git add packages/hatchi-maxchi/site packages/hatchi-maxchi/tests/test_icon_contract.py
git commit -m "feat(taste): gallery snippets use sprite <use>; one symbol sheet injected"
```

### Task 6: Setup include note + Icon Hyperpart page

**Files:**
- Modify: `packages/hatchi-maxchi/site/registry.py` (add an `icon` Hyperpart entry; add Setup copy)
- Modify: `packages/hatchi-maxchi/site/build_site.py` if a Setup/prose region needs a slot
- Test: `packages/hatchi-maxchi/tests/test_contract.py` (registry-class-has-rule already covers new classes)

**Interfaces:**
- Consumes: the `Hyperpart` dataclass (`site/registry.py:53-78`).
- Produces: a gallery page/section documenting (a) the two includes — CSS bundle + icon sheet — and (b) the icon anatomy (inline vs sprite, `.icon` sizes, decorative vs `label`).

- [ ] **Step 1: Add the Setup note** — near the gallery topbar/intro, add prose: "Two one-time includes: `hatchi-maxchi.css` and the icon sheet (`sprite_sheet.svg`, inlined once per page). Component snippets reference icons via `<use href="#name">` — include the sheet or the icon won't render." Place it where the existing intro copy lives in `build_site.py`.

- [ ] **Step 2: Add the Icon Hyperpart** to `registry.py` HYPERPARTS — a page whose `partial` demonstrates: inline form, sprite form, the size scale (`icon--size-xs..xl`), `icon-solid`, and a decorative-vs-`label` pair. Example `partial` (unprefixed, gallery-facing):

```python
Hyperpart(
    id="icon",
    title="Icon",
    group="Primitives",
    blurb="Inline SVG substrate; sprite <use> for repetition. currentColor, decorative by default.",
    partial=(
        '<div class="icon-demo">'
        '<span class="icon icon--size-xs">{svg:check}</span>'
        '<span class="icon icon--size-sm">{svg:check}</span>'
        '<span class="icon icon--size-md">{svg:check}</span>'
        '<span class="icon icon--size-lg">{svg:check}</span>'
        '<span class="icon icon--size-xl">{svg:check}</span>'
        '</div>'
    ),
    notes="Decorative icons are aria-hidden; pass a label for meaningful icons "
          "(role=img). Inline for isolation; sprite <use> when an icon repeats.",
    tags=("icon", "svg", "sprite", "a11y"),
),
```

(`{svg:check}` expands to sprite `<use>` per Task 5. Confirm the `icon-demo` class has a rule or add one, else `test_every_registry_class_has_a_rule` fails.)

- [ ] **Step 3: Add any new CSS class rule** the Icon partial introduces (e.g. `.dz-icon-demo { display:flex; gap: var(--space-md); align-items:center; }`) to a component CSS file, authored `dz-`-prefixed.

- [ ] **Step 4: Rebuild + full suite**

Run:
```bash
cd packages/hatchi-maxchi && python build.py && python site/build_site.py && python -m pytest tests/ -q
```
Expected: PASS (`test_every_registry_class_has_a_rule`, committed-artifact gates green).

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/site packages/hatchi-maxchi/components packages/hatchi-maxchi/dist
git commit -m "feat(taste): Icon Hyperpart page + Setup icon-sheet include note"
```

- [ ] **Step 6: Dazzle-side rebuild + full gate sweep**

Run:
```bash
cd /Volumes/SSD/Dazzle && python scripts/build_dist.py
pytest -n auto --dist loadgroup -m "not e2e" -q
```
Expected: PASS (icon drift, hm boundary, badge WCAG, nav-icons all green; Dazzle server render still inline).

**CHECKPOINT — adversarial review** (fresh reviewer subagent) on Phase 4: confirm (a) demos render on `file://`, (b) no snippet silently depends on an un-included sheet without the Setup note covering it, (c) gallery byte-regeneration is deterministic, (d) Dazzle unaffected. `/bump patch` + push.

---

## Deferred follow-ons (explicitly out of this plan)

- **Helper convergence** `lucide_icon_html`+`lucide_svg_html` → one `icon(name, *, class, label, decorative, mode)` across 16 Dazzle callers. High churn, serves neither stated goal; do later if desired.
- **Dazzle sprite adoption** — serve `/static/icons.svg` (hosted → external `<use>` fine) or inline the sheet in the app shell; convert repeated-icon surfaces (tables) to sprite. Decide when payload matters.
- **Full context-class migration** onto `.dz-icon` (badge/alert/nav emit `class="dz-icon ..."`). Opportunistic; the base contract now exists to migrate toward.
- **Runtime fail-loud in Dazzle** (dev raise on unknown DSL-referenced icon) — currently the client `data-lucide` fallback stays; a gate test (like `test_nav_icons.py`) is the safer enforcement.

## Self-Review

- **Spec coverage:** `.icon` contract → Task 1; `label` a11y → Task 2; fail-loud → Task 3; sprite mode → Task 4; sheet injection + sprite snippets → Task 5; Setup note + Icon page → Task 6. Icon-font rejection & sanitiser-skip → Non-goals (no task, correct). Dazzle sprite delivery → deferred (spec marked it a follow-on). ✅
- **Placeholder scan:** import paths for `build`/`site.build_site`/`expand_icons`/`build_gallery_html` are marked "adjust to actual" — the executor confirms the real symbol names against `build_site.py` at Task 3/5 (the functions exist per the exploration; exact names verified at edit time). No TBD logic.
- **Type consistency:** `sprite_use_html(name, *, cls="icon")` and `build_symbol_sheet(icons)` used identically in Tasks 4–5; `label=None` default consistent across Tasks 2 helpers; `--size-sm/md/lg` preserved throughout.
