# Deferred Decisions (DD)

Long-horizon plans that must **survive months of silence** and wake up when a
**specific consumer force** appears.

In epistemic-engineering terms (see
[practice note](../architecture/epistemic-engineering-practice.md)): stems and
ADRs answer *what is true*; a DD answers *when residual work may proceed* and
preserves the full plan so agents implement **that** plan under force—not a
fresh invention from chat archaeology.

GitHub `future` issues alone are not enough: labels rot, comment threads bury
the plan, and new agents re-derive the wrong design. A **DD** is a greppable,
versioned doc that records:

1. What we already decided (the plan)
2. What is **already shipped** (do not re-litigate)
3. **Reopen when** — concrete consumer signals, not “someday”
4. Links to issues / ADRs / prove commands

## When to write a DD

Write one when you would otherwise leave only an issue comment like:

> “Park until consumer force — do not speculative-build.”

Typical cases:

- Umbrella phase leftover after substrate ships (`#1617` → `#1621`/`#1622`)
- Escape hatches pre-committed by an ADR but not productized
- Counter-priors (“never hand-roll `*_type`+`*_id`”) that agents re-discover as
  “clever” shortcuts

**Do not** write a DD for ordinary backlog items with a near-term owner.

## Lifecycle

| Status | Meaning |
|--------|---------|
| `PARKED` | Plan is valid; no implement without force signal |
| `FORCED` | Named consumer landed; implement against the plan |
| `DONE` | Shipped; issues closed |
| `SUPERSEDED` | Replaced by another DD or ADR |

Improve / `/issues` must **not** implement `PARKED` DDs (or issues labeled
`future` that link a PARKED DD) unless status has moved to `FORCED`.

## How agents use this

```bash
# List parked decisions
rg -n '^status: PARKED' docs/decisions/

# Find plan for an issue number
rg -n '1621|1622' docs/decisions/

# When a consumer appears
# 1. Edit the DD: status FORCED + consumer section
# 2. Comment on linked issues with the consumer path
# 3. Implement; then status DONE
```

New DD: copy [TEMPLATE.md](TEMPLATE.md), assign next free `DD-NNN`, add a row
below, link from the issue body (not only a comment).

## Index

| ID | Title | Status | Issues | Notes |
|----|-------|--------|--------|-------|
| [DD-001](DD-001-1617-poly-ref-and-sti-eav.md) | #1617 residuals: poly_ref polish + STI/EAV-as-JSONB | PARKED | #1621, #1622 | Substrate shipped; consumer-forced only |
| [DD-002](DD-002-pitch-generator.md) | Pitch deck generator (`dazzle pitch`) | PARKED | — | Removed under ADR-0057; restore from 82c9a8571 when AegisMark regenerates a deck |
| [DD-003](DD-003-domain-brief.md) | Agent-audience domain brief (`domain_brief`) | PARKED | #1629, #1631 | Removed in flense ship C; restore from `003c01392` when a prose-bootstrapped consumer needs it |
| [DD-004](DD-004-ledger-and-transaction.md) | `ledger` / `transaction` / `atomic` constructs + `fieldtest_hub` | PARKED | — | Constructs + `atomic` flows removed in flense ship F; reopen on pennydreadful royalties or cyfuture client money |
| [DD-005](DD-005-inbound-webhooks.md) | Inbound `webhook` construct (signature verification, idempotent dispatch) | PARKED | — | Outbound `webhook` removed in flense ship D; reopen when AegisMark or cyfuture asks to replace its hand-written webhook route |
| [DD-006](DD-006-events-dsl.md) | Events DSL (`hless`/`stream`/`event_model`/`subscribe`/`projection`/`ingest`) + Kafka bus + event-transport residue (Postgres/memory buses, `/_dazzle/events` explorer, `live:` SSE push, channel outbox) | PARKED | #1069, #1189, #1676, #1399 | Event core (outbox, inbox, Redis bus) kept; transport parked in flense ship AR (`_dazzle_outbox` dropped by revision 0025, restore from `5bba9833f`); reopen when pennydreadful rights auctions need an ordered or replayable bid stream, a consumer declares `live: on`, or one needs a Postgres-only deployment without Redis |
| [DD-007](DD-007-messaging-dsl.md) | Messaging DSL (`message`/`channel`/`notification`/`asset`/`document`/`template`) | PARKED | #952 | Email kernel kept; reopen on cyfuture SLA `on_breach: notify` or AegisMark safeguarding alerts |
| [DD-008](DD-008-background-jobs.md) | `job` construct + `dazzle worker` | PARKED | #953 | `schedule` kept; reopen when AegisMark replaces Heroku Scheduler (`cohort_analysis`) |
| [DD-009](DD-009-verified-domain-join.md) | Verified-domain self-service join | PARKED | #1424 | SSO domain verification kept; reopen when AegisMark school email domains need it |
| [DD-010](DD-010-process-step-ai-executor.md) | Process-step AI executor (`llm_intent` steps in a `process`) | PARKED | #1454, #1457 | Never mounted (ADR-0043); removed in flense ship O; reopen when a consumer runs an `llm_intent` step inside a process |
| [DD-011](DD-011-island-rendering.md) | Rendering DSL-declared islands (`src:` / `title` / `fallback:`) | PARKED | — | Only `entity:` is live (data route); `dazzle validate` warns since flense ship R; reopen when cyfuture or AegisMark needs a rendered island |
| [DD-012](DD-012-string-translation-catalogue.md) | String translation catalogue (`.po`/`.mo`, `translate`, `dazzle i18n`) | PARKED | #955 | Removed in flense ship AB (display-locale profile kept, middleware now mounted); restore from `3844ec995` when a consumer ships `.po` files |
| [DD-013](DD-013-enterprise-sso-scim-connections.md) | Enterprise SSO / SCIM connections (OIDC, SAML, SCIM, domain verification, `dazzle auth connection`) | PARKED | #1342 | Removed in flense ship AD with its five tables (revision 0023); restore from `23cf59372` when a consumer declares `auth.enterprise.*` with a real IdP |
| [DD-014](DD-014-two-factor-authentication.md) | Two-factor authentication (TOTP, email code, recovery codes, `/2fa/*` pages) | PARKED | #829, #838 | Removed in flense ship AG with its two tables (revision 0024); restore from `229226a88` when a consumer declares 2FA or its assurance pack names MFA |

## Related

- ADRs: `docs/adr/` (accepted architecture — use when the *system* decision is final)
- DD: plan + force conditions when the *timing* of work is deferred
- Representation hatches: `docs/reference/data-representation.md`
- AGENTS.md — Deferred decisions bullet under ship / agent discipline
