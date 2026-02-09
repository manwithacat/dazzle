---
auto_load: true
globs:
  - "**/process*.py"
  - "**/missions/**/*.py"
  - "**/compiler.py"
  - "**/emitter.py"
---

# Process & Story Schema

## Process Save Format

Processes are saved via `mcp__dazzle__process` with operation `save`. The `processes` array expects objects like:

```json
{
  "name": "order_fulfillment",
  "label": "Order Fulfillment",
  "description": "End-to-end order processing",
  "trigger": {
    "kind": "entity_event",
    "entity": "Order",
    "event": "created"
  },
  "steps": [
    {
      "name": "validate_inventory",
      "kind": "action",
      "action": "check_stock",
      "entity": "Product"
    },
    {
      "name": "charge_payment",
      "kind": "action",
      "action": "process_payment",
      "entity": "Payment"
    }
  ],
  "compensation": {
    "steps": [
      {
        "name": "refund",
        "kind": "action",
        "action": "issue_refund",
        "entity": "Payment"
      }
    ]
  }
}
```

## Trigger Kinds

- `entity_event` — fired when entity is created/updated/deleted
- `schedule` — cron-based trigger
- `manual` — user-initiated
- `webhook` — external HTTP trigger
- `compose` — triggered by another process

## Step Kinds

- `action` — execute an operation on an entity
- `decision` — branching logic (has `conditions`)
- `wait` — pause for event or timeout
- `notify` — send notification
- `subprocess` — invoke another process

## Story Format

Stories are saved via `mcp__dazzle__story` with operation `save`:

```json
{
  "id": "story-001",
  "title": "Admin creates new user",
  "persona": "admin",
  "entity": "User",
  "action": "create",
  "preconditions": ["Admin is logged in"],
  "steps": ["Navigate to Users", "Click Create", "Fill form", "Submit"],
  "postconditions": ["User appears in list", "Welcome email sent"],
  "status": "accepted"
}
```

## Compiler & Emitter

- `NarrativeCompiler` groups observations by (category, primary entity), prioritizes by severity x frequency
- `DslEmitter` generates DSL from proposals — template-based for: missing_crud, ux_issue, workflow_gap, navigation_gap
- `infer_crud_action(text)` — shared keyword matcher for create/read/update/delete
- `build_emit_context(appspec)` extracts entity/surface/workspace names + field info
