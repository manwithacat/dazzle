# Phase 2 — VIEW: make the substrate the universal detail render path, retire `render_detail_view`

> **For agentic workers:** execute task-by-task (superpowers:executing-plans), Hybrid mode — inline TDD + an independent adversarial review before the flip (Task 5) and the delete (Task 6). Follows the exact arc proven in Phase 1 (`2026-06-29-substrate-universal-list-phase1.md`, shipped v0.92.15–19).

**Goal:** Every `mode: view` (detail) surface renders through the typed Fragment substrate (`_build_view`); then **delete** the legacy `render_detail_view` (~635 LOC, `page/runtime/detail_renderer.py`) and repoint its callers, with no fallback (ADR-0049 D4).

**Decisions (inherited, locked):** D1 visual—not byte—parity (substrate DOM canonical; re-baseline + gate on `dazzle ux verify` / card-safety composite / a11y). D2 N/A for view (no skeleton/hydrate — detail is server-rendered inline). D4 no silent legacy fallback post-delete. D5 view is this phase; create/edit is Phase 3.

## Step-0 gap-diff (legacy `render_detail_view` vs substrate `_build_view`)

Substrate `_build_view` already has: fields (Row of Heading4+Text), an action toolbar via `_build_detail_actions` (Edit/transitions/integration/external/Delete), related-group regions (as **Skeleton placeholders**). Gaps:

| Element | Legacy | Substrate | Disposition |
|---|---|---|---|
| **RBAC action anchors** | `data-dazzle-action="{entity}.edit/.delete/.transition.{s}/.external.{n}/.integration.{i}.{m}"` on each action | plain `Link`/`Button`, **no `data-dazzle-action`** | **BUILD** — the RBAC contract checker keys off these; without them the detail loses RBAC verification (parallels Phase 1's CreateButton anchor). |
| **htmx wiring on actions** | Delete `hx-delete`+`hx-confirm`, transitions `hx-put`+`hx-vals`, external `target=_blank` | Delete has hx_*; transitions Button has hx_put? (verify); external = plain Link | **VERIFY/BUILD** — confirm transition `hx-vals` (status_field→to_state) + external new-tab. |
| **Back button** | header Back `<a>` with drawer-close/history-back JS | none | **DECISION** — build a substrate Back affordance, or drop (peek/drawer close is separate). Flag for review. |
| **Delete confirm semantics** | `hx-confirm` | Button hx_confirm | OK (verify). |
| **Related groups** | actual related content (verify what legacy renders) | **Skeleton(lines=3) placeholder** | **DECISION** — legacy related-group content vs substrate placeholder. If legacy renders real content, this is a real gap; if it's also a placeholder, parity holds. Verify in Task 1. |
| **`<dt>/<dd>` field structure** | `dz-detail` definition list | Row(Heading4, Text) | substrate-canonical (D1) — re-baseline. |
| **peek `?peek=1` detail-body** | peek 4a (v0.92.14) serves the legacy detail **body** partial | — | **CRITICAL** — peek's content-only body currently rides the legacy path; converging detail must keep peek working (serve the substrate detail body for `?peek=1`). Trace `is_peek_request`/`_render_response` peek branch + `resolve_peek_mode`. |

**Callers of `render_detail_view`** (grep at Task 6): `template_renderer._render_body_inner` (detail branch — the sole legacy detail producer + the D4 loud-error target), `experience_renderer` (the detail STEP — same `page ↛ http` repoint as Phase 1's table-step, via the http experience route), the **peek** body partial path, and any `_render_response`/`pdf_viewer` seam. **Sweep `render_detail_view(` / `render_page(` for detail ctx — Phase 1's lesson: the E2E (PostgreSQL) tier catches missed callers the unit suite can't (build-ui/serve/fidelity).**

## Tasks

- [ ] **Task 1 — Characterize** the legacy detail chrome (`render_detail_view`) across a matrix (no-actions / edit+delete / transitions / external / integration / related-groups / empty) → committed fixtures `tests/unit/__snapshots__/legacy_detail_chrome/` (visual-parity reference; exclude dir from whitespace/eof pre-commit hooks). Verify the related-groups + peek-body shapes here.
- [ ] **Task 2 — RBAC anchors + action htmx parity:** add `data-dazzle-action` to the substrate detail actions (Edit/Delete/transition/external/integration) + confirm transition `hx-put`/`hx-vals` + external new-tab. New primitive fields or a `DetailAction` sidecar; TDD. (Mirrors Phase 1's CreateButton/anchor work.)
- [ ] **Task 3 — Remaining chrome gaps:** Back affordance (decision), related-groups real content vs placeholder (decision), `dz-detail` wrapper class parity, `data-dz-entity-id`. TDD per element.
- [ ] **Task 4 — peek convergence:** the `?peek=1` detail body serves the substrate detail body (not legacy). Trace + repoint `is_peek_request`/`_render_response`/`resolve_peek_mode`; keep peek byte-stable for opted-in lists. TDD + the existing peek tests.
- [ ] **Task 5 — FLIP (independent review):** Step 0 fresh adversarial review (substrate detail vs Task-1 fixtures: RBAC anchors, a11y, peek-body equivalence, action htmx, related groups; fix findings). Step 1 `_maybe_dispatch_inner_html` dispatches `mode: view` even when `render is None`. Step 2 full suite + re-baseline churned goldens (inspect). Step 3 oracles (card-safety + structural scanners; CI runs ux verify/INTERACTION_WALK/GUIDE_WALK). Ship.
- [ ] **Task 6 — DELETE (independent review):** Step 1 grep all callers (incl the page↛http experience detail-STEP + the peek path + build-ui/serve/fidelity sweep). Step 2 fresh review of the deletion plan. Step 3 make `_render_body_inner`'s detail branch a loud error (D4); repoint experience detail-step via the http route (same pattern as Phase 1); delete `render_detail_view` + helpers; migrate tests. Step 4 full suite + lint/mypy/import-linter (`render is pure` + `page ↛ http` KEPT) + **monitor the E2E (PostgreSQL) tier**.
- [ ] **Task 7 — ADR/CHANGELOG/ship.** ADR-0049 status → Phase 2 (view) shipped. CHANGELOG + Agent Guidance. `/bump`, push, CI green.

## Phase 2 gate
- [ ] Every `mode: view` surface renders via the substrate; peek body served by the substrate; `render_detail_view` deleted; full suite + card-safety + a11y + the CI e2e/browser tier green; `render is pure` + `page ↛ http` KEPT; goldens re-baselined with inspected diffs.
