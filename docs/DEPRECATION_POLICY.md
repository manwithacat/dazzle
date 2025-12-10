# DAZZLE Deprecation Policy

**Version**: 1.0
**Last Updated**: 2025-12-01

This document defines how DAZZLE handles deprecations of features, APIs, and code generation stacks.

---

## Overview

DAZZLE follows a structured deprecation process to ensure users have adequate time to migrate while allowing the project to evolve. All deprecations are announced in advance and documented.

---

## Deprecation Lifecycle

### 1. Announcement

When a feature is deprecated:
- Added to this document with deprecation date
- Warning messages added to CLI output
- Documentation updated with migration guidance
- CHANGELOG entry created

### 2. Grace Period

Deprecated features remain functional for:
- **Minor versions**: 2 minor releases minimum
- **Major versions**: Until next major release

### 3. Removal

After the grace period:
- Feature is removed in the announced version
- Breaking change noted in CHANGELOG
- Migration guide available in docs

---

## Current Deprecations

No active deprecations. All previously deprecated features have been removed.

---

## Completed Deprecations

### Removed in v0.5.0

| Item | Description | Replaced By |
|------|-------------|-------------|
| `dazzle build` command | Legacy code generation | `dazzle eject run` |
| `dazzle stacks` command | Stack listing | `dazzle eject adapters` |
| `dazzle infra` command | Infrastructure generation | `dazzle eject run` |
| `dazzle.stacks` module | Stack infrastructure | `dazzle.eject` module |
| `--backend`, `--backends` flags | Legacy build flags | Removed |
| `django_micro_modular` stack | Django code generation | DNR or ejection |
| `django_api` stack | Django REST generation | DNR or ejection |
| `express_micro` stack | Express.js generation | DNR or ejection |
| `nextjs_semantic` stack | Next.js generation | DNR or ejection |
| `openapi` stack | OpenAPI generation | `dazzle eject openapi` |

### Removed in v0.2.0

| Item | Description | Replaced By |
|------|-------------|-------------|
| Dazzle Design Tokens (DDT) | Custom CSS token system | DaisyUI |
| `tokens/` directory | Token compiler and CSS | DaisyUI CDN |
| `variables.css`, `utilities.css`, `components.css` | Generated CSS | DaisyUI classes |

---

## How to Check for Deprecations

### CLI

Run any deprecated command to see migration guidance:

```bash
$ dazzle validate  # Will report any deprecated DSL syntax
$ dazzle lint      # Reports warnings including deprecations
```

---

## Requesting Deprecation Extensions

If you need more time to migrate:

1. Open a GitHub issue with:
   - Which deprecated feature you depend on
   - Why migration is difficult
   - Proposed timeline

2. We'll evaluate and may:
   - Extend the grace period
   - Provide migration assistance
   - Create migration tooling

---

## Version Support Matrix

| Version | Status | Support Until |
|---------|--------|---------------|
| v0.2.x | Current | Active development |
| v0.1.x | Legacy | Bug fixes only until v1.0 |
| v1.0.x | Planned | LTS (when released) |

---

## Questions?

- **Migration help**: Open a GitHub issue
- **Feature requests**: Use GitHub Discussions
- **Bug reports**: GitHub Issues
