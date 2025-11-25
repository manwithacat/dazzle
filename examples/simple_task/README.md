# Simple Task Manager Example (v0.2)

**A beginner-friendly DAZZLE example showing how to build a personal task tracking application with the UX Semantic Layer.**

---

## What This Example Demonstrates

This example shows the complete journey from **human specification to working application**:

1. **SPEC.md** - What a founder/builder writes (in plain English)
2. **dsl/app.dsl** - The DAZZLE v0.2 DSL with UX features
3. **Generated Code** - A fully functional Django, Express.js, or Next.js application

### v0.2 UX Features Demonstrated

- **Attention Signals** - Visual alerts for overdue and high-priority tasks
- **Persona Variants** - Different views for team members, managers, and viewers
- **Workspaces** - Dashboard views with multiple data regions
- **Information Needs** - Declarative sort, filter, search, and empty states

---

## 🚀 Quick Start

### Option 1: Use the Example Directly

```bash
# Clone this example to your workspace
dazzle clone simple_task

# Navigate to the directory
cd simple_task

# Validate the DSL
dazzle validate

# Build the application (Django + SQLite)
dazzle build --stack micro

# Run the generated app
cd build/simple_task
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Visit http://localhost:8000
```

### Option 2: Learn by Exploring

```bash
# Read the human specification first
cat SPEC.md

# Then see how it maps to DSL
cat dsl/app.dsl

# Build and explore the generated code
dazzle build --stack micro
```

---

## 📖 The Three-Step Process

### Step 1: Write Your Specification (SPEC.md)

Start by describing your application in plain English:
- What problem does it solve?
- What data do you need to track?
- What actions can users take?
- What pages/screens do you need?

**Example from SPEC.md:**
```
I need a simple task management application where I can keep track
of my to-do items. For each task, I want to store:
- Title (required)
- Description (optional)
- Status (To Do, In Progress, Done)
- Priority (Low, Medium, High)
```

### Step 2: Translate to DAZZLE DSL (app.dsl)

Convert your specification into structured DSL:

**Data Model → Entity:**
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

**User Stories → Surfaces with UX:**
```dsl
# "I want to view all my tasks" - with attention signals and personas
surface task_list "Task List":
  uses entity Task
  mode: list
  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due Date"

  ux:
    purpose: "Track and manage team tasks efficiently"
    sort: status asc, priority desc
    filter: status, priority, assigned_to
    search: title, description
    empty: "No tasks yet. Create your first task!"

    # Visual alerts based on data conditions
    attention critical:
      when: due_date < today and status != done
      message: "Overdue task"

    attention warning:
      when: priority = high and status = todo
      message: "High priority - start soon"

    # Role-specific views
    for team_member:
      scope: assigned_to = current_user
      purpose: "Your personal task list"

    for manager:
      scope: all
      purpose: "Team task oversight"
```

**Dashboards → Workspaces:**
```dsl
# Multi-region dashboard
workspace task_dashboard "Task Dashboard":
  purpose: "Comprehensive task management overview"

  my_tasks:
    source: Task
    filter: assigned_to = current_user and status != done
    sort: priority desc
    limit: 10
    display: list

  overdue:
    source: Task
    filter: due_date < today and status != done
    sort: due_date asc
    display: list
    empty: "No overdue tasks!"
```

### Step 3: Generate Your Application

```bash
# Django (Python)
dazzle build --stack micro

# Express.js (Node.js)
dazzle build --stack express_micro

# Just the API spec
dazzle build --stack openapi_only
```

---

## 🎯 What You Get

### Generated Files (Django Micro Stack)

```
build/simple_task/
├── manage.py                  # Django CLI
├── requirements.txt           # Python dependencies
├── Procfile                   # Heroku deployment
├── simple_task/
│   ├── settings.py           # Configuration
│   ├── urls.py               # URL routing
│   └── wsgi.py               # Web server interface
├── app/
│   ├── models.py             # Task model (from entity)
│   ├── forms.py              # Task forms (from surfaces)
│   ├── views.py              # CRUD views (from surfaces)
│   ├── admin.py              # Admin interface
│   └── templates/            # HTML templates (from surfaces)
│       ├── base.html
│       └── app/
│           ├── home.html
│           ├── task_list.html
│           ├── task_detail.html
│           ├── task_form.html
│           └── task_confirm_delete.html
└── static/
    └── css/
        └── style.css
```

