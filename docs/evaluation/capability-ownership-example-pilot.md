# Capability ownership pilot in complex examples

**Date:** 2026-09-27
**Status:** Implemented in `invoice_ops` and `fieldtest_hub`

## Question

Can an existing Dazzle module own a recognizable product capability—its data,
pages, processing, and focused workspaces—without adding a DSL construct or
changing what the app delivers? This tests whether a technical founder can
identify a part of the product they control while agents retain one linked
AppSpec and explicit dependencies.

The pilot used `invoice_ops` and `fieldtest_hub` because they put pressure on
different shapes. `invoice_ops` grouped declarations by construct type across
several modules. `fieldtest_hub` placed most of its product in one large `core`
module.

## Changes

The pilot moved declarations without changing their bodies:

| Example | Capability module | Declarations owned together | Composition elsewhere |
|---|---|---|---|
| `invoice_ops` | `invoice_ops.payments` | `PaymentAttempt`, its three surfaces, `pay_desk`, `payments_trail`, `payment_provider`, and `settle_invoice` | `finance_ops` and `audit_review` show payment attempts as part of broader jobs |
| `fieldtest_hub` | `fieldtest_hub.firmware` | `FirmwareRelease`, its four surfaces, and `draft_releases` | `firmware_pipeline` combines releases with remediation `Task` work |

`payments` uses `invoice_ops.entities` for Invoice and Tenant. The remaining
invoice surfaces module uses `payments` because its broad workspaces show
PaymentAttempt. The fieldtest core uses `firmware` because its broad workspaces
show FirmwareRelease. Both import graphs remain acyclic. The now empty
`invoice_ops.services` module was removed.

The unused-import check now counts workspace region sources, actions, navigation
items, and primary actions as uses of their owning modules. This permits an
explicit `use` for a workspace-only dependency without a false warning. Example
tests that inspect declaration text now locate a named declaration across DSL
files instead of assuming it remains in `surfaces.dsl` or `app.dsl`.

## Behaviour check

Both examples pass `dazzle validate`. After excluding source locations and
module metadata, and comparing named declarations without top-level list
order, their AppSpec content matches the originals: 13 entities, 32 surfaces,
and 11 workspaces in `invoice_ops`; 12 entities, 33 surfaces, and 10 workspaces
in `fieldtest_hub`. Their compiled route maps match exactly (34 and 35 routes).
For example, `/app/paymentattempt/{id}` still resolves to
`payment_attempt_detail`, and `/app/firmwarerelease/{id}` still resolves to
`firmware_release_detail`. The moved declarations have their new source files
and lines in `SourceLocation`.

The legacy `nav_items` list in compiled page contexts changes order when a
workspace moves to an earlier dependency module. The actual persona and
anonymous `NavModel` output was compared before and after in both examples and
remained equal. Browser-rendered parity was not tested. The focused example
and linker suite passes (124 tests).

## What the split tells us

A focused capability can own its model, page declarations, processing, and
dedicated workspace in one file. A broad job workspace is different:
`pay_desk` belongs naturally with payments, while `finance_ops` composes
payments with invoices, suppliers, and people. Giving every shared workspace
to one capability would obscure those dependencies.

The useful boundary is **primary ownership plus visible composition**. A
declaration has one source module; other modules may use it. People can assign
repository ownership to those files without encoding a team hierarchy in the
DSL. This preserves the linked AppSpec used for agent reasoning.

The split alone does not answer the founder's URL question. Dazzle still needs
a URL-led inspection view that reports the route, primary surface or workspace,
its source file and line, the declarations it draws on, and representative
rendered HTML for a stated request context. That should expose the generated
page's provenance without introducing an editable second HTML source of truth.

## Limits and next measure

The linker change fixes unused-import reporting; it does not enforce every
cross-module workspace reference as an import. Doing that uniformly would
require a deliberate treatment of existing app modules with cyclic
composition, notably signing flows in `contact_manager` and `support_tickets`.
This pilot leaves those examples alone.

The next useful test is task based: give someone unfamiliar with either app a
URL and ask them to locate its owner, identify a safe place to change it, and
find other capabilities that consume it. A URL-to-source inspection command
would make that test practical and reveal whether the module boundaries offer
real control rather than just shorter files.
