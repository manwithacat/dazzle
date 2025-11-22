"""
Test fixtures and mock data for LLM testing.
"""

# Mock LLM response for a simple task manager spec
MOCK_TASK_ANALYSIS_JSON = {
    "state_machines": [
        {
            "entity": "Task",
            "field": "status",
            "states": ["todo", "in_progress", "done"],
            "transitions_found": [
                {
                    "from": "todo",
                    "to": "in_progress",
                    "trigger": "User starts working on task",
                    "location": "SPEC.md:25",
                    "who_can_trigger": "task owner",
                    "side_effects": ["update updated_at timestamp"],
                    "conditions": [],
                },
                {
                    "from": "in_progress",
                    "to": "done",
                    "trigger": "User marks task complete",
                    "location": "SPEC.md:27",
                    "who_can_trigger": "task owner",
                    "side_effects": ["update updated_at timestamp"],
                    "conditions": [],
                },
            ],
            "transitions_implied_but_missing": [
                {
                    "from": "in_progress",
                    "to": "todo",
                    "reason": "User might want to restart a task",
                    "question": "Can users move tasks back from 'in progress' to 'to do'?",
                }
            ],
            "states_without_exit": [],
            "unreachable_states": [],
        }
    ],
    "crud_analysis": [
        {
            "entity": "Task",
            "operations_mentioned": {
                "create": {
                    "found": True,
                    "location": "SPEC.md:32",
                    "who": "any user",
                    "ui_needed": True,
                },
                "read": {
                    "found": True,
                    "location": "SPEC.md:44",
                    "who": "task owner",
                    "ui_needed": True,
                },
                "update": {
                    "found": True,
                    "location": "SPEC.md:49",
                    "who": "task owner",
                    "constraints": ["can only update own tasks"],
                    "ui_needed": True,
                },
                "delete": {
                    "found": True,
                    "location": "SPEC.md:54",
                    "who": "task owner",
                    "question": "Should there be confirmation before deleting?",
                    "ui_needed": True,
                },
                "list": {
                    "found": True,
                    "location": "SPEC.md:33",
                    "who": "any user",
                    "filters_needed": ["status", "priority"],
                    "ui_needed": True,
                },
            },
            "missing_operations": [],
            "questions": [
                "Should there be confirmation before deleting?",
                "Can users filter tasks by date range?",
            ],
        }
    ],
    "business_rules": [
        {
            "type": "validation",
            "entity": "Task",
            "field": "title",
            "rule": "Required field, maximum 200 characters",
            "location": "SPEC.md:22",
        },
        {
            "type": "validation",
            "entity": "Task",
            "field": "description",
            "rule": "Optional field, text area",
            "location": "SPEC.md:23",
        },
        {
            "type": "constraint",
            "entity": "Task",
            "field": "priority",
            "rule": "Must be one of: Low, Medium, High. Defaults to Medium.",
            "location": "SPEC.md:26",
        },
        {
            "type": "access_control",
            "entity": "Task",
            "field": None,
            "rule": "Users can only edit and delete their own tasks",
            "location": "SPEC.md:50",
        },
    ],
    "missing_specifications": [],
    "clarifying_questions": [
        {
            "category": "State Machine",
            "priority": "medium",
            "questions": [
                {
                    "q": "Can users move tasks back from 'in progress' to 'to do'?",
                    "context": "The spec mentions moving tasks forward but doesn't specify if users can move them backward",
                    "options": [
                        "Yes, users can move tasks back",
                        "No, tasks can only move forward",
                        "Only if task has no time logged",
                    ],
                    "impacts": "State transition logic, UI button availability",
                }
            ],
        },
        {
            "category": "CRUD Completeness",
            "priority": "low",
            "questions": [
                {
                    "q": "Should there be confirmation before deleting tasks?",
                    "context": "Delete operation is mentioned but confirmation dialog is not specified",
                    "options": [
                        "Yes, always confirm",
                        "No confirmation needed",
                        "Confirm only for tasks with comments/attachments",
                    ],
                    "impacts": "UX flow, data safety",
                },
                {
                    "q": "Can users filter tasks by date range?",
                    "context": "Filtering by status and priority mentioned, but date filtering unclear",
                    "options": [
                        "Yes, add date range filter",
                        "No, only status/priority filters",
                        "Show created date but no filter",
                    ],
                    "impacts": "List surface complexity, query performance",
                },
            ],
        },
    ],
}


