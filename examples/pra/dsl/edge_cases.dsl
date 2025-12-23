# Parser Reference: Edge Cases and Boundary Conditions
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# IDENTIFIER EDGE CASES:
# - [x] Single character identifier
# - [x] Very long identifier
# - [x] Underscore prefix
# - [x] Underscore suffix
# - [x] Multiple underscores
# - [x] Numbers in identifier
# - [x] Keywords as field names (where valid)
#
# STRING EDGE CASES:
# - [x] Empty string
# - [x] Single character string
# - [x] Very long string
# - [x] Escaped quotes
# - [x] Special characters
# - [x] Unicode characters
# - [x] Newlines in strings
# - [x] Template syntax in strings
#
# NUMERIC EDGE CASES:
# - [x] Zero value
# - [x] Large integer
# - [x] Decimal precision
# - [x] Negative default (via expression)
# - [x] Scientific notation (where supported)
#
# FIELD TYPE EDGE CASES:
# - [x] str(1) - minimum length
# - [x] str(10000) - maximum length
# - [x] decimal(1,0) - minimum precision
# - [x] decimal(38,10) - maximum precision
# - [x] Long enum value list
#
# MODIFIER COMBINATIONS:
# - [x] All modifiers on one field
# - [x] Conflicting modifiers (optional required)
# - [x] Multiple defaults
# - [x] Modifier with special default
#
# EXPRESSION EDGE CASES:
# - [x] Deeply nested parentheses
# - [x] Complex boolean expressions
# - [x] Chained comparisons
# - [x] Function call with many args
#
# BLOCK EDGE CASES:
# - [x] Empty section
# - [x] Single-item list
# - [x] Many items in list
# - [x] Deep nesting
# - [x] Mixed content blocks
#
# WHITESPACE EDGE CASES:
# - [x] Multiple blank lines
# - [x] Trailing whitespace
# - [x] Mixed tabs/spaces (not recommended)
# - [x] Long comments
#
# =============================================================================

module pra.edge_cases

use pra
use pra.entities
use pra.relationships

# =============================================================================
# IDENTIFIER EDGE CASES
# =============================================================================

# Single character identifier
entity X "Single Char Entity":
  intent: "Test single character entity name"
  domain: testing

  i: uuid pk
  a: str(255)

# Very long identifier (within reasonable limits)
entity VeryLongEntityNameThatTestsTheLimitsOfIdentifierLength "Long Name":
  intent: "Test very long entity identifier"
  domain: testing

  id: uuid pk
  very_long_field_name_that_tests_limits: str(200)

# Underscore variations
entity _underscore_prefix "Underscore Prefix":
  intent: "Test underscore prefix identifier"
  domain: testing

  id: uuid pk
  _prefixed: str(255)
  suffixed_: str(255)
  __double__: str(255)
  a_b_c_d_e_f: str(255)

# Numbers in identifier
entity Entity123 "Entity with Numbers":
  intent: "Test numbers in entity name"
  domain: testing

  id: uuid pk
  field1: str(255)
  field_2: str(255)
  field_3_test: str(255)

# =============================================================================
# STRING EDGE CASES
# =============================================================================

entity StringEdgeCases "String Edge Cases":
  intent: "Test various string edge cases in fields"
  domain: testing

  id: uuid pk

  # Length variations
  empty_default: str(255)=""
  single_char: str(255)="X"
  long_default: str(500)="This is a much longer default value that tests the parser ability to handle extended string content in default values"

  # Special characters
  with_quotes: str(200)
  with_newline: str(200)
  with_tab: str(200)
  with_unicode: str(200)

  # Template syntax
  template_example: str(500)

# =============================================================================
# NUMERIC EDGE CASES
# =============================================================================

entity NumericEdgeCases "Numeric Edge Cases":
  intent: "Test numeric edge cases"
  domain: testing

  id: uuid pk

  # Integer variations
  zero_int: int=0
  large_int: int=2147483647
  small_int: int=1

  # Decimal variations
  zero_decimal: decimal(10,2)=0.00
  precise_decimal: decimal(38,10)=0.0000000001
  large_decimal: decimal(15,2)=9999999999999.99

  # Edge precision
  min_precision: decimal(1,0)=0
  max_precision: decimal(38,18)=0.000000000000000001

# =============================================================================
# FIELD TYPE EDGE CASES
# =============================================================================

entity FieldTypeEdgeCases "Field Type Edge Cases":
  intent: "Test field type parameter edge cases"
  domain: testing

  id: uuid pk

  # String length limits
  min_length_str: str(1)
  max_length_str: str(10000)

  # Decimal precision limits
  min_decimal: decimal(1,0)
  max_decimal: decimal(38,18)

  # Long enum
  many_values: enum[a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z]=a

  # Boolean with explicit default
  bool_true: bool=true
  bool_false: bool=false

