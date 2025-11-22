# DAZZLE Service Profiles & Common Integrations  
## (LLM-Facing Implementation Brief for Expert Developer)

This document provides explicit, imperative instructions for implementing **service profiles** and **common integration patterns** in DAZZLE without bloating the the DSL or forcing domain-specific services (e.g., HMRC APIs) into the core.

Your job is to implement a minimal, extensible system of **service profiles** and **integration templates** that:

- Keep the DSL and IR small.
- Make common services (captcha, analytics, CDN, etc.) easy to wire.
- Allow highly specific integrations (HMRC, Xero, Stripe, etc.) to live outside the core as project- or module-level code.

Follow the design below exactly.

---

## 1. Preserve DSL & IR Minimalism

1. Do **not** add vendor-specific keywords to the DSL such as:
   - `google_captcha`
   - `google_analytics`
   - `cloudflare`
   - `hmrc`

2. Keep existing core constructs:
   - `service`
   - `foreign_model`
   - `integration`

3. Introduce service specialisation only through:
   - **Service profiles** (metadata)
   - **Optional templates** (generators/modules)
   - **Stack selection** and manifest configuration

The DSL must remain vendor-neutral and intent-focused.

---

## 2. Introduce Service Profiles as Structured Metadata

### 2.1 Service Profile Concept

A **service profile** is a short, structured hint that tells backends:

- What “kind” of external service this is.
- What standard behaviour or wiring should be applied.

Implement this as metadata on **ServiceSpec**, not as new DSL syntax.

### 2.2 IR Extension

Extend `ServiceSpec` in the IR (Python side) with:

```python
class ServiceProfile(BaseModel):
    kind: Literal["captcha", "analytics", "cdn", "payment", "tax_api", "identity", "custom"]
    vendor: str | None = None        # e.g. "google", "cloudflare", "stripe"
    name: str | None = None          # e.g. "recaptcha_v3", "ga4", "cf_basic"
    config: dict[str, Any] = {}      # arbitrary profile-specific details
```

Add to `ServiceSpec`:

```python
class ServiceSpec(BaseModel):
    ...
    profile: ServiceProfile | None = None
```

The DSL will surface this via `meta` or optional structured directives, but **you must not** introduce vendor names as first-class grammar.

### 2.3 Manifest Mapping

Allow finer profile configuration in `dazzle.toml`:

```toml
[services.google_analytics]
service = "ga_service"
profile = "analytics/google_ga4"
tracking_id = "G-XXXXXXX"

[services.recaptcha]
service = "recaptcha_service"
profile = "captcha/google_recaptcha_v3"
site_key = "..."
secret_key = "..."
```

Implement:

- Mapping from TOML entries into `ServiceProfile` objects.
- Overriding or enriching DSL-declared service metadata.

---

## 3. Recommended Profile Kinds & Vendors

Implement the following **canonical profile kinds** in core:

- `captcha`
- `analytics`
- `cdn`
- `payment`
- `tax_api`
- `identity` (login/SSO)
- `custom` (fallback for anything else)

Examples:

1. Google reCAPTCHA:

```python
ServiceProfile(
    kind="captcha",
    vendor="google",
    name="recaptcha_v3",
    config={"score_threshold": 0.5}
)
```

2. Google Analytics / GTM:

```python
ServiceProfile(
    kind="analytics",
    vendor="google",
    name="ga4"
)
```

3. Cloudflare CDN/cache:

```python
ServiceProfile(
    kind="cdn",
    vendor="cloudflare",
    name="cdn_basic"
)
```

4. HMRC VAT API (project-specific):

```python
ServiceProfile(
    kind="tax_api",
    vendor="hmrc",
    name="vat"
)
```

You must not treat HMRC as a core vendor; it is just an example of a `tax_api` profile that belongs in project-level modules.

---

## 4. How Backends Use Service Profiles

### 4.1 Frontend/Next.js Backend

Use `ServiceProfile` hints to generate boilerplate:

- `captcha` / `google_recaptcha_v3`:
  - Inject React hook or utility to call the captcha endpoint.
  - Wire environment variables (site key) from infra.

- `analytics` / `google_ga4`:
  - Add GA4 snippet or GTM container script.
  - Provide a small analytics utility in `lib/analytics.ts`.

