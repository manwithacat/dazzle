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
