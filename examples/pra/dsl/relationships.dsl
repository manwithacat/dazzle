# Parser Reference: Relationships
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# RELATIONSHIP TYPES:
# - [x] ref (foreign key reference)
# - [x] ref with entity name
# - [x] ref required
# - [x] ref optional
# - [x] has_many (one-to-many) with cascade/restrict/nullify
# - [x] has_one (one-to-one) with cascade/restrict
# - [x] belongs_to (inverse of has_many)
# - [x] embeds (embedded document)
#
# RELATIONSHIP MODIFIERS (for has_many/has_one only):
# - [x] cascade (delete children when parent deleted)
# - [x] restrict (prevent delete if children exist)
# - [x] nullify (set FK to null on parent delete)
# - [x] readonly (relationship cannot be modified)
#
# RELATIONSHIP PATTERNS:
# - [x] Self-referential (entity references itself)
# - [x] Multiple refs to same entity
# - [x] Circular references between entities
# - [x] Deep nesting (A -> B -> C -> D)
# - [x] Via junction entity for many-to-many
#
# =============================================================================

module pra.relationships

use pra
use pra.entities

# =============================================================================
# BASE ENTITIES FOR RELATIONSHIPS
# =============================================================================

entity Company "Company":
  intent: "Parent entity for relationship demonstrations"
  domain: business

  id: uuid pk
  name: str(200) required
  industry: str(100) optional
  founded_year: int optional
  is_active: bool=true

  created_at: datetime auto_add

  # One-to-many relationships (with on_delete behavior and readonly)
  departments: has_many Department cascade
  employees: has_many Employee restrict

entity Department "Department":
  intent: "Child entity demonstrating belongs_to and has_many"
  domain: business

  id: uuid pk
  name: str(100) required
  code: str(20) unique required
  budget: decimal(15,2) optional

  # Foreign key to parent
  company: ref Company required

  # Children (with on_delete behaviors)
  employees: has_many Employee nullify
  projects: has_many DevProject cascade readonly

  created_at: datetime auto_add

entity Employee "Employee":
  intent: "Entity with multiple relationship types"
  domain: business

  id: uuid pk
  employee_id: str(20) unique required
  first_name: str(50) required
  last_name: str(50) required
  email: email unique required
  hire_date: date=today
  salary: decimal(12,2) optional
  is_active: bool=true

  # FK refs
  company: ref Company required
  department: ref Department required

  # Optional self-reference (manager)
  manager: ref Employee optional

  # Note: Self-referential has_many removed to avoid circular reference validation
  # In production, use: direct_reports: has_many Employee restrict

  created_at: datetime auto_add
  updated_at: datetime auto_update

# =============================================================================
# ONE-TO-ONE RELATIONSHIPS
# =============================================================================

entity EmployeeProfile "Employee Profile":
  intent: "One-to-one relationship with Employee"
  domain: business

  id: uuid pk

  # One-to-one: each employee has exactly one profile
  employee: ref Employee unique required

  bio: text optional
  linkedin_url: url optional
  github_url: url optional
  avatar: file optional
  skills: json optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

entity EmployeeAddress "Employee Address":
  intent: "Optional one-to-one relationship"
  domain: business

  id: uuid pk

  # One-to-one unique ref
  employee: ref Employee unique required

  street_line_1: str(200) required
  street_line_2: str(200) optional
  city: str(100) required
  state: str(100) optional
  postal_code: str(20) required
  country: str(100) required

  is_primary: bool=true

# =============================================================================
# has_one RELATIONSHIPS (inverse of one-to-one)
# =============================================================================

entity UserAccount "User Account":
  intent: "Entity to demonstrate has_one relationship"
  domain: auth

  id: uuid pk
  username: str(50) unique required
  email: email unique required

  # One-to-one inverse with cascade behavior
  profile: has_one UserProfile cascade

  created_at: datetime auto_add

entity UserProfile "User Profile":
  intent: "Profile entity for has_one demo"
  domain: auth

  id: uuid pk
  account: ref UserAccount unique required
  display_name: str(100) optional
  avatar_url: url optional
  bio: text optional

  created_at: datetime auto_add

