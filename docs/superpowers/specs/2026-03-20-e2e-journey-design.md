# E2E Journey Testing — Persona-Driven Live Site Verification

**Date**: 2026-03-20
**Status**: Proposed
**Issue**: #557

## Problem

Dazzle projects have no automated way to verify the full persona experience against a live deployment. Static analysis (`dazzle validate`, persona journey analysis, RBAC matrix) catches structural issues but misses runtime problems: scope filtering returning zero rows, FK fields rendering as UUID text inputs, navigation dead-ends, inaccessible entities, and broken state machine workflows.

AegisMark built a proof-of-concept that walks each persona through their stories on a live Heroku deployment, recording structured observations with screenshots and cross-persona pattern analysis. This design generalises that approach into a framework feature.

## Design Principles

- **Journey testing is a mission type**, not a standalone tool. Users say "make my app better" via `/improve` — the framework dispatches the journey mission when a live deployment is available.
- **Two-phase execution**: deterministic workspace exploration (cheap, fast, no LLM) followed by LLM-assisted story verification (qualitative depth). Phase 1 alone catches 80% of issues.
- **Credential file, not auth bypass**: the agent logs in through the normal UI using credentials from `.dazzle/test_personas.toml`. No session injection — the RBAC model is exercised as deployed.
- **Structured output for AI consumption**: JSONL per persona with typed verdicts, cross-persona analysis as JSON. The HTML report is for human stakeholders.

## Section 1: Two-Phase Mission Execution

### Phase 1 — Deterministic Workspace Exploration (no LLM)

Derived entirely from the AppSpec with Playwright browser automation:

1. Log in as the persona (navigate to `/login`, fill credentials from `.dazzle/test_personas.toml`)
2. Verify landing on the correct default workspace (from `PersonaSpec.default_workspace`)
3. Systematically click every sidebar link, recording: did the page load? What columns/widgets appeared? Any console errors?
4. For each reachable list surface: check row count (zero vs populated), verify column headers match DSL field declarations
5. For each reachable create form: check fields render, identify FK fields that are UUID text inputs vs search-select
6. Screenshot each page

Phase 1 produces `JourneyStep` records with mechanical verdicts: PASS (page loads with expected content), FAIL (404, error, wrong workspace), BLOCKED (unreachable due to navigation gap), SCOPE_LEAK (sees data that scope rules should hide).

The navigation plan is built from the AppSpec: workspace regions, sidebar links, entity surfaces. No LLM call needed — this is a deterministic crawl of the persona's accessible surface area.

### Phase 2 — Story Verification (LLM-assisted)

For each of the persona's DSL stories:

1. The DazzleAgent receives a Mission with: the story's natural language description, the Phase 1 navigation map (what's reachable and what's not), and the persona context
2. The agent attempts to walk the story: navigate to relevant surfaces, evaluate whether the workflow is achievable
3. The agent records qualitative observations — the kind of insight that made AegisMark's report valuable (e.g., "Excellent 4-section wizard" or "Form has correct fields but School FK is unusable UUID text input")
4. Verdicts include: PARTIAL (works but with issues), DEAD_END (navigation leads nowhere), CONFUSING (UX is unclear)

Phase 2 uses the existing `DazzleAgent` with `PlaywrightObserver` and `PlaywrightExecutor`. The Mission system prompt includes persona context, story list, and Phase 1 results as grounding.

### Why two phases

- Phase 1 is fast, cheap, and deterministic — no LLM cost, reproducible results
- Phase 2 adds qualitative depth where judgment matters
- Projects can run Phase 1 only (`--phase explore`) for quick development checks
- Phase 1 results ground Phase 2 — the agent knows what's reachable before attempting stories

## Section 2: Data Model

### JourneyStep

The atomic unit of observation:

```python
class Verdict(StrEnum):
    PASS = "pass"           # Works as expected
    PARTIAL = "partial"     # Works but with issues
    FAIL = "fail"           # Doesn't work
    BLOCKED = "blocked"     # Unreachable due to prior failure
    DEAD_END = "dead_end"   # Navigation leads nowhere
    SCOPE_LEAK = "scope_leak"  # Sees data they shouldn't
    CONFUSING = "confusing"    # UX is unclear (Phase 2 only)
    NAV_BREAK = "nav_break"    # Navigation structure broken
    TIMEOUT = "timeout"        # Page load or action timed out

class JourneyStep(BaseModel):
    persona: str                      # "school_admin"
    story_id: str | None = None       # "ST-001" (None for Phase 1)
    phase: Literal["explore", "verify"]
    step_number: int
    action: str                       # "click", "navigate", "fill", "assert"
    target: str                       # "Sign In button", "Academic Years in sidebar"
    url_before: str
    url_after: str
    expectation: str
    observation: str
    verdict: Verdict
    reasoning: str
    screenshot_path: str | None = None
    timestamp: datetime
```

