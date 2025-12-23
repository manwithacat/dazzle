# Parser Reference: LLM Models, Config, and Intents
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# LLM_MODEL:
# - [x] llm_model name "Title":
# - [x] llm_model name: (no title)
# - [x] provider: anthropic
# - [x] provider: openai
# - [x] provider: google
# - [x] provider: local
# - [x] model_id: identifier
# - [x] model_id: hyphenated (e.g., claude-3-5-sonnet-20241022)
# - [x] model_id: "string"
# - [x] tier: fast
# - [x] tier: balanced
# - [x] tier: quality
# - [x] max_tokens: number
# - [x] cost_per_1k_input: decimal
# - [x] cost_per_1k_output: decimal
#
# LLM_CONFIG:
# - [x] llm_config:
# - [x] default_model: model_name
# - [x] artifact_store: local
# - [x] artifact_store: s3
# - [x] artifact_store: gcs
# - [x] logging: block
# - [x] log_prompts: true/false
# - [x] log_completions: true/false
# - [x] redact_pii: true/false
# - [x] rate_limits: block
# - [x] rate_limits: model_name: number
#
# LLM_INTENT:
# - [x] llm_intent name "Title":
# - [x] llm_intent name: (no title)
# - [x] model: model_name
# - [x] prompt: "template string"
# - [x] prompt: with {{ input.field }} placeholders
# - [x] output_schema: EntityName
# - [x] timeout: seconds
# - [x] retry: block
# - [x] retry: max_attempts
# - [x] retry: backoff: linear
# - [x] retry: backoff: exponential
# - [x] retry: initial_delay_ms
# - [x] retry: max_delay_ms
# - [x] pii: block
# - [x] pii: scan: true/false
# - [x] pii: action: warn
# - [x] pii: action: redact
# - [x] pii: action: reject
# - [x] pii: patterns: list
#
# =============================================================================

module pra.llm

use pra
use pra.entities

# =============================================================================
# LLM_MODEL: ANTHROPIC PROVIDER
# =============================================================================

llm_model claude_haiku "Claude Haiku":
  provider: anthropic
  model_id: claude-3-haiku-20240307
  tier: fast
  max_tokens: 4096
  cost_per_1k_input: 0.00025
  cost_per_1k_output: 0.00125

llm_model claude_sonnet "Claude Sonnet":
  provider: anthropic
  model_id: claude-3-5-sonnet-20241022
  tier: balanced
  max_tokens: 8192
  cost_per_1k_input: 0.003
  cost_per_1k_output: 0.015

llm_model claude_opus "Claude Opus":
  provider: anthropic
  model_id: claude-3-opus-20240229
  tier: quality
  max_tokens: 4096
  cost_per_1k_input: 0.015
  cost_per_1k_output: 0.075

# =============================================================================
# LLM_MODEL: OPENAI PROVIDER
# =============================================================================

llm_model gpt4o "GPT-4o":
  provider: openai
  model_id: gpt-4o-2024-08-06
  tier: balanced
  max_tokens: 16384
  cost_per_1k_input: 0.005
  cost_per_1k_output: 0.015

llm_model gpt4o_mini "GPT-4o Mini":
  provider: openai
  model_id: gpt-4o-mini
  tier: fast
  max_tokens: 16384
  cost_per_1k_input: 0.00015
  cost_per_1k_output: 0.0006

llm_model gpt4_turbo "GPT-4 Turbo":
  provider: openai
  model_id: gpt-4-turbo-2024-04-09
  tier: quality
  max_tokens: 128000
  cost_per_1k_input: 0.01
  cost_per_1k_output: 0.03

# =============================================================================
# LLM_MODEL: GOOGLE PROVIDER
# =============================================================================

llm_model gemini_flash "Gemini Flash":
  provider: google
  model_id: gemini-1.5-flash
  tier: fast
  max_tokens: 8192
  cost_per_1k_input: 0.0001
  cost_per_1k_output: 0.0004

llm_model gemini_pro "Gemini Pro":
  provider: google
  model_id: gemini-1.5-pro
  tier: balanced
  max_tokens: 32768
  cost_per_1k_input: 0.00125
  cost_per_1k_output: 0.005

# =============================================================================
# LLM_MODEL: LOCAL PROVIDER
# =============================================================================

llm_model local_llama "Local Llama":
  provider: local
  model_id: llama3-8b
  tier: fast
  max_tokens: 4096

llm_model local_mixtral "Local Mixtral":
  provider: local
  model_id: mixtral-8x7b
  tier: balanced
  max_tokens: 32768

# =============================================================================
# LLM_MODEL: WITHOUT TITLE
# =============================================================================

llm_model claude_basic:
  provider: anthropic
  model_id: claude-3-haiku-20240307
  tier: fast
  max_tokens: 2048

# =============================================================================
# LLM_MODEL: WITH STRING MODEL_ID
# =============================================================================

llm_model custom_model "Custom Model":
  provider: openai
  model_id: "ft:gpt-4o-mini:my-org:custom-suffix:id"
  tier: balanced
  max_tokens: 4096

