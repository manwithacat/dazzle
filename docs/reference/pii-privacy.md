# PII & Privacy Primitives

**Added**: v0.61.0 (Phase 1 of the analytics / consent / privacy design —
see `docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`.)

Dazzle treats personal data as a first-class DSL concept. Two primitives
carry the weight:

1. **`pii()`** — a field modifier that classifies personal data by category
   and sensitivity.
2. **`subprocessor`** — a top-level construct declaring a third-party that
   handles personal data on the app's behalf.

Together they feed every compile-time privacy artefact: the privacy page,
the GDPR Record of Processing Activities (ROPA), the cookie policy, and the
SOC 2 / ISO 27001 subprocessor list. They also drive the runtime PII
stripping applied before any analytics event leaves the framework.

## The `pii()` modifier

### Syntax

```dsl
entity User "User":
  id: uuid pk
  email: str(200) pii                                           # bare → standard
  phone: str(50) pii(category=contact)                          # category only
  dob: date pii(category=identity, sensitivity=high)            # both kwargs
  ssn: str(20) pii(category=identity, sensitivity=special_category)
  notes: text pii(category=freeform) required                   # with other modifiers
```

### Categories

Closed vocabulary — the parser rejects any value outside this list.

| Category | Meaning | Examples |
|---|---|---|
| `contact` | Ways to reach a subject | email, phone, postal address |
| `identity` | Identifying attributes | name, DOB, national ID, passport |
| `location` | Where a subject is | precise geolocation, IP address |
| `biometric` | Biological templates | fingerprint, face template |
| `financial` | Money-related | bank account, card number, salary |
| `health` | Medical data (GDPR Art. 9) | diagnoses, prescriptions |
| `freeform` | Unstructured text that may contain PII | notes, descriptions |
| `behavioral` | Inferred from usage | preferences, browsing history |

### Sensitivities

| Sensitivity | Meaning | Handling |
|---|---|---|
| `standard` | Ordinary personal data (default) | Stripped from analytics unless opted-in |
| `high` | Higher-risk (DOB, full name, precise location) | Same as standard; flagged in audit |
| `special_category` | GDPR Art. 9 / 10 — health, biometric, criminal, political, religious | Second opt-in gate, mandatory audit-on-read |

### What the annotation does

- **Compile-time**: feeds the privacy page, ROPA, cookie policy generators.
- **Runtime (analytics)**: PII-annotated values are stripped from events
  unless the surface opts in: `analytics: include_pii: [email]` (per-surface
  whitelist — no blanket app-level opt-in).
- **RBAC**: unchanged — PII annotation is orthogonal to `permit:` / `scope:`.
- **Audit**: `special_category` fields receive mandatory audit logging on read.
- **GDPR exports**: right-to-access / right-to-portability handlers auto-populate
  from annotated fields.

### Relationship to the `sensitive` modifier

Dazzle's existing `sensitive` modifier remains as a coarse boolean flag. The
`pii()` modifier is richer — a field may be both `sensitive` AND `pii()`; they
are independent. Over time, framework code should migrate to reading `.pii`
instead of `.is_sensitive` for PII-aware behaviour.

## The `subprocessor` construct

### Syntax

```dsl
subprocessor google_analytics "Google Analytics 4":
  handler: "Google LLC"
  handler_address: "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
  jurisdiction: US
  data_categories: [pseudonymous_id, device_fingerprint, page_url]
  retention: "14 months"
  legal_basis: legitimate_interest
  consent_category: analytics
  dpa_url: "https://business.safety.google/adsprocessorterms/"
  scc_url: "https://business.safety.google/sccs/"
  cookies: [_ga, _ga_*, _gid]
  purpose: "Product and web usage analytics."
```

### Required keys

- `handler` — legal entity processing the data
- `jurisdiction` — ISO country code or region (EU, EEA, UK, US, APAC)
- `retention` — free-form retention period string
- `legal_basis` — GDPR Article 6 basis (see below)
- `consent_category` — Dazzle-native consent category (see below)

### Optional keys

- `handler_address` — postal address of the handler entity
- `data_categories` — list of `DataCategory` values (closed vocabulary)
- `dpa_url` — link to the signed Data Processing Agreement
- `scc_url` — link to Standard Contractual Clauses (required when
  `jurisdiction` is outside EEA)
- `cookies` — cookie names / glob patterns this subprocessor sets
- `purpose` — short human description

