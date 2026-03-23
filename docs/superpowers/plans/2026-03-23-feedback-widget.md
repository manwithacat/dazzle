# In-App Feedback Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-app feedback widget that lets any authenticated user report issues, with agent triage via the BDD cycle.

**Architecture:** FeedbackReport DSL entity with state machine lifecycle, `agent` persona, QA workspace, custom JS widget injected via template override, and BDD cycle Step 0b for agent consumption. Prototype in AegisMark; designed for later extraction to Dazzle framework.

**Tech Stack:** Dazzle DSL (entity, persona, workspace, surfaces), vanilla JS/CSS (widget), Dazzle REST API (submission + agent consumption), Jinja2 template override (widget injection).

**Spec:** `docs/superpowers/specs/2026-03-23-feedback-widget-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `dsl/app.dsl` | Add FeedbackReport entity, agent persona, QA workspace, surfaces, classify directives |
| `templates/base_override.html` | Inject feedback widget into every authenticated page |
| `static/js/feedback-widget.js` | Context collector, floating button, slide-out panel, form submission |
| `static/css/feedback-widget.css` | Widget styling (DaisyUI tokens, slide-out animation) |
| `.claude/commands/bdd-cycle.md` | Add Step 0b: feedback report polling and triage |
| `dsl/tests/` | Auto-generated tests updated via `mcp__dazzle__dsl operation=validate` |

**Security note:** The widget JS uses DOM construction methods for its own static template markup. No user-supplied content is rendered as HTML. The `description` field and all auto-captured context are submitted as JSON via `fetch()` and rendered server-side by Dazzle's template engine (which auto-escapes). The `page_snapshot` field contains DOM structure only (text content stripped). If future iterations render user content client-side, use DOMPurify for sanitisation.

---

### Task 1: Create Feature Branch

**Files:** None (git operation)

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/feedback-widget
```

- [ ] **Step 2: Verify branch**

```bash
git branch --show-current
```

Expected: `feature/feedback-widget`

---

### Task 2: Add `agent` Role to User Entity

The `agent` role must be added to the User role enum before the entity or persona can reference it.

**Files:**
- Modify: `dsl/app.dsl:90` (User role enum)

- [ ] **Step 1: Add `agent` to User role enum**

In `dsl/app.dsl` line 90, change:

```dsl
role: enum[super_admin,trust_admin,governor,senior_leader,school_admin,head_of_department,teacher,cover_supervisor,student,parent]=teacher
```

to:

```dsl
role: enum[super_admin,trust_admin,governor,senior_leader,school_admin,head_of_department,teacher,cover_supervisor,student,parent,agent]=teacher
```

- [ ] **Step 2: Update User invariant for agent role (no school required)**

In `dsl/app.dsl` line 103, change:

```dsl
invariant: role in [super_admin, trust_admin, governor] or school != null
```

to:

```dsl
invariant: role in [super_admin, trust_admin, governor, agent] or school != null
```

This exempts `agent` from requiring a school assignment (like trust-level roles).

- [ ] **Step 3: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): add agent role to User entity enum"
```

---

### Task 3: Add QA Workspace (before persona, to avoid forward-reference risk)

**Files:**
- Modify: `dsl/app.dsl` (after last workspace, before scenarios section at line ~6200)

- [ ] **Step 1: Add qa_workspace**

Insert after the last workspace definition (around line 6195) and before the scenarios section:

```dsl
workspace qa_workspace "QA Dashboard":
  purpose: "Feedback report triage and resolution tracking for platform quality assurance"
  stage: "command_center"

  access: persona(agent, super_admin)

  nav_group "Feedback" icon=message-circle:
    FeedbackReport

  incoming_reports:
    source: FeedbackReport
    filter: status = new
    sort: severity asc, created_at asc
    display: table

  in_triage:
    source: FeedbackReport
    filter: status = triaged
    sort: updated_at desc
    display: table

  active_reports:
    source: FeedbackReport
    filter: status = in_progress
    sort: updated_at desc
    display: table

  recently_resolved:
    source: FeedbackReport
    filter: status = resolved
    sort: resolved_at desc
    display: table