- `cdn` / `cloudflare`:
  - Minimal: may not require frontend changes.
  - Optionally adjust asset URLs or headers.

### 4.2 Backend/Django Backend

Use `ServiceProfile` to:

- Add middleware or context where appropriate.
- Expose endpoints for captcha verification.
- Wire environment variables and settings sections for analytics or CDN integration.

### 4.3 Infra Backends (Docker/Terraform)

Use `ServiceProfile` to:

- Generate required env vars for captcha/analytics providers.
- Optionally create placeholders for secrets (not real values).
- Provide Terraform variables for keys/IDs.

All of this is optional and keyed by `profile.kind` and `profile.vendor`.

---

## 5. Common vs. Project-Specific Services

Distinguish clearly between:

### 5.1 Common, Cross-Project Profiles

Implement these in **core** as first-class profile kinds/vendors:

- `captcha/google_recaptcha_v3`
- `analytics/google_ga4`
- `analytics/google_gtm`
- `cdn/cloudflare_basic`

These must be supported by:
- Frontend backend
- Django backend
- Infra backends (via env var scaffolding)

### 5.2 Project- or Domain-Specific Profiles

Do **not** add these to core:

- `tax_api/hmrc_vat`
- `accounting/xero`
- `payments/custom_lender_x`

Instead, allow:

- Project-local Python modules to define additional `ServiceProfile` interpretations.
- Stacks to reference domain-specific extensions.

You must provide a mechanism (e.g., Python entrypoints or plugin registry) for additional profile handlers without changing the core schema.

---

## 6. Representing Profiles in the DSL Without Bloat

Use the existing `meta` directive or light annotations rather than new grammar constructs.

Example DSL:

```text
service ga_service "Google Analytics":
  spec: url "https://analytics.google.com"
  auth_profile: none
  owner: "Google"
  meta profile.kind="analytics" profile.vendor="google" profile.name="ga4"

service recaptcha_service "Google reCAPTCHA":
  spec: url "https://www.google.com/recaptcha/api/siteverify"
  auth_profile: none
  owner: "Google"
  meta profile.kind="captcha" profile.vendor="google" profile.name="recaptcha_v3"
```

Implement:

- Parsing for `meta` key/value pairs.
- Normalisation into `ServiceProfile` objects in the IR.

Do not add new top-level keywords such as `profile` to the grammar for 0.1; use `meta` to keep surface area small.

---

## 7. Integration Templates for Common Services

Implement **integration templates** as Python helpers, not DSL features.

Example: `dazzle.integrations.analytics` module should:

1. Provide helper to attach analytics to surfaces/experiences.
2. Use `ServiceProfile` to decide which snippets to generate.
3. Offer “one-liner” Python APIs that are triggered by stacks or backends, not by DSL syntax.

Similarly, `dazzle.integrations.captcha` should:

1. Detect `ServiceProfile(kind="captcha")`.
2. Generate:
   - Backend endpoint to verify captcha tokens.
   - Frontend hook/function to call captcha.

All heavy lifting stays in Python modules.

---

## 8. Documentation & UX Guidance

When presenting this to users:

1. Describe service profiles as:
   > “Short hints that tell DAZZLE what kind of external service this is, so generators can wire reasonable defaults.”

2. Explain:
   - Captcha/analytics/CDN are “common” and shipped in core.
   - HMRC, Xero, etc. are **not** in core, but can be layered via project plugins.

3. Show examples:
   - A simple app using Google Analytics + reCAPTCHA via profiles.
   - A domain-specific app (e.g., HMRC VAT tools) using the same mechanism but with project-specific handlers.

---

## 9. Implementation Tasks You Must Complete

1. Extend IR to include `ServiceProfile`.
2. Implement mapping from DSL `meta` and `dazzle.toml` to `ServiceProfile`.
3. Add core profile kinds & vendors:
   - `captcha/google_recaptcha_v3`
   - `analytics/google_ga4`
   - `analytics/google_gtm`
   - `cdn/cloudflare_basic`
4. Update backends (django, nextjs, infra_docker, infra_terraform) to:
   - Inspect `ServiceProfile`
   - Generate appropriate wiring/snippets/env vars
5. Provide plugin mechanism for new profiles without changing core.
6. Add documentation and examples in the DAZZLE repo.

---

# End of Specification
