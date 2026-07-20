# LLM Drivers — Subscription vs API, Dev → Deploy

Dazzle reaches models through **drivers**. Which one is active decides
who gets billed and what's required in the environment:

| Driver | Bills | Needs | Use for |
|--------|-------|-------|---------|
| `claude-cli` | Claude subscription (Claude Code CLI) | `claude` on PATH, signed in once | Dev-time cognition |
| `grok-cli` | Grok subscription (Grok Build CLI) | `grok` on PATH, `grok login` once | Dev-time cognition |
| `anthropic-api` | Metered Anthropic API | `ANTHROPIC_API_KEY` | Deployed apps; CI that mirrors production |
| `auto` | (resolved) | — | Prefer API key if set, else first available subscription CLI |

What counts as "cognition" here: the `dazzle qa trial` persona agent and
its verdict synthesis, `dazzle analyze` spec analysis, and the runtime
executor behind `llm_intent` blocks when you exercise them locally.

Subscription drivers are **development only**. Under
`DAZZLE_ENV=production` the runtime refuses them — a deployed app must
not depend on a developer's personal subscription.

## Configuration

```toml
# dazzle.toml
[llm]
driver = "auto"   # "claude-cli" | "grok-cli" | "anthropic-api" | "auto"
```

Resolution order (first match wins):

1. CLI flag, e.g. `dazzle qa trial --llm-driver grok-cli`
2. `DAZZLE_LLM_DRIVER` environment variable
3. `[llm] driver` in dazzle.toml
4. `auto`:
   - `anthropic-api` if `ANTHROPIC_API_KEY` is set
   - else `claude-cli` if the Claude Code CLI is installed
   - else `grok-cli` if the Grok Build CLI is installed
   - else an error explaining all onboarding paths

New projects (`dazzle init`) pin `driver = "auto"` so evaluating Dazzle
works with whichever subscription CLI you already have.

`dazzle doctor` reports the resolved driver and, for subscription
drivers, prints the deploy checklist.

## The dev → deploy path

**1. Develop on a subscription.** With `claude-cli` or `grok-cli`, trials
and local `llm_intent` testing run through the matching CLI on your
subscription. The subprocess deliberately strips metered API keys
(`ANTHROPIC_API_KEY`, `XAI_API_KEY`, …) so a key in your shell cannot be
silently billed.

```bash
# Prefer Grok when both CLIs are installed:
dazzle qa trial --llm-driver grok-cli
# or
export DAZZLE_LLM_DRIVER=grok-cli
```

**2. Test API-based cognition locally before deploying.** When your app
uses `llm_intent` and you want to verify the exact production path:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
dazzle qa trial --llm-driver anthropic-api
```

**3. Deploy on the API.** Under `DAZZLE_ENV=production`, any subscription
driver (explicit or via auto fallback) raises with the checklist below.

Deploy checklist:

1. Create an API key: <https://console.anthropic.com/settings/keys>
2. Set `ANTHROPIC_API_KEY` in the deployment environment (never in
   dazzle.toml or source control)
3. Set `[llm] driver = "anthropic-api"` — or delete the `[llm]` section,
   since `auto` prefers the key when it's set

## Subscription CLI notes

### `claude-cli`

- Invokes `claude --print --output-format json` (stdin prompt).
- Text protocol only (no native Anthropic tool-use blocks); the agent
  falls back to the text tool parser.
- Default judgment model: Claude Sonnet alias from
  `dazzle.core.model_defaults.DEFAULT_JUDGMENT_MODEL`.

### `grok-cli` (scaffolded)

- Invokes `grok --single` / `--prompt-file` with `--output-format json`
  and `--system-prompt-override`.
- Same text-protocol agent path as `claude-cli`.
- Default judgment model: `grok-4.5`
  (`DEFAULT_GROK_JUDGMENT_MODEL`).
- Long prompts use `--prompt-file` to avoid argv limits.
- Metered keys (`XAI_API_KEY`, `GROK_API_KEY`, `ANTHROPIC_API_KEY`) are
  stripped from the subprocess env so billing stays on the Grok
  subscription.

JSON envelope parsing accepts Claude-shaped `{"result": "..."}` and
common Grok shapes (`response` / `text` / `content` / nested `message`).

## Host-harness vision (also in-subscription)

Separate from these drivers: `dazzle.qa.subscription_vision` and
`scripts/hm_subscription_vision.py` bill judgment to the **host agent**
(Claude Code / Grok Build session) via Read of PNGs — never the metered
HTTP APIs used by `dazzle qa taste-panel`. Prefer that path for day-to-day
taste scoring; see `docs/reference/taste.md`.

## App `llm_intent` providers (runtime tasking)

Separate from the **dev cognition drivers** above (`claude-cli` /
`grok-cli` / `anthropic-api`), each app declares models for
`llm_intent` jobs. Those hit `LLMAPIClient` via `LLMIntentExecutor`
and record governed `AIJob` rows (ADR-0043).

### `provider: anthropic` / `provider: openai`

Standard metered APIs. Keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
(or `api_key_env:` on the model).

### OpenAI-compatible endpoints (`base_url`)

Any server that speaks the OpenAI chat completions API:

```dsl
llm_model local_llama "Local Llama":
  provider: openai          # or: local
  model_id: llama3.2
  base_url: "http://localhost:11434/v1"
  # api_key_env: MY_PROXY_KEY   # optional; dummy key used if unset + base_url