```

**Note:** Stats region (total open, resolved this week, avg time-to-triage, category breakdown) is deferred — Dazzle workspaces don't yet support computed/aggregate regions. Add when framework supports it.

- [ ] **Step 2: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

- [ ] **Step 3: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): add qa_workspace for feedback report triage"
```

---

### Task 4: Add `agent` Persona

**Files:**
- Modify: `dsl/app.dsl:3028-3029` (after `parent` persona, before SURFACES comment)

- [ ] **Step 1: Add agent persona definition**

Insert after the `parent` persona (after line 3028) and before the `# SURFACES` comment at line 3030:

```dsl
persona agent "Agent":
  description: "Automated agent for BDD cycle triage, feedback processing, and CI/CD integrations — no human-facing UI"
  goals: "Triage feedback reports", "Classify and route issues", "Attempt automated fixes"
  proficiency: advanced
  default_workspace: qa_workspace
```

- [ ] **Step 2: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

Expected: No errors (`qa_workspace` was defined in Task 3).

- [ ] **Step 3: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): add agent persona with qa_workspace"
```

---

### Task 5: Add FeedbackReport Entity

**Files:**
- Modify: `dsl/app.dsl:2812-2813` (insert after ParentConsent entity, before GRANT SCHEMAS section)

- [ ] **Step 1: Add FeedbackReport entity**

Insert after line 2812 (end of ParentConsent) and before line 2814 (`# GRANT SCHEMAS`):

```dsl
# =============================================================================
# FEEDBACK & QA
# =============================================================================

entity FeedbackReport "Feedback Report":
  intent: "In-app feedback from any user — issues, impressions, improvement suggestions. Auto-captured context enables agent triage."
  domain: devops
  patterns: [lifecycle, feedback, audit]
  display_field: description

  id: uuid pk
  school: ref School optional

  # Human input
  category: enum[bug,ux,visual,behaviour,enhancement,other] required
  severity: enum[blocker,annoying,minor]=minor
  description: text required

  # Auto-captured context
  page_url: str(500)
  page_title: str(200)
  persona: str(50)
  viewport: str(20)
  user_agent: str(500)
  console_errors: text
  nav_history: text
  page_snapshot: text
  screenshot_data: text
  annotation_data: text

  # Agent triage
  agent_classification: str(100)
  related_entity: str(100)
  related_story: str(20)
  agent_notes: text

  # Duplicate tracking
  duplicate_of: ref FeedbackReport optional

  # Audit — reported_by auto-set via created_by = current_user pattern (Dazzle #484)
  reported_by: ref User required
  assigned_to: ref User optional
  resolved_by: ref User optional
  created_at: datetime auto_add
  updated_at: datetime auto_update
  resolved_at: datetime

  # Lifecycle
  status: enum[new,triaged,in_progress,resolved,verified,wont_fix,duplicate]=new

  transitions:
    new -> triaged: role(agent) or role(super_admin)
    triaged -> in_progress: role(agent) or role(super_admin)
    triaged -> wont_fix: role(agent) or role(super_admin)
    triaged -> duplicate: role(agent) or role(super_admin)
    in_progress -> resolved: role(agent) or role(super_admin)
    in_progress -> wont_fix: role(agent) or role(super_admin)
    # Spec: resolved -> verified/in_progress should be agent, super_admin, or reported_by = current_user
    # Dazzle doesn't support field-match predicates on transitions, so we allow all roles as approximation.
    # Row-level scope rules already restrict visibility to own reports for non-admin roles.
    resolved -> verified: role(agent) or role(super_admin) or role(teacher) or role(school_admin) or role(senior_leader) or role(head_of_department) or role(trust_admin) or role(governor) or role(cover_supervisor) or role(student) or role(parent)
    resolved -> in_progress: role(agent) or role(super_admin) or role(teacher) or role(school_admin) or role(senior_leader) or role(head_of_department) or role(trust_admin) or role(governor) or role(cover_supervisor) or role(student) or role(parent)

  permit:
    read: role(agent) or role(super_admin) or role(trust_admin) or role(governor) or role(senior_leader) or role(school_admin) or role(head_of_department) or role(teacher) or role(cover_supervisor) or role(student) or role(parent)
    list: role(agent) or role(super_admin) or role(trust_admin) or role(governor) or role(senior_leader) or role(school_admin) or role(head_of_department) or role(teacher) or role(cover_supervisor) or role(student) or role(parent)
    create: role(agent) or role(super_admin) or role(trust_admin) or role(governor) or role(senior_leader) or role(school_admin) or role(head_of_department) or role(teacher) or role(cover_supervisor) or role(student) or role(parent)
    update: role(agent) or role(super_admin)
    delete: role(super_admin)

  scope:
    read: reported_by = current_user
      for: teacher, cover_supervisor, student, parent, head_of_department, senior_leader, governor, trust_admin
    read: school = current_user.school
      for: school_admin
    read: all
      for: agent, super_admin
    list: reported_by = current_user
      for: teacher, cover_supervisor, student, parent, head_of_department, senior_leader, governor, trust_admin
    list: school = current_user.school
      for: school_admin
    list: all
      for: agent, super_admin

  index school, status
  index reported_by, status
  index status, severity
```

