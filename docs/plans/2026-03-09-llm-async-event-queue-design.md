# Design: LLM Intent Async Event Queue Integration (#417)

## Architecture

Three layers, each building on the previous:

```
Layer 1: Background Job Queue
  - In-process async queue with semaphore + token bucket
  - AIJob lifecycle (pending -> running -> completed/failed)
  - Polling endpoint + llm_intent:completed/failed events

Layer 2: Entity Event Triggers
  - DSL trigger clause on llm_intent
  - EntityEventBus handler submits to queue
  - Write-back to entity fields on completion

Layer 3: Process Step Execution
  - LLM_INTENT as a StepKind in process IR
  - Linear checkpointed process executor (Model C)
  - Steps share outputs, checkpoint after each
```

## DSL Surface

### Intent triggers

```dsl
llm_intent classify_ticket "Classify Ticket":
  model: support_classifier
  prompt: |
    Classify this ticket: {{ input.title }} - {{ input.body }}

  trigger:
    on: Ticket.created
    input_map:
      title: entity.title
      body: entity.description
    write_back:
      Ticket.category: output
      Ticket.confidence: output.confidence
```

Multiple triggers:

```dsl
llm_intent classify_ticket "Classify Ticket":
  model: support_classifier
  trigger:
    - on: Ticket.created
      input_map:
        title: entity.title
      write_back:
        Ticket.category: output
    - on: Ticket.updated
      when: entity.category == null
      input_map:
        title: entity.title
      write_back:
        Ticket.category: output
```

### Rate limits and concurrency

```dsl
llm_config:
  default_model: claude
  rate_limits:
    claude: 60
    gpt4: 30
  concurrency:
    claude: 5
    gpt4: 3
```

### Process with LLM step

```dsl
process route_ticket "Route Ticket":
  trigger:
    on: Ticket.created

  step classify:
    llm_intent: classify_ticket
    input_map:
      title: trigger.entity.title
      body: trigger.entity.description

  step route:
    condition: classify.output == "billing"
    on_true:
      service: TicketService.assign
      args: { queue: "billing" }
    on_false:
      service: TicketService.assign
      args: { queue: "general" }
```

## Result Delivery

Write-back is the mechanism, events are the consequence:

1. Write-back to entity fields (declared in DSL, deterministic, checkpointed)
2. Entity update event fires automatically (write-back goes through CRUD service)
3. `llm_intent:completed` / `llm_intent:failed` events emitted on event bus
4. Webhook delivery is a future concern (just another event subscriber)

## Rate Limiting

Two complementary mechanisms:

- **Token bucket** (per model): enforces requests-per-minute from `rate_limits`
- **Semaphore** (per model): caps concurrent in-flight requests from `concurrency`

Job dequeued -> acquire semaphore -> check token bucket -> execute -> release both.

## Process Execution Model

**Model C: Checkpointed linear log.**

Each step executes and commits, process records which steps completed. On restart,
completed steps are skipped and execution resumes from last checkpoint. Steps must
be individually idempotent for external side effects, but the checkpoint mechanism
prevents re-execution of completed steps.

Supported step kinds: `LLM_INTENT`, `SERVICE`, `CONDITION`.
PARALLEL, WAIT, FOREACH, HUMAN_TASK deferred to future work.

## IR Changes

### llm.py

- `LLMTriggerEvent(StrEnum)`: created, updated, deleted
- `LLMTriggerSpec(BaseModel)`: on_entity, on_event, input_map, write_back, when
- `LLMIntentSpec`: add `triggers: list[LLMTriggerSpec] = []`
- `LLMConfigSpec`: add `concurrency: dict[str, int] | None = None`

### process.py

- `StepKind`: add `LLM_INTENT = "llm_intent"`
- `ProcessStepSpec`: add `llm_intent: str | None`, `input_map: dict[str, str] | None`

### event_bus.py

- `LLMEventType(StrEnum)`: INTENT_COMPLETED, INTENT_FAILED
- Emit method for LLM-specific events with full context payload

## Files

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle_back/runtime/llm_queue.py` | CREATE | Job queue, token bucket, semaphore, workers |
| `src/dazzle_back/runtime/llm_trigger.py` | CREATE | Entity event -> intent trigger matcher + write-back |
| `src/dazzle_back/runtime/process_executor.py` | CREATE | Linear checkpointed process executor |
| `src/dazzle/core/ir/llm.py` | MODIFY | LLMTriggerSpec, LLMTriggerEvent, concurrency |
| `src/dazzle/core/ir/process.py` | MODIFY | LLM_INTENT step kind, llm_intent/input_map fields |
| `src/dazzle/core/dsl_parser_impl/` | MODIFY | Parse trigger clause, concurrency, llm_intent steps |
| `src/dazzle_back/runtime/event_bus.py` | MODIFY | LLMEventType, LLM event emission |
| `src/dazzle_back/runtime/llm_routes.py` | MODIFY | Async endpoint, job polling |
| `src/dazzle_back/runtime/llm_executor.py` | MODIFY | entity_type/entity_id on AIJob |
| `src/dazzle_back/runtime/server.py` | MODIFY | Wire queue, trigger matcher, process executor |
| `src/dazzle/mcp/server/handlers/graph.py` | MODIFY | triggers operation |
| `src/dazzle/mcp/server/tools_consolidated.py` | MODIFY | triggers in graph tool |
| `src/dazzle/mcp/server/handlers_consolidated.py` | MODIFY | Register triggers handler |
| `tests/unit/test_llm_queue.py` | CREATE | Queue, bucket, semaphore tests |
| `tests/unit/test_llm_trigger.py` | CREATE | Trigger matching, write-back tests |
| `tests/unit/test_process_executor.py` | CREATE | Linear execution, checkpointing tests |
| `tests/unit/test_llm_trigger_parser.py` | CREATE | DSL parsing tests |

## Implementation Order

1. IR changes (foundation, no runtime effect)
2. Parser (trigger clause, concurrency, llm_intent steps)
3. Job queue (core async infrastructure)
4. Trigger matcher (entity events fire intents)
5. LLM routes + events (async endpoint, polling, events)
6. Process executor (linear checkpointed execution)
7. Server wiring (connect everything)
8. Graph tool (triggers cross-referencing)
9. Tests at each step
