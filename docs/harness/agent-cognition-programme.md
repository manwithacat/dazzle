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

Each is independently shippable. W1–W6 are the amendments proposed in #1758;
W7–W8 come out of the orientation investigation.

### W1 — Gate the harness's command surface, not just its prose
`tests/unit/test_improve_harness_paths.py` checks paths named in **playbooks**.
Nothing checks the `make` targets and scripts the driver *invokes*
(`make preflight-surface`, `make test-ux-preflight`, `improve_policy.py`,
`improve_example_probes.py`, `qa_smoke_bar.py`, `improve_github_inbox.py`,
`improve_schedule_next.py`, `improve_compact.py`, `push_gate.py`). Those are the
names that resolve to nothing when a file moves — the failure cycle 2411 hit.
*Done when:* every command the driver's Steps 0b–0e name exists, is executable,
and answers `--help` without error.

### W2 — `future` beats a title heuristic
In `improve_github_inbox.py`, a `future` label (or a `DD-*.md` with
`status: PARKED`) must be **unconditionally** skip-implement; if a parked item is
ever to be claimable, that requires an explicit label, not a sentence containing
"error".
*Done when:* no `future` issue can appear in `recommended[]` without an explicit
override, and a test asserts it for a title that matches every bug keyword.

### W3 — Separate "there is work" from "we have not looked"
`qa_smoke_bar.py` prints `residual=N` for both *findings* and *stale measurement
stamps*; in cycle 2411 all 9 were the staleness kind, and the counter selected
the campaign named for gross bugs. Split the field (`residual=` / `stale=`), and
add a policy rule: a mutation campaign may not be selected on a counter whose
finding-type component has never been non-zero.
*Done when:* the bar distinguishes the two, and `--pick` can report *why* it
picked (finding vs re-stamp).

### W4 — Require belief revision from a COGNITION cycle
Add `Believed` / `Since revised` to the capability map's registry table, and make
a COGNITION PASS state either the belief it revised or the measurement that
falsified the prior one. "Re-tested, unchanged" is a legitimate outcome; "nothing
to say" must not be.
*Done when:* a COGNITION cycle with an empty belief line fails the gate.

### W5 — A missing tool is a first-class outcome
The forced smoke dig needs playwright, which lives in the `e2e` extra and is not
installed by `make dev-install`; no playbook has a BLOCKED row for it. Add the
row (with the remedy), and have Step 0b verify the *forced* campaign's toolchain
before selection.
*Done when:* a strategy whose toolchain is missing reports BLOCKED with the
remedy rather than an unexplained non-zero exit.

### W6 — A stated tool floor, and a portable chain
Publish the **tool floor** the harness assumes (`gh`, `make`, `uv`, Postgres for
runtime paths, a browser for visual paths, `scheduler_create` for the loop's
continuity), extend the Capability Mapping table to cover *binaries* and an
"any other agent" column with a stated degrade path, and give Step 6b a
no-scheduler fallback that writes a machine-readable `chain_blocked` marker so
`make reconcile` can see it.
*Done when:* a documented floor exists, and "the chain is broken" is
distinguishable from "the loop has nothing to do".

### W7 — A principle → gate registry
The repo's own standard (from #1749) is that *a claim nothing checks is a
hope*. AGENTS.md states ~53 rules; some are enforced (mypy for type hints,
`test_no_new_mutable_globals_1445` for ADR-0005, the dead-definition and clone
ratchets, `test_docs_drift`), some are not obviously so. Publish
`docs/harness/principle-gates.md`: claim → enforcing gate → what "failing" looks
like, and a test that every **bold** rule in AGENTS.md's doctrine sections has a
row.
*Done when:* a new agent can answer "what stops me from doing X?" without reading
source.

### W8 — The orientation benchmark (the success metric)
The programme is done when an **alternate agent** is measurably competent here.
Concretely: a task card built from real repo work (e.g. one row of the #1748/#1749
residue, or a bug from the burn-down), given to an agent with **no other
context**, scored by an observer against harness-engagement assertions:

| Assertion | How it is scored |
|---|---|
| ran the right gate before pushing | push-gate stamp + commit content |
| left no shim / singleton / unclassified baseline row | the ratchets (they will fail on their own) |
| consulted the counter-prior or decision record when the task touched one | the agent's report says which; observer checks the file exists |
| did not invent work when the task was already covered | observer reads the diff for speculative scope |
| reported the degradation when it lacked a capability | report text |

The score is the programme's metric, and a *regression* in it outranks any
product lane: an agent that cannot be swapped in is a single-agent repo that
happens to have a `.claude` directory.
*Done when:* two runs on two different host/model combinations, both passing.