- [ ] **Step 2: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

Expected: No errors.

- [ ] **Step 3: Lint DSL**

```bash
mcp__dazzle__dsl operation=lint
```

Expected: No errors or only minor warnings.

- [ ] **Step 4: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): add FeedbackReport entity with lifecycle and RBAC"
```

---

### Task 5: Add Classify Directives for FeedbackReport

**Files:**
- Modify: `dsl/app.dsl` (policies block, after line ~2970)

- [ ] **Step 1: Add classify directives**

Append to the end of the `policies:` block (before the `# PERSONAS` comment).

The spec classifies 3 fields (`page_snapshot`, `screenshot_data`, `console_errors`). We extend this to also cover `page_url`, `user_agent`, and `nav_history` since they contain internal system details and user browsing patterns that should not be exposed to non-admin roles:

```dsl
  classify FeedbackReport.page_snapshot as INTERNAL
  classify FeedbackReport.screenshot_data as INTERNAL
  classify FeedbackReport.console_errors as INTERNAL
  classify FeedbackReport.page_url as INTERNAL
  classify FeedbackReport.user_agent as INTERNAL
  classify FeedbackReport.nav_history as INTERNAL
```

- [ ] **Step 2: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): classify FeedbackReport context fields as INTERNAL"
```

---

### Task 6: Add FeedbackReport Surfaces

**Files:**
- Modify: `dsl/app.dsl` (after existing surfaces, before workspaces section at line ~5561)

- [ ] **Step 1: Add list, detail, and create surfaces**

Insert before the workspaces section:

```dsl
# =============================================================================
# SURFACES — FEEDBACK & QA
# =============================================================================

surface feedback_report_list "Feedback Reports":
  uses entity FeedbackReport
  mode: list
  section main:
    field status "Status"
    field category "Category"
    field severity "Severity"
    field description "Description"
    field page_url "Page"
    field persona "Reporter Role"
    field reported_by "Reported By"
    field created_at "Reported"
  ux:
    sort: created_at desc
    filter: status, category, severity
    search: description, page_url, agent_notes
    empty: "No feedback reports yet."

surface feedback_report_detail "Feedback Report":
  uses entity FeedbackReport
  mode: detail

  section "Report":
    field status "Status"
    field category "Category"
    field severity "Severity"
    field description "Description"
    field reported_by "Reported By"
    field created_at "Reported At"

  section "Context" visible: role(agent) or role(super_admin):
    field page_url "Page URL"
    field page_title "Page Title"
    field persona "Reporter Persona"
    field viewport "Viewport"
    field user_agent "User Agent"
    field console_errors "Console Errors"
    field nav_history "Navigation History"
    field page_snapshot "Page Snapshot"

  section "Triage" visible: role(agent) or role(super_admin):
    field agent_classification "Classification"
    field related_entity "Related Entity"
    field related_story "Related Story"
    field agent_notes "Agent Notes"
    field duplicate_of "Duplicate Of"

  section "Assignment":
    field assigned_to "Assigned To"
    field resolved_by "Resolved By"
    field resolved_at "Resolved At"

