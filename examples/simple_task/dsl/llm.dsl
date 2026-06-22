# LLM Integration for Team Task Manager
# Demonstrates DAZZLE LLM capabilities
#
# LLM features enable:
# - AI-powered task classification
# - Priority assessment
# - Smart suggestions

module simple_task.llm

# =============================================================================
# LLM Configuration
# =============================================================================

llm_config:
  default_model: claude_haiku
  fallback_mode: mock
  artifact_store: local
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_haiku: 100
    claude_sonnet: 60

# =============================================================================
# LLM Models
# =============================================================================

llm_model claude_haiku "Claude Haiku (Fast)":
  provider: anthropic
  model_id: claude-3-haiku-20240307
  tier: fast
  max_tokens: 1024
  description: "Fast model for simple classifications"

llm_model claude_sonnet "Claude Sonnet (Balanced)":
  provider: anthropic
  model_id: claude-3-5-sonnet-20241022
  tier: balanced
  max_tokens: 4096
  description: "Balanced model for complex analysis"

# =============================================================================
# LLM Intents
# =============================================================================

llm_intent classify_task_priority "Auto-classify Task Priority":
  description: "Analyze task title and description to suggest priority level"
  model: claude_haiku
  prompt: "Analyze task '$title' with description '$description' and classify its priority as low, medium, high, or urgent. Respond with JSON containing priority, reasoning, and confidence."
  timeout: 15
  retry:
    max_attempts: 2
    backoff: exponential
  trigger:
    on_entity: Task
    on_event: created
    input_map:
      title: entity.title
      description: entity.description
  pii:
    scan: true
    action: redact

llm_intent suggest_task_tags "Suggest Tags for Task":
  description: "Analyze task to suggest relevant tags/labels"
  model: claude_haiku
  prompt: "Suggest relevant tags for task '$title' with description '$description'. Available tags: backend, frontend, api, database, ui, testing, documentation, infrastructure, security, performance. Respond with JSON containing tags array and reasoning."
  timeout: 10
  trigger:
    on_entity: Task
    on_event: created
    input_map:
      title: entity.title
      description: entity.description
  pii:
    scan: true
    action: redact

llm_intent summarize_task_comments "Summarize Task Discussion":
  description: "Summarize the comment thread on a task"
  model: claude_sonnet
  prompt: "Summarize the discussion on task '$task_title' based on the provided comments. Provide a brief summary of key decisions, outstanding questions, and next steps."
  timeout: 30
  retry:
    max_attempts: 2
    backoff: linear
  trigger:
    on_entity: Task
    on_event: created
    input_map:
      task_title: entity.title
  pii:
    scan: true
    action: redact

llm_intent estimate_task_effort "Estimate Task Effort":
  description: "Estimate effort required for a task"
  model: claude_sonnet
  prompt: "Estimate effort for task '$title' with description '$description' and priority '$priority'. Respond with JSON containing effort_hours, complexity, risks, dependencies, and confidence."
  timeout: 20
  trigger:
    on_entity: Task
    on_event: created
    input_map:
      title: entity.title
      description: entity.description
      priority: entity.priority
  pii:
    scan: true
    action: warn
