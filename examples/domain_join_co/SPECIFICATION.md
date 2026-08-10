# Domain Join Co — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

Domain Join Co is a workspace system built around verified-domain membership:
a company's workspace is anchored to its verified email domain, employees join
under it, and everything the team shares stays inside that boundary. The
system manages four things — the Workspace itself, the root under which a
company operates and where members and their roles are declared;
Announcements, the tenant-scoped posts a workspace admin publishes to keep the
team informed; Workspace Documents, named briefs, onboarding guides, join
playbooks, policies, and decision logs buyers scan above the discussion trail;
and Workspace Members, joined staff with department and job title so the Team
desk shows org shape (title kanban + department queue) before a flat roster or
board load — peer directory tools (Okta / Google Workspace Admin / Microsoft
Entra / Rippling) place people after domain join the same way.

Two kinds of people use it: the workspace admin, who verifies the company
domain, sets the join policy, approves join requests, and posts announcements;
and team members, who join with a verified company email and read what the
admin publishes. Who can see and do what is declared in the model and enforced
on every query — verifiable at any time with `dazzle rbac report`.

## What it does

**Workspace.** The root a company joins under — its verified-domain home.
Members and their roles are declared on the workspace itself, so joining the
workspace is what grants access to everything inside it.

**Announcement.** A team post scoped to its workspace: readable by any joined
member, authored by the admin. Every announcement belongs to exactly one
workspace, and its visibility follows that ownership — it exercises precisely
the access that a verified-domain join unlocks.

An Announcement moves draft -> published -> archived under admin control; published posts may return to draft for edits, and archived posts may be republished.

Announcements can be listed, read in detail, and posted through three
dedicated screens.

**Workspace Document.** A named letter on a workspace — brief, onboarding
guide, join playbook, policy, or decision — with domain-true headlines so team
homes surface composition before discussion notes. Documents are tenant-scoped
to their workspace and dual-open to the workspace hub.

**Workspace Member.** A joined staff row on a workspace — name, email,
department, and job title so admins and members read IT / People Ops /
Security / Facilities placement and title columns before the announcement
board. Staff rows are tenant-scoped and dual-open to the workspace hub.

## Who uses it

- **Workspace Admin** — owns one workspace. Their aims: verify the company
  domain, approve the right joiners, and keep the team informed. Admins are
  the only role that can post or edit announcements.
- **Team Member** — an employee who self-joined with a verified company
  email. Their aims: join their company workspace and stay up to date. Members
  read the team's announcements; within the current workspace, announcements
  are visible to admins and members alike.

## Where work happens

- **Workspace Home** — multi-panel admin landing: team pulse, announcement
  queue and join-readiness dual attention, workspace document composition, then
  live discussion in Message chrome, board timeline, and tenant roots (no
  duplicate board dumps or empty chart theater).
- **Team** — org structure desk: joined staff by job title (kanban) and
  department placement before flat roster and board load (org_structure Goal B).
- **Team Board** — multi-panel member home: board pulse, post feed and
  join-context dual attention, workspace document composition, then live
  discussion in Message chrome and post trail — without twin empty queues or
  workspace voids.
- **Publish** — admin publish desk: draft-only queue, published live cards,
  readiness strip, and publish trail (no empty posts chart).
- **Announcement hub** — lifecycle strip (title, status, workspace) plus body
  and team discussion.
- **Workspace hub** — identity strip, related announcements, workspace
  documents, and joined staff as pull queues.
- **Workspace Document hub** — named letter with kind, status, workspace, and
  body for briefs, playbooks, and policies.
- **Workspace Member hub** — joined staff strip with title, department, email,
  and workspace placement.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see — an announcement is visible only when its workspace is the
current one. The rule is declared once in the model and applied automatically
to every query the framework runs, instead of being re-implemented — and
re-checked — on each screen. (Verify: `dazzle rbac report`.) Every role's
permissions, for every record type and operation, are declared as
machine-readable policy that compiles on demand into an auditable access
matrix — so permission review is something you run and diff, not something you
eyeball — and the row-visibility rules can additionally be submitted to an SMT
solver for formal verification. (Verify: `dazzle rbac prove`.)

**Data & reliability.** All data is stored in PostgreSQL — a mature,
widely-trusted relational database, with no bespoke or experimental datastore
to operate, secure, or reason about. (Verify: `dazzle db status`.) In
production, every change to the data model is applied through versioned,
reversible migrations; the live schema is never edited by hand, so upgrades
are repeatable and fully auditable. (Verify: `dazzle db status`.)

**Architecture.** The interface is rendered on the server and progressively
enhanced. There is no heavy single-page JavaScript application to maintain,
which keeps the product fast, accessible, and simple to operate. (Verify:
`dazzle validate`.)


## How work flows

Work moves through the roles and queues described above so each step has a clear owner.

## Automation & controls

**Announcement lifecycle.** Announcements move draft → published → archived (admin may return published to draft or republish archived).

**Workspace Document lifecycle.** Workspace Documents move draft → published → archived under admin control (admin may return published to draft).

**Workspace Member lifecycle.** Joined staff move pending → active → offboarded under admin control (rejoin and re-invite paths included).

<!-- dazzle-spec-brief: sha256:4f5646c940f8dbb1947da6be31d6d3bf5a4c725bde3cdb33b74d4d981277a2d7 -->
