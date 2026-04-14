# Fitness Investigator

Agent-led investigation of ranked fitness clusters. Reads a cluster from
`fitness-queue.md`, gathers context via read-only tools, and writes a
structured `Proposal` to disk for a later actor subsystem to apply.

## What it does

Given a cluster like:

    CL-a1b2c3d4  form-field  coverage:high  persona=admin  size=17

the investigator:

1. Loads the sample finding + up to 5 diverse siblings from
   `dev_docs/fitness-backlog.md`.
2. Extracts a candidate file path from the sample's evidence transcript
   (heuristically — looks for strings matching `path.ext:line` or `line N`).
3. Loads the locus file (full content if ≤ 500 lines, windowed otherwise
   with the first 200 lines + ±20 line windows around evidence-referenced
   line numbers).
4. Hands the case file to an LLM agent with 6 tools: `read_file`,
   `query_dsl`, `get_cluster_findings`, `get_related_clusters`,
   `search_spec`, and the terminal `propose_fix`.
5. The agent investigates (≤ 25 steps), then calls `propose_fix` with
   a concrete diff, rationale, verification plan, and alternatives.
6. A `Proposal` file lands at
   `.dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md`.

## CLI

    dazzle fitness investigate                     # investigate top 1
    dazzle fitness investigate --top 5             # top 5
    dazzle fitness investigate --cluster CL-...    # target one cluster
    dazzle fitness investigate --dry-run           # print case file, no LLM call
    dazzle fitness investigate --force             # re-investigate even if proposal exists
    dazzle fitness investigate --model claude-opus-4-6

**Exit codes:**
- `0`: at least one proposal written, or dry-run completed.
- `1`: nothing to do (queue empty or all clusters already investigated).
- `2`: invalid arguments (`--cluster` not in queue, `--top 0`).
- `3`: infrastructure failure (LLM client crash, disk write denied).

## Reading a proposal file

Proposals are markdown with YAML frontmatter. The frontmatter is the
machine-readable contract for the actor; the body is for humans.

Key fields:

- `proposal_id` — UUID4 hex, stable per investigation run.
- `cluster_id` — back-reference to the queue cluster (e.g., `CL-a1b2c3d4`).
- `overall_confidence` — investigator's self-assessment, 0.0..1.0. The
  actor will use this to decide between auto-apply and flag-for-review.
- `fixes` — list of per-file diffs with per-fix rationales and confidence.
- `verification_plan` — what the actor should run after applying.
- `alternatives_considered` — short list of rejected approaches with reasons.
- `evidence_paths` — files the investigator actually read during the run.
- `tool_calls_summary` — one line per tool call, in order.
- `status` — `proposed` | `applied` | `verified` | `reverted` | `rejected`.

The markdown body contains the case file the investigator saw, the
investigation log it wrote, and the proposed diff in a fenced code block.

## Debugging blocked investigations

When the investigator cannot produce a proposal, it writes a blocked
artefact to `.dazzle/fitness-proposals/_blocked/<cluster_id>.md`. The
blocked file contains the case file and a transcript excerpt describing
why the run stopped:

- `blocked_step_cap`: 25 LLM steps without a terminal `propose_fix` call.
- `blocked_stagnation`: 4 consecutive steps with no tool call.
- `blocked_invalid_proposal`: `propose_fix` was called but the proposal
  violated a validation rule (short rationale, bad diff, cluster_id
  mismatch, etc.). The raw LLM args are embedded for prompt-tuning.
- `blocked_write_error`: disk write failure.

## Idempotence

`dazzle fitness investigate` skips clusters that already have a proposal
on disk. The `_attempted.json` file is a rebuildable cache — if it's
deleted or corrupt, the next run reconstructs it by scanning the
proposal files.

Use `--force` to re-investigate.

## Metrics

Every investigation attempt appends one line to
`.dazzle/fitness-proposals/_metrics.jsonl`:

    {"cluster_id":"CL-a1b2c3d4","status":"proposed","tokens_in":0,"tokens_out":0,"tool_calls":6,"duration_ms":12400,"created":"2026-04-14T10:15:23Z","model":"claude-sonnet-4-6"}

Use standard JSONL tools (`jq`) to analyse trends.

Note: `tokens_in` and `tokens_out` are 0 in v1 because DazzleAgent's
token-usage tracking isn't wired through to the runner yet. Future
iterations will populate these fields.

## Known v1 limitations

**DazzleAgent ↔ propose_fix JSON payload gap.** DazzleAgent uses a
text-based action protocol that struggles to reliably produce the
complex JSON payload required by `propose_fix` (fixes list with diffs,
alternatives list, etc.). In practice the investigator often hits the
4-step stagnation guard and writes a `blocked_stagnation` artefact
rather than a usable proposal. The integration smoke test at
`tests/integration/fitness/test_investigator_real.py` treats stagnation
as a valid smoke-test outcome for this reason. A follow-up will
introduce a structured tool-call interface (Anthropic SDK tools) to
resolve this at the DazzleAgent layer.

**No proposal quality measurement yet.** The runner appends metrics
but does not grade proposal correctness. Future work will add a
spot-check workflow that samples proposals for human review and
tracks the accept/reject ratio per model.

## Design

See `docs/superpowers/specs/2026-04-14-fitness-investigator-design.md`
for the full design spec and
`docs/superpowers/plans/2026-04-14-fitness-investigator-plan.md`
for the implementation plan.
