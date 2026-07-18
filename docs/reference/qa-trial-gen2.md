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

## Consumer field notes (issue #1625)

CyFuture + AegisMark dogfood (2026-07) argued **agent-first live
investigation** with a machine V&V ladder — human QA is gated L4, not
the quality definition. Gen-2 addresses only the *deep nested-LLM trial*
posture. The larger product shape they want is:

| Consumer ask | Framework status |
|--------------|------------------|
| Agent-first default; human optional | Documented here; still often framed as “pseudo-human” elsewhere |
| Mechanical vs deep trial modes | Partial — improve lane rotation ≈ mechanical-ish; `qa trial` ≈ deep nested LLM |
| **Coverage inventory** drive (URL from matrix OK) | Not first-class in `/qa-trial` — consumers use sibling skills |
| **Journey path** drive (only rendered affordances) | Nested trial navigates freely; no hard “no URL shortcut” mode |
| **Multi-act / handoff** | Not in harness |
| Friction `ownership` (product/seed/rbac_expected/harness/framework) | Gen-2 has `framework_vs_app` only — coarser |
| `story_gap` category | Not in enum yet |
| Inventory walk after golden path | Consumer-side; framework should document + optionally script |
| Domain-theory hypotheses | Not in trial.toml |
| Empty discovery → structured Ask | Improve HOUSEKEEPING paths; no formal Ask protocol |
| Harness false-positive appendix (lazy IO, actionability, magic-link) | Undocumented |
| KPI: closed PENDING / false-positive rate | Not instrumented |

See GitHub #1625 for full CyFuture thesis + AegisMark extensions.
"""
