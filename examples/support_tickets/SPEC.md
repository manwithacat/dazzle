# Support Tickets System - Product Specification

**Project Type**: Internal Support/Help Desk System
**Target Users**: Small teams (5-20 people) handling customer support or IT tickets
**Deployment**: Multi-user web application

---

## Project Overview

I need a support ticket system for my small team. We're getting overwhelmed with support requests coming through email, Slack, and random conversations. I want a central place where:

- Customers or team members can submit support tickets
- Support staff can see what needs attention
- We can assign tickets to specific people
- Everyone can track the status of their requests
- We can add updates and comments as we work on issues

The system should be simple enough that anyone on the team can use it without training. I don't need a complex enterprise system - just something that helps us stay organized and make sure nothing falls through the cracks.

---

## Core Features

### What I Need to Track

**People in the System (Users)**:
- Name and email address
- Some people submit tickets (customers, team members)
- Some people work on tickets (support staff)
- Some people do both

**Support Tickets**:
- **Title** - Brief description of the problem
- **Description** - Full details about what's wrong
- **Status** - Where it is: New, Being Worked On, Fixed, Closed
- **Priority** - How urgent: Low, Medium, High, Critical
- **Who Created It** - So we know who needs help
- **Who's Working On It** - So we know who's responsible (can be unassigned at first)
- **Timestamps** - When created and last updated

**Comments/Updates**:
- Back-and-forth conversation on each ticket
- Who said what and when
- Running history of what we tried

### User Stories

**As a customer/team member, I want to:**

1. **Submit a support request**
   - Fill out a simple form with my issue
   - Set how urgent it is
   - Get confirmation it was received

2. **Check status of my tickets**
   - See all tickets I've submitted
   - Know if someone's working on it
   - Read any updates from support staff

**As support staff, I want to:**

1. **See all open tickets**
   - View everything that needs attention
   - See which are unassigned (need to be picked up)
   - Identify high priority issues quickly

2. **Pick tickets to work on**
   - Assign unassigned tickets to myself
   - See tickets assigned to me
   - Reassign tickets to other team members if needed

3. **Update ticket status**
   - Move tickets through workflow: New → Working → Fixed → Closed
   - Add comments with updates ("I'm looking into this", "Try this fix")
   - Change priority if situation changes

4. **Work tickets to completion**
   - Add notes as I investigate
   - Update the customer with progress
   - Mark as resolved when done
   - Close tickets that are confirmed fixed

**As a manager, I want to:**

1. **See the big picture**
   - How many open tickets do we have?
   - Who's working on what?
   - Are there unassigned tickets sitting around?
   - What's taking a long time?

---

## Data Model

### User

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| ID | UUID | Yes | Auto-generated |
| Email | Text | Yes | Must be unique (login) |
| Name | Text | Yes | Display name |
| Created | Timestamp | Yes | Auto |

### Ticket

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| ID | UUID | Yes | Auto-generated | Unique identifier |
| Title | Text (max 200) | Yes | - | Brief issue summary |
| Description | Long text | Yes | - | Full problem description |
| Status | Choice | Yes | "Open" | Open, In Progress, Resolved, Closed |
| Priority | Choice | Yes | "Medium" | Low, Medium, High, Critical |
| Created By | Link to User | Yes | - | Who submitted this |
| Assigned To | Link to User | No | Empty | Who's working on it (optional) |
| Created At | Timestamp | Yes | Auto | When submitted |
| Updated At | Timestamp | Yes | Auto | Last change |

### Comment

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| ID | UUID | Yes | Auto-generated |
| Ticket | Link to Ticket | Yes | Which ticket this is on |
| Author | Link to User | Yes | Who wrote it |
| Content | Long text | Yes | The actual comment |
| Created At | Timestamp | Yes | Auto |

---

## User Interface

### Pages I Need

