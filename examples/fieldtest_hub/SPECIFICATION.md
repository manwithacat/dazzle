# FieldTest Hub — Specification

## Executive summary

FieldTest Hub is a field-testing operations product for hardware programmes. It tracks physical Devices from prototype through active use to recall or retirement, the Testers who carry them in the field, and everything the field sends back: logged Test Sessions, severity-graded Issue Reports, remediation Tasks, and the versioned Firmware Releases that respond to what the field discovers. It also keeps honest books on the programme itself, accruing repair and replacement costs against the device fleet and drawing them down from the operations budget as balanced, double-entry money movements.

Four kinds of people work in it — Engineers, Field Testers, Managers, and Administrators — and what each can see is not left to convention. Access rules are declared once in the model and applied automatically to every query the product runs, and every role's permissions for every kind of record and operation compile on demand into an auditable access matrix, with the row-visibility rules additionally submittable to an SMT solver for formal verification. A field tester sees only the devices assigned to them, the sessions they logged, the issues they reported, and the tasks handed to them — enforced by the platform, not by the goodwill of each screen.

## What it does

**Devices and the people who test them.** A Device is a physical hardware unit produced in a batch, assigned to a Tester, and tracked through prototype, active, recalled, and retired states. A Tester is a field-testing volunteer or employee who is assigned Devices, logs Test Sessions, and reports Issue Reports.

**The evidence testing produces.** A Test Session is a logged episode of hands-on testing on a specific Device by a Tester, capturing duration, conditions, and observations — every session names both the device it exercised and the tester who ran it. An Issue Report is a problem observed on a Device during field testing, categorised by severity and tracked from open through triage to fixed, verified, and closed; every report is tied to the Device it was observed on and the Tester who filed it.

**Acting on what the field finds.** A Task is a remediation or investigation task spawned from field testing, created by one person and optionally assigned to another, with a lifecycle from open to completed. A Firmware Release is a versioned firmware build that can be rolled out to a Device batch, transitioning from draft to released to deprecated.

Every one of these six kinds of record can be browsed, inspected in detail, created, and edited through dedicated screens — twenty-four capabilities in all, from the Device Dashboard and Issue Board to Log Test Session and Create Firmware Release.

## Who uses it

**Engineers** run the engineering side of the programme. Their goals: monitor all devices and issues, manage firmware releases, and coordinate testers. They work in the Engineering Dashboard, see every record in the system, and hold the create/edit rights over Devices, Testers, and Firmware Releases.

**Field Testers** are the programme's eyes in the field. Their goals: report issues from the field, log test sessions, and track their assigned devices. They work in their own Tester Dashboard, and their view is deliberately narrow: they see only Devices where the assigned tester is the signed-in user, only Test Sessions where the tester is the signed-in user, only Issue Reports they themselves reported, and only Tasks assigned to them. They can create issue reports and test sessions, and update their own.

**Managers** track overall product quality and monitor critical issues. They share the Engineering Dashboard with engineers, with full visibility across devices, issues, sessions, releases, and tasks, and can create and reassign Tasks.

**Administrators** complete the roster as the fourth declared role.

## Where work happens

**Engineering Dashboard** — comprehensive field-testing oversight for engineers and managers. It layers many views over the same records: lists, a kanban board, and a tabbed list of Issue Reports; Devices as a list, kanban, timeline, tree, diagram, and map; Firmware Releases as a list, kanban, and timeline; Tasks as a list and kanban; and a directory of Testers.

**Tester Dashboard** — the personal field-testing hub. A tester lands on their assigned Devices, their Issue Reports, a timeline of their Test Sessions, and their Tasks.

## How work flows through it

Four of the six kinds of record carry an explicit lifecycle, so the state of the programme is always inspectable:

- A **Device** moves from prototype → active, and ultimately to recalled or retired.
- An **Issue Report** moves from open → triaged → in progress → fixed → verified → closed — a full loop from field observation to confirmed resolution.
- A **Task** moves from open → in progress → completed (or is cancelled), and can be pushed back from in progress to open.
- A **Firmware Release** moves from draft → released → deprecated.

Twenty-six authored scenarios pin these flows down, spanning all three active roles. A representative sample:

- When a Field Tester reports a device issue, an Issue Report is created referencing the Device and the tester, and it starts life as open.
- When a Field Tester logs a test session, the session records the device, tester, environment, and duration, and appears in the tester's dashboard.
- When a Field Tester views their devices, they see only Devices whose assigned tester is themselves, and can click through to log a session or report an issue.
- When an Engineer triages recent issue reports, they see all open reports sorted by severity and can move a report from open to triaged.
- When an Engineer links a firmware release to a device batch, devices matching that batch show the new firmware version; when an Engineer marks a device as recalled, its associated testers are notified.
- When a Manager reviews team workload, they see open Tasks grouped by assignee and can reassign a Task from one engineer to another; a Manager tracking release progress sees releases newest-first with counts of drafted versus released versus deprecated.

## Automation & controls

The programme's money is under declared control. Two double-entry accounts, both in GBP, anchor the books: the **Device Cost Account**, which accrues repair and replacement expenses against the fleet of field devices, and the **Operations Budget**, which draws down the field-test programme's allocated operations budget. The **Record Repair Cost** transaction moves money between them as a balanced movement — charging a device repair to the cost account and drawing it from the operations budget in one indivisible step.

## The technical foundation

These guarantees hold because the product is built on Dazzle, and each can be independently verified by running a single command.

**Security.** Access-controlled records are filtered to what each user is permitted to see. The rule is declared once in the model and applied automatically to every query the product runs, instead of being re-implemented — and re-checked — on each screen (verify: `dazzle rbac report`). Every role's permissions, for every kind of record and operation, are declared as machine-readable policy; they compile on demand into an auditable access matrix — permission review is something you run and diff, not something you eyeball — and the row-visibility rules can additionally be submitted to an SMT solver for formal verification (verify: `dazzle rbac prove`).

**Data & reliability.** All data is stored in PostgreSQL — a mature, widely-trusted relational database. There is no bespoke or experimental datastore to operate, secure, or reason about (verify: `dazzle db status`). In production, every change to the data model is applied through versioned, reversible migrations; the live schema is never edited by hand, so upgrades are repeatable and fully auditable (verify: `dazzle db status`). The programme's money movement is modelled as balanced, double-entry transactions against declared ledger accounts, and validation enforces that every declared movement has an equal and opposite entry; the TigerBeetle-backed execution engine for these declarations is in alpha and not yet independently verified (verify: `dazzle validate`).

**Architecture.** The interface is rendered on the server and progressively enhanced. There is no heavy single-page JavaScript application to maintain, which keeps the product fast, accessible, and simple to operate (verify: `dazzle validate`).

<!-- dazzle-spec-brief: sha256:447340bad013792811cf5b1f48a71d36fb871a227e9a800040d94e5bf274b9cf -->
