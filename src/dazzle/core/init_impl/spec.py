"""
SPEC.md template generation.

Creates the product specification template to guide founders in defining their project.
"""

from __future__ import annotations

from pathlib import Path


def create_spec_template(target_dir: Path, project_name: str, title: str) -> None:
    """
    Create a SPEC.md template file to guide founders in defining their project.

    Args:
        target_dir: Project directory
        project_name: Project name
        title: Human-readable project title
    """
    spec_path = target_dir / "SPEC.md"

    spec_content = f"""# {title} - Product Specification

**Project Type**: _[e.g., Personal Tool, Team App, Customer Portal]_
**Target Users**: _[Who will use this? Be specific!]_
**Deployment**: _[Single-user, Multi-user, Public-facing]_

---

## Project Overview

_Describe your project in 2-3 sentences from a founder's perspective._

I need a [type of application] that helps [target users] to [main goal].
The key problem I'm solving is [problem statement].
Users should be able to [primary actions] with minimal friction.

**Example**:
> I need a simple task management application where I can keep track of my to-do items. Nothing fancy - just a straightforward way to create tasks, mark their status, and set priorities. I want to be able to see all my tasks at a glance, view details when needed, and mark tasks as complete when I finish them.

---

## Core Features

### What I Need to Track

_List the main "things" (entities/objects) in your system._

**[Entity Name]** (e.g., Task, User, Order, Ticket):
- **[Field Name]** (required/optional) - Brief description
- **[Field Name]** (required/optional) - Brief description
- **Status/State** - List possible values (e.g., "Draft, Active, Complete")
- **Timestamps** - Created, Updated, etc.

**Example**:
> **Task**:
> - **Title** (required) - Short name for the task
> - **Description** (optional) - Detailed information
> - **Status** - To Do, In Progress, Done
> - **Priority** - Low, Medium, High
> - **Created At** - Auto-timestamp

### User Stories

**As a [user type], I want to:**

1. **[Action/Goal]**
   - [Specific detail about what this enables]
   - [Why this is important]
   - [Expected result]

2. **[Action/Goal]**
   - [Details...]

**Example**:
> **As a user, I want to:**
>
> 1. **View all my tasks**
>    - See a list of all tasks with their title, status, and priority
>    - Quickly scan what needs to be done
>    - Have the most recent tasks appear first
>
> 2. **Create new tasks**
>    - Enter a title (required)
>    - Optionally add a description
>    - Set an initial priority (defaults to Medium)

---

## User Interface

### Pages I Need

1. **[Page Name]** (e.g., Task List, Home Dashboard)
   - Shows: [What data/information]
   - Actions: [What users can do]
   - Features: [Filters, sorting, etc.]

2. **[Page Name]** (e.g., Create Form, Detail View)
   - Purpose: [Why users come here]
   - Fields: [What they fill out or see]
   - Next step: [Where they go after]

**Example**:
> 1. **Task List Page**
>    - Shows: All tasks in a table (Title, Status, Priority)
>    - Actions: Create new task, Edit, Delete, View details
>    - Features: Sort by date, Filter by status

---

## What the System Provides Automatically

_These features are built into DAZZLE-generated applications - you don't need to ask for them!_

### Admin Dashboard
A powerful admin interface is automatically generated with:
- Browse all your data in tables
- Search and filter capabilities
- Bulk actions (delete multiple items)
- Direct database editing
- Data export
- **Access**: Available in navigation and home page

### Home Page
A central hub that shows:
- Quick access to all your resources
- Links to create new items
- Admin dashboard access
- System status

### Navigation
Automatic navigation menu with:
- Links to all main pages
- Admin interface link
- Mobile-responsive design (hamburger menu on phones)

### Data Persistence
- Database with automatic migrations
- Data persists when you close the browser
- Timestamps auto-update when editing
- Relationships between entities maintained

### Deployment Support
- One-click deployment configs for Heroku, Railway, Vercel
- Environment variable management
- Production-ready settings
- SQLite for development, easy migration to PostgreSQL

---

## Example Scenarios

_Write 2-3 concrete examples of how someone would use your application._

### Scenario 1: [Common Use Case]

1. User does [action]
2. System shows [result]
3. User then [next action]
4. Final outcome: [what's achieved]

**Example**:
> ### Scenario 1: Creating My First Task
>
> 1. Open the app - see empty task list
> 2. Click "Create New Task"
> 3. Enter: "Buy groceries" (title)
> 4. Select priority: High
> 5. Click Save
> 6. Return to list - see my new task with status "To Do"

---

## Success Criteria

_How will you know this project is successful?_

This app is successful if:
- [Measurable outcome 1]
- [User experience goal 2]
- [Technical goal 3]
- [Adoption/usage goal 4]

**Example**:
> This app is successful if:
> - I can create a task in under 10 seconds
> - I can see my entire task list at a glance
> - I never lose my task data
> - The app "just works" without configuration
> - I can deploy it for free on a cloud platform

---

## Technical Requirements

### Must Have
- Works on desktop and mobile browsers
- Fast page loads
- Data persists across sessions
- Easy deployment

### Nice to Have
- [Feature that would be great but not essential]
- [Enhancement for later]

### Out of Scope (For Version 1)
_Important: List what you explicitly DON'T need for the first version._

- User authentication (if single-user)
- Advanced search
- File attachments
- Email notifications
- Mobile apps
- API access

---

## Notes for Development

### Keep It Simple
- I'd rather have it working quickly than have lots of features
- Use sensible defaults wherever possible
- Automatic timestamps - I don't want to enter dates manually
- Standard web technologies that are easy to maintain

### Data Relationships
_If your entities relate to each other, describe how:_

- [Entity A] can have many [Entity B] (one-to-many)
- [Entity X] must have a [Entity Y] (required relationship)
- [Entity M] can optionally link to [Entity N]

**Example**:
> - A User can create many Tasks (one-to-many)
> - Every Task must have a creator (required)
> - Tasks can be assigned to a User (optional)

### Priority Guidance
_If using priority/status fields, explain what they mean:_

**Status Options**:
- [Option 1] - When to use this
- [Option 2] - When to use this

**Priority Levels**:
- [Level 1] - Example situations
- [Level 2] - Example situations

---

## Working with AI Assistants to Build This

_Tips for collaborating with LLM agents to turn this spec into DAZZLE DSL:_

### Getting Started

1. **Share this SPEC.md** with your AI assistant (Claude, ChatGPT, etc.)

2. **Ask the AI to help translate** your requirements into DAZZLE DSL:
   - "Based on my SPEC.md, help me create the entity definitions in DAZZLE DSL"
   - "What fields should I define for the [Entity] entity?"
   - "How do I express the relationship between [Entity A] and [Entity B]?"

3. **Iterate on the DSL**:
   - Start with one entity to get the pattern right
   - Add fields incrementally
   - Test with `dazzle validate` frequently
   - The AI can help debug validation errors

4. **Build and refine**:
   - Run `dazzle build` to see your application
   - Show the AI what was generated
   - Discuss what needs to be adjusted
   - Update the DSL based on feedback

### Helpful Prompts for AI

- "Review my entity definitions - are there any missing required fields?"
- "I want users to be able to [action] - what surfaces do I need to define?"
- "The validation is failing - can you help me understand this error?"
- "How do I make [field] optional instead of required?"
- "I need a dropdown field with options [A, B, C] - how do I define that in DSL?"

### What to Show the AI

✅ **DO share**:
- This SPEC.md file
- Your DSL files (dsl/*.dsl)
- Validation errors from `dazzle validate`
- Generated code if you have questions about behavior

❌ **DON'T stress about**:
- Perfect DSL syntax on first try - iterate!
- Getting every field right immediately
- Knowing all DAZZLE features upfront

### Example Conversation Flow

> **You**: "I've created a SPEC.md for a task management app. Can you help me create the DAZZLE DSL?"
>
> **AI**: "I'll help! Based on your spec, let's start with the Task entity. Here's a first draft..."
>
> **You**: "Great! How do I make the description optional?"
>
> **AI**: "Remove the 'required' keyword from that field..."
>
> **You**: [runs `dazzle validate`] "I'm getting an error about the status field"
>
> **AI**: "That error means... try changing it to..."

---

## Next Steps

1. **Fill out this template** with your project requirements
2. **Share with your AI assistant** to create DAZZLE DSL together
3. **Run `dazzle validate`** to check your DSL
4. **Run `dazzle build`** to generate your application
5. **Test and iterate** - update DSL based on what you see

**Remember**: Start simple! You can always add more features later. Better to have a working v1 than a perfect plan that never ships. 🚀
"""

    spec_path.write_text(spec_content)
