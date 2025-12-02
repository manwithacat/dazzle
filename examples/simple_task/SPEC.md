# Simple Task Manager - Product Specification

> **Document Status**: Refined specification ready for DSL conversion
> **Complexity Level**: Beginner
> **DSL Features Demonstrated**: Entity basics, CRUD surfaces, workspaces, attention signals

---

## Vision Statement

A personal task management tool that helps individuals track their to-do items with clear priorities and status tracking. The app provides an at-a-glance dashboard for managing daily work without the complexity of team collaboration features.

---

## User Personas

### Primary: Solo Professional
- **Role**: Individual contributor (developer, designer, freelancer)
- **Need**: Quick capture and tracking of work items
- **Pain Point**: Existing tools are too complex or team-focused
- **Goal**: Zero-friction task management that "just works"

---

## Domain Model

### Entity: Task

A discrete unit of work to be completed.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `title` | String(200) | Yes | - | Short, actionable description |
| `description` | Text | No | - | Extended details, notes, context |
| `status` | Enum | Yes | `todo` | Workflow state: `todo` → `in_progress` → `done` |
| `priority` | Enum | Yes | `medium` | Urgency level: `low`, `medium`, `high` |
| `due_date` | Date | No | - | Target completion date |
| `assigned_to` | String(100) | No | - | Person responsible (free text) |
| `created_at` | DateTime | Yes | Auto | Immutable creation timestamp |
| `updated_at` | DateTime | Yes | Auto | Last modification timestamp |

**Validation Rules**:
- Title must not be empty
- Status transitions: Any status can move to any other (flexible workflow)
- Due date must be a valid date (no time component)

---

## User Interface Specification

### Surface: Task List (Primary View)

**Purpose**: View and manage all tasks at a glance

**Mode**: List with table layout

| Column | Source | Behavior |
|--------|--------|----------|
| Title | `task.title` | Primary identifier, clickable to detail |
| Status | `task.status` | Visual badge (color-coded) |
| Priority | `task.priority` | Visual badge (color-coded) |
| Due Date | `task.due_date` | Formatted date, highlight if overdue |
| Assigned To | `task.assigned_to` | Text |

**Interactions**:
- **Sort**: By creation date (newest first), sortable by any column
- **Filter**: By status, by priority
- **Search**: Title, description, assigned_to fields
- **Actions**: View detail, Edit, Delete (with confirmation)

**Empty State**: "No tasks yet. Create your first task to get started!"

**Attention Signals**:
1. **Warning** (orange): Task is overdue (`due_date < today AND status != done`)
   - Message: "Overdue task"
2. **Notice** (blue): High priority task not started (`priority = high AND status = todo`)
   - Message: "High priority - needs attention"

---

### Surface: Task Detail (Read-only View)

**Purpose**: View complete task information

**Mode**: Single record view

**Fields Displayed**:
- Title (heading)
- Description (full text, markdown supported)
- Status (badge)
- Priority (badge)
- Due Date (formatted)
- Assigned To (text)
- Created (relative timestamp: "2 days ago")
- Updated (relative timestamp)

**Actions**: Edit, Delete, Back to List

---

### Surface: Create Task (Form)

**Purpose**: Add a new task to track

**Mode**: Create form

**Fields**:
| Field | Input Type | Required | Default |
|-------|------------|----------|---------|
| Title | Text input | Yes | - |
| Description | Textarea | No | - |
| Priority | Dropdown | No | Medium |
| Due Date | Date picker | No | - |
| Assigned To | Text input | No | - |

**Note**: Status is automatically set to `todo` and not shown in form.

**Actions**: Save (returns to list), Cancel

---

### Surface: Edit Task (Form)

**Purpose**: Update task details and status

**Mode**: Edit form

**Fields**: Same as Create, plus:
| Field | Input Type | Required |
|-------|------------|----------|
| Status | Dropdown | Yes |

**Actions**: Save, Cancel, Delete

---

## Workspace Specification

### Workspace: Task Dashboard

**Purpose**: Overview of all tasks with key metrics and filtered views

**Layout**: Command center with metrics header + multiple data regions

**Regions**:

#### Metrics Bar
| Metric | Calculation | Display |
|--------|-------------|---------|
| Total | `count(Task)` | Number |
| To Do | `count(Task where status = todo)` | Number + badge |
| In Progress | `count(Task where status = in_progress)` | Number + badge |
| Done | `count(Task where status = done)` | Number + badge |