## Execution plan

Per workstream: the change, what proves it, and what it costs. `W1` and `W7` are
done and shipped; the rest are specified to the point where a session can pick
one up cold.

### W1 — Gate the harness's command surface ✅ shipped (`732ea38ef`)

**Change:** `tests/unit/test_harness_command_surface.py` — every file a `make`
recipe names must exist; every `make` target and `scripts/*.py` the driver names
in a fenced block must resolve; the player's own mandatory preflight is invoked
the way the driver invokes it.
**Proves itself:** both directions were falsified (a dangling recipe reference
fails the static check; the original `test-ux-preflight` bug fails the smoke).
**Cost:** one gate module (~150 lines), ~40 s of gate time.

### W2 — `future` beats a title heuristic ✅ shipped (`e668ec866`)

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

### W3 — Separate findings from staleness ✅ specified

**Change:** `qa_smoke_bar.py` prints `residual=` (findings: auto_seed, dead
crawl) and `stale=` (stamp age) separately; `improve_policy.py` gains a rule that
a mutation campaign may not be selected on a counter whose *finding* component
has never been non-zero, and `--pick` reports **why** (finding vs re-stamp).
**Proves itself:** with nine stale stamps and zero findings, `--pick` must not
select the bug campaign; with one auto_seed it must.
**Cost:** ~60 lines + tests across the bar, the policy and the example_probes
rollup. **Risk:** medium — three consumers read the current field.

### W4 — Require belief revision from a COGNITION cycle ✅ specified

**Change:** capability-map registry gains `Believed` / `Since revised` columns;
a COGNITION cycle's log entry must state one of `revised:` / `re-tested:` /
`falsified:`; a gate checks the map has no COGNITION row whose `Since revised` is
empty while its owning lane is `USED`.
**Proves itself:** a cycle that stamps a COGNITION row `USED` without a belief
line fails.
**Cost:** a gate plus a log-format rule. **Risk:** medium — it changes what every
future cycle must write, so the wording has to be cheap or it will be skipped.

### W9 — the documented surface must work from where the agent stands ✅ shipped

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

### W5 — A missing tool is a first-class outcome ✅ specified

**Change:** a `BLOCKED` row with the remedy in every probe-dependent strategy
(`agent_qa_smoke`, `demo_fleet`, `journey_dogfood`, …): playwright lives in the
`e2e` extra; Step 0b verifies the **forced** campaign's toolchain before
selection, so a forced strategy cannot be selected into a dead end.
**Proves itself:** with playwright absent, `agent_qa_smoke` reports BLOCKED +
remedy instead of exiting non-zero with a bare message.
**Cost:** playbook rows + one preflight probe. **Risk:** low.

### W6 — Tool floor + portable chain ✅ specified

**Change:** publish the **tool floor** (`gh`, `make`, `uv`, Postgres for runtime
paths, a browser for visual paths, `scheduler_create` for the loop's chain);
extend the Capability Mapping table with a *binaries* column and an "any other
agent" column whose cells state the degrade path; give Step 6b a no-scheduler
fallback that writes `chain_blocked` so `make reconcile` can see it.
**Proves itself:** an agent without `scheduler_create` completes a cycle and
leaves a marker `make reconcile` reports.
**Cost:** one table + one code path. **Risk:** low, and it is the most direct
answer to "we can swap in an alternate agent".

### W7 — Principle → gate registry ✅ shipped (`8c4d0f1c6`)

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

### W8 — The orientation benchmark (the metric) ⬜ not started

**Change:** a task card built from real repo work (one residue row from
#1748/#1749, or a bug from the burn-down), an **alternate agent** with no other
context, and an observer scoring the five assertions in the table above.
**Proves itself:** two runs on two host/model combinations, both passing.
**Cost:** two agent sessions plus an observer. **Risk:** the finding will be that
some assertion is unscorable — that is the point of writing it down first.

## Sequencing

W1 and W7 first (they make the harness's own claims checkable), then W2/W3/W5
(cheap, and each closes a defect the loop itself demonstrated), then W4 and W6
(the two that need a design decision rather than a patch), then W8 — which needs
the earlier ones to be worth measuring.

## What this programme will not do

- Not a rewrite of the harness. The refusal vocabulary, the per-cycle audit
  trail, the lane/skill split and the dig classifier are working; two cycles
  produced zero false positives.
- Not a licence for more prose. Every workstream above adds a **gate or a
  counter**, not a page. A workstream that cannot be falsified is not one.
- Not coupled to one host. Any amendment that only works on the host that
  authored it fails W6's bar.
