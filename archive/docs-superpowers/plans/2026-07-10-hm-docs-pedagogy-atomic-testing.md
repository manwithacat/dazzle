# HM Docs Pedagogy + Atomic Per-Hyperpart Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-Hyperpart docs pages that double as atomic test fixtures, a simple-gallery index, per-part agent files, one theory track, structured guidance, and re-targeted atomic behaviour/visual/axe suites — with the docs site drift-gated end-to-end and the HM non-browser suite wired into the Dazzle monorepo gates.

**Architecture:** `site/build_site.py` becomes a three-layer emitter (simple index / `hyperparts/<id>.html` depth pages / `agents/<id>.md` chunks + `guide.html`), all committed and covered by an extended tree-compare drift gate. Tests parametrize over the registry. Spec: `docs/superpowers/specs/2026-07-10-hm-docs-pedagogy-atomic-testing-design.md`.

**Tech Stack:** Python (build script + pytest), Playwright (Chromium+WebKit), PIL baselines, axe, vnu.

## Global Constraints

- Site rebuild = `python site/build_site.py` (from `packages/hatchi-maxchi/`); `python build.py` = dist only. Both artifacts are committed; never edit outputs by hand.
- NEVER subtree-push — `sync-hatchi-maxchi.yml` mirrors automatically, including `.github/workflows/*` in the package tree.
- `index.html` is the SIMPLE gallery: group nav + live demo + copy snippet + part-page link. NO exchanges/contract/guidance/anatomy disclosures on it (spec decision 5).
- Dazzle-side gates are `pytest.mark.gate`, DB/browser-free.
- Ship discipline per phase: `/bump patch`, CHANGELOG (+ Agent Guidance), commit in its own command, verify HEAD moved, THEN tag+push. Run git from the repo root (bash cwd persists).
- Baseline regeneration: local `HM_UPDATE_BASELINES=1`, linux set via `gh workflow run update-baselines.yml`; review diffs before committing.
- guide.html code samples come ONLY from registry/contract strings (drift-gated sources), never hand-typed markup.

## File map

| File | Role |
|---|---|
| `packages/hatchi-maxchi/site/build_site.py` | three-layer emission + guide + agents + llms |
| `packages/hatchi-maxchi/site/registry.py` | `Guidance` dataclass + `guidance:` field |
| `packages/hatchi-maxchi/site/hyperparts/*.html` | generated part pages (committed) |
| `packages/hatchi-maxchi/site/agents/*.md` | generated agent chunks (committed) |
| `packages/hatchi-maxchi/site/guide.html` | generated theory track (committed) |
| `packages/hatchi-maxchi/tests/test_contract.py` | tree-compare drift gate extension |
| `packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py` | PENDING_GUIDANCE ratchet |
| `packages/hatchi-maxchi/tests/{test_behaviour,test_visual,test_wcag}.py` | atomic re-targeting |
| `packages/hatchi-maxchi/tests/conftest.py` | `goto_part` helper |
| `packages/hatchi-maxchi/.github/workflows/ci.yml` | job lists (verify; behaviour/visual/wcag paths unchanged) |
| `tests/unit/test_hm_package_suite_gate.py` (Dazzle) | monorepo fast gate over HM non-browser suite |

---

## Phase 1 — Build split

### Task 1: Part-page + agents emission, simple index, tree drift gate

**Files:**
- Modify: `packages/hatchi-maxchi/site/build_site.py` (part-section assembly ~line 893-903; blueprint sub-page pattern ~1061-1154 is the model; llms.txt block ~1089)
- Modify: `packages/hatchi-maxchi/tests/test_contract.py:232-246` (`test_gallery_regenerates_byte_identically`)

**Interfaces:**
- Produces: `site/hyperparts/<id>.html` for every `HYPERPARTS` entry; `site/agents/<id>.md`; simple index sections linking `hyperparts/<id>.html`; `_part_page_doc(c, prefix) -> str` and `_agent_md(c) -> str` helpers in build_site. Phase 3 tests navigate to `hyperparts/<id>.html`.

- [ ] **Step 1: Write the failing drift-gate extension** — replace the fixed-name loop in `test_gallery_regenerates_byte_identically` with a full tree compare:

