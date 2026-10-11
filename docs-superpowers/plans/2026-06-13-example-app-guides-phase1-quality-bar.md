# Phase 1 — Guide Quality Bar + Fast Static Gate (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fast (`pytest -m "not e2e"`) gate that encodes the per-persona guide quality bar across every example app — terseness, in-fiction copy, closes-the-loop, and per-persona coverage — green against today's state, ratcheting Phase 2 toward universal coverage.

**Architecture:** One new characterization-gate module, `tests/unit/test_example_guide_bar.py`. It loads each example AppSpec via `load_project_appspec` (which already raises on concordance failure, so concordance is enforced for free), runs the quality lints over every declared guide, and asserts a coverage **partition**: every interactive persona is either covered by a conforming guide, deliberately `EXEMPT` (admins/power-users), or on the explicit `PENDING` Phase-2 worklist. A hygiene test ratchets the registries so Phase 2 can't author a guide and forget to clear the worklist.

**Tech Stack:** Python 3.12+, `uv`, pytest. No production-code changes — the "implementation" being validated is the example guides themselves (authored in Phase 2). These tests are green now and drive future work.

**Design source:** `docs/superpowers/specs/2026-06-13-example-app-guides-design.md` (Strand 1 + Strand 3 fast tier). The static "rooted-on-landing-surface" check from the spec is **intentionally deferred to Phase 3's e2e walk** — landing-surface is a derived heuristic (no explicit IR concept; see the design's Open Items), so the runtime walk proves rootedness far more reliably than a static guess.

---

## Key IR facts (verified 2026-06-13)

- Load: `from dazzle.core.appspec_loader import load_project_appspec` → `load_project_appspec(project_root: Path) -> AppSpec`. **Runs guide concordance during load** (`linker.py:254` raises `LinkError` on guide errors) — so a successful load already proves concordance.
- Guides: `appspec.guides: list[GuideSpec]` (`ir/appspec.py:210`). `GuideSpec`: `name, title, audience, steps, step_order, on_complete`. `GuideStep`: `name, kind, title, body, target, placement, cta_label, cta_target, complete_on, audience_when` (`ir/onboarding.py`). `on_complete` is `GuideOnComplete | None` with `.redirect`.
- Personas: `appspec.personas: list[PersonaSpec]` (`ir/appspec.py:137`). Identity is **`.id`** (no `.name`). `interactive: bool` (default True) flags login personas. `default_workspace: str | None`.
- Audience predicate: a raw string like `persona = customer` or `persona = agent or persona = manager`. Extract persona ids with the same regex the linker uses: `r"\bpersona\s*=\s*([A-Za-z_][A-Za-z0-9_]*)"`.

## Empirical baseline (measured 2026-06-13)

Existing copy: 7 guides / 23 steps; body 59–130 chars (mean 93), title 13–40, 2–4 steps/guide → caps **body ≤ 200, title ≤ 60, steps ≤ 6** pass all with headroom. Zero meta-phrase hits today.

Coverage state (interactive personas; `admin`-like = EXEMPT, rest without a guide = PENDING):

| app | covered by a guide | EXEMPT (no guide) | PENDING (Phase 2) |
|-----|--------------------|--------------------|-------------------|
| simple_task | admin | — | manager, member |
| contact_manager | admin | — | user |
| support_tickets | customer, agent, manager | admin | — |
| ops_dashboard | ops_engineer | admin | — |
| fieldtest_hub | engineer, tester | admin | manager |
| project_tracker | — | admin | manager, member |
| design_studio | — | admin | designer, reviewer |
| llm_ticket_classifier | — | admin | support_agent, supervisor |
| acme_billing | — | admin | org_owner, auditor, project_member, external_contractor |
| hr_records | — | hr_admin | manager, finance, employee |
| invoice_ops | — | tenant_admin, finance_admin | requester, approver, finance, auditor |

