# Agent-cognition programme — making the harness worth engaging with

**Status:** active. **Started:** 2026-10-04. **Supersedes nothing**; the
`/improve` efficacy review (`improve-efficacy-review.md`) is the diagnostic that
started it, and [#1758](https://github.com/manwithacat/dazzle/issues/1758) is its
first evidence bundle.

## The goal, stated so it can fail

> Maximise the utility of the repository harness to support agent cognition,
> **such that we can swap in an alternate agent and expect it to engage with the
> provided tools and principles.**

Two clauses, and the second is the hard one:

- **engage with the tools** — an agent that has never seen this repo runs the
  right gate before pushing, discovers the counter-prior that explains the bug it
  is fixing, and finds the decision record that says the thing it is about to
  change was already considered and deferred.
- **engage with the principles** — it does not leave a shim, a singleton, or an
  unclassified baseline entry behind, because it *knows* those are the rules and
  knows which gate will stop it.

"Maximise utility" is measurable only against a swap. So the programme's success
metric is **W8: the orientation benchmark** — an alternate agent, empty context,
one real task, scored on harness engagement. Everything else is instrumentation
toward that.

## What the investigation found (2026-10-04)

Evidence, not impression:

| Observation | Evidence |
|---|---|
| The enforcement substrate is strong | **828** gate tests across **132** `-m gate` modules; 36 `make` targets; `make ci-fast` = preflight + ship-surface + ruff + mypy + gate + docs |
| The epistemic layout is genuinely good | `stems/INDEX.md` is 25 lines and states what a stem *is*; the curriculum (stem → commands → ADR → DD → counter-prior → code) is one line in `AGENTS.md` |
| The orientation surface is heavy and unordered | `AGENTS.md` = 562 lines / 5,413 words / 53 bold rules; harness prose total ≈ 2,085 lines; 17 skill dirs; 12 host command shims |
| **The harness assumes a tool floor it never states** | the Capability Mapping table maps harness *features* (ask-user-choice, task-list, …) across three named hosts — it never names the **binaries** an agent needs (`gh`, `make`, `uv`, `curl`, a browser, `scheduler_create`). `curl` appears **0** times in `AGENTS.md` + `docs/harness/*`, yet `strategies/agent_qa_smoke.md` tells the agent to `curl` a hub endpoint. Running the loop as an agent without `scheduler_create` left Step 6 with no defined path |
| **A mandatory gate was broken and only the loop could have caught it** | `make test-ux-preflight` exited 4 — it named `tests/unit/test_template_none_safety.py`, deleted in #1720. Step 0b says *stop on red*, so cycle 2411 stopped there. Unnoticed for ~30 parked cycles because the loop is the target's only caller (#1758 F1) |
| **The loop's discovery channel works** | two cycles, two clean digs, and 6 + 4 HTTP errors correctly attributed `rbac_expected` rather than seeded as bugs. The classifier does not cry wolf |
| **Cognition is a declared class with no required output** | the capability map defines COGNITION as changing agent *beliefs*; its columns are `Last-exercised | Status`. Nothing in a cycle's output is a revised belief, so nothing fails for not producing one |
| **One rule is enforced by a title heuristic** | a `future`-labelled issue was recommended as claimable work because its *title* contains a bug keyword (#1758 F2) |

## Workstreams

Each is independently shippable, and each records what it changed, what proves
it, and what it cost. W1–W6 are the amendments proposed in #1758; **W7–W9 came
out of investigating the orientation surface** — W7 from mapping principle to
gate, W9 from *using* the harness as documented rather than reading it.

### W1 — Gate the harness's command surface  —  ✅ shipped (`732ea38ef`)

**Change:** `tests/unit/test_harness_command_surface.py` — every file a `make`
recipe names must exist; every `make` target and `scripts/*.py` the driver names
in a fenced block must resolve; the player's own mandatory preflight is invoked
the way the driver invokes it.
**Proves itself:** both directions were falsified (a dangling recipe reference
fails the static check; the original `test-ux-preflight` bug fails the smoke).
**Cost:** one gate module (~150 lines), ~40 s of gate time.

### W2 — `future` beats a title heuristic  —  ✅ shipped (`e668ec866`)

**Change:** in `scripts/improve_github_inbox.py`, `future` (or a `DD-*.md` with
`status: PARKED`) is skip-implement **unconditionally**. Claiming a parked item
requires an explicit label, never a title that happens to contain "error".
**Proves itself:** a test with #1757's exact title and a `future` label must not
appear in `recommended[]`; add `has_dd_status()` so a `FORCED` DD is the only
door.
**Cost:** ~30 lines + a test. **Risk:** low.
**Shipped as:** `is_implementable()` reads the issue's linked DD for
`status: FORCED`, or an explicit `implementable` label. All five `future` issues
now classify as `deferred_future`; one test asserts the title heuristic *still
matches* #1757 and is *not obeyed*, so a future tightening of the regex cannot
quietly re-open the hole.

### W3 — Separate findings from staleness  —  ✅ shipped (`4c9f1a069`)

**Change:** `qa_smoke_bar.py` prints `residual=` (findings: auto_seed, dead
crawl) and `stale=` (stamp age) separately; `improve_policy.py` gains a rule that
a mutation campaign may not be selected on a counter whose *finding* component
has never been non-zero, and `--pick` reports **why** (finding vs re-stamp).
**Proves itself:** with nine stale stamps and zero findings, `--pick` must not
select the bug campaign; with one auto_seed it must.
**Cost:** ~60 lines + tests across the bar, the policy and the example_probes
rollup. **Risk:** medium — three consumers read the current field.

### W4 — Require belief revision from a COGNITION cycle  —  ✅ shipped

**Change:** the capability map's registry gains `Believed` / `Since revised`;
`test_capability_map_beliefs.py` (gate) fails on a `USED` row with an empty
belief, a revision post-dating its run, or a future-dated revision; the driver's
Step 3 requires the line and states that "re-tested, unchanged" is a result.

**Proves itself:** falsified by clearing one belief cell. Filling the seven
existing `USED` rows honestly required **re-testing three of them** rather than
writing from memory — `dazzle fragment-audit examples/simple_task` (71 regions, no
gaps), the CodeQL poll and the inbox poll — which is the point: the gate turns a
timestamp into a claim, and a claim has to be earned.

**Change:** capability-map registry gains `Believed` / `Since revised` columns;
a COGNITION cycle's log entry must state one of `revised:` / `re-tested:` /
`falsified:`; a gate checks the map has no COGNITION row whose `Since revised` is
empty while its owning lane is `USED`.
**Proves itself:** a cycle that stamps a COGNITION row `USED` without a belief
line fails.
**Cost:** a gate plus a log-format rule. **Risk:** medium — it changes what every
future cycle must write, so the wording has to be cheap or it will be skipped.

### W5 — A missing tool is a first-class outcome  —  ✅ shipped (`616324613`)

**Change:** `scripts/improve_toolchain.py` reports every capability with a
remedy and gates on `--require`; Step 0b runs it before lane selection; **27
strategies** that reach for a browser / database / live app / tracker declare the
capability in `tests/unit/fixtures/toolchain_capabilities.json`, and
`test_toolchain_probe.py` fails when a playbook adds a tool dependency without
declaring it. Each gained a `BLOCKED` row naming the probe.
**Proves itself:** the gate found `api_surface_audit`, `distill`,
`dual_lock_expand`, `explore-subagent`, `semgrep_hygiene`,
`hyperpart_presentation`, `trial_signal_action`, `visual_tier2_subagent` and
`domain_lifecycle_priors` reaching for tools they had never declared — nine
unrecorded dependencies, each of which could have selected into a dead end.
**Cost:** one probe, one fixture, one gate, playbook rows.

### W6 — Tool floor + portable chain  —  ✅ shipped (`296fba957`)

**Change:** `docs/harness/tool-floor.md` publishes the floor (which binaries, what
needs them, the remedy, and what to do without each) with `AGENTS.md` pointing at
it; `improve_schedule_next.py --chain-armed 0` records that the host could not arm
the loop's chain, and `make reconcile` reports it as `improve-chain`.

**Why the chain marker is the load-bearing half:** `scheduler_create` is the only
capability whose absence is invisible. Every other missing tool errors when used;
this one produces *silence* — the cycle completes, logs a decision, and no cycle
ever runs. That is what the 30-day park was, and it is why "the loop is broken"
and "the loop has nothing to do" were the same state.

**Proves itself:** four tests — the marker is written on both the armed and
unarmed paths, and `reconcile` is quiet when armed and actionable when not. The
first version omitted the key on the happy path, which the test caught.

### W7 — Principle → gate registry  —  ✅ shipped (`1f54a79b0`)

**Change:** `docs/harness/principle-gates.md`, **rendered** from
`tests/unit/fixtures/principle_gates.json` by
`tests/unit/test_principle_gate_registry.py` — so the human view and the gate
cannot drift. Every doctrine rule in `AGENTS.md` has a row; every gate the
registry names must exist; a row of kind `review` may not cite a gate.
**Result:** **14 of 27** doctrine rules are mechanically enforced; 10 are
review-only, 3 partial, 1 behavioural, 1 a CI check. The gate found two registry
rows citing a non-gate module and one CI check named wrongly — i.e. it caught my
own mistakes while being written.
**Proves itself:** adding a rule to `AGENTS.md` without a row fails.

### W8 — The orientation benchmark (the metric)  —  ⬜ not started

**Change:** a task card built from real repo work (one residue row from
#1748/#1749, or a bug from the burn-down), an **alternate agent** with no other
context, and an observer scoring the five assertions in the table above.
**Proves itself:** two runs on two host/model combinations, both passing.
**Cost:** two agent sessions plus an observer. **Risk:** the finding will be that
some assertion is unscorable — that is the point of writing it down first.

### W9 — the documented surface must work from where the agent stands  —  ✅ shipped (`85ab3acf0`)

Found by *using* the harness as documented rather than reading it. `AGENTS.md`'s
Commands block tells an agent to run `uv run dazzle validate` and `uv run dazzle
lint`; both "operate in CURRENT directory (must contain dazzle.toml)", and the
framework repo root has no `dazzle.toml`. A swapped-in agent's first DSL action
returned `Error: No dazzle.toml found at /Volumes/SSD/Dazzle/dazzle.toml` and it
had to guess a `cd`. Neither `-p` nor `--project` existed on either command,
while `dazzle db` and `dazzle demo quality` already used the convention.

**Change:** both commands take `-p/--project`; the doc uses it; and
`tests/unit/test_documented_commands.py` (gate) parses the Commands block,
requires the `-p` form, and runs both commands from the repo root *and* from
inside a project so the cwd-relative shape other scripts depend on cannot
regress. The `make test-fast` gloss now matches the target.

**The lesson worth more than the fix:** every other harness gate I added this
programme checks that a *reference* resolves. This one runs the *command*. A
reference can be correct while the command still cannot work from the agent's
actual working directory — and no amount of reference-checking finds that.

## Sequencing

Shipped: **W1, W7** (make the harness's own claims checkable) → **W2, W3, W5, W9**
(cheap; each closed a defect the two live cycles demonstrated, and W9 came out of
using the harness rather than reading it) → **W6** (the tool floor, which needed
the chain marker to be observable).

Remaining: **W4**, then **W8**. W8 is the metric, and it should run against a
harness whose claims are checkable, whose parked-work guard holds, whose toolchain
is declared and whose chain state is visible — everything above is instrumentation
toward that one number.

## What this programme will not do

- Not a rewrite of the harness. The refusal vocabulary, the per-cycle audit
  trail, the lane/skill split and the dig classifier are working; two cycles
  produced zero false positives.
- Not a licence for more prose. Every workstream above adds a **gate or a
  counter**, not a page. A workstream that cannot be falsified is not one.
- Not coupled to one host. Any amendment that only works on the host that
  authored it fails W6's bar.
