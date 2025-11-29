# Semantic E2E Testing Implementation Plan

**Status**: ✅ COMPLETE - All 8 phases implemented
**Priority**: HIGH (takes precedence over other roadmap items)
**Created**: 2025-11-29
**Updated**: 2025-11-29
**Target**: v0.3.2

## Progress Summary

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | DOM Contract (`data-dazzle-*` attributes) |
| Phase 2 | ✅ Complete | TestSpec IR Extensions (FlowSpec, FixtureSpec, E2ETestSpec) |
| Phase 3 | ✅ Complete | Auto-generate E2ETestSpec from AppSpec |
| Phase 4 | ✅ Complete | Playwright Harness with semantic locators |
| Phase 5 | ✅ Complete | Test Endpoints (seed/reset/snapshot) |
| Phase 6 | ✅ Complete | DSL Extensions (flow syntax) |
| Phase 7 | ✅ Complete | CLI & CI Integration |
| Phase 8 | ✅ Complete | Usability & Accessibility |

---

## Executive Summary

Implement a semantic E2E testing framework where tests are generated from the same AppSpec that generates the application. Tests operate on semantic identifiers (entities, fields, actions) rather than CSS selectors, making them stack-agnostic.

---

## Current State Analysis

### What Exists

1. **IR Types for Tests** (`src/dazzle/core/ir.py:1010-1113`):
   - `TestSpec`, `TestAction`, `TestAssertion`, `TestSetupStep`
   - API-focused (create, update, delete operations)
   - Missing: UI flows, navigation, form interactions

2. **DNR UI Components** (`src/dazzle_dnr_ui/runtime/static/js/components.js`):
   - Pure JavaScript components using `createElement`
   - CSS class naming: `dnr-*` pattern
   - No semantic data attributes currently

3. **DSL Parser** (`src/dazzle/core/dsl_parser.py`):
   - Supports `test` blocks but limited to API scenarios
   - No flow/journey syntax

4. **DNR Backend** (`src/dazzle_dnr_back/`):
   - CRUD endpoints auto-generated
   - No test seeding/reset endpoints

### What Needs to Be Built

| Component | Effort | Description |
|-----------|--------|-------------|
| DOM Contract | Small | Add `data-dazzle-*` attributes to UI components |
| TestSpec IR Extensions | Medium | Add FlowSpec, fixtures, UI assertions |
| TestSpec Generator | Medium | Generate TestSpec from AppSpec |
| Playwright Harness | Medium | Interpret TestSpec, drive browser |
| Test Endpoints | Small | `/__test__/seed`, `/__test__/reset` |
| DSL Extensions | Medium | `flow` block syntax for user journeys |
| CI Integration | Small | Run tests per stack in matrix |

---

## Phase 1: DOM Contract (Week 1)

### 1.1 Define Semantic Attributes

```html
<!-- Views/Pages -->
<div data-dazzle-view="task_list"></div>
<div data-dazzle-view="task_detail"></div>

<!-- Entity Context -->
<div data-dazzle-entity="Task" data-dazzle-entity-id="uuid-123"></div>

<!-- Fields -->
<input data-dazzle-field="Task.title" data-dazzle-field-type="text" />
<input data-dazzle-field="Task.completed" data-dazzle-field-type="checkbox" />

<!-- Actions -->
<button data-dazzle-action="Task.create" data-dazzle-action-role="primary"></button>
<button data-dazzle-action="Task.delete" data-dazzle-action-role="destructive"></button>

<!-- Messages -->
<div data-dazzle-message="Task.title" data-dazzle-message-kind="validation"></div>
<div data-dazzle-message="global" data-dazzle-message-kind="success"></div>

<!-- Navigation -->
<a data-dazzle-nav="task_list"></a>
```

### 1.2 Update DNR UI Components

Files to modify:
- `src/dazzle_dnr_ui/runtime/static/js/components.js`
- `src/dazzle_dnr_ui/runtime/static/js/dom.js`
- `src/dazzle_dnr_ui/runtime/js_generator.py`

