# Analytics, Consent & Privacy Compliance

**Date**: 2026-04-24
**Status**: Design
**Scope**: Provider-agnostic analytics integration + GDPR-grade consent + auto-generated privacy artefacts

## Motivation

Dazzle users are asking for first-class Google Tag Manager (GTM) and Google Analytics (GA4) support. The requested shape: "declare the GTM ID in `dazzle.toml`, and pages are automatically instrumented; the framework emits useful events." The underlying request is broader: **make product analytics a framework capability, not a per-app integration**.

A naive implementation — drop a GTM `<script>` tag in the base template — would make existing apps immediately non-compliant with GDPR Consent Mode v2 (mandatory in the EU since March 2024) and would leak user PII into third-party systems without consent. Given Dazzle's compliance positioning (ISO 27001 + SOC 2 + provable RBAC), shipping a feature that silently breaks data-protection law is anti-thematic.

This spec proposes an integrated design covering:

1. A provider-agnostic analytics primitive with GTM as first implementation.
2. A framework-owned consent banner with Consent Mode v2 support.
3. PII annotation on entity fields — a new DSL modifier.
4. Subprocessor declarations — a new DSL construct that doubles as privacy-policy source.
5. Auto-generated privacy page, cookie policy, and GDPR Record of Processing Activities (ROPA) from the same source of truth that feeds the SOC 2 / ISO 27001 compliance pipeline.
6. Per-tenant analytics scoping.
7. Server-side event emission via the existing event bus.

The PII annotation is probably the highest-leverage piece independently of analytics — it gives the compliance pipeline structured knowledge about what personal data the app handles.

## Goals

- **Compliance by default.** EU-tenant apps must not fire analytics scripts before consent is granted. Non-EU tenants may opt for opt-out consent.
- **No vendor lock-in.** The abstraction must accommodate GTM, GA4 direct, Plausible, Fathom, PostHog, Segment, and "custom dataLayer" from day one — even if only GTM ships in v0.61.0.
- **Per-tenant scoping.** A multi-tenant Dazzle SaaS must be able to route analytics per tenant (tenant A → GTM-ABC, tenant B → GTM-DEF, tenant C → no analytics).
- **Versioned event contract.** Auto-emitted events are a public API. The event vocabulary is versioned and stable; additions are additive.
- **PII-safe defaults.** No entity IDs, user IDs, email addresses, or free-text fields appear in events unless the DSL explicitly opts in per surface.
- **htmx-native.** Navigation events fire on `htmx:afterSwap`, not just full page loads.
- **Disabled in dev / trial / qa by default.** Automated agents must not pollute production analytics.

## Non-goals

- **v0.61.0 will not ship framework-usage telemetry.** Dazzle itself does not collect stats about its own use in this release. Out of scope.
- **No built-in A/B testing or feature-flag integration** — downstream concern, not an analytics-platform concern.
- **No replacement for application observability.** Analytics ≠ ops telemetry. The existing activity log + audit trail + event bus remain primary for ops. Analytics targets *business / product* metrics.
- **No custom UI/UX builder for the consent banner** — Dazzle owns the banner's structure and semantics; theme tokens control appearance. Users who need radical customisation can fork.

## Architecture Overview

```
 ┌───────────────┐    render-time    ┌──────────────────┐
 │ DSL analytics │ ───────────────▶  │ site_base.html   │
 │   primitive   │                   │ (tenant-resolved │
 └───────────────┘                   │  GTM/GA snippet) │
                                     └──────────────────┘
                                              │
 ┌───────────────┐                            ▼
 │ DSL pii + sub-│ ───────────────▶  ┌──────────────────┐
 │  processor    │  compile-time     │ Consent banner   │
 │  primitives   │                   │ + CSP injection  │
 └───────────────┘                   └──────────────────┘
        │
        ├─────▶  Privacy page template (auto)
        ├─────▶  Cookie policy (auto)
        ├─────▶  ROPA document (auto)
        └─────▶  DPA subprocessor list (auto)

 ┌───────────────┐                   ┌──────────────────┐
 │ Event bus     │ ───subscribe──▶   │ GA4 Measurement  │
 │ (already      │                   │ Protocol sink    │
 │  exists)      │                   │ (server-side)    │
 └───────────────┘                   └──────────────────┘
```

Three data-flow paths:

- **Declarative render path** — DSL `analytics:` block + tenant config → HTML `<head>` snippet + consent banner on every page.
- **Client event path** — GTM `dataLayer` receives page views, user actions, state transitions (emitted from the framework's htmx hooks).
- **Server event path** — event bus topics subscribed by a provider-specific sink; server-side HTTP POST to the analytics provider's ingest endpoint.

Compliance path is an orthogonal compile-time pipeline that reads the same primitives and emits markdown/PDF/HTML artefacts.

## DSL primitives

### 1. `analytics:` block (app-level)

```dsl
app support_ticket_hub "Support Ticket Hub":
  analytics:
    providers:
      gtm:
        event_vocabulary: "dz/v1"
        auto_events:
          page_views: true
          actions: [click, submit]
          transitions: true
          form_submits: true
          search_queries: true
        include_pii: false       # master PII switch, defaults false
      plausible:
        event_vocabulary: "plausible/v1"
        auto_events:
          page_views: true
      server_side:
        sink: ga4_measurement_protocol
        bus_topics: [audit.*, transition.*, order.completed]
    consent:
      default: denied            # or "granted" for non-EU tenants
      banner: auto               # framework-provided banner
      categories: [analytics, advertising, personalization, functional]
    dev_mode: disabled           # explicit — never fires in dev
    trial_mode: disabled         # explicit — never fires during dazzle qa trial
```

**Parser rules:**

- `providers:` is a map of provider-name → provider-config. Provider names draw from a registry (GTM, GA4, plausible, fathom, posthog, segment, custom).
- `server_side:` is a peer of `providers:`, not a provider itself — it describes which topics bridge to which server-side sinks.
- `consent.categories:` uses Consent Mode v2 vocabulary normalised to four categories. The DSL accepts these four names only; additional categories are a parser error (keeps the contract clean).
- `dev_mode` and `trial_mode` accept `disabled` (default) or `enabled`. Explicit opt-in required.

### 2. `pii` field modifier

```dsl
entity User "User":
  id: uuid pk
  email: str pii(category=contact, sensitivity=standard)
  phone: str pii(category=contact, sensitivity=standard)
  dob: date pii(category=identity, sensitivity=high)
  ssn: str pii(category=identity, sensitivity=special_category)
  name: str pii(category=identity, sensitivity=standard)
  department: ref Department                 # NOT PII
  notes: text pii(category=freeform)         # flagged because freeform may contain PII
```

**Categories** (closed vocabulary — parser error on unknown):

- `contact` — email, phone, address
- `identity` — name, DOB, government IDs, tax numbers
- `location` — precise geolocation, IP address
- `biometric` — fingerprints, face templates
- `financial` — bank account, card number, income
- `health` — medical conditions, prescriptions (GDPR special category Art. 9)
- `freeform` — unstructured text that may contain PII
- `behavioral` — browsing history, preferences (analytics-derived)

**Sensitivity** (closed vocabulary):

- `standard` — ordinary personal data
- `high` — higher-risk (DOB, full name, geolocation)
- `special_category` — GDPR Article 9 / 10 (health, biometric, criminal, political, religious)

**What the modifier does:**

- Compile-time: feeds the ROPA, privacy page, and cookie policy generators.
- Runtime: `pii()` fields are automatically stripped from analytics event payloads (never reach client-side dataLayer or server-side sink, unless the surface opts in explicitly via `analytics: include_pii=true`).
- RBAC: unchanged — permissions remain separate. PII annotation is orthogonal to scope/permit.
- Audit: fields annotated with `sensitivity=special_category` receive mandatory audit logging on read (compliance requirement).
- Export: GDPR right-to-access handlers can auto-populate from annotated fields.

### 3. `subprocessor` construct (app-level)

```dsl
subprocessor google_analytics "Google Analytics 4":
  handler: "Google LLC"
  handler_address: "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
  jurisdiction: US
  data_categories: [pseudonymous_id, device_fingerprint, page_url, session_data]
  retention: 14 months
  legal_basis: legitimate_interest
  consent_category: analytics
  dpa_url: "https://business.safety.google/adsprocessorterms/"
  scc_url: "https://business.safety.google/sccs/"
  cookies: [_ga, _ga_*, _gid]

subprocessor stripe "Stripe Payment Processing":
  handler: "Stripe, Inc."
  jurisdiction: US
  data_categories: [financial, contact]
  retention: 7 years           # finance regulatory
  legal_basis: contract
  consent_category: functional
  dpa_url: "https://stripe.com/legal/dpa"
  cookies: [__stripe_mid, __stripe_sid]
```

Some framework-provided subprocessors ship out-of-the-box (GA4, GTM, Stripe, Twilio, SendGrid, AWS SES, Firebase) with default metadata in a registry at `src/dazzle/compliance/subprocessors/`. App-level subprocessor declarations override or extend the registry.

Declaring a provider in `analytics.providers:` **automatically registers the matching subprocessor** — no duplication. Manual subprocessor declarations are only needed for non-analytics third-parties (payment, email, SMS, file storage).

**Parser rules:**

- `jurisdiction:` accepts ISO 3166-1 alpha-2 country codes or multi-region identifiers (EU, EEA, UK, US, APAC).
- `legal_basis:` maps to GDPR Article 6: `consent`, `contract`, `legal_obligation`, `vital_interests`, `public_task`, `legitimate_interest`.
- `consent_category:` must match one of the four consent categories declared in `analytics.consent.categories:` — tied directly to the banner's opt-in structure.
- `retention:` uses the same duration syntax as entity retention (see `rhythm:` — extend if needed).
- `cookies:` may include glob patterns (`_ga_*`) — used to auto-generate the cookie policy.

### 4. DSL grammar impact summary

| Construct | New? | Grammar change |
|---|---|---|
| `analytics:` (app-level) | New | New top-level block; new keyword. |
| `pii()` (field modifier) | New | New modifier token after type, parenthesised kw-args. |
| `subprocessor` (top-level) | New | New top-level construct (peer of `entity`, `integration`). |
| `sensitivity:` inside pii | New | Closed-vocab parser. |
| Consent-category vocabulary | New | Four-member enum. |

Grammar docs and drift tests (`tests/unit/test_docs_drift.py`) update in lockstep.

## TOML config

Per-deployment / per-environment, in `dazzle.toml`:

```toml
[analytics]
enabled = true
default_provider_ids = { gtm = "GTM-XXXXXX", ga4 = "G-YYYYYY", plausible = "example.com" }

[analytics.dev]
enabled = false                # hard off in dev

[analytics.trial]
enabled = false                # hard off during trials

[analytics.server_side]
ga4_api_secret_env = "GA4_API_SECRET"   # Dazzle reads from env, never stored in TOML

[tenant]
# Tenant-overridable fields — see Per-tenant section
analytics_overridable = ["gtm_id", "ga4_measurement_id", "data_residency"]
```

**TOML stores where-to-send, DSL stores what-to-emit.** TOML values can be overridden per tenant; DSL values cannot (the event vocabulary is part of the app contract).

## Per-tenant resolution

### Tenant entity extension

Dazzle's existing tenant model gains an `analytics` facet:

```python
class TenantAnalyticsConfig:
    gtm_id: str | None
    ga4_measurement_id: str | None
    plausible_domain: str | None
    data_residency: Literal["EU", "UK", "US", "APAC", "other"]
    consent_default: Literal["granted", "denied"]
    privacy_page_url: str | None   # override the auto-generated one
    custom_subprocessors: list[SubprocessorSpec]
```

Per-tenant analytics is a runtime resolution — the same Dazzle binary serves tenant A (GTM-ABC) and tenant B (GTM-DEF) from one deployment.

### Request-time resolution

1. Middleware resolves tenant from host/path/JWT (already exists).
2. `TenantAnalyticsResolver` loads the tenant's analytics config from DB.
3. Default falls through to `dazzle.toml` `[analytics].default_provider_ids`.
4. The base template renders the GTM/GA snippet with tenant-resolved IDs.
5. CSP middleware reads the resolved provider list and unions the required origins into `script-src`, `connect-src`, `img-src`.
6. Consent banner is rendered with tenant-appropriate default state (EU tenant → denied, US tenant → granted unless overridden).

### Tenant-level CSP

Each provider declares its required CSP origins:

```python
class ProviderCSPRequirements:
    script_src: list[str]
    connect_src: list[str]
    img_src: list[str]
    frame_src: list[str]
```

The framework builds the tenant-specific CSP at request time by unioning the requirements of all enabled providers for that tenant. The existing `_build_csp_header` function extends to accept a `providers:` argument.

## Consent banner

### States and flow

```
          ┌───────────────────────┐
          │ First visit — no      │
          │  consent cookie       │
          └──────────┬────────────┘
                     │
                     ▼
         ┌────────────────────────┐
         │ Default: ALL DENIED    │
         │ (EU tenants)           │
         │ Dazzle banner renders  │
         │ GTM loads in denied    │
         │  consent mode          │
         └──────────┬─────────────┘
                    │ user action
     ┌──────────────┼───────────────┐
     ▼              ▼               ▼
 [Accept all]  [Reject all]   [Customise]
     │              │               │
     ▼              ▼               ▼
  GRANTED        DENIED         per-category
  per cat.       per cat.         choice
     │              │               │
     └──────────────┼───────────────┘
                    ▼
       Consent cookie persisted:
         dz_consent_v2={...}
       GTM consent state updated:
         gtag('consent','update',{...})
       subsequent events fire per category
```

### Consent Mode v2 integration

Dazzle emits the initial Consent Mode default signal **before** GTM loads:

```html
<script>
gtag('consent', 'default', {
  'ad_storage':           'denied',
  'ad_user_data':         'denied',
  'ad_personalization':   'denied',
  'analytics_storage':    'denied',
  'functionality_storage':'granted',
  'security_storage':     'granted',
  'wait_for_update': 500
});
</script>
<!-- GTM script tag here -->
```

After user choice:

```javascript
gtag('consent', 'update', {
  'analytics_storage': userChose.analytics ? 'granted' : 'denied',
  ...
});
```

### Consent cookie

- Name: `dz_consent_v2` (versioned — if we need to reset consent due to policy change, we can bump to `dz_consent_v3`)
- Format: JSON-encoded, URL-encoded. `{v: 2, categories: {analytics: true, advertising: false, ...}, ts: 1706...}`
- Max-Age: 13 months (GDPR guidance)
- Path: `/`
- Secure + HttpOnly false (banner needs JS read access) + SameSite=Lax
- Per-tenant scoping: when path-based routing is used, cookie name includes tenant slug: `dz_consent_v2_acme`.

### Banner accessibility

- ARIA landmarks, keyboard-navigable, focus-trapped while visible.
- Visible on every page until user makes a choice.
- "Withdraw consent" link in footer re-opens the banner (GDPR requirement: withdrawal must be as easy as granting).
- Screen-reader announces the banner on first load.

### Banner customisation

- Theme tokens control colours + typography (existing ux-architect token system).
- Banner copy is Jinja-templated, overridable per-tenant via the compliance pack.
- Structural changes (adding categories beyond the four, changing the flow) require forking the template — framework does not support this directly.

## Event vocabulary v1

Auto-emitted events. Versioned as `dz/v1` — additive only. Breaking changes cut a new version.

### Events

| Event name | Fires on | Core parameters | Optional parameters (opt-in) |
|---|---|---|---|
| `dz_page_view` | htmx swap + full page load | workspace, surface, persona_class | url, referrer |
| `dz_action` | DSL action invoked | action_name, entity, surface | entity_id (if opted-in) |
| `dz_transition` | state machine transition | entity, from_state, to_state, trigger | entity_id (if opted-in) |
| `dz_form_submit` | form POST success | form_name, entity, surface | validation_errors_count |
| `dz_search` | filterable_table search | surface, entity, result_count | query (truncated, no PII) |
| `dz_api_error` | 4xx/5xx from htmx request | status_code, surface | error_code |

### Parameter rules

- All parameter values are primitives (string, number, boolean) — no nested objects.
- String values are clamped to 100 chars.
- Parameter names are snake_case, prefixed with `dz_` only on event names, not parameters.
- Schema version always in payload: `dz_schema_version: "1"`.
- Tenant ID in payload: `dz_tenant: <tenant_slug>` — allows GA4 property-level segmentation.
- PII fields never appear unless the surface declares `analytics: include_pii=true` AND the specific event whitelists them.

### Versioning policy

- **Additive changes** (new event, new optional parameter) — same version.
- **Breaking changes** (rename event, remove parameter, change parameter type) — new version. Both versions emit in parallel for one release cycle, then the old version is removed.
- **CHANGELOG entry required** for any v1 schema change.
- **Drift test**: `tests/unit/test_event_vocabulary_v1.py` pins the exact schema; modifying it without the test update is a parser failure.

## htmx integration

htmx swaps do not fire `history.pushState`. GTM's built-in "History Change" trigger won't see them.

### Framework-owned hook

Loaded automatically on every Dazzle page when analytics is enabled:

```javascript
// dz-analytics.js — shipped as a framework static asset
document.addEventListener('htmx:afterSwap', function(evt) {
  const target = evt.detail.target;
  if (target.hasAttribute('data-dz-surface')) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: 'dz_page_view',
      dz_schema_version: '1',
      workspace: target.getAttribute('data-dz-workspace'),
      surface: target.getAttribute('data-dz-surface'),
      persona_class: document.body.getAttribute('data-dz-persona-class'),
      dz_tenant: document.body.getAttribute('data-dz-tenant'),
    });
  }
});

document.addEventListener('click', function(evt) {
  const el = evt.target.closest('[data-dz-action]');
  if (el) {
    window.dataLayer.push({
      event: 'dz_action',
      dz_schema_version: '1',
      action_name: el.getAttribute('data-dz-action'),
      entity: el.getAttribute('data-dz-entity'),
      surface: el.getAttribute('data-dz-surface'),
    });
  }
});
```

The framework's template layer adds these `data-dz-*` attributes to rendered action buttons / surface wrappers. Authors never write them by hand — they fall out of the DSL compilation.

### HTMX swap semantics edge cases

- **Partial swap that doesn't change surface** — no page-view event (correct: the user didn't navigate).
- **OOB swaps** — emit only if the primary target has `data-dz-surface`.
- **Error swap** (4xx/5xx response rendered into target) — emits `dz_api_error`, not `dz_page_view`.

