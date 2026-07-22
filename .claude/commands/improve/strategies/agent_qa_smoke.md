# Strategy: agent_qa_smoke (L2.5 mechanical smoke dig)

**Lane:** `example-apps`
**Force:** `/improve example-apps agent_qa_smoke`
**KPI:** gross functional bugs (404 / 5xx / empty main / white screen / structure double-wrap) — **not** adoption verdicts.

## When picked

- Campaign `land-l25-smoke` active (`improve/improve-policy.yaml`)
- `python scripts/qa_smoke_bar.py --status` residual > 0
- Steady-state recurring every N cycles (`improve_policy.py --pick`)
- Operator force for dig exercise

## OBSERVE

```bash
python scripts/improve_policy.py --status
python scripts/qa_smoke_bar.py --status
python scripts/improve_example_probes.py --status   # context only
```

Prefer `qa_smoke next=` app when residual; else smoke-dig rotation.

## ACT

1. Ensure hub / app is up (`DAZZLE_QA_MODE=1` or hub `--test-mode`):

   ```bash
   curl -sS http://127.0.0.1:9080/_hub/api/apps | head -c 400
   # if needed:
   curl -sS -X POST http://127.0.0.1:9080/_hub/start/<app>
   # or: cd examples/<app> && DAZZLE_QA_MODE=1 dazzle serve --port <port> --test-mode
   ```

2. **Dig** (preferred fleet shortcut):

   ```bash
   dazzle qa smoke-dig --once                  # next seeded showcase app
   # or targeted:
   dazzle qa smoke-dig --app simple_task
   python scripts/qa_smoke_dig.py --app simple_task --max-clicks 12
   ```

3. Direct crawl when debugging one URL set:

   ```bash
   dazzle qa smoke-crawl -a <app> -p <persona> -u http://127.0.0.1:PORT \
     --max-clicks 12
   ```

4. Read report: `examples/<app>/dev_docs/qa-smoke-*.json`
   - `auto_seed` → product medium+ bugs (seed improve backlog / fix this cycle if clear)
   - `friction` → full oracle hits (includes rbac_expected / harness)

## FIX bar this strategy

| Finding | Action |
|---------|--------|
| Product 404 / empty main / 5xx on inventory or create | **Fix this cycle** if root cause clear; else PENDING with URL + evidence |
| Structure nested refresh / dup region ids | Framework fix or file framework issue; ownership=framework |
| rbac_expected 403 | No product fix — leave |
| harness (loading shell, ERR_INSUFFICIENT_RESOURCES) | Do not auto-seed product |

Success for near-term campaign: **finding gross bugs** (or confirming a clean dig with evidence). Subtle bugs are bonus.

## Do not

- Run WI densify (`densify_allowed=0` hard stop)
- Treat deep `qa trial` recommend as a substitute for smoke pass/fail
- Stamp HYGIENE STALE rows as the dig outcome without running smoke-crawl

## LOG

```
lane: example-apps
strategy: agent_qa_smoke
app: <app>
smoke_auto_seed: N
report: examples/<app>/dev_docs/qa-smoke-...
fixes: <shas or none>
budget_consumed: 1
```

Stamp capability-map rows for `qa smoke-crawl` / `smoke-dig` as USED this cycle.
