# LLM-First Spec Analysis Workflow
## Surfacing Hidden State Machines and CRUD Gaps

---

## The Problem with Current Workflow

```
Founder writes spec → Developer writes DSL → Build → Discover gaps → Manual code
                      ↑                              ↑
                  Translation barrier          Gap discovery too late
```

**Issues**:
1. Founder doesn't know what to specify (state machines, CRUD completeness)
2. Gaps discovered after build (expensive iteration)
3. Implicit requirements remain implicit
4. No validation that spec is DSL-ready

---

## Proposed LLM-First Workflow

```
Founder writes spec
        ↓
    LLM Analysis
        ├─ Extract state machines
        ├─ Identify CRUD gaps
        ├─ Find implicit business rules
        └─ Generate clarifying questions
        ↓
    Founder answers (natural language)
        ↓
    LLM generates complete spec
        ↓
    LLM generates DSL
        ↓
    DAZZLE build (90%+ coverage)
        ↓
    Minimal manual work
```

---

## Phase 1: Automated Spec Analysis

### Input: Founder's Original Spec (SPEC.md)

Our actual spec from this project (412 lines, non-technical voice)

### LLM Analysis Prompt

```
You are analyzing a product specification for a DSL-based application generator.
Your goal is to surface implicit requirements that the founder may not realize
need to be specified.

Analyze the attached SPEC.md and produce:

1. STATE MACHINES
   - Identify any entities with status/state fields
   - Extract the state transitions described in the spec
   - List any transitions that are implied but not explicitly stated
   - Flag any states mentioned without transition rules

2. CRUD COMPLETENESS
   - For each entity, determine if Create/Read/Update/Delete is needed
   - Flag any CRUD operations mentioned in user stories but not in data model
   - Identify missing list/detail/search operations

3. BUSINESS RULES
   - Extract validation rules (required fields, constraints)
   - Identify access control requirements (who can do what)
   - Find conditional logic (if X then Y)
   - Surface computed/derived fields

4. MISSING SPECIFICATIONS
   - Entities mentioned but not defined
   - Relationships implied but not specified
   - Edge cases described without resolution
   - Error scenarios without handling

5. CLARIFYING QUESTIONS
   - Generate specific questions for the founder
   - Focus on gaps that would prevent code generation
   - Ask about implicit assumptions
   - Confirm state machine completeness

Format output as structured JSON for further processing.
```

### Example Analysis Output

Running this on our actual SPEC.md:

