# LLM Drivers — Subscription vs API, Dev → Deploy

Dazzle reaches Claude models through one of two **drivers**. Which one is
active decides who gets billed and what's required in the environment:

| Driver | Bills | Needs | Use for |
|--------|-------|-------|---------|
| `claude-cli` | Your Claude subscription (via the Claude Code CLI) | `claude` on PATH, signed in once | All development-time cognition. **Never production.** |
| `anthropic-api` | Metered Anthropic API | `ANTHROPIC_API_KEY` | Deployed apps; CI that must mirror production |

What counts as "cognition" here: the `dazzle qa trial` persona agent and
its verdict synthesis, `dazzle analyze` spec analysis, and the runtime
executor behind `llm_intent` blocks when you exercise them locally.

## Configuration

```toml
# dazzle.toml
[llm]
driver = "claude-cli"   # "claude-cli" | "anthropic-api" | "auto"
```

Resolution order (first match wins):

1. CLI flag, e.g. `dazzle qa trial --llm-driver anthropic-api`
2. `DAZZLE_LLM_DRIVER` environment variable
3. `[llm] driver` in dazzle.toml
4. `auto`: `anthropic-api` if `ANTHROPIC_API_KEY` is set, else
   `claude-cli` if the CLI is installed, else an error explaining both
   onboarding paths.

New projects (`dazzle init`) pin `driver = "claude-cli"` so evaluating
Dazzle requires no API credit — a Claude subscription and the Claude Code
CLI are enough.

`dazzle doctor` reports the resolved driver and, when on `claude-cli`,
prints the deploy checklist.

## The dev → deploy path

**1. Develop on the subscription.** With `driver = "claude-cli"`, trials
and local `llm_intent` testing run through `claude -p` on your
subscription. The subprocess deliberately strips `ANTHROPIC_API_KEY` from
its environment so a key exported in your shell can never be silently
billed.

**2. Test API-based cognition locally before deploying.** When your app
uses `llm_intent` and you want to verify the exact production path:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
dazzle qa trial --llm-driver anthropic-api    # or DAZZLE_LLM_DRIVER=anthropic-api
```

This exercises the same `LLMAPIClient` code path production uses —
metered, but on your terms and only for the runs you choose.

**3. Deploy on the API.** A deployed app must not depend on a
developer's personal subscription, and the runtime enforces it: under
`DAZZLE_ENV=production`, any attempt to run cognition through
`claude-cli` (explicitly, or via silent no-key fallback) raises with the
checklist below instead of degrading.

Deploy checklist:

1. Create an API key: <https://console.anthropic.com/settings/keys>
2. Set `ANTHROPIC_API_KEY` in the deployment environment (never in
   dazzle.toml or source control)
3. Set `[llm] driver = "anthropic-api"` — or delete the `[llm]` section,
   since `auto` prefers the key when it's set

## Limitations of `claude-cli`

- **Text protocol only.** The agent loop's native Anthropic tool-use path
  needs the SDK; under `claude-cli` the agent automatically falls back to
  the text protocol (the same one the MCP sampling path uses). Tool
  invocations still work via the robust text parser.
- **Latency.** Each agent step is a fresh CLI invocation (a few seconds
  of startup overhead per step). Fine for trials; wrong for runtime
  request paths — which is one more reason production requires the API.
- **Model IDs** pass through unchanged (`claude --model <id>`), so
  `--model` overrides work identically on both drivers.

## For agents working on this codebase

- Driver resolution and the CLI shell-out live in
  `src/dazzle/llm/driver.py` — the only place `claude -p` is invoked.
- `LLMAPIClient` (`src/dazzle/llm/api_client.py`) carries the no-key →
  CLI fallback and the production guard.
- The agent loop's CLI decide path is `DazzleAgent._decide_via_claude_cli`
  (`src/dazzle/agent/core.py`), dispatch documented in `_decide`.
- When adding a new LLM-calling feature, route it through one of those
  two seams; never construct `anthropic.Anthropic()` directly in feature
  code (the model-defaults policy test and this convention work together).