### Legal basis (GDPR Article 6)

- `consent`
- `contract`
- `legal_obligation`
- `vital_interests`
- `public_task`
- `legitimate_interest`

### Consent categories

Dazzle uses four consent categories that map cleanly to Consent Mode v2:

| Dazzle category | Meaning | Consent Mode v2 equivalent |
|---|---|---|
| `analytics` | Product and web usage telemetry | `analytics_storage` |
| `advertising` | Ad targeting and measurement | `ad_storage` + `ad_user_data` + `ad_personalization` |
| `personalization` | User-preference customisation | `ad_personalization` / `functionality_storage` |
| `functional` | Essential for the service to work | `functionality_storage` + `security_storage` |

### Data categories

Closed vocabulary used inside `data_categories: [...]`. Overlaps with PII
categories where meaningful; extended with web-specific values.

- `contact`, `identity`, `location`, `behavioral`, `financial`, `health`
- `device_fingerprint` — browser/device signals used for tracking
- `pseudonymous_id` — unique IDs that aren't directly identifying
- `page_url` — URLs of pages visited
- `session_data` — within-session timing / flow
- `content` — content of user messages (email/SMS bodies, etc.)

## Framework-provided subprocessor registry

Dazzle ships declarations for common third-party services. App-level
declarations override registry entries by matching `name`.

| Name | Label | Jurisdiction | Consent category |
|---|---|---|---|
| `google_analytics` | Google Analytics 4 | US | analytics |
| `google_tag_manager` | Google Tag Manager | US | analytics |
| `plausible` | Plausible Analytics | EU | analytics |
| `stripe` | Stripe Payments | US | functional |
| `twilio` | Twilio | US | functional |
| `sendgrid` | SendGrid | US | functional |
| `aws_ses` | Amazon SES | US | functional |
| `firebase_cloud_messaging` | Firebase Cloud Messaging | US | functional |

See `src/dazzle/compliance/analytics/registry.py` for the full declaration
including DPA / SCC links.

## The `dazzle analytics audit` command

```bash
dazzle analytics audit                       # human-readable table (default)
dazzle analytics audit --format json         # machine-readable
dazzle analytics audit --project-dir ./my    # audit a different project
```

Produces two reports:

1. **PII annotation audit** — flags entity fields whose names strongly suggest
   PII (email, phone, dob, ssn, etc.) but lack a `pii()` annotation. Uses a
   conservative substring-heuristic — false-positives are expected, false-
   negatives are the real failure mode.

2. **Subprocessor audit** — lists every subprocessor in effect (framework
   defaults + app-declared), flags collisions where an app override differs
   from the framework default in `consent_category` / `jurisdiction` /
   `legal_basis`, and marks subprocessors that require SCCs for EU→non-EU
   data transfers.

The audit **never fails the build**. Treat it as advisory. Future phases
will add enforcement (e.g. require SCC URL when transfer detected).

## Analytics provider abstraction (Phase 3)

Declare analytics providers in the DSL:

```dsl
analytics:
  providers:
    gtm:
      id: "GTM-XXXXXX"
    plausible:
      domain: "example.com"
  consent:
    default_jurisdiction: EU
    consent_override: denied
```

The framework resolves the registered `ProviderDefinition` for each provider
name, unions its required CSP origins into the response's
`Content-Security-Policy`, and renders its script snippets into the HTML —
all gated on the current consent state. GTM bootstraps even under deny-
defaults so Consent Mode v2 can signal the container on later grant;
Plausible only loads when analytics consent is granted.

### Provider registry

Shipped in v0.61.0:

| Name | Label | Consent category | Required params | Links to subprocessor |
|---|---|---|---|---|
| `gtm` | Google Tag Manager | analytics | `id` | `google_tag_manager` |
| `plausible` | Plausible Analytics | analytics | `domain` | `plausible` |

Adding a provider: define a `ProviderDefinition` in
`src/dazzle/compliance/analytics/providers/registry.py`, add the matching
Jinja snippet templates, and update the `linked_subprocessor_name` to point
at the matching subprocessor declaration.

## What comes later

Phase 1-3 (this release stream) ships the primitives + consent banner +
provider abstraction. Subsequent phases:

- **Phase 4** — event vocabulary + htmx integration.
- **Phase 5** — server-side sinks via the event bus.
- **Phase 6** — per-tenant analytics resolution.

See the design spec at `docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`
for the full roadmap.
