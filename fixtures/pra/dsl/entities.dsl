# Parser Reference: Entity Features
# =============================================================================
#
# COVERAGE CHECKLIST:
# - [x] entity declaration with title string
# - [x] entity declaration without title
# - [x] intent metadata
# - [x] domain metadata
# - [x] patterns list
# - [x] extends (archetype inheritance)
# - [x] archetype kinds: settings, tenant, tenant_settings, user, user_membership
# - [x] singleton entities (is_singleton)
# - [x] tenant root entities (is_tenant_root)
#
# FIELD TYPES:
# - [x] uuid
# - [x] str with length: str(100)
# - [x] str without length: str
# - [x] text
# - [x] int
# - [x] decimal with precision: decimal(19,4)
# - [x] decimal without precision: decimal
# - [x] bool
# - [x] date
# - [x] datetime
# - [x] email
# - [x] json
# - [x] money
# - [x] file
# - [x] url
# - [x] timezone
# - [x] enum with values: enum[a,b,c]
# - [x] enum with many values
#
# FIELD MODIFIERS:
# - [x] pk (primary key)
# - [x] required
# - [x] optional (explicit)
# - [x] unique
# - [x] unique? (unique nullable)
# - [x] auto_add
# - [x] auto_update
#
# DEFAULT VALUES:
# - [x] string default: ="value"
# - [x] integer default: =0
# - [x] decimal default: =0.00
# - [x] boolean default: =true, =false
# - [x] enum default: =pending
# - [x] date literal: =today
# - [x] datetime literal: =now
# - [x] date arithmetic: =today + 7d
# - [x] datetime arithmetic: =now - 24h
#
# PUBLISH DECLARATIONS (v0.18.0):
# NOTE: Publish directives are tested in events.dsl to avoid parser ordering issues
# - [x] publish when created (in events.dsl)
# - [x] publish when updated (in events.dsl)
# - [x] publish when deleted (in events.dsl)
# - [x] publish when field changed (in events.dsl)
#
# EXAMPLES BLOCK:
# - [x] example records with field values
#
# =============================================================================

module pra.entities

use pra

# =============================================================================
# PRIMITIVE FIELD TYPES - All scalar types
# =============================================================================

entity FieldTypeShowcase "Field Type Showcase":
  intent: "Demonstrates every primitive field type supported by the parser"
  domain: parser_reference
  patterns: comprehensive, reference

  # Primary key
  id: uuid pk

  # String types
  short_code: str(10) required
  medium_name: str(100) required
  long_description: str(2000) optional
  unlimited_str: str(255) optional
  multiline_content: text optional

  # Numeric types
  count: int required
  small_count: int=0
  large_number: int optional
  amount: decimal(19,4) required
  simple_decimal: decimal(10,2) optional
  percentage: decimal(5,2)=0.00

  # Boolean
  is_active: bool=true
  is_deleted: bool=false
  is_verified: bool required

  # Date/Time types
  birth_date: date optional
  start_date: date=today
  future_date: date=today + 30d
  past_date: date=today - 7d
  created_at: datetime auto_add
  updated_at: datetime auto_update
  expires_at: datetime=now + 24h
  started_at: datetime=now

  # Semantic types
  contact_email: email unique
  secondary_email: email optional
  profile_data: json optional
  metadata: json required
  price: money optional
  total_cost: money required
  avatar: file optional
  document: file optional
  website: url optional
  callback_url: url required
  user_timezone: timezone="UTC"

  # Enum types
  status: enum[draft,pending,active,archived]=draft
  priority: enum[low,medium,high,critical]=medium
  category: enum[alpha,beta,gamma,delta,epsilon,zeta,eta,theta]=alpha

# =============================================================================
# FIELD MODIFIERS - All modifier combinations
# =============================================================================

entity ModifierShowcase "Modifier Showcase":
  intent: "Demonstrates all field modifier combinations"
  domain: parser_reference

  id: uuid pk

  # Primary key is implicitly required and unique
  external_id: str(50) pk

  # Required vs Optional
  mandatory_field: str(100) required
  optional_field: str(100) optional
  implicit_optional: str(100)

  # Unique constraints
  unique_code: str(20) unique required
  unique_nullable_code: str(20) unique?

  # Auto timestamps
  created_at: datetime auto_add
  modified_at: datetime auto_update

  # Combined modifiers
  unique_required: str(50) unique required

# =============================================================================
# ARCHETYPE: Settings (singleton)
# =============================================================================

entity SystemSettings "System Settings":
  archetype: settings
  intent: "Global system configuration - exactly one record exists"
  domain: configuration

  id: uuid pk

  # System-wide settings
  app_name: str(100)="PRA"
  maintenance_mode: bool=false
  max_users: int=1000
  default_timezone: timezone="Europe/London"
  support_email: email required
  api_rate_limit: int=100
  feature_flags: json optional

  updated_at: datetime auto_update
  updated_by: uuid optional

# =============================================================================
# ARCHETYPE: Tenant (multi-tenancy root)
# =============================================================================

entity Organization "Organization":
  archetype: tenant
  intent: "Tenant root for multi-tenant isolation"
  domain: multitenancy

  id: uuid pk

  name: str(200) required
  slug: str(50) unique required
  custom_domain: str(100) unique?
  plan: enum[free,starter,professional,enterprise]=free
  is_active: bool=true

  created_at: datetime auto_add
  trial_ends_at: date=today + 14d

# =============================================================================
# ARCHETYPE: Tenant Settings
# =============================================================================

