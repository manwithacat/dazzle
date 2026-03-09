# Processes

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Processes orchestrate durable, multi-step workflows across entities and services. They handle lifecycle transitions, scheduled jobs, event-driven pipelines, and cross-entity operations that go beyond simple CRUD.

---

## Process

A durable workflow process that orchestrates multi-step operations across entities
and services. Processes handle lifecycle transitions, scheduled jobs, event-driven
pipelines, and cross-entity operations that go beyond simple CRUD.

Workflow: propose → save → inspect → coverage
- propose: clusters uncovered stories into workflow design briefs
- save: persists composed ProcessSpec definitions
- inspect: shows a single process with steps, trigger, and linked stories
- coverage: checks which story outcomes are satisfied by processes

### Syntax

```dsl
Key fields in ProcessSpec:
  name: str               # Process identifier
  title: str              # Human-readable title
  implements: list[str]   # Story IDs this process covers (e.g. ['ST-001', 'ST-002'])
  trigger: ProcessTriggerSpec  # What starts the process (entity event, cron, manual, etc.)
  steps: list[ProcessStepSpec] # Ordered activities (SERVICE, SEND, WAIT, HUMAN_TASK, etc.)
  outputs: list[ProcessOutputField]  # Process output fields
  compensations: list[CompensationSpec]  # Saga rollback handlers

Steps and outputs can declare satisfies refs for explicit coverage traceability:
  satisfies:
    - story: "ST-002"
      outcome: "the invoice is marked as sent"
```

### Example

```dsl
# CRUD process (simple — usually handled by surfaces, not processes):
#   Entity.create / Entity.update / Entity.delete via surface handlers

# Lifecycle process (status transitions):
process order_lifecycle:
  trigger: entity Order status -> confirmed
  steps:
    - name: validate_inventory
      kind: service
      service: Inventory.check_availability
    - name: process_payment
      kind: service
      service: Payment.charge
      compensate_with: refund_payment
    - name: fulfill_order
      kind: service
      service: Fulfillment.ship
  implements: [ST-010, ST-011, ST-012]

# Scheduled process (cron):
process daily_report:
  trigger: cron "0 8 * * *"
  steps:
    - name: generate_report
      kind: service
      service: Reporting.daily_summary
    - name: send_email
      kind: send
      channel: email
      message: daily_report
  implements: [ST-020]
```

**Related:** [Entity](entities.md#entity), Service, [Story](stories.md#story), [State Machine](entities.md#state-machine), Compensation

---

## Process Steps

Process step kinds define the type of activity in a workflow. Each step has a kind
that determines its behaviour and required fields.

Step kinds:
- service: Call a domain service
- send: Send a message via channel
- wait: Wait for a duration or signal
- human_task: Wait for a human action (renders a surface with outcome buttons)
- subprocess: Start another process
- parallel: Execute steps concurrently
- condition: Conditional branch (on_true/on_false goto)
- side_effect: Execute effects only (create/update entities)
- query: Query entities matching a filter
- foreach: Iterate over results from a previous step
- llm_intent: Execute an LLM intent

### Syntax

```dsl
steps:
  - step <name>:
      kind: <service|send|wait|human_task|subprocess|parallel|condition|side_effect|query|foreach|llm_intent>

      # For SERVICE:
      service: <ServiceName>

      # For SEND:
      channel: <channel_name>
      message: <message_type>

      # For WAIT:
      wait_duration_seconds: <int>
      wait_for_signal: "<signal_name>"

      # For HUMAN_TASK:
      human_task:
        surface: <surface_name>
        assignee_role: <role>
        outcomes:
          - name: approve
            label: "Approve"
            goto: <next_step|complete|fail>

      # For CONDITION:
      condition: "<expression>"
      on_true: <step_name>
      on_false: <step_name>

      # For LLM_INTENT:
      llm_intent: <intent_name>

      # Common options:
      [timeout: <duration>]
      [retry:]
        [max_attempts: <int>]
        [backoff: <fixed|exponential|linear>]
      [on_success: <step_name>]
      [on_failure: <step_name>]
      [compensate_with: <handler_name>]
```

### Example

```dsl
process expense_approval "Expense Approval":
  trigger: entity ExpenseReport status -> submitted

  steps:
    - step validate:
        kind: service
        service: validate_expense
        timeout: 30s

    - step review:
        kind: human_task
        human_task:
          surface: expense_review
          assignee_role: manager
          outcomes:
            - name: approve
              label: "Approve Expense"
              goto: complete
            - name: reject
              label: "Reject"
              goto: fail

    - step notify:
        kind: send
        channel: notifications
        message: ExpenseDecision
```

### Best Practices

- Use service steps for business logic, send for notifications
- Use human_task for approval workflows with explicit outcome buttons
- Use parallel with fail_fast policy for independent operations
- Set compensate_with for steps that need saga rollback

**Related:** [Process](processes.md#process), [Schedule](processes.md#schedule), [Story](stories.md#story)

---

## Schedule

A scheduled job definition for recurring tasks. Schedules are a simplified form of process triggered by cron expressions or fixed intervals. Supports catch-up for missed runs, overlap policies, and the same step kinds as processes.

### Syntax

```dsl
schedule <name> "<Title>":
  [cron: "<cron_expression>"]
  [interval_seconds: <int>]
  [timezone: "<IANA_timezone>"]
  [catch_up: true|false]
  [overlap: <skip|queue|cancel_previous|allow>]
  [timeout: <duration>]

  steps:
    - step <name>:
        service: <ServiceName>
        [timeout: <duration>]
```

### Example

```dsl
schedule daily_report "Daily Report":
  cron: "0 8 * * *"
  timezone: "Europe/London"
  catch_up: false
  overlap: skip
  timeout: 1h

  steps:
    - step generate:
        service: generate_report
        timeout: 5m

schedule hourly_sync "Hourly Data Sync":
  interval_seconds: 3600
  overlap: skip

  steps:
    - step sync:
        service: sync_external_data
        timeout: 10m
```

### Best Practices

- Use cron for specific times, interval_seconds for fixed periods
- Set overlap: skip to prevent concurrent runs of the same schedule
- Use catch_up: false unless missed runs must execute on startup
- Always set a timeout to prevent runaway jobs

**Related:** [Process](processes.md#process), [Process Steps](processes.md#process-steps)

---