surface feedback_report_create "Report Feedback":
  uses entity FeedbackReport
  mode: create
  section main:
    field category "What kind of feedback?"
    field severity "How severe?"
    field description "Describe what you observed"
```

**Note:** The create surface is a fallback/admin tool. The primary creation path is the widget, which auto-populates context fields. Reports created via this surface will have empty context fields.

- [ ] **Step 2: Validate DSL**

```bash
mcp__dazzle__dsl operation=validate
```

- [ ] **Step 3: Commit**

```bash
git add dsl/app.dsl
git commit -m "feat(feedback): add FeedbackReport list, detail, and create surfaces"
```

---

### Task 7: Create Widget CSS

**Files:**
- Create: `static/css/feedback-widget.css`

- [ ] **Step 1: Write widget CSS**

Create `static/css/feedback-widget.css` with styles for:
- `.feedback-widget-btn` — fixed position bottom-right, 3rem circle, `oklch(var(--p))` background, z-index 9998
- `.feedback-panel` — fixed right edge, 24rem wide, slide-in via `transform: translateX(100%)`, z-index 9999
- `.feedback-panel.open` — `translateX(0)`
- `.feedback-categories` — 2-column grid of category buttons
- `.feedback-severity` — flex row of 3 severity buttons with color-coded selected states (error/warning/success tokens)
- `.feedback-description` — full-width textarea
- `.feedback-submit` — full-width primary button
- `.feedback-toast` — fixed bottom-right notification
- All using DaisyUI oklch colour tokens consistent with `static/css/manuscript-viewer.css`

See spec for full CSS. Reference `static/css/manuscript-viewer.css` for token patterns.

- [ ] **Step 2: Commit**

```bash
git add static/css/feedback-widget.css
git commit -m "feat(feedback): add feedback widget CSS with DaisyUI tokens"
```

---

### Task 8: Create Widget JavaScript

**Files:**
- Create: `static/js/feedback-widget.js`

- [ ] **Step 1: Write widget JS**

Create `static/js/feedback-widget.js` as an ES6 class `FeedbackWidget` (following the `ManuscriptViewer` pattern in `static/js/manuscript-viewer.js`). Expose as `window.feedbackWidget`.

**Key methods:**

- `constructor()` — initialise error capture, nav tracking, build UI, bind shortcut, retry pending
- `_initErrorCapture()` — register `window.onerror`, `unhandledrejection`, `htmx:responseError`, `htmx:sendError`
- `_trackNavigation()` — push current URL to `sessionStorage` rolling buffer (max 5)
- `_getPageSnapshot()` — clone `document.body`, remove widget elements/scripts/styles, strip text nodes, truncate to 10KB
- `_checkRateLimit()` — max 10 reports/hour via `localStorage` counter with hourly reset
- `_buildUI()` — create floating button and slide-out panel using `document.createElement()` (safe DOM construction, no user content in markup). Category buttons, severity toggles, textarea, submit button
- `_bindShortcut()` — backtick key, suppressed when focus is in textarea/input/contenteditable
- `open()` / `close()` — toggle panel, generate `crypto.randomUUID()` idempotency key on open
- `_submit()` — POST to `/feedbackreports` with JSON payload including all auto-captured context. On failure, save to `localStorage` for retry. On success, show toast and reset form
- `_retryPending()` — on page load, retry any pending reports from `localStorage` (discard >24h old)
- `_toast(msg)` — brief confirmation notification

**`reported_by` auto-population:** Dazzle auto-sets `created_by = current_user` on POST (confirmed working via #484). The `reported_by` field should follow the same pattern. If Dazzle doesn't auto-populate `reported_by`, either: (a) add `data-user-id` attribute to `<body>` in the template override and include it in the POST payload, or (b) make `reported_by` optional and populate it server-side via a DSL default expression.

**Security:** All user input (description) is sent as JSON via `fetch()` and rendered server-side by Dazzle's auto-escaping templates. The widget builds its own UI using `document.createElement()` — no user-supplied content is injected into the DOM as HTML. The `textContent` property is used for all dynamic text (toast messages, button labels).

- [ ] **Step 2: Commit**

```bash
git add static/js/feedback-widget.js
git commit -m "feat(feedback): add feedback widget JS with context collector and panel"
```

---

### Task 9: Create Base Template Override for Widget Injection

**Files:**
- Create: `templates/base_override.html`

The template override pattern follows the existing `manuscript_viewer.html` approach. Dazzle's base template supports block inheritance — we extend it and inject the widget assets.

- [ ] **Step 1: Write base template override**

Create `templates/base_override.html` that:
- Extends Dazzle's `base.html`
- Adds `<link>` to `feedback-widget.css` in the head block
- Conditionally loads `feedback-widget.js` only for authenticated users (`{% if current_user %}`)
- Sets `document.body.dataset.userRole` from the current user's role for the widget to read

**Before executing:** Run `mcp__dazzle__dsl operation=inspect_entity name=User` or check the Dazzle base template (`python3 -c "import dazzle_back; print(dazzle_back.__file__)"` then find `templates/base.html`) to discover available template blocks.

**Fallback approaches if `extra_head`/`extra_body` blocks don't exist:**
1. **Custom route middleware** — create `routes/feedback_widget.py` that hooks into Dazzle's response pipeline and appends `<link>` and `<script>` tags before `</head>` and `</body>` respectively in all HTML responses
2. **Dazzle `custom_head` config** — check if `sitespec.yaml` or the DSL supports a `custom_head` or `extra_scripts` directive
3. **Direct base template patching** — as last resort, copy Dazzle's base template to `templates/base.html` and add the widget includes (but this breaks on Dazzle upgrades)

- [ ] **Step 2: Commit**

```bash
git add templates/base_override.html
git commit -m "feat(feedback): add base template override for widget injection"
```

---

### Task 10: Create Agent Auth User

**Files:** None (CLI command)

- [ ] **Step 1: Create agent auth user**

```bash
python3 -m dazzle auth create-user --email agent@aegismark.ai --password Demo1234! --role agent
```

If this fails (role not yet in deployed schema), it will need to be done after deployment.

- [ ] **Step 2: Document in login matrix**

Add to `.dazzle/demo_data/login_matrix.md`:

```
| agent@aegismark.ai | BDD Agent | agent | Agent |
```

- [ ] **Step 3: Commit**

```bash
git add .dazzle/demo_data/login_matrix.md
git commit -m "feat(feedback): add agent auth user to login matrix"
```

---

### Task 11: Update BDD Cycle with Step 0b

**Files:**
- Modify: `.claude/commands/bdd-cycle.md`

- [ ] **Step 1: Add Step 0b after Step 0a**

Rename existing "Step 0b: INIT" to "Step 0c: INIT", then insert new Step 0b:

```markdown
## Step 0b: CHECK FEEDBACK REPORTS