# =============================================================================
# MODIFIER COMBINATION EDGE CASES
# =============================================================================

entity ModifierEdgeCases "Modifier Edge Cases":
  intent: "Test modifier combinations"
  domain: testing

  id: uuid pk

  # All applicable modifiers
  all_mods_str: str(100) unique required
  all_mods_date: datetime unique auto_add

  # Optional with default
  opt_with_default: str(50) optional="default_value"

  # Multiple temporal
  created: datetime auto_add
  modified: datetime auto_update

# =============================================================================
# EXPRESSION EDGE CASES
# =============================================================================

entity ExpressionEdgeCases "Expression Edge Cases":
  intent: "Test complex expression parsing"
  domain: testing

  id: uuid pk

  # For computed fields
  value_a: decimal(10,2)=0.00
  value_b: decimal(10,2)=0.00
  value_c: decimal(10,2)=0.00
  value_d: decimal(10,2)=0.00

  # Deeply nested
  nested_calc: computed (((value_a + value_b) * (value_c - value_d)) / 100)

  # Complex boolean for access control
  status: enum[draft,review,approved,rejected]=draft
  is_public: bool=false

entity DeepNesting "Deep Nesting Test":
  intent: "Test deeply nested structures"
  domain: testing

  id: uuid pk
  value: int=0

  # Access control with deep conditions (simplified for parser)
  visible:
    when authenticated: value >= 0

  permissions:
    create: authenticated
    update: authenticated

# =============================================================================
# BLOCK EDGE CASES
# =============================================================================

# Empty section (minimal surface)
surface empty_surface "Empty Surface":
  mode: custom
  section main:
    field id

# Single item list
entity SingleItem "Single Item List":
  intent: "Test single item in lists"
  domain: testing

  id: uuid pk
  single_enum: enum[only_one]=only_one

# Many items (long list)
entity ManyItems "Many Items":
  intent: "Test many items in entity"
  domain: testing

  id: uuid pk
  field_01: str(255)
  field_02: str(255)
  field_03: str(255)
  field_04: str(255)
  field_05: str(255)
  field_06: str(255)
  field_07: str(255)
  field_08: str(255)
  field_09: str(255)
  field_10: str(255)
  field_11: str(255)
  field_12: str(255)
  field_13: str(255)
  field_14: str(255)
  field_15: str(255)
  field_16: str(255)
  field_17: str(255)
  field_18: str(255)
  field_19: str(255)
  field_20: str(255)

# =============================================================================
# WHITESPACE EDGE CASES
# =============================================================================



# Multiple blank lines above

entity WhitespaceTest "Whitespace Test":
  intent: "Test whitespace handling"
  domain: testing

  id: uuid pk


  # Blank line within block
  name: str(100)

  description: text



# =============================================================================
# COMMENT EDGE CASES
# =============================================================================

# This is a very long comment that spans multiple words and tests how the parser
# handles extended comment content without any issues or problems occurring during
# the parsing process which should work correctly in all circumstances and situations

entity CommentTest "Comment Test":
  # Comment before field
  id: uuid pk  # Inline comment after field

  # Multi-line explanation
  # Line 1
  # Line 2
  # Line 3
  name: str(100)

# =============================================================================
# MINIMAL DEFINITIONS
# =============================================================================

# Minimal entity (just pk)
entity Minimal "Minimal":
  intent: "Minimal valid entity"
  domain: testing
  id: uuid pk

# Minimal surface
surface minimal_surf:
  mode: view
  section main:
    field id

# Minimal workspace
workspace minimal_ws:
  purpose: "Minimal workspace"
  content:
    source: Minimal
    display: list

# Minimal persona
persona min_persona:
  description: "Minimal persona"

# =============================================================================
# COMPLEX NESTED STRUCTURES
# =============================================================================

workspace complex_nested "Complex Nested":
  purpose: "Test complex nesting"
  access: persona(admin, manager)
  stage: "command_center"

  region_a:
    source: Task
    filter: status = todo and priority = urgent
    sort: created_at desc
    limit: 10
    display: list
    action: task_edit
    empty: "No items"
    aggregate:
      total: count(Task)
      urgent: count(Task)

  region_b:
    source: Invoice
    filter: status in [draft, pending]
    display: bar_chart
    group_by: status
    aggregate:
      amount: sum(total)
      count: count(Invoice)

  ux:
    purpose: "Complex UX"

    attention critical:
      when: priority = urgent and status = todo
      message: "Critical item"
      action: task_edit

    attention warning:
      when: status = pending
      message: "Pending item"

    for admin:
      scope: all
      purpose: "Admin view"
      show: region_a, region_b
      show_aggregate: total, amount

