# Phase 3 — E2E Guide-Walk Oracle (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Prove at runtime that every example guide's declared journey is actually achievable — for each guide, log in as its audience persona, navigate to each step's target surface, and assert the `<dz-onboarding-step>` overlay actually renders there (the real "rooted/reachable" proof that the static gate deferred). Extends the existing `dazzle ux verify --interactions` harness.

**Architecture:** A new `GuideWalkInteraction` (sync `httpx.Client`, server-rendered HTML — no Playwright gestures needed) reuses the managed-boot (`launch_interaction_server`) and `/__test__/authenticate` machinery. A `--guides` mode on `ux verify` builds one walk per guide, authenticating as the guide's audience persona, walking `step_order` (fetch target → assert overlay marker → follow CTA → POST complete → next). Fast-tier coverage already exists (Phase 1 gate); this is the e2e tier.

**Tech Stack:** Python 3.12+, httpx (sync), the existing ux-interactions harness, PostgreSQL (managed boot), GitHub Actions.

**Design source:** `docs/superpowers/specs/2026-06-13-example-app-guides-design.md` §5 (Strand 3 e2e tier). Exploration map: the Phase 3 code-explorer brief (this session).

---

## Key facts (verified via exploration)

- Entry: `dazzle ux verify --interactions --persona <id>` → `cli/ux.py:614` → `run_interaction_walk` (`cli/ux_interactions.py:214`). App = cwd.
- Auth: POST `{site_url}/__test__/authenticate` `{role, username}` + `X-Test-Secret` → `session_token` → `dazzle_session` cookie. (`_authenticate_persona_on_context`, `ux_interactions.py:373`.)
- URL scheme: surfaces route by **entity slug** `/app/{entity_lower}` (NOT surface name). Resolve `step.target` (`surface.<name>`) → surface in `appspec.surfaces` → its `uses entity` → `/app/{entity.lower()}`.
- Overlay marker: `<dz-onboarding-step data-guide="{g}" data-step="{s}" data-kind=... >` (`render/onboarding/renderer.py:_outer_attrs`). CTA anchor `href="/{surface_name}"` (`removeprefix("surface.")`).
- Overlay appears iff: guide exists + persona role matches `audience` + no completed/dismissed progress for that step + current surface == `step.target` surface + `onboarding_state` repo initialized (it is, when guides + DATABASE_URL). (`_inject_onboarding_step`, `page_routes.py:815`; `resolve_active_step`, `resolver.py:115`.)
- Advance: POST `/api/onboarding/{guide}/{step}/complete` (empty 200) updates DB state so the next step resolves on the next fetch. (`back/runtime/onboarding/routes.py`.)
- Boot: `launch_interaction_server(project_root)` (`testing/ux/interactions/server_fixture.py:122`) — spawns `dazzle serve --local`, needs `DATABASE_URL`; reuse as-is.
- CI: `interaction-walks` job (`.github/workflows/ci.yml:541`) — Postgres 16, **no Redis**, single app (support_tickets), persona agent, blocking, 3 retries.
- Interaction protocol + `run_walk`: `testing/ux/interactions/base.py`. Reference impl: `card_add.py`. Unit-test pattern: `tests/unit/test_interaction_walks.py` (`_StubPage`).

---

## Pre-flight forks to settle in Task 0 (resolve from code; escalate only if blocked)

- **F1 Redis bootability:** Which of the 11 examples need `REDIS_URL` to boot? Grep each `dazzle.toml` / dsl for redis/channels/job usage. Apps that need Redis either get a Redis service in the new CI job or are excluded from the e2e walk (still covered by the fast gate). Record the bootable set.
- **F2 Per-persona auth in one process:** `run_interaction_walk` authenticates ONE persona per browser context. For a guide walk we drive httpx directly per guide, so each `GuideWalkInteraction` can hold its own `httpx.Client` authenticated as that guide's audience persona — no Playwright context needed. Confirm the `--guides` path can skip the Playwright browser entirely (faster, fewer deps) OR runs alongside it.
- **F3 CI scope (genuine product decision — may surface):** all 11 apps × their guide personas (comprehensive, ~minutes of CI) vs a representative subset. Default: all bootable apps, matrixed, with the 3-retry pattern; exclude Redis-needing apps if F1 says so.

---

