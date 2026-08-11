# Project Tracker — Specification

## Executive summary

Project Tracker is a team project-management product. It organises work as Projects owned by a team member, broken into Milestones and Tasks, with Comments carrying the conversation, Project Documents (briefs, specs, proposals, status reports, decisions) as named composition buyers scan above the notes trail, and Attachments as binary file evidence on tasks. Everyone on the team shares two working surfaces — a Dashboard for the overview and a Project Board for day-to-day kanban with unassigned and overdue dual attention plus milestones.

Three roles use it — Admin, Project Manager, and Team Member — and what each can see and do is not left to convention. Every role's permissions, for every kind of record and operation, are declared as machine-readable policy that compiles on demand into an auditable access matrix — permission review is something you run and diff, not something you eyeball — and the row-visibility rules can additionally be submitted to an SMT solver for formal verification. Access-controlled records are automatically filtered to what each user is permitted to see: a team member's task list, for instance, shows only the tasks assigned to them.

## What it does

The product manages seven kinds of thing, woven together:

- **Projects** — the top-level containers of work. Every Project has an owning Team Member.
- **Milestones** — staging posts within a Project. Every Milestone belongs to its parent Project and moves through planning, active, and completed states.
- **Tasks** — the units of work. Every Task belongs to a parent Project, can optionally sit under a Milestone, and records who it is assigned to and who created it. A Task travels a five-stage lifecycle from backlog to done.
- **Comments** — the discussion. Every Comment is attached to a Task and names its author. On the Task hub, Discussion renders as a Message/Bubble conversation trail (not a queue of meta rows); Dashboard, My Tasks, and Discussion desk share the same chrome.
- **Project documents** — named project documents (briefs, specs, proposals, status reports, decision logs) with domain-true headlines that buyers scan as composition above the discussion trail.
- **Attachments** — supporting binary files on a Task (PDF exports, mockups) with human filenames.
- **Team Members** — the people, referenced throughout as owners, assignees, authors, and uploaders.

Around these, the product provides the full working surface: browsing, creating, viewing, and editing Projects and Tasks; creating, listing, and editing Milestones and Comments; attaching and browsing Project Documents; and listing, uploading, and viewing Attachments — opening an attachment presents the file in the built-in PDF viewer.

## Who uses it

**Admins** have full access to all projects and settings. They alone can manage the team-member roster, delete projects and milestones, and moderate comments.

**Project Managers** manage projects and assign tasks. They can create and edit Projects and Milestones, see and update every Task, and remove tasks and attachments when needed.

**Team Members** work on assigned tasks. They see all projects, milestones, comments, and attachments, and can create tasks, comment, and upload files — but their task list and their editing rights extend only to Tasks where the assignee is the signed-in user.

Admins and Project Managers land on the **Dashboard**; Team Members land on
the **Project Board**. Both places stay available to everyone with access.

## Where work happens

- **Dashboard** — multi-panel portfolio: teammate **media shelf** headshots first, then task metrics (including document
  count and conversation honesty), dual attention (open-task queue + named
  project-document composition with domain-true headlines) before the live
  discussion trail, then project grid and task-flow kanban (no priority chart
  theater — empty_region honesty; queues capped for fold share).
- **Project Board** — delivery board: board metrics, task kanban, unassigned
  queue, and milestone timeline (status counts live in metrics, not a chart).
- **My Tasks** — multi-panel member desk: load metrics, dual attention
  (assigned queue + status board) before the discussion trail (no twin comment
  dump / priority chart).
- **Milestone Plan** — manager schedule desk: milestone metrics, open
  milestone queue, active project grid, status mix chart, and open-work trail.
- **Discussion** — cross-task comment pulse, one live conversation spine,
  and open-task pull queue (no twin timeline dump, kanban twin, or priority
  chart theater — empty_region honesty, cycle 1924).
- **Files** — document composition desk: project-document pulse and named
  brief/spec composition, tasks needing evidence, and recent file uploads.
- **People** — admin/manager org desk: team pulse, role board (kanban),
  department roster queue, project ownership queue, secondary roster,
  unassigned load, discussion trail, and department headcount chart.
- **Review** — admin/manager review desk: review metrics, review queue,
  pipeline board, comment trail, and open status chart.

## How work flows through it

Work flows through two lifecycles. A **Task** moves from backlog → todo → in progress → review → done — the kanban boards on both workspaces make that journey visible and draggable. A **Milestone** moves from planning → active → completed, marking the larger beats of a Project as its tasks land.

Who advances what is governed by the declared rules: managers and admins can move any task; a team member advances only the tasks assigned to them.

## Automation & controls

**Project lifecycle.** Projects move active ↔ archived (managers archive; admin may reactivate).

One durable process reinforces the review handoff: when a Task enters **review**, a manager review step is required so acceptance is not an informal chat (verify: `dazzle process list`).

## The technical foundation

These guarantees hold because the product is built on Dazzle, and each can be independently verified by running a single command.

**Security.** Access-controlled records are filtered to what each user is permitted to see. The rule is declared once in the model and applied automatically to every query the product runs, instead of being re-implemented — and re-checked — on each screen (verify: `dazzle rbac report`). Every role's permissions, for every kind of record and operation, are declared as machine-readable policy; they compile on demand into an auditable access matrix, and the row-visibility rules can additionally be submitted to an SMT solver for formal verification (verify: `dazzle rbac prove`).

**Data & reliability.** All data is stored in PostgreSQL — a mature, widely-trusted relational database. There is no bespoke or experimental datastore to operate, secure, or reason about (verify: `dazzle db status`). In production, every change to the data model is applied through versioned, reversible migrations; the live schema is never edited by hand, so upgrades are repeatable and fully auditable (verify: `dazzle db status`).

**Architecture.** The interface is rendered on the server and progressively enhanced. There is no heavy single-page JavaScript application to maintain, which keeps the product fast, accessible, and simple to operate (verify: `dazzle validate`).

## Compliance posture

Task attachments are served through an entity-scoped, audited byte-access
boundary: bytes are released only when the same rule that governs the parent
task allows it, and each access is recorded. A static proof holds every
byte-serving route to that boundary, so no new route can stream attachment
bytes outside it without being explicitly listed (verify:
`dazzle rbac byte-routes --strict`).

**Project Document lifecycle.** Project Documents move draft → published → archived (member may publish; manager/admin archive; admin may return published to draft).

<!-- dazzle-spec-brief: sha256:ba4acb9a39d8b8c9fc9e18b9f682f85aa7fd3b459bad3f713cbf9deb0b5e7160 -->
