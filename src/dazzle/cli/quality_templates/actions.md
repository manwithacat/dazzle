# Action Items — Discover & Fix

Parse the latest nightly report and implement fixes.

## Steps

1. Read the latest `dev_docs/nightly-*.md` report
2. Run MCP tools to discover additional issues:
   - `sentinel(findings)` — static analysis findings
   - `semantics(compliance)` — compliance gaps
   - `semantics(extract_guards)` — missing guards
   - `semantics(analytics)` — analytics gaps
3. Merge and deduplicate findings
4. Prioritize by impact: BLOCKING > CONFUSING > NOISY > POLISH
5. Implement DSL fixes for each finding
6. Run `dazzle validate` after each fix to verify
7. Write report to `dev_docs/actions-{date}.md`

## Project Context

- **Entities**: {entity_list}
- **Personas**: {persona_list}
