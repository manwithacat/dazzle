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
back to its creator.

**Design assets under review.** A Design Asset is a piece of creative work that
always belongs to a Brand and carries its creator. Each asset moves through an
explicit life — draft, review, approved, published, archived — so the studio
always knows exactly where a piece of work stands.

**Campaigns.** A Campaign also belongs to a Brand and records who created it,
moving through its own life from planning to active to completed (or
cancelled).

**Feedback.** Design Feedback is always tied to the specific Design Asset it
concerns and to the User who reviewed it, so critique is never detached from
the work or the reviewer.

Brands, assets, campaigns, and feedback can each be browsed, inspected,
created, and edited through dedicated screens — fifteen in all.

## Who uses it

- **Admin** — full access to all brands and assets.
- **Designer** — creates and manages design assets.
- **Reviewer** — reviews and approves assets.

All three roles work in the same two places: the Studio Dashboard and the Asset
Gallery. Visibility of every kind of record — users, brands, assets, campaigns,
and feedback — is governed by declared rules; under the current rules, all
three roles can see all records, and that grant is itself an explicit,
auditable declaration rather than an accident of screen design.

## Where work happens

**Studio Dashboard** — the shared home for admins, designers, and reviewers: a
grid of brands, a grid of design assets, and campaign metrics, giving the whole
team one view of the studio's output.

**Asset Gallery** — where the asset pipeline is worked: a grid of design assets
alongside a queue of assets, serving the same three roles.

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

<!-- dazzle-spec-brief: sha256:2f77d032a1a05d532bb9a318efd11054af2c9a581da603116ef895fcffa4cb3c -->
