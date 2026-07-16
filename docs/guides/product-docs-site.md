# Recipe: Evergreen product docs site for a Dazzle app

**Status:** Proven at AegisMark (live at https://docs.aegismark.ai). Landed as
a Dazzle **consumer guide** (#1612 Stage A). Framework code extraction is
optional and phased (see [Upstream ladder](#upstream-ladder)).

**Proof-of-shape:** AegisMark `docs-site/`, `pipeline/docsite/`,
`scripts/docs_ship.sh`, `tests/docs/`, design
`docs/superpowers/specs/2026-07-01-evergreen-docs-site-design.md`.

**Second-consumer signal:** any multi-persona Dazzle product that needs
user-facing documentation that stays true to the live DSL.

This is **not** Dazzle's developer docs (ADR-0001 / this MkDocs site). It is the
*product* docs path: `docs.<product>` for end users, fully decoupled from the
app process and tenant hosts.

---

## Problem

A Dazzle app already *knows* its personas, workspaces, surfaces, and stories —
that is the AppSpec. Product documentation written by hand drifts the moment a
workspace is renamed or a persona is added. Meanwhile, framework developer docs
(MkDocs on GitHub Pages — ADR-0001) are the wrong place for *end-user* training
content, and the app process (Heroku / `dazzle serve` / tenant middleware) is the
wrong host for a public, unauthenticated docs site.

Every product team that wants evergreen user docs reimplements the same stack:

1. A static docs project separate from internal `docs/`
2. Live labels pulled from the AppSpec at build time
3. A structural drift gate against front-matter manifests
4. Decoupled static hosting on a custom domain (`docs.<product>`)
5. (Later) screen recordings that stay true to the real UI

AegisMark has run this end-to-end. The recipe below is what other Dazzle apps
should copy.

## Non-goals

- Replacing Dazzle's own developer docs site (ADR-0001).
- Serving product docs from the app process / tenant hosts.
- Auth-gated docs, versioned docs, or i18n (extensions, not prerequisites).
- Implementing the trace→video pipeline in v1 (roadmap phase; see below).

## Design principles

| Principle | Choice |
|-----------|--------|
| **Host** | Static site on **Cloudflare Workers (static assets)** — fully decoupled from the app process and tenant infra |
| **Toolchain** | **MkDocs + Material** + `mkdocs-macros-plugin` (Python-native, same stack as Dazzle's own docs) |
| **Source of truth** | Live AppSpec + `stories.json` via a small facts loader |
| **Evergreen contract** | YAML front-matter on every page declares the entities it documents; a tiered drift gate enforces currency |
| **Build location** | Build **locally / in CI where Dazzle is installed**, upload static output — macros need the pinned framework |
| **Content shape** | Getting Started + per-persona guides + cross-cutting how-tos (how-tos are the future video anchors) |

> **Note on Cloudflare product naming.** Cloudflare's current default for a static
> site is a **Worker with static assets**, deployed with `wrangler deploy`. Older
> docs say "Cloudflare Pages" + `wrangler pages deploy`. Functionally equivalent
> (pure static host, custom domain, Direct Upload). Prefer Workers-static-assets
> for new projects; the recipe works with either.

---

## Recipe (follow this)

### 0. Prerequisites

- A Dazzle project that already loads (`dazzle.toml` + DSL + pinned `dazzle-dsl`).
- A Cloudflare account that manages the product zone (or can CNAME into one).
- Node available for one-shot `npx wrangler` (no permanent Node dependency).
- Secrets in a gitignored root `.env`:

```bash
CLOUDFLARE_API_TOKEN=…    # Workers / Pages: Edit
CLOUDFLARE_ACCOUNT_ID=…
```

### 1. Layout — keep product docs out of internal docs

```
docs-site/                       # user-facing MkDocs project (NEW)
  mkdocs.yml
  main.py                        # macros bootstrap (sys.path → repo root)
  wrangler.toml                  # Cloudflare Worker static assets
  docs/
    index.md                     # Getting started
    guides/
      <persona>.md               # one guide per user-facing persona
    how-to/
      <task>.md                  # cross-cutting workflows (video anchors)
  overrides/                     # optional Material brand partials
  site/                          # build output (gitignored)

app/docsite/   (or pipeline/docsite/)   # evergreen tooling (NEW)
  facts.py                       # AppSpec + stories → Facts
  drift.py                       # front-matter parse + tiered gate
  macros.py                      # mkdocs-macros define_env

tests/docs/
  test_facts.py
  test_drift.py
  test_build.py                  # mkdocs build --strict + macros resolve

scripts/docs_ship.sh             # gate + strict build + wrangler deploy
```

**Rules:**

- `docs-site/` is **not** the internal `docs/` tree (ADRs, runbooks, QA).
- The deploy path **never** touches Heroku, `dazzle serve`, or tenant middleware.
- Reserve the `docs` slug in any multi-tenant host map so a stray
  `Host: docs.<product>` at the app process still 404s.

### 2. Dependency group (local-only)

In `pyproject.toml`:

```toml
[dependency-groups]
docs = [
    "mkdocs>=1.6",
    "mkdocs-material>=9.5",
    "mkdocs-macros-plugin>=1.3",
]
```

Never install this group on the app host. Preview and build:

```bash
uv run --group docs mkdocs serve -f docs-site/mkdocs.yml   # :8000
uv run --group docs mkdocs build --strict -f docs-site/mkdocs.yml
```

### 3. MkDocs config skeleton

`docs-site/mkdocs.yml`:

```yaml
site_name: <Product> Documentation
site_url: https://docs.<product-domain>
docs_dir: docs
theme:
  name: material
  custom_dir: overrides          # optional brand partials
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
plugins:
  - search
  - macros:
      module_name: main          # docs-site/main.py
nav:
  - Getting started: index.md
  - Guides:
      - Teacher: guides/teacher.md
      # …one entry per persona
  - How-to:
      - Mark a cohort: how-to/mark-a-cohort.md
      # …cross-cutting tasks
```

`docs-site/main.py` — put the repo root on `sys.path` and re-export
`define_env` from the facts package (MkDocs loads the module relative to
`mkdocs.yml`):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.docsite.macros import define_env  # noqa: E402,F401
```

### 4. Front-matter contract (the evergreen surface)

Every curated page declares the system entities it documents:

```yaml
---
persona: teacher                       # required on guide pages; omit on how-to/index
workspaces: [teacher_workspace, class_view]
surfaces: [class_summary]              # optional
stories: [ST-012, ST-018]
---
```

This declaration is what makes prose machine-checkable. Authors **never**
hard-code persona/workspace labels in the body — they use live macros:

```markdown
# A day as a {{ fact.persona('teacher').label }}

Your home is the **{{ fact.workspace('teacher_workspace').label }}** workspace.
```

Namespace macros under `fact.*`. Page front-matter keys are injected into the
Jinja context by mkdocs-macros and would shadow top-level macros with the same
name.

### 5. Facts loader (source of truth)

`facts.py` is a pure function:

```text
load_facts(appspec=None, stories_path=…) -> Facts
```

Extract from the **live** system (no database):

| Fact | Source |
|------|--------|
| personas | `appspec.personas` (exclude platform-only IDs such as `super_admin`) |
| workspaces | `appspec.workspaces` filtered to those reachable by ≥1 documented persona, via `dazzle.core.access.workspace_allowed_personas` |
| surfaces | `appspec.surfaces` |
| stories | `.dazzle/stories/stories.json` |

Load the AppSpec with the same path the project already uses
(`BuildService(dazzle.toml).load_appspec()` or `load_project_appspec`). The
macros and the drift gate share one `load_facts()` — no second source of truth.

**Reference implementation:** AegisMark `pipeline/docsite/facts.py` (~100 lines).

### 6. Drift gate (tiered, so it has teeth without being brittle)

`drift.py` pure functions:

```text
parse_manifests(docs_dir) -> list[PageManifest]
check_drift(facts, manifests, coverage_mode="partial"|"complete") -> DriftReport
```

| Tier | Meaning | When blocking |
|------|---------|----------------|
| **1** | A page references an entity that no longer exists | **Always** hard-fail |
| **2** | A persona has no guide, or a user-facing workspace is referenced by no guide | Hard-fail only when `coverage_mode: complete` |
| **3** | An accepted/done story referenced by no page | Advisory only |

Rollout:

1. **Pilot** (`partial`): ship the machine + 1–2 persona guides + 1 how-to.
   Tier 1 is live; Tier 2 gaps stay advisory so the pilot does not self-block.
2. **Scale-out:** author remaining persona guides + how-tos.
3. **Flip** to `complete` when the set is full — full coverage becomes hard-fail
   from then on.

Negative-control test: feed a fabricated stale workspace id and assert Tier 1
rejects it (proves the gate has teeth).

**Reference implementation:** AegisMark `pipeline/docsite/drift.py` +
`tests/docs/test_drift.py`.

### 7. Honest boundary (text vs video)

The gate guarantees **structural** currency — entities exist, are covered, and
labels are live. It does **not** verify that narrative steps ("click Mark, then
confirm") match the real UI. That is the job of phase-2 videos generated from
Playwright traces of the live product. Text and video divide the evergreen
problem cleanly; how-to pages are the anchors videos attach to.

### 8. Cloudflare one-time setup

In the Cloudflare dashboard:

1. Create a **Worker** (static assets) named e.g. `<product>-docs`.
2. Attach custom domain `docs.<product-domain>` (zone already on Cloudflare, or
   CNAME from the registrar).
3. Issue an API token with Workers/Pages Edit on the account.

`docs-site/wrangler.toml`:

```toml
# Worker-with-static-assets (Cloudflare's current default for static sites).
# Deploy with `wrangler deploy`, not `wrangler pages deploy`.
name = "<product>-docs"
compatibility_date = "2026-07-02"
# Custom domain is dashboard-managed — do not require a workers.dev subdomain.
workers_dev = false

[assets]
directory = "./site"
# Multi-page MkDocs site, not an SPA.
not_found_handling = "404-page"
```

No `main` Worker script is required — Cloudflare serves `./site` directly.

### 9. Ship script

`scripts/docs_ship.sh`:

```bash
#!/usr/bin/env bash
# gate + strict build + wrangler deploy. Never touches the app process.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then set -a; . ./.env; set +a; fi

echo "==> drift gate"
.venv/bin/python -m pytest tests/docs -q

echo "==> build (strict)"
uv run --group docs mkdocs build --strict -f docs-site/mkdocs.yml

if [[ "${1:-}" == "--build-only" ]]; then
  echo "==> site at docs-site/site (skipping deploy)"
  exit 0
fi

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
( cd docs-site && npx --yes wrangler@3 deploy )
echo "==> live at https://docs.<product-domain>"
```

Fold `pytest tests/docs` (and optionally the ship script's build-only mode) into
the project's nightly / quality loop so drift is caught without requiring PR CI.

### 10. Content authoring method

1. Start from **stories**: each persona's `actor`-matched stories give "what they
   do"; `happy_path_outcome` is the success beat; `given/when/then` seeds steps.
2. Ground non-obvious flows against the live UI with the project's QA harness
   (AegisMark: `/qa-tenant` magic-link + Playwright MCP) — the same traces that
   become videos later.
3. Write warm, task-oriented prose. Prefer how-tos for workflows shared across
   personas; prefer guides for "a day in the life".
4. On every how-to page, leave an explicit video slot (even as a one-line
   placeholder) so phase 2 has a home:

   ```markdown
   *A short screen recording of this flow will appear here in a later release.*
   ```

### 11. Checklist (first ship)

- [ ] `docs` dependency group + `uv lock`
- [ ] `docs-site/` MkDocs project + brand overrides (optional)
- [ ] `*/docsite/{facts,drift,macros}.py` + `tests/docs/` green under
      `coverage_mode: partial`
- [ ] Getting Started + ≥1 persona guide + ≥1 how-to live
- [ ] `mkdocs build --strict` succeeds; macros resolve (no raw `{{` in HTML)
- [ ] Cloudflare Worker + custom domain attached
- [ ] `CLOUDFLARE_*` in `.env`; `docs_ship.sh` deploys
- [ ] `docs` reserved in tenant slug blocklist (if multi-tenant)
- [ ] Drift gate wired into nightly / local quality loop
- [ ] Flip to `coverage_mode: complete` only when every user-facing persona has
      a guide and every user-facing workspace is referenced

---

## Upstream ladder

Ship the **recipe as documentation first**. Framework code extraction is
optional and should follow real second-consumer demand.

| Stage | What lands in Dazzle | When |
|-------|----------------------|------|
| **A. Guide** | This document as `docs/guides/product-docs-site.md` (+ nav entry) | Now — zero risk, unblocks every app |
| **B. Scaffold** | `dazzle docs site init` writes the `docs-site/` skeleton, wrangler.toml, ship script stubs, and a minimal `docsite/` package | When ≥2 apps adopt the guide |
| **C. Library** | Promote facts/drift/macros into `dazzle.docsite` (project package becomes a thin config: platform personas, coverage mode, docs path) | When the AegisMark + second-consumer packages diverge only in config |
| **D. Trace→video** | Shared pipeline: Playwright `trace.zip` → narration script → TTS → MP4/WebM assets embedded on how-to pages; drift extends to "video asset present for every how-to with `video: required`" | Separate design; depends on stable QA-trace capture in consumers |

Stage A is the ask of this draft. B–D are not blockers.

### Suggested Stage B CLI shape

```bash
dazzle docs site init \
  --domain docs.example.com \
  --worker-name example-docs \
  --coverage-mode partial
```

Writes the layout in §1, a starter `index.md`, and documents the Cloudflare
dashboard steps. Does **not** create the Cloudflare resource (operator concern,
same posture as `dazzle deploy plan`).

### Suggested Stage C package surface

```python
from dazzle.docsite import load_facts, check_drift, parse_manifests, define_env

facts = load_facts(
    project_dir=".",
    platform_personas={"super_admin"},   # project policy
)
report = check_drift(facts, parse_manifests(Path("docs-site/docs")),
                     coverage_mode="complete")
```

MkDocs macros keep working via `define_env` re-export.

---

## Phase 2 sketch — Playwright traces → evergreen video

Not in v1. Captured here so the text recipe stays aligned with the long-term
shape.

```
qa harness (persona walk)          how-to page front-matter
        │                                    │
        ▼                                    ▼
  trace.zip  ──►  frame extract  ──►  AI narration  ──►  TTS
        │              │                   │              │
        └──────────────┴───────────────────┴──────────────┘
                                    │
                                    ▼
                         MP4/WebM + VTT captions
                                    │
                                    ▼
              docs-site/docs/how-to/<task>.md  embeds asset
              (built into static site; CDN-cached with the rest)
```

**Invariants for later design work:**

1. **Traces are the ground truth for UI steps**, not the prose. Re-record when
   the happy path changes; regenerate video; re-ship docs.
2. **How-to pages are the only video anchors** (not persona guides) — one
   workflow, one asset, re-used from every guide that links it.
3. **Narration is generated, not hand-edited forever** — hand polish is fine,
   but regeneration must be cheap enough to re-run after every material UX
   change.
4. **Assets are build artefacts or versioned binaries** under something like
   `docs-site/docs/assets/video/` — never hot-linked from the app process.
5. **Extend the drift gate**, don't invent a second one: e.g.
   `video: required` in how-to front-matter → Tier 1 fails if the asset is
   missing after the flip to complete coverage.

AegisMark already produces Playwright `trace.zip` from `/qa-tenant` and
`/qa-flow`; filmstrip extraction exists for QA reports. Phase 2 reuses that
capture path rather than inventing a second walker.

---

## Filing checklist

- [x] Guide text ready (this file)
- [x] Filed: https://github.com/manwithacat/dazzle/issues/1612
- [x] Landed as `docs/guides/product-docs-site.md` + `mkdocs.yml` Guides nav
- [x] Linked from `docs/reference/deployment.md`
- [ ] AegisMark keeps `pipeline/docsite/` as the reference implementation until
      Stage C; no pin-bump required for Stage A
- [ ] Stage B/C when second consumer appears (track on #1612 or a follow-up)

## Alternatives considered (and rejected for the recipe)

| Alternative | Why not default |
|-------------|-----------------|
| Serve docs from the Dazzle app / tenant host | Couples public docs to app deploys, auth, and tenant middleware; wrong failure domain |
| Cloudflare git-connected auto-build | Build needs the pinned Dazzle for macros; build-local + upload-static is robust without CI |
| Sphinx / Docusaurus | MkDocs Material is already Dazzle's docs stack (ADR-0001) and Python-native for the gate |
| Hand-maintained labels only (no macros) | Labels drift; macros make facts evergreen by construction |
| Hard-fail full coverage from day one | Pilots self-block; tiered `coverage_mode` is what made the first ship possible |

---

## Reference map (AegisMark → recipe §)

| AegisMark path | Recipe section |
|----------------|----------------|
| `docs-site/` | §1, §3 |
| `pipeline/docsite/facts.py` | §5 |
| `pipeline/docsite/drift.py` | §6 |
| `pipeline/docsite/macros.py` | §4 |
| `tests/docs/` | §6, §9 |
| `scripts/docs_ship.sh` | §9 |
| `docs-site/wrangler.toml` | §8 |
| `pyproject.toml` `[dependency-groups].docs` | §2 |
| Design spec `docs/superpowers/specs/2026-07-01-evergreen-docs-site-design.md` | full rationale |
| Live site | https://docs.aegismark.ai |
