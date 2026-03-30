# QA Toolkit Design

**Date**: 2026-03-30
**Status**: Approved
**Goal**: Generalize AegisMark's autonomous quality assessment approach into Dazzle framework primitives — visual quality evaluation via LVM, story-driven verification via sidecar JSON, and process lifecycle management — with `/improve` as the orchestration layer.

## Context

AegisMark (a Dazzle consumer project) built a three-loop autonomous quality system: babysit (feedback fixes), bdd-cycle (story verification), and ux-actions (visual quality via Claude Vision). The visual quality evaluator caught the exact class of display bugs we've been fixing in the framework (#755 enum display, #756 UUID display, #757 unclosed div, #760 raw dates, #761 FK dicts). This spec generalizes that approach into the core framework.

## Design Principles

1. **Library first, CLI second** — composable Python functions in `src/dazzle/qa/`, thin CLI wrappers on top
2. **Black-box testing** — the QA package treats the running app as opaque (HTTP + Playwright), no imports from `dazzle_back` or `dazzle_ui`
3. **Pluggable evaluator** — interface for LLM evaluation, Claude Sonnet as default via `[llm]` extra
4. **Tiered cost** — cheap checks first (DSL lint), expensive checks last (LLM visual), `/improve` manages the progression
5. **AegisMark-proven taxonomy** — 8 visual quality categories battle-tested against real workspace UIs

## Architecture

```
┌──────────────────────────────────────────────────┐
│  /improve (orchestration skill)                  │
│  Tiered: DSL gaps → visual findings → stories    │
└──────────────┬───────────────────────────────────┘
               │ imports
┌──────────────▼───────────────────────────────────┐
│  src/dazzle/qa/ (library layer)                  │
│                                                  │
│  server.py    — process lifecycle context mgr    │
│  capture.py   — Playwright screenshot capture    │
│  evaluate.py  — pluggable LLM evaluator          │
│  stories.py   — sidecar loader + verifier        │
│  report.py    — findings aggregation + dedup     │
│  categories.py — 8 evaluation categories         │
└──────────────┬───────────────────────────────────┘
               │ thin wrappers
┌──────────────▼───────────────────────────────────┐
│  src/dazzle/cli/qa.py                            │
│  dazzle qa visual [--url] [--app]                │
│  dazzle qa stories [--url] [--app]               │
│  dazzle qa capture [--url] [--persona]           │
└──────────────────────────────────────────────────┘
```

## Package: `src/dazzle/qa/`

### `server.py` — Process Lifecycle

Context manager that starts a Dazzle app, waits for health, and cleans up.

```python
async with serve_app(project_dir, port=8000) as app:
    # app.site_url = "http://localhost:3000"
    # app.api_url = "http://localhost:8000"
    screenshots = await capture_workspaces(app.site_url, personas)
```

Implementation:
- Starts `dazzle serve --local` as a subprocess
- Polls `GET /api/health` every 500ms, 30s timeout
- Seeds demo data via `POST /__test__/seed` if test routes available
- On exit: SIGTERM → 5s grace → SIGKILL
- Accepts `url` parameter to skip lifecycle for already-running instances (Heroku, agent sessions)

### `capture.py` — Screenshot Capture

Playwright-based capture per persona per workspace. Knows Dazzle's URL conventions and auth flow.

**Authentication:**
- Primary: `POST /__test__/authenticate` with persona name (existing test route, returns session cookie)
- Fallback: form-based login at `/auth/login` with credentials from `.dazzle/demo_data/` or `--credentials` flag

**What it captures:**
- Each workspace defined in the AppSpec (workspace names from `load_project_appspec()` IR)
- Each persona with access to that workspace (from permit/scope rules)
- Full-page screenshot at default viewport (1280x800)

**Output model:**
```python
@dataclass
class CapturedScreen:
    persona: str          # "teacher"
    workspace: str        # "teacher_workspace"
    url: str              # "/workspace/teacher_workspace"
    screenshot: Path      # .dazzle/qa/screenshots/teacher_workspace_teacher.png
    viewport: str         # "desktop"
    timestamp: datetime
```

