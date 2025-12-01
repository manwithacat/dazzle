# DAZZLE E2E Testing Guide

**Version**: 1.0
**Last Updated**: 2025-12-01

This guide covers DAZZLE's specification-driven E2E testing infrastructure.

---

## Overview

DAZZLE provides a unique approach to E2E testing:

- **Specification-driven**: Tests are auto-generated from your DSL, not hand-written
- **Semantic selectors**: Tests use `data-dazzle-*` attributes, not fragile CSS/XPath
- **Stack-agnostic**: Same tests run on DNR, Django, Express, or any adapter
- **Quality integrated**: Built-in usability and accessibility checking

---

## Quick Start

```bash
# 1. Start your app in test mode
dazzle dnr serve --test-mode

# 2. Generate test specification
dazzle test generate -o testspec.json

# 3. Run the tests
dazzle test run

# 4. View results
dazzle test list
```

---

## Table of Contents

1. [CLI Commands](#cli-commands)
2. [Test Generation](#test-generation)
3. [Running Tests](#running-tests)
4. [FlowSpec Architecture](#flowspec-architecture)
5. [Semantic DOM Contract](#semantic-dom-contract)
6. [Authentication Testing](#authentication-testing)
7. [Docker-Based Testing](#docker-based-testing)
8. [Writing Custom Flows](#writing-custom-flows)
9. [Accessibility & Usability](#accessibility--usability)

---

## CLI Commands

### Generate Tests

Generate an E2E test specification from your DSL:

```bash
# Print to stdout
dazzle test generate

# Save to file
dazzle test generate -o testspec.json

# YAML format
dazzle test generate --format yaml

# Skip auto-generated flows (use your own)
dazzle test generate --no-flows

# Skip auto-generated fixtures
dazzle test generate --no-fixtures

# Specify manifest location
dazzle test generate -m path/to/dazzle.toml
```

**Output**: JSON/YAML with fixtures, flows, usability rules, and accessibility rules.

### Run Tests

Execute tests against a running application:

```bash
# Run all tests
dazzle test run

# Filter by priority
dazzle test run --priority high

# Filter by tag
dazzle test run --tag crud

# Run specific flow
dazzle test run --flow Task_create_valid

# Custom URLs
dazzle test run --base-url http://localhost:3000 --api-url http://localhost:8000

# Browser mode (default: headless)
dazzle test run --headed

# Custom timeout (ms)
dazzle test run --timeout 30000

# Save results
dazzle test run -o results.json

# Verbose output
dazzle test run -v
```

**Prerequisites**:
- App running: `dazzle dnr serve --test-mode`
- Playwright installed: `pip install playwright && playwright install chromium`

### List Tests

View available test flows:

```bash
# List all flows
dazzle test list

# Filter by priority
dazzle test list --priority high

# Filter by tag
dazzle test list --tag validation
```

---

## Test Generation

DAZZLE automatically generates comprehensive tests from your DSL.

### Auto-Generated Flows

For each entity, DAZZLE generates:

| Flow Type | ID Pattern | Description |
|-----------|------------|-------------|
| Create | `{Entity}_create_valid` | Create with valid data |
| View | `{Entity}_view_detail` | View entity detail |
| Update | `{Entity}_update_valid` | Update with valid data |
| Delete | `{Entity}_delete_valid` | Delete entity |

For field constraints:

| Flow Type | ID Pattern | Description |
|-----------|------------|-------------|
| Required | `{Entity}_{field}_required` | Required field validation |
| Type | `{Entity}_{field}_invalid_type` | Type validation |
| Length | `{Entity}_{field}_too_long` | Length validation |

For surfaces:

| Flow Type | ID Pattern | Description |
|-----------|------------|-------------|
| Navigation | `{Surface}_navigation` | Surface accessibility |

### Auto-Generated Fixtures

```json
{
  "fixtures": [
    {
      "id": "Task_valid",
      "entity": "Task",
      "data": {
        "title": "Test Task",
        "completed": false
      }
    },
    {
      "id": "Task_updated",
      "entity": "Task",
      "data": {
        "title": "Updated Task",
        "completed": true
      }
    }
  ]
}
```

---

## Running Tests

### Test Execution Flow

1. **Preconditions**: Set up fixtures, authenticate if needed
2. **Steps**: Execute navigation, form fills, clicks
3. **Assertions**: Verify expected outcomes
4. **Cleanup**: Reset state between flows

### Example Results

```json
{
  "total": 15,
  "passed": 14,
  "failed": 1,
  "flows": [
    {
      "id": "Task_create_valid",
      "passed": true,
      "duration_ms": 1234
    },
    {
      "id": "Task_title_required",
      "passed": false,
      "error": "Expected validation error not shown",
      "failed_step": {
        "kind": "assert",
        "target": "message:Task.title"
      }
    }
  ]
}
```

---

## FlowSpec Architecture

### Core Types

```python
# Flow definition
FlowSpec:
  id: str                    # Unique identifier
  description: str           # Human-readable description
  priority: HIGH|MEDIUM|LOW  # Execution priority
  preconditions:
    user_role: str           # Required role
    fixtures: list[str]      # Fixture IDs to seed
    authenticated: bool      # Require auth
    view: str                # Starting view
  steps: list[FlowStep]      # Actions to perform
  tags: list[str]            # Categorization tags
  entity: str                # Primary entity

# Step definition
FlowStep:
  kind: navigate|fill|click|wait|assert|snapshot
  target: str                # Semantic target
  value: str                 # Value for fill/wait
  fixture_ref: str           # Reference fixture data
  assertion: FlowAssertion   # Inline assertion
  description: str           # Step description

# Assertion definition
FlowAssertion:
  kind: entity_exists|visible|text_contains|...
  target: str                # What to check
  expected: any              # Expected value
  operator: eq|ne|gt|lt|...  # Comparison operator
```

### Assertion Types

**Entity Assertions**:
- `entity_exists` - Entity exists in database
- `entity_not_exists` - Entity doesn't exist
- `count` - Entity count matches

**UI Assertions**:
- `visible` - Element is visible
- `not_visible` - Element is hidden
- `text_contains` - Text is present
- `validation_error` - Validation message shown
- `field_value` - Field has expected value

**Navigation Assertions**:
- `redirects_to` - Redirected to view

**Auth Assertions**:
- `is_authenticated` - User is logged in
- `is_not_authenticated` - User is logged out
- `login_succeeded` - Login was successful
- `login_failed` - Login failed with error
- `route_protected` - Route requires auth
- `has_persona` - User has persona

---

## Semantic DOM Contract

Tests use semantic attributes instead of CSS selectors. This makes tests resilient to UI changes.

### Attribute Reference

| Element | Attribute | Example |
|---------|-----------|---------|
| View | `data-dazzle-view` | `data-dazzle-view="task_list"` |
| Entity | `data-dazzle-entity` | `data-dazzle-entity="Task"` |
| Entity ID | `data-dazzle-entity-id` | `data-dazzle-entity-id="123"` |
| Field | `data-dazzle-field` | `data-dazzle-field="Task.title"` |
| Field Type | `data-dazzle-field-type` | `data-dazzle-field-type="text"` |
| Action | `data-dazzle-action` | `data-dazzle-action="Task.create"` |
| Message | `data-dazzle-message` | `data-dazzle-message="Task.title"` |
| Table | `data-dazzle-table` | `data-dazzle-table="Task"` |
| Row | `data-dazzle-row` | `data-dazzle-row="Task"` |
| Form | `data-dazzle-form` | `data-dazzle-form="Task"` |
| Dialog | `data-dazzle-dialog` | `data-dazzle-dialog="confirm"` |

### Semantic Targets

FlowSpec uses semantic target strings:

```
view:task_list           # Navigate to view
entity:Task              # Entity container
field:Task.title         # Form field
action:Task.create       # Button/action
message:Task.title       # Validation message
row:Task                 # Table row
cell:Task.title          # Table cell
dialog:confirm_delete    # Dialog
nav:task_list            # Navigation link
auth:login_button        # Auth element
```

### Example HTML

```html
<!-- View container -->
<div data-dazzle-view="task_list">

  <!-- Table -->
  <table data-dazzle-table="Task">
    <tr data-dazzle-row="Task" data-dazzle-entity-id="123">
      <td data-dazzle-cell="Task.title">My Task</td>
    </tr>
  </table>

  <!-- Form -->
  <form data-dazzle-form="Task" data-dazzle-form-mode="create">
    <input data-dazzle-field="Task.title"
           data-dazzle-field-type="text"
           data-dazzle-required="true" />
    <span data-dazzle-message="Task.title"
          data-dazzle-message-kind="validation"></span>
    <button data-dazzle-action="Task.create"
            data-dazzle-action-role="primary">Create</button>
  </form>

</div>
```

See [SEMANTIC_DOM_CONTRACT.md](SEMANTIC_DOM_CONTRACT.md) for the complete specification.

---

## Authentication Testing

### Auto-Generated Auth Flows

When your app has authentication, DAZZLE generates:

| Flow ID | Description |
|---------|-------------|
| `auth_login_valid` | Login with valid credentials |
| `auth_login_invalid` | Login with wrong password |
| `auth_logout` | Logout flow |
| `auth_register` | Registration flow |
| `auth_route_protected` | Protected route redirect |
| `auth_persona_{name}` | Persona-specific access |

### Auth Fixtures

```json
{
  "fixtures": [
    {
      "id": "auth_test_user",
      "entity": "_User",
      "data": {
        "email": "test@example.com",
        "password": "testpass123",
        "display_name": "Test User"
      }
    },
    {
      "id": "auth_invalid_credentials",
      "entity": "_User",
      "data": {
        "email": "test@example.com",
        "password": "wrongpassword"
      }
    }
  ]
}
```

### Auth Semantic Targets

```
auth:login_button        # Login trigger
auth:logout_button       # Logout trigger
auth:modal               # Auth modal/dialog
auth:form                # Login/register form
auth:field.email         # Email input
auth:field.password      # Password input
auth:error               # Error message
auth:submit              # Submit button
auth:mode_toggle.register # Switch to register
```

### Standard Auth Element IDs

DNR uses these IDs for auth elements:

- `#dz-auth-modal` - Auth modal container
- `#dz-auth-form` - Login/register form
- `#dz-auth-submit` - Form submit button
- `#dz-auth-error` - Error message display

---

## Docker-Based Testing

For CI/CD, use Docker-based E2E testing:

```bash
# Test a single example
dazzle e2e run simple_task

# With coverage threshold
dazzle e2e run contact_manager -c 80

# Save screenshots
dazzle e2e run ops_dashboard --copy-screenshots

# Test all examples
dazzle e2e run-all

# Clean up containers
dazzle e2e clean
```

### What It Does

1. Builds DNR Docker container with your app
2. Starts containers with health checks
3. Runs Playwright tests inside container
4. Captures screenshots and UX coverage
5. Cleans up containers

### UX Coverage

Docker tests calculate UX coverage:

- Surface coverage: % of surfaces tested
- Entity coverage: % of entities with CRUD tests
- Action coverage: % of actions exercised

---

## Writing Custom Flows

You can add custom flows to your `testspec.json`:

```json
{
  "flows": [
    {
      "id": "custom_workflow",
      "description": "Complete task workflow",
      "priority": "high",
      "tags": ["workflow", "custom"],
      "preconditions": {
        "authenticated": true,
        "fixtures": ["Task_valid"]
      },
      "steps": [
        {
          "kind": "navigate",
          "target": "view:task_list"
        },
        {
          "kind": "click",
          "target": "row:Task",
          "description": "Select first task"
        },
        {
          "kind": "fill",
          "target": "field:Task.title",
          "value": "Updated Title"
        },
        {
          "kind": "click",
          "target": "action:Task.save"
        },
        {
          "kind": "assert",
          "assertion": {
            "kind": "text_contains",
            "target": "message:global",
            "expected": "saved"
          }
        }
      ]
    }
  ]
}
```

### Step Kinds

| Kind | Description | Required Fields |
|------|-------------|-----------------|
| `navigate` | Go to view/URL | `target` |
| `fill` | Fill form field | `target`, `value` or `fixture_ref` |
| `click` | Click element | `target` |
| `wait` | Wait for condition | `target` or `value` (ms) |
| `assert` | Verify condition | `assertion` |
| `snapshot` | Capture DB state | - |

---

## Accessibility & Usability

### Accessibility Checking

DAZZLE integrates axe-core for WCAG compliance:

```python
from dazzle_e2e import AccessibilityChecker

checker = AccessibilityChecker(page)
results = await checker.run_axe()

for violation in results.violations:
    print(f"{violation.impact}: {violation.description}")
```

**WCAG Levels**: A, AA, AAA

### Usability Rules

Auto-generated usability checks:

| Rule | Description |
|------|-------------|
| `max_steps` | High-priority flows complete in few steps |
| `primary_action_visible` | Primary action always visible |
| `destructive_confirm` | Destructive actions require confirmation |
| `validation_placement` | Validation messages near fields |

```python
from dazzle_e2e import UsabilityChecker

checker = UsabilityChecker(testspec.usability_rules)
result = checker.check_flow(flow)

if not result.passed:
    for violation in result.violations:
        print(f"{violation.severity}: {violation.details}")
```

---

## Adapters

Tests run through adapters that handle stack-specific details.

### DNR Adapter

Default adapter for DNR runtime:

```python
from dazzle_e2e.adapters.dnr import DNRAdapter

adapter = DNRAdapter(
    base_url="http://localhost:3000",
    api_url="http://localhost:8000"
)

# Seed test data
await adapter.seed(fixtures)

# Authenticate
await adapter.authenticate(email="test@example.com", password="pass")

# Check entities
entities = await adapter.get_entities("Task")
```

### Test Endpoints

DNR exposes test endpoints when started with `--test-mode`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/__test__/seed` | POST | Seed fixtures |
| `/__test__/reset` | POST | Reset database |
| `/__test__/snapshot` | GET | Get database state |
| `/__test__/authenticate` | POST | Create test session |
| `/__test__/entity/{entity}/count` | GET | Get entity count |
| `/__test__/create_user` | POST | Create test user |

---

## Best Practices

1. **Use semantic targets**: Never use CSS selectors directly
2. **Generate first**: Let DAZZLE generate tests, then customize
3. **Tag flows**: Use tags for filtering (`crud`, `auth`, `workflow`)
4. **Set priorities**: Mark critical flows as `high` priority
5. **Test in CI**: Use Docker-based testing for CI/CD
6. **Check accessibility**: Run WCAG checks on all views
7. **Monitor coverage**: Aim for >80% surface/entity coverage

---

## Troubleshooting

### Tests fail to find elements

- Check `data-dazzle-*` attributes in your HTML
- Verify semantic target format (e.g., `field:Entity.field`)
- Increase timeout: `--timeout 10000`

### Authentication tests fail

- Ensure `--test-mode` flag is used
- Check auth endpoint URLs
- Verify auth element IDs match standard (`#dz-auth-*`)

### Docker tests hang

```bash
# Clean up stuck containers
dazzle e2e clean

# Check container logs
docker logs dazzle-dnr-test
```

---

## Related Documentation

- [SEMANTIC_DOM_CONTRACT.md](SEMANTIC_DOM_CONTRACT.md) - Complete attribute specification
- [CAPABILITIES.md](CAPABILITIES.md) - Feature overview
- [dnr/CLI.md](dnr/CLI.md) - DNR command reference
