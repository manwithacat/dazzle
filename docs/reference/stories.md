# Stories

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Stories capture expected user-visible outcomes in a structured format tied to personas and entities. They serve as the contract between specification and implementation, and provide traceability from requirements through processes to test coverage.

---

## Story

A behavioural user story that bridges DSL specifications and implementation.
Stories describe what should happen (outcomes), when (triggers), who is involved
(actors, entities), and what constraints must hold. Stories use Gherkin-style
given/when/then conditions and can include unless branches for exception handling.

Stories can be defined in DSL syntax (v0.22.0) or proposed by LLM and stored as
JSON artifacts in .dazzle/stories/. They link to processes via the implements field.

Workflow: propose -> save -> get -> generate_tests -> coverage

### Syntax

```dsl
story <story_id> "<Title>":
  actor: <PersonaName>
  trigger: <form_submitted|status_changed|timer_elapsed|external_event|user_click|cron_daily|cron_hourly>
  scope: [<Entity1>, <Entity2>, ...]

  given:
    - <precondition expression>
    - <precondition expression> [-> Entity.field]

  when:
    - <trigger condition>

  then:
    - <expected outcome>
    - <expected outcome>

  [unless:]
    [- <exception condition>:]
        [then: <alternative outcome>]
```

### Example

```dsl
story ST-001 "Staff sends invoice to client":
  actor: StaffUser
  trigger: status_changed
  scope: [Invoice, Client]

  given:
    - Invoice.status is 'draft'
    - Client.email is set

  when:
    - Invoice.status changes to 'sent'

  then:
    - Invoice email is sent to Client.email
    - Invoice.sent_at is recorded

  unless:
    - Client.email is missing:
        then: FollowupTask is created

story ST-002 "Customer creates support ticket":
  actor: Customer
  trigger: form_submitted
  scope: [Ticket]

  given:
    - Customer is authenticated

  when:
    - Ticket form is submitted

  then:
    - Ticket is created with status 'open'
    - Ticket.created_by is set to current user
```

### Best Practices

- Use stable IDs (ST-001, ST-002) for traceability
- Keep stories focused on one coherent behaviour
- Link stories to processes via implements field
- Use given/when/then for clear acceptance criteria
- Use unless branches for exception handling

**Related:** [Process](processes.md#process), [Persona](ux.md#persona), [Entity](entities.md#entity), [Scenario](testing.md#scenario)

---