# Mock LLM response for support tickets (more complex)
MOCK_TICKET_ANALYSIS_JSON = {
    "state_machines": [
        {
            "entity": "Ticket",
            "field": "status",
            "states": ["open", "in_progress", "resolved", "closed"],
            "transitions_found": [
                {
                    "from": "open",
                    "to": "in_progress",
                    "trigger": "Support agent assigns ticket to themselves",
                    "who_can_trigger": "support staff",
                    "side_effects": ["send email to user", "update assigned_to field"],
                },
                {
                    "from": "in_progress",
                    "to": "resolved",
                    "trigger": "Support agent marks ticket as resolved",
                    "who_can_trigger": "assigned support staff",
                    "side_effects": ["send email to user", "request user confirmation"],
                },
                {
                    "from": "resolved",
                    "to": "closed",
                    "trigger": "User confirms resolution or 7 days pass",
                    "who_can_trigger": "user or system (auto-close)",
                    "side_effects": ["send closure email", "archive ticket"],
                },
            ],
            "transitions_implied_but_missing": [
                {
                    "from": "closed",
                    "to": "open",
                    "reason": "Spec mentions 'reopening tickets' but doesn't specify who can do this",
                    "question": "Who can reopen closed tickets?",
                },
                {
                    "from": "in_progress",
                    "to": "closed",
                    "reason": "Spec mentions spam/duplicate tickets need to be closed immediately",
                    "question": "Can support staff close tickets directly without resolving first (for spam)?",
                },
                {
                    "from": "resolved",
                    "to": "in_progress",
                    "reason": "User might reject the resolution",
                    "question": "Can resolved tickets be moved back to in_progress if user disagrees?",
                },
            ],
            "states_without_exit": [],
            "unreachable_states": [],
        }
    ],
    "crud_analysis": [
        {
            "entity": "Ticket",
            "operations_mentioned": {
                "create": {"found": True, "who": "any user"},
                "read": {
                    "found": True,
                    "who": "ticket creator or support staff",
                    "question": "Can admins see all tickets or only assigned ones?",
                },
                "update": {"found": True, "who": "support staff (status changes)"},
                "delete": {
                    "found": False,
                    "question": "Can tickets be deleted, or only closed?",
                },
                "list": {
                    "found": True,
                    "filters_needed": [
                        "status",
                        "priority",
                        "assigned_to",
                        "created_date",
                    ],
                },
            },
            "missing_operations": ["delete"],
        },
        {
            "entity": "User",
            "operations_mentioned": {
                "create": {"found": True, "location": "user registration mentioned"},
                "read": {"found": True},
            },
            "missing_operations": ["update", "delete", "list"],
            "questions": ["Can users edit their profiles?", "Can users be deleted?"],
        },
        {
            "entity": "Comment",
            "operations_mentioned": {
                "create": {"found": True, "who": "ticket creator or support"},
                "read": {"found": True},
            },
            "missing_operations": ["update", "delete", "list"],
            "questions": [
                "Can comments be edited after posting?",
                "Can comments be deleted?",
            ],
        },
    ],
    "business_rules": [
        {
            "type": "validation",
            "entity": "Ticket",
            "field": "title",
            "rule": "Required, max 200 characters",
        },
        {
            "type": "validation",
            "entity": "Ticket",
            "field": "description",
            "rule": "Required, rich text",
        },
        {
            "type": "access_control",
            "entity": "Ticket",
            "rule": "Users can only see their own tickets",
        },
        {
            "type": "access_control",
            "entity": "Ticket",
            "rule": "Support staff can see all tickets",
        },
        {
            "type": "access_control",
            "entity": "Ticket",
            "rule": "Only assigned support staff can change ticket status",
        },
        {
            "type": "cascade",
            "entity": "User",
            "rule": "When user deleted, tickets are NOT deleted (reassigned to 'deleted_user')",
        },
        {
            "type": "cascade",
            "entity": "Ticket",
            "rule": "When ticket deleted (if allowed), comments are also deleted",
        },
    ],
    "clarifying_questions": [
        {
            "category": "State Machine",
            "priority": "high",
            "questions": [
                {
                    "q": "Who can reopen closed tickets?",
                    "context": "Spec mentions reopening but doesn't specify permissions",
                    "options": [
                        "Only admins",
                        "Original ticket creator",
                        "Any support staff",
                    ],
                    "impacts": "Access control logic, state transition validation",
                },
                {
                    "q": "Can support staff close tickets directly (spam/duplicates)?",
                    "context": "Spec mentions spam tickets but doesn't detail the workflow",
                    "options": [
                        "Yes, support can close directly from any state",
                        "No, must mark resolved first",
                        "Only admins can close directly",
                    ],
                    "impacts": "State machine transitions, workflow complexity",
                },
            ],
        },
        {
            "category": "CRUD Completeness",
            "priority": "medium",
            "questions": [
                {
                    "q": "Can users edit their profiles?",
                    "context": "User CRUD update not mentioned in spec",
                    "options": [
                        "Yes, users can edit email/name",
                        "No, profiles are read-only",
                        "Only admins can edit user profiles",
                    ],
                    "impacts": "User surface requirements, validation rules",
                }
            ],
        },
        {
            "category": "Access Control",
            "priority": "high",
            "questions": [
                {
                    "q": "Can admins see all tickets or only assigned ones?",
                    "context": "Spec says 'support staff can see all' but admin scope unclear",
                    "options": [
                        "Admins see everything",
                        "Admins only see assigned tickets",
                        "Admins need explicit permission per ticket",
                    ],
                    "impacts": "List filtering logic, database queries",
                }
            ],
        },
    ],
}


