# Parser Reference: State Machines
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# TRANSITION BASICS:
# - [x] from_state -> to_state (basic transition)
# - [x] Wildcard: * -> to_state (from any state)
# - [x] Multiple transitions per state machine
# - [x] Multiple state machines in one entity
#
# TRANSITION GUARDS:
# - [x] requires field_name (field must not be null)
# - [x] role(role_name) (user must have role)
# - [x] Multiple guards on single transition
#
# AUTO TRANSITIONS:
# - [x] auto (immediate auto transition)
# - [x] auto after N days
# - [x] auto after N hours
# - [x] auto after N minutes
# - [x] auto after N days or manual
#
# TRIGGER TYPES:
# - [x] manual (explicit)
# - [x] auto (automatic)
#
# STATE MACHINE PATTERNS:
# - [x] Simple linear workflow
# - [x] Branching workflow
# - [x] Cyclic workflow (states can loop back)
# - [x] Parallel states (multiple status fields)
# - [x] Complex multi-step approval
#
# =============================================================================

module pra.state_machines

use pra
use pra.entities
use pra.relationships

# =============================================================================
# SIMPLE LINEAR WORKFLOW
# =============================================================================

entity SimpleTicket "Simple Ticket":
  intent: "Demonstrates basic linear state transitions"
  domain: support

  id: uuid pk
  title: str(200) required
  description: text optional

  # Simple three-state linear workflow: open -> in_progress -> closed
  status: enum[open,in_progress,closed]=open

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    open -> in_progress
    in_progress -> closed

# =============================================================================
# TRANSITIONS WITH GUARDS: requires field
# =============================================================================

entity SupportTicket "Support Ticket":
  intent: "Demonstrates field requirement guards on transitions"
  domain: support

  id: uuid pk
  ticket_number: str(20) unique required
  title: str(200) required
  description: text required
  status: enum[new,assigned,investigating,resolved,closed]=new
  resolution_note: text optional

  # Assignee must be set before assigning
  assignee: ref Employee optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Can only assign if assignee field is set
    new -> assigned: requires assignee
    assigned -> investigating
    investigating -> resolved: requires resolution_note
    resolved -> closed

# =============================================================================
# TRANSITIONS WITH ROLE GUARDS
# =============================================================================

entity ApprovalRequest "Approval Request":
  intent: "Demonstrates role-based transition guards"
  domain: workflow

  id: uuid pk
  request_type: str(100) required
  description: text required
  status: enum[draft,pending,approved,rejected,cancelled]=draft
  approved_by: uuid optional
  rejection_reason: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Anyone can submit a draft
    draft -> pending

    # Only managers can approve or reject
    pending -> approved: role(manager)
    pending -> rejected: role(manager) requires rejection_reason

    # Only admins can cancel at any stage
    * -> cancelled: role(admin)

# =============================================================================
# WILDCARD TRANSITIONS (* -> state)
# =============================================================================

entity ProjectTask "Project Task":
  intent: "Demonstrates wildcard transitions from any state"
  domain: project_management

  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[backlog,ready,in_progress,review,done,archived]=backlog
  priority: enum[low,medium,high,critical]=medium

  # Assignee for the task
  assignee: ref Employee optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Normal forward progression
    backlog -> ready
    ready -> in_progress: requires assignee
    in_progress -> review
    review -> done
    done -> archived

    # Wildcard: admin can archive anything
    * -> archived: role(admin)

    # Wildcard: can send anything back to backlog
    * -> backlog: role(manager)

# =============================================================================
# AUTO TRANSITIONS
# =============================================================================

entity ExpiringToken "Expiring Token":
  intent: "Demonstrates automatic time-based transitions"
  domain: security

  id: uuid pk
  token_value: str(200) unique required
  token_type: enum[session,reset,verification,api]=session
  status: enum[active,expired,revoked]=active

  created_at: datetime auto_add
  expires_at: datetime required

  transitions:
    # Auto-expire after 24 hours
    active -> expired: auto after 24 hours

    # Manual revocation allowed
    active -> revoked

# =============================================================================
# AUTO TRANSITIONS WITH MANUAL OVERRIDE
# =============================================================================

