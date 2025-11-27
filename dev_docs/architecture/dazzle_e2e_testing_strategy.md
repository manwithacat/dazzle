# Dazzle End-to-End Testing Strategy (Stack-Agnostic via DSL & AppSpec)

## 1. Goals and Constraints

Dazzle is already using a DSL → AppSpec → builder pipeline to generate applications on different stacks. The new goal is to introduce **end-to-end (E2E) testing** that:

- Is **agnostic to the technology stack** (Next.js, Django, Express, etc.).
- Is **generated from the same DSL/AppSpec** that generates the app.
- Uses **Playwright (or similar)** to exercise all routes and interactions.
- Surfaces **usability and accessibility issues**, not just pure correctness bugs.
- Can be automated in CI for each stack with minimal additional work per stack.

Constraints and preferences:

- Tests should be **deterministic and declarative**, not ad-hoc scripts.
- Test logic should live at the **semantic layer** (DSL/AppSpec), not in stack-specific code.
- Stack-specific work should be thin: “adapters” and a DOM contract, not bespoke tests.

---

## 2. High-Level Architecture

Existing pipeline:

```text
DSL → AppSpec → Builder → Stack-specific app
```

Target pipeline with E2E tests:

```text
DSL → AppSpec → (1) Builder → Stack-specific app
                 (2) TestSpec → Generic Playwright runner
```

Where:

- **TestSpec** is a stack-agnostic test intermediate representation (IR).
- **Builder** is any code generator that can produce a runnable web app from AppSpec.
- **Playwright runner** is a single shared test harness that interprets TestSpec and drives the browser using a **semantic DOM contract**.

Key idea: *“Tests are another generated artefact from the same AppSpec.”*

---

## 3. Extending DSL / AppSpec to Capture Behaviour

Right now AppSpec likely captures:

- **Entities and fields** (e.g. `Customer`, `Invoice`).
- **Views/workspaces** (e.g. “Customer List”, “Customer Detail”).
- **Actions** (e.g. `Customer.create`, `Invoice.send`).

To support E2E testing, AppSpec needs to also capture **user flows and invariants**:

### 3.1. Flows

A **flow** is a declarative description of a user journey, e.g.:

- “Create a new customer.”
- “Create a customer, then create an invoice for that customer.”
- “Fail to create a customer when email is invalid.”

Attributes of a flow:

- `id`: stable identifier (`"create_customer_basic"`).
- `description`: human-readable explanation.
- `priority`: e.g. `high`, `medium`, `low` (used for regression gating).
- `preconditions`:
  - What data must already exist.
  - Which user role is active.
- `steps`: sequence of actions and assertions.

Example (conceptual):

```yaml
flows:
  - id: "create_customer_basic"
    description: "User can create a customer with minimal valid fields"
    priority: "high"
    preconditions:
      user_role: "admin"
      fixtures: ["default_org"]
    steps:
      - action: "navigate"
        target: "view:customers.new"
      - action: "fill"
        target: "field:customer.name"
        value_source: "fixture:customer_name_valid"
      - action: "fill"
        target: "field:customer.email"
        value_source: "fixture:customer_email_valid"
      - action: "click"
        target: "action:customers.create"
      - assert:
          type: "entity_exists"
          entity: "Customer"
          where:
            name: "fixture:customer_name_valid"
```

### 3.2. Invariants and Constraints

AppSpec should also describe **rules** that must hold, which become test assertions:

- Field-level constraints:
  - Required / nullable.
  - Type and format (email, URL, numeric ranges).
  - Enumerated values.
- Workflow rules:
  - “After creating a customer, the user should be redirected to the customer detail view.”
  - “Destructive actions must have a confirmation dialog.”
  - “Primary flows should complete in ≤ N steps.”

These invariants can be converted into **auto-generated tests** even if you never write explicit flows for them.

---

## 4. TestSpec: A Stack-Agnostic Test IR

Define a dedicated TestSpec format (e.g. JSON/YAML) that is the **single source of truth for tests**, generated from the AppSpec.

