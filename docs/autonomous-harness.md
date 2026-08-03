# The Dazzle Autonomous Harness

Dazzle ships with a set of agent **slash commands** that, together, form an
autonomous development harness. You point an agent host (Claude Code, Grok
Build, etc.) at the repo, invoke one of these commands (often self-scheduled
or inside a `/loop`), and the agent iterates under a control plane until gates
and residual say stop — or the next one-shot is armed.

This document is the **fleet overview**: what the commands are, how they
compose, and recovery habits. It is **not** the deep package for “how does
`/improve` work as modern harness design?”

| If you want… | Read |
|--------------|------|
| **Human-intelligible structure of `/improve`** (portable exemplar) | [Harness: Improve exemplar](harness/improve-exemplar.md) |
| **Operator status / rearm / force** | [Harness: Operator field guide](harness/operator-field-guide.md) |
| **Strategy one-liners** | [Harness: Strategy catalog](harness/strategy-catalog.md) |
| **Executable cycle for agents** | `.claude/commands/improve.md` |

- **What it is:** slash commands under `.claude/commands/` and skills under
  `.agents/skills/`, host-agnostic in intent, exercised on Dazzle + examples.
- **What it is not:** a general-purpose agent framework. Scoped to Dazzle
  framework + consumer-app development cycles.

### Currency note (read this)

Some sections below retain historical phrasing (early `/loop`-only runs, “commit
but never push”). **Current `/improve` behaviour** includes:

- Safety gates every cycle: **main CI badge**, **CodeQL**, **GitHub inbox**
- **Self-schedule** via `scripts/improve_schedule_next.py` + host one-shots
  (preferred over fixed tickers); daily watchdog
- **Product pushes** when tip CI allows, through push_gate / ship discipline
  (not speculative force-push)
- **Machine residual** (`improve_example_probes.py`) and **policy force**
  (`improve_policy.py`), including post-5.8 Goal B when residual is clear

When this page and the runtime runbook disagree, **`.claude/commands/improve.md`
wins for execution**. Prefer the [exemplar](harness/improve-exemplar.md) for
structure aimed at humans.

---

## 1. Design principles

### 1.1 Convergent loops, not open-ended agents

Every command that can run repeatedly is a **loop with a termination
condition**. `/improve` terminates when the backlog is empty and no new
issues exist. `/issues` terminates when every issue is closed or left with a
triage comment. `/improve`'s `framework-ux` lane terminates when the backlog
has no rows in any actionable state; its `ux-converge` lane terminates when
the contract-failure count hits zero or stops dropping for two cycles.

There is no "run forever and see what happens." Every cycle either advances
a measurable metric or logs a specific reason it didn't and moves on.

### 1.2 Durable state in `dev_docs/` (gitignored)

Long-running commands persist their state in the repo under `dev_docs/`:

| File                              | Owner         | Purpose                                  |
|-----------------------------------|---------------|------------------------------------------|
| `dev_docs/improve-backlog.md`     | `/improve`    | Unified backlog: one `## Lane:` section per lane (framework-ux, example-apps, trials, ux-converge) |
| `dev_docs/improve-log.md`         | `/improve`    | Append-only cycle log across all lanes   |
| `.dazzle/improve.lock`            | `/improve`    | PID + timestamp; 15-min TTL              |
| `.dazzle/improve-explore-count`   | `/improve`    | Shared explore budget (cap 100)          |
| `.dazzle/signals/`                | `ux_cycle_signals` | Cross-lane signal bus (JSON files)  |
| `dev_docs/fitness-queue.md`       | `dazzle fitness triage` | Clustered coverage findings    |
| `agent/smells-report.md`          | `/smells`     | Code-smell analysis snapshot             |

`dev_docs/` is gitignored — this is deliberate. State is local to the
developer's machine; commits that result from a cycle are what the rest of
the team sees. This keeps loop state from polluting git history while still
giving the loop a durable place to plan and record.

### 1.3 Cycle shape: OBSERVE → ENHANCE → BUILD → VERIFY → REPORT

Every productive command follows the same five-phase cycle:

```
OBSERVE → ENHANCE → BUILD → VERIFY → REPORT
    ↑                         │
    │  ┌── green ─────────────┤
    │  │                      │
    │  │    red (≤3): fix → retry from BUILD
    │  │    red (>3) → DIAGNOSE → file issue → next gap
    └──┘──────────────────────┘
```

- **OBSERVE**: read state (backlog, lint, validate, MCP tools).
- **ENHANCE**: propose the change.
- **BUILD**: apply it (edit files, run generators).
- **VERIFY**: re-run the check that originally flagged the gap.
- **REPORT**: update the backlog, append to the log, commit if green.