(simple_task/contact_manager admins already *have* a guide, so they're "covered", not EXEMPT — a Phase-2 note: those two guides target the exempt admin while end-users go without; Phase 2 will author the end-user guides on the PENDING list and may re-target.)

---

### Task 1: Scaffold the gate module + helpers + load smoke test

**Files:** Create `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Write the module skeleton with helpers and a load smoke test**

```python
"""Fast gate: the per-persona guide quality bar across every example app.

Companion to ``test_example_guides_concordance.py`` (which runs concordance
on the apps that already ship guides). This module:

  * lints every declared guide against the terseness / in-fiction /
    closes-the-loop bar, and
  * asserts a coverage PARTITION — every interactive persona is either
    covered by a conforming guide, deliberately EXEMPT, or on the explicit
    PENDING Phase-2 worklist.

Concordance itself is enforced for free: ``load_project_appspec`` raises
``LinkError`` if any guide's target/event/field/CTA-permit fails to resolve.

Design: docs/superpowers/specs/2026-06-13-example-app-guides-design.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"

# Quality-bar thresholds (calibrated against the 7 existing guides:
# body max 130, title max 40, max 4 steps — caps leave deliberate headroom).
MAX_BODY_CHARS = 200
MAX_TITLE_CHARS = 60
MAX_STEPS_PER_GUIDE = 6

# In-fiction lint: high-signal meta tokens that break kayfabe. Conservative
# by design (zero false positives on the current corpus); widen only if a
# real meta-leak slips through.
_META_TOKENS = re.compile(
    r"\b(dazzle|showcase|demonstrat\w*|this demo|example app|sample data)\b",
    re.IGNORECASE,
)

_PERSONA_REF = re.compile(r"\bpersona\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")


def _examples() -> list[str]:
    """Every example app (a dir under examples/ with a dazzle.toml).

    Reads disk so it auto-tracks the Phase 0 reclassification (11 apps).
    """
    return sorted(
        p.name for p in EXAMPLES_DIR.iterdir() if (p / "dazzle.toml").is_file()
    )


def _load(app: str):
    return load_project_appspec(EXAMPLES_DIR / app)


def _audience_personas(audience: str | None) -> set[str]:
    return set(_PERSONA_REF.findall(audience or ""))


def _interactive_personas(appspec) -> set[str]:
    return {p.id for p in appspec.personas if getattr(p, "interactive", True)}


def _personas_with_guide(appspec) -> set[str]:
    covered: set[str] = set()
    for g in appspec.guides:
        covered |= _audience_personas(g.audience)
    return covered


@pytest.mark.parametrize("app", _examples())
def test_example_appspec_loads(app: str) -> None:
    """Every example loads (which also enforces guide concordance)."""
    appspec = _load(app)
    assert appspec is not None
    # personas list is the substrate the coverage gate depends on
    assert isinstance(appspec.personas, list)
```

- [ ] **Step 2: Run the smoke test — confirm all 11 examples load**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_example_appspec_loads -q`
Expected: 11 passed (one per example). If any example raises `LinkError`, a guide there has a concordance break — STOP and fix that guide (it's a real regression), do not weaken the gate.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): scaffold example guide-bar gate + load smoke test"
```

---

### Task 2: Terseness lint

**Files:** Modify `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Add the terseness test**

```python
@pytest.mark.parametrize("app", _examples())
def test_guide_copy_is_terse(app: str) -> None:
    """Overlay copy stays terse — body/title under cap, <= 6 steps/guide.

    Onboarding overlays nobody reads a paragraph in; the cap is the
    structural enforcement of the design's "terse, in-fiction" rule and
    the parking of the externalised-content layer (Option B).
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        if len(g.steps) > MAX_STEPS_PER_GUIDE:
            problems.append(
                f"guide {g.name!r}: {len(g.steps)} steps > {MAX_STEPS_PER_GUIDE} cap"
            )
        for s in g.steps:
            if len(s.body) > MAX_BODY_CHARS:
                problems.append(
                    f"guide {g.name!r} step {s.name!r}: body {len(s.body)} chars "
                    f"> {MAX_BODY_CHARS} cap — tighten it or move long-form content "
                    f"to a help surface (overlays must stay terse)"
                )
            if len(s.title) > MAX_TITLE_CHARS:
                problems.append(
                    f"guide {g.name!r} step {s.name!r}: title {len(s.title)} chars "
                    f"> {MAX_TITLE_CHARS} cap"
                )
    assert not problems, f"{app}: terseness violations:\n  " + "\n  ".join(problems)
```

- [ ] **Step 2: Run it — confirm green against existing guides**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_guide_copy_is_terse -q`
Expected: 11 passed (the 7 existing guides are well under cap; the 4 guide-less apps have nothing to check).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): terseness lint (body<=200, title<=60, <=6 steps)"
```

---

### Task 3: In-fiction lint

**Files:** Modify `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Add the in-fiction test**

