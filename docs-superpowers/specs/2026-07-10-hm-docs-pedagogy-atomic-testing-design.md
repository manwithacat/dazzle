# HM Docs Pedagogy + Atomic Per-Hyperpart Testing — Design

**Date**: 2026-07-10
**Status**: Approved for planning
**Driver**: Following the contract-modules pilot (v0.101.21–.22), use the HM docs for
agent AND human pedagogy — clear copy-pasteable structures per Hyperpart, agent-optimised
guidance — and make each Hyperpart atomically testable, with the docs site itself as the
drift-gated CI fixture (the dual-use house pattern).

## Context (explored 2026-07-10)

- The gallery is ONE committed 331KB `site/index.html` carrying all 70 Hyperparts;
  only app-shell has a standalone live page. Blueprints already have per-page builds.
- The site is already currency-gated: `tests/test_contract.py` rebuilds into a tmp dir
  and compares against the committed artifact. What's missing is *atomicity*, not drift
  protection.
- Behaviour tests hit selectors on the single page (failures don't name a part;
  cross-part event bleed is possible); visual baselines are whole-gallery per theme
  (any part's change churns the shared baseline); axe/vnu sweep the one page.
- "Agent Implementation Guidance" is free prose in the registry `notes` field.
- HM's test suite runs only in the standalone repo's CI post-sync — the monorepo never
  runs it (this is how a stale dist sat unnoticed on main until 2026-07-10).

## Decisions (locked with user, 2026-07-10)

1. **Atomic test subject = the docs-site construction.** Per-part committed pages are
   simultaneously the deep-linkable docs and the isolated fixtures. Dazzle-side
   constructions remain covered by the contract pilot's DOM-conformance gates.
2. **Agent guidance = structured registry block + per-part agent files**
   (`site/agents/<id>.md`, one fetchable chunk per part; llms.txt indexes them).
3. **Human pedagogy = per-part depth + ONE theory track** (`site/guide.html`).
4. **Approach A** (registry-driven per-part pages as the canonical unit) over
   hidden-fixture and iframe alternatives.
5. **Refinement**: `index.html` stays a SIMPLE gallery — live demo + copy snippet +
   link per part, NO contracts/exchanges/guidance/anatomy disclosures. Depth lives on
   the part pages.

## Site architecture (three layers, one build)

```
site/index.html            SIMPLE GALLERY: group nav, live demo + copy snippet per part,
                           link to hyperparts/<id>.html. Pure visual pedagogy.
site/hyperparts/<id>.html  THE canonical part page (×70): live demo + snippet +
                           exchange table + contract section + structured guidance +
                           anatomy note. Docs deep-link AND atomic test fixture.
site/agents/<id>.md        Agent-optimised chunk: partial + exchanges + contract schema
                           + guidance in one fetch. llms.txt lists all of them.
site/guide.html            The theory track: hypermedia/no-client-state → tokens &
                           theming → anatomy of a Hyperpart (grid-edit worked example)
                           → exchanges & contracts → composing Blueprints.
```

Everything is a committed build artifact of `site/build_site.py`; the existing
rebuild-and-compare gate extends over the full set (index + 70 part pages + agents/ +
guide + llms.txt), so no layer can lag the registry.

Framed parts (`framed=True`, fixed-position compositions) keep their `-live.html`
browsing-context treatment, embedded on their part page instead of the index.

## Structured guidance

`Hyperpart` gains a typed `Guidance` block:

- `seams: tuple[str, ...]` — the extension/composition points, by name
- `pitfalls: tuple[str, ...]` — the mistakes the design already rejected
- `do_dont: tuple[tuple[str, str], ...]` — paired do/don't rules
- `a11y_keys: tuple[str, ...]` — keyboard/AT behaviours a consumer must preserve
- `composes_with: tuple[str, ...]` — Hyperpart ids (cross-checked against the registry)

Free-prose `notes` stays for genuinely narrative remarks; guidance-like prose migrates
into the block. Rendering: the guidance section on part pages (human) and verbatim
serialisation into `agents/<id>.md` (agent). Gate: controller-bearing parts must carry
at least `seams` + `pitfalls`, with a shrink-only `PENDING_GUIDANCE` allowlist for
unmigrated parts (the `PENDING_CONTRACTS` ratchet style).

## Atomic testing

- **behaviour** (`test_behaviour.py`): each scenario declares its part id and runs
  against `hyperparts/<id>.html` in isolation; Chromium + WebKit as today. Failures
  name the part; no cross-part event bleed.
- **visual** (`test_visual.py`): per-part baselines `baselines/<theme>/<id>.png` —
  surgical diffs; plus one gallery-level baseline for `index.html` itself.
  Regeneration stays `HM_UPDATE_BASELINES=1` (and the update-baselines workflow).
- **axe + vnu**: sweep every part page + index + guide; failures name the page.
- **Coverage meta-gate**: (a) every registry part has its page in the committed site;
  (b) every controller-bearing part has ≥1 behaviour scenario or a shrink-only
  `PENDING_BEHAVIOUR` entry. Atomicity cannot be quietly opted out of.

## Monorepo CI wiring

One new Dazzle gate (`pytest.mark.gate`, DB/browser-free) runs HM's non-browser suite
from `packages/hatchi-maxchi/` (contracts, cohesion, class↔CSS/exchange parity,
dist+site drift) — closing the gap that let the stale dist sit on main. Browser-based
HM tests (behaviour/visual/wcag) stay in the standalone repo's CI; Playwright weight
does not enter the monorepo pre-flight.

## Rollout (three phases, each ships green)

1. **Build split**: per-part page emission + simple-gallery index + `agents/<id>.md`
   + llms.txt update + drift-gate extension. Mechanical for all 70 (pages generate
   from the registry). Verify the Pages deploy renders locally before push.
2. **Guidance migration + guide**: typed `Guidance` for controller-bearing parts first
   (ratchet for the rest); author `guide.html`, embedding only live registry strings
   wherever it shows code (so the gates see everything embedded).
3. **Test re-targeting**: behaviour per-part, per-part visual baselines (one-time bulk
   regeneration, reviewed), axe/vnu page sweeps, coverage meta-gate, and the monorepo
   fast gate.

## Risks & mitigations

- **Baseline bulk churn** (one-time): bounded, per-part PNGs are small; review via the
  update-baselines workflow diff.
- **Index redesign touches the public Pages site**: committed artifact — eyeball the
  rebuilt index locally before pushing; the visual baseline for index pins it after.
- **guide.html is narrative** (gates can't verify prose): every embedded code sample
  comes from a registry/contract string (drift-gated sources only); prose carries
  theory, not claims about specific APIs.
- **Agent-file size**: `agents/<id>.md` stays one part per file by design — if a part's
  chunk outgrows a sane context budget, that's a smell about the part, not a reason to
  split the file.

## Out of scope

- Dazzle-side per-part emission fixtures (decision 1 — conformance gates cover that).
- A multi-chapter course (decision 3 — one theory track only).
- Blueprint-level pedagogy changes (Blueprints already have per-page builds + tests).