Add helper function to inject attributes:

```javascript
function withDazzleAttrs(element, attrs) {
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined) {
      element.setAttribute(`data-dazzle-${key}`, value);
    }
  }
  return element;
}
```

Update component generation to include semantic context from UISpec.

### 1.3 Deliverables (COMPLETE ✅)

- [x] `data-dazzle-*` attribute specification document (`docs/SEMANTIC_DOM_CONTRACT.md`)
- [x] Updated `components.js` with semantic attributes
- [x] Updated `dom.js` with `withDazzleAttrs` helper
- [x] Updated `surface_converter.py` to pass entity/field context
- [x] Unit tests for attribute presence (`tests/e2e/test_semantic_dom_contract.py`)

---

## Phase 2: TestSpec IR Extensions (Week 1-2)

### 2.1 New IR Types

Add to `src/dazzle/core/ir.py`:

```python
class FlowPriority(str, Enum):
    """Flow priority levels for regression gating."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class FlowStepKind(str, Enum):
    """Types of flow steps."""
    NAVIGATE = "navigate"
    FILL = "fill"
    CLICK = "click"
    WAIT = "wait"
    ASSERT = "assert"
    SNAPSHOT = "snapshot"

class FlowStep(BaseModel):
    """Single step in a user flow."""
    kind: FlowStepKind
    target: str | None = None  # Semantic target: "view:task_list", "field:Task.title"
    value: str | None = None   # For fill steps
    fixture_ref: str | None = None  # Reference to fixture
    assertion: "FlowAssertion | None" = None

class FlowAssertion(BaseModel):
    """Assertion within a flow step."""
    kind: str  # "entity_exists", "validation_error", "redirects_to", "visible", "text_contains"
    target: str | None = None
    expected: Any | None = None

class FlowPrecondition(BaseModel):
    """Preconditions for a flow."""
    user_role: str | None = None
    fixtures: list[str] = Field(default_factory=list)

class FlowSpec(BaseModel):
    """User journey/flow specification."""
    id: str
    description: str | None = None
    priority: FlowPriority = FlowPriority.MEDIUM
    preconditions: FlowPrecondition | None = None
    steps: list[FlowStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

class FixtureSpec(BaseModel):
    """Test fixture/data definition."""
    id: str
    entity: str | None = None  # For entity fixtures
    data: dict[str, Any] = Field(default_factory=dict)

class E2ETestSpec(BaseModel):
    """Complete E2E test specification generated from AppSpec."""
    app_name: str
    version: str
    fixtures: list[FixtureSpec] = Field(default_factory=list)
    flows: list[FlowSpec] = Field(default_factory=list)
    usability_rules: list[dict[str, Any]] = Field(default_factory=list)
    a11y_rules: list[dict[str, Any]] = Field(default_factory=list)
```

### 2.2 Extend AppSpec

Add to `AppSpec`:

```python
class AppSpec(BaseModel):
    # ... existing fields ...
    e2e_flows: list[FlowSpec] = Field(default_factory=list)
    fixtures: list[FixtureSpec] = Field(default_factory=list)
```

### 2.3 Deliverables (COMPLETE ✅)

- [x] New IR types in `ir.py` (FlowSpec, FlowStep, FlowAssertion, FixtureSpec, E2ETestSpec, UsabilityRule, A11yRule)
- [x] Updated `AppSpec` with `e2e_flows` and `fixtures` fields
- [x] Updated `ModuleFragment` with `e2e_flows` and `fixtures` fields
- [x] Pydantic validation for new types
- [x] Unit tests for IR serialization (`tests/unit/test_ir_e2e_types.py`)

---

## Phase 3: Auto-Generate E2ETestSpec (Week 2)

### 3.1 TestSpec Generator

Create `src/dazzle/testing/testspec_generator.py`:

```python
def generate_e2e_testspec(appspec: AppSpec) -> E2ETestSpec:
    """Generate E2ETestSpec from AppSpec."""
    flows = []
    fixtures = []

    # 1. Generate CRUD flows for each entity
    for entity in appspec.domain.entities:
        flows.extend(generate_entity_crud_flows(entity))
        fixtures.extend(generate_entity_fixtures(entity))

    # 2. Generate navigation flows for each surface
    for surface in appspec.surfaces:
        flows.extend(generate_surface_flows(surface, appspec))

    # 3. Generate validation flows from field constraints
    for entity in appspec.domain.entities:
        flows.extend(generate_validation_flows(entity))

    # 4. Add usability rules
    usability_rules = generate_usability_rules(appspec)

    return E2ETestSpec(
        app_name=appspec.name,
        version=appspec.version,
        fixtures=fixtures,
        flows=flows,
        usability_rules=usability_rules,
    )
```

### 3.2 Auto-Generated Flows

For each entity with a list surface:

```yaml
flows:
  - id: "Task_create_valid"
    description: "Create a valid Task entity"
    priority: high
    steps:
      - kind: navigate
        target: "view:task_list"
      - kind: click
        target: "action:Task.create"
      - kind: fill
        target: "field:Task.title"
        fixture_ref: "Task_title_valid"
      - kind: click
        target: "action:Task.save"
      - kind: assert
        assertion:
          kind: entity_exists
          target: Task
          expected: { title: "fixture:Task_title_valid" }

  - id: "Task_create_invalid_required"
    description: "Validation error when required field missing"
    priority: medium
    steps:
      - kind: navigate
        target: "view:task_list"
      - kind: click
        target: "action:Task.create"
      - kind: click
        target: "action:Task.save"
      - kind: assert
        assertion:
          kind: validation_error
          target: "field:Task.title"
```

### 3.3 Deliverables (COMPLETE ✅)

- [x] `testspec_generator.py` module (`src/dazzle/testing/testspec_generator.py`)
- [x] CRUD flow generation for entities (create, view, update, delete)
- [x] Validation flow generation from constraints (required fields)
- [x] Surface navigation flow generation
- [x] Fixture generation from entity schemas (valid + updated variants)
- [x] Usability and accessibility rule generation
- [x] Unit tests (`tests/unit/test_testspec_generator.py`)
- [ ] CLI command: `dazzle test generate` (deferred to Phase 7)

---

## Phase 4: Playwright Harness (Week 2-3)

### 4.1 Structure

```
src/dazzle_e2e/
├── __init__.py
├── harness.py           # Main test runner
├── locators.py          # Semantic locator functions
├── assertions.py        # Domain-level assertions
├── adapters/
│   ├── __init__.py
│   ├── base.py          # Abstract adapter
│   └── dnr.py           # DNR-specific adapter
└── templates/
    └── playwright_test.py.jinja2
```

### 4.2 Locator Library

```python
# src/dazzle_e2e/locators.py

class DazzleLocators:
    """Semantic locators for Dazzle apps."""

    def __init__(self, page):
        self.page = page

    def view(self, view_id: str):
        return self.page.locator(f'[data-dazzle-view="{view_id}"]')

    def field(self, field_id: str):
        return self.page.locator(f'[data-dazzle-field="{field_id}"]')

    def action(self, action_id: str):
        return self.page.locator(f'[data-dazzle-action="{action_id}"]')

    def entity(self, entity_name: str, entity_id: str | None = None):
        selector = f'[data-dazzle-entity="{entity_name}"]'
        if entity_id:
            selector += f'[data-dazzle-entity-id="{entity_id}"]'
        return self.page.locator(selector)

    def message(self, target: str, kind: str | None = None):
        selector = f'[data-dazzle-message="{target}"]'
        if kind:
            selector += f'[data-dazzle-message-kind="{kind}"]'
        return self.page.locator(selector)
```

### 4.3 Test Runner