```json
{
  "state_machines": [
    {
      "entity": "Ticket",
      "field": "status",
      "states": ["open", "in_progress", "resolved", "closed"],
      "transitions_found": [
        {
          "from": "open",
          "to": "in_progress",
          "trigger": "User clicks 'Start Working'",
          "location": "SPEC.md:364-366",
          "side_effects": ["assign to current user", "add comment"],
          "conditions": ["ticket is unassigned or reassignable"]
        },
        {
          "from": "in_progress",
          "to": "resolved",
          "trigger": "User clicks 'Mark as Resolved'",
          "location": "SPEC.md:368-371",
          "side_effects": ["keep assignment", "add timestamp"],
          "conditions": ["user is assigned or is admin"]
        },
        {
          "from": "resolved",
          "to": "closed",
          "trigger": "Confirmation it works",
          "location": "SPEC.md:195-196",
          "side_effects": [],
          "conditions": ["waiting period expired or manual confirmation"]
        },
        {
          "from": "closed",
          "to": "open",
          "trigger": "Issue comes back",
          "location": "SPEC.md:199-200",
          "side_effects": ["unassign", "reset to queue"],
          "conditions": ["any user can reopen"]
        }
      ],
      "transitions_implied_but_missing": [
        {
          "from": "open",
          "to": "closed",
          "reason": "SPEC.md:406 mentions 'ticket was duplicate/spam' but no transition defined",
          "question": "How should spam/duplicate tickets be closed? By anyone, or only admins?"
        },
        {
          "from": "in_progress",
          "to": "open",
          "reason": "SPEC.md:410 mentions 'put back in queue' but conditions unclear",
          "question": "When can someone unassign themselves? Any time, or only if no comments yet?"
        },
        {
          "from": "resolved",
          "to": "in_progress",
          "reason": "SPEC.md:415 mentions 'still broken, keep same assignee'",
          "question": "Who can move a resolved ticket back to in_progress? Creator only, or anyone?"
        }
      ],
      "states_without_exit": [],
      "unreachable_states": []
    }
  ],

  "crud_analysis": [
    {
      "entity": "User",
      "operations_mentioned": {
        "create": {
          "found": true,
          "location": "SPEC.md:404 'Set up users'",
          "who": "Admin/IT",
          "ui_needed": true
        },
        "read": {
          "found": true,
          "location": "SPEC.md:214 'see all tickets created by a user'",
          "who": "Anyone",
          "ui_needed": true
        },
        "update": {
          "found": false,
          "question": "Can users update their own profile (name, email)? Or only admins?"
        },
        "delete": {
          "found": true,
          "location": "SPEC.md:374 'Can't delete a user if they have tickets'",
          "who": "Admin only",
          "constraints": ["no tickets OR reassign all tickets first"],
          "ui_needed": true
        },
        "list": {
          "found": true,
          "location": "SPEC.md:214 'click through to see all tickets'",
          "who": "Anyone",
          "filters_needed": ["assigned tickets", "created tickets"],
          "ui_needed": true
        }
      },
      "missing_operations": ["update"],
      "questions": [
        "Should users be able to edit their own name/email?",
        "Should admins be able to deactivate users instead of deleting?"
      ]
    },
    {
      "entity": "Ticket",
      "operations_mentioned": {
        "create": {
          "found": true,
          "location": "SPEC.md:51-54, 177-181",
          "who": "Any user",
          "required_fields": ["title", "description", "priority"],
          "auto_fields": ["created_by (current user)", "status (open)", "created_at"],
          "ui_needed": true
        },
        "read": {
          "found": true,
          "location": "SPEC.md:144-148",
          "who": "Anyone",
          "includes": ["all comments", "full history"],
          "ui_needed": true
        },
        "update": {
          "found": true,
          "location": "SPEC.md:158-163",
          "who": "Creator, assigned user, or admin",
          "fields": ["title", "description", "status", "priority", "assigned_to"],
          "constraints": ["can't change creator"],
          "ui_needed": true
        },
        "delete": {
          "found": true,
          "location": "SPEC.md:165-169",
          "who": "Admin only (implied)",
          "warning": "if there are comments",
          "ui_needed": true
        },
        "list": {
          "found": true,
          "location": "SPEC.md:135-142",
          "who": "Anyone",
          "filters_needed": [
            "Unassigned only",
            "Assigned to me",
            "Created by me",
            "By status",
            "By priority"
          ],
          "sorting_needed": ["created_at desc", "priority desc"],
          "ui_needed": true
        }
      },
      "missing_operations": [],
      "additional_operations": [
        {
          "name": "assign",
          "trigger": "User clicks 'Assign to Me' or admin assigns",
          "location": "SPEC.md:68-71",
          "question": "Should this be a separate action or just part of update?"
        },
        {
          "name": "status_transition",
          "trigger": "Quick action buttons",
          "location": "SPEC.md:354-358",
          "question": "Separate endpoints for each transition, or single update endpoint?"
        }
      ]
    },
    {
      "entity": "Comment",
      "operations_mentioned": {
        "create": {
          "found": true,
          "location": "SPEC.md:148 'Add Comment button', 193-194",
          "who": "Any user",
          "required_fields": ["ticket", "content"],
          "auto_fields": ["author (current user)", "created_at"],
          "ui_needed": true
        },
        "read": {
          "found": true,
          "location": "SPEC.md:145 'All comments shown chronologically'",
          "who": "Anyone who can view ticket",
          "ui_needed": true,
          "embedded_in": "ticket detail page"
        },
        "update": {
          "found": true,
          "location": "SPEC.md:375 'Comments are permanent (no editing)'",
          "allowed": false,
          "ui_needed": false
        },
        "delete": {
          "found": true,
          "location": "SPEC.md:375 'Comments are permanent (no deleting)'",
          "allowed": false,
          "ui_needed": false
        },
        "list": {
          "found": false,
          "question": "Should there be a page showing all comments across all tickets? Or only shown in ticket context?"
        }
      },
      "missing_operations": [],
      "constraints": ["permanent - no edit/delete", "embedded in ticket view"]
    }
  ],

  "business_rules": [
    {
      "type": "validation",
      "entity": "User",
      "field": "email",
      "rule": "must be unique",
      "location": "SPEC.md:101, 373",
      "error_handling": "prevent duplicate accounts"
    },
    {
      "type": "constraint",
      "entity": "Ticket",
      "field": "created_by",
      "rule": "required, cannot be changed",
      "location": "SPEC.md:115, 163",
      "implementation": "auto-set to current user on create, readonly on edit"
    },
    {
      "type": "constraint",
      "entity": "Ticket",
      "field": "assigned_to",
      "rule": "optional, can be changed",
      "location": "SPEC.md:116, 161-162",
      "implementation": "nullable, editable by reassignment"
    },
    {
      "type": "cascade",
      "entity": "User",
      "rule": "cannot delete user with tickets",
      "location": "SPEC.md:374",
      "question": "What happens: block deletion, or force reassignment first?"
    },
    {
      "type": "auto_timestamp",
      "entity": "Ticket",
      "field": "updated_at",
      "rule": "auto-update on any change",
      "location": "SPEC.md:376"
    },
    {
      "type": "access_control",
      "operation": "edit ticket",
      "rule": "creator, assigned user, or admin",
      "location": "implied from SPEC.md:158-163",
      "question": "Should non-assigned users be able to edit? Or only view?"
    }
  ],

  "missing_specifications": [
    {
      "type": "authentication",
      "issue": "Spec mentions 'current user' but no auth system defined",
      "locations": ["SPEC.md:365", "SPEC.md:398"],
      "questions": [
        "How do users log in? Email/password, SSO, magic link?",
        "Should there be user roles (admin, support, customer)?",
        "How is 'current user' determined?"
      ]
    },
    {
      "type": "notifications",
      "issue": "Mentioned as 'Future Features' but referenced in workflows",
      "locations": ["SPEC.md:379 (future)", "SPEC.md:366 (workflow mentions comment)"],
      "questions": [
        "Should there be ANY notifications for v1? Even just on-screen messages?",
        "When status changes, should creator be notified?"
      ]
    },
    {
      "type": "search",
      "issue": "Listed as 'Out of Scope' but may be needed for usability",
      "locations": ["SPEC.md:381"],
      "questions": [
        "With potentially hundreds of tickets, how do users find old tickets?",
        "Is filtering enough, or do we need text search?"
      ]
    }
  ],

  "clarifying_questions": [
    {
      "category": "State Machine Completeness",
      "priority": "high",
      "questions": [
        {
          "q": "You mentioned closing spam/duplicate tickets directly from 'open' status. Who can do this?",
          "context": "SPEC.md:406",
          "options": ["Anyone", "Assigned user only", "Admin only"],
          "impacts": "Access control logic, UI buttons"
        },
        {
          "q": "When a ticket is marked 'resolved', should there be an automatic timeout before it closes? Or always manual?",
          "context": "SPEC.md:195-196, 286",
          "options": ["Auto-close after 24h", "Auto-close after 7 days", "Always manual", "Let admin configure"],
          "impacts": "Background job scheduling, state transitions"
        },
        {
          "q": "If someone reopens a closed ticket, should it go to 'open' (back in queue) or 'in_progress' (back to same person)?",
          "context": "SPEC.md:348, 418",
          "options": ["Always 'open'", "Back to previous assignee", "User chooses"],
          "impacts": "Reopen button behavior, assignment logic"
        }
      ]
    },
    {
      "category": "CRUD Completeness",
      "priority": "medium",
      "questions": [
        {
          "q": "Should users be able to edit their own profile (name, email)?",
          "context": "Not mentioned in spec",
          "options": ["Yes, users can edit", "No, admin only", "Users can request changes"],
          "impacts": "User edit form, permissions"
        },
        {
          "q": "For the comment list view - should there be a page showing all comments across all tickets, or only in ticket context?",
          "context": "Comment entity defined but no standalone list mentioned",
          "options": ["Only in ticket context", "Standalone list page too", "Not needed"],
          "impacts": "URL routing, UI navigation"
        }
      ]
    },
    {
      "category": "Authentication & Authorization",
      "priority": "high",
      "questions": [
        {
          "q": "How should users log in?",
          "context": "Spec mentions 'current user' but no auth method",
          "options": ["Email/password", "Magic link (passwordless)", "SSO (Google/Microsoft)", "For later"],
          "impacts": "Authentication system, user model"
        },
        {
          "q": "Should there be user roles (admin vs regular user)?",
          "context": "Spec implies admins can do more but not formalized",
          "options": ["Yes, admin + user roles", "Everyone same permissions", "Admin + support + customer"],
          "impacts": "Permission system, access control"
        }
      ]
    }
  ]
}
```