The retry policy is bounded (≤3 attempts per gap). On the fourth failure
the gap is marked BLOCKED, typically with an upstream GitHub issue filed,
and the loop moves on. This is the most important rule in the harness —
without it, a single stubborn gap would swallow an entire run.

### 1.4 Commit every green cycle, never push speculatively

Productive cycles commit. They do **not** push. A `/loop` run of
`/improve` that fixes 10 gaps produces 10 local commits; the human reviews
`git log -10` once and decides whether to push. `/issues` and `/ship`
are the only commands that push, and `/ship` does additional gates
(ruff/mypy) before doing so.

The result: long autonomous runs accumulate small, coherent commits with
descriptive messages. A human reviewing a full loop's output sees a ready
history, not a junk drawer.

### 1.5 Parallel subagents for breadth, sequential main thread for depth

Commands that fan out (issues triage, cross-project scans, smell analysis,
quality checks) dispatch **parallel subagents** in a single message. The
top-level agent synthesises their reports. This pattern is used by
`/check`, `/smells`, `/xproject`, and by `/issues` when there are 2+
open issues.

Subagents run `model: "sonnet"` (when judgment is needed) or
`model: "haiku"` (for mechanical checks). The main thread stays on the
session's current model.

### 1.6 Self-observation: the loop tracks its own activity

`/improve` logs every cycle including no-op cycles; its `framework-ux` lane
logs selected row, attempts, verdict, and notes. `/issues` logs triage decisions
and closed issues. After a multi-hour run, the log reads like a bench
technician's journal — "attempted X, failed, attempted Y, succeeded,
moved to Z" — and gives the human reviewer a compact story of what the
loop did and why.

### 1.7 External signals promote pushed work

Several commands (especially `/improve`) check for new
GitHub issues at the end of each cycle. A `needs-triage` label from one of
the consumer teams (CyFuture, AegisMark, Penny Dreadful) causes the loop
to **interrupt its backlog** and switch to `/issues` mode. This is how
downstream apps "talk" to the harness: they file an issue with the right
label, and the next loop cycle picks it up.

---

## 2. The commands

### 2.1 Productive loops

Commands that advance state and may commit.

#### `/improve [lane] [strategy]`
**Source:** `.claude/commands/improve.md`
**Human map:** [Harness exemplar](harness/improve-exemplar.md) · [Operator guide](harness/operator-field-guide.md) · [Strategy catalog](harness/strategy-catalog.md)

Single agent-first entrypoint for autonomous investigation, improvement,
refactoring, and remediation. Consolidated former `/ux-cycle`, `/trial-cycle`,
and `/ux-converge` skills into one driver (2026-04).

**Cycle shape (current):** lock → local preflight → **CI badge** (repair if
red) → **CodeQL** (remediate if high/error) → **GitHub inbox** → signals →
policy/probes → pick lane → playbook → log → release lock → **self-schedule**
next one-shot.

Lanes (`.claude/commands/improve/lanes/*.md`):

| Lane | Targets | Cycle action |
|------|---------|--------------|
| `framework-ux` | Dazzle UI templates, contracts, fitness walks | Contract / edge / presentation / open-discovery ships |
| `example-apps` | Example app product/demo/journey residual + Goal B depth | Probe force → dig → prove (stills/receipts) → ship |
| `trials` | Qualitative persona scenarios via `dazzle qa trial` | Rotate (app, scenario) → trial → triage findings |
| `ux-converge` | Example apps with nonzero contract failures | RUN→CLASSIFY→FIX→RE-RUN (bounded) |
| `test-suite` | Test redundancy / collapse tracks | Cluster-driven reduction |
| `hm-convergence` | HM ownership, dual-lock, hyperpart coherence | Investigate / drain queues |

The driver respects `$ARGUMENTS` to force a lane and strategy. Cross-lane
signals (`ux-component-shipped`, `trial-friction`, `app-fixed`, …) bias picks.
Explore budget is global (cap 100). Cadence panels: **self-audit** (~15 cycles),
**capability-sweep** (~20 cycles); optional Grok workflows for parallel fan-out.

**Self-scheduling (preferred):** Step 6 — `scripts/improve_schedule_next.py` →
host `scheduler_create` with opportunistic CI-aware intervals (poll while tip
CI in progress; settle after deploy; hot on bugs/red; inbox re-probe when
quiet). Daily durable watchdog: `scripts/improve_watchdog_prompt.md`.
Session-bound alternative: `/loop 15–30m /improve`. Read-only: `/improve --status`.