> **Task 0 partially executed 2026-06-13 (de-risking):**
> - **F1 (Redis):** survey across 11 examples — only `simple_task` (messaging.dsl) and
>   `support_tickets` (runtime.dsl) match redis-ish constructs; support_tickets already
>   boots in the existing INTERACTION_WALK CI job **without** a Redis service, so it
>   degrades gracefully. Provisional conclusion: all 11 bootable on Postgres alone;
>   confirm per-app in Task 3/4.
> - **Mechanism PROVEN:** booted support_tickets locally, authed as `customer`, fetched
>   `/app/ticket` (200) — the `<dz-onboarding-step ... data-guide="customer_onboarding"
>   data-step="welcome_empty" ...>` overlay rendered. The guide-walk oracle is viable.
> - **Correction:** the real tag is `<dz-onboarding-step class="..." data-guide="..."
>   data-step="..." data-kind="..." data-placement="...">` — `class` precedes the
>   `data-*` attrs, so the matcher checks `data-guide`/`data-step` independently (applied
>   to the Task 1 impl above).

### Task 0: Settle the forks + confirm the boot+auth+overlay path manually

**Files:** none (investigation) — produces the facts the later tasks hardcode.

- [ ] **Step 1: Redis/boot survey (F1)**

Run:
```bash
cd /Volumes/SSD/Dazzle
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub project_tracker design_studio llm_ticket_classifier acme_billing hr_records invoice_ops; do
  needs=$(grep -rilE "redis|channel|\bjob\b|schedule|stream" examples/$app/dsl/ 2>/dev/null | head -1)
  echo "$app: redis-ish=${needs:-none}"
done
```
Record which apps reference Redis-backed constructs. (Bootability is ultimately proven in Task 4; this is the first filter.)

- [ ] **Step 2: Manually prove the overlay-renders-for-persona path on one app**