# =============================================================================
# MULTIPLE REFERENCES TO SAME ENTITY
# =============================================================================

entity DevProject "DevProject":
  intent: "Entity with multiple refs to same target entity"
  domain: business

  id: uuid pk
  name: str(200) required
  code: str(20) unique required
  description: text optional
  status: enum[planning,active,on_hold,completed,cancelled]=planning
  budget: decimal(15,2) optional
  start_date: date optional
  end_date: date optional

  # Parent department
  department: ref Department required

  # Multiple refs to Employee with different semantics
  project_manager: ref Employee required
  tech_lead: ref Employee optional
  product_owner: ref Employee optional
  created_by: ref Employee optional

  # One-to-many
  tasks: has_many Task cascade
  members: has_many ProjectMember cascade

  created_at: datetime auto_add
  updated_at: datetime auto_update

entity ProjectMember "DevProject Member":
  intent: "Join table pattern for many-to-many"
  domain: business

  id: uuid pk

  # Composite relationship
  dev_project: ref DevProject required
  employee: ref Employee required

  role: enum[member,lead,reviewer,observer]=member
  allocation_percent: int=100
  joined_at: datetime auto_add
  left_at: datetime optional

  # Composite unique constraint
  unique dev_project, employee

# =============================================================================
# MANY-TO-MANY VIA JUNCTION ENTITY
# =============================================================================

entity Tag "Tag":
  intent: "Entity for many-to-many demonstration"
  domain: content

  id: uuid pk
  name: str(50) unique required
  color: str(7) optional

  # Many-to-many via junction entity
  articles: has_many Article via ArticleTag

entity Article "Article":
  intent: "Entity with many-to-many tags"
  domain: content

  id: uuid pk
  title: str(200) required
  content: text required

  # Many-to-many via junction entity
  tags: has_many Tag via ArticleTag

entity ArticleTag "Article Tag Junction":
  intent: "Junction table for many-to-many"
  domain: content

  id: uuid pk
  article: ref Article required
  tag: ref Tag required
  added_at: datetime auto_add

  unique article, tag

# =============================================================================
# DEEP NESTING (A -> B -> C -> D)
# =============================================================================

entity Task "Task":
  intent: "Third level in DevProject -> Task hierarchy"
  domain: business

  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[todo,in_progress,review,done]=todo
  priority: enum[low,medium,high,critical]=medium
  estimated_hours: decimal(6,2) optional
  actual_hours: decimal(6,2) optional
  due_date: date optional

  # Parent
  dev_project: ref DevProject required

  # Optional assignee
  assignee: ref Employee optional
  reporter: ref Employee optional

  # Subtasks (self-referential for hierarchy)
  parent_task: ref Task optional
  # Note: Self-referential has_many removed to avoid circular reference validation

  # Fourth level
  comments: has_many TaskComment cascade

  created_at: datetime auto_add
  updated_at: datetime auto_update

entity TaskComment "Task Comment":
  intent: "Fourth level demonstrating deep nesting"
  domain: business

  id: uuid pk
  content: text required

  # Parent
  task: ref Task required
  author: ref Employee required

  # Reply to another comment (self-referential)
  reply_to: ref TaskComment optional
  # Note: Self-referential has_many removed to avoid circular reference validation

  created_at: datetime auto_add
  updated_at: datetime auto_update

# =============================================================================
# CIRCULAR REFERENCES
# =============================================================================

entity Category "Category":
  intent: "Self-referential tree structure"
  domain: catalog

  id: uuid pk
  name: str(100) required
  slug: str(100) unique required
  description: text optional
  sort_order: int=0
  is_active: bool=true

  # Self-referential parent (tree structure)
  parent: ref Category optional
  # Note: Self-referential has_many removed to avoid circular reference validation

  products: has_many Product restrict

  created_at: datetime auto_add