```python
    import build_site

    build_site.build(tmp_path)
    fresh_files = {p.relative_to(tmp_path).as_posix(): p for p in tmp_path.rglob("*") if p.is_file()}
    committed_root = PKG / "site"
    SKIP = {"__pycache__"}  # committed-side helper dirs that build() does not emit
    committed_files = {
        p.relative_to(committed_root).as_posix(): p
        for p in committed_root.rglob("*")
        if p.is_file() and not any(part in SKIP for part in p.parts)
        and p.suffix not in (".py",)  # registry/build/blueprints sources live here too
    }
    missing = sorted(set(fresh_files) - set(committed_files))
    stale_extra = sorted(set(committed_files) - set(fresh_files))
    assert not missing, f"built artifacts not committed: {missing} — run site/build_site.py and commit"
    assert not stale_extra, f"committed artifacts the build no longer emits: {stale_extra} — delete them"
    for rel, fp in fresh_files.items():
        assert fp.read_bytes() == committed_files[rel].read_bytes(), (
            f"site/{rel} is stale or the build is nondeterministic — re-run and commit"
        )
    # Sanity: the three new layers exist.
    assert any(r.startswith("hyperparts/") for r in fresh_files)
    assert any(r.startswith("agents/") for r in fresh_files)
    assert "guide.html" in fresh_files or True  # guide lands in Phase 2; drop the `or True` then
```

(Check what non-emitted files live under `site/` — `fonts/` are copied by build; `blueprints.py`/`build_site.py`/`registry.py`/`icons` sources are excluded by the `.py` filter; extend SKIP for anything else the first run reveals, each with a comment.)

- [ ] **Step 2:** Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_contract.py::test_gallery_regenerates_byte_identically -q` — expected FAIL (no `hyperparts/` in fresh build yet).

- [ ] **Step 3: Split the emitter.** In `build()`:
  1. Extract today's full per-part section builder (the `body_parts.append(...)` block at ~893-903 including exchanges/contracts/composed/anatomy/notes) into `_part_page_doc(c, prefix) -> str` that wraps it in a standalone HTML document — copy the blueprint sub-page document scaffold (`bp_doc` assembly ~1105-1154: same `<head>` bundle/sheet links but with `../` relative paths, same theme toggle) with `<title>{c.title} — HaTchi-MaXchi</title>`, a back-link to `../index.html#{c.id}`, and the part's full section as the body. Framed parts embed their existing `-live.html` iframe (path-adjusted `../hyperparts/{id}-live.html` stays emitted where it is today).
  2. Emit: `hp_dir = out_dir / "hyperparts"; hp_dir.mkdir(exist_ok=True)`, then per part `(hp_dir / f"{c.id}.html").write_text(_part_page_doc(c, prefix) + "\n", encoding="utf-8")`.
  3. The index `body_parts.append` block becomes the SIMPLE section:

```python
        body_parts.append(
            f'<section class="hm-comp" id="{c.id}">'
            f"<h2>{_html.escape(c.title)}{tag}</h2>"
            f'<p class="blurb">{apply_prefix(_html.escape(c.blurb), prefix)}</p>'
            f'<div class="hm-preview">{framed_live}</div>'
            f'<div class="hm-code">{copy_button}'
            f'<pre tabindex="0" role="region" aria-label="Code for {_html.escape(c.title)}">'
            f"<code>{snippet}</code></pre></div>"
            f'<p class="hm-more"><a href="hyperparts/{c.id}.html">Full reference: '
            f"contracts, guidance, anatomy →</a></p></section>"
        )
```

  (Drop `deps` chips + `_exchanges_html` + `_contracts_html` + `_composed_of_html` + `_anatomy_html` + `notes` from the index — they all move into `_part_page_doc`.)
  4. `_agent_md(c) -> str`: markdown chunk — front section `# {c.title} ({c.id})`, blurb, `## Partial` fenced markup (`c.partial` prefixed), `## Exchanges` as a markdown table from `c.exchanges`, `## Contract` per `c.contracts` (model schema field list + DOM contract node/attr list — import the contract module as `_contracts_html` does), `## Guidance` (Phase 2 adds the structured block; until then serialise `c.notes`). Emit to `out_dir / "agents" / f"{c.id}.md"`.
  5. llms.txt: after the contract-modules bullet, add a `## Per-part agent files` section listing `agents/<id>.md` one line per part with the blurb.

- [ ] **Step 4:** Rebuild + verify: `cd packages/hatchi-maxchi && python site/build_site.py && python -m pytest tests/test_contract.py tests/test_pretty.py tests/test_hyperpart_cohesion.py tests/test_contracts.py -q` — expected PASS (drift gate now green with all layers committed). `git -C /Volumes/SSD/Dazzle status --short packages/hatchi-maxchi/site | head` shows index + 70 part pages + 70 agent files + llms.txt.
- [ ] **Step 5: Eyeball locally** — `open packages/hatchi-maxchi/site/index.html` and one part page (`open packages/hatchi-maxchi/site/hyperparts/grid.html`): index is the simple gallery; part page carries the depth; back-link works; framed parts render.
- [ ] **Step 6:** Commit: `git add packages/hatchi-maxchi/site packages/hatchi-maxchi/tests/test_contract.py && git commit -m "feat(hm): three-layer docs — simple index, per-part pages, per-part agent files"`

