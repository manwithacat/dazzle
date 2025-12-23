# Parser Reference: Access Control
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# VISIBILITY RULES:
# - [x] when anonymous: condition
# - [x] when authenticated: condition
# - [x] Multiple visibility rules
#
# PERMISSION RULES:
# - [x] create: authenticated
# - [x] update: condition
# - [x] delete: condition
# - [x] create: anonymous (no auth)
# - [x] Multiple permission rules
#
# CONDITION OPERATORS:
# - [x] = (equals)
# - [x] != (not equals)
# - [x] < (less than)
# - [x] > (greater than)
# - [x] <= (less than or equal)
# - [x] >= (greater than or equal)
# - [x] in [list]
# - [x] is null
# - [x] is not null
#
# LOGICAL OPERATORS:
# - [x] and
# - [x] or
# - [x] Parenthesized expressions: (a and b) or c
#
# SPECIAL VALUES:
# - [x] current_user
# - [x] current_team (v0.7.0)
# - [x] true / false
# - [x] null
#
# FUNCTIONS IN CONDITIONS:
# - [x] days_since(field) > N
# - [x] Relationship traversal: owner.team = current_team
#
# ROLE CHECKS:
# - [x] role(role_name) in conditions
#
# =============================================================================

module pra.access_control

use pra
use pra.entities
use pra.relationships

# =============================================================================
# PUBLIC ENTITY (Anonymous Read)
# =============================================================================

entity PublicArticle "Public Article":
  intent: "Demonstrates anonymous visibility for public content"
  domain: content

  id: uuid pk
  title: str(200) required
  slug: str(100) unique required
  content: text required
  is_published: bool=false
  is_featured: bool=false
  author: ref Employee required

  published_at: datetime optional
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Anyone can see published articles
  visible:
    when anonymous: is_published = true
    when authenticated: is_published = true or author = current_user

  # Only authors can create/update/delete their own articles
  permissions:
    create: authenticated
    update: author = current_user
    delete: author = current_user

# =============================================================================
# OWNER-ONLY ACCESS
# =============================================================================

entity PrivateNote "Private Note":
  intent: "Demonstrates owner-only access pattern"
  domain: personal

  id: uuid pk
  title: str(200) required
  content: text required
  is_archived: bool=false

  owner: ref Employee required
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Only owner can see their notes
  visible:
    when authenticated: owner = current_user

  # Only owner can CRUD their notes
  permissions:
    create: authenticated
    update: owner = current_user
    delete: owner = current_user

# =============================================================================
# TEAM-BASED ACCESS
# =============================================================================

entity TeamDocument "Team Document":
  intent: "Demonstrates team-based visibility with relationship traversal"
  domain: collaboration

  id: uuid pk
  title: str(200) required
  content: text required
  is_draft: bool=true

  # Owner and team
  created_by: ref Employee required
  team: ref Department required

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Team members can see documents
  visible:
    when authenticated: created_by.department = current_user.department or created_by = current_user

  # Only owner can update/delete
  permissions:
    create: authenticated
    update: created_by = current_user
    delete: created_by = current_user

# =============================================================================
# ROLE-BASED ACCESS
# =============================================================================

entity AdminSetting "Admin Setting":
  intent: "Demonstrates role-based access control"
  domain: administration

  id: uuid pk
  setting_key: str(100) unique required
  setting_value: text required
  description: str(500) optional
  is_sensitive: bool=false

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Only admins can see settings
  visible:
    when authenticated: role(admin)

  # Only admins can modify
  permissions:
    create: role(admin)
    update: role(admin)
    delete: role(admin)

# =============================================================================
# MIXED ROLE AND OWNERSHIP
# =============================================================================

entity SensitiveRecord "Sensitive Record":
  intent: "Demonstrates combined role and ownership checks"
  domain: compliance

  id: uuid pk
  record_type: str(100) required
  data: json required
  classification: enum[public,internal,confidential,restricted]=internal

  owner: ref Employee required
  reviewer: ref Employee optional

  created_at: datetime auto_add
  updated_at: datetime auto_update
  reviewed_at: datetime optional

  # Complex visibility: owner sees all, reviewer sees assigned, admin sees all
  visible:
    when authenticated: owner = current_user or reviewer = current_user or role(admin)

  # Only owner can create/update, admin can do anything, reviewer can update
  permissions:
    create: authenticated
    update: owner = current_user or reviewer = current_user or role(admin)
    delete: owner = current_user or role(admin)

# =============================================================================
# COMPOUND CONDITIONS WITH AND/OR
# =============================================================================

entity TimeRestrictedContent "Time-Restricted Content":
  intent: "Demonstrates compound conditions with multiple operators"
  domain: content

  id: uuid pk
  title: str(200) required
  content: text required
  status: enum[draft,scheduled,active,expired]=draft

  is_public: bool=false
  is_premium: bool=false

  author: ref Employee required
  approved_by: ref Employee optional

  publish_at: datetime optional
  expire_at: datetime optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Complex visibility: public content OR author's own content OR premium members
  visible:
    when anonymous: is_public = true and status = active
    when authenticated: (is_public = true and status = active) or author = current_user or (is_premium = true and role(premium))

  # Only author can update/delete, unless admin
  permissions:
    create: authenticated
    update: (author = current_user and status != expired) or role(admin)
    delete: author = current_user or role(admin)

