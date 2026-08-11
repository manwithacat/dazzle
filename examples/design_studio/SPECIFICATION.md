# Design Studio — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

Design Studio is a creative-operations system for teams that produce branded
design work. It manages brands, the design assets created for them, the
campaigns those assets serve, and the review feedback that moves an asset from
first draft to published work.

Three kinds of people work in the system — admins, designers, and reviewers —
and access to every kind of record is governed by rules declared once in the
model and applied automatically to every query the system runs, rather than
re-implemented screen by screen. Every role's permissions for every operation
compile on demand into an auditable access matrix, and the visibility rules can
additionally be submitted to an SMT solver for formal verification. A skeptic
does not have to take this on trust: `dazzle rbac report` produces the matrix,
and `dazzle rbac prove` runs the formal check.

## What it does

**Brands and the people behind them.** A Brand is the organising anchor of the
studio's work, recorded along with the User who created it. Users are the
people working in the system — every brand, asset, and campaign can be traced
back to its creator. Studio staff also carry department and job title so the
**Team** desk can show Creative Ops / Design Systems / Brand Strategy / Review QA
shape (title kanban + department queue) before a flat people dump — peer
creative-ops tools (Figma, Adobe, Abstract, Frame.io) put org placement first.

**Design assets under review.** A Design Asset is a piece of creative work that
always belongs to a Brand and carries its creator. Each asset moves through an
explicit life — draft, review, approved, published, archived — so the studio
always knows exactly where a piece of work stands. Peer creative-ops tools
(Figma, Frame.io, Bynder) also put a **revision number** and **approval stamp**
on the creative row — not status-only meta — so directors see version grain
above the fold on media shelves and hubs.

**Campaigns.** A Campaign also belongs to a Brand and records who created it,
moving through its own life from planning to active to completed (or
cancelled). Design assets may be assigned to a campaign; opening a campaign
shows a schedule strip, brand context, and a pull-queue of those creatives —
not a bare field dump.

**Feedback.** Design Feedback is always tied to the specific Design Asset it
concerns and to the User who reviewed it, so critique is never detached from
the work or the reviewer.

**Design documents.** Named design documents (briefs, brand guides, art
direction notes, creative specs, decision logs) with domain-true headlines that
buyers scan as composition above the critique trail — attached to a Brand hub.

Brands, assets, campaigns, feedback, and design documents can each be browsed,
inspected, created, and edited through dedicated screens.

## Who uses it

- **Admin** — full access to all brands and assets.
- **Designer** — creates and manages design assets.
- **Reviewer** — reviews and approves assets.

Admins and designers land on the **Studio Dashboard**; reviewers land on the
**Review Desk** so review pressure is first. Visibility of every kind of
record — users, brands, assets, campaigns, feedback, and design documents — is
governed by declared rules; under the current rules, all three roles can see all
records, and that grant is itself an explicit, auditable declaration.

## Where work happens

- **Studio Dashboard** — multi-panel studio home (command_density + document):
  creative preview thumbs above the fold, compact load metrics (including
  document count), dual attention (in-review + draft queues), design-document
  composition with domain-true headlines, then critique trail and brand pull-queue.
- **Brand Desk** — brand media path: asset preview grid (logo/photo/illustration
  thumbs above fold), compact logo identity shelf, and active campaign queue
  (no trail/bar thrash — bar_chart/timeline dogfood lives on Asset Catalog).
- **Review Desk** — multi-panel review home (command_density + document):
  review-load metrics (including document + conversation counts), dual attention
  (awaiting-review + draft queues), design-document composition, then live critique
  trail (Feedback copy), recently approved, and pipeline kanban.
- **Asset Catalog** — media shelf first: asset preview thumbs above fold, then
  compact brand palette, review queue, pipeline kanban; under-fold status mix chart
  and recent-activity timeline host bar_chart/timeline dogfood for the studio.
- **Campaigns** — campaign media desk: assigned creative preview thumbs above the fold,
  compact schedule metrics, active briefs, and status board; campaign detail hubs show
  an assigned creative media wall (not a bare name table).
- **Feedback** — critique desk: conversation pulse, live notes queue, and
  assets-in-review pull queue (no twin timeline or asset status bar dump).
- **Publish Desk / Draft Studio / Review Pipeline / Active Campaigns** — secondary
  pressure desks keep pulse + work queues only (empty_region_honesty); no twin
  gallery/trail/status-bar thrash under the fold.
- **Team** — org structure desk: studio staff by job title (kanban) and department
  placement before flat roster and brand load (org_structure Goal B).

## How work flows through it

Two of the record types carry an explicit lifecycle, so the state of the
studio's work is always inspectable:

- A **Design Asset** moves from *draft* → *review* → *approved* → *published*,
  and ultimately to *archived*.
- A **Campaign** moves from *planning* → *active* → *completed* (or
  *cancelled*).

Together these form the studio's operating rhythm: designers draft assets for a
brand, reviewers attach feedback and move work through review to approval,
approved work is published into campaigns, and finished material is archived.

## Automation & controls

One durable process reinforces campaign ownership: when a Campaign becomes
**active**, a designer claim step confirms who owns the work so activation is
not an informal chat (verify: `dazzle process list`).

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

## Compliance posture

Design assets attached to records are served through an entity-scoped, audited
byte-access boundary: bytes are released only when the same rule that governs
the record allows it, and each access is recorded. A static proof holds every
byte-serving route to that boundary, so no new route can stream asset bytes
outside it without being explicitly listed. (Verify:
`dazzle rbac byte-routes --strict`.)

**Design Document lifecycle.** Design Documents move draft → published → archived (designer publishes; admin may archive or return published to draft).

<!-- dazzle-spec-brief: sha256:4b6ccc0fdd46db47ec5a00475bb7073429b8173602013ae3a453f7140a07693c -->
