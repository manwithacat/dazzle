# shared_parent_aggregate

Framework-validation fixture for the **shared-parent JOIN** pattern
documented in [#1216](https://github.com/manwithacat/dazzle/issues/1216)
and tracked by the [#1217](https://github.com/manwithacat/dazzle/issues/1217)
3NF audit (Pattern 4).

This is **not a user-facing example app** — it's an abstract probe used
by `tests/unit/test_shared_parent_aggregate_fixture.py` and the
inference-KB retrieval gate. The schema is deliberately minimal so the
diamond shape is obvious.

## Shape

```
        Person  ← shared parent (pivot)
         ▲ ▲
         │ │
         │ └── Contribution.person       (the entity we aggregate over)
         └─── ProjectMember.person      (the cohort source row)
```

`ProjectMember` and `Contribution` do **not** FK to each other directly.
Both reference `Person`. The canonical pattern for "for each project
member, show the count of their contributions" is the `share:` keyword
on a `cohort_strip`'s `primary_aggregate`.

## DSL excerpt

```dsl
project_members:
  source: ProjectMember
  display: cohort_strip
  cohort_strip_config:
    member_via: id
    lenses:
      - id: contribution_count
        label: "Contributions"
        primary_aggregate:
          aggregate: count(Contribution)
          share: Person
```

The framework finds the `person` ref on `ProjectMember` and the
`person` ref on `Contribution`, both pointing at `Person`, and joins
on equality of those FK columns — no `via:` junction needed because
the source IS the row we're grouping by.

If you write a schema where either side has multiple `ref Person`
fields, the compute path refuses with an "ambiguous" warning rather
than silently picking one.
