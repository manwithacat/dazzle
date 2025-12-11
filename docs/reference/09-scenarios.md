# Personas and Scenarios

Personas define user types. Scenarios define test data states for development and demonstration.

## Personas

Define user archetypes with their goals and preferences:

```dsl
persona persona_id "Display Name":
  description: "Description of this user type"
  goals: "Goal 1", "Goal 2", "Goal 3"
  proficiency: novice|intermediate|expert
  default_workspace: workspace_name
  default_route: "/path"
```

### Persona Properties

| Property | Description |
|----------|-------------|
| `description` | Human-readable description |
| `goals` | List of user goals (comma-separated strings) |
| `proficiency` | Skill level: `novice`, `intermediate`, `expert` |
| `default_workspace` | Starting workspace for this persona |
| `default_route` | Default URL path |

### Persona Examples

```dsl
persona teacher "Teacher":
  description: "A classroom teacher managing students and assignments"
  goals: "Grade student work", "Track attendance", "Communicate with parents"
  proficiency: intermediate
  default_workspace: classroom_dashboard
  default_route: "/classes"

persona student "Student":
  description: "A student completing assignments and tracking progress"
  goals: "Submit assignments", "Check grades", "View schedule"
  proficiency: novice
  default_workspace: student_dashboard
  default_route: "/my-work"

persona admin "Administrator":
  description: "School administrator with full system access"
  goals: "Manage users", "Generate reports", "Configure settings"
  proficiency: expert
  default_workspace: admin_dashboard
  default_route: "/admin"

persona finance_manager "Finance Manager":
  description: "Manages invoices, payments, and financial reporting"
  goals: "Process payments", "Generate financial reports", "Manage budgets"
  proficiency: expert
  default_workspace: finance_dashboard
  default_route: "/finance"

persona sales_rep "Sales Representative":
  description: "Manages customer accounts and sales pipeline"
  goals: "Track deals", "Update customer info", "Meet quotas"
  proficiency: intermediate
  default_workspace: sales_pipeline
  default_route: "/deals"
```

## Scenarios

Define application states with seed data for testing and demos:

```dsl
scenario scenario_id "Display Name":
  description: "Description of this scenario"
  seed_script: "path/to/seed-data.json"

  for persona persona_name:
    start_route: "/path"
    seed_script: "path/to/persona-specific-data.json"

  demo:
    EntityName:
      - field: value, field: value
```

### Scenario Properties

| Property | Description |
|----------|-------------|
| `description` | Human-readable description |
| `seed_script` | Path to JSON seed data file |
| `for persona` | Persona-specific configuration |
| `demo` | Inline demo data |

### Per-Persona Configuration

| Property | Description |
|----------|-------------|
| `start_route` | Starting URL for this persona in this scenario |
| `seed_script` | Additional seed data for this persona |

### Scenario Examples

```dsl
scenario empty_state "Fresh Start":
  description: "New installation with no data - for testing onboarding"

  for persona admin:
    start_route: "/setup"

  for persona teacher:
    start_route: "/welcome"

scenario busy_term "Busy Term":
  description: "Mid-year state with active classes, assignments, and grades"
  seed_script: "scenarios/busy_term.json"

  for persona teacher:
    start_route: "/classes"
    seed_script: "scenarios/teacher_assignments.json"

  for persona student:
    start_route: "/my-assignments"
    seed_script: "scenarios/student_work.json"

  for persona admin:
    start_route: "/reports"

scenario end_of_year "End of Year":
  description: "End of school year with completed courses and final grades"
  seed_script: "scenarios/end_of_year.json"

  for persona teacher:
    start_route: "/grade-reports"

  for persona admin:
    start_route: "/annual-reports"
```

## Demo Fixtures

Define inline test data directly in DSL:

```dsl
demo:
  EntityName:
    - field1: value, field2: value, field3: value
    - field1: value, field2: value, field3: value
```

### Demo Data Types

| Type | Syntax |
|------|--------|
| String | `"value"` |
| Number | `123` or `45.67` |
| Boolean | `true` or `false` |
| Identifier | `pending` (for enums) |