```python
# src/dazzle_e2e/harness.py

async def run_flow(page, flow: FlowSpec, adapter: BaseAdapter, fixtures: dict):
    """Execute a single flow."""
    locators = DazzleLocators(page)

    # Apply preconditions
    if flow.preconditions:
        await adapter.seed(flow.preconditions.fixtures)

    for step in flow.steps:
        await execute_step(page, step, locators, adapter, fixtures)

async def execute_step(page, step: FlowStep, locators, adapter, fixtures):
    match step.kind:
        case FlowStepKind.NAVIGATE:
            url = adapter.resolve_view_url(step.target)
            await page.goto(url)

        case FlowStepKind.FILL:
            value = resolve_fixture_value(step, fixtures)
            await locators.field(step.target).fill(value)

        case FlowStepKind.CLICK:
            await locators.action(step.target).click()

        case FlowStepKind.ASSERT:
            await perform_assertion(page, step.assertion, locators, adapter)

        case FlowStepKind.WAIT:
            await page.wait_for_timeout(int(step.value or 1000))
```

### 4.4 Deliverables (COMPLETE ✅)

- [x] `dazzle_e2e` package structure (`src/dazzle_e2e/`)
- [x] Locator library with semantic selectors (`locators.py`)
- [x] Flow execution engine (`harness.py` - FlowRunner, run_flow, run_testspec)
- [x] Assertion library (`assertions.py` - 15+ domain assertions)
- [x] Base adapter interface (`adapters/base.py`)
- [x] DNR adapter implementation (`adapters/dnr.py`)
- [x] Unit tests (`tests/unit/test_e2e_harness.py`)
- [ ] pytest-playwright integration (deferred to Phase 7)

---

## Phase 5: Test Endpoints ✅ COMPLETE

### 5.1 DNR Backend Test Routes

Created `src/dazzle_dnr_back/runtime/test_routes.py` with endpoints:

- `POST /__test__/seed` - Seed fixtures with reference resolution
- `POST /__test__/reset` - Clear all test data
- `GET /__test__/snapshot` - Get database state for assertions
- `POST /__test__/authenticate` - Test authentication
- `GET /__test__/entity/{name}` - Get entity data
- `GET /__test__/entity/{name}/count` - Get entity count
- `DELETE /__test__/entity/{name}/{id}` - Delete specific entity

### 5.2 Test Mode Configuration

Added `enable_test_mode` parameter to:
- `DNRBackendApp.__init__()` - stores flag
- `DNRBackendApp.build()` - conditionally includes test routes
- `create_app()` - passes flag through
- `run_app()` - passes flag through

Test endpoints are only available when `enable_test_mode=True`.

### 5.3 Deliverables ✅

- [x] `/__test__/seed` endpoint (`src/dazzle_dnr_back/runtime/test_routes.py`)
- [x] `/__test__/reset` endpoint
- [x] `/__test__/snapshot` endpoint
- [x] `/__test__/authenticate` endpoint
- [x] Entity-specific endpoints
- [x] Test mode flag and configuration
- [x] Security: endpoints only available in test mode
- [x] Unit tests (`tests/unit/test_dnr_test_routes.py` - 23 tests)

---

## Phase 6: DSL Extensions (Week 3-4)

### 6.1 Flow Syntax in DSL

```dsl
module my_app

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false

surface task_list "Tasks":
  uses entity Task
  mode: list

# New: Flow definitions
flow create_task_basic "Create a basic task":
  priority: high
  preconditions:
    user_role: admin
  steps:
    navigate task_list
    click action:new
    fill field:title "Test Task"
    click action:save
    assert entity_exists Task where title="Test Task"

flow create_task_validation "Validation on empty title":
  priority: medium
  steps:
    navigate task_list
    click action:new
    click action:save
    assert validation_error field:title
```

### 6.2 Parser Updates

Add to `dsl_parser.py`:
- `parse_flow()` function
- Flow step parsing (navigate, click, fill, assert)
- Assertion expression parsing

### 6.3 Deliverables

- [ ] `flow` block DSL syntax
- [ ] Parser support for flows
- [ ] Grammar documentation update
- [ ] Example flows in sample projects

---

## Phase 7: CLI & CI Integration (Week 4)

### 7.1 CLI Commands