Poll for user-submitted feedback reports and triage them.

1. **Authenticate as agent**: POST `/auth/login` with `{"email": "agent@aegismark.ai", "password": "Demo1234!"}` — save session cookie
2. **Poll new reports**: GET `/feedbackreports?status=new`
3. **For each new report** (max 3 per cycle to avoid blocking story work):
   a. Read auto-captured context: `page_url` (identify entity/surface), `console_errors` (JS errors), `page_snapshot` (DOM state)
   b. **Classify** using taxonomy:
      - `dsl_fix` — entity/surface/scope/access change in `dsl/app.dsl`
      - `data_fix` — bad data, run SQL or API correction
      - `framework_bug` — Dazzle bug, file issue at `manwithacat/dazzle`
      - `framework_enhancement` — feature request for Dazzle
      - `aesthetic` — taste/philosophy, flag for human (do NOT fix)
      - `duplicate` — link to existing report
      - `not_reproducible` — cannot reproduce, add notes
   c. **PATCH** report: transition `new` to `triaged`, set `agent_classification`, `related_entity`, `related_story`, `agent_notes`
4. **Poll triaged reports**: GET `/feedbackreports?status=triaged` (highest severity first)
5. **For highest-priority triaged report**:
   a. If `dsl_fix`: modify `dsl/app.dsl`, validate, commit
   b. If `data_fix`: run correction via API or SQL
   c. If `framework_bug`: file GitHub issue via `gh issue create -R manwithacat/dazzle`
   d. If `aesthetic` or `not_reproducible`: skip (awaiting human)
   e. PATCH status `triaged` to `in_progress`, then `in_progress` to `resolved` on success
   f. Populate `agent_notes` with resolution details
