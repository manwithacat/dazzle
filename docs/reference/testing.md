# Testing

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

DAZZLE provides a comprehensive testing toolkit including E2E testing with Playwright, FlowSpec test generation, semantic DOM conventions, capability discovery, CRUD completeness analysis, workflow coherence checks, and RBAC validation.

---

## E2E Testing

End-to-end testing system using Playwright. Tests are auto-generated from DSL and execute against the running Dazzle app.

**Related:** [Flowspec](testing.md#flowspec), [Semantic Dom](testing.md#semantic-dom), [Authentication](access-control.md#authentication)

---

## Flowspec

JSON/YAML specification defining E2E test flows. Auto-generated from DSL but can be customized.

### Example

```dsl
{
  "flows": [{
    "id": "task_crud_create",
    "name": "Create Task",
    "priority": "high",
    "tags": ["crud", "task"],
    "steps": [
      {"type": "navigate", "url": "/tasks/new"},
      {"type": "fill", "selector": "[data-dazzle-field='title']", "value": "Test Task"},
      {"type": "click", "selector": "[data-dazzle-action='submit']"},
      {"type": "assert", "condition": "url_contains", "value": "/tasks"}
    ]
  }]
}
```

**Related:** [E2E Testing](testing.md#e2e-testing), [Semantic Dom](testing.md#semantic-dom)

---

## Semantic Dom

Convention for data attributes in the Dazzle UI runtime that enable reliable E2E testing. These attributes provide semantic meaning to DOM elements.

**Related:** [E2E Testing](testing.md#e2e-testing), [Flowspec](testing.md#flowspec)

---

## Capability Discovery

Static check of a project's app shape per persona: workspace binding, nav filtering, surface access, experience reachability and story coverage, scored 0-100 per persona. Use: discovery(operation='coherence'). CRUD coverage per entity is dsl(operation='analyze'); story-to-implementation coverage is story(operation='coverage').

**Related:** [E2E Testing](testing.md#e2e-testing), [Rbac Validation](testing.md#rbac-validation)

---

## Rbac Validation

NIST SP 800-162 compliance validation for Cedar-style permit/forbid/audit policies. Validates policy completeness, conflict detection, separation of duty, least privilege, default deny, and audit coverage. Uses the policy handler's analysis functions (_analyze, _find_conflicts, _coverage_matrix). Reference implementation: fixtures/rbac_validation/ and tests/unit/test_rbac_validation.py.

**Related:** [Capability Discovery](testing.md#capability-discovery), [E2E Testing](testing.md#e2e-testing), [Access Rules](access-control.md#access-rules)

---

## Scenario

Named demo state that sets up context for testing or demonstration. Scenarios define per-persona entry points and optional demo data.

### Syntax

```dsl
scenario <name> "<Title>":
  description: "<what this scenario tests>"
  [seed_script: "<path/to/data.json>"]

  as persona <persona_name>:
    start_route: "<url>"
    [seed_script: "<path/to/data.json>"]

  [demo:]
    [<EntityName>:]
      [- <field>: <value>, <field>: <value>]
```

### Example

```dsl
scenario happy_path "Happy Path":
  description: "Normal user flow - create, edit, complete"

  as persona customer:
    start_route: "/tickets/new"

  as persona agent:
    start_route: "/queue"

scenario with_data "Populated State":
  description: "Pre-loaded data for testing"

  as persona agent:
    start_route: "/queue"

  demo:
    Task:
      - title: "Fix login bug", status: open, priority: high
      - title: "Update docs", status: in_progress, priority: medium
```

**Related:** [Persona](ux.md#persona), [Demo Data](testing.md#demo-data)

---

## Demo Data

Seed data embedded in scenarios or generated from demo data blueprints. Provides realistic starting state for testing and demonstrations.

### Syntax

```dsl
# Inline in scenario:
demo:
  <EntityName>:
    - <field>: <value>, <field>: <value>
    - <field>: <value>, <field>: <value>

# Or via the CLI:
# dazzle demo propose  → generates blueprint
# dazzle demo generate → creates seed files
```

**Related:** [Scenario](testing.md#scenario), [Persona](ux.md#persona)

---
