# Parser Reference: Personas and Scenarios
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# PERSONA BASICS:
# - [x] persona name "Label":
# - [x] persona name: (no label)
# - [x] description: "..."
# - [x] goals: "goal1", "goal2"
# - [x] proficiency: novice
# - [x] proficiency: intermediate
# - [x] proficiency: expert
# - [x] default_workspace: workspace_name
# - [x] default_route: "/path"
#
# SCENARIO BASICS:
# - [x] scenario name "Name":
# - [x] scenario name: (no name string)
# - [x] description: "..."
# - [x] seed_script: "path/to/data.json"
#
# PERSONA SCENARIO ENTRIES:
# - [x] for persona name:
# - [x] start_route: "/path"
# - [x] seed_script: "path"
#
# DEMO BLOCKS:
# - [x] demo: (top-level)
# - [x] demo: (inside scenario)
# - [x] EntityName:
# - [x] - field: value, field: value
# - [x] String values
# - [x] Number values (int and float)
# - [x] Boolean values (true, false)
# - [x] Identifier values (enum values)
#
# =============================================================================

module pra.personas

use pra
use pra.workspaces

# =============================================================================
# BASIC PERSONA
# =============================================================================

persona basic_user "Basic User":
  description: "A basic user with minimal configuration"

# =============================================================================
# PERSONA WITHOUT LABEL
# =============================================================================

persona anonymous:
  description: "Anonymous visitor persona"

# =============================================================================
# PERSONA WITH ALL FIELDS
# =============================================================================

persona admin "Administrator":
  description: "System administrator with full access to all features"
  goals: "Manage users", "Configure system settings", "Monitor activity"
  proficiency: expert
  default_workspace: admin_console
  default_route: "/admin"

# =============================================================================
# PROFICIENCY LEVELS
# =============================================================================

persona novice_user "New User":
  description: "First-time user learning the system"
  goals: "Complete onboarding", "Learn basic features"
  proficiency: novice
  default_workspace: simple_dashboard
  default_route: "/getting-started"

persona regular_user "Regular User":
  description: "Everyday user with standard skills"
  goals: "Complete daily tasks", "Track progress"
  proficiency: intermediate
  default_workspace: member_dashboard
  default_route: "/dashboard"

persona power_user "Power User":
  description: "Advanced user with deep system knowledge"
  goals: "Optimize workflows", "Create automations", "Train others"
  proficiency: expert
  default_workspace: operations_center
  default_route: "/advanced"

# =============================================================================
# BUSINESS PERSONAS
# =============================================================================

persona sales_rep "Sales Representative":
  description: "Field sales representative managing leads and deals"
  goals: "Convert leads", "Close deals", "Track pipeline"
  proficiency: intermediate
  default_workspace: sales_dashboard
  default_route: "/sales"

persona sales_manager "Sales Manager":
  description: "Sales team manager overseeing performance"
  goals: "Review team metrics", "Forecast revenue", "Assign territories"
  proficiency: expert
  default_workspace: sales_manager_view
  default_route: "/sales/team"

persona support_agent "Support Agent":
  description: "Customer support representative handling tickets"
  goals: "Resolve tickets", "Help customers", "Document solutions"
  proficiency: intermediate
  default_workspace: support_queue
  default_route: "/support"

persona support_manager "Support Manager":
  description: "Support team manager reviewing metrics and escalations"
  goals: "Monitor SLAs", "Handle escalations", "Coach agents"
  proficiency: expert
  default_workspace: support_manager_view
  default_route: "/support/manage"

# =============================================================================
# TECHNICAL PERSONAS
# =============================================================================

persona developer "Developer":
  description: "Software developer building integrations"
  goals: "Build integrations", "Test APIs", "Debug issues"
  proficiency: expert
  default_workspace: developer_console
  default_route: "/developer"

persona devops "DevOps Engineer":
  description: "DevOps engineer managing infrastructure"
  goals: "Monitor systems", "Deploy updates", "Manage infrastructure"
  proficiency: expert
  default_workspace: operations_center
  default_route: "/ops"

# =============================================================================
# BASIC SCENARIO
# =============================================================================

scenario empty_state "Empty State":
  description: "Fresh installation with no data"

# =============================================================================
# SCENARIO WITHOUT NAME STRING
# =============================================================================

scenario minimal:
  description: "Minimal scenario configuration"

# =============================================================================
# SCENARIO WITH SEED SCRIPT
# =============================================================================

scenario sample_data "Sample Data":
  description: "Demo with sample records for all entities"
  seed_script: "fixtures/sample_data.json"

# =============================================================================
# SCENARIO WITH PERSONA ENTRIES
# =============================================================================