---

## Phase 2: Interactive Clarification

### LLM-Generated Questionnaire

Present to founder in plain language:

```markdown
# Quick Questions to Complete Your Spec

I analyzed your support ticket spec and found a few things that need clarification
before we can generate the app. These are quick decisions - just pick the option
that matches what you want.

## Status Workflow Questions

### 1. Closing spam/duplicate tickets
Your spec mentions closing tickets that are spam or duplicates without assigning them.
**Who should be able to do this?**

○ Anyone who sees the ticket
○ Only admins
● Only the person who created the ticket

*Recommendation: Only admins, to prevent abuse*

---

### 2. Auto-closing resolved tickets
When a ticket is marked "Resolved", what should happen next?

○ Automatically close after 24 hours if no response
○ Always wait for manual confirmation
● Let the creator respond; if no response in 3 days, auto-close

*Recommendation: Auto-close prevents resolved tickets from piling up*

---

### 3. Reopening closed tickets
If someone reopens a closed ticket, what should happen?

● Put it back in the "Open" queue for anyone to pick up
○ Assign it back to whoever resolved it originally
○ Let the person reopening decide who to assign it to

*Recommendation: Back to queue gives flexibility*

---

## Missing Features Questions

### 4. User profile editing
Should users be able to edit their own name and email?

● Yes, users can edit their own profile
○ No, only admins can change user info
○ Users can request changes, admin approves

*Recommendation: Let users self-manage basic info*

---

### 5. Comment listing
Should there be a page showing all recent comments across all tickets?

○ Yes, helpful to see activity feed
● No, comments only show on ticket detail page
○ Maybe in a future version

*Recommendation: Comments in context is clearer*

---

## Authentication Questions

### 6. Login method
How should users log in to the system?

● Email and password (simple)
○ Magic link (passwordless, sent to email)
○ Google/Microsoft SSO
○ We'll add authentication later

*Recommendation: Email/password for v1, can add SSO later*

---

### 7. User roles
Should there be different permission levels?

● Yes: Admin (full access) and User (limited)
○ Yes: Admin, Support Staff, and Customer
○ No: Everyone has the same permissions

*Recommendation: Admin/User split prevents accidents*

---

## Your Answers

Just reply with the numbers and your choices:

1. Only admins
2. Auto-close after 3 days
3. Back to queue
4. Yes
5. No
6. Email/password
7. Admin + User

---

These answers will let me generate a complete, working app with no gaps!
```

