# QA Trial gen-2 — current-model posture

**Status:** shipped in harness (mission builder + report). Scenarios may
opt into gen-2 fields incrementally; defaults apply when fields are
omitted.

## Why

Gen-1 (`v0.57` era) sized the trial agent for short, fragile sessions:
5–10 minute founder skim, wrap-up at 60% of steps, thin tool output
(paragraph verdict only). That matched models that thrashed and
re-filed the same 404. Current models (subscription Grok / Claude
drivers) can hold longer careful-pilot sessions, recover once, and
score structured criteria.

The improve loop also under-exercised the surface (capability map lag
on `dazzle qa trial` / `qa-trial` skill). Gen-2 raises *signal quality
per run* so fewer rotations still produce triageable output.

## What changed

| Area | Gen-1 | Gen-2 |
|------|-------|-------|
| Persona posture | Busy founder, 5–10 min | Careful pilot evaluator, 25–40 min energy |
| Default `max_steps` | 35 | **50** (scenario override still wins) |
| Default `token_budget` | 200k | **400k** |
| Wrap-up hint | 60% of steps | **80%** of steps |
| Recovery | “give up if hard” | **One alternate path**, then record |
| `record_friction` | category/severity/url/evidence | + `blocks_pilot`, `framework_vs_app` |
| `submit_verdict` | text only | + `recommend`, `criteria_scores`, `pilot_blockers_summary` |
| Scenario keys | tasks, stop_when, … | + optional `adoption_criteria`, `phases`, `token_budget` |
| Report | Verdict + friction | + Recommend, Adoption criteria, pilot blockers, scope tags |

Still **not** a CI gate. Non-determinism is expected.

## Scenario authoring (opt-in)

```toml
[[scenario]]
name = "manager_evaluation"
max_steps = 55
token_budget = 400000
phases = ["Orient", "Core jobs", "Light stress", "Decide"]
adoption_criteria = [
  "Urgency of open work is visible without spreadsheet mental math",
  "Would run a two-week pilot as-is or with minor fixes",
]
stop_when = """
Score adoption criteria and call submit_verdict with recommend=…
and criteria_scores (pass|partial|fail|untested).
"""
```

Flagship reference: `examples/support_tickets/trial.toml` →
`manager_evaluation`.

## Ops

- Prefer subscription drivers: `dazzle qa trial --fresh-db --llm-driver grok-cli`
- Improve lane: still one `(app, scenario)` per cycle; gen-2 runs cost
  more tokens — trade frequency for depth, or reset explore budget when
  you want a matrix night.
- Skill: `.agents/skills/qa-trial/SKILL.md` (gen-2 rules).

## Non-goals (this slice)

- Multi-agent or multi-session handoff harness
- Built-in vision pass on every friction URL (pair with taste/component
  vision manually when needed)
- Explore-budget carve-out in `/improve` (ops decision; not required for
  harness correctness)

## Agent QA ladder (issue #1625 → recipe)

Full published recipe: **`docs/recipes/agent-qa-ladder.md`**.

| Consumer ask | Framework status |
|--------------|------------------|
| Agent-first; human L4 | Recipe doctrine + skill |
| Coverage inventory | `dazzle qa trial-inventory` / `trial-coverage` |
| Journey affordance-only | `dazzle qa trial --mode journey` |
| Deep nested pilot | `dazzle qa trial` (this doc) |
| `ownership` + `story_gap` | `trial_friction.py` schema; auto_seed filter |
| Domain-theory hook | `dazzle qa trial-hypotheses`; example `agent/domain-theory/` |
| JSON closed loop | trial report sidecar `schema_version: 2` + `auto_seed` |
| Multi-act handoff | Still consumer skill (framework hook later) |

See GitHub #1625 for CyFuture + AegisMark field notes.
"""