**GitHub inbox (Step 0c3):** `scripts/improve_github_inbox.py`. Consumer and
owner/pilot bugs are first-class (`consumer_issues`). Dependabot green checks
may auto-merge (`github_prs`). Quiet product still re-arms ~15–30m so inbox is
not left multi-hour cold.

#### `/issues`
**Source:** `.claude/commands/issues.md`

Iterative GitHub-issue resolver. Triage → parallel-investigate → pick →
implement → test → commit → push → close → repeat. Author-routed:

- Issues from `manwithacat` (project owner): full cycle — implement,
  ship, close.
- Issues from anyone else: analysis comment only; do not implement or
  close.

When 2+ open owner-issues exist, it dispatches one sonnet subagent per
issue in parallel to produce structured investigation reports, then picks
the best next issue based on priority × complexity × momentum.

### 2.2 One-shot commands

Commands that execute once and stop.

#### `/check`
**Source:** `.agents/skills/check/SKILL.md`

Quality gate. Looks at `git diff --name-only HEAD`, then dispatches
parallel haiku subagents: lint+format, mypy (core + backend), unit
tests, DSL validation, parser corpus, MCP verification — only the ones
relevant to what changed. Read-only: never commits or pushes.

#### `/bump [level]`
**Source:** `.agents/skills/bump/SKILL.md`

Semantic-version bumper. Updates `pyproject.toml`, `AGENTS.md`,
`ROADMAP.md`, `src/dazzle/mcp/semantics_kb/core.toml`, and
`homebrew/dazzle.rb` in lock-step. Moves CHANGELOG's `[Unreleased]`
entries under a new `[X.Y.Z]` heading. Does not commit or tag — that
is `/ship`'s job.

#### `/ship`
**Source:** `.agents/skills/ship/SKILL.md`

Commit + push gate. Runs ruff/format, runs mypy, then stages named files
(never `git add -A`), writes a HEREDOC commit message, tags if
`pyproject.toml`'s version changed, and pushes. Refuses to force-push.
This is the only way productive local commits reach origin.

#### `/cimonitor`
**Source:** `.agents/skills/cimonitor/SKILL.md`

CI-badge watchdog. Reports whether the main-branch `CI` workflow is
green or red, shows the job-level breakdown, fetches logs for failed
jobs, and categorises each failure as type error / lint / test /
security / flaky. Explicitly requires fixing pre-existing CI failures
too, not just those caused by the current branch.

#### `/smells`
**Source:** `.agents/skills/smells/SKILL.md`

Read-only code-smell analysis. Four parallel sonnet subagents covering
regression checks, error-handling/coupling patterns, duplication/type
safety, and complexity/mutable globals. Writes the report to
`agent/smells-report.md` and appends a summary to
`agent/smells-log.md`.

Does not fix anything. A separate `/improve` or `/issues` cycle acts
on the findings.

#### `/xproject [name]`
**Source:** `.claude/commands/xproject.md`

Cross-project quality scan across every sibling app in
`/Volumes/SSD/*/dazzle.toml`. One sonnet subagent per project runs
`dazzle validate`, `dazzle lint`, plus the `sentinel`, `pulse`, and
`discovery` MCP tools. Synthesises a cross-project report that flags
shared patterns (which usually indicate framework issues in Dazzle
itself).

#### `/docs-update [since]`
**Source:** `.agents/skills/docs-update/SKILL.md`

Scans recently-closed GitHub issues and proposes surgical edits to
CHANGELOG, README, and MkDocs pages. Dry-runs by default; asks for
confirmation before writing.

### 2.3 Command dependency graph

```
              /improve ───┬──▶ /issues (when backlog clean and issues exist)
                          │
              /issues ────┼──▶ /ship (after each fix)
              /bump ──────┼──▶ /ship (after version bump)
                          │
              /docs-update ┘
              /smells   ──▶ writes findings; human or /issues acts
              /xproject ──▶ writes findings; /improve or /issues acts
              /check    ──▶ read-only; informs /ship
              /cimonitor──▶ triggers a /issues cycle if CI is red
```

The productive loop (`/improve`) delegates to `/issues`
when its backlog is clean. `/issues` and `/bump` delegate to
`/ship` to actually publish work. `/check`, `/cimonitor`, `/smells`,
and `/xproject` are read-only feeds that inform what the productive
loops do next.

---

## 3. How `/loop` amplifies the harness

Claude Code's built-in `/loop` skill wraps any other slash command in
either a fixed-interval cron (`/loop 15m /improve`) or a self-paced
cadence (`/loop /improve`, where Claude picks its own delay between
runs based on what changed).