Screenshots saved to `.dazzle/qa/screenshots/` (gitignored). Capture is pure — no evaluation. This separation allows capture-once, evaluate-many.

### `evaluate.py` — Pluggable LLM Evaluator

**Interface:**
```python
class QAEvaluator(Protocol):
    def evaluate(self, screen: CapturedScreen, categories: list[str]) -> list[Finding]: ...

@dataclass
class Finding:
    category: str       # "data_quality", "alignment", etc.
    severity: str       # "high", "medium", "low"
    location: str       # "teacher_workspace > Needs Review region"
    description: str    # "UUID visible in student name column"
    suggestion: str     # "Apply ref_display filter to resolve FK to display name"
```

**Default Claude implementation (`ClaudeEvaluator`):**
- Reads screenshot as base64
- Sends to Claude Sonnet via `anthropic` SDK (from `[llm]` extra)
- Structured prompt covering the 8 categories with definitions and examples
- Evaluative framing: "would a human find this readable?" — not regression
- One LLM call per screenshot (all categories evaluated together)
- Parses JSON response into `Finding` objects
- Graceful degradation: if `anthropic` not installed, raises clear error directing to `pip install dazzle-dsl[llm]`

### `categories.py` — Evaluation Taxonomy

The 8 categories from AegisMark, stored as structured data for prompt construction:

| Category | Definition | Example Finding |
|----------|-----------|----------------|
| `text_wrapping` | Words broken mid-word across lines | "Username 'Alexand-er' wraps mid-word in the card header" |
| `truncation` | Content cut off by container boundaries | "Assessment title truncated to 'Introduction to...' with no tooltip" |
| `title_formatting` | Headings inline with content instead of above | "Region title 'Needs Review' sits alongside filter controls" |
| `column_layout` | Columns too narrow or cramped for their data | "Date column shows '2026-...' because column is 60px wide" |
| `empty_state` | No data shown without helpful messaging | "Table body is blank — no 'No results' message" |
| `alignment` | Inconsistent spacing or misaligned elements | "Card titles have 16px left margin except the third card (8px)" |
| `readability` | Font size, contrast, or density issues | "8px grey text on light grey background for status labels" |
| `data_quality` | Raw UUIDs, "None" values, internal field names, raw dicts | "Student column shows 'a1b2c3d4-e5f6-...' instead of student name" |

Each category has: `id`, `definition`, `example`, `severity_default`. The prompt builder reads these to construct the evaluation prompt.

### `stories.py` — Story Sidecar Verification

**Sidecar format** (`.dazzle/stories/stories.json`):
```json
[
  {
    "story_id": "ST-001",
    "title": "User creates a new task with all fields",
    "actor": "admin",
    "scope": ["Task"],
    "preconditions": ["At least one User exists for assignment"],
    "happy_path": [
      {"action": "navigate", "target": "/workspace/admin_dashboard"},
      {"action": "click", "target": "New Task button"},
      {"action": "fill_form", "fields": {"title": "Test Task"}},
      {"action": "submit"},
      {"action": "assert", "condition": "success toast visible"}
    ],
    "status": "pending"
  }
]
```

**Functions:**
- `load_stories(project_dir) -> list[Story]` — reads sidecar JSON
- `verify_story(story, site_url) -> StoryResult` — runs happy path via Playwright (login as actor, execute actions, check assertions)
- `scaffold_stories(appspec) -> list[Story]` — generates skeleton sidecar from DSL `story` blocks

**Story status lifecycle:** `pending` → `verified` (pass) or `failing` (fail). Verified stories skip unless `--recheck`.

**Scaffold command:** `dazzle qa stories init` reads DSL stories from AppSpec and generates a starter sidecar with navigate/click/assert skeletons. Human refinement expected — the scaffold provides structure, not completeness.

### `report.py` — Findings Aggregation

Merges findings from visual evaluation and story verification:
- Deduplicates by (category, location) — same issue found across personas counted once
- Severity ranking: high → medium → low
- Maps findings to `/improve` backlog gap types:
  - `Finding(category="data_quality")` → gap type `visual_quality`
  - `StoryResult(passed=False)` → gap type `story_failure`
