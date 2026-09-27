# Trace a page URL to its DSL

Run `dazzle inspect page` from a Dazzle project, or pass `--project`:

```bash
dazzle inspect page /app/paymentattempt/123e4567-e89b-12d3-a456-426614174000 --project examples/invoice_ops
dazzle inspect page /app/workspaces/draft_releases --project examples/fieldtest_hub --json
```

The command reports the matching route pattern, the winning surface or
workspace, its DSL file and line, its module, and direct entity or surface
references. For an entity detail URL without an authored view surface, it
identifies the generated detail page and points to the entity declaration.
The lookup uses the linked AppSpec and the route ownership rules shared with
the page-context compiler, including collision winners. It creates no
HTML or route manifest in the project.

The path from source to browser is:

```text
DSL declaration → linked AppSpec → page route/context → typed Fragment renderer → HTML response
```

For a surface, `page/converters/template_compiler.py` builds the page context;
`http/runtime/page_routes.py` handles the request and dispatches the body to
`render/`. A workspace uses `page/runtime/workspace_renderer.py` for its
regions before the same app-shell rendering step. These are framework
functions shared by pages, not generated per-app HTML templates.

For example, `/app/paymentattempt/<uuid>` resolves to the
`payment_attempt_detail` surface in `invoice_ops.payments`, which reads the
`PaymentAttempt` entity. `/app/workspaces/draft_releases` resolves to the
`draft_releases` workspace in `fieldtest_hub.firmware`, which reads
`FirmwareRelease` and links to `firmware_release_edit`.

## See the HTML from a running app

```bash
dazzle inspect page /app/paymentattempt/123e4567-e89b-12d3-a456-426614174000 -p examples/invoice_ops --html
```

`--html` sends a read-only GET to `http://localhost:3000` and prints the
response after the explanation. Pass a full URL to fetch a different origin,
or `--origin` with a relative path. `--json --html` includes the response as
the `html` field. The HTML reflects that server's current data, auth state,
theme, and request headers. It is an observation, not a maintained template.
The DSL and AppSpec remain the source of truth for what the route means.

For a page that needs authentication, provide a local JSON file of request
headers with `--headers-file`. The command reads the headers only for this
request and never prints them. It refuses to present a login redirect or a
non-HTML response as the requested page.

## Trace one workspace region

```bash
dazzle inspect page /app/workspaces/engineering_dashboard \
  -p examples/fieldtest_hub --region triage_pressure --json
```

`--region` adds the region's source declaration, filter and sort IR, limit,
workspace access rule, source entity's list permission and scope IR, registered
fragment GET, action surface, action page
route, and form submission method/URL when the action is a create or edit
surface. With `--html`, the command reads both the full page and the region's
live HTML, returning `html` and `region_html` in JSON mode. The same request
headers are sent to both GETs. Neither GET performs the mutation.

The trace follows the existing runtime: the page handler checks workspace
persona access; the region handler independently resolves identity, applies
filter and entity scope, fetches rows, and renders a typed fragment. The
action route opens a form whose `hx-post` or `hx-put` submits to the API.
The output describes declared access, not whether a particular user will
pass those checks. Compare the two live HTML responses when you need to
verify the current user's result. See the Fieldtest Hub walkthrough in
`dev_docs/agent-first-experiments/trace.md`.

The static explanation describes Dazzle's AppSpec route projection. A custom
route override can take precedence at runtime; the live HTML response reveals
what the running app actually returned. Use `dazzle inspect routes --runtime`
when you need the complete mounted route table, including extensions. API,
auth, and marketing URLs are outside `inspect page` because they are not
AppSpec surface or workspace pages.