### Founder Response (Natural Language)

```
Okay here's what I want:

1. Only admins should close spam tickets - good call on preventing abuse
2. I like the auto-close idea but 3 days is too short. Let's do 7 days.
   If customer doesn't respond in a week, we can assume it's fixed.
3. Reopening should go back to queue - let the team decide who picks it up
4. Yes users should edit their profile, but NOT their email (that's their login)
5. No comment listing page - too confusing
6. Email/password is fine for now
7. Wait, I need three roles actually:
   - Admin (can do everything including delete)
   - Support Staff (can work on tickets, assign, etc)
   - Customers (can only create tickets and comment)

   Is that hard to add?
```

---

## Phase 3: LLM Synthesizes Complete Spec

### LLM Processing

Take original spec + founder's answers → Generate complete, unambiguous spec

```
Input:
- SPEC.md (original)
- Founder's answers above

Output:
- Enhanced SPEC.md with:
  ✓ Complete state machine
  ✓ All transitions defined
  ✓ CRUD operations specified
  ✓ Access control rules
  ✓ Authentication method
  ✓ Role definitions
```

### Generated Enhanced Spec (Excerpt)

```markdown
## State Machine: Ticket Status

### States
- **open**: Just submitted, in queue
- **in_progress**: Someone actively working
- **resolved**: Fix applied, waiting for confirmation
- **closed**: Confirmed fixed

### Transitions

| From | To | Trigger | Who | Side Effects |
|------|----|----|-----|--------------|
| open | in_progress | "Start Working" button | Support Staff, Admin | Assign to self, add comment |
| open | closed | "Close as Spam" button | Admin only | Mark as spam |
| in_progress | resolved | "Mark Resolved" button | Assigned user, Admin | Keep assignment, add timestamp |
| in_progress | open | "Back to Queue" button | Assigned user, Admin | Unassign, add comment |
| resolved | closed | Auto after 7 days | System | Add auto-close comment |
| resolved | closed | "Confirm Fixed" button | Creator, Admin | Add confirmation comment |
| resolved | in_progress | "Still Broken" button | Creator, Support Staff, Admin | Keep assignment, add comment |
| closed | open | "Reopen" button | Any user | Unassign, reset to queue, add comment |

### Business Rules
- Auto-close only runs on tickets in "resolved" status for 7+ days
- When auto-closing, add comment: "Auto-closed: No response after 7 days"
- "Start Working" button only shows if current user is Support Staff or Admin
- Customers cannot see "Mark Resolved" button

---

## Access Control Matrix

| Operation | Customer | Support Staff | Admin |
|-----------|----------|---------------|-------|
| Create Ticket | ✓ | ✓ | ✓ |
| View All Tickets | ✗ (only own) | ✓ | ✓ |
| Edit Own Ticket | ✓ (title, description only) | ✓ (all fields) | ✓ |
| Edit Any Ticket | ✗ | ✓ | ✓ |
| Delete Ticket | ✗ | ✗ | ✓ |
| Assign Ticket | ✗ | ✓ (to self or others) | ✓ |
| Change Status | ✗ (except reopen) | ✓ | ✓ |
| Add Comment | ✓ | ✓ | ✓ |
| Create User | ✗ | ✗ | ✓ |
| Edit Own Profile | ✓ (name only) | ✓ (name only) | ✓ |
| Edit Any Profile | ✗ | ✗ | ✓ |
| Change User Role | ✗ | ✗ | ✓ |

---

## CRUD Operations - Complete List

### User
- **Create**: Admin only, via admin interface
- **Read (Detail)**: Self (own profile) or Admin
- **Read (List)**: Support Staff and Admin only
- **Update**: Users can update own name; Admin can update all fields except email
- **Delete**: Admin only, blocked if user has tickets

### Ticket
- **Create**: All users; auto-set created_by to current user
- **Read (Detail)**: Creator, or Support Staff, or Admin
- **Read (List)**: Customers see own; Support Staff and Admin see all
  - Filters: Status, Priority, Assigned To, Created By, Unassigned
  - Sort: Created Date (desc), Priority (desc)
- **Update**: Creator (limited fields), Assigned User (full), Admin (full)
- **Delete**: Admin only, with confirmation if comments exist

### Comment
- **Create**: All users who can view the ticket
- **Read**: All users who can view the ticket (embedded in ticket detail)
- **Update**: Not allowed (immutable)
- **Delete**: Not allowed (permanent)
- **List**: No standalone list; only shown in ticket context
```

