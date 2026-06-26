---
id: reinvented_capability
name: Reinvented capability (duplication over discovery)
layer: inference
status: active
summary: >-
  Re-implementing a capability that already exists — a framework keyword, a
  shared helper, an existing utility — because the existing one was not in view
  at write time. The flaw is not duplication (declining a premature abstraction
  can be the correct call); it is duplicating an invariant-equivalent capability
  that already exists, without searching for it, creating an undocumented
  divergence surface where one rule now lives in two places that do not know
  about each other.
triggers_text:
  - "write a helper"
  - "utility function"
  - "reimplement"
  - "roll our own"
  - "from scratch"
  - "add a function to"
  - "similar to the existing"
  - "i'll just write my own"
triggers_code: []
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  tests: []
detectors: []
---

# Reinvented capability (duplication over discovery)

## The corpus prior

This is an **agent-production** prior, not (only) a training-corpus idiom — and
it is measured. Across 2025–2026 large-scale studies, agent-written code shows
*lower* cross-file reuse of shared utilities and *higher* within-file
duplication than matched human code (a matched-pair study of ~56k files: 17.2%
vs 24.5% cross-file reuse, 0.679 vs 0.534 clone instances/file; FSE 2025 found
Type-1/2 clone rates up to 7.50% in commercial generators). The fingerprint —
reuse what is visible in-file, re-derive what lives in a file you never loaded —
is the signature of **bounded context**: the agent does not have the existing
helper in view, so it re-implements it. "Append, don't refactor" compounds it.

The mechanism is not laziness or a bad idiom from Stack Overflow; it is a
structural property of generating code from a context window that does not, by
default, contain the whole codebase.

## Wrong shape

Re-implementing a capability that **already exists and carries the same essential
invariant** — without searching for it first:

- hand-writing a `deleted_at` filter when the framework has `soft_delete:`
- writing an as-of date handler when the framework has `temporal:`
- looping per-row to count related entities when the aggregate path does it in
  one query
- re-deriving a string/slug/identity helper that already lives in `core.strings`

The tell is not that the code is duplicated — it is that **the choice was never
made**. There was no trade-off evaluation, just an unexamined gap. The next
bug-fix patches one copy and silently leaves the other wrong.

## Right shape

Search before you write, and if you still duplicate, say why in the code:

1. Ask: *does a construct with this exact responsibility already exist?* Check the
   DSL keywords, the framework helpers (`knowledge concept`, `dazzle search`), and
   the surrounding module.
2. If yes and the behaviour is invariant-equivalent — **reuse it.**
3. If you are deliberately declining a *premature or coincidental* abstraction
   (two blocks that look alike but answer to different forces, at or below the
   rule-of-three), duplication is legitimate — but make it a documented choice,
   not an invisible fork.

The discriminating question, asked at write time:

> *Does a helper with this exact responsibility already exist — and if a future
> change altered this behaviour, would I be REQUIRED to make the identical change
> everywhere it appears? If yes to both, reuse. If I still duplicate, I must say
> why.*

## Why this matters here

Dazzle's whole posture is that the substrate provides capabilities centrally so
they are enforced once. This counter-prior is the **general form** of a cluster
the catalogue already documents as special cases — [hand-rolled-soft-delete](hand-rolled-soft-delete.md),
[hand-rolled-temporal](hand-rolled-temporal.md), and [n-plus-one-in-user-code](n-plus-one-in-user-code.md)
are each "the agent re-implemented a capability the framework already provides."
Those are first-party evidence that this prior recurs in Dazzle's own
agent-generated history. Where a specific capability has a keyword, the **grammar**
layer closes it by construction; for everything else, the fix is inference-time —
discover before you write. A re-implemented invariant is a divergence surface that
RBAC, scope composition, and migrations cannot see, because the framework only
guarantees the path that goes through the framework.

**First-party corroboration.** A scan of this repo's own closed issues (the
codebase is ~entirely agent-generated, 5.5k commits) finds the prior recurring as
filed tech-debt: a `slug:` primitive added because *"every multi-tenant Dazzle app
reimplements"* it (#1288); *"~20 inline copies"* of DB-URL normalisation
consolidated (#1185); duplicate `VIRTUAL_ENTITY_NAMES` (#1459); persistent
re-export/wrapper blocks (#1439). The agent re-derived, then a later agent filed
the consolidation — exactly the discover-before-you-write gap, paid down after the
fact instead of avoided.