### JourneySession

Per-persona aggregate:

```python
class JourneySession(BaseModel):
    persona: str
    run_date: str
    steps: list[JourneyStep]
    verdict_counts: dict[str, int]   # {"pass": 11, "partial": 8, ...}
    stories_attempted: int
    stories_covered: int
```

### CrossPersonaPattern

Systemic finding across multiple personas:

```python
class CrossPersonaPattern(BaseModel):
    id: str                          # "CPP-001"
    title: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_personas: list[str]
    description: str
    evidence: list[str]
    recommendation: str
```

### AnalysisReport

The top-level `analysis.json` document (matches AegisMark schema):

```python
class DeadEnd(BaseModel):
    id: str                          # "DE-001"
    persona: str
    page: str                        # URL where navigation stopped
    story: str | None                # story ID if during Phase 2
    description: str

class NavBreak(BaseModel):
    id: str                          # "NB-001"
    description: str
    affected_personas: list[str]
    workaround: str | None

class Recommendation(BaseModel):
    priority: int                    # 1 = highest
    title: str
    description: str
    effort: str                      # "quick_fix", "moderate", "significant"
    affected_entities: list[str]

class AnalysisReport(BaseModel):
    run_id: str                      # "2026-03-20"
    dazzle_version: str
    deployment_url: str
    personas_analysed: int
    personas_failed: list[str]       # personas where login failed
    total_steps: int
    total_stories: int
    verdict_counts: dict[str, int]   # global counts across all personas
    cross_persona_patterns: list[CrossPersonaPattern]
    dead_ends: list[DeadEnd]
    nav_breaks: list[NavBreak]
    scope_leaks: list[str]           # descriptions of scope leak observations
    recommendations: list[Recommendation]
```

### Session directory

```
.dazzle/test_sessions/YYYY-MM-DD/
  school_admin.jsonl        # streamed incrementally
  teacher.jsonl
  governor.jsonl
  ...
  screenshots/
    school_admin-login-001.png
    school_admin-ST001-001.png
    ...
  analysis.json             # cross-persona patterns
  report.html               # human-readable HTML report
```

JSONL files are written incrementally (one line per step, flushed immediately) for crash resilience during long runs.

## Section 3: Integration Points

### CLI

```bash
dazzle e2e journey --url https://myapp.herokuapp.com              # all personas, both phases
dazzle e2e journey --url http://localhost:3000 --personas teacher,student
dazzle e2e journey --url https://staging.example.com --phase explore  # Phase 1 only (no LLM)
```

Options:
- `--url` (required): base URL of the deployment
- `--personas`: comma-separated or "all" (default: all personas with credentials in test_personas.toml)
- `--phase`: "all" (default), "explore" (Phase 1 only), "verify" (Phase 2 only, requires prior explore data)
- `--output-dir`: override `.dazzle/test_sessions/YYYY-MM-DD/`
- `--headless/--no-headless`: Playwright headless mode (default: headless)

### MCP

`test_intelligence journey` operation. A **read-only** operation that returns the most recent `analysis.json` from `.dazzle/test_sessions/`. Does not trigger a journey run (that is a CLI process operation, consistent with MCP/CLI boundary). An AI agent runs the journey via CLI first, then reads results via MCP.

### Improvement pipeline

The `/improve` skill and `dazzle improve` CLI already orchestrate quality checks. When a running deployment is detected (health check at configured URL), the journey mission is dispatched as one of the checks. Results feed into the unified improvement report.

### Credential file

`.dazzle/test_personas.toml`:

```toml
[personas.school_admin]
email = "admin@oakwood.sch.uk"
password = "test-password-123"

[personas.teacher]
email = "teacher@oakwood.sch.uk"
password = "test-password-123"
```

The `dazzle demo propose` command is extended to generate this file with credentials matching the demo users it creates.

### Report generation

HTML report from Jinja2 template at `src/dazzle_ui/templates/reports/e2e_journey.html`. The AegisMark report at `/Volumes/SSD/AegisMark/.dazzle/test_sessions/2026-03-20/report.html` is the reference design — dark theme, per-persona collapsible timelines, verdict colour coding, cross-persona pattern cards with severity, inline screenshots.

## Section 4: Cross-Persona Pattern Analysis

The analyser is deterministic (no LLM). It reads all per-persona JSONL files after completion and detects:

| Pattern | Detection method |
|---------|-----------------|
| Scope filtering returns zero rows | Persona sees empty lists when Phase 1 of another persona (e.g., admin) saw populated lists for the same entity |
| FK fields render as UUID text inputs | Phase 1 form inspection detects `<input type="text">` for ref/belongs_to fields without search-select |
| Navigation gaps | Entity declared in workspace region but not reachable from sidebar |
| RBAC button violations | Edit/Delete buttons visible to personas denied by permit rules (cross-reference with predicate algebra) |
| State machine dead-ends | Story verification hits a state transition that fails or is inaccessible |
| Common failures across personas | Same entity/surface fails for 3+ personas — systemic rather than persona-specific |

