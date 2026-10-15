# Rhythms: Longitudinal UX Evaluation

## The Problem

You've built an app with a dozen surfaces, four personas, and thirty stories. Every story passes. Every surface renders. But can a new user actually get from signup to their first meaningful outcome?

Stories test atomic interactions — "user submits form, record is created." Processes model multi-actor state machines — "student submits, teacher grades, student views result." Neither asks the longitudinal question: does this persona's journey through the app make sense over time?

A new user doesn't just "enroll in a course." They discover courses, enroll, engage with content across weeks, and eventually earn a credential. Each step works in isolation; the question is whether the journey holds together.

## What Rhythms Are

A **rhythm** is a journey map for a single persona through your app, organized into temporal phases. It expresses the natural cadence of how someone uses the system over time.

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "first 30 days"

  phase discovery:
    scene browse_catalog "Browse Available Courses":
      on: course_list
      action: filter, browse
      expects: "visible_results"

  phase engagement:
    scene complete_module "Complete First Module":
      on: module_view
      action: submit
      entity: ModuleCompletion
      expects: "progress_recorded"

  phase mastery:
    scene view_progress "Check Progress":
      on: progress_dashboard
      action: browse
      expects: "credential_visible"
```

Three constructs, nested:

- **Rhythm** — the journey. Bound to one persona. Has a cadence hint and one or more phases.
- **Phase** — a stage in the journey (discovery, engagement, mastery). Groups related scenes.
- **Scene** — a single evaluable action. Bound to a specific surface. This is what gets checked.

## Building a Rhythm Step by Step

Start with the persona and the question you want to answer:

```dsl
rhythm onboarding "New User Onboarding":
  persona: new_user
  cadence: "first 30 days"
```

`persona:` is a hard reference — it must match an existing persona definition. The linker validates this at compile time. `cadence:` is a free-form string — the framework doesn't interpret it. An AI agent uses it to understand temporal context when evaluating or proposing changes.

Add a phase:

```dsl
  phase discovery:
```

Phase names must be unique within the rhythm. They represent journey stages, not calendar dates. "Discovery" could mean "day 1" for a SaaS onboarding or "September" for an academic app — the DSL doesn't prescribe this.

Scene names must be unique within the entire rhythm, not just within their phase. Two phases cannot both define a scene named `review_progress`.

Add scenes to the phase:

```dsl
    scene browse_catalog "Browse Available Courses":
      on: course_list
      action: filter, browse
      expects: "visible_results"
```

- `on:` is a hard reference — must match an existing surface. The linker validates this.
- `action:` is free-form — describes what the persona does. Not an enum. Domain-specific.
- `expects:` is free-form — the expected outcome. Agents interpret this during evaluation.

Optionally link to an entity or story:

```dsl
    scene enroll "Enroll in First Course":
      on: course_detail
      action: submit
      entity: Enrollment
      expects: "enrollment_confirmed"
      story: ST-005
```

- `entity:` if present, must match an existing entity. Validated at compile time.
- `story:` if present, must match an existing story. Validated at compile time. Bridges rhythms and stories — "this scene exercises this story."

## The Structural/Semantic Split

This is the key design principle. Some properties are **structural** — validated deterministically at compile time:

| Property | Validated Against |
|----------|-------------------|
| `persona:` | Must match existing persona |
| `on:` | Must match existing surface |
| `entity:` | Must match existing entity (if present) |
| `story:` | Must match existing story (if present) |

Others are **semantic** — free-form strings that agents interpret per domain:

| Property | Purpose |
|----------|---------|
| `cadence:` | Temporal frequency hint ("quarterly", "first 30 days", "academic year") |
| `action:` | What the persona does ("filter, browse", "submit", "review") |
| `expects:` | Expected outcome ("visible_results", "enrollment_confirmed") |

The DSL captures structure deterministically. Agents add temporal and domain-specific meaning. This means:

- Compilation is always deterministic — no LLM involved in parsing or linking
- The same rhythm DSL works across domains — an agent specializes "quarterly" to mean April–March for accounting or September–September for education
- Validation catches real errors (referencing a surface that doesn't exist) without false positives on domain-specific language

## When to Use What

| Question | Construct | Why |
|----------|-----------|-----|
| "Does submitting this form create a record?" | **Story** | Atomic interaction, one step, one outcome |
| "When an order is confirmed, does payment → fulfillment → notification happen?" | **Process** | Multi-actor state machine with handoffs and compensations |
| "Can a new user get from signup to their first meaningful outcome?" | **Rhythm** | Single persona, multiple surfaces, temporal progression |
| "Do all personas have complete journeys through the app?" | **Rhythm coverage** | Cross-cutting gap analysis |

**Rules of thumb:**

- If it involves one persona acting on one surface → **story**
- If it involves handoffs between personas (student submits → teacher grades) → **process**
- If it follows one persona through multiple surfaces over time → **rhythm**
- Stories and rhythms can coexist — a scene's `story:` property bridges them

## Using MCP Tools

The `rhythm` MCP tool reads rhythms back from the parsed AppSpec:

**Find missing rhythms:**
```
"Which personas don't have rhythms yet?"
→ rhythm coverage (persona/surface coverage matrix, highlights gaps)
```

**Inspect a rhythm:**
```
"Show me the onboarding rhythm"
→ rhythm get (full rhythm detail as JSON)
```

`rhythm list` names every rhythm with its persona, cadence and phase counts.

## Gap Analysis

The `pipeline` quality run carries a `rhythm(gaps)` step: static analysis against the
parsed AppSpec, no running app required. It reports scenes whose story is missing or still
draft, scenes with no `story:` link, stories no scene references, personas with no ambient
phase, and personas with stories but no rhythm. The gap kinds,
severities and ordering are in the [Rhythms reference](../reference/rhythms.md#gaps-analysis).

## Full Example

A multi-phase rhythm for an accounting app:

```dsl
rhythm quarterly_close "Quarterly Close Process":
  persona: accountant
  cadence: "quarterly"

  phase preparation:
    scene review_outstanding "Review Outstanding Invoices":
      on: invoice_list
      action: filter, browse
      expects: "all_invoices_visible"

    scene reconcile_accounts "Reconcile Bank Accounts":
      on: reconciliation_surface
      action: submit
      entity: Reconciliation
      expects: "accounts_balanced"

  phase execution:
    scene generate_reports "Generate Financial Reports":
      on: report_builder
      action: submit
      entity: FinancialReport
      expects: "reports_generated"

    scene review_pnl "Review Profit & Loss":
      on: pnl_dashboard
      action: browse
      expects: "pnl_accurate"

  phase completion:
    scene submit_filing "Submit Regulatory Filing":
      on: filing_surface
      action: submit
      entity: RegulatoryFiling
      expects: "filing_submitted"
      story: ST-040
```

This rhythm answers: "Can an accountant complete a full quarterly close using this app?" Static evaluation checks that every surface exists, every entity is used by its bound surface, and the persona can navigate between them.