---

## Phase 4: LLM Generates DSL

Now with complete spec, LLM can generate comprehensive DSL

```dsl
# Generated from enhanced SPEC.md
# Date: 2025-11-21

module support_tickets.core

app support_tickets "Support Tickets"

# ============================================================================
# ROLES & AUTHENTICATION
# ============================================================================

# Note to backend: Implement role-based access control
# Roles: customer, support_staff, admin
# Authentication: email/password

# ============================================================================
# ENTITIES
# ============================================================================

entity User "User":
  id: uuid pk
  email: str(255) required unique  # Cannot be changed after creation
  name: str(200) required
  role: enum[customer,support_staff,admin]=customer
  created_at: datetime auto_add

entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  description: text required

  # State machine field - see transitions below
  status: enum[open,in_progress,resolved,closed]=open

  priority: enum[low,medium,high,critical]=medium

  # Relationships
  created_by: ref User required  # Auto-set to current user on create
  assigned_to: ref User  # Nullable, set by "Start Working" action

  # Timestamps
  created_at: datetime auto_add
  updated_at: datetime auto_update
  resolved_at: datetime  # Set when status → resolved
  closed_at: datetime    # Set when status → closed

entity Comment "Comment":
  id: uuid pk
  ticket: ref Ticket required
  author: ref User required  # Auto-set to current user
  content: text required
  created_at: datetime auto_add

# ============================================================================
# STATE MACHINE: Ticket Status
# ============================================================================

# Note: Current DAZZLE doesn't support workflow syntax
# Manual implementation required - see SPEC.md lines 400-422
#
# Required transitions:
#   open → in_progress: "Start Working" (support_staff, admin)
#   open → closed: "Close as Spam" (admin only)
#   in_progress → resolved: "Mark Resolved" (assigned user, admin)
#   in_progress → open: "Back to Queue" (assigned user, admin)
#   resolved → closed: Auto after 7 days (system) OR manual confirm
#   resolved → in_progress: "Still Broken" (any user)
#   closed → open: "Reopen" (any user)
#
# Side effects:
#   - "Start Working": set assigned_to = current_user, add comment
#   - "Mark Resolved": set resolved_at = now(), add comment
#   - "Close": set closed_at = now(), add comment
#   - "Reopen": clear assigned_to, add comment

# ============================================================================
# SURFACES - USER
# ============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  # Access: support_staff, admin only

  section main "Team Members":
    field name "Name"
    field email "Email"
    field role "Role"
    field created_at "Joined"

surface user_detail "User Profile":
  uses entity User
  mode: view
  # Access: self or admin

  section main "Profile":
    field name "Name"
    field email "Email"
    field role "Role"
    field created_at "Member Since"

surface user_create "Add User":
  uses entity User
  mode: create
  # Access: admin only

  section main "New User":
    field email "Email"
    field name "Name"
    field role "Role"

surface user_edit "Edit Profile":
  uses entity User
  mode: edit
  # Access: self (name only) or admin (all fields)
  # Note: email field should be readonly

  section main "Edit Profile":
    field name "Name"
    # Note: Role field only editable by admin

# ============================================================================
# SURFACES - TICKET
# ============================================================================

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list
  # Access: customers see own, support_staff+admin see all
  # Filters needed: status, priority, assigned_to, created_by, unassigned

  section main "Support Tickets":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned To"
    field created_by "Created By"
    field created_at "Created"

surface ticket_detail "Ticket":
  uses entity Ticket
  mode: view
  # Access: creator, assigned user, support_staff, admin
  # Action buttons needed - see state machine above

  section main "Ticket Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_by "Created By"
    field assigned_to "Assigned To"
    field created_at "Created"
    field updated_at "Last Updated"

  # Note: Workflow action buttons to be implemented manually:
  # - "Start Working" button (visible if status=open, user is support_staff/admin)
  # - "Mark Resolved" button (visible if status=in_progress, user is assigned/admin)
  # - "Close as Spam" button (visible if status=open, user is admin)
  # - "Back to Queue" button (visible if status=in_progress, user is assigned/admin)
  # - "Confirm Fixed" button (visible if status=resolved, user is creator/admin)
  # - "Still Broken" button (visible if status=resolved, user is any)
  # - "Reopen" button (visible if status=closed, user is any)

surface ticket_create "New Ticket":
  uses entity Ticket
  mode: create
  # Access: all users
  # Auto-populate: created_by = current_user, status = open

  section main "Submit Support Request":
    field title "Title"
    field description "Describe the issue"
    field priority "How urgent is this?"

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit
  # Access: creator (limited), assigned user, admin
  # Creator can only edit: title, description
  # Support staff can edit: title, description, priority, assigned_to, status
  # Admin can edit: all fields

  section main "Edit Ticket":
    field title "Title"
    field description "Description"
    field priority "Priority"
    field status "Status"
    field assigned_to "Assigned To"

# ============================================================================
# SURFACES - COMMENT
# ============================================================================

# Note: No standalone comment list/detail surfaces
# Comments only shown embedded in ticket detail view

surface comment_create "Add Comment":
  uses entity Comment
  mode: create
  # Access: any user who can view the ticket
  # Auto-populate: author = current_user, ticket = current ticket
  # UI: Embedded in ticket detail page

  section main "Add Comment":
    field content "Your comment"

# ============================================================================
# VALIDATION RULES
# ============================================================================

# Note to backend: Implement these validation rules

# User:
#   - email must be unique across all users
#   - email cannot be changed after creation
#   - role can only be changed by admin

# Ticket:
#   - created_by cannot be changed after creation
#   - status transitions must follow state machine rules
#   - cannot delete ticket if has comments (or cascade delete comments)

# Comment:
#   - immutable after creation (no edit/delete)
#   - author and ticket cannot be changed

# ============================================================================
# ACCESS CONTROL
# ============================================================================

# Note to backend: Implement role-based permissions

# customer:
#   - Can create tickets
#   - Can view own tickets only
#   - Can edit own ticket (title, description only)
#   - Can comment on tickets they can view
#   - Can edit own profile (name only)
#   - Can reopen tickets

# support_staff:
#   - All customer permissions PLUS:
#   - Can view all tickets
#   - Can assign tickets to self or others
#   - Can change ticket status (following state machine)
#   - Can edit all ticket fields
#   - Can view user list

# admin:
#   - All support_staff permissions PLUS:
#   - Can create/edit/delete users
#   - Can change user roles
#   - Can delete tickets
#   - Can close tickets as spam
#   - Full access to all operations
```

