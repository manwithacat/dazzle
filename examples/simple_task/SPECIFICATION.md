# Team Task Manager — Specification

## Executive summary

Team Task Manager is a task-tracking system for teams: work is captured as
Tasks, assigned to Team Members, discussed in threaded comments, and moved
through an explicit lifecycle from *todo* to *done*. Three roles use it —
Administrators, Team Managers, and Team Members — each seeing exactly the work
that concerns them.

Two guarantees stand out. First, who can see what is declared once in the
model and enforced automatically on every query: a Team Member sees only the
tasks assigned to them or created by them, while managers and administrators
see the whole board. Second, every role's permissions compile into an
auditable access matrix that can be reviewed, diffed, and even formally
verified — permission review is something you run, not something you eyeball.

## What it does

The system manages three kinds of things. A **Team Member** is a person with
an account who can create and be assigned tasks within an organisation. A
**Task** is a unit of work assigned to a Team Member, with a lifecycle that
runs from todo through review to done; every task carries links to the Team
Member it is assigned to and the Team Member who created it. A **Task
Comment** is a discussion note attached to a task by a Team Member to capture
context or decisions — each comment is always tied to its task and its author.

## Who uses it

**Administrators** have full system access for task and user management. They
aim to manage all tasks, configure team settings, and view analytics. They
land on the **Admin Dashboard** — task and team metrics plus urgent and
overdue work queues — and also use the Task Board and Team Overview. They
alone can add, change, or remove Team Member accounts.

**Team Managers** oversee team tasks and assignments — assigning work,
tracking progress, and reviewing completed work. They land on **Team
Overview**: team metrics and review, unassigned, and in-progress queues —
not a flat dump of every task. Like administrators, they can see every task
and every Team Member.

**Team Members** work on assigned tasks: completing them, updating status,
and requesting help. They land on **My Work** — personal metrics and WIP/todo
queues, with completed history as a list. A Team Member sees only tasks where
they are the assignee or the creator, and can update only those.

## Where work happens

Work is organised into job-shaped workspaces. The **Task Board** — shared by
all three roles — has board metrics, a kanban of tasks, due timeline, urgent
queue, status chart, and comment trail. The **Admin Dashboard** is the
administrator home: metrics for tasks and users, plus urgent and overdue
queues. The **Team Overview** is the manager home: metrics, flow chart, review
queue, and team roster. **My Work** is each person's assigned pressure strip,
personal board, and due timeline. **Discussion** is the comment desk with
trail, active cards, and status chart. **People** is the roster and capacity
desk with unassigned queue, in-flight board, and load chart.

## How work flows through it

A Task moves through a declared lifecycle: **todo → in progress → review →
done**, with the option to send work back from in progress to todo. Fifteen
authored scenarios pin these flows down; representative ones:

- When a Team Manager assigns a task, the task's assignee is set and the Team
  Member sees it appear in their My Work view.
- When a Team Member updates their own task's status, it transitions through
  the declared lifecycle and the change is timestamped.
- When a Team Manager reviews completed work, they see the review queue sorted
  by most recently updated and can approve a task to done or send it back to
  in progress.
- When a Team Manager looks for unassigned work, they see the tasks with no
  assignee and can click one to assign it.
- When an Administrator views system-wide analytics, they see aggregate task
  counts by status and team velocity metrics.

## Automation & controls

Several things run without a human. Three processes react to task changes:
high-priority tasks are auto-assigned, overdue tasks are escalated, and urgent
tasks go through an approval step. Two schedules keep the rhythm — a daily
overdue-task check every morning at 9, and a weekly team report every Monday.

Four AI-assisted steps help along the way: suggesting a priority level from a
task's title and description, suggesting relevant tags, summarising a task's
comment thread, and estimating the effort a task will need.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see; the rule is declared once in the model and applied
automatically to every query the framework runs, instead of being
re-implemented — and re-checked — on each screen (verify:
`dazzle rbac report`). Every role's permissions, for every kind of record and
operation, are declared as machine-readable policy that compiles on demand
into an auditable access matrix, and the visibility rules can additionally be
submitted to an SMT solver for formal verification (verify:
`dazzle rbac prove`).

**Data & reliability.** All data lives in PostgreSQL — a mature,
widely-trusted relational database, with no bespoke or experimental datastore
to operate, secure, or reason about (verify: `dazzle db status`). In
production, every change to the data model is applied through versioned,
reversible migrations; the live structure is never edited by hand, so
upgrades are repeatable and fully auditable (verify: `dazzle db status`).

**Architecture.** The interface is rendered on the server and progressively
enhanced — no heavy single-page JavaScript application to maintain, which
keeps the product fast, accessible, and simple to operate (verify:
`dazzle validate`). Significant business moments are modelled as first-class
events with formally-defined semantics, giving a precise, auditable record of
what happened and when (verify: `dazzle specs asyncapi`). Long-running and
scheduled work is executed by a built-in background engine coordinated
through the database itself — no separate queue infrastructure to deploy, and
an interrupted run is picked up rather than lost (verify:
`dazzle process list`). Finally, the AI-assisted steps are declared in the model — each with
an explicit trigger, prompt contract, and timeout — rather than ad-hoc calls
buried in code, so what the AI is allowed to touch is reviewable in one place
(verify: `dazzle validate`).

<!-- dazzle-spec-brief: sha256:7778f58d150af74ad78cbacdaaa57b06f56d2e6b3652db84885e8bd8772da693 -->