# =============================================================================
# LLM_CONFIG: BASIC
# =============================================================================

llm_config:
  default_model: claude_sonnet
  artifact_store: local

# =============================================================================
# LLM_CONFIG: WITH LOGGING
# =============================================================================

llm_config:
  default_model: claude_haiku
  artifact_store: local
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true

# =============================================================================
# LLM_CONFIG: WITH S3 STORE
# =============================================================================

llm_config:
  default_model: gpt4o
  artifact_store: s3
  logging:
    log_prompts: true
    log_completions: false
    redact_pii: true

# =============================================================================
# LLM_CONFIG: WITH GCS STORE
# =============================================================================

llm_config:
  default_model: gemini_pro
  artifact_store: gcs
  logging:
    log_prompts: false
    log_completions: true
    redact_pii: false

# =============================================================================
# LLM_CONFIG: WITH RATE LIMITS
# =============================================================================

llm_config:
  default_model: claude_sonnet
  artifact_store: local
  rate_limits:
    claude_haiku: 100
    claude_sonnet: 60
    claude_opus: 20
    gpt4o: 50
    gpt4o_mini: 100

# =============================================================================
# LLM_CONFIG: COMPLETE
# =============================================================================

llm_config:
  default_model: claude_sonnet
  artifact_store: s3
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true
  rate_limits:
    claude_haiku: 200
    claude_sonnet: 100
    claude_opus: 30
    gpt4o: 80
    gemini_flash: 200
    gemini_pro: 60

# =============================================================================
# LLM_INTENT: BASIC
# =============================================================================

llm_intent summarize_text "Summarize Text":
  model: claude_haiku
  prompt: "Summarize the following text concisely:\n\n{{ input.text }}"
  timeout: 30

# =============================================================================
# LLM_INTENT: WITHOUT TITLE
# =============================================================================

llm_intent translate:
  model: claude_haiku
  prompt: "Translate the following text to {{ input.target_language }}:\n\n{{ input.text }}"
  timeout: 45

# =============================================================================
# LLM_INTENT: WITH OUTPUT SCHEMA
# =============================================================================

llm_intent extract_entities "Extract Entities":
  model: claude_sonnet
  prompt: "Extract all named entities from the following text:\n\n{{ input.text }}\n\nReturn a structured list of entities with their types."
  output_schema: ExtractedEntity
  timeout: 60

llm_intent classify_priority "Classify Task Priority":
  model: claude_haiku
  prompt: "Analyze this task and classify its priority:\n\nTitle: {{ input.title }}\nDescription: {{ input.description }}\n\nReturn the priority level (low, medium, high, urgent) with reasoning."
  output_schema: PriorityClassification
  timeout: 20

# =============================================================================
# LLM_INTENT: WITH RETRY (LINEAR)
# =============================================================================

llm_intent analyze_sentiment "Analyze Sentiment":
  model: claude_haiku
  prompt: "Analyze the sentiment of the following text:\n\n{{ input.text }}\n\nReturn: positive, negative, or neutral with confidence score."
  output_schema: SentimentResult
  timeout: 30
  retry:
    max_attempts: 3
    backoff: linear
    initial_delay_ms: 1000
    max_delay_ms: 10000

# =============================================================================
# LLM_INTENT: WITH RETRY (EXPONENTIAL)
# =============================================================================

llm_intent generate_code "Generate Code":
  model: claude_sonnet
  prompt: "Generate {{ input.language }} code that accomplishes the following:\n\n{{ input.specification }}\n\nProvide clean, well-commented code."
  timeout: 120
  retry:
    max_attempts: 5
    backoff: exponential
    initial_delay_ms: 500
    max_delay_ms: 30000

# =============================================================================
# LLM_INTENT: WITH PII WARN
# =============================================================================

llm_intent customer_insight "Customer Insight":
  model: claude_sonnet
  prompt: "Analyze the following customer data and provide insights:\n\n{{ input.customer_data }}"
  timeout: 60
  pii:
    scan: true
    action: warn

# =============================================================================
# LLM_INTENT: WITH PII REDACT
# =============================================================================

llm_intent support_ticket_summary "Summarize Support Ticket":
  model: claude_haiku
  prompt: "Summarize this support ticket:\n\nSubject: {{ input.subject }}\nBody: {{ input.body }}\nCustomer: {{ input.customer_name }}"
  output_schema: TicketSummary
  timeout: 45
  pii:
    scan: true
    action: redact

# =============================================================================
# LLM_INTENT: WITH PII REJECT
# =============================================================================

llm_intent analyze_document "Analyze Document":
  model: claude_opus
  prompt: "Analyze the following document and extract key information:\n\n{{ input.document_text }}"
  output_schema: DocumentAnalysis
  timeout: 180
  pii:
    scan: true
    action: reject
    patterns: "SSN", "credit_card", "password"

# =============================================================================
# LLM_INTENT: COMPLETE WITH ALL OPTIONS
# =============================================================================

