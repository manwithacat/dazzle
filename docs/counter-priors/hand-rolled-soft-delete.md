---
id: hand_rolled_soft_delete
name: Hand-rolled soft-delete columns
layer: grammar
status: active
summary: >-
  `deleted_at: datetime optional` + per-surface `scope: deleted_at = null`
  rules + a custom DELETE handler is the corpus shape. Dazzle ships a
  `soft_delete:` keyword (#1218, v0.71.153) that auto-adds the column,
  applies the tombstone filter on list/read/aggregate, and rewrites DELETE
  to stamp instead of drop. Reach for the keyword; never the manual columns.
triggers_text:
  - "soft delete"
  - "is_deleted"
  - "deleted_at"
  - "archived_at"
  - "tombstone"
  - "logical delete"
  - "retention"
  - "undelete"
  - "restore deleted"
  - "mark as deleted"
triggers_code:
  - 'deleted_at\s*:\s*datetime'
  - 'is_deleted\s*:\s*bool'
  - 'archived_at\s*:\s*datetime'
refs:
  adrs: []
  kb_patterns:
    - prefer_soft_delete_keyword
  tests: []
---

# Hand-rolled soft-delete columns

## The corpus prior

The hand-rolled-tombstone-column pattern is canonical in Rails (the `paranoia` gem, `acts_as_paranoid`), Django (the `SoftDeletableModel` pattern), and every ORM tutorial that mentions "you don't actually want to lose data." Stack Overflow's top answers to "how do I soft-delete in <framework>" all show some variant of: add a `deleted_at` nullable timestamp, filter every read with `WHERE deleted_at IS NULL`, and override DELETE to stamp the column.

The pattern is widely copied because the mechanics are simple. The cost shows up later: every new surface has to remember the filter; every new aggregate has to remember the filter; every join across soft-deletable entities has to remember the filter on both sides. Forgetting it once is a data leak (deleted rows appear in a query they shouldn't); forgetting it twice across a join is a silent inconsistency.

## Wrong shape

```dsl
entity Document "Document":
  id: uuid pk
  title: str(200) required
  deleted_at: datetime optional   # the manual tombstone

surface document_list "Documents":
  uses entity Document
  mode: list
  scope: deleted_at = null         # remember the filter every time

surface document_detail "Document":
  uses entity Document
  mode: detail
  scope: deleted_at = null         # remember again

# ... and now write a custom DELETE handler that stamps deleted_at
#     instead of issuing SQL DELETE
```

Every new read surface, every new aggregate, every new joined query risks forgetting the `deleted_at = null` predicate. The filter is implicit in author intent ("show live rows") but explicit in every scope rule. The corpus pattern doesn't have a way to make the framework remember.

## Right shape

```dsl
entity Document "Document":
  soft_delete
  id: uuid pk
  title: str(200) required
  # `deleted_at: datetime optional` is auto-added by the linker.

surface document_list "Documents":
  uses entity Document
  mode: list
  # No scope: deleted_at = null. The framework filters tombstones at the
  # Repository layer for every read path.

# DELETE /api/document/<id> stamps deleted_at = NOW() instead of issuing
# a hard DELETE — soft-deleted rows become invisible to readers without
# leaving the table. URL parameter ?include_deleted=true bypasses the
# filter for admin / recovery surfaces.
```

The `soft_delete:` keyword composes with `scope:` predicates via the QueryBuilder, so author-supplied scopes don't double-filter. RBAC predicates compose cleanly. Aggregations honour the tombstone by default.

When to *not* reach for `soft_delete:`: if the lifecycle has multiple meaningful states (draft → published → archived → republished), that's a state machine, not a tombstone flag. Soft-delete is a single transition into "invisible-but-recoverable." A state machine is for multi-stage workflows.

## Why this matters here

The "remember the filter" cost compounds across surfaces, aggregates, scope rules, and joins. Every layer that touches a soft-deletable entity has the same implicit filter; making it explicit per-surface guarantees that *something*, somewhere, eventually forgets. The framework can hold the invariant centrally — the QueryBuilder applies the filter once, deterministically, for every read path.

This is the substrate at work: instead of relying on author discipline to apply the same predicate everywhere, encode the predicate in the substrate so the discipline isn't optional. The corpus pattern is the discipline-required form; the keyword is the discipline-enforced form.

## Cross-references

- `soft_delete:` keyword reference — `docs/reference/grammar.md`.
- Inference KB `prefer_soft_delete_keyword` — bootstrap auto-surfacing.
- Released in v0.71.153 (#1218).
