# UX Actions — Test & Improve User Experience

Evaluate and improve the user experience for each persona.

## Phase 1a: Workspace UX Audit (curl-based, parallelizable)

For each persona workspace, evaluate against the 7-point rubric:
1. UUID visibility — are raw UUIDs shown?
2. Information density — is data useful at a glance?
3. Actionability — can users take next steps?
4. Column relevance — are displayed fields meaningful?
5. Data freshness — are timestamps current?
6. Dead-end detection — are there views with no way out?
7. Sidebar coherence — does nav match the persona's role?

### Persona Workspaces to Evaluate

{persona_workspace_table}

## Phase 1b: Persona Journey Testing (sequential, Playwright)

For each persona, test the narrative journey:
- Login as persona → land on default workspace → drill into detail → navigate back
- Verify visual coherence across the journey

## Phase 2: Implement Findings

Group by persona story, prioritize by impact:
- **BLOCKING** — user cannot complete their task
- **CONFUSING** — user can complete but is misled
- **NOISY** — unnecessary clutter
- **POLISH** — cosmetic improvement

Write dual-audience report to `dev_docs/ux-actions-{date}.md`:
- Persona narratives for human stakeholders
- Action tables for agents
