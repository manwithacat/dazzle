"""
Semantic index for DAZZLE DSL v0.2 concepts.

Provides structured definitions, syntax examples, and relationships
for all DAZZLE DSL concepts to enable immediate context access for LLMs.
"""

from typing import Any


def get_semantic_index() -> dict[str, Any]:
    """
    Get the complete semantic index for DAZZLE DSL v0.2.

    Returns a structured dictionary mapping concepts to their definitions,
    syntax, examples, and related concepts.
    """
    return {
        "version": "0.2.0",
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
                "v0_2_changes": "No changes from v0.1"
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
                "v0_2_changes": "Added optional ux: block for semantic layer"
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
                "v0_2_changes": "NEW in v0.2"
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
                "v0_2_changes": "NEW in v0.2"
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
                    "❌ Avoid 'List of...' or 'CRUD for...'"
                ]
            },

            "information_needs": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Specifications for how data should be displayed, sorted, filtered, and searched - the 'what' without the 'how'.",
                "directives": {
                    "show": "Fields to display",
                    "sort": "Default sort order",
                    "filter": "Fields available for filtering",
                    "search": "Fields to include in text search",
                    "empty": "Message when no data available"
                },
                "syntax": """show: field1, field2, field3
sort: field1 desc, field2 asc
filter: status, category, assigned_to
search: title, description, tags
empty: "No items found. Create your first item.\"""",
                "related": ["ux_block"],
                "v0_2_changes": "NEW in v0.2"
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
                    "❌ Don't overuse - reserve for truly important conditions"
                ]
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
                    "❌ Avoid preference-based personas (dark-mode-user)"
                ]
            },

            "scope": {
                "category": "UX Semantic Layer (v0.2)",
                "definition": "Filter expression defining what data a persona can see.",
                "syntax": """scope: all
scope: owner = current_user
scope: team = current_user.team
scope: status = Active and owner = current_user""",
                "related": ["persona", "conditions"],
                "v0_2_changes": "NEW in v0.2"
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
                    "aggregate": "Computed metrics"
                },
                "related": ["workspace", "display_modes", "aggregates"],
                "v0_2_changes": "NEW in v0.2"
            },

            "display_modes": {
                "category": "Workspace Component (v0.2)",
                "definition": "Visualization modes for workspace regions.",
                "modes": {
                    "list": "Traditional table/list (default)",
                    "grid": "Card grid layout",
                    "timeline": "Chronological timeline",
                    "map": "Geographic visualization (requires lat/lng fields)"
                },
                "syntax": "display: <list|grid|timeline|map>",
                "related": ["regions", "workspace"],
                "v0_2_changes": "NEW in v0.2"
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
                    "round": "round(expression, decimals)"
                },
                "syntax": """aggregate:
  total: count(Task)
  completed: count(Task where status = done)
  completion_rate: count(Task where status = done) * 100 / count(Task)
  avg_duration: avg(Task.duration_days)""",
                "related": ["regions", "workspace"],
                "v0_2_changes": "NEW in v0.2"
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
                    "membership": "in [value1, value2, ...]"
                },
                "functions": {
                    "days_since": "days_since(datetime_field)",
                    "count": "count(related_field)",
                    "sum": "sum(numeric_field)",
                    "avg": "avg(numeric_field)"
                },
                "examples": [
                    "status = 'Failed'",
                    "count > 100",
                    "date < today",
                    "status in [Critical, Severe]",
                    "days_since(last_update) > 30",
                    "count(items) = 0 and status != Archived"
                ],
                "related": ["attention_signals", "scope", "regions"],
                "v0_2_changes": "Enhanced with new functions in v0.2"
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
                    "uuid": "UUID identifier"
                },
                "special_types": {
                    "email": "Email address (with validation)",
                    "url": "URL (with validation)",
                    "enum[V1,V2,V3]": "Enumeration of values"
                },
                "modifiers": {
                    "required": "Field must have a value",
                    "optional": "Field can be null (default)",
                    "unique": "Value must be unique across records",
                    "pk": "Primary key",
                    "auto_add": "Auto-set on creation (datetime)",
                    "auto_update": "Auto-update on save (datetime)"
                },
                "related": ["entity"],
                "v0_2_changes": "No changes from v0.1"
            },

            "surface_modes": {
                "category": "Surface System",
                "definition": "Interaction modes for surfaces.",
                "modes": {
                    "list": "Display multiple records (table, grid, cards)",
                    "view": "Display single record details (read-only)",
                    "create": "Form for creating new records",
                    "edit": "Form for modifying existing records"
                },
                "related": ["surface"],
                "v0_2_changes": "No changes from v0.1"
            },

            "relationships": {
                "category": "Type System",
                "definition": "References between entities.",
                "syntax": "field_name: ref <EntityName> [required|optional]",
                "example": "assigned_to: ref User optional",
                "related": ["entity", "field_types"],
                "v0_2_changes": "No changes from v0.1"
            }
        },

        # ================================================================
        # Common Patterns
        # ================================================================
        "patterns": {
            "crud": {
                "name": "CRUD Pattern",
                "description": "Complete create-read-update-delete interface for an entity",
                "surfaces": [
                    "{entity}_list (list mode)",
                    "{entity}_detail (view mode)",
                    "{entity}_create (create mode)",
                    "{entity}_edit (edit mode)"
                ],
                "example_entity": "Task",
                "example_surfaces": ["task_list", "task_detail", "task_create", "task_edit"]
            },
            "dashboard": {
                "name": "Dashboard Pattern",
                "description": "Workspace aggregating multiple data views",
                "components": [
                    "Metrics/KPIs",
                    "Recent activity",
                    "Alerts/attention items",
                    "Quick actions"
                ],
                "v0_2_feature": True
            },
            "role_based_access": {
                "name": "Role-Based Access Pattern",
                "description": "Persona variants controlling scope and capabilities",
                "personas": [
                    "Admin: full access, all records",
                    "Manager: department/team scope",
                    "Member: own records only"
                ],
                "v0_2_feature": True
            }
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
                "enums": "Use lowercase with underscores (in_progress, not InProgress)"
            },
            "purpose_statements": {
                "do": "Explain WHY the surface exists, focus on user intent",
                "dont": "Avoid 'List of...' or 'CRUD for...' or implementation details"
            }
        }
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

    # Direct lookup
    if term_normalized in index["concepts"]:
        return {
            "term": term,
            "found": True,
            **index["concepts"][term_normalized]
        }

    # Search in all concepts for partial matches
    matches = []
    for concept_name, concept_data in index["concepts"].items():
        if term_normalized in concept_name or term_normalized in concept_data.get("definition", "").lower():
            matches.append({
                "name": concept_name,
                "category": concept_data.get("category"),
                "definition": concept_data.get("definition")
            })

    if matches:
        return {
            "term": term,
            "found": False,
            "suggestions": matches
        }

    return {
        "term": term,
        "found": False,
        "error": f"Concept '{term}' not found in semantic index"
    }