#### Overdue Tasks
- **Source**: Task
- **Filter**: `due_date < today AND status != done`
- **Sort**: `due_date ASC` (most overdue first)
- **Limit**: 5 items
- **Empty**: "No overdue tasks!"
- **Action**: Click → Edit Task

#### High Priority
- **Source**: Task
- **Filter**: `priority = high AND status != done`
- **Sort**: `due_date ASC`
- **Limit**: 5 items
- **Empty**: "No high priority tasks pending"
- **Action**: Click → Edit Task

#### Recent Activity
- **Source**: Task
- **Sort**: `created_at DESC`
- **Limit**: 10 items
- **Action**: Click → Task Detail

---

### Workspace: My Work

**Purpose**: Personal task view organized by workflow stage

**Layout**: Three-column kanban-style view

**Regions**:

#### In Progress
- **Filter**: `status = in_progress`
- **Sort**: `priority DESC, due_date ASC`
- **Limit**: 10 items
- **Empty**: "No tasks in progress"

#### To Do
- **Filter**: `status = todo`
- **Sort**: `priority DESC, due_date ASC`
- **Limit**: 10 items
- **Empty**: "No pending tasks"

#### Recently Completed
- **Filter**: `status = done`
- **Sort**: `updated_at DESC`
- **Limit**: 5 items
- **Empty**: "No completed tasks yet"

---

## User Stories & Acceptance Criteria

### US-1: Create a Task
**As a** user
**I want to** quickly create a new task
**So that** I can capture work items before I forget them

**Acceptance Criteria**:
- [ ] Can access "Create Task" from task list
- [ ] Only title is required
- [ ] Priority defaults to Medium
- [ ] Status automatically set to "To Do"
- [ ] After save, return to task list showing new task
- [ ] Task appears at top of list (sorted by created_at DESC)

**Test Flow**:
```
1. Navigate to task list
2. Click "Create Task" button
3. Enter title: "Buy groceries"
4. Select priority: High
5. Click Save
6. Verify: Redirected to task list
7. Verify: "Buy groceries" appears in list with status "To Do"
```

---

### US-2: View Task Details
**As a** user
**I want to** see all information about a task
**So that** I can understand the full context

**Acceptance Criteria**:
- [ ] Click task title in list → opens detail view
- [ ] All fields displayed with labels
- [ ] Timestamps shown in readable format
- [ ] Can navigate back to list
- [ ] Can edit or delete from detail view

---

### US-3: Update Task Status
**As a** user
**I want to** change a task's status
**So that** I can track my progress

**Acceptance Criteria**:
- [ ] Can change status via Edit form
- [ ] Status change updates `updated_at` timestamp
- [ ] Task moves to correct section in "My Work" workspace

**Test Flow**:
```
1. Navigate to task list
2. Find task "Buy groceries"
3. Click Edit
4. Change status from "To Do" to "In Progress"
5. Click Save
6. Navigate to "My Work" workspace
7. Verify: Task appears in "In Progress" section
```

---

### US-4: Track Overdue Tasks
**As a** user
**I want to** see which tasks are overdue
**So that** I can prioritize catching up

**Acceptance Criteria**:
- [ ] Overdue tasks shown in dashboard "Overdue Tasks" region
- [ ] Overdue tasks have warning indicator in task list
- [ ] Completed tasks never shown as overdue (even if past due date)

---

### US-5: Delete a Task
**As a** user
**I want to** remove tasks I no longer need
**So that** my list stays clean

**Acceptance Criteria**:
- [ ] Delete button available in task detail and edit views
- [ ] Confirmation required before deletion
- [ ] After deletion, return to task list
- [ ] Deleted task no longer appears anywhere

---

## Technical Notes

### DSL Features Demonstrated
- **Entity**: Single entity with various field types (uuid, str, text, enum, date, datetime)
- **Field modifiers**: `required`, `pk`, `auto_add`, `auto_update`, default values
- **Surfaces**: All four CRUD modes (list, view, create, edit)
- **UX block**: purpose, sort, filter, search, empty, attention signals
- **Workspaces**: Multiple regions with aggregations, filters, and limits
- **Attention signals**: Warning and notice levels with conditional expressions

### Out of Scope (Beginner Example)
- Multi-user authentication
- Task categories/tags
- File attachments
- Recurring tasks
- Task dependencies
- Comments/activity log
- Email notifications

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Task creation time | < 10 seconds | Time from click "Create" to saved |
| Page load time | < 2 seconds | Initial list render |
| Mobile usability | Responsive | Works on 375px width |
| E2E test pass rate | 100% | All user stories validated |

---

*This specification is designed to be converted to DAZZLE DSL. See `dsl/app.dsl` for the implementation.*
