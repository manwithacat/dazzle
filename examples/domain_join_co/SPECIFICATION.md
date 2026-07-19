# Domain Join Co — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

Domain Join Co is a workspace system built around verified-domain membership:
a company's workspace is anchored to its verified email domain, employees join
under it, and everything the team shares stays inside that boundary. The
system manages two things — the Workspace itself, the root under which a
company operates and where members and their roles are declared, and
Announcements, the tenant-scoped posts a workspace admin publishes to keep the
team informed.

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

Announcements can be listed, read in detail, and posted through three
dedicated screens.

## Who uses it

- **Workspace Admin** — owns one workspace. Their aims: verify the company
  domain, approve the right joiners, and keep the team informed. Admins are
  the only role that can post or edit announcements.
- **Team Member** — an employee who self-joined with a verified company
  email. Their aims: join their company workspace and stay up to date. Members
  read the team's announcements; within the current workspace, announcements
  are visible to admins and members alike.

## Where work happens

- **Workspace Home** — admin landing after domain join is configured: team
  pulse metrics, a join-readiness status strip (verified domain, join policy,
  announcements — join approval itself lives in the auth admin console), then
  the announcement feed.
- **Team Board** — member home (and shared board for admins): announcement
  metrics and the team noticeboard without the join-readiness strip.

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

<!-- dazzle-spec-brief: sha256:3b02c9127d872c23d5e41cf1759dd70b46d2b2e98247c71b8b27a8a80a90a2a0 -->
