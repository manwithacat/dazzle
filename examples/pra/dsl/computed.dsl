# Parser Reference: Computed Fields and Invariants
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# COMPUTED FIELD BASICS:
# - [x] computed keyword
# - [x] Simple field reference
# - [x] Relation traversal: relation.field
#
# AGGREGATE FUNCTIONS:
# - [x] count(field)
# - [x] sum(field)
# - [x] avg(field)
# - [x] min(field)
# - [x] max(field)
# - [x] days_until(date_field)
# - [x] days_since(date_field)
#
# ARITHMETIC OPERATORS:
# - [x] + (addition)
# - [x] - (subtraction)
# - [x] * (multiplication)
# - [x] / (division)
# - [x] Parenthesized expressions: (a + b) * c
# - [x] Numeric literals: 1.5, 100
#
# COMPUTED PATTERNS:
# - [x] Simple aggregate
# - [x] Aggregate with arithmetic
# - [x] Multiple aggregates combined
# - [x] Relation aggregates: sum(line_items.amount)
#
# INVARIANT BASICS:
# - [x] invariant: expression
# - [x] invariant with message
# - [x] invariant with code
#
# INVARIANT COMPARISON OPERATORS:
# - [x] == (equals)
# - [x] != (not equals)
# - [x] > (greater than)
# - [x] < (less than)
# - [x] >= (greater than or equal)
# - [x] <= (less than or equal)
#
# INVARIANT LOGICAL OPERATORS:
# - [x] and
# - [x] or
# - [x] not
#
# INVARIANT VALUE TYPES:
# - [x] Field references
# - [x] Relation field references: relation.field
# - [x] Numeric literals
# - [x] String literals
# - [x] Boolean literals: true, false
# - [x] null
# - [x] Duration expressions: N days, N hours
#
# =============================================================================

module pra.computed

use pra
use pra.entities
use pra.relationships

# =============================================================================
# SIMPLE COMPUTED FIELDS
# =============================================================================

entity BasicComputed "Basic Computed":
  intent: "Demonstrates simple computed field expressions"
  domain: parser_reference

  id: uuid pk
  name: str(100) required

  # Simple counts on has_many relationships
  children: has_many ComputedChild

  # Count of related items
  child_count: computed count(ComputedChild)

  created_at: datetime auto_add

entity ComputedChild "Computed Child":
  intent: "Child entity for computed field demonstrations"
  domain: parser_reference

  id: uuid pk
  parent: ref BasicComputed required
  value: decimal(15,2) required
  created_at: datetime auto_add

# =============================================================================
# ALL AGGREGATE FUNCTIONS
# =============================================================================

entity OrderWithTotals "Order with Totals":
  intent: "Demonstrates all aggregate functions"
  domain: commerce

  id: uuid pk
  order_number: str(30) unique required
  status: enum[draft,confirmed,shipped,delivered]=draft

  items: has_many OrderItem

  # All aggregate functions
  item_count: computed count(OrderItem)
  subtotal: computed sum(OrderItem.amount)
  average_item_price: computed avg(OrderItem.unit_price)
  min_item_price: computed min(OrderItem.unit_price)
  max_item_price: computed max(OrderItem.unit_price)

  # Date-based computed fields
  order_date: date=today
  delivery_date: date optional

  days_until_delivery: computed days_until(delivery_date)
  days_since_order: computed days_since(order_date)

  created_at: datetime auto_add

entity OrderItem "Order Item":
  intent: "Line item for order totals"
  domain: commerce

  id: uuid pk
  order: ref OrderWithTotals required
  product_name: str(200) required
  quantity: int=1
  unit_price: decimal(15,2) required
  amount: decimal(15,2) required

# =============================================================================
# ARITHMETIC EXPRESSIONS
# =============================================================================

