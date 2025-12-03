"""
Semantic index for DAZZLE DSL v0.2 concepts.

Provides structured definitions, syntax examples, and relationships
for all DAZZLE DSL concepts to enable immediate context access for LLMs.
"""

from typing import Any


def get_semantic_index() -> dict[str, Any]:
    """
    Get the complete semantic index for DAZZLE DSL v0.5.

    Returns a structured dictionary mapping concepts to their definitions,
    syntax, examples, and related concepts.
    """
    return {
        "version": "0.5.0",
        "concepts": {
            # ================================================================
            # Core Constructs
            # ================================================================
            "entity": {
                "category": "Core Construct",
                "definition": "A domain model representing a business concept (User, Task, Device, etc.). Similar to a database table but defined at the semantic level.",
                "syntax": """entity <EntityName> "<Display Name>":
  <field_name>: <type> [modifiers]
  ...

  [index <field1>, <field2>]
  [unique <field1>, <field2>]""",
                "example": """entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add""",
                "related": ["surface", "field_types", "relationships"],
                "v0_2_changes": "No changes from v0.1",
            },
            "surface": {
                "category": "Core Construct",
                "definition": "A UI or API interface definition for interacting with entities. Defines WHAT data to show and HOW users interact with it.",
                "syntax": """surface <surface_name> "<Display Name>":
  uses entity <EntityName>
  mode: <list|view|create|edit>

  section <section_name> ["Section Title"]:
    field <field_name> ["Field Label"]
    ...

  [ux:]
    [purpose: "<semantic intent>"]
    [... UX directives ...]""",
                "example": """surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status

  ux:
    purpose: "Track team task progress"
    sort: status asc
    filter: status, assigned_to""",
                "related": ["entity", "ux_block", "surface_modes"],
                "v0_2_changes": "Added optional ux: block for semantic layer",
            },
            "workspace": {
                "category": "Core Construct (v0.2)",
                "definition": "A composition of multiple data views into a cohesive dashboard or information hub. Workspaces aggregate related surfaces and data for specific user needs.",
                "syntax": """workspace <workspace_name> "<Display Name>":
  purpose: "<semantic intent>"

  <region_name>:
    source: <Entity|surface_name>
    [filter: <condition>]
    [sort: <field> [asc|desc], ...]
    [limit: <number>]
    [display: <list|grid|timeline|map>]
    [action: <surface_name>]
    [empty: "<message>"]
    [aggregate:]
      <metric_name>: <expression>

  [ux:]
    [for <persona>: ...]""",
                "example": """workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"

  urgent_tasks:
    source: Task
    filter: priority = high
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  team_metrics:
    aggregate:
      total: count(Task)
      done: count(Task where status = done)""",
                "related": ["persona", "regions", "aggregates", "display_modes"],
                "v0_2_changes": "NEW in v0.2",
            },
            # ================================================================
            # UX Semantic Layer (v0.2)
            # ================================================================
            "ux_block": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Optional metadata on surfaces and workspaces expressing WHY they exist and WHAT matters to users, without prescribing HOW to implement it.",
                "syntax": """ux:
  purpose: "<semantic intent>"

  [show: <field1>, <field2>, ...]
  [sort: <field> [asc|desc], ...]
  [filter: <field1>, <field2>, ...]
  [search: <field1>, <field2>, ...]
  [empty: "<message>"]

  [attention <level>:]
    when: <condition>
    message: "<user message>"
    [action: <surface_name>]

  [for <persona>:]
    [scope: <filter_expression>]
    [purpose: "<persona purpose>"]
    [show: <fields>]
    [hide: <fields>]
    [show_aggregate: <metrics>]
    [action_primary: <surface>]
    [read_only: true|false]""",
                "example": """ux:
  purpose: "Manage user accounts"

  sort: name asc
  filter: role, is_active
  search: name, email

  attention warning:
    when: days_since(last_login) > 90
    message: "Inactive account"

  for admin:
    scope: all
    action_primary: user_create

  for member:
    scope: id = current_user.id
    read_only: true""",
                "related": ["purpose", "information_needs", "attention_signals", "persona"],
                "v0_2_changes": "NEW in v0.2",
            },
            "purpose": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "A single-line statement capturing the semantic intent of a surface or workspace - explaining WHY it exists.",
                "syntax": 'purpose: "<single line explanation>"',
                "example": 'purpose: "Track customer support ticket resolution"',
                "related": ["ux_block"],
                "v0_2_changes": "NEW in v0.2",
                "best_practices": [
                    "✅ Focus on user intent, not implementation",
                    "✅ Answer 'why does this exist?'",
                    "✅ Keep to one line",
                    "❌ Avoid 'List of...' or 'CRUD for...'",
                ],
            },
            "information_needs": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Specifications for how data should be displayed, sorted, filtered, and searched - the 'what' without the 'how'.",
                "directives": {
                    "show": "Fields to display",
                    "sort": "Default sort order",
                    "filter": "Fields available for filtering",
                    "search": "Fields to include in text search",
                    "empty": "Message when no data available",
                },
                "syntax": """show: field1, field2, field3
sort: field1 desc, field2 asc
filter: status, category, assigned_to
search: title, description, tags
empty: "No items found. Create your first item.\"""",
                "related": ["ux_block"],
                "v0_2_changes": "NEW in v0.2",
            },
            "attention_signals": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Data-driven conditions that require user awareness or action. Signals have severity levels and can trigger actions.",
                "levels": ["critical", "warning", "notice", "info"],
                "syntax": """attention <critical|warning|notice|info>:
  when: <condition_expression>
  message: "<user-facing message>"
  [action: <surface_name>]""",
                "example": """attention critical:
  when: due_date < today and status != done
  message: "Overdue task"
  action: task_edit

attention warning:
  when: priority = high and status = todo
  message: "High priority - needs assignment"
  action: task_assign""",
                "related": ["ux_block", "conditions"],
                "v0_2_changes": "NEW in v0.2",
                "best_practices": [
                    "✅ Use for data anomalies requiring action",
                    "✅ Use for time-sensitive conditions",
                    "❌ Don't use for purely visual styling",
                    "❌ Don't overuse - reserve for truly important conditions",
                ],
            },
            "persona": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "A role-based variant that adapts surfaces or workspaces for different user types without code duplication. Controls scope, visibility, and capabilities.",
                "syntax": """for <persona_name>:
  scope: <filter_expression>
  purpose: "<persona-specific purpose>"
  [show: <field1>, <field2>, ...]
  [hide: <field1>, <field2>, ...]
  [show_aggregate: <metric1>, <metric2>, ...]
  [action_primary: <surface_name>]
  [read_only: true|false]""",
                "example": """for admin:
  scope: all
  purpose: "Full user management"
  show_aggregate: total_users, active_count
  action_primary: user_create

for manager:
  scope: department = current_user.department
  purpose: "Manage department users"
  hide: salary, ssn
  action_primary: user_invite

for member:
  scope: id = current_user.id
  purpose: "View own profile"
  read_only: true""",
                "related": ["ux_block", "scope", "workspace"],
                "v0_2_changes": "NEW in v0.2",
                "best_practices": [
                    "✅ Use lowercase role names (admin, manager, member)",
                    "✅ Base on roles or responsibilities",
                    "❌ Avoid device-specific personas (mobile, desktop)",
                    "❌ Avoid preference-based personas (dark-mode-user)",
                ],
            },
            "scope": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Filter expression defining what data a persona can see.",
                "syntax": """scope: all
scope: owner = current_user
scope: team = current_user.team
scope: status = Active and owner = current_user""",
                "related": ["persona", "conditions"],
                "v0_2_changes": "NEW in v0.2",
            },
            # ================================================================
            # Workspace Components (v0.2)
            # ================================================================
            "regions": {
                "category": "Workspace Component (v0.2)",
                "definition": "Named sections within a workspace that pull data from entities or surfaces.",
                "directives": {
                    "source": "Entity or surface to pull data from (required)",
                    "filter": "Filter expression",
                    "sort": "Sort expression",
                    "limit": "Maximum records (1-1000)",
                    "display": "Visualization mode",
                    "action": "Primary action surface",
                    "empty": "Empty state message",
                    "aggregate": "Computed metrics",
                },
                "related": ["workspace", "display_modes", "aggregates"],
                "v0_2_changes": "NEW in v0.2",
            },
            "display_modes": {
                "category": "Workspace Component (v0.2)",
                "definition": "Visualization modes for workspace regions.",
                "modes": {
                    "list": "Traditional table/list (default)",
                    "grid": "Card grid layout",
                    "timeline": "Chronological timeline",
                    "map": "Geographic visualization (requires lat/lng fields)",
                },
                "syntax": "display: <list|grid|timeline|map>",
                "related": ["regions", "workspace"],
                "v0_2_changes": "NEW in v0.2",
            },
            "aggregates": {
                "category": "Workspace Component (v0.2)",
                "definition": "Computed metrics and aggregate functions for workspace regions.",
                "functions": {
                    "count": "count(Entity) or count(Entity where condition)",
                    "sum": "sum(Entity.field)",
                    "avg": "avg(Entity.field)",
                    "min": "min(Entity.field)",
                    "max": "max(Entity.field)",
                    "round": "round(expression, decimals)",
                },
                "syntax": """aggregate:
  total: count(Task)
  completed: count(Task where status = done)
  completion_rate: count(Task where status = done) * 100 / count(Task)
  avg_duration: avg(Task.duration_days)""",
                "related": ["regions", "workspace"],
                "v0_2_changes": "NEW in v0.2",
            },
            # ================================================================
            # Expression System
            # ================================================================
            "conditions": {
                "category": "Expression System",
                "definition": "Boolean expressions used in filters, attention signals, and persona scopes.",
                "operators": {
                    "comparison": "=, !=, <, >, <=, >=",
                    "logical": "and, or, not",
                    "membership": "in [value1, value2, ...]",
                },
                "functions": {
                    "days_since": "days_since(datetime_field)",
                    "count": "count(related_field)",
                    "sum": "sum(numeric_field)",
                    "avg": "avg(numeric_field)",
                },
                "examples": [
                    "status = 'Failed'",
                    "count > 100",
                    "date < today",
                    "status in [Critical, Severe]",
                    "days_since(last_update) > 30",
                    "count(items) = 0 and status != Archived",
                ],
                "related": ["attention_signals", "scope", "regions"],
                "v0_2_changes": "Enhanced with new functions in v0.2",
            },
            # ================================================================
            # Field Types
            # ================================================================
            "field_types": {
                "category": "Type System",
                "definition": "Data types available for entity fields.",
                "basic_types": {
                    "str(N)": "String with max length N",
                    "text": "Long text (no length limit)",
                    "int": "Integer number",
                    "decimal(P,S)": "Decimal number (precision, scale)",
                    "bool": "Boolean (true/false)",
                    "date": "Date only",
                    "time": "Time only",
                    "datetime": "Date and time",
                    "uuid": "UUID identifier",
                },
                "special_types": {
                    "email": "Email address (with validation)",
                    "url": "URL (with validation)",
                    "enum[V1,V2,V3]": "Enumeration of values",
                },
                "modifiers": {
                    "required": "Field must have a value",
                    "optional": "Field can be null (default)",
                    "unique": "Value must be unique across records",
                    "pk": "Primary key",
                    "auto_add": "Auto-set on creation (datetime)",
                    "auto_update": "Auto-update on save (datetime)",
                },
                "related": ["entity"],
                "v0_2_changes": "No changes from v0.1",
            },
            "surface_modes": {
                "category": "Surface System",
                "definition": "Interaction modes for surfaces.",
                "modes": {
                    "list": "Display multiple records (table, grid, cards)",
                    "view": "Display single record details (read-only)",
                    "create": "Form for creating new records",
                    "edit": "Form for modifying existing records",
                },
                "related": ["surface"],
                "v0_2_changes": "No changes from v0.1",
            },
            "relationships": {
                "category": "Type System",
                "definition": "References between entities.",
                "syntax": "field_name: ref <EntityName> [required|optional]",
                "example": "assigned_to: ref User optional",
                "related": ["entity", "field_types"],
                "v0_2_changes": "No changes from v0.1",
            },
            # ================================================================
            # Authentication (DNR Runtime)
            # ================================================================
            "authentication": {
                "category": "DNR Runtime",
                "definition": "Session-based authentication system in DNR. Uses cookie-based sessions with SQLite storage. Auth is optional and can be enabled/disabled per project.",
                "endpoints": {
                    "/auth/login": "POST - Authenticate with username/password",
                    "/auth/logout": "POST - End session",
                    "/auth/me": "GET - Get current user info",
                    "/auth/register": "POST - Create new user (if enabled)",
                },
                "test_mode": {
                    "description": "When running with --test-mode, additional endpoints are available:",
                    "endpoints": {
                        "/__test__/auth/login": "Test login without password",
                        "/__test__/auth/set-user": "Set current user for testing",
                    },
                },
                "persona_binding": "Personas in DSL map to user roles. Use current_user in scope expressions to filter data by logged-in user.",
                "example": """# In DSL, use personas to define role-based access:
ux:
  for admin:
    scope: all
  for member:
    scope: owner = current_user

# API login:
POST /auth/login
Content-Type: application/json
{"username": "admin", "password": "secret"}

# Response sets session cookie automatically""",
                "related": ["persona", "scope"],
                "commands": {
                    "enable": "dazzle dnr serve (auth enabled by default if User entity exists)",
                    "test_mode": "dazzle dnr serve --test-mode",
                },
            },
            # ================================================================
            # E2E Testing
            # ================================================================
            "e2e_testing": {
                "category": "Testing",
                "definition": "End-to-end testing system using Playwright. Tests are auto-generated from DSL and execute against the running DNR app.",
                "workflow": [
                    "1. Start app: dazzle dnr serve --test-mode",
                    "2. Generate tests: dazzle test generate -o testspec.json",
                    "3. Run tests: dazzle test run",
                ],
                "commands": {
                    "dazzle test generate": "Generate FlowSpec from DSL",
                    "dazzle test run": "Execute tests with Playwright",
                    "dazzle test list": "List available test flows",
                },
                "options": {
                    "--test-mode": "Enable test endpoints (/__test__/*) for fixtures and auth",
                    "--headed": "Show browser window during tests",
                    "--priority": "Filter tests by priority (high, medium, low)",
                    "--tag": "Filter tests by tag (crud, auth, validation)",
                },
                "related": ["flowspec", "semantic_dom", "authentication"],
            },
            "flowspec": {
                "category": "Testing",
                "definition": "JSON/YAML specification defining E2E test flows. Auto-generated from DSL but can be customized.",
                "structure": {
                    "metadata": "Test suite info (name, version, generated_at)",
                    "config": "Test configuration (base_url, timeouts)",
                    "flows": "Array of test flow definitions",
                    "fixtures": "Test data fixtures",
                },
                "flow_structure": {
                    "id": "Unique flow identifier",
                    "name": "Human-readable flow name",
                    "description": "What the flow tests",
                    "priority": "high | medium | low",
                    "tags": "Array of tags (crud, auth, validation)",
                    "steps": "Array of test steps",
                },
                "step_types": {
                    "navigate": "Go to a URL",
                    "click": "Click an element",
                    "fill": "Fill a form field",
                    "assert": "Verify condition",
                    "wait": "Wait for element or condition",
                },
                "example": """{
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
}""",
                "related": ["e2e_testing", "semantic_dom"],
            },
            "semantic_dom": {
                "category": "Testing",
                "definition": "Convention for data attributes in DNR UI that enable reliable E2E testing. These attributes provide semantic meaning to DOM elements.",
                "attributes": {
                    "data-dazzle-surface": "Surface identifier (e.g., 'task_list')",
                    "data-dazzle-entity": "Entity type (e.g., 'Task')",
                    "data-dazzle-field": "Field name (e.g., 'title', 'status')",
                    "data-dazzle-action": "Action type (e.g., 'submit', 'cancel', 'delete')",
                    "data-dazzle-row": "Row identifier in lists",
                    "data-dazzle-mode": "Surface mode (list, view, create, edit)",
                },
                "selectors": {
                    "surface": "[data-dazzle-surface='task_list']",
                    "field": "[data-dazzle-field='title']",
                    "action": "[data-dazzle-action='submit']",
                    "row": "[data-dazzle-row]",
                },
                "benefits": [
                    "Stable selectors that survive CSS/layout changes",
                    "Semantic meaning for test assertions",
                    "Auto-generated from DSL - no manual annotation",
                    "Enables visual regression testing",
                ],
                "related": ["e2e_testing", "flowspec"],
            },
            # ================================================================
            # Extensibility (v0.5)
            # ================================================================
            "domain_service": {
                "category": "Extensibility (v0.5)",
                "definition": "Custom business logic declaration in DSL with implementation in Python/TypeScript stubs. Part of the Anti-Turing extensibility model.",
                "syntax": """service <name> "<Title>":
  kind: <domain_logic|validation|integration|workflow>
  input:
    <field_name>: <type> [required]
    ...
  output:
    <field_name>: <type>
    ...
  guarantees:
    - "<contract guarantee>"
  stub: <python|typescript>""",
                "example": """service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
  stub: python""",
                "kinds": {
                    "domain_logic": "Business calculations (VAT, pricing, discounts)",
                    "validation": "Complex validation rules across fields/entities",
                    "integration": "External API calls (payment, email, SMS)",
                    "workflow": "Multi-step processes (order fulfillment, approvals)",
                },
                "related": ["stub", "three_layer_architecture"],
                "v0_5_changes": "NEW in v0.5",
                "commands": {
                    "generate_stubs": "dazzle stubs generate",
                    "list_services": "dazzle stubs list",
                },
            },
            "stub": {
                "category": "Extensibility (v0.5)",
                "definition": "Turing-complete implementation of a domain service. Stubs are auto-generated from DSL with typed function signatures.",
                "languages": ["python", "typescript"],
                "location": "stubs/ directory in project root",
                "example": """# stubs/calculate_vat.py (auto-generated header)
# === AUTO-GENERATED HEADER - DO NOT MODIFY ===
# Service ID: calculate_vat
# Kind: domain_logic
# Input: invoice_id (uuid required), country_code (str(2) optional)
# Output: vat_amount (decimal), breakdown (json)
# ============================================

from typing import TypedDict

class CalculateVatResult(TypedDict):
    vat_amount: float
    breakdown: dict

def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    # Your implementation here
    invoice = get_invoice(invoice_id)
    vat_rate = get_vat_rate(country_code or invoice.country)
    return {
        "vat_amount": invoice.total * vat_rate,
        "breakdown": {"rate": vat_rate, "country": country_code}
    }""",
                "related": ["domain_service", "three_layer_architecture"],
                "v0_5_changes": "NEW in v0.5",
            },
            "three_layer_architecture": {
                "category": "Extensibility (v0.5)",
                "definition": "DAZZLE's separation of concerns: DSL (declarative) → Kernel (runtime) → Stubs (custom code). The DSL is Anti-Turing (no arbitrary computation) while stubs allow full programming.",
                "layers": {
                    "dsl_layer": "Declarative definitions - entities, surfaces, services. Anti-Turing: cannot express arbitrary computation.",
                    "kernel_layer": "DNR runtime - CRUD, auth, routing, state management. Platform-managed behavior.",
                    "stub_layer": "Custom business logic - Turing-complete Python/TypeScript implementations.",
                },
                "rationale": [
                    "Predictability: DSL behavior is fully analyzable",
                    "Safety: No runtime errors from DSL-level code",
                    "Tooling: Complete static analysis and validation",
                    "Flexibility: Full programming power in stubs when needed",
                ],
                "related": ["domain_service", "stub"],
                "v0_5_changes": "NEW in v0.5",
            },
            "access_rules": {
                "category": "Extensibility (v0.5)",
                "definition": "Inline access control rules on entities defining read/write permissions.",
                "syntax": """entity Task "Task":
  id: uuid pk
  title: str(200) required

  access:
    read: owner = current_user or shared = true
    write: owner = current_user""",
                "rules": {
                    "read": "Controls who can view records (maps to visibility rule)",
                    "write": "Controls who can create/update/delete records (maps to permission rules)",
                },
                "expressions": [
                    "owner = current_user",
                    "shared = true",
                    "role = admin",
                    "department = current_user.department",
                ],
                "related": ["entity", "persona"],
                "v0_5_changes": "NEW in v0.5",
            },
            "action_purity": {
                "category": "Extensibility (v0.5)",
                "definition": "Classification of actions as pure (no side effects) or impure (has side effects like fetch, navigate, etc.).",
                "syntax": """actions:
  toggleFilter: pure    # Only affects local state
  saveTask: impure      # Has side effect (API call)""",
                "inference": "Purity is auto-inferred from action effects. Explicit annotation overrides inference.",
                "related": ["component_role"],
                "v0_5_changes": "NEW in v0.5",
            },
            "component_role": {
                "category": "Extensibility (v0.5)",
                "definition": "Classification of components as presentational (no state/impure actions) or container (has state or impure actions).",
                "roles": {
                    "presentational": "Pure rendering - no state, no side effects",
                    "container": "Stateful - manages state or performs side effects",
                },
                "inference": "Role is auto-inferred from component definition. Explicit annotation overrides inference.",
                "related": ["action_purity"],
                "v0_5_changes": "NEW in v0.5",
            },
        },
        # ================================================================
        # Common Patterns with Copy-Paste Examples
        # ================================================================
        "patterns": {
            "crud": {
                "name": "CRUD Pattern",
                "description": "Complete create-read-update-delete interface for an entity",
                "surfaces": [
                    "{entity}_list (list mode)",
                    "{entity}_detail (view mode)",
                    "{entity}_create (create mode)",
                    "{entity}_edit (edit mode)",
                ],
                "example": """# Complete CRUD for Task entity
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title
    field status
  ux:
    purpose: "View and manage all tasks"
    sort: created_at desc
    filter: status

surface task_detail "Task Details":
  uses entity Task
  mode: view
  section main:
    field title
    field description
    field status
    field created_at

surface task_create "New Task":
  uses entity Task
  mode: create
  section main:
    field title
    field description

surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  section main:
    field title
    field description
    field status""",
            },
            "dashboard": {
                "name": "Dashboard Pattern",
                "description": "Workspace aggregating multiple data views with metrics",
                "components": [
                    "Metrics/KPIs",
                    "Recent activity",
                    "Alerts/attention items",
                    "Quick actions",
                ],
                "v0_2_feature": True,
                "example": """# Team dashboard with metrics and activity
workspace team_dashboard "Team Dashboard":
  purpose: "Real-time team overview and key metrics"

  # Urgent items needing attention
  urgent_items:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "All caught up!"

  # Recent completions
  recent_done:
    source: Task
    filter: status = done
    sort: completed_at desc
    limit: 10
    display: timeline

  # Key performance metrics
  metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      in_progress: count(Task where status = in_progress)
      completion_rate: round(count(Task where status = done) * 100 / count(Task), 1)""",
            },
            "role_based_access": {
                "name": "Role-Based Access Pattern",
                "description": "Persona variants controlling scope and capabilities",
                "personas": [
                    "Admin: full access, all records",
                    "Manager: department/team scope",
                    "Member: own records only",
                ],
                "v0_2_feature": True,
                "example": """# Role-based access with personas
surface ticket_list "Support Tickets":
  uses entity Ticket
  mode: list

  section main:
    field subject
    field status
    field assigned_to.name

  ux:
    purpose: "Manage support tickets by role"

    # Admins see everything, can reassign
    for admin:
      scope: all
      action_primary: ticket_assign
      show_aggregate: total, open, resolved_today

    # Agents see assigned + unassigned
    for agent:
      scope: assigned_to = current_user or assigned_to = null
      action_primary: ticket_respond

    # Customers see only their tickets
    for customer:
      scope: created_by = current_user
      hide: internal_notes, assigned_to
      read_only: true""",
            },
            "master_detail": {
                "name": "Master-Detail Pattern",
                "description": "Parent-child relationship with nested views",
                "v0_2_feature": False,
                "example": """# Project with nested tasks
entity Project "Project":
  id: uuid pk
  name: str(200) required
  status: enum[active,completed,archived]=active

entity Task "Task":
  id: uuid pk
  title: str(200) required
  project: ref Project required
  status: enum[todo,done]=todo

surface project_list "Projects":
  uses entity Project
  mode: list
  section main:
    field name
    field status

surface project_detail "Project":
  uses entity Project
  mode: view
  section info:
    field name
    field status
  section tasks "Tasks":
    uses entity Task
    filter: project = this
    field title
    field status""",
            },
            "kanban_board": {
                "name": "Kanban Board Pattern",
                "description": "Status-based workflow visualization",
                "example": """# Kanban-style task board
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[backlog,todo,in_progress,review,done]=backlog
  priority: enum[low,medium,high]=medium
  assigned_to: ref User optional

workspace kanban "Task Board":
  purpose: "Visual workflow management"

  backlog:
    source: Task
    filter: status = backlog
    sort: priority desc
    display: grid
    action: task_edit

  in_progress:
    source: Task
    filter: status = in_progress
    sort: priority desc
    display: grid

  review:
    source: Task
    filter: status = review
    sort: priority desc
    display: grid

  done:
    source: Task
    filter: status = done
    sort: completed_at desc
    limit: 20
    display: grid""",
            },
            "audit_trail": {
                "name": "Audit Trail Pattern",
                "description": "Track who changed what and when",
                "example": """# Entity with full audit fields
entity Document "Document":
  id: uuid pk
  title: str(200) required
  content: text
  # Audit fields
  created_by: ref User required
  created_at: datetime auto_add
  updated_by: ref User optional
  updated_at: datetime auto_update
  version: int=1

surface document_history "Document History":
  uses entity Document
  mode: view
  section main:
    field title
    field version
  section audit "Audit Trail":
    field created_by.name "Created By"
    field created_at "Created At"
    field updated_by.name "Last Updated By"
    field updated_at "Last Updated At" """,
            },
            "search_filter": {
                "name": "Search & Filter Pattern",
                "description": "Full-text search with faceted filtering",
                "v0_2_feature": True,
                "example": """# Searchable product catalog
entity Product "Product":
  id: uuid pk
  name: str(200) required
  description: text
  category: enum[electronics,clothing,home,other]
  price: decimal(10,2)
  in_stock: bool=true

surface product_catalog "Products":
  uses entity Product
  mode: list

  section main:
    field name
    field category
    field price
    field in_stock

  ux:
    purpose: "Browse and find products"
    search: name, description
    filter: category, in_stock
    sort: name asc
    empty: "No products match your search" """,
            },
            "notifications": {
                "name": "Notifications Pattern",
                "description": "Alert users to important events",
                "v0_2_feature": True,
                "example": """# Surface with attention signals
surface order_list "Orders":
  uses entity Order
  mode: list

  section main:
    field order_number
    field customer.name
    field status
    field total

  ux:
    purpose: "Process and fulfill orders"

    # Payment failed - critical
    attention critical:
      when: payment_status = failed
      message: "Payment failed!"
      action: order_retry_payment

    # Shipping delayed
    attention warning:
      when: days_since(shipped_at) > 5 and status = shipped
      message: "Delayed shipment"

    # New order
    attention notice:
      when: status = new and created_at > today
      message: "New order today" """,
            },
            "domain_service_pattern": {
                "name": "Domain Service Pattern",
                "description": "Custom business logic with DSL declaration and stub implementation",
                "v0_5_feature": True,
                "components": [
                    "DSL service declaration with kind, input, output",
                    "Guarantees documenting contracts",
                    "Python/TypeScript stub implementation",
                ],
                "example": """# DSL declaration in app.dsl
entity Invoice "Invoice":
  id: uuid pk
  total: decimal(10,2) required
  country: str(2) required
  vat_amount: decimal(10,2) optional

service calculate_vat "Calculate VAT for Invoice":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
  stub: python

# Generate stub file:
# $ dazzle stubs generate --service calculate_vat

# Implement in stubs/calculate_vat.py:
def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    invoice = db.get_invoice(invoice_id)
    country = country_code or invoice.country

    # VAT rates by country
    rates = {"GB": 0.20, "DE": 0.19, "FR": 0.20, "US": 0.0}
    rate = rates.get(country, 0.0)

    return {
        "vat_amount": float(invoice.total) * rate,
        "breakdown": {
            "rate": rate,
            "country": country,
            "net": float(invoice.total),
            "gross": float(invoice.total) * (1 + rate)
        }
    }""",
                "use_cases": [
                    "Complex calculations (pricing, tax, discounts)",
                    "External API integration (payment, email)",
                    "Multi-step workflows (approval processes)",
                    "Cross-entity validation rules",
                ],
            },
        },
        # ================================================================
        # Best Practices
        # ================================================================
        "best_practices": {
            "naming_conventions": {
                "entities": "Use singular nouns (Task, not Tasks)",
                "surfaces": "Use {entity}_{mode} pattern (task_list, user_edit)",
                "workspaces": "Use {context}_dashboard or {role}_workspace",
                "personas": "Use lowercase role names (admin, manager, member)",
                "fields": "Use snake_case (first_name, not firstName)",
                "enums": "Use lowercase with underscores (in_progress, not InProgress)",
            },
            "purpose_statements": {
                "do": "Explain WHY the surface exists, focus on user intent",
                "dont": "Avoid 'List of...' or 'CRUD for...' or implementation details",
            },
        },
    }


