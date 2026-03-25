# Feedback Widget CRUD Integration

> **Issue:** #685
> **Status:** Approved
> **Date:** 2026-03-25
> **Follow-on:** Universal admin workspace for auth-enabled apps (new issue)

## Goal

Make FeedbackReport a proper CRUD citizen by generating synthetic surfaces in the linker. The widget POST and admin triage go through the same pipeline as every other entity — no hand-coded routes.

## Design Principle

This establishes a reusable pattern: **synthetic DSL fragments injected by framework features**. When a DSL keyword (like `feedback_widget: enabled`) needs runtime entities and surfaces, the linker generates them as if they were written in DSL. The surface converter, route generator, and auth evaluator handle them identically to user-authored constructs.

## Changes

### 1. Linker — `src/dazzle/core/linker.py`

When `feedback_widget: enabled`, alongside the existing `_build_feedback_report_entity()`, generate two synthetic surfaces and append them to `merged_fragment.surfaces`:

**`_build_feedback_create_surface()`** — headless CREATE surface
- `name: "feedback_create"`, `mode: create`, `uses entity FeedbackReport`
- No UI sections (API-only — the widget JS is the UI)
- Access: `permit: create: role(*)` (any authenticated user)
- This generates `POST /feedbackreports` via the normal surface converter

**`_build_feedback_admin_surface()`** — LIST+VIEW admin surface
- `name: "feedback_admin"`, `mode: list`, `uses entity FeedbackReport`
- Sections with fields: `category`, `severity`, `description`, `status`, `submitted_by`, `page_url`, `created_at`
- Access: `permit: read: role(admin) or role(super_admin)`, `permit: update: role(admin) or role(super_admin)`
- Renders at `/app/feedbackreports`

Both surfaces follow the same `ir.SurfaceSpec` structure as DSL-declared surfaces. The linker code sits next to the existing `_build_feedback_report_entity()` function.

### 2. CSRF — `src/dazzle_back/runtime/csrf.py`

Add `/feedbackreports` to `exempt_paths`. The route validates session auth via the normal access evaluator. The widget JS doesn't have access to the CSRF token (no meta tag rendered in base template).

### 3. System Routes Cleanup — `src/dazzle_back/runtime/subsystems/system_routes.py`

Remove the TODO comment and any hand-coded feedback route code. The surfaces handle everything.

### 4. CDN Bundle — `scripts/build_dist.py`

Already done: `feedback-widget.css` is included in `CSS_SOURCES` (committed in v0.48.7).

## What Does NOT Change

- `convert_surfaces_to_services` — no modifications needed
- `route_generator.py` — no modifications needed
- `server.py` — no modifications needed
- The feedback widget JS (`feedback-widget.js`) — posts to `/feedbackreports` as before
- The feedback widget CSS — already styled, already in bundle

## Testing

### Unit Tests

Add to `tests/unit/test_linker.py` (or new file `tests/unit/test_feedback_widget_linker.py`):

- `test_feedback_widget_generates_entity_and_surfaces` — parse DSL with `feedback_widget: enabled`, verify linker produces:
  - 1 FeedbackReport entity
  - 1 feedback_create surface (mode=create)
  - 1 feedback_admin surface (mode=list)
- `test_feedback_widget_disabled_no_surfaces` — `feedback_widget: disabled` produces no FeedbackReport entity or surfaces
- `test_feedback_create_surface_has_correct_access` — CREATE surface permits any authenticated role
- `test_feedback_admin_surface_has_admin_access` — LIST surface restricted to admin roles

### E2E Test

Playwright test against simple_task example (which now has `feedback_widget: enabled` and `auth: enabled`):

1. Create user via AuthStore
2. Login via API (JSON POST to `/auth/login`)
3. Navigate to authenticated page
4. Verify feedback button present (`.dz-feedback-btn`)
5. Open panel, select category + severity, fill description
6. Submit — expect 201 from `POST /feedbackreports`
7. Verify DB row in `FeedbackReport` table
8. (Optional) Navigate to `/app/feedbackreports` as admin — verify list surface renders

## Not In Scope

- Universal admin workspace (follow-on issue)
- Deprecating no-auth sites (separate discussion)
- Widget visual redesign (current styling works)