# Sample spec content for testing
SIMPLE_TASK_SPEC = """# Task Manager

I need a simple personal task manager where I can track my to-do items.

## Features

### Task Management
- Create tasks with a title (required, max 200 chars)
- Add optional description
- Set status: To Do, In Progress, Done
- Set priority: Low, Medium, High (default: Medium)

### Task List
- View all my tasks
- See title, status, priority
- Filter by status and priority
- Most recent tasks first

### Task Details
- View full task information
- See when created and last updated

### Edit Tasks
- Update title and description
- Change status (move from To Do → In Progress → Done)
- Change priority

### Delete Tasks
- Remove tasks I don't need anymore
"""


SUPPORT_TICKETS_SPEC = """# Support Ticket System

A help desk system where customers can submit support tickets and support staff can respond.

## User Roles
- **Customer**: Can create and view their own tickets
- **Support Staff**: Can see all tickets, respond, change status
- **Admin**: Full access

## Ticket Lifecycle
Tickets flow through these states:
1. **Open**: Customer creates ticket
2. **In Progress**: Support staff assigns to themselves and starts work
3. **Resolved**: Support staff marks as fixed
4. **Closed**: Customer confirms or auto-close after 7 days

Special cases:
- Spam/duplicate tickets should be closable immediately by support
- Closed tickets can be reopened if issue returns

## Features

### Create Ticket
- Customer fills out:
  - Title (required, max 200 chars)
  - Description (required, rich text)
  - Priority: Low, Medium, High
- Ticket starts in "Open" status

### View Tickets
- Customers see only their tickets
- Support sees all tickets (or only assigned?)
- Admin sees everything

### Update Ticket
- Support can change status
- Support can assign to themselves
- Support can update priority

### Comments
- Both customer and support can add comments
- Comments show timestamp and author
- Can comments be edited? Deleted?

### Notifications
- Email when ticket status changes
- Email when new comment added

## Open Questions
- Can customers delete tickets, or only close them?
- Can users edit their profiles (name, email)?
- When user is deleted, what happens to their tickets?
"""
