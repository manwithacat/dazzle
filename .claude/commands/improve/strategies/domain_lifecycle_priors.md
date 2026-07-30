# Strategy: domain_lifecycle_priors (example-apps COGNITION)

**Class:** COGNITION
**Capability:** `dazzle domain` + lifecycle/process priors (`domain_brief.lifecycles`)
**Probe:** `scripts/domain_cognition_bar.py` (also via `improve_example_probes.py`)
**Force:** `/improve example-apps domain_lifecycle_priors`

## Why this exists

P0–P2 wired workflow templates, fuzzy lifecycle attach, process candidates, and
persona job filters into domain extract. The improve loop must **exercise** that
path or the capability map stamps `dazzle domain` STALE forever and gold examples
never densify from the new signals.

This is **not** Schema.org/OWL. Residual is:

| Signal | Meaning | Action |
|--------|---------|--------|
| `domain_stale` | Committed `AGENT_DOMAIN` lacks lifecycle_hint / process_candidates that live extract has | `--reextract` fleet or app |
| `multi_persona_no_process` + process_candidates | Gold DSL has ≥3 personas and 0 `process` blocks, but domain proposes handoffs | Author **one** real process in that app |
| `status∄transitions` + lifecycle_hint | Status enum without transitions while prior suggests states | Add `transitions:` (or `lifecycle:`) on that entity |

## Dig steps (one app per cycle unless reextract-only)

1. **OBSERVE**
   ```bash
   .venv/bin/python scripts/domain_cognition_bar.py --status
   .venv/bin/python scripts/domain_cognition_bar.py --next
   .venv/bin/python docs/research/scripts/example_sophistication.py
   ```
2. **If `next_action=reextract:*` or many `stale_domain`:**
   ```bash
   .venv/bin/python scripts/domain_cognition_bar.py --reextract
   ```
   Commit `examples/*/AGENT_DOMAIN.md` + `agent_domain.json` only. Log novelty:
   lifecycle_hint count and process_candidates before/after.
3. **If `next_action=process_densify:APP`:**
   - Read `examples/APP/agent_domain.json` → `process_candidates` + persona ids.
   - Author **one** grounded `process` in DSL (approval / escalation / assignment /
     settlement / triage) matching a candidate — not decorative.
   - Prefer apps with story spines already (`support_tickets`, `invoice_ops`,
     `fieldtest_hub`). Mirror idioms from `simple_task` processes.
   - `dazzle validate` in that example.
4. **If `next_action=transitions:APP:Entity`:**
   - Add transitions from lifecycle_hint / gold status enum; role guards when
     personas imply them.
   - Validate.
5. **Do not** invent chrome entities; do not re-run bootstrap as SSOT
   (counter-prior `bootstrap_pollution`).
6. **Receipt** (optional JSON under `.dazzle/improve-digs/`):
   - `strategy=domain_lifecycle_priors`
   - `lifecycle_hints_after`, `process_candidates`, `dsl_change` summary
   - `novel_cognition`: true if extract filled new hints **or** DSL gained
     process/transitions that were missing

## Selection notes

- Prefer when `improve_example_probes` residual_total is only domain_cognition,
  or when residual_total=0 and `dazzle domain` is COGNITION STALE (driver rule 7).
- `densify_allowed=0` does **not** block this dig — it is not WI D densify.
- One process or transition set per cycle; fleet reextract may ship alone.

## Success

- Probe residual drops for the worked app, **or**
- Fleet reextract clears `domain_stale` and stamps domain capability USED, **and**
- Cycle log states whether novel structure appeared (process/transitions/hints).
