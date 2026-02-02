# Testing

Dazzle provides a tiered testing infrastructure that matches test complexity to the appropriate tooling.

## Testing Tiers

### Tier 1: API Tests (Default)

**Characteristics:**
- Fast (milliseconds per test)
- Deterministic (same result every run)
- Free (no API costs)
- Generated from DSL
- No browser required

**Best for:**
- CRUD operations
- Form validation
- API response checks
- State machine transitions

**Commands:**
```bash
dazzle test dsl-run              # Run all generated tests
dazzle test dsl-run --tag crud   # Filter by tag
```

**How it works:**
1. DSL is parsed into AppSpec
2. Test generator creates test cases from entities and relationships
3. Tests run via HTTP against the runtime server
4. Results are deterministic and fast

### Tier 2: Scripted E2E (Playwright)

**Characteristics:**
- Medium speed (seconds per test)
- Deterministic (same result every run)
- Free (no API costs)
- Uses semantic DOM selectors
- Scenarios for state setup

**Best for:**
- Navigation verification
- UI interaction flows
- Form submission with UI
- Multi-step workflows with known steps

**Commands:**
```bash
dazzle test playwright           # Run scripted E2E tests
dazzle test playwright --headed  # Show browser
```

**How it works:**
1. Scenario sets up predictable state via Dazzle Bar
2. Playwright navigates using `data-dazzle-*` selectors
3. Auth bypassed via persona switching
4. Assertions use semantic selectors

### Tier 3: Agent Tests (LLM-Driven)

**Characteristics:**
- Slow (~5 seconds per step)
- Adaptive (handles UI changes)
- Costs money (LLM API calls)
- Visual understanding

**Best for:**
- Visual verification ("does this look right?")
- Exploratory testing
- Accessibility audits
- Regression analysis when UI changes
- Testing unknown or dynamic UIs

**Commands:**
```bash
dazzle test agent                    # Run agent tests (browser visible)
dazzle test agent --headless         # Run headless
dazzle test agent --report           # Generate HTML coverage report
```

**How it works:**
1. Playwright launches a browser
2. Agent observes page state (DOM + screenshot)
3. LLM decides next action based on test goal
4. Agent executes action and repeats
5. LLM determines when goal is achieved

## When to Use Each Tier

| Scenario | Tier | Why |
|----------|------|-----|
| "Verify Task API returns correct data" | 1 | Pure API, no browser |
| "Create a task via API" | 1 | CRUD, deterministic |
| "Navigate to dashboard and see tasks" | 2 | Browser UI, scripted steps |
| "Fill form and submit" | 2 | UI interaction, known selectors |
| "Does the dashboard look correct?" | 3 | Visual verification |
| "Try to break the registration form" | 3 | Exploratory, edge cases |
| "Navigate using only keyboard" | 3 | Accessibility audit |

## Test Generation

Tests are generated from your DSL automatically:

```bash
dazzle test dsl-generate    # Generate test cases from DSL
```

This creates `dsl/tests/dsl_generated_tests.json` with:
- CRUD tests for each entity (API-based)
- Navigation tests for workspaces (Playwright, `tier1` tag)
- Validation tests for required fields
- State machine transition tests

**All generated tests are Tier 1** - deterministic and scriptable.

## Test Tags

Tests are classified by tags:

| Tag | Meaning |
|-----|---------|
| `tier1` | API-based test (no browser) |
| `tier2` or `playwright` | Scripted Playwright test |
| `tier3` or `agent` | LLM agent test |
| `crud` | Create/Read/Update/Delete operations |
| `validation` | Field validation tests |
| `state_machine` | State transition tests |

## Creating Tier 3 Tests

Tier 3 (agent) tests are NOT auto-generated. Create them manually when you need:
- Visual verification
- Adaptive/exploratory behavior
- Testing unknown or dynamic UIs

Add tests to `dsl/tests/dsl_generated_tests.json` with the `tier3` or `agent` tag:

```json
{
  "test_id": "VISUAL_DASHBOARD_CHECK",
  "title": "Verify dashboard layout after refactor",
  "description": "Check that all dashboard components render correctly",
  "tags": ["tier3", "agent", "visual", "regression"],
  "steps": [
    {
      "action": "navigate_to",
      "target": "workspace:admin_dashboard",
      "rationale": "Go to dashboard"
    },
    {
      "action": "visual_check",
      "target": "page",
      "data": {"verify": "Layout is correct with no overlapping elements"},
      "rationale": "Verify visual appearance"
    }
  ]
}
```

## MCP Tier Guidance

When using MCP tools, use `get_test_tier_guidance` to determine the right tier:

```
Tool: get_test_tier_guidance
Input: {"scenario": "verify the checkout form looks correct after CSS changes"}
Output: {"recommendation": "tier2", "reason": "This scenario suggests visual judgment..."}
```

## Coverage Reports

### Tier 1 Coverage
```bash
dazzle test dsl-run --verbose    # Shows pass/fail for each test
```

### Tier 3 Coverage (Agent)
```bash
dazzle test agent --report
```

Generates an HTML report with:
- Summary statistics
- Screenshots at each step
- LLM prompts and responses (collapsible)
- Pass/fail reasoning

Reports are saved to: `dsl/tests/reports/agent_e2e_report_YYYYMMDD_HHMMSS.html`

## Configuration

### Environment Variables

For Tier 3 (agent) tests:
```bash
# .env file
ANTHROPIC_API_KEY=sk-ant-...
```

### Test Filtering

```bash
# Tier 1 (API)
dazzle test dsl-run --tag crud
dazzle test dsl-run --entity Task

# Tier 2 (Playwright)
dazzle test playwright --scenario active_sprint

# Tier 3 (Agent)
dazzle test agent --test WS_DASHBOARD_NAV
```

## Tier 3 Use Cases (Detailed Examples)

### Complex Multi-Step Journeys

When a user flow requires decisions based on dynamic content:

```
Goal: "As a new user, sign up, create a project, invite a team member,
       and verify the invite was sent"
```

The agent adapts to:
- Form validation errors it discovers
- Dynamic element loading
- Confirmation dialogs
- Email verification steps

### Visual Regression Detection

After a UI refactor:

```
Goal: "Navigate to the dashboard and verify the layout looks correct"
```

The agent can detect:
- Missing elements that should be present
- Broken layouts or overlapping content
- Color/contrast issues
- Unexpected visual changes

### Exploratory Testing

Find edge cases humans might miss:

```
Goal: "Try to break the registration form by entering unusual inputs"
```

The agent will attempt:
- Empty submissions
- Very long strings
- Special characters
- SQL injection patterns (safely)
- XSS patterns (safely)

### Accessibility Auditing

Verify keyboard navigation and screen reader support:

```
Goal: "Complete the checkout flow using only keyboard navigation"
```

The agent checks:
- Tab order is logical
- All interactive elements are reachable
- Focus states are visible
- Skip links work correctly

### Cross-Feature Integration

Test features that span multiple surfaces:

```
Goal: "Create a task in the dashboard, then verify it appears
       in the mobile view with the correct status"
```

The agent handles:
- Context switching between views
- Data consistency verification
- State synchronization

## Best Practices

1. **Default to Tier 1** - Use API tests for CRUD and validation
2. **Use Tier 2 for UI flows** - Scripted Playwright tests for navigation and forms
3. **Reserve Tier 3 for judgment** - Only use agent tests when human-like judgment is needed
4. **Run Tiers 1-2 in CI** - Fast and deterministic
5. **Run Tier 3 periodically** - For regression and exploratory testing
6. **Use scenarios for state** - Set up predictable state before tests