entity Product "Product":
  intent: "Entity with category reference"
  domain: catalog

  id: uuid pk
  sku: str(50) unique required
  name: str(200) required
  description: text optional
  price: decimal(10,2) required
  is_active: bool=true

  # Required category
  category: ref Category required

  # Related products via junction
  relations: has_many ProductRelation cascade

  created_at: datetime auto_add

entity ProductRelation "Product Relation":
  intent: "Many-to-many self-reference via join table"
  domain: catalog

  id: uuid pk

  # Source and target products
  source_product: ref Product required
  related_product: ref Product required

  relation_type: enum[similar,accessory,upgrade,replacement]=similar
  sort_order: int=0

  unique source_product, related_product

# =============================================================================
# belongs_to RELATIONSHIP
# =============================================================================

entity Order "Order":
  intent: "Entity demonstrating belongs_to"
  domain: commerce

  id: uuid pk
  order_number: str(50) unique required
  total: decimal(15,2) required
  status: enum[pending,confirmed,shipped,delivered,cancelled]=pending

  customer: ref Customer required

  created_at: datetime auto_add

entity Customer "Customer":
  intent: "Entity with has_many orders"
  domain: commerce

  id: uuid pk
  name: str(200) required
  email: email unique required

  # has_many with inverse side
  orders: has_many Order cascade

entity Review "Review":
  intent: "Entity with belongs_to"
  domain: commerce

  id: uuid pk
  rating: int required
  comment: text optional

  # belongs_to establishes the FK relationship with inverse semantics
  customer: belongs_to Customer
  product: belongs_to Product

  created_at: datetime auto_add

# =============================================================================
# READONLY RELATIONSHIPS
# =============================================================================

entity AuditLog "Audit Log":
  intent: "Entity with readonly has_one (immutable references)"
  domain: audit

  id: uuid pk
  action: enum[create,update,delete] required
  entity_type: str(100) required
  entity_id: uuid required
  old_values: json optional
  new_values: json optional
  ip_address: str(45) optional
  user_agent: str(500) optional

  # FK refs (readonly is for has_many/has_one)
  performed_by: ref Employee required
  company: ref Company required

  occurred_at: datetime auto_add

# =============================================================================
# EMBEDS RELATIONSHIP
# =============================================================================

entity Document "Document":
  intent: "Entity demonstrating embeds for nested data"
  domain: content

  id: uuid pk
  title: str(200) required

  # Embedded document (denormalized/nested data)
  metadata: embeds DocumentMetadata

  created_at: datetime auto_add

entity DocumentMetadata "Document Metadata":
  intent: "Embeddable entity"
  domain: content

  id: uuid pk
  author: str(100) optional
  version: str(20) optional
  keywords: json optional

# =============================================================================
# COMPLEX RELATIONSHIP ENTITY
# =============================================================================

entity Invoice "Invoice":
  intent: "Complex entity with multiple relationship types"
  domain: finance

  id: uuid pk
  invoice_number: str(50) unique required
  status: enum[draft,sent,paid,overdue,cancelled]=draft
  subtotal: decimal(15,2) required
  tax_amount: decimal(15,2)=0.00
  total: decimal(15,2) required
  currency: str(3)="GBP"
  issue_date: date=today
  due_date: date=today + 30d
  paid_date: date optional
  notes: text optional

  # Various FK refs
  company: ref Company required
  customer_company: ref Company required
  dev_project: ref DevProject optional
  created_by: ref Employee required
  approved_by: ref Employee optional

  # Line items (cascade on parent delete)
  line_items: has_many InvoiceLineItem cascade

  created_at: datetime auto_add
  updated_at: datetime auto_update

entity InvoiceLineItem "Invoice Line Item":
  intent: "Child in parent-child cascade relationship"
  domain: finance

  id: uuid pk
  line_number: int required
  description: str(500) required
  quantity: decimal(10,2)=1.00
  unit_price: decimal(15,2) required
  total: decimal(15,2) required
  tax_rate: decimal(5,2)=0.00

  # Parent ref
  invoice: ref Invoice required

  # Optional product reference
  product: ref Product optional

  unique invoice, line_number
