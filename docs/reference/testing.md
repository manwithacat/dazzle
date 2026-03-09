# Testing

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

DAZZLE provides a comprehensive testing toolkit including E2E testing with Playwright, FlowSpec test generation, semantic DOM conventions, capability discovery, CRUD completeness analysis, workflow coherence checks, and RBAC validation.

---

## E2E Testing

End-to-end testing system using Playwright. Tests are auto-generated from DSL and execute against the running DNR app.

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

Convention for data attributes in DNR UI that enable reliable E2E testing. These attributes provide semantic meaning to DOM elements.

**Related:** [E2E Testing](testing.md#e2e-testing), [Flowspec](testing.md#flowspec)

---

## Capability Discovery

Agent-driven capability discovery system that explores a running Dazzle app and identifies gaps between the DSL specification and the actual implementation. Uses the generic agent framework with three modes: persona (open-ended exploration as a role), entity_completeness (static CRUD coverage analysis plus targeted verification), and workflow_coherence (static process/story integrity analysis plus targeted verification). Access via the 'discovery' MCP tool.

**Related:** [E2E Testing](testing.md#e2e-testing), [Entity Completeness](testing.md#entity-completeness), [Workflow Coherence](testing.md#workflow-coherence)

---

## Entity Completeness

Discovery mode that statically analyzes CRUD surface coverage for each entity and checks for state machine transition UI. Identifies missing list, create, edit, and view surfaces, then guides an agent to verify findings against the running app. Use: discovery(operation='run', mode='entity_completeness').

**Related:** [Capability Discovery](testing.md#capability-discovery), [Workflow Coherence](testing.md#workflow-coherence)

---

## Workflow Coherence

Discovery mode that statically analyzes process and story integrity. Checks that process human_task steps reference existing surfaces, subprocess steps reference existing processes, triggers match entities with state machines, and stories have implementing processes. Use: discovery(operation='run', mode='workflow_coherence').

**Related:** [Capability Discovery](testing.md#capability-discovery), [Entity Completeness](testing.md#entity-completeness)

---

## Rbac Validation

NIST SP 800-162 compliance validation for Cedar-style permit/forbid/audit policies. Validates policy completeness, conflict detection, separation of duty, least privilege, default deny, and audit coverage. Uses the policy handler's analysis functions (_analyze, _find_conflicts, _coverage_matrix). Reference implementation: examples/rbac_validation/ and tests/unit/test_rbac_validation.py.

**Related:** [Capability Discovery](testing.md#capability-discovery), [E2E Testing](testing.md#e2e-testing), [Access Rules](access-control.md#access-rules)

---

## Scenario

Named demo state that sets up context for testing or demonstration. Scenarios define per-persona entry points and optional demo data.

### Syntax

```dsl
scenario <name> "<Title>":
  description: "<what this scenario tests>"

  for persona <persona_name>:
    start_route: "<url>"

  [demo:]
    [<EntityName>:]
      [- <field>: <value>, <field>: <value>]
```

### Example

```dsl
scenario happy_path "Happy Path":
  description: "Normal user flow - create, edit, complete"

  for persona customer:
    start_route: "/tickets/new"

  for persona agent:
    start_route: "/queue"

scenario with_data "Populated State":
  description: "Pre-loaded data for testing"

  for persona agent:
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

# Or via MCP tool:
# demo_data(operation="propose") → generates blueprint
# demo_data(operation="generate") → creates seed files
```

**Related:** [Scenario](testing.md#scenario), [Persona](ux.md#persona)

---
