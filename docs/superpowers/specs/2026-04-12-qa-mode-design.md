# QA Mode — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Issue:** manwithacat/dazzle#768

## Goal

Turn Dazzle example apps into first-class tools for human QA evaluation. When a tester runs `dazzle serve --local` on an example, the landing page should guide them through exploring the app as different personas, without needing to create users, tenants, or type credentials.

## Non-goals

- Production authentication changes beyond adding a general magic link consumer endpoint
- Changes to existing examples' sitespec files (QA section is runtime-injected)
- Persistent dev tooling (no Django Debug Toolbar-style fixed panel)
- Dev-only auth backdoors (rejected — we use the real magic link system)

## User Story

1. Tester sets `DATABASE_URL` and `REDIS_URL` (or puts them in `.env` — #769)
2. Tester runs `cd examples/ops_dashboard && dazzle serve --local`
3. Server startup auto-provisions a dev user per DSL persona in a dev tenant
4. Startup banner prints the provisioned personas and a QA-mode warning
5. Tester opens `http://localhost:3462/`
6. Landing page shows hero → **QA Personas section** → features → ... (rest of sitespec)
7. QA Personas section shows one card per persona with role, description, sample stories, and a "Log in as X" button
8. Tester clicks "Log in as Accountant"
9. Browser fires `POST /qa/magic-link` (dev-gated), gets `{url: "/auth/magic/<token>"}`, redirects
10. Magic link consumer validates the token, creates a session, redirects to the home page
11. Tester is now logged in as the Accountant persona and can explore the app

## Decisions

### 1. Scope

**Full contract.** This change spans three layers:
- **CLI/runtime:** .env loading (already shipped in #769), persona provisioning, QA mode environment flag
- **Backend auth:** general-purpose `GET /auth/magic/{token}` consumer endpoint, dev-gated `POST /qa/magic-link` generator
- **Frontend:** new sitespec `qa_personas` section type, template, runtime injection into landing page

### 2. QA personas source

**Auto-derived from DSL personas.** Every `persona X:` block in the DSL becomes a dev user with:
- Email: `{persona_id}@example.test` (RFC2606 reserved TLD)
- No password (magic link only)
- Role: matching the persona's DSL role definition
- Tenant: dev tenant (created if missing)

Rationale: zero config, works for existing example apps without edits. The DSL already knows the personas; duplicating them in sitespec is boilerplate.

### 3. Login flow

**Magic links with no auth backdoor.** The login button on each persona card:
1. Fires `POST /qa/magic-link` with `{persona_id: "accountant"}` (dev-gated endpoint)
2. Server calls existing `create_magic_link(store, user_id=..., ttl_seconds=60)` primitive
3. Returns `{url: "/auth/magic/<token>"}`
4. Browser redirects to the consumer endpoint
5. Consumer endpoint (production-safe) validates via existing `validate_magic_link` primitive, creates a session, redirects home

Rationale: reuses the existing magic link crypto (32-byte token, one-time use, expiry). No parallel auth path. The only "dev" aspect is that the generator endpoint is authentication-free; the consumer is identical to what email-based passwordless login would use in production.

### 4. Magic link endpoint mounting

- **Consumer `GET /auth/magic/{token}`:** mounted unconditionally. General-purpose primitive. Production apps can use it for email-based passwordless login without further changes.
- **Generator `POST /qa/magic-link`:** dev-gated. Double-check: `DAZZLE_ENV=development` AND `DAZZLE_QA_MODE=1`. The serve command sets `DAZZLE_QA_MODE=1` when `--local` is active. Endpoint is never mounted in production builds.

### 5. Password strategy for dev personas

**No passwords.** Dev personas have no password set. Access is magic-link only, and magic links require hitting the dev-gated generator endpoint. This means:
- Brute force is impossible — no password to guess
- Access requires dev endpoint exposure (which requires `DAZZLE_ENV=development` AND `DAZZLE_QA_MODE=1`)
- The dev tenant is isolated from production tenants
- No leaked dev passwords in CI logs or screenshots

### 6. QA panel placement

**Dedicated sitespec section between hero and features.** New `qa_personas` section type, runtime-injected by the landing page renderer when `DAZZLE_QA_MODE=1`. Fits the "landing page is the QA entry point" framing and reuses existing sitespec rendering patterns.

### 7. Tenant scoping

**Single dev tenant.** All personas share one tenant. Tenant-specific examples still work (the dev tenant has its own ID). Production tenants are never touched.

### 8. Failure handling

**Non-blocking.** If provisioning fails (db connection, missing role, etc.), print a warning and continue serving. The QA panel just doesn't render. Never block the dev workflow over a setup error.

## Files Changed

| Layer | File | Action |
|---|---|---|
| Backend | `src/dazzle_back/runtime/auth/magic_link_routes.py` | Create — `GET /auth/magic/{token}` |
| Backend | `src/dazzle_back/runtime/auth/__init__.py` (or auth router setup) | Modify — register consumer route |
| Backend | `src/dazzle_back/runtime/qa_routes.py` | Create — `POST /qa/magic-link` dev-gated |
| Backend | FastAPI app factory (grep for `include_router` + `auth` in `src/dazzle_back/runtime/`) | Modify — conditionally include qa_router with the env gate |
| CLI | `src/dazzle/cli/runtime_impl/serve.py` | Modify — call `_provision_dev_personas()`, set `DAZZLE_QA_MODE=1`, print startup banner |
| CLI | `src/dazzle/cli/runtime_impl/dev_personas.py` | Create — persona enumeration + idempotent user creation |
| Site | `src/dazzle_ui/specs/sitespec.py` | Modify — add `qa_personas` section type |
| Site | `src/dazzle_ui/runtime/template_context.py` | Modify — `QAPersonaCard`, `QAPersonasSection` models |
| Site | `src/dazzle_ui/templates/site/sections/qa_personas.html` | Create — card grid template |
| Site | `src/dazzle_ui/runtime/page_routes.py` (landing renderer) | Modify — runtime-inject QA section when env flag is set |
| Tests | `tests/unit/test_magic_link_routes.py` | Create — consumer endpoint tests |
| Tests | `tests/unit/test_qa_routes.py` | Create — generator endpoint tests (gated + un-gated behaviour) |
| Tests | `tests/unit/test_dev_personas.py` | Create — provisioning tests |

## Component Designs

### CLI: persona provisioning

New module `src/dazzle/cli/runtime_impl/dev_personas.py`:

```python
"""Dev persona provisioning for QA mode (#768).

Called from serve_command when --local is active. Creates a dev user for
each DSL persona so testers can log in as any of them via magic links.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.core.ir import AppSpec


@dataclass
class ProvisionedPersona:
    """A dev user that was provisioned (or already existed) for a persona."""
    persona_id: str
    display_name: str
    role: str
    email: str
    user_id: str
    description: str
    stories: list[str]


def provision_dev_personas(
    appspec: AppSpec,
    user_service: Any,
    tenant_service: Any,
) -> list[ProvisionedPersona]:
    """Ensure a dev user exists for every DSL persona. Idempotent.

    Returns the list of (new or existing) dev personas for the QA panel.
    Failures are logged but don't raise.
    """
    personas = getattr(appspec, "personas", []) or []
    if not personas:
        return []

    # Ensure dev tenant exists
    dev_tenant_id = _ensure_dev_tenant(tenant_service)

    provisioned: list[ProvisionedPersona] = []
    for persona in personas:
        email = f"{persona.id}@example.test"
        try:
            user = user_service.get_by_email(email, tenant_id=dev_tenant_id)
            if user is None:
                user = user_service.create(
                    email=email,
                    display_name=persona.name or persona.id.replace("_", " ").title(),
                    role=persona.role,
                    tenant_id=dev_tenant_id,
                    password=None,  # magic link only
                )
            provisioned.append(
                ProvisionedPersona(
                    persona_id=persona.id,
                    display_name=persona.name or persona.id.replace("_", " ").title(),
                    role=persona.role,
                    email=email,
                    user_id=str(user.id),
                    description=_derive_description(persona),
                    stories=_derive_stories(appspec, persona.id),
                )
            )
        except Exception as err:
            import sys
            print(f"Warning: failed to provision dev persona '{persona.id}': {err}", file=sys.stderr)
            continue

    return provisioned


def _ensure_dev_tenant(tenant_service: Any) -> str:
    """Create or retrieve the shared dev tenant ID."""
    # Implementation depends on tenant service API — see existing
    # `dazzle tenant create` CLI command for the pattern.
    ...


def _derive_description(persona) -> str:
    """Return persona description from DSL or auto-generate from scope rules."""
    if getattr(persona, "description", None):
        return persona.description
    # Auto-generate from scope rules
    scopes = getattr(persona, "scopes", []) or []
    if not scopes:
        return f"Full access to the application"
    return "Row-level access based on scope rules"


def _derive_stories(appspec: AppSpec, persona_id: str) -> list[str]:
    """Return up to 2 story titles that reference this persona."""
    stories = getattr(appspec, "stories", []) or []
    relevant = [s for s in stories if persona_id in (getattr(s, "personas", []) or [])]
    return [s.title or s.id for s in relevant[:2]]
```

### Backend: magic link consumer

New file `src/dazzle_back/runtime/auth/magic_link_routes.py`:

```python
"""HTTP routes for magic link authentication.

Exposes the consumer endpoint GET /auth/magic/{token}. The token
validation primitives live in magic_link.py — this module only wires
them to HTTP.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from dazzle_back.runtime.auth.magic_link import validate_magic_link

router = APIRouter(tags=["auth"])


@router.get("/auth/magic/{token}")
async def consume_magic_link(token: str, request: Request) -> RedirectResponse:
    """Validate a magic link token and create a session.

    One-time use, expiry-gated. On success: creates session, redirects
    to ?next=... or /. On failure: redirects to /auth/login with an
    error query param.
    """
    store = request.app.state.auth_store
    session_service = request.app.state.session_service

    user_id = validate_magic_link(store, token)
    if user_id is None:
        return RedirectResponse(
            url="/auth/login?error=invalid_magic_link",
            status_code=303,
        )

    # Create session using the same code path as password login
    session_token = session_service.create_session(user_id=user_id)

    # Honour ?next= if present and same-origin
    next_url = request.query_params.get("next", "/")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        key="dazzle_session",
        value=session_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response
```

### Backend: dev-gated generator

New file `src/dazzle_back/runtime/qa_routes.py`:

```python
"""Dev-only QA mode endpoints. Never mount in production.

This module is imported and its router registered ONLY when both:
- DAZZLE_ENV=development
- DAZZLE_QA_MODE=1

The serve command sets DAZZLE_QA_MODE=1 when --local is active.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dazzle_back.runtime.auth.magic_link import create_magic_link

router = APIRouter(tags=["qa"])


class MagicLinkRequest(BaseModel):
    persona_id: str


class MagicLinkResponse(BaseModel):
    url: str


@router.post("/qa/magic-link")
async def generate_qa_magic_link(
    body: MagicLinkRequest,
    request: Request,
) -> MagicLinkResponse:
    """Generate a magic link for a provisioned dev persona.

    Double-checks env gating at request time in case of misconfiguration.
    Returns 404 if the feature is disabled or the persona doesn't exist.
    """
    if os.environ.get("DAZZLE_ENV") != "development":
        raise HTTPException(status_code=404)
    if os.environ.get("DAZZLE_QA_MODE") != "1":
        raise HTTPException(status_code=404)

    store = request.app.state.auth_store
    user_service = request.app.state.user_service

    email = f"{body.persona_id}@example.test"
    user = user_service.get_by_email(email, tenant_id="dev")
    if user is None:
        raise HTTPException(status_code=404, detail="persona not provisioned")

    token = create_magic_link(
        store,
        user_id=str(user.id),
        ttl_seconds=60,  # short TTL — used immediately
        created_by="qa_panel",
    )

    import logging
    logging.warning(
        "[QA MODE] Magic link generated for persona '%s'",
        body.persona_id,
    )

    return MagicLinkResponse(url=f"/auth/magic/{token}")
```

### Site: sitespec section type

Modify `src/dazzle_ui/specs/sitespec.py` to add `qa_personas` to the section enum. This doesn't need to be author-declarable — it's runtime-injected — but the section type must be registered so the template renderer can dispatch to the right template.

### Site: template

New file `src/dazzle_ui/templates/site/sections/qa_personas.html`:

```html
{# QA Personas section — rendered only in local dev mode when DAZZLE_QA_MODE=1 #}
<section class="py-16 px-6 max-w-6xl mx-auto">
  <div class="text-center mb-10">
    <div class="inline-flex items-center gap-2 px-3 py-1 mb-4
                rounded-full bg-amber-100 text-amber-900 text-[11px] font-medium uppercase tracking-wide">
      <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 2L2 18h16L10 2zm0 5l5 9H5l5-9z"/>
      </svg>
      Local Dev Mode — not visible in production
    </div>
    <h2 class="text-3xl font-semibold tracking-tight mb-3">{{ section.headline }}</h2>
    <p class="text-base text-[hsl(var(--muted-foreground))] max-w-2xl mx-auto">{{ section.subtitle }}</p>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {% for persona in section.personas %}
    <article class="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-5
                    transition-[border-color] duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
                    hover:border-[hsl(var(--border-strong),var(--border))]">
      <div class="flex items-start justify-between mb-3">
        <h3 class="text-[15px] font-medium tracking-[-0.01em]">{{ persona.name }}</h3>
        <span class="px-2 py-0.5 rounded-full bg-[hsl(var(--muted))] text-[11px] font-medium text-[hsl(var(--muted-foreground))]">
          {{ persona.role }}
        </span>
      </div>
      <p class="font-mono text-[11px] text-[hsl(var(--muted-foreground))] mb-3">{{ persona.email }}</p>
      <p class="text-[13px] text-[hsl(var(--foreground))] mb-3">{{ persona.description }}</p>
      {% if persona.stories %}
      <ul class="text-[12px] text-[hsl(var(--muted-foreground))] mb-4 space-y-1">
        {% for story in persona.stories %}
        <li class="flex items-start gap-1.5">
          <span class="text-[hsl(var(--muted-foreground))]">→</span>
          <span>{{ story }}</span>
        </li>
        {% endfor %}
      </ul>
      {% endif %}
      <button
        type="button"
        data-qa-login-persona="{{ persona.id }}"
        class="w-full h-9 px-3 rounded-[4px] text-[13px] font-medium
               bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]
               transition-colors duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
               hover:opacity-90">
        Log in as {{ persona.name }}
      </button>
    </article>
    {% endfor %}
  </div>
</section>

<script>
(function() {
  document.querySelectorAll('[data-qa-login-persona]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const personaId = btn.dataset.qaLoginPersona;
      btn.disabled = true;
      btn.textContent = 'Logging in...';
      try {
        const resp = await fetch('/qa/magic-link', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({persona_id: personaId}),
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (data.url) {
          window.location.href = data.url;
        } else {
          throw new Error('No URL in response');
        }
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Error — try again';
        console.error('QA magic link failed:', err);
      }
    });
  });
})();
</script>
```

### CLI: serve command wiring

In `src/dazzle/cli/runtime_impl/serve.py` `serve_command`, after infrastructure validation and before starting the server:

```python
if local:
    # Enable QA mode for the running process
    os.environ["DAZZLE_QA_MODE"] = "1"
    os.environ.setdefault("DAZZLE_ENV", "development")

    # Provision dev personas (idempotent)
    from dazzle.cli.runtime_impl.dev_personas import provision_dev_personas
    try:
        provisioned = provision_dev_personas(appspec, user_service, tenant_service)
    except Exception as err:
        provisioned = []
        typer.echo(f"Warning: dev persona provisioning failed: {err}", err=True)

    if provisioned:
        typer.echo()
        typer.echo("⚠ QA MODE ACTIVE")
        typer.echo("  Dev-only endpoint /qa/magic-link is mounted.")
        typer.echo("  Any request can create a session for any provisioned persona.")
        typer.echo("  This mode is ONLY intended for local QA testing.")
        typer.echo("  Never expose this server to untrusted networks.")
        typer.echo()
        typer.echo(f"Dev Personas ({len(provisioned)})")
        for p in provisioned:
            typer.echo(f"  {p.display_name:<20} → {p.email}")
        typer.echo()

    # Stash provisioned personas so the landing page renderer can pick them up
    app.state.qa_personas = provisioned
```

### Frontend: runtime injection of QA section

In the landing page renderer, where sitespec sections are assembled:

```python
if os.environ.get("DAZZLE_QA_MODE") == "1" and hasattr(request.app.state, "qa_personas"):
    provisioned = request.app.state.qa_personas
    if provisioned:
        qa_section = QAPersonasSection(
            personas=[
                QAPersonaCard(
                    id=p.persona_id,
                    name=p.display_name,
                    role=p.role,
                    email=p.email,
                    description=p.description,
                    stories=p.stories,
                )
                for p in provisioned
            ]
        )
        # Insert after hero (index 1) or at start if no hero
        insert_idx = 1 if sections and sections[0].kind == "hero" else 0
        sections.insert(insert_idx, qa_section)
```

## Quality Gates

1. **Persona provisioning is idempotent** — running `serve --local` twice doesn't create duplicate users. Test with a fresh dev tenant.
2. **QA section only appears in local mode** — start server without `--local`, verify landing page has no `qa_personas` section in the HTML output.
3. **Magic link consumer rejects replayed tokens** — generate a token, consume it, attempt to consume again, verify 303 redirect to `/auth/login?error=invalid_magic_link`.
4. **Dev-gated endpoint returns 404 without env flags** — unset `DAZZLE_QA_MODE`, verify `POST /qa/magic-link` returns 404 regardless of payload.
5. **End-to-end QA flow** — Playwright test: navigate to landing, click "Log in as X" button, verify redirect lands on home page with session cookie set.

## Open Questions for Follow-ups

- **Dev persona photos/avatars** — could scrape `picsum.photos` or generate identicons for the cards. Deferred.
- **Reset data between QA runs** — a "Reset test data" button in the QA panel that re-runs demo data seeding. Separate feature.
- **Multi-tenant example apps** — some examples may have multiple tenants by design (e.g. a B2B app with test orgs). For v1, dev tenant is singular; multi-tenant dev is a follow-up.
- **Remember-me for persona switching** — quick persona switcher in the app header when QA mode is active. Nice-to-have.
- **Custom credentials via sitespec** — hybrid path where `sitespec.yaml` can override the auto-derived credentials with explicit emails/passwords. Only needed if auto-derived causes real friction.