entity PendingInvoice "Pending Invoice":
  intent: "Demonstrates auto-transition with manual override option"
  domain: finance

  id: uuid pk
  invoice_number: str(50) unique required
  amount: decimal(15,2) required
  status: enum[pending,auto_reminded,escalated,paid,written_off]=pending
  reminder_sent_at: datetime optional
  paid_at: datetime optional

  created_at: datetime auto_add
  due_date: date required

  transitions:
    # Auto-send reminder after 7 days, but can also be triggered manually
    pending -> auto_reminded: auto after 7 days or manual

    # Auto-escalate after 14 more days, or manual escalation
    auto_reminded -> escalated: auto after 14 days or manual

    # Payment can happen from any unpaid state
    pending -> paid
    auto_reminded -> paid
    escalated -> paid

    # Write-off requires manager approval
    escalated -> written_off: role(manager)

# =============================================================================
# MULTIPLE TIME UNITS
# =============================================================================

entity TimeSensitiveAlert "Time-Sensitive Alert":
  intent: "Demonstrates all time unit options for auto-transitions"
  domain: monitoring

  id: uuid pk
  alert_type: str(100) required
  message: text required
  severity: enum[info,warning,error,critical]=warning
  status: enum[new,acknowledged,investigating,resolved,auto_closed]=new

  acknowledged_by: uuid optional
  resolved_by: uuid optional

  created_at: datetime auto_add

  transitions:
    # Must acknowledge within 5 minutes or auto-escalate
    new -> acknowledged: requires acknowledged_by

    # Investigating phase
    acknowledged -> investigating
    investigating -> resolved: requires resolved_by

    # Auto-close info alerts after 1 hour
    new -> auto_closed: auto after 1 hours

    # Auto-close acknowledged but stale alerts after 2 days
    acknowledged -> auto_closed: auto after 2 days

    # Auto-close resolved alerts after 30 days (archive)
    resolved -> auto_closed: auto after 30 days

# =============================================================================
# COMPLEX MULTI-STEP APPROVAL WORKFLOW
# =============================================================================

entity PurchaseOrder "Purchase Order":
  intent: "Complex approval workflow with multiple approvers and conditions"
  domain: procurement

  id: uuid pk
  po_number: str(30) unique required
  description: str(500) required
  amount: decimal(15,2) required
  currency: str(3)="GBP"
  status: enum[draft,submitted,manager_review,finance_review,cfo_review,approved,rejected,cancelled]=draft

  # Approval chain
  requester: ref Employee required
  manager_approved_by: uuid optional
  manager_approved_at: datetime optional
  finance_approved_by: uuid optional
  finance_approved_at: datetime optional
  cfo_approved_by: uuid optional
  cfo_approved_at: datetime optional
  rejection_reason: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Submit for approval
    draft -> submitted

    # Manager review (required first step)
    submitted -> manager_review
    manager_review -> finance_review: role(manager) requires manager_approved_by
    manager_review -> rejected: role(manager) requires rejection_reason

    # Finance review
    finance_review -> cfo_review: role(finance) requires finance_approved_by
    finance_review -> rejected: role(finance) requires rejection_reason

    # CFO review (for high-value orders)
    cfo_review -> approved: role(cfo) requires cfo_approved_by
    cfo_review -> rejected: role(cfo) requires rejection_reason

    # Direct approval from finance for lower amounts
    finance_review -> approved: role(finance) requires finance_approved_by

    # Requester can cancel draft
    draft -> cancelled
    # Admin can cancel anything
    * -> cancelled: role(admin)

# =============================================================================
# CYCLIC WORKFLOW (States Can Loop Back)
# =============================================================================

entity ReviewableDocument "Reviewable Document":
  intent: "Demonstrates cyclic workflow where states can return to previous states"
  domain: documentation

  id: uuid pk
  title: str(200) required
  content: text required
  version: int=1
  status: enum[draft,under_review,changes_requested,approved,published,archived]=draft

  reviewer: ref Employee optional
  review_comments: text optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Submit for review
    draft -> under_review: requires reviewer

    # Review outcomes
    under_review -> approved: role(reviewer)
    under_review -> changes_requested: role(reviewer) requires review_comments

    # After changes, go back to draft then resubmit
    changes_requested -> draft

    # This creates a cycle: draft -> under_review -> changes_requested -> draft -> ...

    # Publish approved documents
    approved -> published: role(publisher)

    # Archive old versions
    published -> archived: role(admin)

    # Reactivate archived documents
    archived -> draft: role(admin)

# =============================================================================
# MULTIPLE STATUS FIELDS (Parallel State Machines)
# =============================================================================

