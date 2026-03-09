# Governance

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Governance constructs enforce organisational policies, approval workflows, and service-level agreements. Approvals define multi-step sign-off chains, while SLAs set measurable targets with escalation rules for time-sensitive operations.

---

## Approval

A first-class approval gate definition. Approvals intercept entity state transitions
and require human sign-off before proceeding. Features include quorum (number of
approvals needed), threshold conditions (when approval is required), escalation
timers, auto-approve rules, and outcome mappings to entity status transitions.

### Syntax

```dsl
approval <name> "<Title>":
  entity: <EntityName>
  trigger: <field> -> <value>
  approver_role: <role_name>
  [quorum: <int>]
  [threshold: <condition>]
  [escalation:]
    [after: <int> <hours|days>]
    [to: <escalation_role>]
  [auto_approve:]
    [when: <condition>]
  [outcomes:]
    [<decision> -> <target_status>]
```

### Example

```dsl
approval PurchaseApproval "Purchase Order Approval":
  entity: PurchaseOrder
  trigger: status -> pending_approval
  approver_role: finance_manager
  quorum: 1
  threshold: amount > 1000
  escalation:
    after: 48 hours
    to: finance_director
  auto_approve:
    when: amount <= 100
  outcomes:
    approved -> approved
    rejected -> rejected

approval LeaveRequest "Leave Approval":
  entity: LeaveRequest
  trigger: status -> submitted
  approver_role: line_manager
  quorum: 1
  outcomes:
    approved -> approved
    rejected -> rejected
```

### Best Practices

- Use threshold to skip approval for low-value items
- Set escalation to avoid approval bottlenecks
- Use auto_approve for items below a safe threshold
- Map outcomes to entity status transitions for clean workflow

**Related:** [Entity](entities.md#entity), [State Machine](entities.md#state-machine), [Sla](governance.md#sla), [Process](processes.md#process)

---

## Sla

A Service Level Agreement definition with deadline tiers, business hours, and
breach actions. SLAs track time between state transitions on entities using
starts_when, pauses_when, and completes_when conditions. Multiple tiers
(warning, breach, critical) define escalation levels. Business hours ensure
SLA clocks only run during working time.

### Syntax

```dsl
sla <name> "<Title>":
  entity: <EntityName>
  starts_when: <field> -> <value>
  [pauses_when: <field> = <value>]
  completes_when: <field> -> <value>
  tiers:
    <tier_name>: <int> <hours|days|minutes>
    ...
  [business_hours:]
    [schedule: "<Mon-Fri HH:MM-HH:MM>"]
    [timezone: "<IANA_timezone>"]
  [on_breach:]
    [notify: <role_name>]
    [set: <field> = <value>]
```

### Example

```dsl
sla TicketResponse "Ticket Response SLA":
  entity: SupportTicket
  starts_when: status -> open
  pauses_when: status = on_hold
  completes_when: status -> resolved
  tiers:
    warning: 4 hours
    breach: 8 hours
    critical: 24 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
  on_breach:
    notify: support_lead
    set: escalated = true

sla OrderFulfillment "Order Fulfillment SLA":
  entity: Order
  starts_when: status -> confirmed
  completes_when: status -> shipped
  tiers:
    warning: 1 days
    breach: 3 days
```

### Best Practices

- Use business_hours to exclude non-working time from SLA calculations
- Set tiers for progressive escalation (warning before breach)
- Use on_breach to notify responsible roles and flag records
- Use pauses_when for states where the clock should stop (e.g., on_hold)

**Related:** [Entity](entities.md#entity), [State Machine](entities.md#state-machine), [Approval](governance.md#approval), [Process](processes.md#process)

---
