# Fitness Triage — User Reference

Fitness triage turns a flat `fitness-backlog.md` (thousands of
near-duplicate findings) into a ranked, deduped `fitness-queue.md` that
agents and humans can read top-down. Use it to pick what to work on
next after a fitness run.

## Quick start

```bash
# Regenerate the queue for a single example
cd examples/support_tickets
dazzle fitness triage

# Regenerate for every example under the current directory
dazzle fitness triage --all

# Read the top 10 as JSON (agent-friendly)
dazzle fitness queue --top 10 --json
```

## How it works

1. `dazzle fitness triage` parses `dev_docs/fitness-backlog.md` using
   the existing fitness reader.
2. Each raw finding is mapped to a dedupe key —
   `(locus, axis, canonicalised_summary, persona)` — where
   `canonicalised_summary` is lowercased, whitespace-collapsed, and
   truncated to 120 characters.
3. Findings with the same key collapse into a single **cluster**.
   Each cluster has a stable `cluster_id` of the form `CL-<8 hex>`
   derived from a SHA-256 of the dedupe key.
4. Clusters are sorted by
   `(-severity_rank, -cluster_size, cluster_id)` — highest severity
   first, biggest clusters within a severity band first, alphabetical
   tiebreaker.
5. The result is written atomically to `dev_docs/fitness-queue.md`.

## File layout

```
examples/<app>/dev_docs/
    fitness-backlog.md   # raw findings, written by the fitness engine
    fitness-queue.md     # deduped + ranked view, written by triage
```

The queue file is always a pure projection of the backlog. It's safe
to delete; `dazzle fitness triage` will regenerate it from scratch.

## Commands

```bash
dazzle fitness triage [--project <path>] [--all] [--top N]
    # Regenerate fitness-queue.md. Writes the file; optionally prints
    # the top N clusters to stdout. Exit 1 if the backlog is missing.

dazzle fitness queue [--project <path>] [--top N] [--json]
    # Read-only: prints the existing queue. Exit 1 if the file doesn't
    # exist (run `dazzle fitness triage` first). `--json` for agents.
```

## MCP surface

Agents can query the queue without running the CLI:

```
mcp__dazzle__fitness queue(
    project_root="examples/support_tickets",
    top=10,
)
```

Returns the same JSON shape as `dazzle fitness queue --json`. This is
read-only; to regenerate the queue, agents call
`dazzle fitness triage` (shell-out), not an MCP operation.

## Referencing clusters in commit messages

Cluster IDs are stable across regenerations, so they make good commit
message anchors:

```
fix: resolve CL-a7f3b2c1 story_drift for Administrator

The Administrator persona was hitting "no matching story found" on
the /app/tickets/assign route because the DSL had no story covering
admin-side ticket reassignment. Added the missing story block and
re-ran fitness to confirm.
```

After the fix lands and the next fitness cycle runs, the cluster
either disappears (all members got fixed) or shrinks (partial fix),
and the queue re-ranks naturally.

## What triage deliberately does NOT do

- **Classify** findings as noise vs. real — every distinct cluster
  appears in the queue. Agents decide what to work on.
- **Investigate** individual clusters — reading the underlying
  evidence envelope in `fitness-backlog.md` (via `sample_id`) is
  the agent's job.
- **Track status** — the queue is ephemeral; regenerate after each
  fitness cycle and trust the new numbers. Git log + commit messages
  are the state history.
- **Auto-run after fitness cycles** — triage is a manual CLI call.
  Agents can chain it themselves via `/loop` if they want a fresh
  queue without intervention.

## Design notes

See `docs/superpowers/specs/2026-04-14-fitness-triage-design.md` for
the full design, including the rationale for the dedupe key choice,
the ranking formula, and what's deferred to future investigator and
actor subsystems.
