# Marketing Surface Conformance Checklist

This guide walks a Dazzle project through bringing its public-facing surface (marketing pages, legal pages, blog) into conformance with [ADR-0021](../adr/0021-marketing-via-sitespec.md). It is the prescribed remediation path for the #969 cookie-clearing regression class.

**Audience:** project owners (e.g. AegisMark) preparing for 1.0 stability or hunting auth flakiness on the same hostname as their app.

**Time:** 30–60 minutes for a project with ~10 marketing pages.

## What's at stake

The framework's site_routes (`src/dazzle_back/runtime/site_routes.py`) carefully maintain three invariants on marketing GETs:

1. **Cookie discipline** — never call `set_cookie` / `delete_cookie` on `dazzle_session` or `dazzle_csrf`
2. **CSRF middleware compatibility** — preserve framework-injected Set-Cookie headers
3. **Auth-aware nav rendering** — pass `is_authenticated` and `dashboard_url` into page context

When a project route override bypasses the framework's site router for a public path, it must re-implement these invariants correctly. The failure mode is severe: subsequent `/app/*` requests can return 403 because the marketing visit silently invalidated the user's session.

The fastest fix is to delete the project-side override and let the framework render the page from `sitespec.yaml`. Most marketing pages can be expressed in the existing `landing` / `markdown` / `legal` page types.

## Step 1 — Inventory project-side route overrides

```bash
grep -rn "# dazzle:route-override" routes/ 2>/dev/null | sort
```

Output is a list of every route your project has overridden. Categorise each:

| Path shape | Override status | Action |
|---|---|---|
| `/app/<entity>/...` | OK | App routes are project-scoped — overrides are the documented extension point |
| `/api/...`, `/auth/...`, `/webhooks/...` | OK | API/auth/webhooks are project-scoped |
| `/<marketing-path>` (e.g. `/about`, `/pricing`, `/demo`, `/blog/...`) | **Migrate** | Move to sitespec |
| `/<auth-required-non-app-path>` (e.g. `/preferences`, `/settings`) | **Audit** | See Step 4 |

## Step 2 — Migrate marketing overrides to sitespec

For each public-path override, find an equivalent sitespec page type:

| Original handler returns | Sitespec page type | Notes |
|---|---|---|
| Bespoke HTML with hero / sections | `type: landing` | Use `sections:` array — supports `hero`, `cta`, `card_grid`, `stats`, `split_content`, `markdown`, `media_band` |
| Static prose loaded from a markdown file | `type: markdown` with `source: { format: md, path: "..." }` | Path is relative to project root |
| Terms or Privacy policy | `type: legal` | Auto-wires the `[legal]` block in `dazzle.toml` |
| Dynamic content (e.g. DB-backed) | **Stop and file a framework issue** | Don't override — propose a new page type |

### Example — converting a route override

**Before** (project-side override at `routes/about_page.py`):

```python
# dazzle:route-override GET /about
"""Custom about page."""
from fastapi.responses import HTMLResponse
from fastapi import Request

async def handler(request: Request):
    return HTMLResponse("""
    <html><body>
        <h1>About AegisMark</h1>
        <p>...</p>
    </body></html>
    """)
```

**After** (`sitespec.yaml`):

```yaml
pages:
  - route: "/about"
    type: landing
    title: "About AegisMark"
    sections:
      - type: hero
        headline: "About AegisMark"
        subhead: "..."
      - type: markdown
        source:
          path: "pages/about.md"
          format: md
```

Then delete `routes/about_page.py` and move the prose into `pages/about.md`.

## Step 3 — Audit the remaining public-path overrides

If you have public-path overrides that genuinely cannot be expressed in sitespec (rare — most can), make sure each one:

| Check | How |
|---|---|
| Doesn't call `response.set_cookie` or `response.delete_cookie` | `grep -n "set_cookie\|delete_cookie" routes/<file>.py` should return zero hits |
| Doesn't construct a fresh `Response()` that drops inbound headers | If using `Response()` constructor, copy `request.headers` carefully or use `HTMLResponse(content=...)` |
| Reads auth via `current_user_id(request)` from `dazzle_back.runtime.auth` | Don't roll your own session lookup |
| Renders auth-aware nav (logged-in vs logged-out) | Use `render_in_app_shell(...)` if the page is auth-required, or sitespec's auth-aware nav if public |

If any check fails, that's likely the source of cookie-clearing or auth-state inconsistency.

## Step 4 — Audit auth-required non-app paths

Routes like `/preferences`, `/settings`, `/help` that need auth but aren't `/app/*` paths require care:

- **Use `render_in_app_shell`** (from `dazzle_back.runtime.shell`) so the page picks up the framework's sidebar / topbar / auth chrome
- **Redirect unauth via `RedirectResponse(url="/login?next=<path>", status_code=302)`** — match the framework's auth-redirect pattern exactly
- **Never** call `current_user.delete_cookie(...)` or similar — if you need to log the user out, link to `/auth/logout`

Example of a conforming `/preferences` stub:

```python
# dazzle:route-override GET /preferences
from dazzle_back.runtime.auth import current_user_id
from dazzle_back.runtime.shell import render_in_app_shell
from fastapi import Request
from fastapi.responses import RedirectResponse


async def handler(request: Request):
    if not current_user_id(request):
        return RedirectResponse(url="/login?next=/preferences", status_code=302)
    return render_in_app_shell(
        request,
        template="preferences.html",
        title="Preferences",
        active_nav_route="/preferences",
    )
```

This matches the pattern in `examples/.../preferences_stub.py` and never touches cookies.

## Step 5 — Remove custom session middleware

```bash
grep -rn "set_cookie\|delete_cookie\|Set-Cookie" --include="*.py" 2>/dev/null | grep -v __pycache__
```

In a properly conforming project, the only hits should be:

- `auth/` routes you're explicitly allowed to extend (none, in normal usage — auth is framework-provided)
- Tests
- Demo seeders (one-shot scripts that read external Set-Cookie, like AegisMark's `pipeline/demo/load_seed.py`)

Any project-side runtime code writing `dazzle_session` or `dazzle_csrf` is a bug. Delete it; the framework owns those cookies.

## Step 6 — Verify in dev

Boot your project locally with `dazzle serve --local`, then run this trace:

```bash
JAR=/tmp/conformance_test.txt
rm -f $JAR

# 1. Login
curl -s -c $JAR -X POST http://localhost:8765/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"<test-user>","password":"<password>"}' \
  -o /dev/null

# 2. Capture session cookie value
SESSION_BEFORE=$(grep dazzle_session $JAR | awk '{print $7}')
echo "session before marketing: $SESSION_BEFORE"

# 3. Visit each public page; verify no Set-Cookie touches dazzle_session
for path in / /about /pricing /how-it-works /evidence /for-schools; do
  echo "=== GET $path ==="
  curl -s -b $JAR -c $JAR -D - "http://localhost:8765${path}" -o /dev/null 2>&1 \
    | grep -i "^set-cookie:.*dazzle_session" \
    && echo "FAIL: $path emits Set-Cookie for dazzle_session" \
    || echo "OK: $path does not touch session cookie"
done

# 4. Verify session value unchanged
SESSION_AFTER=$(grep dazzle_session $JAR | awk '{print $7}')
[ "$SESSION_BEFORE" = "$SESSION_AFTER" ] \
  && echo "PASS: session cookie unchanged across marketing visits" \
  || echo "FAIL: session cookie value changed"

# 5. Verify app GET still works
curl -s -b $JAR -o /dev/null -w "post-marketing app GET: %{http_code}\n" \
  http://localhost:8765/app/<known-accessible-workspace>
```

Expected: every step prints OK / PASS, and the final app GET returns 200.

If any step fails, the failing path is your culprit. Apply Step 2/3/4 to that path.

## Step 7 — Run the framework's drift gates

After the migration:

```bash
pytest tests/unit/ -m "not e2e" -q
```

If you've registered any project-side site_routes overrides, the framework's drift suite may now flag them. That's the gate doing its job — fix the override or file a framework issue.

## Common failure modes you might find

### Override returns `Response(...)` instead of `HTMLResponse(...)`

`Response()` constructor doesn't pre-populate headers. If a downstream FastAPI dependency emits `Set-Cookie`, it lands on the response. Switch to `HTMLResponse(content=html_str)` or use the framework's `render_site_page(...)` / `render_in_app_shell(...)`.

### Override imports a third-party library that injects middleware

Libraries like `starlette-csrf` or `starlette-auth-toolkit` register their own middleware that touches cookies. Remove them — Dazzle's `CSRFMiddleware` and `AuthMiddleware` cover the same ground without conflict.

### Override fetches data from an external API and forwards Set-Cookie

If your handler does `httpx.get(...)` and returns the response body, make sure you're not also forwarding `Set-Cookie` from the upstream. Use `response.headers` slicing or `.json()` instead of `.content` to drop response headers.

### Override uses `app.add_middleware(...)` for project-specific concerns

Project-side middleware that wraps responses can interact badly with the framework's cookie injection. If you must add middleware, make it pure-additive — never modify or remove headers from outgoing responses.

## After conformance

Once the audit passes, remove the override files and commit the sitespec migration. Your CHANGELOG should note:

```markdown
### Changed
- Migrated marketing pages from project-side route overrides to
  sitespec.yaml entries (per dazzle ADR-0021). Closes the
  cookie-clearing regression class on the marketing surface (see
  dazzle#969 for the framework-side investigation).
```

Then redeploy and run your site-fuzz / persona harness — the 403-on-marketing-visit pattern should be gone.

## See also

- ADR-0021 — Marketing pages via sitespec (the policy this guide implements)
- ADR-0011 — SSR + HTMX architecture
- `src/dazzle_back/runtime/site_routes.py` — framework site router (the code path your sitespec entries flow through)
- `src/dazzle_back/runtime/shell.py` — `render_in_app_shell` for auth-required non-app pages
- [#969](https://github.com/manwithacat/dazzle/issues/969) — the regression that surfaced this guide