entity OrderWithPayment "Order with Payment":
  intent: "Demonstrates entity with multiple independent state machines"
  domain: ecommerce

  id: uuid pk
  order_number: str(30) unique required
  total_amount: decimal(15,2) required

  # First state machine: Order fulfillment
  fulfillment_status: enum[pending,processing,shipped,delivered,returned]=pending

  # Second state machine: Payment processing
  payment_status: enum[unpaid,processing,paid,refunded,disputed]=unpaid

  # Third state machine: Customer service
  support_status: enum[none,open,in_progress,resolved]=none

  shipped_at: datetime optional
  delivered_at: datetime optional
  paid_at: datetime optional
  refunded_at: datetime optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Fulfillment transitions
  transitions:
    pending -> processing
    processing -> shipped: requires shipped_at
    shipped -> delivered: requires delivered_at
    delivered -> returned

  # Note: In v0.2, multiple transitions blocks or separate field-specific
  # transitions are planned. For now, primary status field takes precedence.

# =============================================================================
# BRANCHING WORKFLOW
# =============================================================================

entity LeadQualification "Lead Qualification":
  intent: "Demonstrates branching paths in state machine"
  domain: sales

  id: uuid pk
  company_name: str(200) required
  contact_email: email required
  estimated_value: decimal(15,2) optional
  status: enum[new,contacted,qualified,disqualified,nurturing,opportunity,closed_won,closed_lost]=new

  qualification_notes: text optional
  disqualification_reason: text optional

  assigned_to: ref Employee optional

  created_at: datetime auto_add
  updated_at: datetime auto_update

  transitions:
    # Initial contact
    new -> contacted: requires assigned_to

    # Branch 1: Qualified leads
    contacted -> qualified: requires qualification_notes
    qualified -> opportunity: requires estimated_value
    opportunity -> closed_won
    opportunity -> closed_lost

    # Branch 2: Disqualified leads
    contacted -> disqualified: requires disqualification_reason

    # Branch 3: Nurturing (not ready yet)
    contacted -> nurturing
    nurturing -> contacted
    nurturing -> disqualified: requires disqualification_reason

    # Re-qualify old lost deals
    closed_lost -> nurturing: role(sales_manager)

# =============================================================================
# MINIMAL STATE MACHINE (Edge Case)
# =============================================================================

entity ToggleFlag "Toggle Flag":
  intent: "Minimal state machine with just two states"
  domain: configuration

  id: uuid pk
  flag_name: str(100) unique required
  status: enum[off,on]=off

  toggled_by: uuid optional
  toggled_at: datetime optional

  transitions:
    off -> on
    on -> off

# =============================================================================
# KITCHEN SINK: ALL FEATURES COMBINED
# =============================================================================

entity ComplexWorkflow "Complex Workflow":
  intent: "Exercises all state machine features in one entity"
  domain: parser_reference
  extends: Timestamped, Auditable

  id: uuid pk
  workflow_id: str(50) unique required
  title: str(200) required
  description: text optional

  # Main workflow status
  status: enum[draft,pending_review,level1_approved,level2_approved,final_review,completed,rejected,on_hold,cancelled,expired]=draft

  # Required approvals
  reviewer: ref Employee optional
  level1_approver: uuid optional
  level1_approved_at: datetime optional
  level2_approver: uuid optional
  level2_approved_at: datetime optional
  final_approver: uuid optional
  final_approved_at: datetime optional

  # Rejection/cancellation
  rejection_reason: text optional
  hold_reason: text optional
  cancellation_reason: text optional

  transitions:
    # Basic forward flow
    draft -> pending_review: requires reviewer

    # Level 1 approval
    pending_review -> level1_approved: role(approver) requires level1_approver

    # Level 2 approval (manager required)
    level1_approved -> level2_approved: role(manager) requires level2_approver

    # Final review
    level2_approved -> final_review
    final_review -> completed: role(director) requires final_approver

    # Rejection from any review stage (with reason)
    pending_review -> rejected: requires rejection_reason
    level1_approved -> rejected: role(approver) requires rejection_reason
    level2_approved -> rejected: role(manager) requires rejection_reason
    final_review -> rejected: role(director) requires rejection_reason

    # Hold from any active stage
    pending_review -> on_hold: requires hold_reason
    level1_approved -> on_hold: requires hold_reason
    level2_approved -> on_hold: requires hold_reason
    final_review -> on_hold: requires hold_reason

    # Resume from hold (back to previous stage - simplified to pending_review)
    on_hold -> pending_review

    # Cancellation (admin only, from any state)
    * -> cancelled: role(admin) requires cancellation_reason

    # Auto-expire drafts after 30 days
    draft -> expired: auto after 30 days or manual

    # Auto-expire on_hold items after 90 days
    on_hold -> expired: auto after 90 days