## Server-side sink

### Architecture

Existing components: Dazzle has an event bus (`src/dazzle_back/events/`) with outbox pattern for reliable delivery. Subscribers live in `src/dazzle_back/events/subscribers/`.

New: `src/dazzle_back/analytics/sinks/` — per-provider server-side sinks.

```python
class AnalyticsSink(Protocol):
    provider: str
    async def emit(self, event: AnalyticsEvent, tenant: TenantContext) -> None: ...

class GA4MeasurementProtocolSink:
    async def emit(self, event: AnalyticsEvent, tenant: TenantContext) -> None:
        api_secret = os.environ["GA4_API_SECRET"]
        payload = {
            "client_id": event.client_id or self._generate_synthetic_id(tenant),
            "events": [{
                "name": event.name,
                "params": _strip_pii(event.params, event.entity_spec),
            }],
        }
        measurement_id = tenant.analytics.ga4_measurement_id
        url = f"https://www.google-analytics.com/mp/collect?measurement_id={measurement_id}&api_secret={api_secret}"
        async with self.http_client.post(url, json=payload) as response:
            response.raise_for_status()
```

### Subscription

```dsl
analytics:
  server_side:
    sink: ga4_measurement_protocol
    bus_topics: [audit.*, transition.*, order.completed]
```