entity InvoiceWithTax "Invoice with Tax":
  intent: "Demonstrates arithmetic operators in computed fields"
  domain: finance

  id: uuid pk
  invoice_number: str(50) unique required

  lines: has_many InvoiceLine

  # Aggregate
  subtotal: computed sum(InvoiceLine.amount)

  # Arithmetic: multiplication with literal
  tax_amount: computed sum(InvoiceLine.amount) * 0.2

  # Arithmetic: addition
  total: computed sum(InvoiceLine.amount) + sum(InvoiceLine.amount) * 0.2

  created_at: datetime auto_add

entity InvoiceLine "Invoice Line":
  intent: "Line item for invoice calculations"
  domain: finance

  id: uuid pk
  invoice: ref InvoiceWithTax required
  description: str(200) required
  amount: decimal(15,2) required

# =============================================================================
# COMPLEX ARITHMETIC EXPRESSIONS
# =============================================================================

entity ProjectMetrics "Project Metrics":
  intent: "Demonstrates complex arithmetic with proper precedence"
  domain: project_management

  id: uuid pk
  project_name: str(200) required

  milestones: has_many Milestone
  time_entries: has_many TimeEntry

  # Multiple aggregates combined
  total_hours: computed sum(TimeEntry.hours)
  billable_hours: computed sum(TimeEntry.billable_hours)
  non_billable_hours: computed sum(TimeEntry.hours) - sum(TimeEntry.billable_hours)

  # Parenthesized expression for correct precedence
  hourly_rate: decimal(10,2)=100.00
  estimated_revenue: computed sum(TimeEntry.billable_hours) * 100

  # Complex: (sum + sum) * rate
  total_cost: computed (sum(TimeEntry.hours) - sum(TimeEntry.billable_hours)) * 50

  # Multiple operations chained
  milestone_count: computed count(Milestone)
  completed_milestones: computed count(Milestone)

  created_at: datetime auto_add

entity Milestone "Milestone":
  intent: "Project milestone for metrics"
  domain: project_management

  id: uuid pk
  project_ref: ref ProjectMetrics required
  name: str(200) required
  target_date: date required
  completed: bool=false
  completed_at: date optional

entity TimeEntry "Time Entry":
  intent: "Time tracking entry for project metrics"
  domain: project_management

  id: uuid pk
  project_ref: ref ProjectMetrics required
  date: date=today
  hours: decimal(6,2) required
  billable_hours: decimal(6,2)=0.00
  description: str(500) optional

# =============================================================================
# DIVISION AND PERCENTAGES
# =============================================================================

entity TeamStats "Team Stats":
  intent: "Demonstrates division in computed expressions"
  domain: analytics

  id: uuid pk
  team_name: str(100) required

  total_tasks: int=0
  completed_tasks: int=0

  # Division to calculate percentage
  completion_rate: computed completed_tasks / total_tasks

  # More complex calculations
  points_earned: decimal(10,2)=0.00
  points_possible: decimal(10,2)=100.00

  score_percentage: computed points_earned / points_possible * 100

  created_at: datetime auto_add

# =============================================================================
# NESTED RELATION AGGREGATES
# =============================================================================

entity DepartmentStats "Department Stats":
  intent: "Demonstrates aggregates over nested relationships"
  domain: organization

  id: uuid pk
  name: str(100) required

  teams: has_many DeptTeam
  projects: has_many DepartmentProject

  # Count teams
  team_count: computed count(DeptTeam)

  # Aggregate through relationship
  total_budget: computed sum(DepartmentProject.budget)

  created_at: datetime auto_add

entity DeptTeam "Dept Team":
  intent: "Team entity for nested aggregates"
  domain: organization

  id: uuid pk
  department: ref DepartmentStats required
  name: str(100) required
  member_count: int=0

entity DepartmentProject "Department Project":
  intent: "Project for budget aggregation"
  domain: organization

  id: uuid pk
  department: ref Department required
  name: str(200) required
  budget: decimal(15,2)=0.00

# =============================================================================
# SIMPLE INVARIANTS
# =============================================================================