### 4.1. Core Schema

TestSpec should express:

- **Flows**:
  - `id`, `description`, `priority`, `tags`.
  - `steps`: `navigate`, `fill`, `click`, `assert`, `wait`, `snapshot`, etc.
- **Targets**:
  - All targets are **semantic**, not CSS/DOM selectors:
    - `view:customers.new`
    - `field:customer.name`
    - `action:customers.create`
- **Fixtures**:
  - Named test data sources: `fixture:customer_name_valid`, `fixture:invalid_email`.
- **Assertions**:
  - Domain-level: `entity_exists`, `entity_count`, `redirects_to_view`, `validation_error_for_field`.
  - UI-level: `element_visible`, `has_text`, `dialog_open`, etc.

Example schema fragment:

```yaml
fixtures:
  - id: "customer_name_valid"
    type: "string"
    value: "Acme Corp"
  - id: "customer_email_valid"
    type: "string"
    value: "billing@acme.test"

flows:
  - id: "create_customer_invalid_email"
    description: "User sees validation error when email is invalid"
    priority: "medium"
    preconditions:
      user_role: "admin"
    steps:
      - action: "navigate"
        target: "view:customers.new"
      - action: "fill"
        target: "field:customer.name"
        value_source: "fixture:customer_name_valid"
      - action: "fill"
        target: "field:customer.email"
        value_source: "fixture:invalid_email"
      - action: "click"
        target: "action:customers.create"
      - assert:
          type: "validation_error_for_field"
          target: "field:customer.email"
```

### 4.2. Usability and Accessibility Checks in TestSpec

TestSpec should also include **usability expectations** and **accessibility checks** specified at a semantic level:

```yaml
usability_checks:
  - id: "primary_flow_steps"
    apply_to_flows: "priority:high"
    rule: "step_count <= 5"

a11y_checks:
  - id: "basic_accessibility"
    apply_to_views: "all"
    rules:
      - "no_critical_axe_violations"
```

The **rules** are interpreted by the Playwright runner and use semantic knowledge (e.g. which flows are high priority).

---

## 5. DOM Contract: Semantic Attributes in All Builders

To allow a single Playwright harness to operate across all stacks, enforce a **DOM contract**: all generated UIs must include specific semantic attributes derived from AppSpec / TestSpec.

### 5.1. Semantic Attributes

Examples:

- Views / screens:

  ```html
  <div data-appspec-view="customers.new"></div>
  ```

- Fields:

  ```html
  <input
    data-appspec-field="customer.name"
    data-appspec-entity="Customer"
    data-appspec-role="input"
  />
  <label data-appspec-label-for="customer.name">Name</label>
  ```

- Actions / buttons / links:

  ```html
  <button
    data-appspec-action="customers.create"
    data-appspec-role="primary"
  >
    Save
  </button>
  ```

- Messages / validation errors:

  ```html
  <div
    data-appspec-message-for="customer.email"
    data-appspec-message-kind="validation"
  >
    Email is invalid.
  </div>
  ```

This contract should be:

- Minimal but **stable**.
- Documented and versioned.
- Enforced by builder templates (ideally with helper functions / components).

### 5.2. Builder Responsibilities

Each builder (Next.js, Django, etc.) must:

- Use shared helper functions/components that automatically inject these `data-appspec-*` attributes based on AppSpec metadata.
- Guarantee that **every interactive element** referenced in TestSpec has a corresponding element in the DOM with the correct attributes.
- Optionally, run a compile-time or lint-time check to ensure coverage (e.g. “no orphan fields without `data-appspec-field`”).

Once this is in place, TestSpec can always be resolved into concrete DOM locators via these attributes, independent of stack.

---

## 6. Playwright Runner: Interpreting TestSpec

Implement a **single Playwright test harness** that:

1. Reads TestSpec (YAML/JSON).
2. For each flow:
   - Starts a test case.
   - Executes steps against the app.
   - Applies domain-level and usability assertions.
3. Produces a standard report (per-stack, per-flow).

