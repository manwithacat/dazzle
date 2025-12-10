"""
Semantic index for DAZZLE DSL v0.2-v0.7.2 concepts.

Provides structured definitions, syntax examples, and relationships
for all DAZZLE DSL concepts to enable immediate context access for LLMs.

Version history:
- v0.2: UX Semantic Layer (personas, workspaces, attention signals)
- v0.5: Extensibility Framework (domain services, stubs, three-layer architecture)
- v0.6: GraphQL BFF Layer (adapters, error normalization, schema generation)
- v0.7: Business Logic (state machines, invariants, computed fields, access rules)
- v0.7.1: LLM Cognition (intent, examples, archetypes, relationship semantics)
- v0.7.2: Ejection Toolchain (standalone code generation, OpenAPI, adapters)
"""

from typing import Any


def get_semantic_index() -> dict[str, Any]:
    """
    Get the complete semantic index for DAZZLE DSL v0.5.

    Returns a structured dictionary mapping concepts to their definitions,
    syntax, examples, and related concepts.
    """
    return {
        "version": "0.7.2",
        "concepts": {
            # ================================================================
            # Core Constructs
            # ================================================================
            "entity": {
                "category": "Core Construct",
                "definition": "A domain model representing a business concept (User, Task, Device, etc.). Similar to a database table but defined at the semantic level. Includes fields with types, constraints, relationships, and business logic. v0.7.1 adds LLM cognition features: intent, domain/patterns tags, archetypes, and relationship semantics.",
                "syntax": """entity <EntityName> "<Display Name>":
  [intent: "<why this entity exists>"]
  [domain: <tag>]
  [patterns: <tag1>, <tag2>, ...]
  [extends: <ArchetypeName1>, <ArchetypeName2>, ...]

  <field_name>: <type> [modifiers]
  ...

  [<computed_field>: computed <expression>]

  [transitions:
    <from_state> -> <to_state>
    <from_state> -> <to_state>: requires <field>
    <from_state> -> <to_state>: role(<role_name>)]

  [invariant: <condition>
    [message: "<error message>"]
    [code: <ERROR_CODE>]]

  [access:
    read: <condition>
    write: <condition>]

  [examples:
    {<field>: <value>, <field>: <value>, ...}
    {<field>: <value>, <field>: <value>, ...}]

  [index <field1>, <field2>]
  [unique <field1>, <field2>]""",
                "example": """entity Ticket "Support Ticket":
  intent: "Track and resolve customer issues through structured workflow"
  domain: support
  patterns: lifecycle, assignment, audit

  id: uuid pk
  title: str(200) required
  status: enum[open,in_progress,resolved,closed]=open
  assigned_to: ref User
  resolution: text
  created_at: datetime auto_add

  # Computed field
  days_open: computed days_since(created_at)

  # State machine
  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> resolved: requires resolution
    resolved -> closed
    closed -> open: role(manager)

  # Invariants with messages
  invariant: status != resolved or resolution != null
    message: "Resolution is required before closing ticket"
    code: TICKET_NEEDS_RESOLUTION

  # Access rules
  access:
    read: role(agent) or role(manager)
    write: role(agent) or role(manager)

  # Example data for LLM understanding
  examples:
    {title: "Login page not loading", status: open, priority: high}
    {title: "Password reset email delayed", status: in_progress, priority: medium}""",
                "related": [
                    "surface",
                    "field_types",
                    "relationships",
                    "state_machine",
                    "invariant",
                    "computed_field",
                    "access_rules",
                    "archetype",
                    "intent",
                    "examples",
                ],
                "v0_7_changes": "Enhanced with state machines, invariants, computed fields, and access rules",
                "v0_7_1_changes": "Added intent, domain/patterns tags, extends archetypes, examples block, invariant message/code",
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
                "definition": "References and ownership relationships between entities. v0.7.1 adds semantic relationship types (has_many, has_one, embeds, belongs_to) with delete behaviors.",
                "syntax": """# Simple reference (foreign key)
field_name: ref <EntityName> [required|optional]

# v0.7.1 Ownership relationships
field_name: has_many <EntityName> [cascade|restrict|nullify|readonly]
field_name: has_one <EntityName> [cascade|restrict|nullify]
field_name: embeds <EntityName>
field_name: belongs_to <EntityName>""",
                "example": """# Parent entity with children
entity Order "Order":
  id: uuid pk
  items: has_many OrderItem cascade  # Delete items when order deleted
  shipping_address: embeds Address   # Embedded value object
  customer: ref Customer required    # Foreign key reference

entity OrderItem "Order Item":
  id: uuid pk
  order: belongs_to Order            # Inverse of has_many
  product: ref Product required

# Readonly relationship (prevents modification through parent)
entity Customer "Customer":
  id: uuid pk
  orders: has_many Order readonly    # View orders but don't modify through Customer""",
                "relationship_types": {
                    "ref": "Simple foreign key reference to another entity",
                    "has_many": "Parent owns multiple children (one-to-many)",
                    "has_one": "Parent owns exactly one child (one-to-one)",
                    "embeds": "Value object embedded in parent (no separate identity)",
                    "belongs_to": "Child side of has_many/has_one relationship",
                },
                "delete_behaviors": {
                    "cascade": "Delete children when parent is deleted (default for has_many)",
                    "restrict": "Prevent parent deletion if children exist",
                    "nullify": "Set child's FK to null when parent deleted",
                    "readonly": "Cannot modify children through this relationship",
                },
                "related": ["entity", "field_types", "archetype"],
                "v0_2_changes": "No changes from v0.1",
                "v0_7_1_changes": "Added has_many, has_one, embeds, belongs_to with cascade/restrict/nullify/readonly behaviors",
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
            # Business Logic (v0.7)
            # ================================================================
            "state_machine": {
                "category": "Business Logic (v0.7)",
                "definition": "Define allowed status/state transitions with optional guards. Prevents invalid state changes and documents workflow rules declaratively.",
                "syntax": """transitions:
  <from_state> -> <to_state>
  <from_state> -> <to_state>: requires <field_name>
  <from_state> -> <to_state>: role(<role_name>)
  * -> <to_state>: role(admin)  # wildcard: from any state""",
                "example": """entity Task "Task":
  status: enum[todo,in_progress,done]=todo
  assigned_to: ref User

  transitions:
    todo -> in_progress: requires assigned_to
    in_progress -> done
    in_progress -> todo
    done -> todo: role(admin)  # Only admin can reopen""",
                "guards": {
                    "requires <field>": "Field must be non-null before transition",
                    "role(<name>)": "User must have the specified role",
                    "no guard": "Transition always allowed",
                },
                "related": ["entity", "invariant", "access_rules"],
                "v0_7_changes": "NEW in v0.7",
                "best_practices": [
                    "Use for status fields with defined workflows",
                    "Document transition rules that match business processes",
                    "Use role guards for administrative overrides",
                    "Use requires guards for data integrity",
                ],
            },
            "invariant": {
                "category": "Business Logic (v0.7)",
                "definition": "Cross-field validation rules that must always hold. Enforced on create and update. Part of the declarative business logic layer.",
                "syntax": """invariant: <condition>

# Operators:
# Comparison: =, !=, >, <, >=, <=
# Logical: and, or, not
# Null check: field != null, field = null

# IMPORTANT: Use single = for equality (not ==)""",
                "example": """entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required
  priority: enum[low,medium,high]=medium
  due_date: date

  # End must be after start
  invariant: end_date > start_date

  # High priority bookings must have a due date
  invariant: priority != high or due_date != null""",
                "related": ["entity", "state_machine", "access_rules"],
                "v0_7_changes": "NEW in v0.7",
                "best_practices": [
                    "Use = for equality (consistent with access rules)",
                    "Express as 'A or B' for 'if A then B' rules",
                    "Keep invariants simple and focused",
                    "Document the business rule in a comment",
                ],
            },
            "computed_field": {
                "category": "Business Logic (v0.7)",
                "definition": "Derived values calculated from other fields. Computed at query time, not stored. Part of the declarative business logic layer.",
                "syntax": """<field_name>: computed <expression>

# Functions:
# days_since(datetime_field) - Days since the field's value
# sum(related.field) - Sum of related records
# count(related) - Count of related records""",
                "example": """entity Ticket "Ticket":
  created_at: datetime auto_add
  due_date: date

  # Days since ticket was opened
  days_open: computed days_since(created_at)

  # Days until due (negative if overdue)
  days_until_due: computed days_since(due_date)""",
                "related": ["entity", "field_types"],
                "v0_7_changes": "NEW in v0.7",
            },
            "access_rules": {
                "category": "Business Logic (v0.7)",
                "definition": "Inline access control rules on entities defining read/write permissions. Maps to visibility and permission rules at runtime.",
                "syntax": """access:
  read: <condition>
  write: <condition>

# Expressions:
# field = current_user - Field matches logged-in user
# role(<name>) - User has the specified role
# field = value - Field equals literal value
# Combine with: and, or""",
                "example": """entity Document "Document":
  owner: ref User required
  is_public: bool = false

  access:
    read: owner = current_user or is_public = true or role(admin)
    write: owner = current_user or role(admin)""",
                "related": ["entity", "persona", "invariant"],
                "v0_7_changes": "Enhanced in v0.7 with refined syntax",
                "best_practices": [
                    "Use = for equality (not ==)",
                    "Start with restrictive rules, expand as needed",
                    "Use role() for administrative access",
                    "Combine with persona scopes for UI filtering",
                ],
            },
            # ================================================================
            # LLM Cognition (v0.7.1)
            # ================================================================
            "intent": {
                "category": "LLM Cognition (v0.7.1)",
                "definition": "A single-line declaration explaining WHY an entity exists in the domain. Helps LLMs understand the semantic purpose of data structures.",
                "syntax": 'intent: "<explanation of entity purpose>"',
                "example": """entity Invoice "Invoice":
  intent: "Represent a finalized billing request with line items and tax calculations"

entity User "User":
  intent: "Authenticate and authorize system access with role-based permissions"

entity AuditLog "Audit Log":
  intent: "Track all data modifications for compliance and debugging" """,
                "related": ["entity", "archetype", "examples"],
                "v0_7_1_changes": "NEW in v0.7.1",
                "best_practices": [
                    "Focus on WHY the entity exists, not WHAT it contains",
                    "Describe the business/domain purpose",
                    "Keep to one sentence",
                    "Avoid technical implementation details",
                ],
            },
            "archetype": {
                "category": "LLM Cognition (v0.7.1)",
                "definition": "Reusable template defining common field patterns. Entities can extend archetypes to inherit fields, computed fields, and invariants. Promotes consistency and reduces repetition.",
                "syntax": """archetype <ArchetypeName>:
  <field_name>: <type> [modifiers]
  ...
  [<computed_field>: computed <expression>]
  [invariant: <condition>]

# Entity extending an archetype
entity <EntityName> "<Display Name>":
  extends: <ArchetypeName1>, <ArchetypeName2>, ...
  <additional_fields>""",
                "example": """# Define reusable archetypes
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User
  version: int = 1

archetype SoftDelete:
  is_deleted: bool = false
  deleted_at: datetime
  deleted_by: ref User

# Entity using archetypes
entity Document "Document":
  extends: Timestamped, Auditable, SoftDelete
  intent: "Store versioned documents with full audit trail"

  id: uuid pk
  title: str(200) required
  content: text
  status: enum[draft,published,archived] = draft""",
                "related": ["entity", "intent", "relationships"],
                "v0_7_1_changes": "NEW in v0.7.1",
                "best_practices": [
                    "Use for cross-cutting concerns (audit, timestamps, soft delete)",
                    "Keep archetypes focused on one pattern",
                    "Name archetypes as adjectives or nouns (Timestamped, Auditable)",
                    "Entity fields override archetype fields with same name",
                ],
            },
            "domain_patterns": {
                "category": "LLM Cognition (v0.7.1)",
                "definition": "Semantic tags that classify entities by domain area and common patterns. Helps LLMs understand entity relationships and generate consistent code.",
                "syntax": """# Single domain tag
domain: <tag>

# Multiple pattern tags
patterns: <tag1>, <tag2>, <tag3>""",
                "example": """entity Invoice "Invoice":
  domain: billing
  patterns: lifecycle, audit, line_items

entity User "User":
  domain: identity
  patterns: authentication, authorization, profile

entity Order "Order":
  domain: commerce
  patterns: lifecycle, workflow, aggregate_root""",
                "common_domains": [
                    "identity - Users, roles, permissions",
                    "billing - Invoices, payments, subscriptions",
                    "commerce - Orders, products, inventory",
                    "support - Tickets, cases, communications",
                    "content - Documents, media, articles",
                    "analytics - Events, metrics, reports",
                ],
                "common_patterns": [
                    "lifecycle - Has status with transitions",
                    "audit - Tracks created_by, updated_by, timestamps",
                    "workflow - Multi-step process with states",
                    "aggregate_root - DDD aggregate with owned children",
                    "lookup - Reference data (categories, types)",
                    "line_items - Parent with detail lines",
                ],
                "related": ["entity", "intent", "archetype"],
                "v0_7_1_changes": "NEW in v0.7.1",
            },
            "examples": {
                "category": "LLM Cognition (v0.7.1)",
                "definition": "Inline example records that demonstrate valid data for an entity. Helps LLMs understand data formats, relationships, and realistic values.",
                "syntax": """examples:
  {<field>: <value>, <field>: <value>, ...}
  {<field>: <value>, <field>: <value>, ...}""",
                "example": """entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done] = todo
  priority: enum[low,medium,high] = medium
  due_date: date

  examples:
    {title: "Write documentation", status: todo, priority: high, due_date: "2024-03-15"}
    {title: "Fix login bug", status: in_progress, priority: high}
    {title: "Update dependencies", status: done, priority: low}

entity User "User":
  id: uuid pk
  email: email required unique
  name: str(100) required
  role: enum[admin,manager,member] = member

  examples:
    {email: "admin@example.com", name: "Alice Admin", role: admin}
    {email: "bob@example.com", name: "Bob Manager", role: manager}
    {email: "carol@example.com", name: "Carol Member", role: member}""",
                "related": ["entity", "intent", "field_types"],
                "v0_7_1_changes": "NEW in v0.7.1",
                "best_practices": [
                    "Include 2-3 representative examples",
                    "Show different states/variations",
                    "Use realistic but non-sensitive values",
                    "Demonstrate enum values and relationships",
                ],
            },
            "invariant_message": {
                "category": "LLM Cognition (v0.7.1)",
                "definition": "Human-readable error message and machine-readable error code for invariant violations. Improves API responses and internationalization.",
                "syntax": """invariant: <condition>
  message: "<human-readable error message>"
  code: <ERROR_CODE>""",
                "example": """entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required
  status: enum[pending,confirmed,cancelled] = pending
  confirmed_at: datetime

  # Invariant with message and code
  invariant: end_date > start_date
    message: "End date must be after start date"
    code: BOOKING_INVALID_DATE_RANGE

  invariant: status != confirmed or confirmed_at != null
    message: "Confirmed bookings must have a confirmation timestamp"
    code: BOOKING_MISSING_CONFIRMATION

  # Invariant without message (generates default)
  invariant: status != cancelled or end_date > today""",
                "related": ["entity", "invariant", "access_rules"],
                "v0_7_1_changes": "NEW in v0.7.1",
                "best_practices": [
                    "Use SCREAMING_SNAKE_CASE for error codes",
                    "Make messages user-friendly and actionable",
                    "Include entity prefix in error codes (BOOKING_, USER_)",
                    "Message and code are optional - defaults are generated",
                ],
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
            # ================================================================
            # Ejection Toolchain (v0.7.2)
            # ================================================================
            "ejection": {
                "category": "Ejection Toolchain (v0.7.2)",
                "definition": "Path from DNR runtime to standalone generated code when projects outgrow the native runtime or have deployment constraints. Generates FastAPI backend, React frontend, testing, and CI configuration.",
                "syntax": """# Run ejection
dazzle eject run                    # Full ejection
dazzle eject run --no-frontend      # Backend only
dazzle eject run --dry-run          # Preview changes
dazzle eject run -o ./generated     # Custom output directory

# Check configuration
dazzle eject status

# List adapters
dazzle eject adapters

# Generate OpenAPI spec
dazzle eject openapi -o openapi.yaml""",
                "example": """# dazzle.toml configuration
[ejection]
enabled = true
reuse_dnr = false

[ejection.backend]
framework = "fastapi"
models = "sqlalchemy"
async_handlers = true
routing = "tags"

[ejection.frontend]
framework = "react"
api_client = "tanstack_query"
state = "tanstack_query"

[ejection.testing]
contract = "schemathesis"
unit = "pytest"
e2e = "playwright"

[ejection.ci]
template = "github_actions"

[ejection.output]
directory = "generated"
clean = true""",
                "related": ["ejection_config", "ejection_adapter", "openapi_generation"],
                "v0_7_2_changes": "NEW in v0.7.2",
                "use_cases": [
                    "Custom deployment requirements (Kubernetes, serverless)",
                    "Performance optimization (precompiled code)",
                    "Independence from DAZZLE runtime",
                    "Advanced customization beyond DNR capabilities",
                    "Compliance requirements (code review, audit)",
                ],
            },
            "ejection_config": {
                "category": "Ejection Toolchain (v0.7.2)",
                "definition": "Configuration in dazzle.toml's [ejection] section controlling what code is generated and how.",
                "syntax": """[ejection]
enabled = true                    # Enable ejection commands
reuse_dnr = false                 # Import DNR components vs generate standalone

[ejection.backend]
framework = "fastapi"             # Backend framework (fastapi)
models = "sqlalchemy"             # ORM (sqlalchemy, pydantic)
async_handlers = true             # Use async handlers
routing = "tags"                  # Router organization (tags, modules)

[ejection.frontend]
framework = "react"               # Frontend framework (react)
api_client = "tanstack_query"     # API client (tanstack_query, axios, fetch)
state = "tanstack_query"          # State management (tanstack_query, zustand, redux)

[ejection.testing]
contract = "schemathesis"         # Contract testing (schemathesis, none)
unit = "pytest"                   # Unit testing (pytest)
e2e = "playwright"                # E2E testing (playwright, none)

[ejection.ci]
template = "github_actions"       # CI template (github_actions, gitlab_ci, none)

[ejection.output]
directory = "generated"           # Output directory (relative to project)
clean = true                      # Clean output before generating""",
                "related": ["ejection", "ejection_adapter"],
                "v0_7_2_changes": "NEW in v0.7.2",
            },
            "ejection_adapter": {
                "category": "Ejection Toolchain (v0.7.2)",
                "definition": "Pluggable generators that produce code for different targets. Adapters extend the Generator base class and register with AdapterRegistry.",
                "adapter_types": {
                    "backend": "Generate server-side code (FastAPI, Django, Express)",
                    "frontend": "Generate client-side code (React, Vue, Svelte)",
                    "testing": "Generate test suites (Schemathesis, Pytest, Playwright)",
                    "ci": "Generate CI/CD configuration (GitHub Actions, GitLab CI)",
                },
                "syntax": """from dazzle.eject.adapters import AdapterRegistry

# Get an adapter
backend_adapter = AdapterRegistry.get_backend("fastapi")
frontend_adapter = AdapterRegistry.get_frontend("react")

# List available adapters
backends = AdapterRegistry.list_backends()    # ["fastapi"]
frontends = AdapterRegistry.list_frontends()  # ["react"]
testing = AdapterRegistry.list_testing()      # ["schemathesis", "pytest"]
ci = AdapterRegistry.list_ci()                # ["github_actions", "gitlab_ci"]""",
                "example": """# Custom adapter implementation
from dazzle.eject.adapters import Generator, GeneratorResult
from dazzle.core.ir import AppSpec

class MyFrameworkAdapter(Generator):
    def __init__(self, spec: AppSpec, output_dir: Path, config):
        super().__init__(spec, output_dir)
        self.config = config

    def generate(self) -> GeneratorResult:
        result = GeneratorResult()
        # Generate code files...
        return result

# Register the adapter
AdapterRegistry.register_backend("my_framework", MyFrameworkAdapter)""",
                "related": ["ejection", "ejection_config", "openapi_generation"],
                "v0_7_2_changes": "NEW in v0.7.2",
            },
            "openapi_generation": {
                "category": "Ejection Toolchain (v0.7.2)",
                "definition": "Generate OpenAPI 3.1 specification from DAZZLE AppSpec. Includes CRUD endpoints, state transition actions, and schema definitions.",
                "syntax": """# Generate OpenAPI spec
dazzle eject openapi                    # Print to stdout
dazzle eject openapi -o openapi.yaml    # Save to file
dazzle eject openapi -f json            # Output as JSON""",
                "example": """# Generated OpenAPI includes:
# - Entity schemas (Base, Create, Update, Read, List)
# - CRUD endpoints (GET, POST, PUT, DELETE)
# - State transition action endpoints
# - Enum schemas for enum fields

# Example output structure:
openapi: "3.1.0"
info:
  title: My App
  version: "1.0.0"
paths:
  /api/tasks:
    get:
      summary: List all Tasks
      operationId: list_tasks
    post:
      summary: Create a new Task
      operationId: create_task
  /api/tasks/{task_id}:
    get: ...
    put: ...
    delete: ...
  /api/tasks/{task_id}/actions/open_to_in_progress:
    post:
      summary: Transition Task from open to in_progress
components:
  schemas:
    Task: ...
    TaskCreate: ...
    TaskUpdate: ...
    TaskRead: ...
    TaskList: ...
    TaskStatus: ...  # Enum schema""",
                "features": [
                    "OpenAPI 3.1 with nullable type arrays",
                    "CRUD endpoints with proper HTTP methods",
                    "State transition endpoints from state machines",
                    "Enum schemas for enum fields",
                    "Bearer token security scheme",
                    "Pagination parameters (skip, limit)",
                ],
                "related": ["ejection", "ejection_adapter"],
                "v0_7_2_changes": "NEW in v0.7.2",
            },
            "ejection_runner": {
                "category": "Ejection Toolchain (v0.7.2)",
                "definition": "Orchestrates all ejection adapters and generates shared infrastructure files. Entry point for the ejection process.",
                "syntax": """from dazzle.eject import EjectionRunner, load_ejection_config

# Load configuration
config = load_ejection_config(project_path / "dazzle.toml")

# Create runner
runner = EjectionRunner(spec, project_path, config)

# Run ejection
result = runner.run(
    backend=True,
    frontend=True,
    testing=True,
    ci=True,
    clean=True,
)

# Check result
if result.success:
    print(f"Generated {len(result.files)} files")
else:
    for error in result.errors:
        print(f"Error: {error}")""",
                "generated_files": {
                    "shared": [
                        "README.md",
                        "docker-compose.yml",
                        "docker-compose.dev.yml",
                        "Makefile",
                        ".gitignore",
                    ],
                    "backend": [
                        "backend/main.py",
                        "backend/models/*.py",
                        "backend/schemas/*.py",
                        "backend/routes/*.py",
                        "backend/guards/*.py",
                        "backend/validators/*.py",
                        "backend/access/*.py",
                    ],
                    "frontend": [
                        "frontend/src/types/*.ts",
                        "frontend/src/schemas/*.ts",
                        "frontend/src/hooks/*.ts",
                        "frontend/src/components/*.tsx",
                    ],
                    "testing": [
                        "tests/conftest.py",
                        "tests/contract/*.py",
                        "tests/unit/*.py",
                    ],
                    "ci": [
                        ".github/workflows/*.yml",
                        ".github/dependabot.yml",
                    ],
                },
                "related": ["ejection", "ejection_config", "ejection_adapter"],
                "v0_7_2_changes": "NEW in v0.7.2",
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
            # ================================================================
            # v0.6 GraphQL BFF Layer
            # ================================================================
            "graphql_bff_pattern": {
                "name": "GraphQL BFF Pattern",
                "description": "Backend-for-Frontend using GraphQL as the API layer between UI and backend services",
                "v0_6_feature": True,
                "components": [
                    "GraphQL schema generated from BackendSpec entities",
                    "Auto-generated resolvers for CRUD operations",
                    "External API adapters for third-party integrations",
                    "Unified error normalization",
                ],
                "example": """# GraphQL schema is auto-generated from your entities:
# entity Task → GraphQL type Task with Query/Mutation

# Inspect the generated schema:
# $ dazzle dnr inspect --schema

# Mount GraphQL endpoint in your app:
from dazzle_dnr_back.graphql import mount_graphql
mount_graphql(app, backend_spec)

# Query example:
query {
  tasks(status: "todo") {
    id
    title
    status
  }
}

# Mutation example:
mutation {
  createTask(input: {title: "New task"}) {
    id
    title
  }
}""",
                "use_cases": [
                    "Mobile apps needing flexible data fetching",
                    "Complex UIs with nested data requirements",
                    "Multi-client applications (web, mobile, desktop)",
                    "APIs aggregating multiple external services",
                ],
            },
            "external_adapter": {
                "category": "Integration (v0.6)",
                "definition": "Abstract base class for integrating with external APIs (HMRC, banks, payment providers, etc.) with built-in retry logic, rate limiting, and error normalization.",
                "syntax": """from dazzle_dnr_back.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    AdapterResult,
)

class MyServiceAdapter(BaseExternalAdapter[AdapterConfig]):
    async def get_data(self, id: str) -> AdapterResult[dict]:
        return await self._get(f"/api/data/{id}")""",
                "example": """from dazzle_dnr_back.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    RetryConfig,
    RateLimitConfig,
    AdapterResult,
)

class HMRCAdapter(BaseExternalAdapter[AdapterConfig]):
    \"\"\"Adapter for HMRC VAT API.\"\"\"

    def __init__(self, bearer_token: str):
        config = AdapterConfig(
            base_url="https://api.service.hmrc.gov.uk",
            timeout=30.0,
            headers={"Authorization": f"Bearer {bearer_token}"},
            retry=RetryConfig(max_retries=3, base_delay=1.0),
            rate_limit=RateLimitConfig(requests_per_second=4),
        )
        super().__init__(config)

    async def get_vat_obligations(
        self, vrn: str, from_date: str, to_date: str
    ) -> AdapterResult[list[dict]]:
        \"\"\"Fetch VAT obligations for a business.\"\"\"
        return await self._get(
            f"/organisations/vat/{vrn}/obligations",
            params={"from": from_date, "to": to_date, "status": "O"},
        )""",
                "related": ["error_normalization", "adapter_result", "graphql_bff_pattern"],
                "v0_6_changes": "NEW in v0.6",
            },
            "adapter_result": {
                "category": "Integration (v0.6)",
                "definition": "Result type for adapter operations using success/failure pattern instead of exceptions for expected errors.",
                "syntax": """AdapterResult[T] = Success with data or Failure with error

result = await adapter.get_data(id)
if result.is_success:
    data = result.data  # Access the data
else:
    error = result.error  # Handle the error""",
                "example": """async def fetch_customer_data(customer_id: str):
    result = await crm_adapter.get_customer(customer_id)

    if result.is_success:
        return result.data

    # Handle specific error types
    if result.error.status_code == 404:
        return None  # Customer not found

    # Re-raise unexpected errors
    raise result.error

# Or use unwrap_or for defaults:
data = result.unwrap_or(default_data)

# Or map the result:
names = result.map(lambda data: data["name"])""",
                "related": ["external_adapter", "error_normalization"],
                "v0_6_changes": "NEW in v0.6",
            },
            "error_normalization": {
                "category": "Integration (v0.6)",
                "definition": "System for converting diverse external API errors into a consistent format for GraphQL responses.",
                "syntax": """from dazzle_dnr_back.graphql.adapters import (
    normalize_error,
    NormalizedError,
    ErrorCategory,
    ErrorSeverity,
)

normalized = normalize_error(error, service_name="hmrc")""",
                "example": """from dazzle_dnr_back.graphql.adapters import (
    normalize_error,
    ErrorCategory,
    ErrorSeverity,
)

try:
    result = await hmrc_adapter.get_vat_obligations(vrn)
except AdapterError as e:
    normalized = normalize_error(e, request_id="req-123")

    # Access normalized error properties
    print(normalized.code)           # "HMRC_RATE_LIMIT_EXCEEDED"
    print(normalized.category)       # ErrorCategory.RATE_LIMIT
    print(normalized.severity)       # ErrorSeverity.WARNING
    print(normalized.user_message)   # "Too many requests. Please try again in 30 seconds."
    print(normalized.retry_after)    # 30.0

    # Convert to GraphQL error extensions
    extensions = normalized.to_graphql_extensions()
    raise GraphQLError(normalized.user_message, extensions=extensions)""",
                "related": ["external_adapter", "adapter_result", "error_category"],
                "v0_6_changes": "NEW in v0.6",
            },
            "error_category": {
                "category": "Integration (v0.6)",
                "definition": "High-level error categories for routing and handling decisions in the GraphQL layer.",
                "syntax": """ErrorCategory.AUTHENTICATION  # Redirect to login
ErrorCategory.AUTHORIZATION   # Show forbidden message
ErrorCategory.VALIDATION      # Show field-level errors
ErrorCategory.RATE_LIMIT      # Implement backoff
ErrorCategory.TIMEOUT         # Retry or show timeout
ErrorCategory.NOT_FOUND       # Show 404 message
ErrorCategory.EXTERNAL_SERVICE # Show service unavailable
ErrorCategory.INTERNAL        # Log and show generic error""",
                "example": """# Use categories to route error handling:
def handle_adapter_error(normalized: NormalizedError):
    match normalized.category:
        case ErrorCategory.AUTHENTICATION:
            return redirect_to_login()
        case ErrorCategory.RATE_LIMIT:
            return show_retry_message(normalized.retry_after)
        case ErrorCategory.VALIDATION:
            return show_field_errors(normalized.field_errors)
        case _:
            return show_generic_error(normalized.user_message)""",
                "related": ["error_normalization", "error_severity"],
                "v0_6_changes": "NEW in v0.6",
            },
            "error_severity": {
                "category": "Integration (v0.6)",
                "definition": "Error severity levels for logging and alerting decisions.",
                "syntax": """ErrorSeverity.INFO      # Expected errors (validation, not found)
ErrorSeverity.WARNING   # Recoverable errors (rate limits, timeouts)
ErrorSeverity.ERROR     # Unexpected errors needing attention
ErrorSeverity.CRITICAL  # System errors requiring immediate action""",
                "example": """# Log based on severity:
def log_error(normalized: NormalizedError):
    log_data = normalized.to_log_dict()

    match normalized.severity:
        case ErrorSeverity.INFO:
            logger.info("Expected error", extra=log_data)
        case ErrorSeverity.WARNING:
            logger.warning("Recoverable error", extra=log_data)
        case ErrorSeverity.ERROR:
            logger.error("Unexpected error", extra=log_data)
        case ErrorSeverity.CRITICAL:
            logger.critical("System error", extra=log_data)
            alert_on_call_team(normalized)""",
                "related": ["error_normalization", "error_category"],
                "v0_6_changes": "NEW in v0.6",
            },
            "graphql_schema_inspection": {
                "category": "CLI (v0.6)",
                "definition": "CLI command to inspect the auto-generated GraphQL schema from BackendSpec.",
                "syntax": """# Display GraphQL SDL
dazzle dnr inspect --schema

# Get schema info as JSON
dazzle dnr inspect --schema --format json""",
                "example": """$ dazzle dnr inspect --schema
📊 GraphQL Schema

type Query {
  task(id: ID!): Task
  tasks(status: String, limit: Int): [Task!]!
}

type Mutation {
  createTask(input: TaskInput!): Task!
  updateTask(id: ID!, input: TaskInput!): Task!
  deleteTask(id: ID!): Boolean!
}

type Task {
  id: ID!
  title: String!
  status: String!
  createdAt: DateTime!
}

input TaskInput {
  title: String!
  status: String
}""",
                "related": ["graphql_bff_pattern", "external_adapter"],
                "v0_6_changes": "NEW in v0.6",
            },
            # ================================================================
            # v0.7 Business Logic Pattern
            # ================================================================
            "business_logic_pattern": {
                "name": "Business Logic Pattern",
                "description": "Complete entity with state machine, invariants, computed fields, and access rules",
                "v0_7_feature": True,
                "components": [
                    "State machine with guarded transitions",
                    "Computed fields for derived values",
                    "Invariants for cross-field validation",
                    "Access rules for row-level security",
                ],
                "example": """# Complete v0.7.0 Entity with Business Logic
entity Ticket "Support Ticket":
  id: uuid pk
  ticket_number: str(20) unique
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  created_by: ref User required
  assigned_to: ref User
  resolution: text
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Computed field: days since opened
  days_open: computed days_since(created_at)

  # State machine: ticket lifecycle
  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> resolved: requires resolution
    in_progress -> open
    resolved -> closed
    resolved -> in_progress
    closed -> open: role(manager)

  # Invariants: data integrity rules
  # IMPORTANT: Use single = for equality (not ==)
  invariant: status != resolved or resolution != null
  invariant: status != closed or resolution != null
  invariant: priority != critical or assigned_to != null

  # Access rules: visibility and permissions
  access:
    read: created_by = current_user or role(agent) or role(manager)
    write: role(agent) or role(manager)

  # Indexes for performance
  index status, priority
  index assigned_to""",
                "use_cases": [
                    "Workflow systems (tickets, orders, approvals)",
                    "Document lifecycle management",
                    "Multi-role applications with row-level security",
                    "Data integrity enforcement at the model level",
                ],
                "related": ["state_machine", "invariant", "computed_field", "access_rules"],
            },
            # ================================================================
            # v0.7.1 LLM Cognition Pattern
            # ================================================================
            "llm_cognition_pattern": {
                "name": "LLM Cognition Pattern",
                "description": "Entity design optimized for LLM understanding with intent, semantic tags, archetypes, and example data",
                "v0_7_1_feature": True,
                "components": [
                    "Intent declaration explaining entity purpose",
                    "Domain and patterns tags for classification",
                    "Archetypes for shared field patterns",
                    "Example records for data understanding",
                    "Invariant messages for clear validation errors",
                    "Relationship semantics (has_many, embeds, etc)",
                ],
                "example": """# v0.7.1 LLM-Optimized Entity Design

# First, define reusable archetypes
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User

# Main entity with full LLM cognition features
entity Invoice "Invoice":
  intent: "Represent a finalized billing request from vendor to customer"
  domain: billing
  patterns: lifecycle, line_items, audit
  extends: Timestamped, Auditable

  id: uuid pk
  invoice_number: str(50) unique required
  status: enum[draft,sent,paid,overdue,cancelled] = draft
  customer: ref Customer required
  items: has_many InvoiceItem cascade
  subtotal: decimal(10,2) required
  tax_amount: decimal(10,2)
  total: decimal(10,2) required
  due_date: date required
  paid_at: datetime

  # Computed fields
  days_until_due: computed days_since(due_date)
  is_overdue: computed due_date < today and status != paid

  # State machine
  transitions:
    draft -> sent: requires customer
    sent -> paid: requires paid_at
    sent -> overdue: auto after 30 days
    sent -> cancelled: role(admin)
    overdue -> paid: requires paid_at
    * -> cancelled: role(admin)

  # Invariants with messages
  invariant: total = subtotal + tax_amount
    message: "Total must equal subtotal plus tax"
    code: INVOICE_TOTAL_MISMATCH

  invariant: status != paid or paid_at != null
    message: "Paid invoices must have a payment date"
    code: INVOICE_MISSING_PAYMENT_DATE

  # Access rules
  access:
    read: role(accountant) or role(admin) or customer = current_user.company
    write: role(accountant) or role(admin)

  # Example data
  examples:
    {invoice_number: "INV-2024-001", status: draft, subtotal: 1000.00, tax_amount: 200.00, total: 1200.00}
    {invoice_number: "INV-2024-002", status: sent, subtotal: 500.00, tax_amount: 100.00, total: 600.00}
    {invoice_number: "INV-2024-003", status: paid, subtotal: 750.00, tax_amount: 150.00, total: 900.00}

entity InvoiceItem "Invoice Line Item":
  intent: "Single line item on an invoice with quantity and pricing"
  domain: billing
  patterns: line_items
  extends: Timestamped

  id: uuid pk
  invoice: belongs_to Invoice
  description: str(500) required
  quantity: int required
  unit_price: decimal(10,2) required
  line_total: computed quantity * unit_price

  invariant: quantity > 0
    message: "Quantity must be positive"
    code: ITEM_INVALID_QUANTITY

  examples:
    {description: "Consulting hours", quantity: 10, unit_price: 150.00}
    {description: "Software license", quantity: 5, unit_price: 99.00}""",
                "use_cases": [
                    "LLM-assisted code generation from DSL",
                    "Semantic understanding of domain models",
                    "Automatic documentation generation",
                    "Consistent cross-entity patterns",
                    "Better validation error messages",
                ],
                "related": [
                    "intent",
                    "archetype",
                    "domain_patterns",
                    "examples",
                    "invariant_message",
                    "relationships",
                ],
            },
            # ================================================================
            # v0.7.2 Ejection Pattern
            # ================================================================
            "ejection_pattern": {
                "name": "Ejection Pattern",
                "description": "Generate standalone application code from DAZZLE specification for custom deployment",
                "v0_7_2_feature": True,
                "components": [
                    "Ejection configuration in dazzle.toml",
                    "Backend adapter (FastAPI with SQLAlchemy)",
                    "Frontend adapter (React with TanStack Query)",
                    "Testing adapter (Schemathesis, Pytest)",
                    "CI adapter (GitHub Actions, GitLab CI)",
                    "OpenAPI specification generation",
                ],
                "example": """# Step 1: Add ejection configuration to dazzle.toml
[ejection]
enabled = true

[ejection.backend]
framework = "fastapi"
models = "sqlalchemy"
async_handlers = true

[ejection.frontend]
framework = "react"
api_client = "tanstack_query"

[ejection.testing]
contract = "schemathesis"
unit = "pytest"

[ejection.ci]
template = "github_actions"

[ejection.output]
directory = "generated"

# Step 2: Preview what will be generated
dazzle eject run --dry-run

# Step 3: Generate the code
dazzle eject run

# Step 4: Run the generated application
cd generated
docker compose -f docker-compose.dev.yml up

# Step 5: Run the generated tests
cd generated
pytest tests/

# Optional: Generate OpenAPI spec
dazzle eject openapi -o openapi.yaml

# Optional: Check ejection status
dazzle eject status

# Generated file structure:
generated/
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
├── .gitignore
├── backend/
│   ├── main.py
│   ├── models/
│   │   └── {entity}.py
│   ├── schemas/
│   │   └── {entity}.py
│   ├── routes/
│   │   └── {entity}.py
│   ├── guards/
│   │   └── {entity}_guards.py
│   ├── validators/
│   │   └── {entity}_validators.py
│   └── access/
│       └── {entity}_access.py
├── frontend/
│   └── src/
│       ├── types/
│       ├── schemas/
│       ├── hooks/
│       └── components/
├── tests/
│   ├── conftest.py
│   ├── contract/
│   └── unit/
└── .github/
    └── workflows/
        ├── ci.yml
        ├── contract.yml
        └── deploy.yml""",
                "use_cases": [
                    "Deploy to platforms not supporting DNR runtime",
                    "Need code review and audit for compliance",
                    "Performance optimization with precompiled code",
                    "Custom infrastructure requirements",
                    "Migration away from DAZZLE runtime",
                ],
                "related": [
                    "ejection",
                    "ejection_config",
                    "ejection_adapter",
                    "openapi_generation",
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
            # v0.7.0 Business Logic Best Practices
            "business_logic_v0_7": {
                "state_machines": [
                    "Define transitions for enum fields that represent lifecycle states",
                    "Use 'requires' guards for data prerequisites (requires assigned_to)",
                    "Use 'role()' guards for permission-based transitions",
                    "Use wildcard '*' for 'from any state' transitions sparingly",
                ],
                "invariants": [
                    "Use single = for equality (consistent with access rules, not ==)",
                    "Express invariants as 'condition or fallback' pattern",
                    "Example: 'status != resolved or resolution != null'",
                    "Keep invariants focused on one logical constraint each",
                ],
                "computed_fields": [
                    "Use for derived values: days_since(), count(), sum()",
                    "Computed fields are read-only and calculated at query time",
                    "Name clearly to indicate derived nature (days_open, total_items)",
                ],
                "access_rules": [
                    "Use single = for equality checks",
                    "Combine conditions with 'and' / 'or'",
                    "Use 'current_user' to reference logged-in user",
                    "Use 'role(name)' for role-based access",
                ],
            },
            # v0.7.1 LLM Cognition Best Practices
            "llm_cognition_v0_7_1": {
                "intent": [
                    "Write intent as a single sentence explaining WHY the entity exists",
                    "Focus on business purpose, not technical implementation",
                    "Example: 'Track and resolve customer issues through structured workflow'",
                    "Avoid: 'Stores ticket data' (too technical)",
                ],
                "archetypes": [
                    "Create archetypes for cross-cutting concerns (Timestamped, Auditable, SoftDelete)",
                    "Keep archetypes focused on one pattern",
                    "Name archetypes as adjectives (Timestamped, Auditable) or nouns (AuditTrail)",
                    "Entity fields override archetype fields with the same name",
                    "Use 'extends' to compose multiple archetypes",
                ],
                "domain_and_patterns": [
                    "Use 'domain' for single domain classification (billing, identity, commerce)",
                    "Use 'patterns' for multiple behavioral patterns (lifecycle, audit, workflow)",
                    "Common domains: identity, billing, commerce, support, content, analytics",
                    "Common patterns: lifecycle, audit, workflow, aggregate_root, lookup, line_items",
                ],
                "examples": [
                    "Include 2-3 representative example records per entity",
                    "Show different states and variations",
                    "Use realistic but non-sensitive values",
                    "Demonstrate enum values and common field combinations",
                ],
                "relationships": [
                    "Use 'has_many' for parent-owns-children (Order has_many OrderItem)",
                    "Use 'embeds' for value objects without identity (Order embeds Address)",
                    "Use 'belongs_to' on child side of has_many/has_one",
                    "Use 'cascade' for children that should be deleted with parent",
                    "Use 'restrict' to prevent parent deletion if children exist",
                    "Use 'readonly' when viewing children but not modifying through parent",
                ],
                "invariant_messages": [
                    "Add 'message' for user-friendly validation errors",
                    "Add 'code' for API responses and i18n (SCREAMING_SNAKE_CASE)",
                    "Include entity prefix in codes (INVOICE_INVALID_TOTAL)",
                    "Messages should be actionable ('Total must equal subtotal plus tax')",
                ],
            },
            # v0.7.2 Ejection Best Practices
            "ejection_v0_7_2": {
                "when_to_eject": [
                    "Custom deployment requirements not supported by DNR",
                    "Need code review/audit trails for compliance",
                    "Performance optimization beyond DNR capabilities",
                    "Migration away from DAZZLE runtime",
                ],
                "when_not_to_eject": [
                    "Rapid prototyping - use DNR for instant iteration",
                    "Standard deployments - DNR handles most cases",
                    "Frequent DSL changes - ejected code becomes stale",
                ],
                "configuration": [
                    "Always use dry-run first to preview changes",
                    "Set clean=true to avoid stale files",
                    "Choose appropriate adapters for your stack",
                    "Configure output directory to avoid overwriting project files",
                ],
                "generated_code": [
                    "Ejected code is standalone - no DAZZLE runtime dependency",
                    "Business logic (guards, validators, access) is code-generated",
                    "Customize generated code in your target framework",
                    "Re-eject to regenerate from updated DSL (loses customizations)",
                ],
                "testing": [
                    "Contract tests (Schemathesis) verify API against OpenAPI spec",
                    "Unit tests validate business logic (guards, validators)",
                    "Run tests immediately after ejection to verify correctness",
                ],
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
