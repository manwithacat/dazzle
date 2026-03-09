# LLM Models & Intents

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

DAZZLE supports declarative LLM job definitions for AI-powered tasks such as classification, extraction, and generation. This page covers model configuration, intent definitions with prompt templates, and global LLM settings including rate limits and PII policies.

---

## Llm Model

LLM provider and model configuration. Defines provider, model ID, performance tier, token limits, and optional cost tracking per 1K tokens. Providers: anthropic, openai, google, local. Tiers: fast (low latency), balanced (default), quality (best output).

### Syntax

```dsl
llm_model <name> "<Title>":
  provider: <anthropic|openai|google|local>
  model_id: <model_identifier>
  [tier: <fast|balanced|quality>]
  [max_tokens: <int>]
  [cost_per_1k_input: <decimal>]
  [cost_per_1k_output: <decimal>]
```

### Example

```dsl
# Fast model for simple classifications
llm_model claude_haiku "Claude Haiku (Fast)":
  provider: anthropic
  model_id: claude-3-haiku-20240307
  tier: fast
  max_tokens: 1024

# Balanced model for most tasks
llm_model claude_sonnet "Claude Sonnet (Balanced)":
  provider: anthropic
  model_id: claude-3-5-sonnet-20241022
  tier: balanced
  max_tokens: 4096
  cost_per_1k_input: 0.003
  cost_per_1k_output: 0.015

# Alternative provider
llm_model gpt4o_mini "GPT-4o Mini":
  provider: openai
  model_id: gpt-4o-mini
  tier: fast
  max_tokens: 2048
```

**Related:** [Llm Intent](llm.md#llm-intent), [Llm Config](llm.md#llm-config)

---

## Llm Config

Global LLM configuration for the application. Sets default model, default provider, artifact storage (local/s3/gcs), logging policy, per-model rate limits (requests per minute), per-model concurrency limits (max concurrent requests), and budget alerts.

### Syntax

```dsl
llm_config:
  [default_model: <llm_model_name>]
  [default_provider: <anthropic|openai|google|local>]
  [budget_alert_usd: <decimal>]
  [artifact_store: <local|s3|gcs>]
  [logging:]
    [log_prompts: true|false]
    [log_completions: true|false]
    [redact_pii: true|false]
  [rate_limits:]
    [<model_name>: <requests_per_minute>]
  [concurrency:]
    [<model_name>: <max_concurrent_requests>]
```

### Example

```dsl
llm_config:
  default_model: claude_sonnet
  artifact_store: local
  budget_alert_usd: 50.00
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_haiku: 100
    claude_sonnet: 60
    gpt4o_mini: 50
  concurrency:
    claude_haiku: 10
    claude_sonnet: 5
    gpt4o_mini: 3
```

**Related:** [Llm Model](llm.md#llm-model), [Llm Intent](llm.md#llm-intent), [Llm Concurrency](llm.md#llm-concurrency)

---

## Llm Intent

LLM job definition for AI-powered tasks like classification, extraction, or generation. Defines model, prompt template, timeout, retry, PII policies, and optional entity event triggers with input/output mapping.

### Syntax

```dsl
llm_intent <name> "<Title>":
  model: <llm_model_name>
  prompt: "<template with {{ input.field }} variables>"
  [description: "<text>"]
  [output_schema: <EntityName>]
  [timeout: <seconds>]
  [vision: true|false]
  [retry:]
    [max_attempts: <int>]
    [backoff: <linear|exponential>]
    [initial_delay_ms: <int>]
    [max_delay_ms: <int>]
  [pii:]
    [scan: true|false]
    [action: <warn|redact|reject>]
  [trigger:]
    [on_entity: <EntityName>]
    [on_event: <created|updated|deleted>]
    [input_map:]
      [<key>: entity.<field>]
    [write_back:]
      [<Entity.field>: output]
    [when: "<condition>"]
```

### Example

```dsl
# Simple classification - auto-triggers on new tickets
llm_intent classify_ticket "Classify Support Ticket":
  model: claude_haiku
  prompt: "Classify this support ticket into exactly one category: billing, technical, feature_request, account, or other.\n\nTicket:\n{{ input.description }}\n\nRespond with only the category name."
  timeout: 15
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      description: entity.description

# Structured output with retry and PII scanning
llm_intent assess_priority "Assess Ticket Priority":
  model: claude_sonnet
  prompt: "Assess the priority of this support ticket.\n\nTicket:\n{{ input.description }}"
  output_schema: PriorityAssessment
  timeout: 30
  retry:
    max_attempts: 3
    backoff: exponential
  pii:
    scan: true
    action: redact

# Response generation with linear retry
llm_intent suggest_response "Suggest Response":
  model: claude_sonnet
  prompt: "Suggest a helpful response for this ticket.\n\nCategory: {{ input.category }}\nDescription: {{ input.description }}"
  timeout: 45
  retry:
    max_attempts: 2
    backoff: linear
    initial_delay_ms: 500
  pii:
    scan: true
    action: warn
```

**Related:** [Llm Model](llm.md#llm-model), [Llm Config](llm.md#llm-config), [Llm Trigger](llm.md#llm-trigger)

---

## Llm Trigger

A trigger clause on an llm_intent that fires the intent automatically when an entity lifecycle event occurs. Supports input_map to pass entity fields to the intent, write_back to store results on the entity, and an optional when condition for conditional triggering.

### Syntax

```dsl
llm_intent <name> "<Title>":
  ...
  trigger:
    on_entity: <EntityName>
    on_event: <created|updated|deleted>
    [input_map:]
      [<intent_input>: entity.<field>]
    [write_back:]
      [<Entity.field>: output]
    [when: "<condition_expression>"]
```

### Example

```dsl
# Auto-classify tickets on creation
llm_intent classify_ticket "Classify Support Ticket":
  model: claude_haiku
  prompt: "Classify this ticket: {{ input.description }}"
  timeout: 15
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      description: entity.description
    write_back:
      Ticket.category: output
    when: "entity.category == null"
```

### Best Practices

- Use input_map to pass only the fields the LLM needs
- Use write_back to store classification results on the entity
- Use when to avoid re-triggering on already-classified records
- Keep trigger intents fast (low timeout) to avoid blocking entity creation

**Related:** [Llm Intent](llm.md#llm-intent), [Llm Model](llm.md#llm-model), [Entity](entities.md#entity)

---

## Llm Concurrency

Concurrency configuration for LLM models within llm_config. Sets maximum concurrent requests per model to prevent overloading providers. Works alongside rate_limits (requests per minute) to control LLM API usage.

### Syntax

```dsl
llm_config:
  ...
  concurrency:
    <model_name>: <max_concurrent_requests>
    <model_name>: <max_concurrent_requests>

  rate_limits:
    <model_name>: <requests_per_minute>
```

### Example

```dsl
llm_config:
  default_model: claude_sonnet
  artifact_store: local
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_haiku: 100
    claude_sonnet: 60
    gpt4o_mini: 50
  concurrency:
    claude_haiku: 10
    claude_sonnet: 5
    gpt4o_mini: 3
```

### Best Practices

- Set concurrency lower than rate_limits to leave headroom
- Fast-tier models (haiku) can handle higher concurrency
- Quality-tier models should have lower concurrency to manage costs
- Monitor budget_alert_usd to catch runaway LLM usage

**Related:** [Llm Config](llm.md#llm-config), [Llm Model](llm.md#llm-model), [Llm Intent](llm.md#llm-intent)

---