1. **Ticket List** (Main dashboard)
   - Shows all tickets in a table
   - Columns: Title, Status, Priority, Created By, When Created
   - Color coding for priority (red for critical, etc.)
   - Filter options: Show Only Unassigned, Show Only Mine
   - "Create New Ticket" button
   - Click any ticket to see details

2. **Ticket Detail**
   - Full ticket information
   - All comments shown chronologically
   - Who created it, who's assigned
   - Current status and priority
   - Buttons: Edit, Delete, Add Comment
   - Option to change assignment

3. **Create Ticket Form**
   - Fields: Title (required), Description (required), Priority
   - Who created it: filled in automatically
   - Status: automatically "Open"
   - Assigned to: blank (will be assigned by staff)
   - Simple, fast to fill out

4. **Edit Ticket Form**
   - Update title and description
   - Change status (staff can move through workflow)
   - Change priority (if it becomes more/less urgent)
   - Reassign to different person
   - Shows who created it (can't change)

5. **Delete Confirmation**
   - "Are you sure?" page
   - Shows ticket title
   - Warning if there are comments
   - Confirm/Cancel buttons

---

## Workflows

### New Ticket Workflow

1. **Customer submits ticket**
   - Fills out form: "Can't log in to email"
   - Selects Priority: High
   - Submits
   - Ticket created with Status="Open", Assigned To=(empty)

2. **Support staff sees it**
   - Checks ticket list
   - Sees new unassigned ticket
   - Opens details, reads description
   - Assigns to themselves: "I'll handle this"
   - Status changes to "In Progress"

3. **Staff works on it**
   - Investigates the issue
   - Adds comment: "Checking your account settings"
   - Finds the problem
   - Adds comment: "Reset your password, should work now"
   - Changes Status to "Resolved"

4. **Customer confirms**
   - Customer tries it, works!
   - Staff changes Status to "Closed"
   - Ticket done

### Reassignment Workflow

1. Staff member A is assigned ticket
2. A goes on vacation
3. Manager opens ticket, clicks Edit
4. Changes "Assigned To" from A to B
5. B now sees it in their queue
6. B picks up where A left off

### Unassigned Ticket Queue

1. Several tickets come in
2. They're unassigned (no owner yet)
3. Support staff filter by "Unassigned"
4. Pick tickets based on expertise/availability
5. Assign to themselves

---

## What the System Provides Automatically

*These features are built into the generated application!*

### Admin Dashboard
- Manage all users, tickets, and comments
- Search and filter everything
- Bulk operations
- Quick data corrections
- Export data to CSV

### Home Page
- Welcome page with links to:
  - View all tickets
  - Create new ticket
  - Admin dashboard
- Quick stats (# open tickets, etc.)

### Navigation
- Top menu bar with links to main pages
- Mobile-friendly (works on phones)
- Breadcrumb trail ("Home > Tickets > Ticket #123")

### Relationships
- When viewing a ticket, see the user who created it (linked)
- When viewing a ticket, see assigned user (linked)
- Click through to see all tickets created by a user
- Click through to see all tickets assigned to a user

### Data Integrity
- Can't delete a user who has tickets (or tickets become "orphaned")
- Timestamps auto-update when editing
- Comment history preserved forever

---

## Example Scenarios

### Scenario 1: First Day Setup

1. IT creates user accounts for team (5 support staff, 10 team members)
2. Posts link to ticket system on company Slack
3. First ticket arrives: "Printer is jammed"
4. Support tech assigns to himself
5. Fixes printer, adds photo in comment
6. Marks resolved
7. Requester confirms, ticket closed

### Scenario 2: Escalation

1. Junior support gets assigned ticket: "Website is down"
2. Junior realizes it's too complex
3. Adds comment: "Need help, looks like database issue"
4. Manager reassigns to senior engineer
5. Senior engineer investigates
6. Finds problem, fixes it
7. Updates ticket, marks resolved
8. Whole team can see the history of what happened

### Scenario 3: Customer View

1. Customer submits ticket: "Account locked"
2. Gets confirmation "Ticket #42 created"
3. Checks back later - sees status "In Progress"
4. Sees comment from support: "Reset sent to your email"
5. Tries it, works
6. Ticket automatically closes after 24 hours in "Resolved"

---

## Technical Requirements

### Must Have
- Works on phones and tablets (support staff on the go)
- Fast - ticket list loads in under 2 seconds
- Don't lose data (tickets are important!)
- Easy deployment to Heroku or Railway

### Nice to Have
- Visual priority indicators (colors, icons)
- Filter/sort ticket list
- Basic stats on home page
- Email notifications (coming soon)

### Out of Scope (For Version 1)
- Email integration (create ticket from email)
- Customer portal (separate login for customers)
- SLA tracking (response time requirements)
- File attachments
- Mobile apps
- Integrations with Slack/Teams
- Advanced reporting/analytics
- Knowledge base
- Canned responses/templates

---

## Success Criteria

This system is successful if:

1. **We never lose a ticket** - Everything gets recorded and tracked
2. **Average response time under 1 hour** - Someone picks up tickets quickly
3. **Team actually uses it** - They prefer it over email/Slack
4. **Zero training needed** - New team members figure it out immediately
5. **Customers know what's happening** - Transparency into status

---

## Priority Levels Explained

Since we have four priority levels, here's when to use each:

- **Low** - Nice to have, no rush (e.g., "Can we add dark mode?")
- **Medium** - Normal day-to-day issues (e.g., "Can't access shared drive")
- **High** - Impacting work, needs attention today (e.g., "Can't log in")
- **Critical** - Everything's broken, drop everything (e.g., "Website down for all users")

## Status Flow Explained

Tickets move through these states:

1. **Open** - Just submitted, waiting for someone to pick it up
2. **In Progress** - Someone's actively working on it
3. **Resolved** - We think it's fixed, waiting for confirmation
4. **Closed** - Confirmed fixed, ticket done

Note: Tickets can be reopened if the issue comes back (Closed → Open)

---

## Notes for Developer

### Keep It Simple
- Don't overcomplicate the assignment logic - simple dropdown is fine
- Status colors: Open=blue, In Progress=yellow, Resolved=green, Closed=gray
- Priority colors: Critical=red, High=orange, Medium=yellow, Low=gray

### Relationships
- A ticket must have a creator (who submitted it)
- A ticket can be unassigned (assigned_to can be empty)
- Users can create many tickets
- Users can be assigned many tickets
- Comments belong to a ticket and have an author

### Key User Experience Points
- Creating a ticket should take 30 seconds max
- Assigning a ticket should be one click
- The ticket list is the most-used page - make it fast
- Use sensible defaults (Medium priority, Open status)

### Data Rules
- Email addresses must be unique (people can't have duplicate accounts)
- Can't delete a user if they have tickets (or reassign all their tickets first)
- Comments are permanent (no editing or deleting)
- Timestamps update automatically

### Future Features (Not Now)
- Email notifications when assigned or status changes
- Attach screenshots to tickets
- Search across all tickets
- Reports (tickets per person, average resolution time)
- Customer-facing portal
- Integration with email

---

## Questions for the Team

Before building, let's decide:

1. **Who can create tickets?** Everyone? Or just certain users?
2. **Who can assign tickets?** Only managers? Or any support staff?
3. **Can customers see all tickets or just their own?** (For now: everyone sees everything)
4. **What happens to tickets when someone leaves the team?** (Reassign to manager?)
5. **How long do we keep closed tickets?** (Forever? Archive after 90 days?)

---

## Getting Started

Once this is built:

1. **Set up users** - Add your team in the admin
2. **Create test tickets** - Make sure everything works
3. **Train the team** (5 minutes) - Show them how to create and assign tickets
4. **Announce it** - Post the link in Slack
5. **Monitor usage** - Check if tickets are getting picked up
6. **Iterate** - Add features based on what the team needs

This is version 1. We'll improve it based on real usage!
