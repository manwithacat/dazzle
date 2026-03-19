# Nightly Quality Check

Run the nightly quality check for this project.

## Steps

1. Check if a newer version of dazzle-dsl is available
2. Run `dazzle validate` to verify DSL pipeline
3. Run `dazzle lint` for extended checks
4. Run `dazzle sentinel scan` for static analysis
5. Check site health: curl {site_url}/health (if configured)
6. Write report to `dev_docs/nightly-{date}.md`

## Project Context

- **Personas**: {persona_list}
- **Entities**: {entity_count} entities
- **Workspaces**: {workspace_list}