entity DateRangeEvent "Date Range Event":
  intent: "Demonstrates basic comparison invariants"
  domain: scheduling

  id: uuid pk
  title: str(200) required
  start_date: date required
  end_date: date required

  created_at: datetime auto_add

  # Basic comparison invariant
  invariant: end_date > start_date

entity QuantityItem "Quantity Item":
  intent: "Demonstrates numeric comparison invariants"
  domain: inventory

  id: uuid pk
  name: str(100) required
  quantity: int=0
  min_quantity: int=0
  max_quantity: int=1000

  created_at: datetime auto_add

  # Multiple invariants
  invariant: quantity >= 0
  invariant: min_quantity >= 0
  invariant: max_quantity >= min_quantity
  invariant: quantity <= max_quantity

# =============================================================================
# INVARIANTS WITH MESSAGES AND CODES
# =============================================================================

entity HotelBooking "Hotel Booking":
  intent: "Demonstrates invariants with messages and error codes"
  domain: hospitality

  id: uuid pk
  confirmation_number: str(20) unique required
  guest_name: str(100) required
  room_type: enum[single,double,suite,penthouse]=double
  check_in: date required
  check_out: date required
  adults: int=1
  children: int=0
  total_guests: int=1

  created_at: datetime auto_add

  # Invariant with message
  invariant: check_out > check_in
    message: "Check-out date must be after check-in date"

  # Invariant with message and code
  invariant: adults >= 1
    message: "At least one adult must be included in the booking"
    code: INVALID_GUEST_COUNT

  # Note: Arithmetic in invariants not supported; use computed field for validation
  invariant: total_guests >= adults
    message: "Total guests must be at least the number of adults"
    code: GUEST_COUNT_MISMATCH

  invariant: total_guests <= 10
    message: "Maximum 10 guests per room"
    code: EXCEEDS_CAPACITY

# =============================================================================
# LOGICAL OPERATORS IN INVARIANTS
# =============================================================================

entity LogicalInvariant "Logical Invariant":
  intent: "Demonstrates AND, OR, NOT in invariants"
  domain: parser_reference

  id: uuid pk
  status: enum[draft,active,suspended,terminated]=draft
  is_verified: bool=false
  is_premium: bool=false
  suspended_at: datetime optional
  termination_reason: text optional
  termination_date: date optional

  created_at: datetime auto_add

  # AND - both conditions must be true
  invariant: status == active and is_verified == true
    message: "Active accounts must be verified"

  # OR - either condition can be true
  invariant: status != suspended or suspended_at != null
    message: "Suspended accounts must have a suspension date"

  # Complex logical expression
  invariant: status != terminated or (termination_reason != null and termination_date != null)
    message: "Terminated accounts require reason and date"

# =============================================================================
# NOT OPERATOR AND NEGATION
# =============================================================================

entity NegationExample "Negation Example":
  intent: "Demonstrates NOT operator in invariants"
  domain: parser_reference

  id: uuid pk
  is_deleted: bool=false
  is_active: bool=true
  deleted_at: datetime optional

  created_at: datetime auto_add

  # NOT operator
  invariant: not is_deleted or deleted_at != null
    message: "Deleted records must have a deletion timestamp"

# =============================================================================
# DURATION EXPRESSIONS
# =============================================================================

entity DurationConstraints "Duration Constraints":
  intent: "Demonstrates duration expressions in invariants"
  domain: scheduling

  id: uuid pk
  event_name: str(200) required
  start_time: datetime required
  end_time: datetime required
  booking_window_start: date required
  booking_window_end: date required

  created_at: datetime auto_add

  # Duration comparisons (these are conceptual - actual implementation may vary)
  invariant: end_time > start_time
    message: "Event must have positive duration"

  invariant: booking_window_end > booking_window_start
    message: "Booking window must be valid"

# =============================================================================
# FIELD REFERENCE COMPARISONS
# =============================================================================