### Task 2: Ship Phase 1

- [ ] `/bump patch`; CHANGELOG Added: "HM docs split into three layers: simple-gallery index, per-part deep pages (`hyperparts/<id>.html` — docs AND atomic fixtures), per-part agent chunks (`agents/<id>.md`, llms.txt-indexed). Site drift gate is now a full tree compare." `### Agent Guidance`: "Consuming an HM part? Fetch `agents/<id>.md` — one chunk with partial + exchanges + contract + guidance." Then `/ship`. After sync, spot-check the Pages deploy renders the new index.

---

## Phase 2 — Guidance + guide

### Task 3: `Guidance` dataclass + ratchet + rendering

**Files:**
- Modify: `packages/hatchi-maxchi/site/registry.py` (dataclass above `Hyperpart`; field after `contracts`)
- Modify: `packages/hatchi-maxchi/site/build_site.py` (`_guidance_html(c)` on part pages; `_agent_md` serialisation)
- Modify: `packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py` (ratchet)

**Interfaces:**
- Produces: `Guidance(seams, pitfalls, do_dont, a11y_keys, composes_with)` (all tuple fields, defaults empty) and `Hyperpart.guidance: Guidance | None = None`.

- [ ] **Step 1: Failing gates** (append to `test_hyperpart_cohesion.py`):

```python
# Controller-bearing Hyperparts not yet migrated to structured Guidance.
# SHRINK-ONLY — remove entries as guidance blocks land; never add.
PENDING_GUIDANCE = frozenset({
    # seed with every controller-bearing part id EXCEPT the ones migrated in
    # this task (grid at minimum); enumerate at implementation from
    # {h.id for h in HYPERPARTS if h.controller}
})


def test_controller_parts_have_guidance_or_pending() -> None:
    for h in HYPERPARTS:
        if not h.controller or h.id in PENDING_GUIDANCE:
            continue
        g = h.guidance
        assert g is not None and g.seams and g.pitfalls, (
            f"{h.id}: controller-bearing part needs Guidance with seams + pitfalls "
            f"(or a PENDING_GUIDANCE entry — which only shrinks)"
        )


def test_guidance_composes_with_ids_are_real() -> None:
    for h in HYPERPARTS:
        if h.guidance:
            ghosts = sorted(set(h.guidance.composes_with) - _IDS)
            assert not ghosts, f"{h.id}: guidance.composes_with names unknown parts {ghosts}"
```

- [ ] **Step 2:** Run — expected FAIL (`Guidance` undefined / field missing).
- [ ] **Step 3:** Add to `registry.py` (above `Hyperpart`):

```python
@dataclass(frozen=True)
class Guidance:
    """Structured, agent-optimised implementation guidance — replaces
    guidance-like prose in `notes` (narrative remarks stay in notes).
    Rendered on the part page for humans and serialised verbatim into
    agents/<id>.md for agents."""

    seams: tuple[str, ...] = ()          # extension/composition points, by name
    pitfalls: tuple[str, ...] = ()       # mistakes the design already rejected
    do_dont: tuple[tuple[str, str], ...] = ()  # (do, don't) pairs
    a11y_keys: tuple[str, ...] = ()      # keyboard/AT behaviours to preserve
    composes_with: tuple[str, ...] = ()  # Hyperpart ids (cross-checked)
```