```bash
# Generate TestSpec from AppSpec
dazzle test generate

# Run E2E tests
dazzle test run

# Run specific flow
dazzle test run --flow create_task_basic

# Run with specific priority
dazzle test run --priority high
```

### 7.2 CI Workflow

```yaml
# .github/workflows/ci.yml

semantic-e2e:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6

    - name: Install Playwright
      run: npx playwright install chromium

    - name: Start DNR server
      run: |
        cd examples/simple_task
        dazzle dnr serve --test-mode &
        sleep 5

    - name: Run E2E tests
      run: |
        cd examples/simple_task
        dazzle test run --priority high

    - name: Upload test artifacts
      uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: playwright-report
        path: playwright-report/
```

### 7.3 Deliverables ✅

- [x] `dazzle test generate` command - Generate E2ETestSpec from AppSpec
- [x] `dazzle test run` command - Run E2E tests with Playwright
- [x] `dazzle test list` command - List available test flows
- [x] `dazzle dnr serve --test-mode` flag - Enable test endpoints
- [x] CI workflow for semantic E2E (`semantic-e2e` job in ci.yml)
- [x] Sync methods in DNRAdapter for CLI usage

### 7.4 Files Changed

- `src/dazzle/cli.py` - Added `test` sub-app with generate, run, list commands
- `src/dazzle_e2e/adapters/dnr.py` - Added sync methods for CLI usage
- `src/dazzle_dnr_ui/runtime/combined_server.py` - Added `enable_test_mode` parameter
- `.github/workflows/ci.yml` - Added `semantic-e2e` job

### 7.5 Bug Fixes During Implementation

- Fixed lexer conflict: `priority`, `high`, `medium`, `low` were incorrectly added as keywords
  - These are commonly used as enum values (e.g., `priority: enum[low,medium,high]=medium`)
  - Changed to handle them as identifiers in the flow parser
- Added missing `VIEW` TokenType to lexer

---

## Phase 8: Usability & Accessibility ✅ COMPLETE

### 8.1 Usability Rules ✅

Implemented `src/dazzle_e2e/usability.py`:

- **UsabilityChecker**: Evaluates usability rules against flows and pages
- **Supported Rule Types**:
  - `max_steps`: Check that flows complete in acceptable step counts
  - `destructive_confirm`: Check destructive actions have confirmation
  - `primary_action_visible`: Check primary actions visible on page load
  - `validation_placement`: Check validation messages near fields
- **Rule Targeting**: By priority, tag, entity, or all flows
- **Severity Levels**: Warning vs Error violations

### 8.2 Accessibility Integration ✅

Implemented `src/dazzle_e2e/accessibility.py`:

- **AccessibilityChecker**: Loads and runs axe-core in browser
- **WCAG Level Checking**: Level A, AA, AAA support
- **Dazzle Element Mapping**: Maps violations to semantic elements
- **Result Types**: AxeResults, AxeViolation, AxeNode, AxePass
- **A11yRule Filtering**: Violations filtered by E2ETestSpec rules

### 8.3 WCAG Violation Mapping ✅

Implemented `src/dazzle_e2e/wcag_mapping.py`:

- **WCAGMapper**: Maps violations to AppSpec elements
- **WCAG Criteria Database**: 25+ WCAG 2.1 success criteria
- **Axe Rule Mapping**: 45+ axe rules mapped to WCAG criteria
- **Suggested Fixes**: Rule-specific fix suggestions
- **Violation Report**: Human-readable report generation

### 8.4 Deliverables ✅

- [x] Usability rule engine (`src/dazzle_e2e/usability.py`)
- [x] axe-core integration (`src/dazzle_e2e/accessibility.py`)
- [x] WCAG violation mapping (`src/dazzle_e2e/wcag_mapping.py`)
- [x] Unit tests:
  - `tests/unit/test_usability_checker.py` (17 tests)
  - `tests/unit/test_accessibility_checker.py` (21 tests)
  - `tests/unit/test_wcag_mapping.py` (23 tests)

