# Authoring trial.toml — domain patterns

The generic template in `templates/trial-toml-template.toml` works for most SaaS apps. This guide is for when you want sharper scenarios by leaning into your domain.

## SaaS / general productivity

Works well with the default template. Emphasise: team size, tooling-they're-switching-from, visibility pressures (who's watching performance), the specific decision at stake.

Task patterns that tend to surface framework-level friction:
- "Who has the most X right now?" — tests aggregation surfaces
- "Find the oldest pending Y" — tests sort/filter
- "Did Alex handle the escalation from yesterday?" — tests audit trail
- "I want to hand this off to someone" — tests assignment / transfer flows

## Finserv (lending, trading, payments)

Compliance and audit pressure dominates. Personas are more formally defined: maker vs checker, relationship manager vs risk officer.

Task patterns:
- "Show me every unapproved item older than 24 hours" — tests approval workflows + SLA
- "Who approved this? When?" — tests audit trail surfaces
- "Can this counterparty be traded with?" — tests lookup + cross-entity access control
- "I need to reject this with a reason" — tests rejection flows
- "Show me the position history for this account" — tests time-series views

Identity patterns:
```
You are <NAME>, credit risk officer at a mid-sized bank. You're reviewing
tomorrow's approval queue. Regulators audit quarterly, and every
approval/rejection needs a reason on record. You're evaluating whether
this software can replace the current Excel + email process.
```

Business context should mention: approval SLA (e.g. 4h for investment grade), audit expectations, segregation of duties.

## Healthcare / clinical

Safety pressure dominates; RBAC is non-negotiable. Personas often include nurse, physician, pharmacist, MA.

Task patterns:
- "Can I prescribe this dose to this patient?" — tests safety checks + lookup
- "What did the MA enter for this vitals check?" — tests audit + edit history
- "Show me today's patients in declining status" — tests alerting surfaces
- "I need to order labs — is the form clear about urgency?" — tests field clarity

Identity patterns:
```
You are Dr. <NAME>, attending physician at a 200-bed community hospital.
You typically see 20 patients a day. Your current EMR is <CURRENT>, which
<WHAT_HURTS>. You're evaluating this system for an outpatient pilot.
```

Business context: patient volume, most-common orders, handoff expectations, safety-critical paths.

## Logistics / ops / field service

Location + time constraints dominate. Personas: dispatcher, driver/tech, customer-facing agent.

Task patterns:
- "Which driver should I assign to this urgent pickup?" — tests dispatch UX
- "Is tech X running behind schedule?" — tests real-time status
- "What's the exception rate on this route today?" — tests aggregation
- "Customer called — where's their order?" — tests lookup by phone/email

Identity patterns:
```
You are <NAME>, regional dispatcher for a 30-driver LTL carrier. You're
evaluating this dispatch software during a Tuesday morning — your busiest
shift. Current system is two tabs: Excel tracker + SMS with drivers.
```

## Edtech / assessment

Time pressure + roster management dominates. Personas: teacher, student, admin, parent.

Task patterns:
- "Did any students hand this in late?" — tests deadline UX
- "Show me the three lowest scorers on last week's quiz" — tests ranking
- "Can I see Sam's attendance pattern this term?" — tests time-series
- "I need to excuse an absence" — tests exception workflow

## Multi-tenant / platform

Tenancy boundaries and tenant admin workflows are the interesting surface.

Task patterns:
- "Can tenant A see tenant B's data?" (intentionally test-for-leak)
- "Add a new user to my workspace" — tests delegated admin
- "Show me usage across all workspaces" — tests platform-admin surfaces
- "I accidentally deleted X — can I restore it?" — tests recovery UX

## Graph-heavy (supply chain, social, org charts)

Traversal and visualisation are the interesting surfaces.

Task patterns:
- "Show me suppliers two hops away from XYZ Corp" — tests graph queries
- "Who manages the manager of Alice?" — tests hierarchy UX
- "What components are affected if we stop sourcing from Widget Co?" — tests impact analysis

## Anti-patterns

Avoid these regardless of domain:

- **Tutorial-shaped tasks** — "First click here, then there, verify X appears". This is a Playwright script.
- **One persona doing everything** — if your app has clear role boundaries, separate scenarios per role. Asking a "manager" to do both admin and end-user work confuses the evaluation.
- **Too many tasks (>6)** — agents lose focus and produce shallow verdicts. 3–4 is the sweet spot.
- **Tasks the LLM can complete without touching the UI** — e.g. "look up the entity schema". That's not a trial; it's a knowledge-base query. Tasks should require *doing* work in the app.
- **Explicit success criteria** — "Make sure you can see X, Y, Z". The agent is supposed to *decide* whether what they saw was good enough, not check boxes.

## Iterating on scenarios

The best trial.toml is one you've iterated. After the first trial run:

1. Read the report end-to-end.
2. If the verdict is a shrug ("seems fine") → the identity or tasks were too vague. Add specificity.
3. If the agent flagged things that aren't really friction → the tasks were too leading. Trust the agent less.
4. If the agent gave up early (<10 steps) → either they couldn't log in, or the first task was impossible. Check `login_persona` and task 1.
5. If you got 20+ friction entries, most clustered — read the clusters and ask: which are framework vs DSL? File the framework ones upstream; fix the DSL ones in your app.

Trials aren't deterministic. Two runs of the same scenario will find different things. That's a feature: domain stress-testing is the point, not reproducibility.
