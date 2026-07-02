# Acme Billing — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

Acme Billing is a multi-organization billing system. It manages organizations,
the users who belong to them, the projects each organization runs, the invoices
raised against those projects, and the memberships that assign users to
specific projects.

The system's defining property is that every one of those five record types is
under declared visibility rules, and the rules distinguish five different roles
— from a platform administrator with cross-organization access down to an
external contractor who sees only non-sensitive material on assigned projects.
Each rule is declared once in the model and applied automatically to every
query the system runs; every role's permissions for every operation compile on
demand into an auditable access matrix, and the visibility rules can
additionally be submitted to an SMT solver for formal verification. A skeptic
does not have to take this on trust: `dazzle rbac report` produces the matrix,
and `dazzle rbac prove` runs the formal check.

## What it does

**Organizations and their people.** An Organization is the root of the tenancy
model — the boundary within which everything else lives. A User is a person's
record in the system, and every user belongs to an organization; that link is
what the visibility rules resolve against when deciding what the signed-in
person may see.

**Projects.** A Project always belongs to an Organization. Which projects a
given person can see depends on their role — owners and auditors see their
organization's projects, while project members see only the projects a
membership assigns them to.

**Invoices.** An Invoice is a billing record always raised against a Project,
with its amount recorded in whole cents. Invoices can be flagged as sensitive,
and that flag is enforced by the visibility rules: members and contractors
never see sensitive invoices, while auditors and owners do.

**Memberships.** A Membership links a User to a Project — it is the assignment
record that grants project members and contractors their view of the work.

All five record types can be browsed, inspected in detail, created, and edited
through dedicated screens — twenty in all.

## Who uses it

- **Administrator** — the platform administrator, with full cross-organization
  access as a break-glass role. Their aims are to manage organizations and
  audit access; under the declared rules they alone can see and manage all
  records of every kind, across every organization.
- **Organization Owner** — owns one organization, with full access within that
  organization only. Their aims are to manage projects and review invoices;
  the rules confine them to users, projects, invoices, and memberships whose
  organization is their own, and only they (besides the administrator) can
  create projects or manage memberships there.
- **Auditor** — a read-only reviewer scoped to one organization. Their aims are
  to review invoices and projects and verify compliance; they can see their
  organization's users, projects, and invoices — including sensitive invoices —
  but the rules grant them no ability to create, change, or delete anything.
- **Project Member** — works on assigned projects only. They see a project when
  a membership record links it to them, and they see its invoices only when the
  invoice belongs to their organization and is not flagged sensitive.
- **External Contractor** — a limited outside collaborator. Their one aim is to
  view assigned, non-sensitive project data; the same combined rule applies —
  invoices in their own organization, and never anything flagged sensitive.

Administrators, organization owners, and auditors work in the Acme Billing
workspace; project members and external contractors reach their assigned
material through the record screens themselves.

## Where work happens

**Acme Billing** — the single workspace, serving administrators, organization
owners, and auditors. Its purpose is to manage organizations, projects,
invoices, and team memberships, and it presents all four side by side: a list
of organizations, a list of projects, a list of invoices, and a list of
memberships.

## How work flows through it

Five authored scenarios pin down exactly how the visibility rules behave in
practice, one per role:

- When an organization owner creates a project, it is created within their own
  organization, appears in their project list alongside only that
  organization's projects, and never exposes another organization's work.
- When an auditor lists invoices for one of their organization's projects, they
  can read every invoice within the organization — sensitive ones included —
  but cannot create, update, or delete any of them.
- When a project member lists available projects, they see the project they are
  assigned to and not the one they are not.
- When an external contractor lists invoices, the non-sensitive invoices of
  their own organization are visible, the sensitive one is hidden, and every
  invoice belonging to any other organization is excluded outright — the
  organization boundary applies regardless of sensitivity.
- When an administrator lists organizations, projects, and invoices, they see
  everything across every organization, unrestricted by any single
  organization's boundary.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see. The rule is declared once in the model and applied
automatically to every query the framework runs, instead of being
re-implemented — and re-checked — on each screen.
(Verify: `dazzle rbac report`.) Beyond filtering, every role's permissions, for every entity and
operation, are declared as machine-readable policy. They compile on demand into
an auditable access matrix — so permission review is something you run and
diff, not something you eyeball — and the row-visibility rules can additionally
be submitted to an SMT solver for formal verification. (Verify:
`dazzle rbac prove`.)

**Data & reliability.** All data is stored in PostgreSQL — a mature,
widely-trusted relational database. There is no bespoke or experimental
datastore to operate, secure, or reason about. (Verify: `dazzle db status`.) In
production, every change to the data model is applied through versioned,
reversible migrations. The live schema is never edited by hand, so upgrades are
repeatable and fully auditable. (Verify: `dazzle db status`.)

**Architecture.** The interface is rendered on the server and progressively
enhanced. There is no heavy single-page JavaScript application to maintain,
which keeps the product fast, accessible, and simple to operate. (Verify:
`dazzle validate`.)

<!-- dazzle-spec-brief: sha256:935d746423ced5b9f6b339ebae4cb4e6a7b30151ed7139204fd780d88d34d0cf -->
