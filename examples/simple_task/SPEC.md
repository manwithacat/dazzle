# Team Task Manager - Product Specification

> **Document Status**: Refined specification ready for DSL conversion
> **Complexity Level**: Intermediate
> **DSL Features Demonstrated**: Multi-entity relationships, personas, scenarios, access control, state machines

---

## Vision Statement

A team task management tool that enables collaboration between administrators, managers, and team members. The app provides role-based dashboards, task assignment workflows, and proper access control to ensure the right people see the right information.

---

## User Personas

### Administrator
- **Role**: System administrator with full access
- **Need**: Manage all tasks and team members across the organization
- **Goals**: Configure team settings, view analytics, ensure data integrity
- **Proficiency**: Expert user comfortable with all features

### Team Manager
- **Role**: Department or project lead
- **Need**: Oversee team tasks and assignments
- **Goals**: Assign work, track team progress, review completed tasks
- **Proficiency**: Intermediate user focused on team coordination

### Team Member
- **Role**: Individual contributor
- **Need**: Work on assigned tasks and track personal progress
- **Goals**: Complete assigned work, update status, request help when blocked
- **Proficiency**: Novice user needing streamlined workflows

---

## Domain Model

### Entity: User (Team Member)

Represents a team member who can be assigned tasks.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `email` | String(200) | Yes | - | Unique, valid email format |
| `name` | String(100) | Yes | - | Display name |
| `role` | Enum | Yes | `member` | Access level: `admin`, `manager`, `member` |
| `department` | String(50) | No | - | Organizational unit |
| `avatar_url` | String(500) | No | - | Profile image URL |
| `is_active` | Boolean | Yes | `true` | Account status |
| `created_at` | DateTime | Yes | Auto | Immutable creation timestamp |

### Entity: Task

A discrete unit of work to be completed by a team member.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `title` | String(200) | Yes | - | Short, actionable description |
| `description` | Text | No | - | Extended details, notes, context |
| `status` | Enum | Yes | `todo` | Workflow: `todo` → `in_progress` → `review` → `done` |
| `priority` | Enum | Yes | `medium` | Urgency: `low`, `medium`, `high`, `urgent` |
| `due_date` | Date | No | - | Target completion date |
| `assigned_to` | Ref(User) | No | - | Team member responsible for task |
| `created_by` | Ref(User) | No | - | Team member who created the task |
| `created_at` | DateTime | Yes | Auto | Immutable creation timestamp |
| `updated_at` | DateTime | Yes | Auto | Last modification timestamp |

**State Machine (Status Transitions)**:
- `todo` → `in_progress`: Requires `assigned_to` to be set
- `in_progress` → `review`: Task ready for review
- `in_progress` → `todo`: Send back to backlog
- `review` → `done`: Approved and complete
- `review` → `in_progress`: Needs more work
- `done` → `todo`: Reopen (admin only)

**Invariants**:
- Urgent priority tasks must have a due date

**Access Control**:
- **Read**: Admin, Manager, or task is assigned to/created by current user
- **Write**: Admin, Manager, or task is assigned to current user

---

## Demo Scenarios

### Scenario: Empty State
**Purpose**: Test onboarding flows with no data
- Admin starts at `/admin`
- Manager starts at `/team`
- Member starts at `/my-work`

### Scenario: Active Sprint
**Purpose**: Mid-sprint with tasks in various states
- Pre-populated with 5 team members and 7 tasks
- Mix of todo, in_progress, review, and done tasks
- Various priority levels to demonstrate attention signals

### Scenario: Overdue Crisis
**Purpose**: Test overdue task handling
- Several tasks with past due dates
- Tests warning indicators and overdue filtering

---

## User Interface Specification

### Surface: Task List

**Purpose**: View and manage all tasks
**Mode**: List with table layout

| Column | Source | Behavior |
|--------|--------|----------|
| Title | `task.title` | Primary identifier, clickable to detail |
| Status | `task.status` | Visual badge (color-coded) |
| Priority | `task.priority` | Visual badge (color-coded) |
| Due Date | `task.due_date` | Formatted date, highlight if overdue |
| Assigned To | `task.assigned_to.name` | User name with avatar |

**Persona Variants**:
- **Admin**: Sees all tasks, full management
- **Manager**: Sees all tasks, can assign to team
- **Member**: Sees only tasks assigned to or created by self

**Attention Signals**:
1. **Warning**: Task is overdue (`due_date < today AND status != done`)
2. **Notice**: Urgent task not started (`priority = urgent AND status = todo`)

---

### Surface: Task Create

**Purpose**: Create a new task
**Mode**: Create form

**Persona Variants**:
- **Admin/Manager**: Can assign to any team member
- **Member**: `assigned_to` field hidden (auto-assigned to self)

---

### Surface: Team Members

**Purpose**: Manage team members (admin-focused)
**Mode**: List with table layout

**Persona Variants**:
- **Admin**: Full team management, can create new members
- **Manager**: Read-only view of team members

---

## Workspace Specification

### Workspace: Admin Dashboard

**Purpose**: System-wide overview and management

**Regions**:
- **Metrics**: Total tasks, by status (todo/in_progress/review/done)
- **Team Metrics**: Total users, active users
- **Urgent Tasks**: Priority = urgent, not done
- **Overdue Tasks**: Past due date, not done

---

### Workspace: Team Overview

**Purpose**: Monitor team progress and workload

**Regions**:
- **Metrics**: Total tasks, in progress, in review, completed today
- **Needs Review**: Tasks awaiting approval
- **Team Workload**: Currently in-progress tasks
- **Unassigned**: Tasks needing assignment

---

### Workspace: My Work

**Purpose**: Personal task view for individual contributors

**Regions**:
- **My In Progress**: Current work items
- **My To Do**: Upcoming tasks
- **My In Review**: Awaiting approval
- **My Completed**: Recent accomplishments

---

## Workflows

Each workflow below corresponds to a user story in `dsl/stories.dsl`. The
clauses are written at the intention level — the DSL stories carry the
specific given/then conditions.

### Administrator workflows
- Administrator creates a new Team Member via the user_create surface
- Administrator creates a new Task on behalf of any Team Member
- Administrator changes Task status across every transition in the
  lifecycle (todo → in_progress → review → done, plus the admin-only
  done → todo rollback)
- Administrator creates a new TaskComment on any Task
- Administrator views all tasks across the organization regardless of
  assignee
- Administrator configures team settings by updating any Team Member's
  role or department
- Administrator views system-wide analytics via the admin dashboard
  workspace

### Team Manager workflows
- Team Manager views all tasks for their team via the team_overview
  workspace
- Team Manager views unassigned tasks and assigns them to a Team Member
- Team Manager reviews completed tasks in the review queue and approves
  or sends back

### Team Member workflows
- Team Member views only their own tasks (assigned or created) in the
  my_work workspace
- Team Member updates own task status through the declared state machine

---

## Technical Notes

### DSL Features Demonstrated
- **Multi-entity relationships**: `ref User` for assigned_to/created_by
- **Personas**: Role-based UI variants (admin, manager, member)
- **Scenarios**: Demo data states for testing
- **State machine**: Controlled status transitions
- **Invariants**: Business rule enforcement
- **Access control**: Row-level security based on user role
- **Attention signals**: Visual alerts for overdue/urgent tasks

### Dev Mode Integration
The development environment includes a dev control plane for:
- Switching between personas to test role-based views
- Loading different scenarios to test data states
- Resetting/regenerating demo data

---

*This specification is designed to be converted to DAZZLE DSL. See `dsl/app.dsl` for the implementation.*