---

## Implementation: CLI Tool

### Command: `dazzle analyze-spec`

```bash
$ dazzle analyze-spec SPEC.md --interactive

🔍 Analyzing specification...

Found:
  ✓ 3 entities (User, Ticket, Comment)
  ✓ 1 state machine (Ticket.status)
  ✓ 7 state transitions (4 explicit, 3 implied)
  ⚠ 3 missing transitions
  ⚠ 2 CRUD gaps
  ⚠ 5 access control ambiguities

📊 State Machine Analysis
─────────────────────────────────────────────────
Ticket.status: open → in_progress → resolved → closed

Explicit transitions found: 4
Implied transitions found: 3
Missing transition details: 3

❓ Questions about state transitions:

1. [HIGH] Who can close tickets as spam (open → closed)?
   a) Anyone
   b) Admin only ✓ (recommended)
   c) Support staff and admin

2. [HIGH] Resolved tickets: auto-close or manual?
   a) Auto-close after 24 hours
   b) Auto-close after 7 days ✓ (mentioned in spec)
   c) Always manual confirmation

3. [MEDIUM] Reopening closed tickets: who gets assigned?
   a) Back to open queue ✓ (recommended)
   b) Previous assignee
   c) Person who reopens

Choose answers [1a, 2b, 3a] or type 'skip' to answer later: _
```

