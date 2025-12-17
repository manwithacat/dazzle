# LLM Jobs as First-Class Events - Parser corpus test
# Tests all LLM constructs: llm_model, llm_config, llm_intent
module corpus.llm_constructs
app llm_test "LLM Test App"

# Minimal model definition
llm_model claude_haiku "Claude Haiku":
  provider: anthropic
  model_id: claude-3-haiku-20240307

# Full model definition
llm_model gpt4o "GPT-4o (Latest)":
  provider: openai
  model_id: gpt-4o
  tier: quality
  max_tokens: 8192

# Model with cost tracking
llm_model claude_sonnet "Claude Sonnet":
  provider: anthropic
  model_id: claude-3-5-sonnet-20241022
  tier: balanced
  max_tokens: 4096

# LLM config block
llm_config:
  default_model: claude_sonnet
  artifact_store: local
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_sonnet: 60
    gpt4o: 30

# Minimal intent definition
llm_intent summarize "Summarize Text":
  prompt: "Summarize the following text: {{ input.text }}"

# Intent with model reference
llm_intent extract_entities "Extract Named Entities":
  model: gpt4o
  prompt: "Extract named entities (people, places, organizations) from: {{ input.text }}"
  timeout: 60

# Full intent with retry and PII policies
llm_intent classify_support_ticket "Classify Support Ticket":
  model: claude_sonnet
  prompt: "Classify the support ticket into: billing, technical, feature_request, other. Ticket: {{ input.ticket_text }}"
  output_schema: TicketClassification
  timeout: 45
  retry:
    max_attempts: 5
    backoff: exponential
    initial_delay_ms: 500
    max_delay_ms: 10000
  pii:
    scan: true
    action: redact