---

## Success Criteria

1. **DOM Contract**: All DNR UI components emit `data-dazzle-*` attributes
2. **Auto-Generation**: `dazzle test generate` produces valid E2ETestSpec
3. **Playwright Integration**: Tests run via `dazzle test run`
4. **CI Gate**: High-priority flows block PRs on failure
5. **Coverage**: 100% of entities have auto-generated CRUD tests
6. **Stack-Agnostic**: Same TestSpec works across DNR (and future stacks)

---

## Files Created/Modified ✅

### New Files Created

| Path | Purpose |
|------|---------|
| `src/dazzle/testing/__init__.py` | Testing package ✅ |
| `src/dazzle/testing/testspec_generator.py` | Generate E2ETestSpec from AppSpec ✅ |
| `src/dazzle_e2e/__init__.py` | E2E harness package ✅ |
| `src/dazzle_e2e/harness.py` | Playwright test runner ✅ |
| `src/dazzle_e2e/locators.py` | Semantic locator library ✅ |
| `src/dazzle_e2e/assertions.py` | Domain-level assertions ✅ |
| `src/dazzle_e2e/adapters/base.py` | Base adapter interface ✅ |
| `src/dazzle_e2e/adapters/dnr.py` | DNR-specific adapter ✅ |
| `src/dazzle_e2e/usability.py` | Usability rule engine ✅ |
| `src/dazzle_e2e/accessibility.py` | axe-core integration ✅ |
| `src/dazzle_e2e/wcag_mapping.py` | WCAG violation mapper ✅ |
| `tests/unit/test_usability_checker.py` | Usability tests (17) ✅ |
| `tests/unit/test_accessibility_checker.py` | Accessibility tests (21) ✅ |
| `tests/unit/test_wcag_mapping.py` | WCAG mapping tests (23) ✅ |
| `tests/unit/test_e2e_harness.py` | Harness tests ✅ |
| `tests/unit/test_ir_e2e_types.py` | IR type tests ✅ |
| `tests/unit/test_testspec_generator.py` | Generator tests ✅ |
| `tests/unit/test_flow_parsing.py` | Flow parsing tests (22) ✅ |
| `tests/e2e/test_semantic_dom_contract.py` | DOM contract tests ✅ |
| `docs/SEMANTIC_DOM_CONTRACT.md` | DOM contract specification ✅ |

### Modified Files

| Path | Change |
|------|--------|
| `src/dazzle/core/ir.py` | Add FlowSpec, FixtureSpec, E2ETestSpec, UsabilityRule, A11yRule ✅ |
| `src/dazzle/core/dsl_parser.py` | Parse `flow` blocks ✅ |
| `src/dazzle/core/lexer.py` | Add flow/E2E keywords ✅ |
| `src/dazzle/cli.py` | Add `test generate`, `test run`, `test list` commands ✅ |
| `src/dazzle_dnr_ui/runtime/static/js/components.js` | Add data-dazzle-* attributes ✅ |
| `src/dazzle_dnr_ui/runtime/static/js/dom.js` | Add withDazzleAttrs helper ✅ |
| `src/dazzle_dnr_ui/runtime/js_generator.py` | Pass semantic context to components ✅ |
| `src/dazzle_dnr_ui/runtime/combined_server.py` | Add test-mode flag, proxy test routes ✅ |
| `src/dazzle_dnr_back/runtime/server.py` | Add test endpoints ✅ |
| `.github/workflows/ci.yml` | Add semantic-e2e job ✅ |

---

## Dependencies

- `playwright` (Python) - Browser automation
- `pytest-playwright` - Pytest integration
- `axe-core` (npm) - Accessibility testing

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Playwright flaky tests | Use semantic locators, proper waits |
| DOM contract drift | Lint-time validation of attributes |
| Test data isolation | Per-test database reset |
| CI slowness | Parallel test execution, priority filtering |

---

## Next Steps

1. **Approve this plan**
2. Start Phase 1: DOM Contract implementation
3. Weekly progress review against milestones