### 6.1. Locators via Semantic Attributes

In the Playwright harness, define a small “locator library”:

```ts
function view(page, id: string) {
  return page.locator(`[data-appspec-view="${id}"]`);
}

function field(page, id: string) {
  return page.locator(`[data-appspec-field="${id}"]`);
}

function action(page, id: string) {
  return page.locator(`[data-appspec-action="${id}"]`);
}

function messageForField(page, fieldId: string) {
  return page.locator(`[data-appspec-message-for="${fieldId}"]`);
}
```

Then steps become simple:

```ts
async function executeStep(step, page, adapters) {
  switch (step.action) {
    case "navigate":
      await page.goto(adapters.baseUrl + adapters.resolveViewUrl(step.target));
      break;
    case "fill":
      await field(page, step.targetId).fill(resolveFixture(step.valueSource));
      break;
    case "click":
      await action(page, step.targetId).click();
      break;
    case "assert":
      await performAssertion(step.assert, page, adapters);
      break;
  }
}
```

### 6.2. Assertions

Implement generic assertions, all stack-agnostic:

- `entity_exists` → optionally verify via test API (`/__test__/snapshot`) or via page content.
- `redirects_to_view(viewId)` → check URL or view attribute.
- `validation_error_for_field(fieldId)` → check for `data-appspec-message-for` element.
- `element_visible(target)` → check `.isVisible()` on semantic locator.

The Playwright code never references raw CSS; it always goes through semantic locators + the adapter.

---

## 7. Stack-Specific Adapters (Thin Layer)

Each stack must provide a **configuration object** (adapter) that tells the Playwright harness how to:

- Reach the app in test mode.
- Seed/reset data.
- Resolve semantic view IDs to URLs (if needed).

Example TypeScript adapter:

