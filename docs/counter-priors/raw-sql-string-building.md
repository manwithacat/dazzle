---
id: raw_sql_string_building
name: Raw SQL string-building in user code
layer: inference
status: active
summary: >-
  String concatenation or f-string interpolation to build SQL — `f"SELECT *
  FROM orders WHERE id = {order_id}"` — inside user-authored Python in `app/`.
  Framework paths parameterise by construction (predicate algebra, Repository
  helpers); user code can still reach for raw strings, and a 25-year-old known
  injection class then ships unobserved.
triggers_text:
  - "raw SQL"
  - "build the query"
  - "execute SQL"
  - "string SQL"
  - "concat SQL"
  - "format the query"
  - "f-string SQL"
  - "interpolate into the query"
triggers_code:
  - "execute\\s*\\(\\s*f[\"']"
  - "execute\\s*\\(\\s*[\"'][^\"']*\\+"
  - "cursor\\.execute\\s*\\(\\s*[\"'][^\"']*%"
  - "\\.execute\\(.+\\.format\\("
refs:
  adrs:
    - ADR-0009
  tests:
    - tests/unit/test_python_audit_raw_sql_string_building.py
detectors:
  - id: PA-LLM-11
    agent: PA
    note: >-
      Fires on `.execute(...)` calls whose first positional arg is built
      via f-string, string-concat (`+`), `%`-format on a SQL literal, or
      `"...{}".format()` on a SQL literal. Bare string literals
      (`cur.execute("SELECT 1")`) are parameter-free and safe.
      Identifier arguments (`cur.execute(query)`) and parameterised calls
      (`cur.execute("... %s ...", (val,))`) are NOT flagged — data-flow
      tracking on identifiers is out of scope, and parameterisation is
      the canonical right shape.
---

# Raw SQL string-building in user code

## The corpus prior

A staggering amount of training-corpus Python and Ruby code uses string concatenation or interpolation to build SQL. Stack Overflow answers, "quick script" tutorials, and "let's bypass the ORM for performance" blog posts all default to f-strings or `+` operators for SQL. SQL injection has been a known vulnerability class for over twenty years; the corpus still teaches the unsafe shape because the unsafe shape looks shorter and the tutorial examples never use untrusted input.

LLMs emit the corpus shape. Worse: in user app code (`app/sync/`, `app/db/`, one-shot scripts in `scripts/`), the framework's substrate doesn't catch it. The Repository's predicate algebra is unreachable from `.execute(...)`, so the moment an agent reaches for raw SQL, the substrate's safety guarantees stop applying.

## Wrong shape

```python
# app/db/admin_reports.py
def get_overdue_invoices(tenant_id: str) -> list[dict]:
    sql = f"SELECT * FROM invoice WHERE tenant_id = '{tenant_id}' AND due_date < NOW()"
    with connection.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

# scripts/migrate_tags.py
def rename_tag(old_name: str, new_name: str):
    cur.execute(
        "UPDATE tag SET name = '" + new_name + "' WHERE name = '" + old_name + "'"
    )
```

The first example accepts a `tenant_id` straight off the wire and interpolates it into the SQL. A request with `tenant_id="' OR '1'='1"` reads every row in the table. The second example does the same with two parameters.

These aren't theoretical. Every real-world SQL injection breach started with somebody convinced the input was already-sanitised, or that this particular code path "won't ever receive untrusted input."

## Right shape

1. **Stay in the substrate by default.** `Repository.list`, `Repository.aggregate`, `Repository.get` already handle the scope-predicate-to-SQL compilation. Anything that fits the predicate algebra (ADR-0009) should compile through it.
2. **When the query genuinely doesn't fit the algebra**, use parameterised execution — pass the values as a separate argument, not as part of the SQL string.

```python
# app/db/admin_reports.py
def get_overdue_invoices_v2(tenant_id: str) -> list[Invoice]:
    return invoice_repo.list(
        scope={
            "tenant_id": tenant_id,        # scope-validated against the FK graph
            "due_date__lt": utcnow(),
        }
    )

# scripts/migrate_tags.py — when you really do need raw SQL
def rename_tag_v2(old_name: str, new_name: str):
    cur.execute(
        "UPDATE tag SET name = %s WHERE name = %s",
        (new_name, old_name),  # parameterised, not interpolated
    )
```

The first form goes through the substrate — scope rules, FK validation, predicate algebra all apply. The second form, when you've genuinely reached the limit of the substrate (rare in practice), uses the database driver's parameter substitution. The driver does the escaping; the SQL string remains a literal with placeholders.

If you find yourself reaching for raw SQL frequently: that's a signal the Repository helpers are missing a shape, not that you should reach for strings. File an issue.

## Why this matters here

Dazzle's predicate algebra (ADR-0009) is the substrate's promise that every authorised read is bounded by the user's scope. The promise depends on every SQL-generating path going through the algebra. Raw SQL in `app/` code bypasses the algebra and silently breaks the promise — a row-level-security guarantee that holds for 99% of the application becomes "holds for 99% of the application except in `app/db/admin_reports.py`, which nobody is checking."

The substrate's value emerges when it covers the whole codebase. The first raw-SQL escape hatch is the one that erodes the guarantee everywhere downstream.

## Cross-references

- ADR-0009 (predicate algebra) — the substrate-side closure that user-code raw SQL bypasses.
- `src/dazzle/http/runtime/repository.py` — Repository helpers that should cover ~all real read patterns.
- The `awesome-secure-defaults` list (Helmet, secure-by-construction libraries) recommends the same approach industry-wide; raw SQL string-building is the canonical example.