and on `Hyperpart` (after `contracts`): `guidance: Guidance | None = None`.
- [ ] **Step 4: Migrate the grid family** as the worked example: author `guidance=Guidance(...)` on the grid entry from its current notes + the dz-grid-edit contract header (seams: cols/resize/edit extension attributes; pitfalls: morph-buffer, options-shape; do_dont: state-in-DOM vs JS objects; a11y_keys: Tab/Shift-Tab commit-advance, Esc cancel). Seed `PENDING_GUIDANCE` with the other controller-bearing ids. Move migrated guidance-prose OUT of `notes` (keep narrative remainder).
- [ ] **Step 5:** `_guidance_html(c)` in build_site (part pages only — renders the four lists + do/don't table inside the existing `.hm-guidance` disclosure styling); `_agent_md` emits `## Guidance` with the same content as markdown lists. Rebuild site; run the HM non-browser suite — expected PASS.
- [ ] **Step 6:** Commit: `git add packages/hatchi-maxchi && git commit -m "feat(hm): structured Guidance block + shrink-only PENDING_GUIDANCE ratchet (grid migrated)"`

### Task 4: guide.html theory track

**Files:**
- Modify: `packages/hatchi-maxchi/site/build_site.py` (a `GUIDE_SECTIONS` structure + `_guide_doc()` emission; index nav gains a "Guide" link)

- [ ] **Step 1:** Author `GUIDE_SECTIONS: list[tuple[str, str, str | None]]` — `(title, prose_html, embed_key)` where `embed_key` optionally names a live artifact to embed: `"partial:grid"` (renders `_BY_ID["grid"].partial` as demo + snippet), `"contract:grid_edit"` (reuses `_contracts_html` for the grid entry), `"blueprint:dashboard"` (links the blueprint page). Five sections per the spec: (1) Why hypermedia — no client state graph, state in DOM + server; (2) Tokens & theming — scheme flip demo using the existing theme toggle; (3) Anatomy of a Hyperpart — grid-edit worked example (partial → controller marker → contract module); (4) Exchanges & contracts — the two contract halves, embedding the grid exchange table + contract section; (5) Composing Blueprints. Prose is written fresh (theory, no API claims); every code/markup block comes from an embed_key.
- [ ] **Step 2:** `_guide_doc()` assembles the document with the part-page scaffold; `build()` writes `out_dir / "guide.html"`; index nav gets `<a href="guide.html">Guide</a>`; llms.txt gets a Guide line; drop the Phase-1 `or True` in the drift gate's guide assertion.
- [ ] **Step 3:** Rebuild; HM non-browser suite green; eyeball `guide.html` locally.
- [ ] **Step 4:** Commit: `git add packages/hatchi-maxchi && git commit -m "feat(hm): guide.html theory track — embeds only drift-gated registry/contract strings"`

### Task 5: Ship Phase 2

- [ ] `/bump patch`; CHANGELOG Added (Guidance block + ratchet + guide.html); `### Agent Guidance`: "Structured guidance lives on `Hyperpart.guidance` — controller-bearing parts require seams+pitfalls (PENDING_GUIDANCE shrinks only)." `/ship`.

---

## Phase 3 — Atomic test re-targeting + monorepo gate

### Task 6: Behaviour re-targeting

**Files:**
- Modify: `packages/hatchi-maxchi/tests/conftest.py` (helper), `packages/hatchi-maxchi/tests/test_behaviour.py`

- [ ] **Step 1:** In `conftest.py` add:

```python
def part_uri(part_id: str) -> str:
    return (PKG / "site" / "hyperparts" / f"{part_id}.html").as_uri()


def goto_part(page, part_id: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(part_uri(part_id))
    page.wait_for_timeout(200)
```

Change the shared `page` fixture to open a blank page WITHOUT goto (keep viewport + JS-error capture); add a `gallery_page` fixture that gotos `SITE_URI` for index-level tests.
- [ ] **Step 2:** In `test_behaviour.py`: each test's first action becomes `goto_part(page, "<id>")` — palette tests → `command`, confirm tests → `confirm-panel`'s owning part id (check registry), grid tests → `grid`, etc. Module-level mock-htmx works unchanged (part pages carry the same mock shim — verify; if the shim is index-only, `_part_page_doc` must include it, fix in build_site). A module-level `PART_FOR_TEST` mapping is NOT needed — the explicit first line per test is the declaration the coverage gate greps (Task 8).
- [ ] **Step 3:** Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_behaviour.py -q` (needs playwright locally; if unavailable, rely on standalone CI and note it) — expected PASS both engines.
- [ ] **Step 4:** Commit: `git add packages/hatchi-maxchi/tests && git commit -m "test(hm): behaviour scenarios run atomically against per-part pages"`

### Task 7: Visual + wcag re-targeting

**Files:**
- Modify: `packages/hatchi-maxchi/tests/test_visual.py`, `packages/hatchi-maxchi/tests/test_wcag.py`

- [ ] **Step 1:** `test_visual.py`: keep `test_gallery_visual` (index baseline, `gallery-{theme}` names unchanged); add:

```python
_PART_IDS = [h.id for h in HYPERPARTS]  # import registry like other tests


@pytest.mark.parametrize("part_id", _PART_IDS)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_part_visual(page, part_id, theme) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, part_id)
    if theme == "dark":
        page.evaluate("hmTheme('dark')")
    page.wait_for_timeout(300)
    page.evaluate("document.fonts && document.fonts.ready")
    _compare(f"part-{part_id}-{theme}", page.screenshot())
