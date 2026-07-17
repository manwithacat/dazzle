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

## Related

- ADRs: `docs/adr/` (accepted architecture — use when the *system* decision is final)
- DD: plan + force conditions when the *timing* of work is deferred
- Representation hatches: `docs/reference/data-representation.md`
- AGENTS.md — Deferred decisions bullet under ship / agent discipline