def lookup_concept(term: str) -> dict[str, Any] | None:
    """
    Look up a DAZZLE concept by name.

    Args:
        term: The concept name (e.g., 'persona', 'workspace', 'ux_block')

    Returns:
        Concept definition or None if not found
    """
    index = get_semantic_index()

    # Normalize term
    term_normalized = term.lower().replace(" ", "_").replace("-", "_")

    # Direct lookup in concepts
    if term_normalized in index["concepts"]:
        return {
            "term": term,
            "found": True,
            "type": "concept",
            **index["concepts"][term_normalized],
        }

    # Check patterns
    if term_normalized in index["patterns"]:
        return {
            "term": term,
            "found": True,
            "type": "pattern",
            **index["patterns"][term_normalized],
        }

    # Check if asking for "pattern" or "patterns" - return all patterns
    if term_normalized in ("pattern", "patterns"):
        pattern_list = [
            {"name": name, "description": data.get("description")}
            for name, data in index["patterns"].items()
        ]
        return {
            "term": term,
            "found": True,
            "type": "pattern_list",
            "patterns": pattern_list,
            "hint": "Use lookup_concept with a specific pattern name (e.g., 'crud', 'dashboard') to get full example code",
        }

    # Search in all concepts for partial matches
    matches = []
    for concept_name, concept_data in index["concepts"].items():
        if (
            term_normalized in concept_name
            or term_normalized in concept_data.get("definition", "").lower()
        ):
            matches.append(
                {
                    "name": concept_name,
                    "category": concept_data.get("category"),
                    "definition": concept_data.get("definition"),
                }
            )

    # Also search patterns
    for pattern_name, pattern_data in index["patterns"].items():
        if (
            term_normalized in pattern_name
            or term_normalized in pattern_data.get("description", "").lower()
        ):
            matches.append(
                {
                    "name": pattern_name,
                    "type": "pattern",
                    "description": pattern_data.get("description"),
                }
            )

    if matches:
        return {"term": term, "found": False, "suggestions": matches}

    return {"term": term, "found": False, "error": f"Concept '{term}' not found in semantic index"}


def get_dsl_patterns() -> dict[str, Any]:
    """
    Get all available DSL patterns with examples.

    Returns:
        Dictionary of pattern names to their definitions and examples
    """
    index = get_semantic_index()
    return {
        "patterns": index["patterns"],
        "hint": "Each pattern includes a complete, copy-paste ready example",
    }