llm_intent full_analysis "Full Text Analysis":
  model: claude_sonnet
  prompt: "Perform a comprehensive analysis of the following text:\n\nTitle: {{ input.title }}\nContent: {{ input.content }}\nContext: {{ input.context }}\n\nProvide:\n1. Summary\n2. Key themes\n3. Sentiment\n4. Entity extraction\n5. Recommendations"
  output_schema: ComprehensiveAnalysis
  timeout: 180
  retry:
    max_attempts: 3
    backoff: exponential
    initial_delay_ms: 2000
    max_delay_ms: 60000
  pii:
    scan: true
    action: redact
    patterns: "email", "phone", "address"

# =============================================================================
# LLM_INTENT: COMPLEX PROMPT TEMPLATE
# =============================================================================

llm_intent generate_report "Generate Report":
  model: claude_opus
  prompt: "Generate a {{ input.report_type }} report based on the following data:\n\n{% for item in input.data_items %}\n- {{ item.name }}: {{ item.value }}\n{% endfor %}\n\nReport period: {{ input.start_date }} to {{ input.end_date }}\nFormat: {{ input.output_format }}"
  output_schema: GeneratedReport
  timeout: 300
  retry:
    max_attempts: 2
    backoff: linear

# =============================================================================
# LLM_INTENT: CHAT COMPLETION
# =============================================================================

llm_intent chat_response "Chat Response":
  model: gpt4o
  prompt: "You are a helpful assistant. Continue this conversation:\n\n{{ input.conversation_history }}\n\nUser: {{ input.user_message }}\n\nAssistant:"
  timeout: 60
  retry:
    max_attempts: 3
    backoff: exponential
    initial_delay_ms: 1000
    max_delay_ms: 15000

# =============================================================================
# LLM_INTENT: USING DIFFERENT PROVIDERS
# =============================================================================

llm_intent fast_classification "Fast Classification":
  model: gpt4o_mini
  prompt: "Classify the following text into one of these categories: {{ input.categories }}\n\nText: {{ input.text }}"
  timeout: 15

llm_intent quality_reasoning "Quality Reasoning":
  model: claude_opus
  prompt: "Provide detailed reasoning and analysis for the following question:\n\n{{ input.question }}\n\nConsider multiple perspectives and provide a thorough answer."
  timeout: 240
  retry:
    max_attempts: 2
    backoff: exponential

llm_intent local_embedding "Local Embedding":
  model: local_llama
  prompt: "Generate a summary embedding for:\n\n{{ input.text }}"
  timeout: 30

# =============================================================================
# LLM_INTENT: CODE REVIEW
# =============================================================================

llm_intent code_review "Code Review":
  model: claude_sonnet
  prompt: "Review the following {{ input.language }} code for:\n1. Bugs and errors\n2. Security issues\n3. Performance improvements\n4. Best practices\n\nCode:\n```{{ input.language }}\n{{ input.code }}\n```"
  output_schema: CodeReviewResult
  timeout: 120
  retry:
    max_attempts: 3
    backoff: exponential
    initial_delay_ms: 2000
    max_delay_ms: 30000
  pii:
    scan: true
    action: warn

# =============================================================================
# OUTPUT SCHEMA ENTITIES (for reference)
# =============================================================================

entity ExtractedEntity "Extracted Entity":
  intent: "Entity extracted from text analysis"
  domain: nlp

  id: uuid pk
  entity_type: str(100) required
  entity_value: str(500) required
  confidence: decimal(3,2)=0.00
  start_position: int
  end_position: int

entity PriorityClassification "Priority Classification":
  intent: "Task priority classification result"
  domain: nlp

  id: uuid pk
  priority: enum[low,medium,high,urgent]=medium
  confidence: decimal(3,2)=0.00
  reasoning: text

entity SentimentResult "Sentiment Result":
  intent: "Sentiment analysis result"
  domain: nlp

  id: uuid pk
  sentiment: enum[positive,negative,neutral]=neutral
  confidence: decimal(3,2)=0.00
  scores: json

entity TicketSummary "Ticket Summary":
  intent: "Support ticket summary"
  domain: support

  id: uuid pk
  summary: text required
  key_issues: json
  suggested_category: str(100)
  urgency_level: enum[low,medium,high,critical]=medium

entity DocumentAnalysis "Document Analysis":
  intent: "Comprehensive document analysis"
  domain: nlp

  id: uuid pk
  summary: text required
  key_points: json
  entities: json
  metadata: json

entity ComprehensiveAnalysis "Comprehensive Analysis":
  intent: "Full text analysis result"
  domain: nlp

  id: uuid pk
  summary: text required
  themes: json
  sentiment: str(50)
  entities: json
  recommendations: json

entity GeneratedReport "Generated Report":
  intent: "Generated report output"
  domain: reporting

  id: uuid pk
  title: str(200) required
  content: text required
  charts: json
  tables: json

entity CodeReviewResult "Code Review Result":
  intent: "Code review findings"
  domain: development

  id: uuid pk
  overall_score: int
  bugs: json
  security_issues: json
  performance_issues: json
  best_practice_violations: json
  suggestions: json