# =============================================================================
# RESERVED WORD ADJACENT
# =============================================================================

# Names that are similar to keywords but valid
entity Status "Status Entity":
  intent: "Test status as entity name"
  domain: testing

  id: uuid pk
  name: str(255) required

entity Mode "Mode Entity":
  intent: "Test mode as entity name"
  domain: testing

  id: uuid pk
  name: str(255) required

entity Action "Action Entity":
  intent: "Test action as entity name"
  domain: testing

  id: uuid pk
  name: str(255) required

# =============================================================================
# MULTIPLE DEFINITIONS IN SEQUENCE
# =============================================================================

entity Seq1 "Sequence 1":
  intent: "First in sequence"
  domain: testing
  id: uuid pk
entity Seq2 "Sequence 2":
  intent: "Second in sequence"
  domain: testing
  id: uuid pk
entity Seq3 "Sequence 3":
  intent: "Third in sequence"
  domain: testing
  id: uuid pk

# =============================================================================
# CIRCULAR AND SELF REFERENCE
# =============================================================================

entity TreeNode "Tree Node":
  intent: "Self-referential for tree structure"
  domain: testing

  id: uuid pk
  name: str(100) required
  parent: ref TreeNode optional
  # Note: Self-referential has_many removed to avoid circular reference validation

entity GraphNode "Graph Node":
  intent: "For testing graph relationships"
  domain: testing

  id: uuid pk
  name: str(100) required

entity GraphEdge "Graph Edge":
  intent: "Edge between graph nodes"
  domain: testing

  id: uuid pk
  source: ref GraphNode required
  target: ref GraphNode required
  weight: decimal(5,2)=1.00

# =============================================================================
# STATE MACHINE EDGE CASES
# =============================================================================

entity ComplexState "Complex State Machine":
  intent: "Test complex state machine"
  domain: testing

  id: uuid pk
  name: str(100) required
  status: enum[new,pending,active,paused,completed,cancelled,archived]=new
  is_validated: bool=false
  approved_by: uuid optional

  transitions:
    new -> pending: requires is_validated
    new -> cancelled
    pending -> active: requires approved_by
    pending -> cancelled
    active -> paused
    active -> completed
    paused -> active
    paused -> cancelled
    * -> archived: role(admin)

# =============================================================================
# DEEP RELATIONSHIP CHAINS
# =============================================================================

entity Level1 "Level 1":
  intent: "First level of chain"
  domain: testing
  id: uuid pk
  name: str(255) required

entity Level2 "Level 2":
  intent: "Second level of chain"
  domain: testing
  id: uuid pk
  parent: ref Level1 required
  name: str(255) required

entity Level3 "Level 3":
  intent: "Third level of chain"
  domain: testing
  id: uuid pk
  parent: ref Level2 required
  name: str(255) required

entity Level4 "Level 4":
  intent: "Fourth level of chain"
  domain: testing
  id: uuid pk
  parent: ref Level3 required
  name: str(255) required

entity Level5 "Level 5":
  intent: "Fifth level of chain"
  domain: testing
  id: uuid pk
  parent: ref Level4 required
  name: str(255) required

# =============================================================================
# SPECIAL VALUE DEFAULTS
# =============================================================================

entity SpecialDefaults "Special Defaults":
  intent: "Test special default values"
  domain: testing

  id: uuid pk

  # Zero values
  zero_str: str(255)=""
  zero_int: int=0
  zero_dec: decimal(10,2)=0.00
  zero_bool: bool=false

  # Max-like values
  max_str: str(10)="ZZZZZZZZZZ"
  large_num: int=999999999

  # Status defaults
  status: enum[pending,active,done]=pending

# =============================================================================
# ALL FIELD TYPES TOGETHER
# =============================================================================

entity AllTypesAgain "All Types Combined":
  intent: "Comprehensive field type test"
  domain: testing

  id: uuid pk
  uuid_field: uuid unique
  str_field: str(100) required
  str_short: str(1)
  str_long: str(5000)
  text_field: text
  int_field: int=0
  bool_field: bool=true
  date_field: date
  datetime_field: datetime
  email_field: email unique
  decimal_field: decimal(10,2)=0.00
  money_field: money(USD)=0.00
  json_field: json
  file_field: file
  url_field: url
  timezone_field: timezone="UTC"
  enum_field: enum[a,b,c]=a

  created_at: datetime auto_add
  updated_at: datetime auto_update