scenario busy_workday "Busy Workday":
  description: "High-activity scenario with many pending items"

  for persona admin:
    start_route: "/admin/alerts"
    seed_script: "fixtures/busy_admin.json"

  for persona sales_rep:
    start_route: "/sales/leads"
    seed_script: "fixtures/busy_sales.json"

  for persona support_agent:
    start_route: "/support/queue"
    seed_script: "fixtures/busy_support.json"

# =============================================================================
# SCENARIO WITH MULTIPLE PERSONA ENTRIES
# =============================================================================

scenario onboarding_demo "Onboarding Demo":
  description: "Demo scenario for new user onboarding"
  seed_script: "fixtures/onboarding_base.json"

  for persona novice_user:
    start_route: "/getting-started"
    seed_script: "fixtures/onboarding_new_user.json"

  for persona admin:
    start_route: "/admin/users"

  for persona support_agent:
    start_route: "/support/new-users"

# =============================================================================
# SCENARIO WITH INLINE DEMO (TOP-LEVEL DEMO BLOCK)
# =============================================================================

scenario quick_demo "Quick Demo":
  description: "Demo with inline fixture data"

  demo:
    Task:
      - title: "Review Q1 Report", status: todo, priority: high
      - title: "Update Documentation", status: in_progress, priority: medium
      - title: "Fix Bug #123", status: done, priority: low

    Product:
      - sku: "DEMO-001", name: "Demo Widget", price: 29.99, is_active: true
      - sku: "DEMO-002", name: "Demo Gadget", price: 49.99, is_active: true
      - sku: "DEMO-003", name: "Demo Thing", price: 9.99, is_active: false

# =============================================================================
# DEMO WITH ALL VALUE TYPES
# =============================================================================

scenario value_types "Value Type Demo":
  description: "Demonstrates all demo value types"

  demo:
    FieldTypeShowcase:
      - short_code: "ABC", count: 42, amount: 123.45, is_active: true, is_deleted: false
      - short_code: "XYZ", count: 0, amount: 0.00, is_active: false, is_verified: true
      - short_code: "TEST", count: 100, amount: 999.99, status: active, priority: high

# =============================================================================
# SCENARIO WITH COMBINED SEED AND DEMO
# =============================================================================

scenario full_demo "Full Demo":
  description: "Complete demo with global seed and per-persona configuration"
  seed_script: "fixtures/full_demo_base.json"

  for persona admin:
    start_route: "/admin"
    seed_script: "fixtures/full_demo_admin.json"

  for persona sales_rep:
    start_route: "/sales"

  for persona support_agent:
    start_route: "/support"

  demo:
    Invoice:
      - invoice_number: "INV-001", status: draft, total: 1500.00
      - invoice_number: "INV-002", status: paid, total: 2500.00
      - invoice_number: "INV-003", status: overdue, total: 3500.00

# =============================================================================
# EDGE CASE: MANY GOALS
# =============================================================================

persona multi_goal "Multi-Goal User":
  description: "User with many goals to test goal parsing"
  goals: "Goal One", "Goal Two", "Goal Three", "Goal Four", "Goal Five", "Goal Six"
  proficiency: intermediate

# =============================================================================
# EDGE CASE: PERSONA WITH ONLY REQUIRED FIELDS
# =============================================================================

persona minimal_persona "Minimal":
  description: "Persona with just description"

# =============================================================================
# COMPLEX SCENARIO
# =============================================================================

scenario complex_demo "Complex Demo State":
  description: "Complex scenario demonstrating all features together"
  seed_script: "fixtures/complex_base.json"

  for persona admin:
    start_route: "/admin/dashboard"
    seed_script: "fixtures/complex_admin.json"

  for persona sales_manager:
    start_route: "/sales/pipeline"
    seed_script: "fixtures/complex_sales_manager.json"

  for persona sales_rep:
    start_route: "/sales/my-leads"

  for persona support_manager:
    start_route: "/support/metrics"

  for persona support_agent:
    start_route: "/support/queue"

  for persona developer:
    start_route: "/developer/api"

  demo:
    Company:
      - name: "Acme Corp", industry: "Technology", is_active: true
      - name: "Beta Inc", industry: "Finance", is_active: true
      - name: "Gamma Ltd", industry: "Healthcare", is_active: false

    Employee:
      - employee_id: "EMP001", first_name: "Alice", last_name: "Admin", is_active: true
      - employee_id: "EMP002", first_name: "Bob", last_name: "Builder", is_active: true
      - employee_id: "EMP003", first_name: "Carol", last_name: "Customer", is_active: true

    Task:
      - title: "Critical Task", priority: critical, status: todo
      - title: "Normal Task", priority: medium, status: in_progress
      - title: "Done Task", priority: low, status: done

    Invoice:
      - invoice_number: "INV-2024-001", status: paid, total: 15000.00
      - invoice_number: "INV-2024-002", status: overdue, total: 8500.00
      - invoice_number: "INV-2024-003", status: draft, total: 22000.00