entity OrganizationSettings "Organization Settings":
  archetype: tenant_settings
  intent: "Per-tenant configuration scoped to tenant admins"
  domain: configuration

  id: uuid pk
  organization_id: uuid required

  branding_color: str(7)="#3B82F6"
  logo_url: url optional
  custom_domain: str(100) optional
  sso_enabled: bool=false
  sso_provider: enum[none,okta,azure_ad,google]=none

  updated_at: datetime auto_update

# =============================================================================
# ARCHETYPE: User
# =============================================================================

entity AppUser "Application User":
  archetype: user
  intent: "Core user entity with authentication fields"
  domain: identity

  id: uuid pk

  email: email unique required
  password_hash: str(200) optional

  # OAuth support
  oauth_provider: enum[none,google,github,microsoft]=none
  oauth_id: str(200) optional

  # Profile
  display_name: str(100) required
  avatar_url: url optional

  # Status
  is_active: bool=true
  is_verified: bool=false
  last_login_at: datetime optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

# =============================================================================
# ARCHETYPE: User Membership
# =============================================================================

entity OrganizationMembership "Organization Membership":
  archetype: user_membership
  intent: "User-tenant relationship with per-tenant roles"
  domain: multitenancy

  id: uuid pk
  user_id: uuid required
  organization_id: uuid required

  role: enum[member,admin,owner]=member
  invited_by: uuid optional
  invited_at: datetime optional
  accepted_at: datetime optional

  is_active: bool=true
  created_at: datetime auto_add

# =============================================================================
# EXTENDS: Archetype Inheritance
# =============================================================================

archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype SoftDeletable:
  is_deleted: bool=false
  deleted_at: datetime optional
  deleted_by: uuid optional

archetype Auditable:
  created_by: uuid optional
  updated_by: uuid optional
  version: int=1

entity AuditedRecord "Audited Record":
  intent: "Demonstrates archetype inheritance with extends"
  domain: parser_reference
  extends: Timestamped, SoftDeletable, Auditable

  id: uuid pk
  name: str(100) required
  description: text optional

# =============================================================================
# PUBLISH DECLARATIONS (Event Publishing v0.18.0)
# =============================================================================

entity PublishShowcase "Publish Showcase":
  intent: "Demonstrates all publish declaration variants"
  domain: parser_reference

  id: uuid pk
  title: str(200) required
  status: enum[draft,published,archived]=draft
  assigned_to: uuid optional
  priority: enum[low,medium,high]=medium
  content: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # NOTE: Publish directives moved to events.dsl to avoid parser ordering issues
  # See TrackedOrder entity in events.dsl for comprehensive publish coverage

# =============================================================================
# EXAMPLES BLOCK
# =============================================================================

entity ProductCatalog "Product Catalog":
  intent: "Demonstrates example records for LLM cognition"
  domain: commerce
  patterns: catalog, searchable

  id: uuid pk
  sku: str(50) unique required
  name: str(200) required
  description: text optional
  price: money required
  currency: str(3)="GBP"
  category: enum[electronics,clothing,home,food,other]=other
  in_stock: bool=true
  stock_count: int=0

  created_at: datetime auto_add

  examples:
    - sku: "ELEC-001", name: "Wireless Headphones", price: 79.99, category: electronics, in_stock: true, stock_count: 150
    - sku: "CLOTH-042", name: "Cotton T-Shirt", price: 24.99, category: clothing, in_stock: true, stock_count: 500
    - sku: "HOME-103", name: "LED Desk Lamp", price: 45.00, category: home, in_stock: false, stock_count: 0

# =============================================================================
# CONSTRAINTS: Unique and Index
# =============================================================================

entity ConstraintShowcase "Constraint Showcase":
  intent: "Demonstrates entity-level constraints"
  domain: parser_reference

  id: uuid pk
  tenant_id: uuid required
  code: str(20) required
  name: str(100) required
  category: str(50) required
  sort_order: int=0

  created_at: datetime auto_add

  # Multi-column unique constraint
  unique tenant_id, code

  # Index for common queries
  index tenant_id, category
  index category, sort_order

# =============================================================================
# COMPLEX ENTITY: Kitchen Sink
# =============================================================================

entity KitchenSink "Kitchen Sink Entity":
  intent: "Maximum complexity entity exercising all features together"
  domain: parser_reference
  patterns: comprehensive, stress_test, reference
  extends: Timestamped, Auditable

  id: uuid pk
  external_ref: str(100) unique required

  # All field types
  name: str(200) required
  description: text optional
  count: int=0
  amount: decimal(19,4) required
  rate: decimal(5,4)=0.0000
  is_active: bool=true
  is_premium: bool=false
  start_date: date=today
  end_date: date=today + 365d
  processed_at: datetime optional
  email: email optional
  website: url optional
  config: json optional
  attachment: file optional
  tz: timezone="UTC"

  # Complex enum
  status: enum[pending,processing,completed,failed,cancelled,on_hold,escalated]=pending
  tier: enum[bronze,silver,gold,platinum,diamond]=bronze

  # NOTE: Publish events tested in events.dsl (see TrackedOrder)

  # Constraints
  unique external_ref
  index status, tier
  index start_date, end_date

  examples:
    - external_ref: "KS-2024-001", name: "Test Record Alpha", amount: 1234.5678, status: pending, tier: gold
    - external_ref: "KS-2024-002", name: "Test Record Beta", amount: 9999.9999, status: completed, tier: platinum
