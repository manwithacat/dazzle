# Messaging & Events

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Messaging and events enable asynchronous communication between components and users. Channels define delivery mechanisms (email, in-app, webhook), while the eventing system routes domain events to subscribers and integration endpoints.

---

## Channel

A messaging channel definition for communication pathways. Channels define how
messages flow through the system with three kinds: email (human-readable),
queue (reliable async processing), and stream (event sourcing with replay).

Channels contain send operations (outbound) and receive operations (inbound),
each with message type references, triggers, field mappings, and throttling.

### Syntax

```dsl
channel <name> ["<Title>"]:
  kind: <email|queue|stream>
  provider: <auto|mailpit|sendgrid|...>

  [config:]
    [from_address: "<email>"]
    [from_name: "<name>"]
    [dead_letter_after: <int>]           # queue
    [retention: <duration>]              # stream
    [partition_key: <field>]             # stream

  [provider_config:]
    [max_per_minute: <int>]
    [max_concurrent: <int>]

  [send <operation_name>:]
    [message: <MessageName>]
    [when: entity <Entity> <event>]
    [when: entity <Entity> status -> <state>]
    [delivery_mode: <outbox|direct>]
    [mapping:]
      [<target> -> <source.path>]
    [throttle:]
      [per_recipient:]
        [window: <duration>]
        [max_messages: <int>]
        [on_exceed: <drop|error|log>]

  [receive <operation_name>:]
    [message: <MessageName>]
    [match:]
      [<field>: "<pattern>"]
    [action: <create|update|upsert> <EntityName>]
    [mapping:]
      [<source> -> <target>]
```

### Example

```dsl
channel notifications "Email Notifications":
  kind: email
  provider: auto

  config:
    from_address: "noreply@example.com"
    from_name: "My App"

  send welcome:
    message: WelcomeEmail
    when: entity User created
    delivery_mode: outbox
    mapping:
      to -> User.email
      name -> User.display_name

  send order_shipped:
    message: ShipmentNotice
    when: entity Order status -> shipped
    mapping:
      to -> Order.customer.email
      order_number -> Order.number

  receive support:
    message: InboundEmail
    match:
      to: "support@example.com"
    action: create SupportTicket
    mapping:
      from -> requester_email
      subject -> title
      body -> description
```

### Best Practices

- Use outbox delivery for transactional consistency
- Set throttle limits to prevent email flooding
- Use queue channels for async processing pipelines
- Use stream channels for event sourcing with replay

**Related:** [Process Steps](processes.md#process-steps), [Entity](entities.md#entity)

---
