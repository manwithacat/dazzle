# ADR-0052: `scope: all` on tenant-kind entities compiles to the partition-root subtree

**Status**: Accepted (2026-07-07)
**Issue**: #1541

## Context

`scope: <verb>: all` compiles to `Tautology` — no filter. For ordinary
entities that is correct: the tenant fence (RLS `tenant_id` partition)
bounds the rows before the scope rule is consulted.

Tenant-KIND entities (those declaring `tenant_host:` — the ADR-0036
hierarchy anchors, e.g. Region ▸ Trust ▸ School) are different: they are
usually in `tenancy.entities_excluded`, carry no `tenant_id` column, and
have **no fence at all**. `all` on such an entity therefore meant "every
row of every tenant": a trust admin listing Schools saw every school of
every trust on the platform (reproduced live against a two-trust
dataset while investigating #1541).

The session's authority boundary already exists: since #1463 every
membership carries `partition_root_id` — the `archetype:tenant` root the
RLS rows are partitioned at — and the scope layer resolves
`current_user.tenant_id` to it.

## Decision

When a `scope:` rule's condition is `all` **and the entity itself is a
tenant kind** (declares `tenant_host:`), the linker compiles the rule to
the **partition-root subtree** instead of `Tautology`:

```
id = current_user.tenant_id                    -- the row IS the session root
OR <parent> = current_user.tenant_id           -- the row's parent is the root
OR <parent>.<parent> = current_user.tenant_id  -- deeper ancestors
```

walking the entity's own `tenant_host.parent` FK chain (the inverse of
the ADR-0036 self-or-ancestor expansion, which walks an FK *to* a kind).
A root kind (no `parent`) compiles to the single `id` check. Entities
that are not tenant kinds keep `Tautology` — no behaviour change.

Like the ADR-0036 expansion, this applies where the linker provides the
entity map: **READ and LIST scopes**. Write-verb `all` rules keep
`Tautology` (writes on tenant kinds should use explicit conditions; a
subtree write story needs the #1455 payload-probe machinery and is a
follow-up).

### Fail-closed properties

- A membership-less/anonymous session resolves `current_user.tenant_id`
  to the deny sentinel → impossible filter → zero rows.
- A broken or cyclic `parent:` chain stops the walk and keeps the legs
  built so far — a *narrower* predicate, never a broader one. Depth is
  bounded by the same `_MAX_TENANT_HIERARCHY_DEPTH` as ADR-0036.
- `dazzle db explain-scope <Kind> list` shows the compiled subtree.

### RLS

Tenant kinds in `entities_excluded` have no RLS policies; the subtree
predicate applies on the app-layer and in-process page paths (both run
the scope filters). A fenced tenant kind (one that *does* carry
`tenant_id`) compiles the same predicate through the Phase C scope-policy
path unchanged. Extending fence coverage to excluded anchors is out of
scope here.

## Consequences

- **Behaviour change**: apps relying on `all` to mean "platform-wide"
  on a tenant kind now get subtree rows. Platform-wide listings belong
  to admin personas (which bypass scopes) or an explicit non-kind
  reporting entity. AegisMark's workaround filter
  (`trust = current_user.trust`) remains valid and now redundant.
- The #1541 zero-rows report did not reproduce and is not this defect;
  the silent-empty observability fixes shipped alongside make any
  recurrence diagnosable (scope/permit denials and swallowed fetch
  errors are now logged, and an errored fetch renders distinct copy
  instead of the surface's `empty:` message).
