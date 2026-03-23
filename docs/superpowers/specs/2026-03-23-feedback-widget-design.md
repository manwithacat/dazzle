# In-App Feedback Widget — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Branch:** feature/feedback-widget
**Framework target:** Dazzle (propose as framework feature after AegisMark prototype)

## Overview

A framework-level Dazzle feature enabling any authenticated user to report issues, impressions, and improvement suggestions directly from the app. Humans provide free-form observations; agents triage, classify, and fix.

**Philosophy:** Humans are sensors, agents are processors. The feedback loop is permanent — not a QA phase but a continuous improvement channel available to every user.

## 1. FeedbackReport Entity

Auto-generated when `feedback_widget: enabled` is declared in the DSL. Follows the same auto-entity pattern as `AIJob`.

### Fields

**Human input (minimal):**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `category` | enum `[bug, ux, visual, behaviour, enhancement, other]` | yes | Quick-select buttons, not a dropdown |
| `severity` | enum `[blocker, annoying, minor]` | no | Optional — defaults to `minor` if omitted |
| `description` | text | yes | Free-form. The only field requiring effort. |

**Auto-captured context (populated by widget JS):**

| Field | Type | Notes |
|-------|------|-------|
| `page_url` | str | Current route (e.g. `/app/markingresult/abc-123`) |
| `page_title` | str | Rendered page title |
| `persona` | str | Role of logged-in user (e.g. `teacher`) |
| `viewport` | str | e.g. `1440x900` |
| `user_agent` | str | Browser identification |
| `console_errors` | text | JS errors captured via `window.onerror`, `unhandledrejection`, and HTMX error events (`htmx:responseError`, `htmx:sendError`) |
| `nav_history` | text | JSON array of last 5 URLs visited in session (persisted in `sessionStorage` to survive full page navigations) |
| `page_snapshot` | text | DOM structure of current page with text content stripped (layout-only, ~5-10KB). Classified as `internal`. |
| `screenshot_data` | text | Base64 PNG — nullable, stretch goal (Tier 2/3). Classified as `internal`. |
| `annotation_data` | text | JSON coordinates of annotations — nullable, stretch goal (Tier 3) |
| `duplicate_of` | ref FeedbackReport | Nullable — links to canonical report when status is `duplicate` |

**Agent triage fields (populated during `new → triaged`):**

| Field | Type | Notes |
|-------|------|-------|
| `agent_classification` | str | Agent's interpretation of the report |
| `related_entity` | str | Which DSL entity this relates to (nullable) |
| `related_story` | str | Matched story ID, e.g. `ST-042` (nullable) |
| `agent_notes` | text | Agent's analysis and proposed fix |

**Audit trail:**

| Field | Type | Notes |
|-------|------|-------|
| `reported_by` | ref User | Auto-set to `current_user` |
| `assigned_to` | ref User | Nullable — human or agent working the report |
| `resolved_by` | ref User | Nullable — who resolved it |
| `created_at` | datetime | auto_add |
| `updated_at` | datetime | auto_update |
| `resolved_at` | datetime | Nullable — set on transition to `resolved` |

**Tenant:**

| Field | Type | Notes |
|-------|------|-------|
| `school` | ref School | Nullable — agent/super_admin reports may be school-less |

### Status Lifecycle

```
new → triaged → in_progress → resolved → verified
                     ↓             ↑
                  wont_fix    (reopen)
                  duplicate
```

**Reopen transition:** `resolved → in_progress` allows reopening reports that the reporter confirms are not actually fixed.

### Transition Guards

| Transition | Permitted roles |
|-----------|----------------|
| `new → triaged` | `agent`, `super_admin` |
| `triaged → in_progress` | `agent`, `super_admin` |
| `triaged → wont_fix` | `agent`, `super_admin` |
| `triaged → duplicate` | `agent`, `super_admin` |
| `in_progress → resolved` | `agent`, `super_admin` |
| `in_progress → wont_fix` | `agent`, `super_admin` |
| `resolved → verified` | `agent`, `super_admin`, or `reported_by = current_user` |
| `resolved → in_progress` | `agent`, `super_admin`, or `reported_by = current_user` |

### Access Control

| Operation | Rule |
|-----------|------|
| `create` | any authenticated role |
| `read` (own) | `reported_by = current_user` for all roles |
| `read` (school) | `school = current_user.school` for `school_admin` |
| `read` (all) | `agent`, `super_admin` |
| `list` | same scoping as `read` |
| `update` | `agent`, `super_admin` |
| `delete` | `super_admin` only |

### Data Classification

The following fields carry `classify` directives:

| Field | Classification | Reason |
|-------|---------------|--------|
| `page_snapshot` | `internal` | May contain rendered PII from the page being viewed |
| `screenshot_data` | `internal` | Visual capture may include sensitive content |
| `console_errors` | `internal` | May contain internal system details |

### Notification

MVP has no push notification. Reporters check their own reports list for status changes. Future: HTMX polling badge on the feedback button showing count of reports with `status = resolved` (awaiting verification by reporter).

### Rate Limiting

Client-side: max 10 reports per hour per user (enforced in widget JS via `localStorage` counter with hourly reset). Server-side: standard Dazzle request rate limiting applies. Retry mechanism uses an idempotency key (`crypto.randomUUID()` generated at panel open time, sent with POST) to prevent duplicate submissions on network retry.

## 1b. Agent Role

The `agent` role is a full DSL persona with `default_workspace: qa_workspace`. It represents automated agents (BDD cycle, future CI/CD integrations) that interact with the platform programmatically.

```dsl
persona agent "Agent":
  default_workspace: qa_workspace
```

The `agent` persona:
- Has no human-facing nav menu or UI preferences
- Exists purely for RBAC resolution — `role(agent)` predicates in `permit:`, `scope:`, and `transitions:` blocks
- Auth user `agent@aegismark.ai` is created via `dazzle auth create-user` with this role
- `super_admin` already exists as an AegisMark role and retains full access

## 2. DSL Keyword: `feedback_widget`

Declared in the app's top-level or `policies:` block:

```dsl
feedback_widget: enabled
  position: bottom-right
  shortcut: backtick
  categories: [bug, ux, visual, behaviour, enhancement, other]
  severities: [blocker, annoying, minor]
  capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
```

All sub-keys have defaults — `feedback_widget: enabled` with no configuration is a valid declaration that uses all defaults.

### What the Framework Does

1. **DSL parser** — recognises `feedback_widget` keyword, validates sub-keys, stores in manifest
2. **Auto-entity generation** — if no `FeedbackReport` entity is explicitly declared, generates one with the standard field set (sites can override by declaring their own `FeedbackReport` entity with additional fields)
3. **Base template injection** — conditionally injects widget HTML + JS into every authenticated page
4. **Static assets** — serves `feedback-widget.js` (~2KB context collector + panel UI) and `feedback-widget.css`
5. **Session preference** — `POST /api/feedback-widget/preferences` endpoint for hide/show toggle, stored in user session

### Widget Runtime Behaviour

1. **Page load** — context collector starts: registers `window.onerror` and `unhandledrejection` handlers, listens for HTMX error events (`htmx:responseError`, `htmx:sendError`), pushes current URL to `sessionStorage` nav history buffer (max 5), captures viewport dimensions
2. **Button visible** — floating button in configured position, respects user hide preference. Backtick shortcut active when focus is NOT inside a `textarea`, `input`, or `[contenteditable]` element.
3. **Panel open** — slide-out panel with category buttons, optional severity toggle, description textarea. All auto-context fields are pre-populated as hidden inputs.
4. **Submit** — `POST /feedbackreports` with all fields. Panel closes, brief confirmation toast. No page reload.
5. **Error handling** — if POST fails (network, auth), report is saved to `localStorage` with its idempotency key and retried on next page load. Duplicate submissions are prevented server-side by the idempotency key.

## 3. QA Workspace

New workspace: `qa_workspace`, visible to `agent` and `super_admin`.

### Regions

| Region | Content | Sort |
|--------|---------|------|
| **Incoming** | `status = new` | Severity (blockers first), then `created_at` |
| **In Triage** | `status = triaged` | `updated_at` desc |
| **Active** | `status = in_progress` | `updated_at` desc |
| **Recently Resolved** | `status = resolved`, last 7 days | `resolved_at` desc |
| **Stats** | Counts: total open, resolved this week, avg time-to-triage, category breakdown | — |

### Surfaces

- **List** — standard entity list with status badge, category icon, severity indicator, reporter name, page URL, created_at
- **Detail** — full report with all auto-captured context. Page snapshot rendered in an iframe/code block. Agent notes editable. Status transition buttons.
- **Create** — not needed in workspace (reports created via widget only)

## 4. Agent Consumption Loop

### BDD Cycle Integration

New step `0b: CHECK FEEDBACK REPORTS` added to `/bdd-cycle`, runs before existing story verification:

```
Step 0b: CHECK FEEDBACK REPORTS
  1. Authenticate as agent persona (MVP) or via API key (long-term)
  2. GET /feedbackreports?status=new
  3. For each new report:
     a. Read auto-captured context (URL → identify entity/surface, page snapshot, console errors)
     b. Classify: map to DSL entity, match to story ID if possible
     c. Assess: framework bug (file Dazzle issue), DSL fix (modify app.dsl), data issue (fix data), or aesthetic/philosophy (flag for human)
     d. PATCH status → triaged
     e. Populate: agent_classification, related_entity, related_story, agent_notes
  4. GET /feedbackreports?status=triaged (highest severity first)
  5. For highest-priority triaged report:
     a. Attempt fix (DSL change, data fix, or file framework issue)
     b. PATCH status → in_progress, then → resolved on success
     c. Populate agent_notes with resolution details
  6. Continue to existing BDD cycle steps (story verification)
```

### Classification Taxonomy

The agent maps each report to one of:

| Classification | Action |
|---------------|--------|
| `dsl_fix` | Modify `app.dsl` — entity, surface, scope, or access rule change |
| `data_fix` | SQL or API call to correct bad data |
| `framework_bug` | File Dazzle GitHub issue, mark as `in_progress` pending framework fix |
| `framework_enhancement` | File Dazzle GitHub issue, mark as `wont_fix` with explanation |
| `aesthetic` | Flag for human review — taste/philosophy decisions the agent shouldn't make |
| `duplicate` | Link to existing report, mark as `duplicate` |
| `not_reproducible` | Agent couldn't reproduce, add notes, keep as `triaged` for human review |

## 5. Service Account Authentication

### MVP (immediate)

New `agent` role in DSL. Auth user `agent@aegismark.ai` created via `dazzle auth create-user`. BDD cycle logs in via `POST /auth/login`, receives session cookie, operates within standard RBAC.

### Long-term (Dazzle framework issue)

New DSL keyword:

```dsl
service_accounts:
  bdd_agent:
    role: agent
    scopes: [feedbackreport.read, feedbackreport.write, feedbackreport.transition]
```

Framework generates API key at deploy time, stored as env var (e.g. `DAZZLE_SERVICE_KEY_BDD_AGENT`). Agent sends `Authorization: Bearer <key>`. Key is scoped — cannot access entities outside declared scopes.

### MCP Integration (stretch)

New MCP tool operations:

```
mcp__dazzle__feedback operation=poll         → returns new/triaged reports
mcp__dazzle__feedback operation=triage id=X  → classify and transition
mcp__dazzle__feedback operation=resolve id=X notes="..."
mcp__dazzle__feedback operation=stats        → dashboard metrics
```

## 6. Screenshot Annotation (Stretch Goal)

Designed in three tiers. Entity fields accommodate Tier 3 from day one.

| Tier | Feature | Dependency |
|------|---------|------------|
| **1 (MVP)** | No screenshot. Description + auto-context only. | None |
| **2** | Screenshot capture via `html2canvas` (~40KB). One-click page snapshot. | `html2canvas` library |
| **3** | Screenshot + annotation overlay (highlight, arrow, redact, text label). Annotations stored as JSON coordinates. | Custom canvas overlay |

**Known constraints for Tier 2/3:**
- Cross-origin images (e.g. S3 presigned URLs) may render blank — needs CORS headers or graceful fallback
- Screenshot data ~100-500KB base64 per report — acceptable for internal use, needs size limits at scale
- `html2canvas` rendering fidelity varies — not pixel-perfect, but sufficient for "point at the problem"

## Implementation Sequence

1. **FeedbackReport entity** in `app.dsl` with full field set, lifecycle, transitions, access control
2. **Agent persona** — new `agent` role, auth user, scope rules
3. **QA workspace** — workspace, regions, surfaces in DSL
4. **Widget JS/CSS** — context collector, floating button, slide-out panel, POST to API
5. **Base template injection** — conditional widget loading for authenticated users
6. **BDD cycle Step 0b** — poll, triage, classify, attempt fix
7. **DSL keyword** (`feedback_widget:`) — parser, manifest, auto-entity generation
8. **Service account auth** — Dazzle framework issue for API key support
9. **Screenshot capture** (Tier 2) — `html2canvas` integration
10. **Annotation overlay** (Tier 3) — drawing tools, JSON coordinate storage

**Prototype vs framework:** Steps 1-6 are prototype implementations built on the AegisMark feature branch. Step 7 replaces the manual entity declaration and template injection with framework automation. The AegisMark-specific code from steps 1-5 will be removed once the framework feature lands — design accordingly (keep widget JS modular, entity definition aligned with auto-generation schema).

Steps 7-8 require Dazzle framework PRs.
Steps 9-10 are stretch goals.