With a local Postgres, boot simple_task and fetch a guide step's target surface as the audience persona, asserting the marker. Run:
```bash
cd /Volumes/SSD/Dazzle/examples/simple_task
DATABASE_URL="postgresql://localhost:5432/dazzle_simple_task" uv run python - <<'PY'
# minimal manual probe — boot + auth + fetch + assert marker
from dazzle.testing.ux.interactions.server_fixture import launch_interaction_server
from dazzle.testing.ux.runtime_secret import read_runtime_test_secret  # adjust import per code
import httpx, pathlib
root = pathlib.Path(".")
with launch_interaction_server(root) as conn:
    secret = read_runtime_test_secret(root)
    c = httpx.Client(base_url=conn.site_url, headers={"X-Test-Secret": secret}, follow_redirects=True)
    tok = c.post("/__test__/authenticate", json={"role":"member","username":"member"}).json()["session_token"]
    c.cookies.set("dazzle_session", tok)
    # member_onboarding step 1 target = surface.task_list -> entity Task -> /app/task
    r = c.get("/app/task")
    assert r.status_code == 200, r.status_code
    assert 'dz-onboarding-step data-guide="member_onboarding"' in r.text, "overlay not rendered for member on task_list"
    print("OVERLAY OK")
PY
```
Expected: `OVERLAY OK`. If the marker is absent, diagnose the resolver gate (audience role string, surface-name match, repo init) BEFORE building the generic walk. (This de-risks the whole phase: if the overlay doesn't render for the real persona on the real surface, that's either a guide-rooting bug to fix in Phase 2 copy or a resolver detail to understand.) The exact `read_runtime_test_secret` import path is confirmed in `cli/ux_interactions.py` (it's already imported there) — copy it verbatim.

*(No commit — investigation. Record findings in PLAN.md.)*

---

### Task 1: `GuideWalkInteraction` + helpers (unit-tested with a stub)

**Files:** Create `src/dazzle/testing/ux/interactions/guide_walk.py`; Test `tests/unit/test_interaction_guide_walk.py`

- [ ] **Step 1: Write the failing unit test (stub HTTP, no real server)**

Following `tests/unit/test_interaction_walks.py`'s `_StubPage` pattern, build a `_StubHttp` returning canned responses, and assert `GuideWalkInteraction.execute` passes when every step's target returns the marker and fails when one is missing.

```python
# tests/unit/test_interaction_guide_walk.py
from dazzle.testing.ux.interactions.guide_walk import GuideWalkInteraction, _surface_to_path


def test_surface_to_path_maps_via_entity():
    # surface.task_list (uses entity Task) -> /app/task
    surfaces = [type("S", (), {"name": "task_list", "entity": "Task"})()]
    assert _surface_to_path("surface.task_list", surfaces) == "/app/task"


class _StubHttp:
    def __init__(self, pages, completes=None):
        self._pages = pages  # path -> (status, html)
        self.completed = []
    def get(self, path):
        status, html = self._pages.get(path, (404, ""))
        return type("R", (), {"status_code": status, "text": html})()
    def post(self, path):
        self.completed.append(path)
        return type("R", (), {"status_code": 200, "text": ""})()


def test_guide_walk_passes_when_every_step_renders():
    # 2-step guide; both targets return the marker
    guide = _make_guide("member_onboarding", ["s1", "s2"], targets=["surface.a", "surface.b"])
    surfaces = [_surf("a", "A"), _surf("b", "B")]
    http = _StubHttp({
        "/app/a": (200, '<dz-onboarding-step data-guide="member_onboarding" data-step="s1">'),
        "/app/b": (200, '<dz-onboarding-step data-guide="member_onboarding" data-step="s2">'),
    })
    walk = GuideWalkInteraction(guide=guide, persona="member", surfaces=surfaces, http=http)
    result = walk.execute(page=None)
    assert result.passed, result.detail
    assert http.completed == ["/api/onboarding/member_onboarding/s1/complete",
                              "/api/onboarding/member_onboarding/s2/complete"]


def test_guide_walk_fails_when_a_step_overlay_is_missing():
    guide = _make_guide("member_onboarding", ["s1"], targets=["surface.a"])
    surfaces = [_surf("a", "A")]
    http = _StubHttp({"/app/a": (200, "<div>no overlay here</div>")})
    walk = GuideWalkInteraction(guide=guide, persona="member", surfaces=surfaces, http=http)
    result = walk.execute(page=None)
    assert not result.passed
    assert "overlay" in result.detail.lower()
```

(Define the `_make_guide`, `_surf` helpers inline using `SimpleNamespace` to mirror `GuideSpec`/`GuideStep`/surface shape — `guide.name`, `guide.step_order`, `guide.steps[i].name/target/cta_target`, surface `.name/.entity`.)

- [ ] **Step 2: Run — expect failure (module missing)**

Run: `uv run pytest tests/unit/test_interaction_guide_walk.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement `guide_walk.py`**

```python
"""Guide-walk oracle: prove a guide's journey renders for its audience persona."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.testing.ux.interactions.base import InteractionResult


def _surface_to_path(target: str, surfaces: list[Any]) -> str | None:
    """Map a guide step target (surface.<name>) to its runtime URL /app/<entity>."""
    name = target.removeprefix("surface.").split(".")[0]
    for s in surfaces:
        if getattr(s, "name", None) == name:
            entity = getattr(s, "entity", None) or getattr(s, "entity_name", None)
            if entity:
                return f"/app/{entity.lower()}"
    return None


@dataclass
class GuideWalkInteraction:
    guide: Any
    persona: str
    surfaces: list[Any]
    http: Any  # sync client exposing .get(path) and .post(path)
    label: str = field(default="")

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"guide-walk:{self.persona}:{self.guide.name}"

    def execute(self, page: Any = None) -> InteractionResult:  # noqa: ANN401
        steps = {s.name: s for s in self.guide.steps}
        for step_name in self.guide.step_order:
            step = steps.get(step_name)
            if step is None:
                return InteractionResult(self.label, False, f"step_order names unknown step {step_name!r}")
            path = _surface_to_path(step.target, self.surfaces)
            if path is None:
                return InteractionResult(self.label, False, f"could not resolve {step.target!r} to a URL")
            resp = self.http.get(path)
            if resp.status_code != 200:
                return InteractionResult(self.label, False, f"{path} returned {resp.status_code} for {self.persona}")
            # Attribute order is NOT guaranteed — the real tag is
            # `<dz-onboarding-step class="..." data-guide="..." data-step="..." ...>`
            # (class precedes the data-* attrs; verified by the Task 0 probe).
            # Match the two identifying attributes independently.
            if (
                "dz-onboarding-step" not in resp.text
                or f'data-guide="{self.guide.name}"' not in resp.text
                or f'data-step="{step_name}"' not in resp.text
            ):
                return InteractionResult(
                    self.label, False,
                    f"overlay for step {step_name!r} did not render on {path} as {self.persona} "
                    f"(guide promises it but the runtime didn't show it)",
                )
            cta = getattr(step, "cta_target", None)
            if cta:
                cta_path = _surface_to_path(cta, self.surfaces)
                if cta_path is not None:
                    cresp = self.http.get(cta_path)
                    if cresp.status_code != 200:
                        return InteractionResult(self.label, False, f"cta {cta} -> {cta_path} returned {cresp.status_code}")
            # advance guide state so the next step resolves
            self.http.post(f"/api/onboarding/{self.guide.name}/{step_name}/complete")
        return InteractionResult(self.label, True, f"{len(self.guide.step_order)} step(s) rendered for {self.persona}")
```

(Verify `InteractionResult`'s exact constructor signature in `base.py` and match it — adjust field names/order if it differs, e.g. `InteractionResult(label=..., passed=..., detail=...)`.)

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/unit/test_interaction_guide_walk.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/interactions/guide_walk.py tests/unit/test_interaction_guide_walk.py && \
git commit -m "feat(ux): GuideWalkInteraction — assert a guide's overlay renders per step (guides Phase 3)"
```

---

### Task 2: `--guides` mode on `dazzle ux verify` + `_build_guide_walk`

**Files:** Modify `src/dazzle/cli/ux_interactions.py` (add `_build_guide_walk`, a `run_guide_walk` driver, or extend `run_interaction_walk`); `src/dazzle/cli/ux.py` (add `--guides` flag); Test `tests/unit/test_cli_ux_interactions.py` (assembly-function test).

- [ ] **Step 1: Write the failing assembly test**

```python
def test_build_guide_walk_one_per_guide_filtered_by_persona(tmp_path):
    from dazzle.cli.ux_interactions import _build_guide_walk
    # load a real example appspec; build walks for persona 'member'
    walks = _build_guide_walk(EXAMPLES / "simple_task", persona="member", http=_FakeHttp())
    labels = [w.label for w in walks]
    assert any("member_onboarding" in l for l in labels)
    assert all("member" in l for l in labels)  # only member-audience guides
```

- [ ] **Step 2: Run — FAIL (function missing).**

- [ ] **Step 3: Implement `_build_guide_walk`** — load appspec, filter `appspec.guides` whose audience admits `persona` (reuse the `_PERSONA_REF`-style extraction already used in the Phase-1 gate, or `_audience_matches_persona` from `resolver.py`), build one `GuideWalkInteraction(guide, persona, surfaces=appspec.surfaces, http=<sync client>)` each. Add a `run_guide_walk(project_root, *, persona, json_output)` that boots via `launch_interaction_server`, builds an authed sync `httpx.Client` (mirror `_authenticate_persona_on_context`'s POST), assembles walks, runs them via `run_walk`-equivalent, reports, returns the 0/1/2 exit code. Add `--guides` to `ux.py:verify_command`, dispatching to `run_guide_walk` when set.

- [ ] **Step 4: Run the assembly test + existing ux-interactions tests — PASS.**

Run: `uv run pytest tests/unit/test_cli_ux_interactions.py tests/unit/test_interaction_guide_walk.py -q`.

- [ ] **Step 5: Commit.**

---

### Task 3: Local end-to-end smoke against 2-3 apps

**Files:** none (manual verification) — proves the real harness works before CI.

- [ ] **Step 1:** With local Postgres, for simple_task (member, manager), contact_manager (user), and one read-only app (hr_records/employee):
```bash
cd examples/<app> && DATABASE_URL=... uv run dazzle ux verify --interactions --guides --persona <p> --headless
```
Expected exit 0 with per-guide PASS lines. Any FAIL is a real finding: the guide promises a journey the app can't render for that persona — fix the guide (Phase 2 copy/target) or the app, re-run. Record results in PLAN.md.

*(No commit — but any guide fix committed under its app.)*

---

### Task 4: CI wiring (settle F3 scope) + full gate

**Files:** Modify `.github/workflows/ci.yml`.

- [ ] **Step 1:** Add guide-walk steps to the `interaction-walks` job (or a new `guide-walks` job) as a matrix over the **bootable** example apps (from Task 0/3), each `cd examples/${{matrix.app}}` running `dazzle ux verify --interactions --guides` per the app's guide personas, with the existing 3-retry pattern. Add a Redis service only if Task 0 proved an in-scope app needs it (else exclude those apps and `log()` the exclusion). Keep it blocking.

- [ ] **Step 2:** Local CI-shape check: run the exact command(s) the job will run for 2 apps locally (Task 3 already does this). The workflow YAML itself can only be fully validated by a CI run (per the local-composite-action memory).

- [ ] **Step 3: Full gate + ship.** `uv run ruff check src/ tests/ && uv run mypy src/dazzle && uv run pytest tests/ -m "not e2e" -q`; `/bump patch`; commit (`&&`-chained: commit && tag && push); confirm CI green (the new guide-walk job must pass).

---

## Self-review notes (author)

- **Spec coverage:** implements Strand 3 e2e tier — the guide-walk-as-oracle. The "rooted on landing surface" check the fast gate deferred is realized here as "the overlay actually renders for the audience persona on the step's surface."
- **Smallest change:** reuses `launch_interaction_server` + `/__test__/authenticate` + `run_walk`; adds one Interaction + one mode + CI steps. No new boot machinery, no new deps (httpx already present).
- **Forks surfaced, not guessed:** F1 (Redis) and F3 (CI scope) are settled empirically in Task 0/4; if an in-scope app can't boot in CI without new services, that's surfaced rather than silently dropped (`log()` the exclusion — no silent caps).
- **Type consistency:** `_surface_to_path`, `GuideWalkInteraction(guide, persona, surfaces, http)`, `InteractionResult(label, passed, detail)` used identically across Tasks 1–2 (verify `InteractionResult`'s real signature in base.py at impl time).
