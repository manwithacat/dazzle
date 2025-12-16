# ADR-0001: MkDocs Material Documentation Site

**Status:** Accepted
**Date:** 2024-12-16

## Context

The Dazzle project has accumulated ~25 high-quality documentation files spread across `docs/` and `dev_docs/` directories. These documents cover:

- DSL reference (10 files)
- Architecture documentation
- Installation and getting started guides
- Testing infrastructure
- Example project documentation

The current structure has limitations:

1. **No navigation** - Users must know file paths to find content
2. **No search** - Finding information requires grep
3. **No deployment** - Docs only viewable on GitHub or locally
4. **Inconsistent format** - Mixed styles and cross-references

## Decision

Adopt **MkDocs Material** as the documentation framework, deployed to **GitHub Pages** via **GitHub Actions**.

### Why MkDocs Material?

| Criterion | MkDocs Material | Docusaurus | Sphinx |
|-----------|-----------------|------------|--------|
| Setup complexity | Low | Medium | High |
| Python-friendly | Yes | No | Yes |
| Search quality | Excellent | Good | Good |
| Theme quality | Excellent | Good | Variable |
| LLM compatibility | Good | Good | Poor |
| Build time | Fast | Medium | Slow |

MkDocs Material provides:

- **Instant navigation** with client-side routing
- **Built-in search** with highlighting
- **Material Design** theme out of the box
- **Mermaid diagrams** with native support
- **Edit on GitHub** links
- **Dark mode** toggle

### Deployment

GitHub Actions workflow:

1. Build docs on all PRs (catches broken links)
2. Deploy to GitHub Pages on main branch pushes
3. Docs available at `https://manwithacat.github.io/dazzle/`

### LLM Ingestion

Two special files for AI agent consumption:

- `/llms.txt` - Curated index of key pages
- `/llms-full.txt` - Comprehensive content export

## Consequences

### Positive

- Professional documentation site with zero hosting cost
- Searchable content improves discoverability
- Consistent structure and navigation
- CI catches documentation issues early
- AI agents can consume structured docs

### Negative

- Must maintain `mkdocs.yml` nav configuration
- Content changes require rebuilds (vs. GitHub's instant preview)
- Additional CI time (~30 seconds)

### Neutral

- Existing content migrated to new structure
- Internal docs (`dev_docs/`) remain separate
- ADR format adopted for architectural decisions

## Alternatives Considered

### 1. Keep Current Structure

Continue with raw Markdown in `docs/` directory.

**Rejected:** Doesn't solve navigation or search problems.

### 2. GitHub Wiki

Use GitHub's built-in wiki feature.

**Rejected:** Limited formatting, no search, separate from repo.

### 3. Docusaurus

React-based documentation framework.

**Rejected:** More complex setup, less Python-friendly, slower builds.

## Implementation

See plan file for detailed implementation steps covering:

1. Infrastructure setup (mkdocs.yml, workflows)
2. Content migration
3. Navigation configuration
4. LLM ingestion files
5. Validation and deployment