6. Continue to Step 0c (story verification)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/bdd-cycle.md
git commit -m "feat(feedback): add Step 0b feedback report triage to BDD cycle"
```

---

### Task 12: Deploy and Verify

**Files:** None (deployment)

- [ ] **Step 1: Validate full DSL**

```bash
mcp__dazzle__dsl operation=validate
mcp__dazzle__dsl operation=lint
```

Expected: No errors.

- [ ] **Step 2: Run DSL API tests**

```bash
python3 -m dazzle pipeline run --format json --detail issues
```

Expected: All existing tests pass, new FeedbackReport tests auto-generated.

- [ ] **Step 3: Deploy to Heroku**

```bash
GIT_LFS_SKIP_PUSH=1 git push heroku feature/feedback-widget:main
```

- [ ] **Step 4: Run migration**

Dazzle auto-migrates on startup for most schema changes. If the FeedbackReport table doesn't exist after deploy, run manually:

```bash
heroku run python3 -m dazzle migrate -a aegismark
```

If migration crashes (known Dazzle issue), use `pipeline/fix_schema.py` to manually CREATE TABLE.

- [ ] **Step 5: Health check**

```bash
/usr/bin/curl -sL -o /dev/null -w "%{http_code}" https://www.aegismark.ai/
```

Expected: 200

- [ ] **Step 6: Create agent auth user on production**

```bash
heroku run python3 -m dazzle auth create-user --email agent@aegismark.ai --password Demo1234! --role agent -a aegismark
```

- [ ] **Step 7: Verify widget loads**

Login as any user at https://www.aegismark.ai/, confirm:
- Floating button visible in bottom-right
- Clicking opens slide-out panel
- Backtick shortcut works (when not in a text field)
- Submit creates a FeedbackReport visible at `/app/feedbackreport`

- [ ] **Step 8: Verify QA workspace**

Login as `super@aegismark.ai`, navigate to `/app/workspaces/qa_workspace`. Confirm the workspace loads with Incoming, In Triage, Active, Recently Resolved regions.

- [ ] **Step 9: Push to GitHub**

```bash
git push origin feature/feedback-widget
```

---

### Task 13: Capture Golden Snapshot

After verifying the deployment works with the new entity and agent user:

- [ ] **Step 1: Capture updated golden snapshot**

```bash
python3 -m pipeline.db_snapshot --capture
```

---

## Deferred Work (Not in This Plan)

| Item | Where | Notes |
|------|-------|-------|
| `feedback_widget:` DSL keyword | Dazzle framework PR | Parser, auto-entity generation, base template injection |
| `service_accounts:` DSL keyword | Dazzle framework PR | API key auth for agents |
| MCP `mcp__dazzle__feedback` tool | Dazzle framework PR | Feedback-specific MCP operations |
| Screenshot capture (Tier 2) | AegisMark feature branch | `html2canvas` integration |
| Annotation overlay (Tier 3) | AegisMark feature branch | Drawing tools, JSON coordinates |
| Notification badge | AegisMark feature branch | HTMX polling for resolved reports |