```python
@pytest.mark.parametrize("app", _examples())
def test_guide_copy_is_in_fiction(app: str) -> None:
    """Guide copy speaks as the product, never as a meta demo.

    Kayfabe: a guide says "File a ticket", never "this example shows
    bar_chart". Conservative high-signal token list (zero false positives
    on the current corpus).
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        for s in g.steps:
            for field_name, text in (("title", s.title), ("body", s.body)):
                hit = _META_TOKENS.search(text)
                if hit:
                    problems.append(
                        f"guide {g.name!r} step {s.name!r} {field_name}: meta phrase "
                        f"{hit.group(0)!r} breaks kayfabe — write as the product"
                    )
    assert not problems, f"{app}: in-fiction violations:\n  " + "\n  ".join(problems)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_guide_copy_is_in_fiction -q`
Expected: 11 passed (current corpus has zero meta-token hits).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): in-fiction copy lint (no meta tokens)"
```

---

### Task 4: Closes-the-loop lint

**Files:** Modify `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Add the on_complete.redirect test**

```python
@pytest.mark.parametrize("app", _examples())
def test_guide_closes_the_loop(app: str) -> None:
    """Every guide ends by sending the user somewhere useful.

    A guide that finishes without an ``on_complete.redirect`` leaves the
    user stranded on the last step's surface. All 7 existing guides set it.
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        redirect = getattr(g.on_complete, "redirect", None) if g.on_complete else None
        if not redirect:
            problems.append(
                f"guide {g.name!r}: missing on_complete.redirect — a finished "
                f"guide must route the user to their home surface"
            )
    assert not problems, f"{app}: closes-the-loop violations:\n  " + "\n  ".join(problems)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_guide_closes_the_loop -q`
Expected: 11 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): closes-the-loop lint (on_complete.redirect required)"
```

---

### Task 5: Coverage partition + EXEMPT/PENDING registries

**Files:** Modify `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Add the registries and the coverage partition test**

