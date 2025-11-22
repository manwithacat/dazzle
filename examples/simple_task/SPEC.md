# Simple Task Manager - Product Specification

**Project Type**: Personal Productivity Tool
**Target Users**: Individual users who need to track their tasks
**Deployment**: Single-user web application

---

## Project Overview

I need a simple task management application where I can keep track of my to-do items. Nothing fancy - just a straightforward way to create tasks, mark their status, and set priorities. I want to be able to see all my tasks at a glance, view details when needed, and mark tasks as complete when I finish them.

The app should be easy to deploy and run on platforms like Heroku or Railway without complex setup. I don't need multi-user features or team collaboration - this is just for my personal use.

---

## Core Features

### What I Need to Track

For each task, I want to store:
- **Title** (required) - A short name for the task (e.g., "Buy groceries", "Fix the bug")
- **Description** (optional) - More details about what needs to be done
- **Status** - Where the task is in my workflow: "To Do", "In Progress", or "Done"
- **Priority** - How important it is: Low, Medium, or High
- **Timestamps** - When I created the task and when I last updated it

### User Stories

**As a user, I want to:**

1. **View all my tasks**
   - See a list of all tasks with their title, status, and priority
   - Quickly scan what needs to be done
   - Have the most recent tasks appear first

2. **Create new tasks**
   - Enter a title (required)
   - Optionally add a description
   - Set an initial priority (defaults to Medium)
   - Task starts in "To Do" status automatically

3. **View task details**
   - Click on a task to see all information
   - See the full description
   - Check when it was created and last updated

4. **Edit existing tasks**
   - Update the title and description
   - Change the status (move from To Do → In Progress → Done)
   - Adjust the priority

5. **Delete tasks**
   - Remove tasks I no longer need
   - Get a confirmation before deleting to prevent accidents

---

## Data Model

### Task Object

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| ID | UUID | Yes | Auto-generated | Unique identifier |
| Title | Text (max 200 chars) | Yes | - | Short description |
| Description | Long text | No | - | Detailed information |
| Status | Choice | Yes | "To Do" | Options: To Do, In Progress, Done |
| Priority | Choice | Yes | Medium | Options: Low, Medium, High |
| Created At | Timestamp | Yes | Auto | When task was created |
| Updated At | Timestamp | Yes | Auto | Last modification time |

---

## User Interface

### Pages I Need

1. **Task List Page** (Home/Main page)
   - Table showing: Title, Status, Priority
   - "Create New Task" button at the top
   - Actions for each task: View, Edit, Delete
   - Most recent tasks shown first

2. **Task Detail Page**
   - Display all fields in a readable format
   - Show full description
   - Show creation and update timestamps
   - Buttons: Edit, Delete, Back to List

3. **Create Task Form**
   - Fields: Title (required), Description (optional), Priority
   - Status automatically set to "To Do"
   - Save button returns to task list

4. **Edit Task Form**
   - Fields: Title, Description, Status, Priority
   - Save button returns to task list
   - Cancel option to go back without saving

5. **Delete Confirmation**
   - "Are you sure?" message
   - Shows task title being deleted
   - Confirm and Cancel buttons

---

## What the System Provides Automatically

*These features are built into the generated application - you don't need to ask for them!*

### Admin Dashboard
A powerful admin interface is automatically generated with:
- Browse all tasks in a data table
- Search and filter capabilities
- Bulk actions (delete multiple items)
- Direct database editing
- Data export
- **Access**: Available in the navigation bar and home page

### Home Page
A central hub that shows:
- Quick access to all your resources (Tasks)
- Links to create new items
- Admin dashboard access
- System status

### Navigation
Automatic navigation menu with:
- Links to all your main pages (Task List, etc.)
- Admin interface link
- Mobile-responsive hamburger menu

### Data Persistence
- SQLite database (included)
- Automatic migrations when you change fields
- Data backup capabilities via admin

### Deployment Support
- One-click deployment configs for Heroku, Railway, Vercel
- Environment variable management
- Production-ready settings

---

## Technical Requirements

### Must Have
- Works on desktop and mobile browsers
- Fast page loads
- Data persists when I close the browser
- Simple deployment (one-click if possible)

### Nice to Have
- Basic styling (doesn't need to be fancy)
- Admin interface for data management
- Pagination if I have lots of tasks

### Out of Scope (for now)
- User authentication (single user only)
- Task sharing or collaboration
- Due dates or reminders
- Categories or tags
- File attachments
- Search functionality
- Mobile apps

---

## Example Scenarios

### Creating My First Task
1. Open the app - see empty task list
2. Click "Create New Task"
3. Enter: "Buy milk" (title)
4. Select priority: High
5. Click Save
6. Return to list - see my new task with status "To Do"

### Completing a Task
1. Find task in list: "Buy milk"
2. Click Edit
3. Change status from "To Do" to "Done"
4. Click Save
5. Return to list - see task marked as Done

### Managing Multiple Tasks
1. Create several tasks
2. See them all in the list
3. Quickly identify high priority items
4. Track what's in progress vs. done

---

## Success Criteria

This app is successful if:
- I can create a task in under 10 seconds
- I can see my entire task list at a glance
- I never lose my task data
- The app "just works" without configuration
- I can deploy it for free on a cloud platform

---

## Notes for Developer

- Keep it simple - I'd rather have it working quickly than have lots of features
- Use sensible defaults (Medium priority, To Do status)
- Make the status and priority dropdowns easy to use
- Timestamps should be automatic - I don't want to enter them manually
- Use standard web technologies that are easy to maintain