### Demo Examples

```dsl
# Standalone demo block
demo:
  Task:
    - title: "Review PRs", status: pending, priority: high
    - title: "Write docs", status: in_progress, priority: medium
    - title: "Fix bug #123", status: done, priority: high

  User:
    - name: "Alice", email: "alice@example.com", role: admin
    - name: "Bob", email: "bob@example.com", role: user

# Demo within scenario
scenario sales_demo "Sales Demo":
  description: "Sales pipeline demonstration"

  demo:
    Customer:
      - name: "Acme Corp", status: active, revenue: 50000
      - name: "Tech Inc", status: prospect, revenue: 0
      - name: "Global Ltd", status: active, revenue: 125000

    Deal:
      - title: "Enterprise License", customer: "Acme Corp", value: 25000, stage: negotiation
      - title: "Starter Package", customer: "Tech Inc", value: 5000, stage: qualification
      - title: "Expansion", customer: "Global Ltd", value: 75000, stage: closed_won

    Activity:
      - type: call, customer: "Acme Corp", notes: "Discussed pricing", date: "2024-01-15"
      - type: email, customer: "Tech Inc", notes: "Sent proposal", date: "2024-01-16"
```

## Complete Example

```dsl
# Personas
persona warehouse_manager "Warehouse Manager":
  description: "Oversees inventory and fulfillment operations"
  goals: "Maintain stock levels", "Process orders", "Manage staff"
  proficiency: expert
  default_workspace: warehouse_dashboard
  default_route: "/warehouse"

persona picker "Warehouse Picker":
  description: "Picks and packs orders for shipping"
  goals: "Pick orders efficiently", "Maintain accuracy"
  proficiency: novice
  default_workspace: pick_queue
  default_route: "/pick"

persona customer_service "Customer Service":
  description: "Handles customer inquiries and order issues"
  goals: "Resolve issues quickly", "Track order status"
  proficiency: intermediate
  default_workspace: support_dashboard
  default_route: "/support"

# Scenarios
scenario normal_operations "Normal Operations":
  description: "Typical day with normal order volume"
  seed_script: "scenarios/normal_day.json"

  for persona warehouse_manager:
    start_route: "/warehouse/overview"

  for persona picker:
    start_route: "/pick/queue"

scenario peak_season "Peak Season":
  description: "High volume period (Black Friday, holidays)"
  seed_script: "scenarios/peak_season.json"

  for persona warehouse_manager:
    start_route: "/warehouse/alerts"
    seed_script: "scenarios/manager_alerts.json"

  for persona picker:
    start_route: "/pick/priority"

  demo:
    Order:
      - order_number: "ORD-2024-0001", status: pending, priority: high, items_count: 5
      - order_number: "ORD-2024-0002", status: pending, priority: normal, items_count: 2
      - order_number: "ORD-2024-0003", status: picking, priority: high, items_count: 8
      - order_number: "ORD-2024-0004", status: pending, priority: urgent, items_count: 1

    StockAlert:
      - product: "Widget A", current_stock: 5, reorder_point: 20, status: critical
      - product: "Widget B", current_stock: 15, reorder_point: 25, status: warning

scenario inventory_audit "Inventory Audit":
  description: "Quarterly inventory count and reconciliation"

  for persona warehouse_manager:
    start_route: "/warehouse/audit"

  demo:
    InventoryCount:
      - location: "A-01-01", expected: 100, counted: 98, status: variance
      - location: "A-01-02", expected: 50, counted: 50, status: matched
      - location: "B-02-01", expected: 75, counted: 80, status: variance
```

## Using Scenarios

Scenarios are used by:

1. **Dazzle Bar** - Developer overlay for switching personas and scenarios
2. **Test Framework** - Automated testing with predefined states
3. **Demo Mode** - Client demonstrations with realistic data
4. **Development** - Local development with consistent test data

Select scenarios via:
- Dazzle Bar UI (development mode)
- `dazzle scenario load <scenario_id>` CLI command
- Test fixtures in automated tests