### Features Included

✅ **Database Schema** - SQLite with Task model
✅ **CRUD Operations** - Create, Read, Update, Delete tasks
✅ **List View** - See all tasks with filtering
✅ **Detail View** - View individual task
✅ **Forms** - Create and edit with validation
✅ **Admin Interface** - Django Admin for data management
✅ **Responsive UI** - Works on desktop and mobile
✅ **Deployment Ready** - Heroku, Railway, PythonAnywhere

---

## 🔄 The DSL-to-Code Mapping

| DSL Concept | Becomes in Django | Becomes in Express.js |
|-------------|-------------------|----------------------|
| `entity Task` | `models.Task` class | `models/Task.js` Sequelize model |
| `title: str(200)` | `CharField(max_length=200)` | `DataTypes.STRING(200)` |
| `status: enum[...]` | `CharField` with choices | `DataTypes.STRING` |
| `surface task_list` | `TaskListView` class | `GET /task` route |
| `mode: create` | `TaskCreateView` + form | `POST /task` route |
| `mode: edit` | `TaskUpdateView` + form | `PUT /task/:id` route |
| `field title` in surface | Included in form.fields | Form field in template |

---

## 🧪 Try Modifying the Example

### Add a "Due Date" Field

**1. Update SPEC.md:**
```markdown
- **Due Date** (optional) - When the task should be completed
```

**2. Update app.dsl:**
```dsl
entity Task "Task":
  # ... existing fields ...
  due_date: date  # Add this line
```

**3. Add to surfaces:**
```dsl
surface task_create "Create Task":
  section main "New Task":
    # ... existing fields ...
    field due_date "Due Date"  # Add this line
```

**4. Rebuild:**
```bash
dazzle build --stack micro
```

The new field automatically appears in:
- Database schema (migrations)
- Forms (with date picker)
- Views (display logic)
- Admin interface

---

## 📚 Key Concepts

### Entities
Define your data model. Think: "What nouns/objects does my app track?"
- Products, Orders, Customers (e-commerce)
- Posts, Comments, Users (blog)
- Tasks, Projects (project management)

### Surfaces
Define user interfaces. Think: "What can users do?"
- `list` - Browse multiple records (table view)
- `view` - See details of one record (detail page)
- `create` - Add new records (form)
- `edit` - Update existing records (form)

### Field Types
Map to database columns and form inputs:
- `str(N)` - Short text (VARCHAR)
- `text` - Long text (TEXT)
- `int`, `decimal` - Numbers
- `bool` - True/False
- `date`, `datetime` - Dates and times
- `uuid` - Unique identifiers
- `enum[a,b,c]` - Fixed choices (dropdown)

### Modifiers
Add special behavior:
- `required` - Field cannot be empty
- `pk` - Primary key
- `auto_add` - Set automatically on creation
- `auto_update` - Update automatically on save

---

## 🎓 Learning Path

1. **Read SPEC.md** - Understand the problem
2. **Study app.dsl** - See how specs map to DSL
3. **Build and explore** - See the generated code
4. **Make changes** - Add fields, modify surfaces
5. **Create your own** - Start with `dazzle init`

---

## 🔗 Related Examples

- **support_tickets** - Multi-entity relationships, more complex surfaces
- **api_only** - Generate just the API without UI
- **django_next** - Full-stack with React frontend

---

## ✨ Next Steps

**Want to build your own app?**

```bash
# Start a new project
dazzle init my-app

# Write your SPEC.md (describe what you want)
# Then translate to DSL in dsl/app.dsl

# Validate and build
dazzle validate
dazzle build --stack micro

# Deploy to production
git init
git add .
git commit -m "Initial commit"
heroku create
git push heroku main
```

Happy building! 🚀
