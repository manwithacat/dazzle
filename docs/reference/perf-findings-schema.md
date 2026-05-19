# `dazzle perf report --format json` schema

The JSON payload is a serialisation of `dazzle.perf.findings.types.FindingsReport`.

```json
{
  "run_id": "string",
  "app_name": "string | null",
  "started_at": "ISO 8601 string",
  "ended_at": "ISO 8601 string | null",
  "slow_endpoints":  [ { "route": "GET /tasks", "calls": 12, "total_ms": 4200.0, "p95_ms": 380.0 } ],
  "slow_queries":    [ { "statement": "SELECT FROM task", "calls": 12, "total_ms": 1100.0 } ],
  "n_plus_one":      [ { "parent_span": "GET /tasks", "child_statement": "SELECT FROM user", "repetitions": 24 } ],
  "slow_phases":     [ { "name": "aggregate.build_sql", "calls": 8, "total_ms": 120.0, "max_ms": 30.0 } ],
  "render_fanout":   [ { "route": "GET /tasks", "region_renders": 18, "total_ms": 600.0 } ],
  "boot_cost":       { "parse_dsl_ms": 240.0, "route_gen_ms": 80.0, "total_ms": 320.0 } ,
  "exceptions":      [ { "span_name": "repo.aggregate", "message": "bad SQL", "count": 1 } ]
}
```

Note: `boot_cost` may be `null` when neither `dsl.parse` nor `route.gen` spans fired.

## Stability

The field names and shapes here are the public contract. Renaming or
removing a field requires:

1. CHANGELOG entry under **Changed** or **Removed**.
2. Update of this doc in the same commit.
3. Discussion on whether to bump the schema-version key (none today —
   add one when the first breaking change lands).