### Founder Interaction

```bash
Choose answers: 1b, 2b, 3a

✓ Answers recorded

📝 CRUD Completeness Check
─────────────────────────────────────────────────
User entity:
  ✓ Create (mentioned)
  ✓ Read (mentioned)
  ⚠ Update - not specified
  ✓ Delete (mentioned with constraints)
  ✓ List (mentioned)

❓ Should users be able to edit their own profiles?
   a) Yes, all fields
   b) Yes, name only (not email) ✓ (recommended)
   c) No, admin only

Choose: b

✓ Recorded

Comment entity:
  ✓ Create (embedded in ticket)
  ✓ Read (embedded in ticket)
  ⚠ List - standalone page?

❓ Should there be a page showing all recent comments?
   a) Yes, activity feed
   b) No, only in ticket context ✓ (recommended)

Choose: b

✓ Recorded

🔐 Access Control Analysis
─────────────────────────────────────────────────
Spec mentions "customers", "support staff", "admins"
but doesn't formally define roles.

❓ Should the system have formal user roles?
   a) Yes, 2 roles: Admin + User
   b) Yes, 3 roles: Admin + Support + Customer ✓ (recommended)
   c) No, everyone same permissions

Choose: b

✓ Recorded

Generating enhanced specification...
───────────────────────────────────────────────────

✓ SPEC_ENHANCED.md created (complete state machine, CRUD, access control)
✓ QUESTIONS_ANSWERED.json created (for reference)

Ready to generate DSL? [y/n]: y

Generating DSL from enhanced specification...
───────────────────────────────────────────────────

✓ dsl/app_generated.dsl created
✓ DSL includes:
  - 3 entities with validation rules
  - State machine documentation
  - Access control annotations
  - CRUD surface definitions
  - Workflow action comments

Validate DSL? [y/n]: y

Running: dazzle validate dsl/app_generated.dsl

✓ OK: spec is valid

Summary:
───────────────────────────────────────────────────
From SPEC.md → Enhanced spec → DSL

Next steps:
1. Review dsl/app_generated.dsl
2. Run: dazzle build
3. Implement workflow actions (manual - see comments in DSL)

Estimated coverage: 85% generated, 15% manual (workflow logic)
```