```

Also works with Azure OpenAI resource URLs, LiteLLM proxies, vLLM, etc.
Install: `pip install 'dazzle-dsl[llm]'` (pulls `openai`).

### `provider: google` — Vertex AI / Gemini (GCP)

Uses the **Google Gen AI SDK** (`google-genai`) in Vertex mode with
**Application Default Credentials** — same contract as the Badger
mail-ops Vertex smoke path. Prefer this for production GCP deploys
(IAM, same bill as Cloud Run, PII stays in-org). No third-party API key.

```dsl
llm_model gemini_flash "Gemini Flash (Vertex)":
  provider: google
  model_id: gemini-2.5-flash
  project: my-gcp-project      # or VERTEX_PROJECT / GOOGLE_CLOUD_PROJECT
  location: global            # or VERTEX_LOCATION / GOOGLE_CLOUD_LOCATION
  tier: fast
  max_tokens: 4096
```

Local / Cloud Run enablement:

```bash
gcloud auth application-default login   # local ADC
gcloud services enable aiplatform.googleapis.com --project=my-gcp-project
# Grant roles/aiplatform.user to your user (local) or runtime SA (Cloud Run)

export GOOGLE_CLOUD_PROJECT=my-gcp-project
export GOOGLE_CLOUD_LOCATION=global
# optional pin: VERTEX_MODEL=gemini-2.5-flash
```

Install: `pip install 'dazzle-dsl[llm]'` (pulls `google-genai`).

Optional `GOOGLE_API_KEY` still selects the Gemini **Developer API**
(AI Studio) when no `project` is set — fine for personal experiments,
not the production Vertex path.

Cost on `AIJob` is `NULL` until a model is priced in `costing.py` (or
you set `cost_per_1k_*` on the `llm_model` for display-only rates —
executor still uses the costing module for live usage).

### Example intent

```dsl
llm_intent classify_ticket "Classify Support Ticket":
  model: gemini_flash
  prompt: "Classify into billing|technical|other:\n\n$description"
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      description: entity.description
```

## For agents working on this codebase

- Driver resolution and CLI shell-outs live in
  `src/dazzle/llm/driver.py` — the only place `claude` / `grok` are invoked
  for cognition.
- `call_subscription_cli(driver, …)` dispatches to the concrete CLI.
- `LLMAPIClient` falls back to the first available subscription CLI when
  no API key is set (Anthropic path). Vertex never falls back to CLI.
- App tasking: `LLMIntentExecutor._build_client` maps IR `llm_model` →
  `LLMAPIClient` (including `base_url` / Vertex `project`+`location`).
- When adding a new LLM-calling feature, route it through
  `resolve_llm_driver` + `call_subscription_cli` / `LLMAPIClient`; never
  construct `anthropic.Anthropic()` directly in feature code.
