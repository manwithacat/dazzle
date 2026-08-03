# Improve — operator field guide

One page for humans who run or babysit the loop. Does not replace the agent
runbook (`.claude/commands/improve.md`).

For structure and portable design, see [Improve as harness exemplar](improve-exemplar.md).

---

## Status (no cycle)

```bash
# Probes + policy (what the next dig would see)
uv run python scripts/improve_example_probes.py --status
uv run python scripts/improve_policy.py --status

# Explore budget (cap 100)
cat .dazzle/improve-explore-count

# Last schedule decision
cat .dazzle/improve-schedule-state.json | head -40

# Tip CI
gh run list --workflow ci.yml --branch main --limit 1 \
  --json status,conclusion,databaseId,url,displayTitle,headSha

# Driver status mode (if the host supports /improve args)
# /improve --status
```

---

## Start / rearm the chain

```bash
# Manual budget reset (escape hatch; no cycle)
# /improve --reset-budget
printf '0\n' > .dazzle/improve-explore-count

# Decide next arm (agent then calls host scheduler with JSON fields)
uv run python scripts/improve_schedule_next.py --result PASS --ci auto

# Prefer one pending /improve one-shot; keep daily watchdog
# Prompt body: scripts/improve_watchdog_prompt.md (interval 1d, durable)
```

**Operator rearm pattern:** reset explore if capped → schedule_next →
`scheduler_create` with `scheduler_create` fields (honor `fire_immediately`
when you want the next dig soon). Log a one-liner in `dev_docs/improve-log.md`.

---

## Force a dig (when you know the lane)

```text
/improve                              # driver picks
/improve example-apps interesting_product
/improve framework-ux
/improve cimonitor                    # snapshot; repair only if red
/improve self-audit
/improve capability-sweep
/improve codeql
```

Full force table: `.claude/commands/improve.md` (ARGUMENTS).

---

## Read a cycle log entry

In `dev_docs/improve-log.md`, each cycle usually has:

| Field | Meaning |
|-------|---------|
| **when** | UTC timestamp |
| **ci** | tip badge + run id |
| **lane / strategy** | what ran |
| **status** | PASS / FAIL / BLOCKED / … |
| **budget_consumed / explore-count** | thrash accounting |
| **commit / pushed** | ship evidence |
| **Next:** | schedule interval + reason |

Ignore STALE map noise when the cycle stopped for **budget** or **CI hold** —
the stop reason is the signal.

---

## Common holds (not failures)

| Observation | Meaning | What to do |
|-------------|---------|------------|
| tip CI **in_progress** | No product push this cycle | Wait; chain should poll ~15m |
| tip CI **red** | Cycle is repair | Read cimonitor path; don’t stack Goal B |
| residual=0 + require_mutation | Prefer product/framework ship or PENDING seed | Not a stop condition under aggressive |
| explore 100/100 | Housekeeping only | `/improve --reset-budget` or release signal |
| Stale lock, dead PID | Previous agent died holding lock | Delete `.dazzle/improve.lock` if PID is dead |

---

## Safety reminders

- Red main CI **outranks** interesting product digs for that cycle.
- Prefer **one** pending improve chain; prune duplicates.
- Do not force-push; use `push_gate` / ship skill paths for product.
- Local state under `.dazzle/` and much of `dev_docs/` is ops — **git history**
  is what the team reviews after a long run.

---

## Related

- [Exemplar](improve-exemplar.md) · [Strategy catalog](strategy-catalog.md) · [Autonomous Harness](../autonomous-harness.md)