This is what promotes single-cycle commands into autonomous runs:

- `/loop 15m /improve` — every 15 minutes, fix the next gap. Walks
  away for hours; comes back to a tree with N ready-to-review commits.
- `/loop 30m /improve framework-ux` — medium cadence for slow UX verification.
- `/loop /issues` — self-paced issue triage. Claude picks its own
  delay; speeds up when there's active work, slows down when there
  isn't.

The loop scheduler respects the 5-minute prompt-cache TTL: delays are
either comfortably inside it (60–270s, for active polling) or
comfortably outside it (1200s+, for idle heartbeat). The cache math is
worth understanding if you care about cost — see the `/loop` skill's
own description for the breakdown.

`/loop` runs can be cancelled at any time via `CronDelete` in Claude
Code, or by exiting the session. Session-only cron jobs auto-expire
after seven days.

---

## 4. Recovery, safety, and ship discipline

The harness is deliberately paranoid about a few things:

- **Safety gates before ambition.** Red main CI and high CodeQL outrank
  product digs for that cycle. Tip CI **in_progress** blocks new product
  pushes (poll / hold; repair path uses explicit repair flags).

- **Small coherent commits; gated push.** `/improve` product cycles commit
  and may push through `push_gate` / ship-surface when tip allows — not
  speculative force-push. `/issues` and `/ship` remain first-class publish
  paths. A broken local run is still reviewable via `git log` + cycle log.

- **Worktree discipline.** Prefer named staging (not casual `git add -A`).
  Secrets stay out of commits. Pre-commit failures → fix + new commit, not
  amend-to-bypass.

- **Close-the-loop.** Recurrent CI failure classes get promoted into
  local ship-surface / preflight so the next dig fails before push.

- **Versioning is traceable** when `/bump` is used for release trails;
  not every improve dig bumps the public version.

---

## 5. State-file conventions

Every productive loop keeps two files: a **backlog** (PENDING /
IN_PROGRESS / DONE / BLOCKED rows) and an **append-only log**
(one entry per cycle).

The backlog is the loop's scheduling queue. Rows move PENDING →
IN_PROGRESS → (DONE | BLOCKED) and never back. `attempts` is tracked
per row and drives the ≤3-retry rule.

The log is evidence. Each entry names the cycle number, the app or
component, the gap, the action, and the verdict. A human reviewer can
reconstruct what the loop did just by reading the log.

When a loop interrupts itself (e.g. `/improve` sees a new
needs-triage issue), it notes the interrupt in the log, switches mode,
resumes after.

---

## 6. What to watch for when running the harness

Three failure modes to watch for:

**Silent drift.** If the loop keeps reporting "no-op, backlog clean"
but the app quality clearly hasn't improved to the target, the
discovery rules probably aren't catching the class of gap you care
about. Add a new check to `/improve` (a new gap type) or file it as an
issue that `/improve` can pick up.

**Thrashing.** If the same gap shows up repeatedly as PENDING after
being marked DONE, the verification step is too weak. Tighten the
VERIFY check so it catches the regression immediately, or add a
dev_docs baseline file to track the pre-fix state.

**Runaway attempts.** If a gap racks up 3 attempts and lands in
BLOCKED, check whether the bot's fix idea is structurally right but
the validation is wrong, or whether the validation is right but the
fix can't express what's needed. Either way it's a human signal, not
a "try harder" problem.

---

## 7. Practical invocation recipes

Prefer **self-schedule** (Step 6 of `/improve`) over stacking fixed tickers.
For day-one:

```
# one cycle (agent host)
/improve

# review log / backlog
$EDITOR dev_docs/improve-log.md
# probes
uv run python scripts/improve_example_probes.py --status

# rearm if the chain died — see docs/harness/operator-field-guide.md
```

Session-bound alternative (Claude Code `/loop`):

```
/loop 15m /improve
/loop 30m /improve framework-ux
```

Operator rearm, budget reset, force table: [Operator field guide](harness/operator-field-guide.md).

---

## 8. Extending the harness

The commands are all Markdown files in `.claude/commands/`. Adding a
new command is three steps:

1. Create `.claude/commands/<name>.md` with a clear phase structure
   (OBSERVE → ENHANCE → BUILD → VERIFY → REPORT, or a read-only
   variant).
2. Define the termination condition. Write it before anything else.
3. If the command persists state, put it in `dev_docs/<name>-*.md` and
   add the file to `.gitignore` (if not already covered).

Write the termination condition **first**. Every command in this
harness started from "here is exactly when you stop running." Without
it, you have an agent, not a harness.
