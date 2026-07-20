# Recipe: API setup then UI click (scene walks)

**Audience:** apps with multi-step jobs (VAT approve, sign, upload).
**Related:** #1638 walk core · #1639 `api_*` extensions.

## Pattern

Idempotent **HTTP setup** → **Playwright subject-bearing click** → **API assert**:

```yaml
persona: customer
scenes:
  - id: approve_item
    story: ST-215
    entry: /app/vatreturn/{vat_id}
    actions:
      - type: api_find
        path: /vatreturns
        where: { period_key: "26A1" }
        company_name_contains: "Demo · Briar"
        prefer_status: awaiting_client_approval
        save_as: vat_id
      - type: api_ensure_status
        path_template: /vatreturns/{vat_id}
        status: awaiting_client_approval
      - type: navigate
      - type: assert_http_ok
      - type: playwright_click
        role: button
        name: "Approve"
        regex: true
      - type: api_assert_field
        path_template: /vatreturns/{vat_id}
        field: status
        equals: client_approved
```

## Commands

```bash
dazzle test walk validate -m .
dazzle test walk run -w vat_approve_customer -u $URL --playwright
dazzle test walk pack-dry-run --pack A --execute -u $URL
dazzle docs claims check --run -u $URL
```

Showcase apps should keep **core-only** walks:

```bash
dazzle test walk run -m examples/simple_task/dazzle.toml --core-only --dry-run
```

## Seed honesty

`api_ensure_status` resets rows to a known state so re-runs stay green.
Prefer story seeds (#1626) over faker for `api_find` filters.


## CSRF (required on live Dazzle apps)

Mutating `api_*` actions need the same browser-parity CSRF as the rest of
the runtime:

| Cookie | Header |
|--------|--------|
| `dazzle_csrf` | `X-CSRF-Token: <same>` |

The walk runner primes the cookie after auth and attaches the header on
POST/PUT/PATCH/DELETE automatically. Do **not** disable CSRF for walk
paths in production.


## CyFuture Pack A lessons (framework-only)

1. Body / path templates use **`{save_as}`** placeholders (not `@save_as`).
2. Resolve related rows with `api_find` before `api_post` when the API needs FKs.
3. Upload field default is **`file`** (`file_field: file`); **`save_as`** is filled from the JSON `id` in the upload response.
4. Prefer seed/sanitize for known states; use `api_ensure_status` only when re-runs need a reset.
5. Pack execute auto-enables Playwright when walks contain `playwright_*`.