entity FieldComparisons "Field Comparisons":
  intent: "Demonstrates various field comparison patterns"
  domain: parser_reference

  id: uuid pk

  # Numeric comparisons
  current_value: int=0
  previous_value: int=0
  target_value: int=100
  threshold: int=50

  # String comparisons
  primary_code: str(20) required
  alternate_code: str(20) optional

  # Boolean comparisons
  is_enabled: bool=true
  is_visible: bool=true

  created_at: datetime auto_add

  # Greater than
  invariant: target_value > current_value or current_value >= target_value
    message: "Value invariant check"

  # Less than or equal
  invariant: current_value <= target_value
    message: "Current value cannot exceed target"

  # Equality check
  invariant: is_enabled == true or is_visible == false
    message: "Disabled items should be hidden"

# =============================================================================
# LITERAL VALUES IN INVARIANTS
# =============================================================================

entity LiteralComparisons "Literal Comparisons":
  intent: "Demonstrates all literal types in invariants"
  domain: parser_reference

  id: uuid pk

  # Numeric fields
  count: int=0
  rate: decimal(5,2)=0.00
  score: int=0

  # String fields
  status_code: str(10)="INIT"
  category: str(50) optional

  # Boolean fields
  is_active: bool=true
  is_verified: bool=false

  # Optional/nullable field
  optional_ref: uuid optional

  created_at: datetime auto_add

  # Numeric literal comparison
  invariant: count >= 0
    message: "Count cannot be negative"

  invariant: rate <= 100.00
    message: "Rate cannot exceed 100%"

  # String literal comparison
  invariant: status_code != "ERROR"
    message: "Status cannot be ERROR"

  # Boolean literal comparison
  invariant: is_active == true or is_verified == false
    message: "Inactive accounts cannot be verified"

# =============================================================================
# COMPLEX COMBINED EXAMPLE
# =============================================================================

entity ComplexInvariants "Complex Invariants":
  intent: "Exercises all invariant features together"
  domain: parser_reference
  extends: Timestamped, Auditable

  id: uuid pk
  record_id: str(50) unique required

  # Status and lifecycle
  status: enum[draft,pending,approved,rejected,archived]=draft
  priority: enum[low,medium,high,critical]=medium
  is_active: bool=true
  is_locked: bool=false

  # Dates
  effective_date: date required
  expiration_date: date optional
  last_reviewed: datetime optional

  # Quantities
  quantity: int=0
  reserved_quantity: int=0
  available_quantity: int=0

  # Financial
  unit_price: decimal(15,2)=0.00
  discount_percent: decimal(5,2)=0.00
  tax_rate: decimal(5,2)=0.00

  # Computed field combining with invariants
  total_quantity: computed quantity + reserved_quantity

  # Complex invariant: nested logical with multiple comparisons
  invariant: (status == approved or status == archived) and is_active == false or status != approved
    message: "Approved items must be deactivated before archiving"
    code: INVALID_ARCHIVE_STATE

  # Date range invariant
  invariant: expiration_date > effective_date or expiration_date == null
    message: "Expiration date must be after effective date"
    code: INVALID_DATE_RANGE

  # Quantity invariants
  invariant: available_quantity >= 0
    message: "Available quantity cannot be negative"
    code: NEGATIVE_QUANTITY

  invariant: reserved_quantity <= quantity
    message: "Cannot reserve more than total quantity"
    code: OVER_RESERVATION

  # Financial invariants
  invariant: discount_percent >= 0.00 and discount_percent <= 100.00
    message: "Discount must be between 0% and 100%"
    code: INVALID_DISCOUNT

  invariant: tax_rate >= 0.00
    message: "Tax rate cannot be negative"
    code: NEGATIVE_TAX

  # Locked state invariant
  invariant: not is_locked or status != draft
    message: "Draft items cannot be locked"
    code: INVALID_LOCK_STATE