Compiles to a registered subscriber that filters events by topic glob and pushes to the sink.

### Event shape

Server-side events use the same vocabulary as client-side where possible, plus business events that have no client-side counterpart (`subscription_created`, `payment_succeeded`, `invoice_generated`). These fall outside the `dz_` namespace and follow GA4's own conventions where applicable.

### Reliability

- Outbox pattern ensures at-least-once delivery.
- On HTTP 4xx from GA MP: log + drop (bad event shape, retry won't help).
- On HTTP 5xx or network: retry with exponential backoff, max 3 attempts, then dead-letter.
- Metrics: `dz_analytics_sink_success_total`, `dz_analytics_sink_failure_total`, `dz_analytics_sink_latency_ms` — feed into existing Dazzle observability.

## PII stripping

Central redaction layer applied before any event leaves the framework:

```python
def _strip_pii(params: dict, entity_spec: EntitySpec, opt_in: set[str]) -> dict:
    """Remove values for fields declared as pii() unless opted in."""
    result = {}
    for key, value in params.items():
        field = entity_spec.fields.get(key)
        if field and field.pii and key not in opt_in:
            continue    # drop silently
        result[key] = value
    return result
```

Applied at three boundaries:

1. **Client-side dataLayer push** — the framework JS never includes values from PII-annotated fields in pushed events. Template-time enforcement, not runtime.
2. **Server-side sink** — the `_strip_pii` helper runs before the HTTP POST.
3. **Debug logging** — analytics-event log (dev mode) applies the same filter to avoid PII on disk.

`include_pii=true` opt-in is surface-scoped. A DSL author who wants email in events must explicitly declare it:

```dsl
surface user_signup "Sign Up":
  analytics:
    include_pii: [email]    # explicit whitelist, not blanket opt-in
```

Never a blanket opt-in at app level — too easy to ship accidentally.

## Privacy page auto-generation

### Template

Shipped at `src/dazzle_ui/templates/compliance/privacy_page.html.j2`:

```jinja
# Privacy Policy

**Last updated:** {{ last_updated }}

## What data we collect

{% for category, fields in pii_fields_by_category.items() %}
### {{ category.title }} data
{% for field in fields %}
- **{{ field.label }}** ({{ field.entity.label }}): {{ field.purpose }}
{% endfor %}
{% endfor %}

## Who we share it with

{% for sp in subprocessors %}
### {{ sp.name }}
- **Handler:** {{ sp.handler }} ({{ sp.jurisdiction }})
- **Purpose:** {{ sp.purpose }}
- **Legal basis:** {{ sp.legal_basis }}
- **Retention:** {{ sp.retention }}
- **DPA:** [{{ sp.dpa_url }}]({{ sp.dpa_url }})
- **Cookies:** {{ sp.cookies | join(', ') }}
{% endfor %}

## Your rights

- **Access your data:** [/gdpr/access](/gdpr/access)
- **Delete your data:** [/gdpr/erase](/gdpr/erase)
- **Export your data:** [/gdpr/portability](/gdpr/portability)
- **Withdraw consent:** [Reopen consent banner](#){onclick="dzConsent.reopen()"}

## Data retention

{% for entity in entities_with_retention %}
- **{{ entity.label }}**: {{ entity.retention }}
{% endfor %}
```

### Compile pipeline

1. Scan IR for all `pii()` annotations; group by category.
2. Resolve subprocessor declarations (app-level + framework defaults for active providers).
3. Gather retention metadata from entity + rhythm definitions.
4. Render template to `docs/privacy/policy.md` + `/privacy` route at runtime.

Output is markdown — Dazzle renders it via the existing markdown renderer. Legal teams can fork the template; a `dazzle compliance privacy --regenerate-facts` command re-updates only the auto-enumerated sections while preserving manual edits.

### GDPR rights endpoints

Framework-provided (auto-registered when `analytics:` block present):

- `GET /gdpr/access` — authenticated user downloads their data (enumerated from `pii()` fields).
- `POST /gdpr/erase` — authenticated user requests erasure; triggers the existing soft-delete + 30-day grace period flow.
- `GET /gdpr/portability` — machine-readable export (JSON).

Entity-level hooks let apps customise what "delete" means (anonymise vs hard-delete vs mark-for-review).

## Compliance artefact reuse

The same primitives feed three separate outputs:

### 1. ROPA (Record of Processing Activities)

GDPR Article 30 requirement. Dazzle generates a CSV/PDF:

| Activity | Data categories | Subjects | Recipients | Retention | Legal basis | Cross-border |
|---|---|---|---|---|---|---|
| User account management | contact, identity | Customers | Google Analytics, Stripe | 7 years | contract | US (SCCs) |

### 2. Cookie policy

Enumerated from subprocessor `cookies:` declarations:

| Name | Provider | Purpose | Duration | Category |
|---|---|---|---|---|
| `_ga` | Google Analytics | Distinguishes users | 2 years | Analytics |
| `__stripe_mid` | Stripe | Fraud prevention | 1 year | Functional |

### 3. DPA hub

Lists all subprocessors with DPA URLs, SCC URLs, last-reviewed dates — SOC 2 CC6.6 evidence.

All three reuse the subprocessor + PII primitives. No duplicate source of truth.

## Provider registry

Shipped providers (v0.61.0):

| Provider | Client-side | Server-side | Notes |
|---|---|---|---|
| GTM | Yes | N/A (GTM is client-only) | Primary test case. Loads GA4 via container. |
| GA4 direct | Yes (gtag.js) | Yes (Measurement Protocol) | Alternative for users who don't want GTM's runtime surface. |
| Plausible | Yes | Via Plausible Events API | Privacy-friendly; no cookies; EU-hosted option. |
| Fathom | Yes | No (not released) | Minimal. |
| PostHog | Yes | Yes | Product analytics + session replay. |
| Segment | Yes (Analytics.js) | Yes (HTTP API) | Fan-out to downstream tools. |
| Custom | Client-only dataLayer push | N/A | Escape hatch: pushes events, user wires own script. |

Each provider has:

- A `ProviderDefinition` in `src/dazzle/compliance/analytics/providers/`
- A client-side snippet template
- CSP requirements
- Default subprocessor metadata
- An optional server-side sink class

Adding a provider = one file + registration. Registry lives alongside the subprocessor registry.

## CSP integration

The existing `_build_csp_header(directives)` function gains a `providers: list[ProviderDefinition]` parameter. When building the header:

```python
def _build_csp_header(custom, providers=None):
    directives = _default_directives()
    if providers:
        for p in providers:
            directives["script-src"].update(p.csp.script_src)
            directives["connect-src"].update(p.csp.connect_src)
            directives["img-src"].update(p.csp.img_src)
    ...
```

Providers-in-CSP is tenant-resolved at request time. Tenants without analytics get the strict baseline; tenants with GTM + Plausible get unioned origins.

**CSP reporting endpoint** (future): `/csp-report` that logs violations. Out of scope for v0.61.0 but the middleware is ready for it.

## Dev / trial / qa disable semantics

Three hard-off paths:

1. **Dev mode** (`DAZZLE_ENV=dev`): no analytics scripts rendered, no server-side sinks subscribed. Overridable via `DAZZLE_ANALYTICS_FORCE=1` for testing the feature itself.
2. **Trial mode** (agent-driven `dazzle qa trial`): trial context sets `DAZZLE_MODE=trial`; analytics is force-off regardless of TOML.
3. **E2E tests** (`pytest -m e2e`): test fixtures set the mode; analytics is no-op.

Analytics-enabled integration tests opt in via a fixture:

```python
@pytest.fixture
def analytics_enabled(monkeypatch):
    monkeypatch.setenv("DAZZLE_ANALYTICS_FORCE", "1")
```

## Migration path for existing apps

Existing Dazzle apps (v0.60.x) keep working. Steps to adopt:

1. Add `analytics:` block to the app DSL.
2. Add `pii()` modifiers to sensitive fields (linter warns if email/phone/DOB-named fields are missing the modifier).
3. Configure TOML `[analytics]` section.
4. Run `dazzle compliance regenerate` — produces the updated privacy page + ROPA + cookie policy.
5. Deploy; consent banner appears on first visit.

A `dazzle analytics audit` CLI command scans the DSL and reports:

- Fields with PII-indicative names (email, phone, dob, ssn, name) that aren't annotated.
- Subprocessors declared but not referenced in any `integration:` or `analytics:` block.
- Consent categories declared but not used by any subprocessor.
- Analytics providers without a matching CSP allowance.

## Phased delivery

The full scope is ~4-6 weeks. Breaking into shippable phases:

### Phase 1: PII foundation (≈1 week)

Independently valuable even without analytics.

- `pii()` field modifier — parser + IR
- Subprocessor construct — parser + IR + framework registry (5 default subprocessors)
- PII stripping utility
- `dazzle analytics audit` command (only the PII-name-heuristic check in this phase)
- Docs + examples

Ship: **v0.61.0-rc1**.

### Phase 2: Consent + privacy page (≈1 week)

- Consent banner component + Consent Mode v2 bootstrap
- Consent cookie handling
- Privacy page auto-generation (template + compile pipeline)
- GDPR rights endpoints (`/gdpr/access`, `/gdpr/erase`, `/gdpr/portability`)
- Cookie policy + ROPA generators

Ship: **v0.61.0-rc2**.

### Phase 3: Provider abstraction + GTM + Plausible (≈1 week)

- Provider registry + `ProviderDefinition` type
- GTM provider (client-side)
- Plausible provider (client-side, to prove abstraction)
- CSP integration
- Per-tenant resolution (read TOML defaults; tenant entity extension scaffolding)
- `analytics:` block parsing

Ship: **v0.61.0-rc3**.

### Phase 4: Event vocabulary + htmx integration (≈3-4 days)

- `dz-analytics.js` framework asset
- Template-layer `data-dz-*` attribute injection
- Event vocabulary v1 spec + drift test
- Dev/trial/qa disable semantics

Ship: **v0.61.0-rc4**.

### Phase 5: Server-side sink (≈3-4 days)

- GA4 Measurement Protocol sink
- Event bus bridge
- Outbox reliability + metrics

Ship: **v0.61.0-rc5**.

### Phase 6: Per-tenant resolution completion (≈3-4 days)

- Tenant entity analytics facet migration
- Request-time resolver
- Per-tenant CSP union
- Cross-tenant isolation tests

Ship: **v0.61.0** (stable).

### Phase 7 (post-GA): PostHog + Segment providers, GA4-direct, Fathom

Ship: **v0.62.x**.

## Example app

`examples/analytics_demo/` — a new example showing:

- GTM + GA4 via one provider declaration
- Plausible running alongside
- Three entity types with varied PII annotations
- Two subprocessor declarations beyond analytics (Stripe, SendGrid)
- Full consent banner flow
- Auto-generated privacy page rendering at `/privacy`
- Per-tenant analytics (three demo tenants with different IDs)
- Server-side GA4 for subscription events

Used by the trial-cycle loop to qualitative-test the full flow.

## Open questions (decide before Phase 2 kicks off)

These don't block Phase 1 (PII primitives) but need resolving before consent + banner work:

1. **Consent-category naming**: Dazzle-native (`analytics`, `advertising`, `personalization`, `functional`) or GA4-native (`ad_storage`, `analytics_storage`, etc.)? Strong lean toward Dazzle-native with a docs mapping table — framework shouldn't leak GA4 vocabulary into every app's consent model.
2. **Default consent state**: `denied` for EU tenants, `granted` for US? Or `denied` universally? Strong lean toward residency-driven defaults: EU/UK = denied, elsewhere = granted, with tenant-level override.
3. **Privacy page editability**: fully auto-gen, or auto-gen-with-override? Legal requires copy control. Proposal: generate markdown with delimited `<!-- DZ-AUTO -->` blocks; the regenerate command touches only those blocks. Non-auto sections are author-owned.
4. **GDPR special-category handling**: do `sensitivity=special_category` fields get automatic extra handling (audit log on read, restricted export, explicit-consent gate)? Likely yes, but defining "extra handling" crisply is a separate design discussion.
5. **Multi-domain tenancy**: if tenant A serves `acme.com` and `portal.acme.com`, do they share a consent cookie? Probably yes within the same apex domain (set cookie with `Domain=.acme.com`), but this needs confirming against consent law.

## Risks

| Risk | Mitigation |
|---|---|
| Legal liability from mis-configured consent | EU default-deny + banner can't be dismissed without a choice; audit command flags misalignment. |
| Event vocabulary v1 becomes a burden to evolve | Strict additive-only rule + drift test + versioned emission (dual-emit during transitions). |
| Per-tenant complexity leaks to simple apps | Single-tenant apps never resolve tenant analytics; config stays in TOML. |
| GTM container includes rogue scripts (user adds tracker without updating subprocessor list) | `dazzle analytics audit` flags providers declared in TOML but not in DSL. Not a hard block (users may deliberately use GTM's late-binding), but a loud warning. |
| Ad-blockers eat client-side events | Server-side sink via MP provides a fallback channel for business-critical events. |
| Framework telemetry temptation | Explicit non-goal in v0.61.0. If added later, must ship as opt-in separate channel. |

## Related

- ADR-0011 (no SPA frameworks) — analytics integration must not require SPA patterns; htmx hooks are the right shape.
- ADR-0017 (schema via Alembic) — tenant entity extension requires a migration.
- `docs/reference/compliance.md` (if exists) — privacy artefacts extend the compliance pipeline.
- `src/dazzle_back/runtime/security_middleware.py` — CSP host.
- `src/dazzle_back/events/` — event bus substrate for server-side sink.
- `docs/reference/workspaces.md` — workspace + surface definitions drive page-view events.

## Next step

Brainstorm the open questions (especially #1-3), then start Phase 1 (PII + subprocessor primitives). That phase is independently valuable, unblocks the compliance pipeline, and de-risks the DSL shape before committing to the larger consent + privacy work.
