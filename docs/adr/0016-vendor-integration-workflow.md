# ADR-0016: Vendor Integration via API Packs

**Status:** Accepted
**Date:** 2026-03-01

## Context

Dazzle applications frequently integrate with third-party APIs (payment providers, email services, CRMs, etc.). Without a standard approach, each integration requires hand-coding HTTP clients, mock servers, and webhook handlers.

## Decision

Use **API Packs** — TOML-based vendor API descriptions that drive code generation, mock servers, and webhook handling.

### Workflow

1. `dazzle api-pack search` (MCP) — check for existing pack
2. `dazzle api-pack scaffold` (CLI) — create pack TOML (from OpenAPI or blank)
   - Save to `.dazzle/api_packs/<vendor>/<name>.toml`
3. `dazzle api-pack generate-dsl` (CLI) — generate `service` + `foreign_model` DSL blocks
4. Write integration + mapping DSL blocks
5. `dazzle serve --local` — mocks auto-start for all pack references
6. `dazzle mock fire-webhook` (CLI) — test webhook handling
7. `mock request_log` (MCP) — verify integration calls
8. `dazzle mock scenarios` (CLI) — test edge cases

### Project-Local Packs

Place custom packs in `.dazzle/api_packs/<vendor>/<name>.toml`. Project-local packs override built-in packs with the same name.

## Consequences

### Positive

- Standardised integration pattern across all vendor APIs
- Mock servers auto-generated from pack definitions — no external services needed for development
- Webhook testing built-in via `fire-webhook`
- DSL generation eliminates boilerplate `service` and `foreign_model` definitions

### Negative

- TOML pack format is Dazzle-specific (not a standard like OpenAPI alone)
- Pack maintenance required when vendor APIs change

### Neutral

- Built-in packs ship with Dazzle for common vendors
- OpenAPI specs can bootstrap pack TOML via `scaffold --from-openapi`

## Alternatives Considered

### 1. Direct OpenAPI Client Generation

Generate HTTP clients directly from vendor OpenAPI specs.

**Rejected:** OpenAPI alone doesn't capture Dazzle-specific mapping (which entity fields map to which API fields), mock behavior, or webhook routing.

### 2. Manual Integration Per Vendor

Hand-code each integration without a standard pattern.

**Rejected:** Inconsistent patterns, no mock infrastructure, duplicated effort across projects.