Each pattern gets: ID (CPP-NNN), severity, affected personas, description, evidence list, recommendation. This matches the AegisMark `analysis.json` schema.

## Section 5: Edge Cases and Error Handling

### Missing credential file
If `.dazzle/test_personas.toml` does not exist, the CLI aborts immediately with: `Error: .dazzle/test_personas.toml not found. Run 'dazzle demo propose' to generate test credentials, or create the file manually.` No personas are attempted.

### Persona with no stories
Phase 2 is skipped for that persona. Phase 1 (workspace exploration) still runs — it tests navigation and access without story context. The `JourneySession.stories_attempted` is 0. A log message notes: `Persona '{name}' has no stories — Phase 2 (story verification) skipped.`

### Persona with no default_workspace
If `PersonaSpec.default_workspace` is None, Phase 1 skips the landing workspace verification (step 2) and begins exploration from whatever page the login redirects to. A PARTIAL verdict is recorded: "No default_workspace declared for persona — cannot verify correct landing page."

### Deployment unreachable
Before starting any persona run, the CLI performs a health check (`GET {url}/`). If the connection is refused, times out, or returns a non-2xx status, the CLI aborts with: `Error: Deployment at {url} is not reachable (status: {code or error}).` No personas are attempted.

### Playwright not installed
The `journey` subcommand checks for Playwright availability before starting: `try: from playwright.sync_api import sync_playwright`. If ImportError, abort with: `Error: Playwright is required for journey testing. Install with: pip install playwright && playwright install chromium`. This mirrors the existing pattern in `dazzle e2e check-infra`.

### Phase 2 browser session handoff
Phase 1 and Phase 2 share the same Playwright browser context per persona. After Phase 1 completes, the browser is still authenticated — Phase 2 does not re-login. The `DazzleAgent` for Phase 2 receives a pre-authenticated `PlaywrightObserver` and `PlaywrightExecutor` wrapping the existing browser page. The Mission's `start_url` is set to the persona's default workspace (not the login page).

### `--phase verify` without prior explore data
If `--phase verify` is specified and no explore JSONL exists in the output directory for a persona, that persona is skipped with a warning: `Warning: No explore data for persona '{name}' — run with --phase explore first.`

### Login failure for a persona
If login fails (wrong credentials, account locked, 2FA required), the persona is recorded in `analysis.json` as `personas_failed` and all remaining steps for that persona are skipped. Other personas continue.

### MCP boundary
The `test_intelligence journey` MCP operation does NOT trigger a journey run (that would violate the MCP = stateless reads rule). Instead, it reads the most recent session from `.dazzle/test_sessions/` and returns the `analysis.json` content. Triggering a journey run is a CLI-only operation (`dazzle e2e journey`), consistent with the MCP/CLI boundary: MCP for knowledge, CLI for process.

### `dazzle demo propose` credential generation
When `dazzle demo propose` generates demo user records, it also writes `.dazzle/test_personas.toml` with one entry per persona that has a demo user. Credentials use the demo user's email and a standard test password (configurable via `[demo] test_password` in `dazzle.toml`, default: `"dazzle-test-2026"`). If the file already exists, it is not overwritten — a message notes: `test_personas.toml already exists, skipping credential generation.`

## Section 6: Files Affected

### New files
- `src/dazzle/agent/journey_models.py` — JourneyStep, Verdict, JourneySession, CrossPersonaPattern, AnalysisReport, DeadEnd, NavBreak, Recommendation
- `src/dazzle/agent/missions/journey.py` — JourneyMission: Phase 1 explorer + Phase 2 DazzleAgent verifier
- `src/dazzle/agent/journey_analyser.py` — cross-persona pattern detection
- `src/dazzle/agent/journey_writer.py` — session directory, JSONL streaming, screenshot management
- `src/dazzle/agent/journey_reporter.py` — Jinja2 template rendering
- `src/dazzle_ui/templates/reports/e2e_journey.html` — HTML report template
- `tests/unit/test_journey_models.py`
- `tests/unit/test_journey_analyser.py`
- `tests/unit/test_journey_writer.py`

### Modified files
- `src/dazzle/cli/e2e.py` — add `journey` subcommand
- `src/dazzle/mcp/server/handlers/test_intelligence.py` — add `journey` operation
- `src/dazzle/cli/demo.py` — extend `dazzle demo propose` to generate `test_personas.toml`

### Not modified (boundaries)
- `src/dazzle/agent/core.py` — DazzleAgent used as-is for Phase 2
- `src/dazzle/agent/transcript.py` — JourneyStep is a separate type, not an Observation extension
- `src/dazzle/agent/missions/persona_journey.py` — static analysis stays independent