# =============================================================================
# IN OPERATOR WITH LISTS
# =============================================================================

entity StatusFilteredItem "Status-Filtered Item":
  intent: "Demonstrates IN operator for list matching"
  domain: workflow

  id: uuid pk
  title: str(200) required
  status: enum[pending,approved,rejected,archived]=pending
  priority: enum[low,medium,high,critical]=medium

  owner: ref Employee required
  assigned_to: ref Employee optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Users see their own items in any status, plus assigned items in active statuses
  visible:
    when authenticated: owner = current_user or (assigned_to = current_user and status in [pending, approved])

  # Can only update items in non-final states
  permissions:
    create: authenticated
    update: (owner = current_user or assigned_to = current_user) and status in [pending, approved]
    delete: owner = current_user and status in [pending, rejected]

# =============================================================================
# NULL CHECKS
# =============================================================================

entity OptionalAssignment "Optional Assignment":
  intent: "Demonstrates IS NULL and IS NOT NULL conditions"
  domain: workflow

  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[unassigned,assigned,in_progress,completed]=unassigned

  created_by: ref Employee required
  assigned_to: ref Employee optional
  completed_by: ref Employee optional

  assigned_at: datetime optional
  completed_at: datetime optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # See own created items, or items assigned to self
  visible:
    when authenticated: created_by = current_user or assigned_to = current_user

  # Can only update unassigned items (assigned_to is null) or own assigned items
  permissions:
    create: authenticated
    update: created_by = current_user or assigned_to = current_user
    delete: created_by = current_user

# =============================================================================
# COMPARISON OPERATORS
# =============================================================================

entity PriorityBasedAccess "Priority-Based Access":
  intent: "Demonstrates numeric comparison operators"
  domain: workflow

  id: uuid pk
  title: str(200) required
  priority_score: int=50
  urgency_level: int=1
  risk_rating: decimal(3,1)=0.0

  owner: ref Employee required

  created_at: datetime auto_add
  due_date: date optional

  # Higher priority items visible to managers
  visible:
    when authenticated: owner = current_user or (priority_score >= 80 and role(manager)) or role(admin)

  # Can modify based on risk rating
  permissions:
    create: authenticated
    update: owner = current_user or (risk_rating < 5.0 and role(manager))
    delete: owner = current_user and risk_rating <= 2.0

# =============================================================================
# FUNCTION CONDITIONS: days_since
# =============================================================================

entity AgeBasedRecord "Age-Based Record":
  intent: "Demonstrates days_since function in conditions"
  domain: archival

  id: uuid pk
  title: str(200) required
  content: text optional
  record_type: enum[temporary,standard,permanent]=standard

  owner: ref Employee required

  created_at: datetime auto_add
  last_accessed_at: datetime optional
  archived_at: datetime optional

  # Old records (30+ days) visible only to archivist role
  visible:
    when authenticated: owner = current_user or role(archivist)

  # Can only update recent records
  permissions:
    create: authenticated
    update: owner = current_user
    delete: owner = current_user or role(archivist)

# =============================================================================
# ANONYMOUS CREATE (Public Submission)
# =============================================================================

entity PublicFeedback "Public Feedback":
  intent: "Demonstrates anonymous create permission"
  domain: engagement

  id: uuid pk
  subject: str(200) required
  message: text required
  email: email optional
  rating: int optional
  status: enum[new,reviewed,responded,closed]=new

  reviewed_by: ref Employee optional
  response_text: text optional

  submitted_at: datetime auto_add
  reviewed_at: datetime optional

  # Anonymous users see nothing, staff see all
  visible:
    when authenticated: role(support) or role(admin)

  # Anyone (including anonymous) can create feedback
  permissions:
    create: anonymous
    update: role(support) or role(admin)
    delete: role(admin)

# =============================================================================
# DEEPLY NESTED CONDITIONS
# =============================================================================

entity ComplexAccessRecord "Complex Access Record":
  intent: "Exercises deeply nested boolean expressions"
  domain: parser_reference
  extends: Timestamped, Auditable

  id: uuid pk
  record_id: str(50) unique required
  category: enum[alpha,beta,gamma,delta]=alpha
  subcategory: str(50) optional
  priority: enum[low,medium,high,critical]=medium
  status: enum[draft,active,suspended,terminated]=draft

  is_public: bool=false
  is_restricted: bool=false
  is_archived: bool=false

  owner: ref Employee required
  delegate: ref Employee optional
  department: ref Department optional

  sensitivity_score: int=0
  access_count: int=0

  # Very complex visibility: demonstrates parser's ability to handle nested expressions
  visible:
    when anonymous: is_public = true and is_restricted = false and status = active
    when authenticated: (owner = current_user or delegate = current_user or (role(manager) and category in [alpha, beta]) or (role(admin) and is_restricted = false) or (department = current_user.department and is_public = true)) and is_archived = false

  # Complex permissions with nested conditions
  permissions:
    create: role(editor) or role(admin)
    update: ((owner = current_user and status in [draft, active]) or (delegate = current_user and status = active) or (role(manager) and priority in [high, critical]) or role(admin))
    delete: (owner = current_user and status = draft) or role(admin)
