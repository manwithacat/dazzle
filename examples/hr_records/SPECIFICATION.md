# HR Records — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

HR Records is a personnel record system built around a simple idea: the facts
about a person's career change over time, and the system should remember every
period, not just the present. It manages departments, job roles, and people —
and, for each person, an effective-dated history of their employment, their
compensation, and who they report to. Because each fact carries the period it
was true for, the system can answer not only "who works here today?" but "what
did the organisation look like on any given date?"

Four kinds of people use it — HR administrators, line managers, finance staff,
and employees themselves — and what each of them can see is not left to
convention. Visibility rules are declared once in the model and applied
automatically to every query the system runs (verifiable with
`dazzle rbac report`), and the rules themselves can be submitted to a formal
solver for verification (`dazzle rbac prove`). An employee sees only their own
record; a manager sees only their own reports; finance sees compensation but
not the reporting hierarchy.

## What it does

**The organisation.** A Department is an organisational unit; departments can
nest under a parent department, forming a tree. A Role is a catalogued job
title, and every role belongs to a department. People hold roles through
employment records rather than directly, so a job change never overwrites
history.

**People and their histories.** A Person is a staff member, past or present —
an identity record that notes when they started and, where applicable, when
they left. The facts that vary over a career live in three effective-dated
record types tied to that person:

- An **Employment** record assigns a person to a role and a department for a
  period; a record with no end date is the currently active assignment.
- A **Salary** record captures compensation for a period; one with no closing
  date is the compensation in force today.
- A **Manager Link** records a reporting line between a report and their
  manager for a period; an open-ended link is the current one.

Each of these can be browsed, inspected, created, and maintained through
dedicated screens — fourteen in all, from the staff directory to
"End Reporting Line".

## Who uses it

- **HR Admin** — full create, read, update, and delete access across every
  record type and its history; works in every workspace, including the Time
  Machine. Thinks in events.
- **Line Manager** — reads their own direct reports, current and historical: a
  person, and that person's employment history, is visible to a manager only
  when a manager-link record connects them. Managers see the reporting lines
  where they are the manager or the report. No salary access.
- **Finance** — reads all salary data and employment history across the
  organisation, but not the manager hierarchy. Works in the staff directory,
  person detail, and the compensation review workspace.
- **Employee** — reads self only: their own person record, their own
  employment and salary history, and their own current reporting line.

## Where work happens

- **Staff Directory** — shared entry for all four roles: headcount metrics
  (people, departments, roles) first, then current staff and recent starters.
- **Person Detail** — a career timeline, showing a person's employment history
  and salary history side by side. Open to all four roles, with each seeing
  only what their visibility rules allow.
- **Departments & Roles** — the department tree and manager hierarchy, with role
  listings; used by HR admins and line managers.
- **Compensation Review** — finance/HR home for salary work: compensation
  metrics strip, then the active salary list for band analysis.
- **Time Machine** — an HR-admin-only workspace that re-projects employment,
  salary, and reporting-line views as of any chosen date: append
  `?as_of=YYYY-MM-DD` and every region shows the organisation as it stood on
  that day.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see. Each rule — "an employee sees only records whose person is
themselves", "a manager sees people a manager link connects to them" — is
declared once in the model and applied automatically to every query the
framework runs, instead of being re-implemented, and re-checked, screen by
screen. (Verify: `dazzle rbac report`.) Beyond filtering, every role's
permissions for every record type and operation are declared as
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

<!-- dazzle-spec-brief: sha256:7af1858ae928741e52e99fc74cf2f02464f6fd531845052d199640149e251184 -->