```

- [ ] **Step 2:** `test_wcag.py`: parametrize the page-level sweep over `_PART_IDS + ["index", "guide"]` (goto part page / SITE_URI / guide URI); the open-state tests (palette/confirm/drawer/menu) goto their part's page first. Keep the allowlist gate.
- [ ] **Step 3:** Bulk baseline generation: local `HM_UPDATE_BASELINES=1 python -m pytest tests/test_visual.py -q` (writes darwin set; each write skips), commit after eyeballing a sample; dispatch `gh workflow run update-baselines.yml` for the linux set once pushed (Ship, Task 9).
- [ ] **Step 4:** Commit: `git add packages/hatchi-maxchi/tests && git commit -m "test(hm): per-part visual baselines + per-page axe sweep"`

### Task 8: Coverage meta-gate + monorepo fast gate

**Files:**
- Modify: `packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py` (coverage gate)
- Create: `tests/unit/test_hm_package_suite_gate.py` (Dazzle)
- Modify: `packages/hatchi-maxchi/.github/workflows/ci.yml` (verify job paths; behaviour/visual/wcag file names unchanged — no edit expected; the html5validator/vnu step must validate `site/` RECURSIVELY so the new `hyperparts/` + `guide.html` pages are swept — check its invocation and add `--root site/` or equivalent recursion flag if it currently names files)

- [ ] **Step 1: Coverage meta-gate** (append to cohesion tests):

```python
def test_every_part_has_a_committed_page() -> None:
    for h in HYPERPARTS:
        assert (PKG / "site" / "hyperparts" / f"{h.id}.html").is_file(), (
            f"{h.id}: no committed part page — run site/build_site.py and commit"
        )


# Controller-bearing parts with no atomic behaviour scenario yet. SHRINK-ONLY.
PENDING_BEHAVIOUR = frozenset({
    # seed at implementation: controller-bearing ids minus those named in
    # goto_part(page, "<id>") calls in tests/test_behaviour.py
})


def test_controller_parts_have_behaviour_coverage_or_pending() -> None:
    behaviour_src = (PKG / "tests" / "test_behaviour.py").read_text(encoding="utf-8")
    for h in HYPERPARTS:
        if not h.controller or h.id in PENDING_BEHAVIOUR:
            continue
        assert f'goto_part(page, "{h.id}")' in behaviour_src, (
            f"{h.id}: controller-bearing part has no atomic behaviour scenario "
            f"(add one targeting hyperparts/{h.id}.html, or a PENDING_BEHAVIOUR "
            f"entry — which only shrinks)"
        )
```

- [ ] **Step 2: Monorepo fast gate** (`tests/unit/test_hm_package_suite_gate.py`):

```python
"""The HM package's non-browser suite runs inside the Dazzle gate sweep.

Closes the stale-dist class (2026-07-10: a shadow-token change shipped
without a dist rebuild and sat unnoticed — HM tests only ran in the
standalone repo's CI post-sync). Browser suites (behaviour/visual/wcag)
stay standalone-CI-only; this gate is the fast structural set."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.gate, pytest.mark.xdist_group("hm-package-suite")]

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"
NON_BROWSER = [
    "tests/test_contract.py",
    "tests/test_boundary.py",
    "tests/test_contracts.py",
    "tests/test_hyperpart_cohesion.py",
    "tests/test_css_parse_integrity.py",
    "tests/test_icon_contract.py",
    "tests/test_pretty.py",
]


def test_hm_non_browser_suite_is_green() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *NON_BROWSER, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(HM),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        "HM package non-browser suite failed inside the monorepo gate sweep "
        "(the stale-dist class). Output:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
    )
```

- [ ] **Step 3:** Run both: HM cohesion file + the new Dazzle gate (`pytest tests/unit/test_hm_package_suite_gate.py -q`, ~30s) — expected PASS. Then the full Dazzle gate sweep.
- [ ] **Step 4:** Commit: `git add packages/hatchi-maxchi/tests tests/unit/test_hm_package_suite_gate.py && git commit -m "test: coverage meta-gate + HM non-browser suite in the monorepo gate sweep"`

### Task 9: Ship Phase 3

- [ ] `/bump patch`; CHANGELOG Added/Changed (atomic re-targeting, per-part baselines, coverage gate, monorepo HM gate); `### Agent Guidance`: "New controller-bearing Hyperparts need an atomic behaviour scenario (`goto_part(page, \"<id>\")`) — PENDING_BEHAVIOUR shrinks only. HM non-browser tests now run in the Dazzle gate sweep — a red HM structural test blocks every ship." `/ship`; after push, `gh workflow run update-baselines.yml` for the linux baseline set and confirm standalone CI green on the sync.