```ts
export const nextjsAdapter = {
  name: "nextjs",
  baseUrl: "http://localhost:3000",
  testApiBase: "http://localhost:3000/__test__",

  async seed(fixtures) {
    await fetch(`${this.testApiBase}/seed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fixtures }),
    });
  },

  async reset() {
    await fetch(`${this.testApiBase}/reset`, { method: "POST" });
  },

  resolveViewUrl(viewId: string) {
    // Option 1: simple mapping based on AppSpec.
    // Option 2: AppSpec includes `route` for each view.
    return routes[viewId] ?? "/";
  },
};
```

A Django adapter would be similar, just with different URLs and ports.

### 7.1. Builder Contract Checklist

For each stack, you maintain a **Builder Contract**:

1. Must emit `data-appspec-*` attributes according to the DOM contract.
2. Must expose:
   - `/__test__/seed`
   - `/__test__/reset`
   - Optional `/__test__/snapshot`.
3. Must define a standard **boot command** (`npm run dev:test`, `python manage.py runserver_test`, etc.).
4. Must ship an adapter file consumed by the Playwright harness.

Once a stack satisfies this contract, it “plugs in” to the shared E2E test system.

---

## 8. Usability and Accessibility in the Test Loop

Beyond correctness, you want to identify **usability** issues and **accessibility** problems. This can be done generically as well.

### 8.1. Usability Checks

Examples of checks you can define at AppSpec/TestSpec level:

- **Primary flows**:
  - `priority: high` flows should have `step_count <= N`.
  - Ensure at least one `primary` action is visible when the view loads.
- **Destructive Actions**:
  - Any action with `intent: destructive` must:
    - Show a confirmation dialog.
    - Require explicit user confirmation.
- **Form Feedback**:
  - Submitting invalid data must:
    - Show validation messages near the relevant fields.
    - Keep user input intact where appropriate.

These rules live in TestSpec as reusable rules and are executed by the Playwright harness, which:

- Counts steps.
- Checks visibility of `data-appspec-role="primary"`.
- Detects dialogs and confirmation flows.

### 8.2. Accessibility Checks

Integrate accessibility tools in the Playwright runner:

- Use `page.accessibility.snapshot()` for basic ARIA checks.
- Use `axe-core` via Playwright to detect standard WCAG violations.

These checks can be:

- Run on every view in `views:` section of TestSpec.
- Mapped back to AppSpec IDs (so you know which view/spec generated which issue).

---

## 9. CI Integration and Reporting

To fully benefit from this system, integrate it into CI for each AppSpec change.

### 9.1. CI Steps

For each commit / PR that changes AppSpec or builders:

1. **Generate** stack-specific code from AppSpec.
2. **Generate** TestSpec from AppSpec.
3. For each supported stack:
   - Start the app in test mode.
   - Run Playwright harness with the stack’s adapter.
   - Collect test results and artifacts (screenshots, HTML snapshots).

This gives you a **matrix** of results:

| AppSpec version | Stack    | E2E Result | Usability | Accessibility | Notes                     |
|-----------------|----------|------------|-----------|---------------|---------------------------|
| v0.3.12         | nextjs   | ✅          | 2 warnings| 1 warning     | Missing confirmation text |
| v0.3.12         | django   | ❌          | -         | -             | Missing field selector    |

### 9.2. Regression Gating

Use `priority` in flows to decide gating rules:

- All `priority: high` flows **must pass** before merge.
- `priority: medium` can be warnings at first, then later turned into gates.
- `priority: low` could be smoke tests or experiments.

---

## 10. LLM-Assisted Fixes (Optional Layer)

The E2E system itself is deterministic. To reduce manual bug fixing, you can add an **LLM-based remediation loop** on top:

1. When tests fail, capture:
   - AppSpec relevant slice.
   - Generated code snippet from the builder.
   - TestSpec flow details and Playwright error logs.
2. Feed this into an LLM “fix agent” with a constrained remit:
   - Propose patches to the builder templates or AppSpec configuration.
   - Never directly edit TestSpec unless the spec is genuinely wrong.
3. Have a human review and apply patches (at least initially).

This keeps the **testing semantics stable** while using LLMs where they shine: suggesting code changes based on failing tests.

---

## 11. Implementation Roadmap

A pragmatic implementation sequence for Dazzle:

### Phase 1 — Minimum Viable System

1. **Define DOM contract** (`data-appspec-view`, `data-appspec-field`, `data-appspec-action`).
2. Adapt **one builder** (e.g. Next.js) to emit the attributes via helper components.
3. Define a **minimal TestSpec** with:
   - A handful of flows for a simple app (e.g. “create customer”).
4. Implement a **Playwright harness** that:
   - Reads TestSpec.
   - Uses semantic locators.
   - Performs basic assertions (navigation, form submission, redirects).
5. Hook into CI for that one stack.

### Phase 2 — Generalisation and Usability

6. Extend TestSpec to cover:
   - Fixtures.
   - Negative paths (validation failures).
   - Basic usability checks (step count, primary actions).

7. Add **accessibility checks** including axe-core.

8. Build adapters for **additional stacks** (Django, Express), each fulfilling the Builder Contract.

### Phase 3 — Automation and Fix Agents

9. Integrate reporting in a structured way (JSON reports, dashboards).

10. Add an **LLM fix agent** that ingests failing tests and proposes changes to builders or AppSpec.

11. Refine the DSL/AppSpec to make flows easier to declare and reuse across Dazzle apps.

---

## 12. Summary

The core strategy is:

- Treat **tests as first-class generated artefacts** derived from the same AppSpec that drives code generation.
- Enforce a **semantic DOM contract** so that tests can be written in terms of entities, fields, actions, and views, not CSS/HTML specificity.
- Implement a **single, shared Playwright harness** that interprets a stack-agnostic TestSpec and uses thin per-stack adapters for wiring.
- Layer in **usability and accessibility checks** on top of basic functional flows.
- Optionally use **LLM agents** to suggest fixes when generated apps fail these tests, keeping the test semantics deterministic.

This gives Dazzle a robust, stack-agnostic E2E testing environment that scales with your DSL and AppSpec rather than fragmenting across stacks.
