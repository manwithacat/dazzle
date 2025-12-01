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

### Code Generation Stacks

| Stack | Deprecated | Removal | Migration |
|-------|------------|---------|-----------|
| `django_micro_modular` | v0.2.0 | v1.0.0 | Use DNR runtime |
| `django_api` | v0.2.0 | v1.0.0 | Use DNR runtime |
| `express_micro` | v0.2.0 | v1.0.0 | Use DNR runtime |
| `nextjs_semantic` | v0.2.0 | v1.0.0 | Use DNR runtime |
| `openapi` | v0.2.0 | v1.0.0 | Use `dazzle dnr build-api` |
| `terraform` | v0.2.0 | v1.0.0 | Manual infrastructure |

**Why**: The Dazzle Native Runtime (DNR) provides a superior development experience - run DSL directly without code generation. Legacy stacks required maintaining multiple code generators for different frameworks.

**Migration**:
```bash
# Before (legacy)
dazzle build --stack django_micro_modular
cd build && python manage.py runserver

# After (DNR)
dazzle dnr serve
```

### CLI Flags

| Flag | Deprecated | Removal | Migration |
|------|------------|---------|-----------|
| `--backend` | v0.2.0 | v1.0.0 | Use `--stack` |
| `--backends` | v0.2.0 | v1.0.0 | Use `--stack` |
| `--single-container` | v0.2.0 | v1.0.0 | No longer needed |

### Commands

| Command | Deprecated | Removal | Migration |
|---------|------------|---------|-----------|
| `dazzle infra` | v0.2.0 | v1.0.0 | Use `dazzle build --stack docker` |

---

## Completed Deprecations

### Removed in v0.2.0

| Item | Description | Replaced By |
|------|-------------|-------------|
| Dazzle Design Tokens (DDT) | Custom CSS token system | DaisyUI |
| `tokens/` directory | Token compiler and CSS | DaisyUI CDN |
| `variables.css`, `utilities.css`, `components.css` | Generated CSS | DaisyUI classes |

---

## How to Check for Deprecations

### CLI Warnings

Deprecated features emit warnings:
```bash
$ dazzle build --backend django_micro_modular
Warning: --backend is deprecated, use --stack instead
Warning: Stack 'django_micro_modular' is deprecated. Use 'dazzle dnr serve' instead.
```

### Validation

```bash
dazzle validate --strict  # Fails on deprecated usage
dazzle lint               # Reports deprecation warnings
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
