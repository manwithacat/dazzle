# DazzleAgent Robust Parser and Optional Tool Use — Design

**Status:** Draft for review
**Date:** 2026-04-14
**Scope:** `src/dazzle/agent/`, `src/dazzle/fitness/investigator/`
**Related:** cycle 147 (EXPLORE stagnation), cycle 156 (runbook fix), cycle 188 (sweep complete), fitness investigator v1 spec

---

## 1. Goal

Make `DazzleAgent` reliable enough that an autonomous cycle can run for hours under a Claude Code host without stagnating on protocol bugs. Specifically:

- **Bug 5a (prose-before-JSON parse failure)** — fix on all paths via a robust text parser that extracts the first balanced JSON object from any response and preserves surrounding prose as reasoning.
- **Bug 5b (nested-JSON-in-tool-values)** — fix on the direct Anthropic SDK path via opt-in support for Anthropic's native tool use API, where the investigator's `propose_fix` (and any future tool with a nested input schema) can emit structured arguments without the stringified-JSON-in-string encoding that the text protocol requires.

The deliverable is infrastructure plus one mission migration (investigator's `propose_fix` to structured tool use). All other missions remain on the text protocol, now with the robust parser, and keep working unchanged.

---

## 2. Design philosophy

Three principles, lifted from the brainstorm, that shape every decision below:

**Continuity over speed.** A strong cognitive exercise that runs autonomously for multiple hours is a better outcome than a highly-parallelised workflow that is brittle and needs babysitting. We choose single-action-per-step over multi-tool-call-per-step even though the latter could batch parallel reads.

**Reasoning preservation over presentation.** The raw LLM reasoning — prose preambles, scratch notes, interrupted thoughts — is part of the reward/feedback signal for downstream evaluation tasks. It is not expected to be immediately human-readable. The parser's job is to extract the structured action and pipe everything else into the `reasoning` field verbatim. No cleanup pass, no formatting logic. A future "justify this step" task can derive human explanations from the raw reasoning when needed.

**Economics shape the default path.** Running DazzleAgent under a Claude Code host via MCP sampling is near-zero marginal cost (subsidised by subscription). Running it via direct Anthropic SDK is metered and non-trivial at scale. The MCP sampling path is first-class for autonomous cycles. The direct SDK path is the fallback for environments without a host (CI, cloud runners, production agents with API keys) and the only path where Anthropic's native tool use API is available.

---

## 3. Background

### 3.1 The valley

Cycles 156–188 advanced 33 widget contracts from FAIL to DONE by fixing a single runbook rule (`qa:PASS` if `degraded is False`, not if `findings_count == 0`). That sweep revealed two underlying DazzleAgent protocol bugs that had been blocking autonomous operation:

- **Bug 5a:** Claude 4.6 emits prose preambles before JSON action blocks (`"I'll start by exploring the ticket form. {\"action\": \"navigate\", ...}"`). The current `_parse_action` calls `json.loads(response_text)` which fails on any non-JSON prefix. On failure, it returns `AgentAction(type=DONE, success=False)`. The outer loop treats DONE as terminal. Result: the mission stagnates at step 1. Cycle 147's EXPLORE run captured this empirically (8 steps, 0 findings).

- **Bug 5b:** The investigator's `propose_fix` terminal action requires a nested payload: `cluster_id`, `root_cause`, and a `changes` array of objects. The text protocol encodes tool invocations as `{"action": "tool", "target": "propose_fix", "value": "{\"cluster_id\": \"...\", \"changes\": [...]}"}` — a JSON string containing a JSON string. Claude 4.6 gets this escaping wrong often enough that cycle 147's investigator run couldn't reliably complete its terminal action. The investigator shipped as read-only in v0.54.5 with this documented as a known v1 limitation.

### 3.2 Two bugs, one protocol

Bug 5a is a parser bug: the text protocol is fine, the parser is brittle. Fix: make the parser tolerant of prose-before-JSON.

Bug 5b is a protocol-level limit: even a perfect parser can't make nested JSON encoding reliable, because the model itself has to emit a correctly-escaped string containing a JSON object. The only fix is to switch protocols for the specific tools where it matters, from text to Anthropic's native tool use API.

These two bugs share the same symptom (agent stagnates) but have different root causes and different fixes. This design addresses both.

### 3.3 Economic framing

Token costs by execution path:

| Path | Entry point | Token cost | Structured output support |
|---|---|---|---|
| Claude Code host via MCP sampling | `mcp_session.create_message(...)` | Near-zero marginal (subsidised) | Text only — `TextContent` |
| Direct Anthropic SDK | `client.messages.create(api_key=...)` | Metered per-token | Full tool use (native `tool_use`/`tool_result` blocks) |

Today, four of five DazzleAgent call sites use the direct SDK path with an API key (journey testing, e2e testing, fitness strategy, investigator). Only one call site uses MCP sampling (`mcp/server/handlers/discovery/missions.py`). Cycle 147's EXPLORE stagnation ran on the metered path — burning API tokens to fail.

For autonomous operation at scale, the MCP sampling path should become first-class. Dropping it to force all missions onto native tool use would be economically wrong. The right shape is: make the MCP-sampling-text-path reliable (parser fix, works on both paths), and add tool use as an opt-in optimisation on the SDK path for the specific tools that need it (investigator's `propose_fix`).

A longer-term direction (deferred to a separate brainstorm) is to route more missions through MCP sampling, bringing autonomous operation fully inside the subsidised boundary. A related forward-looking idea is to restructure the investigator as a Claude Code subagent (spawned via the Task tool) that uses the host's native tools (Read/Grep/Bash/Write) to investigate and emit proposals, trading tool-use schema enforcement for economic elimination. Both are out of scope for this project but noted in Section 11.

---

## 4. Architecture

`DazzleAgent` remains a single class with a single `run()` loop. The `observe → decide → execute → record` shape is unchanged. The changes are additive and localised to:

1. **`_parse_action`** — becomes robust via three-tier fallback (plain `json.loads` → bracket-counting extraction → diagnostic DONE sentinel).
2. **`AgentTool`** — gains an optional `input_schema: dict | None = None` field.
3. **`DazzleAgent.__init__`** — gains an optional `use_tool_calls: bool = False` kwarg.
4. **`_decide`** — gains a three-way branch (MCP sampling + text / SDK + text / SDK + tool use).
5. **`_decide_via_anthropic_tools`** — new method, ~40 lines, handles the tool-use code path.
6. **`_build_system_prompt`** — gains one paragraph of prompt hardening on the text path demanding JSON-only output.

**What does not change:**

- The `observe → decide → execute → record` loop
- `AgentAction` / `PageState` / `Step` / `AgentTranscript` dataclasses
- `Mission.completion_criteria`
- Non-investigator missions (journey testing, UX quality, discovery, contract walks, EXPLORE)
- The MCP sampling code path (`_decide_via_sampling`) — internals unchanged
- The text-protocol action schema (click / type / select / navigate / scroll / wait / assert / done + tool)
- Transcript HTML report format

**Files touched:**

- `src/dazzle/agent/core.py` — parser, tool-use path, prompt hardening, `_decide` branch
- `src/dazzle/agent/models.py` — `AgentTool.input_schema`
- `src/dazzle/fitness/investigator/tools.py` — `propose_fix` schema definition
- `src/dazzle/fitness/investigator/runner.py` — flip `use_tool_calls=True`
- `tests/unit/agent/test_parse_action.py` — new
- `tests/unit/agent/test_extract_json.py` — new
- `tests/unit/agent/test_tool_use.py` — new
- `tests/integration/agent/test_investigator_propose_fix.py` — new
- `tests/unit/agent/test_regression.py` — new (cycle 147 pattern)

**Architecture explicitly rejects:**

- A separate `StructuredAgent` class (would double class surface for no gain).
- A plugin architecture for LLM protocols (two paths is the total forever).
- An abstract `LLMProtocol` interface (same reasoning — two concrete paths don't need an abstraction).
- Schema auto-generation from Python type hints (convenience feature, additive, not needed for v1).

---

## 5. Components

### 5.1 `AgentTool` (models.py)

```python
@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]
    input_schema: dict[str, Any] | None = None  # NEW
```

Semantics:

- `input_schema is None` (default) → legacy text-protocol tool. No behaviour change. All existing tools compile and run unchanged.
- `input_schema is not None` → structured tool. Contains an Anthropic-format JSON Schema (`{"type": "object", "properties": {...}, "required": [...]}`). Enables tool-use path when `DazzleAgent.use_tool_calls=True`.

No validation of the schema dict at registration time — Anthropic's API validates at the `messages.create(tools=[...])` boundary. Malformed schemas surface as API errors on the first `_decide` call.

### 5.2 `_parse_action` (core.py)

Three-tier fallback contract:

```python
def _parse_action(self, response: str, tool_registry: dict[str, AgentTool]) -> AgentAction:
    # Tier 1: json.loads(response) — fast path for well-behaved output
    # Tier 2: bracket-counting extraction, preserve surrounding text as reasoning
    # Tier 3: no balanced JSON found — return DONE sentinel with full response as reasoning
```

A new helper function handles the bracket counting:

```python
def _extract_first_json_object(text: str) -> tuple[str | None, str]:
    """Find the first balanced JSON object in a string.

    Returns (json_substring, surrounding_text) where surrounding_text is
    everything in `text` minus the extracted JSON substring. If no balanced
    object is found, returns (None, text).

    Handles nested braces, string literals (braces inside strings are counted
    as characters, not brackets), escape sequences (\\", \\\\), and markdown
    code fences (```json ... ```).
    """
```

**Reasoning preservation rule:**

| Tier | Reasoning field population |
|---|---|
| 1 success | `data.get("reasoning", "")` — current behaviour |
| 2 success | `data.get("reasoning", "") + " [PROSE]: " + surrounding_text` |
| 3 failure | `"Failed to extract action. Full response: " + response[:2000]` |

The raw prose goes into the reasoning field untouched. No cleanup, no summarisation, no formatting.

**Logging levels:**

- Tier 1 success: silent
- Tier 2 success: DEBUG (expected path for prose-preamble outputs)
- Tier 3 failure: WARNING with truncated response
- Unknown action type / unknown tool name: INFO

### 5.3 `DazzleAgent.__init__` + `_decide`

```python
def __init__(
    self,
    observer,
    executor,
    model: str = "claude-opus-4-6",
    api_key: str | None = None,
    mcp_session: Any = None,
    use_tool_calls: bool = False,  # NEW
):
    ...
    self._use_tool_calls = use_tool_calls
    self._tool_use_warned = False  # one-shot warning latch for path γ
```

`_decide` gains a three-way branch (see Section 6 for full data flow):

```python
if self._mcp_session is not None:
    # Path γ: MCP sampling + text protocol
    if self._use_tool_calls and not self._tool_use_warned:
        logger.warning("use_tool_calls=True on MCP sampling path — falling back to text")
        self._tool_use_warned = True
    response_text, tokens = await self._decide_via_sampling(...)
    action = self._parse_action(response_text, tool_registry)
elif self._use_tool_calls:
    # Path β: SDK + tool use
    action, tokens = self._decide_via_anthropic_tools(...)
    response_text = action.reasoning
else:
    # Path α: SDK + text protocol
    response_text, tokens = self._decide_via_anthropic(...)
    action = self._parse_action(response_text, tool_registry)
```

### 5.4 `_decide_via_anthropic_tools` (new)

```python
def _decide_via_anthropic_tools(
    self,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tool_registry: dict[str, AgentTool],
) -> tuple[AgentAction, int]:
    """Request a completion via Anthropic SDK with native tool use."""
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tool_registry.values()
        if tool.input_schema is not None
    ]

    client = self._get_client()
    response = client.messages.create(
        model=self._model,
        max_tokens=2000,
        system=system_prompt,
        messages=messages,
        tools=tools,
    )

    tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

    text_blocks: list[str] = []
    tool_use_block: Any = None
    for block in response.content:
        if block.type == "text":
            text_blocks.append(block.text)
        elif block.type == "tool_use" and tool_use_block is None:
            tool_use_block = block

    reasoning = "\n".join(text_blocks).strip()

    if tool_use_block is None:
        return AgentAction(
            type=ActionType.DONE,
            success=False,
            reasoning=reasoning or "Model emitted no tool_use block",
        ), tokens

    return AgentAction(
        type=ActionType.TOOL,
        target=tool_use_block.name,
        value=json.dumps(tool_use_block.input),  # serialise back for _execute_tool compat
        reasoning=reasoning,
    ), tokens
```

Key contracts:

- Only tools with `input_schema is not None` appear in `tools=[...]`. Legacy text-protocol tools in the same registry are invisible on this path.
- `tool_use.input` is already a dict (Anthropic's SDK parses against the schema). We serialise it with `json.dumps` before storing in `AgentAction.value` to preserve backwards compatibility with `_execute_tool`, which calls `json.loads` on tool invocation values.
- Multiple `tool_use` blocks in one response → take the first, ignore the rest, log at INFO.

### 5.5 Prompt hardening (`_build_system_prompt`)

On the text path only, append a paragraph to the system prompt:

> Your response must be valid JSON and nothing else. Do not prefix your JSON with prose, reasoning, or explanation. Any text outside the JSON object will be discarded.

This is preventive maintenance — it reduces the rate at which the parser has to catch prose-before-JSON. The parser remains the safety net.

On the tool-use path, the system prompt structure is different (Anthropic's SDK handles the tool description format), so the hardening paragraph is not appended there.

---

## 6. Data flow

Three paths, traced through `_decide`:

### 6.1 Path α — SDK + text protocol

**Used by:** journey testing, UX quality, discovery (SDK mode), EXPLORE, contract walks, investigator when `use_tool_calls=False` (including tests), any future mission without structured outputs.

1. `_decide(mission, state, tool_registry)` builds `system_prompt` and `messages`.
2. `self._mcp_session is None` and `self._use_tool_calls is False` → `_decide_via_anthropic`.
3. `client.messages.create(model, max_tokens=800, system, messages, tools=[])` — **no tools parameter**.
4. Response is `content[0].text`. Possibly prose+JSON, possibly JSON, possibly fenced.
5. `_parse_action` tries tier 1 → tier 2 → tier 3, returns an `AgentAction`.
6. `run()` executes the action and records a Step.

**Fixes Bug 5a.** Does not fix Bug 5b.

### 6.2 Path β — SDK + tool use

**Used by:** investigator with `use_tool_calls=True`. Only call site after migration.

1. `_decide(...)` as above.
2. `self._mcp_session is None` and `self._use_tool_calls is True` → `_decide_via_anthropic_tools`.
3. Builds `tools=[...]` from registry entries with `input_schema`.
4. `client.messages.create(model, max_tokens=2000, system, messages, tools=tools)`.
5. Response `content` is a list of `TextBlock` and/or `ToolUseBlock` instances.
6. Collect text blocks into `reasoning`. Take first `ToolUseBlock` as action.
7. If no `ToolUseBlock` → `AgentAction(DONE, success=False)` with text as reasoning.
8. If `ToolUseBlock` present → `AgentAction(TOOL, target=block.name, value=json.dumps(block.input), reasoning=...)`.
9. `run()` sees `TOOL` action, calls `_execute_tool` → `json.loads(value)` → `handler(**args)`. Unchanged.

**Fixes Bug 5b.** Bug 5a is irrelevant here (no free-form JSON to parse).

### 6.3 Path γ — MCP sampling + text protocol

**Used by:** `mcp/server/handlers/discovery/missions.py` — the only MCP sampling call site.

1. `_decide(...)` as above.
2. `self._mcp_session is not None` → MCP sampling branch.
3. If `use_tool_calls=True`, log one-shot warning. Set latch.
4. `_decide_via_sampling` via `mcp.types.SamplingMessage` — unchanged.
5. Response is text. `_parse_action` handles it with the same three-tier fallback as path α.

**Fixes Bug 5a on the cheap path.** Does not fix Bug 5b (investigator is not wired to this path).

### 6.4 Cross-path invariants

1. Every path produces a valid `AgentAction`. Never `None`, never a raised exception from `_decide`. Failures convert to DONE sentinels.
2. Reasoning is always populated. Worst-case failure still carries raw response or a diagnostic.
3. Tool execution is protocol-agnostic. `_execute_tool(tool, action.value)` works identically whether the action came from α, β, or γ, because `action.value` is always a JSON string.
4. `AgentTool.input_schema` is only consulted on path β. Ignored on α and γ.
5. The `use_tool_calls` flag is a request, not a guarantee. Path β delivers it. Path γ logs a warning and falls back. Mission authors design tools so the text protocol can also handle them (less reliably).

---

## 7. Error handling

### 7.1 Text path parse failures

| Failure mode | Outcome |
|---|---|
| Valid JSON, valid action | `AgentAction(type=..., reasoning=data['reasoning'])` |
| Prose preamble + balanced JSON | Tier 2 extraction, reasoning = `data['reasoning'] + " [PROSE]: " + surrounding_text` |
| Trailing prose + balanced JSON | Tier 2 extraction, same |
| Markdown code fence + balanced JSON | Tier 2 extraction (bracket counter finds object inside fence) |
| Garbage, no balanced JSON | Tier 3: `AgentAction(DONE, success=False, reasoning="Failed to extract action. Full response: ...")` |
| Valid JSON, unknown action type | `AgentAction(DONE, success=False, reasoning="Unknown action: " + action_str)` |
| Valid JSON, `action == "tool"`, target not in registry | `AgentAction(DONE, success=False, reasoning="Unknown tool: " + target)` |

### 7.2 Tool-use path failures

| Failure mode | Outcome |
|---|---|
| Text blocks + first tool_use block, valid | Happy path |
| Text blocks only, no tool_use | `AgentAction(DONE, success=False, reasoning=text)` — model is done/stuck |
| tool_use block with unknown tool name | Shouldn't happen (Anthropic validates). If it does: `AgentAction(DONE, success=False, reasoning="Unknown tool: ...")`. |
| tool_use block with wrong input shape | Anthropic validates against schema. If it slips through, `_execute_tool` raises TypeError → caught → ActionResult with error → mission continues. |
| Multiple tool_use blocks | Take first, log rest at INFO |
| Empty content list | `AgentAction(DONE, success=False, reasoning="Model emitted no tool_use block")` |

### 7.3 Tool handler exceptions (unchanged)

Existing behaviour in `_execute_tool` — exceptions are caught into `ActionResult(error=...)` and the step is recorded. The mission continues. No change.

### 7.4 Network / API errors (out of scope)

`client.messages.create()` raising `APIConnectionError`, `APIStatusError`, 429, 500 — propagates out of `_decide`, crashes `run()`. Unchanged. Retry / backoff / rate-limit handling is a separate concern and a separate project.

### 7.5 Schema validation (trust Anthropic)

We do not validate `AgentTool.input_schema` dicts ourselves. Anthropic validates at the `messages.create(tools=[...])` call boundary. Malformed schemas surface as API errors on the first `_decide` call. Developer experience: caught in CI by the integration test that wires up investigator with its real schema.

### 7.6 One-shot warning latch

`_tool_use_warned` fires the MCP-sampling-with-tool-use warning once per agent instance, not once per decide call. Avoids flooding the transcript.

### 7.7 Reasoning preservation under failure

Even in the worst case, the failing `AgentAction` carries a populated `reasoning` field with raw diagnostic or response text. Downstream analysis always has something to work with. No model output is discarded on error.

---

## 8. Testing

### 8.1 Parser unit tests (`tests/unit/agent/test_parse_action.py`)

14 tests covering tiers 1, 2, and 3:

- Tier 1: 3 tests (plain JSON click, tool, done)
- Tier 2: 7 tests (prose before, prose after, prose around, markdown fence, nested object value, string containing braces, escaped quote)
- Tier 3: 4 tests (garbage, unbalanced JSON, invalid action type, unknown tool name)

### 8.2 Bracket counter unit tests (`tests/unit/agent/test_extract_json.py`)

9 tests covering `_extract_first_json_object` in isolation:

- Simple object, prose before, prose after, nested, brace-in-string, escaped-quote, multiple-objects-takes-first, no object, unbalanced.

### 8.3 Tool-use path unit tests (`tests/unit/agent/test_tool_use.py`)

8 tests covering `_decide_via_anthropic_tools` with a mocked Anthropic client:

- Text + tool_use block, multiple text blocks concatenated, only text no tool_use, empty content, multiple tool_use blocks takes first, builds tools from schema (asserts only schema-bearing tools appear), input serialised to string, warning on MCP session (latch verified).

### 8.4 Integration test (`tests/integration/agent/test_investigator_propose_fix.py`)

One end-to-end test that proves Bug 5b is fixed for the motivating case. Constructs a `DazzleAgent(use_tool_calls=True)` with a mocked Anthropic client that returns a canned tool_use response with the exact nested `changes` array that `propose_fix` expects. Asserts:

- `action.type == ActionType.TOOL`
- `action.target == "propose_fix"`
- `json.loads(action.value)` recovers the full nested structure
- `action.reasoning` contains the text block content

### 8.5 Cycle 147 regression test (`tests/unit/agent/test_regression.py`)

One test using the exact prose+JSON pattern captured from cycle 147's stagnation logs. Asserts the agent extracts the action cleanly and preserves both the stated `reasoning` and the prose preamble in the final reasoning field. Gets a comment pointing back to cycle 147 so future maintainers know why the specific pattern matters.

### 8.6 Out of scope for this project's tests

- Live Anthropic API calls (all mocked)
- Live MCP sampling (mocked)
- Performance / latency
- End-to-end investigator run against a real example app (separate project)
- Multi-turn tool_result flows, dynamic tool registration, schema auto-generation

### 8.7 Test count summary

| File | Tests |
|---|---|
| `test_parse_action.py` | 14 |
| `test_extract_json.py` | 9 |
| `test_tool_use.py` | 8 |
| `test_investigator_propose_fix.py` | 1 |
| `test_regression.py` | 1 |
| **Total** | **33** |

All tests fast (<50ms), deterministic, no network, no API key required.

---

## 9. Migration

### 9.1 Investigator `propose_fix`

1. Add an `input_schema` to the existing `propose_fix` tool definition in `src/dazzle/fitness/investigator/tools.py` (or wherever the tool is currently registered — `tools_write.py` based on file layout).
2. Schema shape:

```python
PROPOSE_FIX_SCHEMA = {
    "type": "object",
    "required": ["cluster_id", "root_cause", "changes"],
    "properties": {
        "cluster_id": {"type": "string", "description": "The fitness cluster ID being investigated"},
        "root_cause": {"type": "string", "description": "Concise root cause explanation"},
        "changes": {
            "type": "array",
            "description": "Concrete file-level changes to apply",
            "items": {
                "type": "object",
                "required": ["file", "action"],
                "properties": {
                    "file": {"type": "string"},
                    "action": {"enum": ["add", "modify", "delete"]},
                    "line_range": {"type": "string"},
                    "snippet": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "alternative_fixes": {"type": "array", "items": {"type": "string"}},
    },
}
```

Exact shape to be verified against the current `Proposal` dataclass during implementation — this spec captures the intent, the plan verifies the fields.

3. Flip `use_tool_calls=True` in `src/dazzle/fitness/investigator/runner.py` at the `DazzleAgent(...)` construction site.

### 9.2 Everything else

No migration. All other missions (journey, e2e, UX quality, discovery, EXPLORE, contract walks, free_roam, ux_quality) keep their current `DazzleAgent(...)` construction with `use_tool_calls=False` (default). They benefit from the parser fix (Bug 5a) automatically.

---

## 10. Out of scope

- **Multi-tool-call per step.** Parallel read tools. Deferred — the continuity-over-speed principle says no for now.
- **Schema auto-generation from Python type hints.** Convenience helper. Deferred.
- **MCP sampling everywhere.** Pushing more missions through MCP sampling to reduce token cost. This is the "option C" from brainstorming and deserves its own brainstorm.
- **Investigator as Claude Code subagent.** Forward-looking alternative to option C — restructure investigator to spawn as a Task subagent using native Read/Grep/Bash/Write tools instead of Anthropic tool use. Trades schema enforcement for economic elimination.
- **Network / API error retry and backoff.** Separate project.
- **Performance and latency measurement.** Not currently a concern.
- **End-to-end investigator run against a live example app.** Valuable but part of the broader "we don't exercise investigator in CI" problem, not specific to this project.
- **Pass 2a / contract-walk finding separation in StrategyOutcome.** The other item from cycle 188's action items. Separate brainstorm.
- **Per-app persona auto-derivation from DSL permits.** Separate brainstorm.
- **Initiative ceiling / strategic pause mechanism for the ux-cycle skill.** Fuzzier. Separate brainstorm.

---

## 11. Open questions for future projects

These were raised during brainstorming and are worth capturing for future work, but are not decisions this spec needs to make.

### 11.1 Should autonomous cycles route DazzleAgent calls through MCP sampling when available?

Today most call sites hardcode `api_key=...` on DazzleAgent construction. To make MCP sampling first-class for autonomous operation, these call sites would need to accept an optional `mcp_session` parameter and pass it through. The change is mechanical but crosses many files (fitness strategy, investigator runner, journey testing, agent_e2e, etc.), and each call site has its own subprocess / session lifecycle assumptions. Worth a dedicated brainstorm.

### 11.2 Could investigator be a Claude Code subagent instead of an SDK-API-key process?

Claude Code subagents (spawned via the Task tool) run inside the subscription boundary. An investigator restructured as a subagent would use native Read/Grep/Bash/Write tools, emit its proposal via `Write`, and be coordinated by a thin runner that spawns the subagent with the case file as input. Trade-off: loses Anthropic tool use schema enforcement, gains full economic elimination of token costs. Different tactic from 11.1 — rather than routing DazzleAgent through a host, it replaces DazzleAgent entirely for the investigator's use case. Worth its own brainstorm.

### 11.3 Should the text-protocol tools gain input_schema for documentation even though they're not used on the text path?

Adding schemas to legacy tools would improve documentation and enable future migration to tool use. But it also creates a split where the schema exists but isn't enforced on the text path, which might be more confusing than no schema at all. Decision deferred pending operational experience with the opt-in design.

### 11.4 How should `AgentAction.value` be typed going forward?

Currently `str | None` because `_execute_tool` does `json.loads(value)`. With tool use producing structured dicts, a cleaner long-term shape would be `dict | str | None`. But that cascades into transcript serialisation, `AgentAction` dataclass definition, and `_execute_tool` type handling. Worth a separate refactor once we have more missions using structured outputs.

---

## 12. Success criteria

This project is done when:

1. All 33 new tests pass, locally and in CI.
2. `_parse_action` handles the exact cycle 147 prose-before-JSON pattern and extracts the action cleanly.
3. The investigator can emit `propose_fix` with a nested `changes` array via Anthropic tool use and the proposal lands in `.dazzle/fitness-proposals/` (validated by the integration test with mocks).
4. All existing tests still pass (no regressions in journey testing, UX quality, discovery, fitness strategy, contract walks).
5. `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp` and `mypy src/dazzle_back/` clean.
6. `ruff check src/ tests/` and `ruff format src/ tests/` clean.
7. The cycle 188 action item list is updated to mark Bug 5a and Bug 5b as resolved, with a note pointing to this spec.

Non-goals (explicitly not success criteria):

- Any live Anthropic API call succeeding in CI.
- Any live investigator run against a real example app.
- Any measurable performance improvement.
- Any change to the text-protocol missions' behaviour beyond the parser becoming robust.

---

## 13. Estimated shape of implementation

Not a plan — that's the next skill. But for rough sizing:

- Parser rewrite + bracket counter helper: ~100 LOC in `core.py`
- `AgentTool.input_schema` field: 1 LOC in `models.py`
- `_decide` branch: ~15 LOC in `core.py`
- `_decide_via_anthropic_tools` new method: ~50 LOC in `core.py`
- Prompt hardening: ~5 LOC in `_build_system_prompt`
- Investigator `propose_fix` schema: ~30 LOC in `tools_write.py`
- Investigator runner flag flip: 1 LOC in `runner.py`
- Tests: ~500 LOC across 5 new test files
- **Total new/changed: ~700 LOC**

One TDD pass, probably 15–25 tasks depending on granularity.

---