```python
# --- Coverage registries -------------------------------------------------
#
# Every interactive persona of every example must be in exactly one bucket:
#   1. covered by a conforming guide (audience names the persona), OR
#   2. EXEMPT — deliberately no guide (admins / power users; overlays are
#      friction for them — the support_tickets onboarding.dsl comment), OR
#   3. PENDING — the Phase-2 authoring worklist; a guide is owed.
#
# Phase 2 shrinks PENDING to {} as it authors guides (the hygiene ratchet in
# test_guide_registry_hygiene fails if a PENDING persona gains a guide but
# isn't removed here). A persona may move PENDING -> EXEMPT only with a
# one-line rationale added below.

# Admins / power users that deliberately get NO onboarding overlay.
_GUIDE_EXEMPT: dict[str, set[str]] = {
    "support_tickets": {"admin"},
    "ops_dashboard": {"admin"},
    "fieldtest_hub": {"admin"},
    "project_tracker": {"admin"},
    "design_studio": {"admin"},
    "llm_ticket_classifier": {"admin"},
    "acme_billing": {"admin"},
    "hr_records": {"hr_admin"},
    "invoice_ops": {"tenant_admin", "finance_admin"},
}

# Interactive personas still owed a guide (Phase 2 worklist). Shrinks to {}.
_PENDING_GUIDE_AUTHORING: dict[str, set[str]] = {
    "simple_task": {"manager", "member"},
    "contact_manager": {"user"},
    "fieldtest_hub": {"manager"},
    "project_tracker": {"manager", "member"},
    "design_studio": {"designer", "reviewer"},
    "llm_ticket_classifier": {"support_agent", "supervisor"},
    "acme_billing": {"org_owner", "auditor", "project_member", "external_contractor"},
    "hr_records": {"manager", "finance", "employee"},
    "invoice_ops": {"requester", "approver", "finance", "auditor"},
}


@pytest.mark.parametrize("app", _examples())
def test_guide_coverage_partition(app: str) -> None:
    """Every interactive persona is covered, exempt, or explicitly pending.

    This is the gate that drives Phase 2: an interactive persona that is
    neither covered nor classified FAILS, forcing either a guide or an
    explicit EXEMPT/PENDING decision.
    """
    appspec = _load(app)
    interactive = _interactive_personas(appspec)
    covered = _personas_with_guide(appspec) & interactive
    exempt = _GUIDE_EXEMPT.get(app, set())
    pending = _PENDING_GUIDE_AUTHORING.get(app, set())

    unclassified = interactive - covered - exempt - pending
    assert not unclassified, (
        f"{app}: interactive persona(s) {sorted(unclassified)} have no guide and "
        f"aren't EXEMPT or PENDING. Author a guide whose audience names them, or "
        f"add them to _GUIDE_EXEMPT (with rationale) / _PENDING_GUIDE_AUTHORING in "
        f"tests/unit/test_example_guide_bar.py."
    )
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_guide_coverage_partition -q`
Expected: 11 passed (every interactive persona is covered/exempt/pending per the table).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): per-persona coverage partition + EXEMPT/PENDING registries"
```

---

### Task 6: Registry hygiene ratchet

**Files:** Modify `tests/unit/test_example_guide_bar.py`

- [ ] **Step 1: Add the hygiene test**

```python
def test_guide_registry_hygiene() -> None:
    """The coverage registries stay honest as Phase 2 progresses.

    - EXEMPT and PENDING name only real interactive personas of real apps.
    - No persona is in both EXEMPT and PENDING.
    - No PENDING persona already has a guide (the ratchet: Phase 2 must
      remove a persona from PENDING when it authors that persona's guide).
    """
    examples = set(_examples())
    problems: list[str] = []

    for registry_name, registry in (
        ("_GUIDE_EXEMPT", _GUIDE_EXEMPT),
        ("_PENDING_GUIDE_AUTHORING", _PENDING_GUIDE_AUTHORING),
    ):
        for app, personas in registry.items():
            if app not in examples:
                problems.append(f"{registry_name}: {app!r} is not an example app")
                continue
            interactive = _interactive_personas(_load(app))
            ghosts = personas - interactive
            if ghosts:
                problems.append(
                    f"{registry_name}[{app!r}]: {sorted(ghosts)} are not interactive "
                    f"personas of {app}"
                )

    for app in examples:
        exempt = _GUIDE_EXEMPT.get(app, set())
        pending = _PENDING_GUIDE_AUTHORING.get(app, set())
        both = exempt & pending
        if both:
            problems.append(f"{app}: {sorted(both)} in BOTH EXEMPT and PENDING")
        covered = _personas_with_guide(_load(app))
        stale = pending & covered
        if stale:
            problems.append(
                f"{app}: {sorted(stale)} are PENDING but already have a guide — "
                f"remove them from _PENDING_GUIDE_AUTHORING (Phase 2 ratchet)"
            )

    assert not problems, "guide registry hygiene:\n  " + "\n  ".join(problems)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_example_guide_bar.py::test_guide_registry_hygiene -q`
Expected: 1 passed. If it fails on a "ghost" persona, the registry has a typo vs the app's real persona ids — fix the registry.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_example_guide_bar.py
git commit -m "test(guides): registry hygiene ratchet (no ghosts, no stale PENDING)"
```

---

### Task 7: Full-module verification, bump & ship

