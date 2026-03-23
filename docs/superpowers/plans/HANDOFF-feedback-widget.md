# Feedback Widget — Implementation Handoff

## Context

AegisMark (our reference Dazzle app) needs an in-app feedback widget that lets any authenticated user report issues directly from the UI. Humans record observations; agents triage and fix. This is designed as a **framework-level Dazzle feature** — not app-specific code.

The design spec and implementation plan have been ported from AegisMark to this repo:
- **Spec:** `docs/superpowers/specs/2026-03-23-feedback-widget-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-23-feedback-widget.md`

The plan was written for AegisMark's DSL file. **Your job is to implement the framework-level pieces in Dazzle itself**, so that any Dazzle app can opt in with a single DSL line.

## Branch

You are on `feature/feedback-widget`. All work goes here.

## What to Build

### 1. `feedback_widget` DSL Keyword Parser

**New file:** `src/dazzle/core/dsl_parser_impl/feedback_widget.py`

A parser mixin (like `entity.py`, `workspace.py`) that recognises:

```dsl
feedback_widget: enabled
  position: bottom-right
  shortcut: backtick
  categories: [bug, ux, visual, behaviour, enhancement, other]
  severities: [blocker, annoying, minor]
  capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
```

All sub-keys have defaults. `feedback_widget: enabled` with no configuration is valid.

Register the mixin in `src/dazzle/core/dsl_parser_impl/__init__.py`.

### 2. IR Model

**New file:** `src/dazzle/core/ir/feedback_widget.py`

Pydantic model `FeedbackWidgetSpec`:

```python
class FeedbackWidgetSpec(BaseModel):
    enabled: bool = False
    position: str = "bottom-right"
    shortcut: str = "backtick"
    categories: list[str] = ["bug", "ux", "visual", "behaviour", "enhancement", "other"]
    severities: list[str] = ["blocker", "annoying", "minor"]
    capture: list[str] = ["url", "persona", "viewport", "user_agent", "console_errors", "nav_history", "page_snapshot"]
```

Add `feedback_widget: FeedbackWidgetSpec | None = None` to `AppSpec` in `src/dazzle/core/ir/appspec.py`.

### 3. Auto-Entity Generation

When `feedback_widget` is enabled and no `FeedbackReport` entity is explicitly declared, auto-generate one with the standard fields defined in the spec (Section 1). This should happen during the linking/compilation phase, after parsing.

**Where:** Check how other post-parse entity generation works (if any), or add to the linker. The entity needs the full field set, state machine, transitions, permit/scope rules, and classify directives from the spec.

### 4. Base Template Widget Injection

**Modify:** `src/dazzle_ui/templates/base.html`

The base template already has three extension blocks:
- `{% block head_extra %}` (line 90) — for CSS
- `{% block body %}` (line 94) — for page content
- `{% block scripts_extra %}` (line 116) — for JS

Add a conditional block **after** `{% block scripts_extra %}` and before `</body>`:

```html
{# Feedback widget — injected when feedback_widget is enabled in DSL #}
{% if _feedback_widget_enabled | default(false) %}
<link rel="stylesheet" href="/static/css/feedback-widget.css">
<script src="/static/js/feedback-widget.js"></script>
<script>document.body.dataset.userRole = "{{ _current_user_role | default('') }}";</script>
{% endif %}
```

The `_feedback_widget_enabled` and `_current_user_role` template variables need to be passed from the route/template context. Check how `_tailwind_bundled` and `_use_cdn` are passed — follow the same pattern.

### 5. Static Assets

**New files:**
- `src/dazzle_ui/static/js/feedback-widget.js`
- `src/dazzle_ui/static/css/feedback-widget.css`

See the AegisMark plan (Tasks 7-8) for the full JS and CSS. Key points:

**JS (`FeedbackWidget` class):**
- Context collector: `window.onerror`, `unhandledrejection`, HTMX error events, `sessionStorage` nav history
- Floating button (bottom-right), slide-out panel
- Category quick-select buttons, severity toggle, description textarea
- Submit via `POST /feedbackreports` with JSON + `X-Idempotency-Key` header
- Backtick shortcut (suppressed in textarea/input/contenteditable)
- Rate limiting: 10 reports/hour via `localStorage`
- Offline retry: failed POSTs saved to `localStorage`, retried on next page load
- All DOM construction via `document.createElement()` — no innerHTML with user content
- Uses DaisyUI oklch colour tokens

**CSS:**
- Floating button: fixed bottom-right, `oklch(var(--p))` background
- Slide-out panel: fixed right, 24rem wide, `translateX` animation
- Category/severity buttons with selected states
- Toast notification

### 6. Template Context Injection

**Modify:** wherever the base template context is assembled (likely in `src/dazzle_back/runtime/route_generator.py` or a template context middleware).

When the AppSpec has `feedback_widget.enabled == True`:
- Set `_feedback_widget_enabled = True` in template context
- Set `_current_user_role` from the authenticated user's role

### 7. Tests

**New file:** `tests/unit/test_feedback_widget_parser.py`

Test cases:
- Parse `feedback_widget: enabled` with all defaults
- Parse with custom sub-keys
- Parse with partial sub-keys (defaults fill in)
- Invalid sub-key raises parse error
- `feedback_widget: disabled` — no widget, no auto-entity
- Auto-entity generation: when enabled and no explicit FeedbackReport entity, one is created with correct fields
- Auto-entity skipped: when explicit FeedbackReport entity exists, no auto-generation

**Parser corpus:** Add fixtures to `tests/parser_corpus/` if that's the convention.

## What NOT to Build

- **Service account auth** (`service_accounts:` keyword) — separate feature, file as issue
- **MCP feedback tool** — separate feature
- **Screenshot/annotation** (Tier 2/3) — stretch goal, not in MVP
- **QA workspace** — this is app-level DSL, not framework. AegisMark defines its own workspace.

## Key Dazzle Conventions

From CLAUDE.md:
- Type hints required on all public functions
- Pydantic models for data crossing module boundaries
- Prefer clean breaks over backward compat shims
- Keep functions small and single-purpose
- No metaprogramming or monkey-patching
- Run `ruff check` and `mypy` before committing

## Reference Files

| What | Where |
|------|-------|
| Parser mixin pattern | `src/dazzle/core/dsl_parser_impl/workspace.py` |
| IR model pattern | `src/dazzle/core/ir/workspace.py` (or similar) |
| AppSpec registration | `src/dazzle/core/ir/appspec.py` |
| Base template | `src/dazzle_ui/templates/base.html` |
| Static JS pattern | `src/dazzle_ui/static/js/dz-islands.js` |
| Static CSS pattern | `src/dazzle_ui/static/css/dz.css` |
| Template context | `src/dazzle_back/runtime/route_generator.py` |
| Parser tests | `tests/unit/test_parser.py` |
| Design spec | `docs/superpowers/specs/2026-03-23-feedback-widget-design.md` |
| Full plan (AegisMark) | `docs/superpowers/plans/2026-03-23-feedback-widget.md` |