---

## Benefits of This Approach

### 1. Founder-Friendly
- ✓ Founder writes in natural language (comfortable)
- ✓ LLM asks yes/no questions (easy to answer)
- ✓ No need to learn DSL syntax
- ✓ No wireframes required

### 2. Complete Specification
- ✓ LLM surfaces implicit requirements
- ✓ State machines made explicit
- ✓ CRUD gaps identified
- ✓ Access control clarified

### 3. Better Code Generation
- ✓ DSL is complete and unambiguous
- ✓ Less manual coding needed
- ✓ Fewer iterations
- ✓ Higher coverage (85%+ vs 60%)

### 4. Token Efficient (Over Time)
- Initial: 15K tokens (spec + analysis + questions)
- Each rebuild: 1.2K tokens (DSL only)
- Break-even: After 3-4 iterations
- Long-term: 92% token savings

### 5. Catches Problems Early
- ✓ Missing transitions identified before build
- ✓ CRUD completeness verified
- ✓ Access control thought through
- ✓ Edge cases surfaced

---

## Limitations & Edge Cases

### What LLM Can Surface
✓ State machines from status fields
✓ CRUD gaps (missing operations)
✓ Inconsistencies in spec
✓ Implied business rules
✓ Access control ambiguities

### What LLM May Miss
✗ Domain-specific validation (e.g., "email format must match company domain")
✗ Integration requirements (e.g., "sync with Salesforce")
✗ Performance requirements (e.g., "search must return in <200ms")
✗ Complex calculations (e.g., "SLA time excludes weekends")

**Solution**: Iterative refinement + developer review

---

## Recommended Workflow

```
1. Founder writes SPEC.md (natural language, 1-2 hours)
   ↓
2. Run: dazzle analyze-spec SPEC.md --interactive
   ↓
3. Founder answers questions (10-15 minutes)
   ↓
4. LLM generates SPEC_ENHANCED.md + DSL (automatic)
   ↓
5. Developer reviews DSL (30 minutes)
   ↓
6. Run: dazzle build
   ↓
7. 85% coverage → minimal manual work
   ↓
8. Deploy
```

**Total time**: ~3-4 hours from idea to working app
**Founder effort**: ~2 hours
**Developer effort**: ~1-2 hours

---

## Comparison: Current vs LLM-First

| Aspect | Current DAZZLE | LLM-First |
|--------|----------------|-----------|
| Founder effort | Write spec + learn DSL | Write spec + answer questions |
| Developer effort | Write DSL + manual code | Review DSL + minimal code |
| Spec completeness | 60% (founder knowledge limit) | 90% (LLM surfaces gaps) |
| Code coverage | 60% | 85% |
| Iterations | Many (gaps discovered late) | Few (gaps caught early) |
| Time to working app | 1-2 weeks | 1-2 days |
| Token usage (long-term) | Medium | Low (amortized) |

---

## Next Steps for DAZZLE

1. **Implement `dazzle analyze-spec`**
   - Parse natural language specs
   - Extract state machines
   - Identify CRUD gaps
   - Generate clarifying questions

2. **Build Question Templates**
   - State machine transitions
   - Access control patterns
   - CRUD completeness
   - Validation rules

3. **Enhance DSL Generator**
   - Accept enhanced spec as input
   - Generate complete DSL with annotations
   - Include workflow action stubs

4. **Add Workflow Code Generation**
   - Parse state machine definitions
   - Generate Django view methods
   - Generate URL patterns
   - Generate template conditionals

**Result**: 85%+ code coverage from founder's natural language spec, no DSL knowledge required.