**Files:** the new test module + version-bump files.

- [ ] **Step 1: Run the whole new module**

Run: `uv run pytest tests/unit/test_example_guide_bar.py -q`
Expected: all pass (≈ 45 cases: 11 apps × 4 parametrized lints + 1 hygiene).

- [ ] **Step 2: Lint + type-check the new file**

Run:
```bash
uv run ruff format tests/unit/test_example_guide_bar.py
uv run ruff check tests/unit/test_example_guide_bar.py
uv run mypy src/dazzle
```
Expected: ruff clean; mypy `Success` (the test file isn't under `src/`, but run mypy to confirm no incidental breakage).

- [ ] **Step 3: Confirm the gate runs inside the fast suite selector**

Run: `uv run pytest tests/unit/test_example_guide_bar.py -m "not e2e" -q`
Expected: same pass count (the module carries no e2e marker, so it's in the fast suite).

- [ ] **Step 4: Bump the patch version**

Run the `/bump patch` skill steps. CHANGELOG entry:
```markdown
### Added
- **Guide quality-bar fast gate** (`tests/unit/test_example_guide_bar.py`, example-guides
  Phase 1). Every example app's onboarding guides are now linted on every commit for
  terseness (body ≤200 / title ≤60 / ≤6 steps), in-fiction copy (no meta tokens), and
  closes-the-loop (`on_complete.redirect`); concordance is enforced for free at load.
  A per-persona **coverage partition** asserts every interactive persona is covered by a
  guide, deliberately EXEMPT (admins), or on an explicit PENDING Phase-2 worklist, with a
  hygiene ratchet so authoring a guide must clear its worklist entry.

### Agent Guidance
- When adding/editing an example guide, keep `body` ≤200 chars and speak as the product
  (no "demo"/"Dazzle"/"showcase"). New interactive personas must be covered by a guide or
  classified in `_GUIDE_EXEMPT`/`_PENDING_GUIDE_AUTHORING` in `test_example_guide_bar.py`.
```

- [ ] **Step 5: Sync uv.lock + single commit + tag + push** (substitute the bumped `X.Y.Z`)

```bash
cd /Volumes/SSD/Dazzle
sed -i.bak '/name = "dazzle-dsl"/{n;s/version = "[0-9.]*"/version = "X.Y.Z"/;}' uv.lock && rm -f uv.lock.bak
git add -A
git commit -m "feat(guides): example guide quality-bar fast gate (guides Phase 1) — vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
git status --short && echo CLEAN
```

- [ ] **Step 6: Full fast suite (pre-ship gate) before/with the push**

Run: `set -o pipefail; uv run pytest tests/ -m "not e2e" -q 2>&1 | tail -5`
Expected: all pass (prior baseline + the new ~45 cases). If red elsewhere, investigate before considering Phase 1 done.

- [ ] **Step 7: Confirm CI green** (the gate is pure-unit, so the `Python Tests` matrix covers it).

---

## Self-review notes (author)

- **Spec coverage:** implements Strand 1 (quality bar) + Strand 3 fast tier of the design. Concordance (free at load), terseness, in-fiction, closes-loop, per-persona coverage all encoded. The spec's static "rooted-on-landing-surface" is deliberately deferred to Phase 3's e2e walk (documented above + in the design Open Items) — not dropped, relocated to where it's reliably testable.
- **No placeholders:** every test body and both registries are complete with empirically-derived contents.
- **Green-now, ratchet-forward:** all tests pass against today's state; `_PENDING_GUIDE_AUTHORING` is the Phase-2 worklist and the hygiene ratchet forces it to drain.
- **Type/name consistency:** helpers (`_examples`, `_load`, `_audience_personas`, `_interactive_personas`, `_personas_with_guide`) and registry names (`_GUIDE_EXEMPT`, `_PENDING_GUIDE_AUTHORING`) are referenced identically across tasks.
- **Reuse:** mirrors the `_projects()` / `_DOGFOOD_EXEMPT` patterns already in the suite; complements (does not duplicate) `test_example_guides_concordance.py`.