- JSON output for machine consumption, table output for human reading

## CLI: `dazzle qa`

```bash
# Visual quality evaluation (full pipeline)
dazzle qa visual                        # auto-start app, capture all, evaluate
dazzle qa visual --url http://localhost:3000  # use running instance
dazzle qa visual --app project_tracker   # specific example app
dazzle qa visual --json                  # machine-readable output

# Screenshot capture only (no LLM)
dazzle qa capture                        # capture all workspaces
dazzle qa capture --persona teacher      # specific persona

# Story verification
dazzle qa stories                        # verify all pending stories
dazzle qa stories init                   # scaffold sidecar from DSL stories
dazzle qa stories --recheck              # re-verify all including previously passed
```

## `/improve` Integration

The existing OBSERVE → ENHANCE → BUILD → VERIFY → REPORT loop gains two new gap types and a tiered check strategy.

**New gap types:**

| Gap Type | Source | Severity Mapping |
|----------|--------|-----------------|
| `visual_quality` | `dazzle qa visual` findings | high→critical, medium→warning, low→info |
| `story_failure` | `dazzle qa stories` failures | always warning |

**Tiered OBSERVE phase:**

1. **Every cycle** (free, fast): DSL checks — lint, validate, conformance, fidelity
2. **When DSL gaps exhausted** (medium cost): Story verification — Playwright, no LLM
3. **When stories exhausted or every N cycles** (expensive): Visual QA — Playwright + LLM

The server lifecycle wraps tiers 2 and 3: one `serve_app()` context manager per cycle, all browser work inside it.

**Backlog priority:** Within a tier, priority is critical > warning > info, then alphabetical by app. Across tiers, DSL gaps take precedence (cheaper to fix, often root cause of visual issues).

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/qa/__init__.py` | Create | Public API exports |
| `src/dazzle/qa/server.py` | Create | Process lifecycle context manager |
| `src/dazzle/qa/capture.py` | Create | Playwright screenshot capture |
| `src/dazzle/qa/evaluate.py` | Create | Evaluator protocol + Claude implementation |
| `src/dazzle/qa/categories.py` | Create | 8 evaluation categories as data |
| `src/dazzle/qa/stories.py` | Create | Story sidecar loader + verifier + scaffolder |
| `src/dazzle/qa/report.py` | Create | Findings aggregation and output |
| `src/dazzle/cli/qa.py` | Create | CLI subcommands |
| `src/dazzle/cli/__init__.py` | Modify | Register `qa` subcommand |
| `.claude/commands/improve.md` | Modify | Add visual_quality and story_failure gap types |
| `pyproject.toml` | Modify | Add playwright to dev extras if not present |
| `tests/unit/test_qa_categories.py` | Create | Category data tests |
| `tests/unit/test_qa_report.py` | Create | Findings aggregation tests |
| `tests/unit/test_qa_stories.py` | Create | Story loader + scaffold tests |

## Testing

**Unit tests (no browser, no LLM):**
- Category data completeness (all 8 categories have required fields)
- Report dedup and severity ranking
- Story sidecar loading and validation
- Story scaffolding from mock AppSpec
- Finding → backlog gap type mapping

**Integration tests (browser required, marked `e2e`):**
- Server lifecycle start/health/stop against `simple_task` example
- Screenshot capture against running simple_task
- Story verification against a trivial story

**No LLM tests in CI** — the evaluator is tested via mock (fake LLM response → Finding parsing). Real LLM evaluation is manual: `dazzle qa visual --app simple_task`.

## Dependencies

- `playwright` — already in dev extras for E2E testing
- `anthropic` — in `[llm]` extra, only needed for Claude evaluator
- No new core dependencies

## Scope Boundary

This spec covers the library + CLI + `/improve` integration. It does NOT cover:
- Signal-based coordination between loops (AegisMark's `signals.py`) — not needed when `/improve` is the single orchestrator
- Visual regression baselines (pixel diff) — existing `viewport_screenshot.py` handles this separately
- Persona profile enrichment (AegisMark's `profiles.json` with "daily reality" context) — nice-to-have, not MVP
