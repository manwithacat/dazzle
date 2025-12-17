# Invalid LLM model - unknown provider
module corpus.llm_invalid
app llm_invalid "LLM Invalid"

llm_model bad_model "Bad Model":
  provider: unknown_provider
  model_id: some-model
