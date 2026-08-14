Single autonomous-improvement entrypoint for Dazzle. Each cycle: lock → local preflight → **CI badge snapshot** (repair if main is red) → **CodeQL open-alert snapshot** (remediate if high/error open) → **GitHub inbox** (consumer + owner/pilot bugs + open PRs / Dependabot) → signals → pick the highest-leverage lane → hand off to its playbook → record outcome → **self-schedule the next one-shot** (opportunistic CI-aware interval; ~15m inbox re-probe when quiet).

**Human intelligibility (does not change this runbook):** structure and portable design → `docs/harness/improve-exemplar.md`; operator rearm/status → `docs/harness/operator-field-guide.md`; strategy one-liners → `docs/harness/strategy-catalog.md`.

Replaces /improve, /ux-cycle, /trial-cycle, /ux-converge. The lanes preserve those skills' bodies; the driver owns the scaffolding (lock, preflight, CI gate, CodeQL gate, GitHub inbox, signal bus, log, self-schedule).

### Multi-agent workflows (Grok Build)

Parallel cognition panels are extracted as project workflows under
`.grok/workflows/` (see that directory's `README.md`). The driver still owns
lock, gates, pick, ship, and self-schedule; workflows return structured
`complete()` results for the driver to apply.

| Force / cadence | Workflow | Notes |
|-----------------|----------|--------|
| `self-audit` / ≥15 cycles | `improve-self-audit` | ≤5 parallel commit skeptics; `budget_consumed: 0` |
| `capability-sweep` / ≥20 cycles | `improve-capability-sweep` | inventory + 3 dig recommenders; `budget_consumed: 0` |
| `example-apps` visual tier-2 | `improve-visual-review` | after `dazzle qa capture`; pass `manifest_path`; budget **5** |

```text
/workflow improve-self-audit
/workflow improve-self-audit {"apply":true}
/workflow improve-capability-sweep
/workflow improve-visual-review {"manifest_path":"dev_docs/ux_cycle_runs/…/manifest.json"}
```

On hosts without the workflow tool, fall back to the numbered playbooks in
`improve/strategies/*.md` (hand-rolled subagent dispatch).

ARGUMENTS: $ARGUMENTS

If `$ARGUMENTS` is empty: driver picks the lane.
If `$ARGUMENTS` matches a lane name (`framework-ux` / `example-apps` / `trials` / `ux-converge` / `test-suite` / `hm-convergence`): force that lane. (`self-audit` forces the driver-level self-audit strategy; `capability-sweep` forces the capability-coverage sweep; `trial-signals` forces the TR-action drain strategy; `cimonitor` forces the CI-badge gate playbook even when main is green — re-check + report only unless red; `codeql` forces the CodeQL open-alert poll + remediate playbook; `consumer-issues` / `github-prs` force GitHub inbox strategies; `semgrep` / `semgrep-hygiene` forces Semgrep packs + Sentinel python_audit hygiene — `improve/strategies/semgrep_hygiene.md`.)
If `$ARGUMENTS` is `<lane> <strategy>`: force that lane and that sub-strategy.
Known **example-apps** sub-strategies (agent-first maturity loop — run in order
when residual remains: product → demo → journey):

| Force | Playbook | Probe |
|-------|----------|-------|
| `example-apps product_maturity` | `improve/strategies/product_maturity.md` | `scripts/example_product_maturity.py` |
| `example-apps demo_fleet` | `improve/strategies/demo_fleet.md` | `scripts/demo_fleet_bar.py` (+ #1626) |
| `example-apps journey_dogfood` | `improve/strategies/journey_dogfood.md` | `scripts/example_journey_maturity.py` |
| `example-apps story_walk` | `improve/strategies/story_walk.md` | `scripts/story_walk_bar.py` (landing stories ↔ walks) |
| `example-apps agent_acceptance_panel` | `improve/strategies/agent_acceptance_panel.md` | `scripts/trial_verdict_bar.py` + live `qa trial` |
| `example-apps agent_qa_smoke` | `improve/strategies/agent_qa_smoke.md` | `scripts/qa_smoke_bar.py` + `dazzle qa smoke-dig` |
| `example-apps domain_lifecycle_priors` | `improve/strategies/domain_lifecycle_priors.md` | `scripts/domain_cognition_bar.py` (+ lifecycle/process priors) |
| `example-apps hyperpart_presentation` | `improve/strategies/hyperpart_presentation.md` | recapture prove only; emit fix is framework-ux |
| `framework-ux hyperpart_presentation` | `improve/strategies/hyperpart_presentation.md` | MCP `presentation` + `product_quality` presentation residual |
| `framework-ux hyperpart_emitter` | `improve/strategies/hyperpart_emitter.md` | `hyperpart_scenarios planned_emitter>0` — ship DSL path for gallery-only part |
| `example-apps interesting_product` | `improve/strategies/interesting_product.md` | post-5.8 Goal B depth menu + still proof |
| `example-apps depth` | `improve/strategies/interesting_product.md` | alias of interesting_product |
| `example-apps distill` | `improve/strategies/distill.md` | Goal C coat residual — subtract filter-wall / cartesian / rails |

**Post-5.8 (interesting SaaS):** when `residual_total=0` **and**
`goal_b_coat residual_total=0` and open-hop / dual-open cycles hit the policy
cap (`max_consecutive_open_hop`, default 5), force
**`example-apps interesting_product`** — one closed depth id + hero recapture.
When Goal A is green but `goal_b_coat residual_total>0`, force
**`example-apps distill <app>`** (Goal C — subtract, do not add).
Doctrine: `docs/reference/interesting-saas-context.md`. Dual-open without recapture
is **harness_only** (Goal A); do not claim bake-off lift. Presentation OCR residual
stays the immune system when residual > 0.

**Presentation residual** (`ref_as_repr` / `person_as_text` / `delta_theater` on hero
still OCR) is folded into `product_quality` / `dazzle demo quality` residual_total.
When it fires, probes force **`framework-ux hyperpart_presentation`** (not demo_fleet).
Agent surfaces:

```bash
# OBSERVE
dazzle demo quality -p examples --json          # presentation residual in residual_total
dazzle qa hyperpart-opportunities --app support_tickets --table
python scripts/improve_example_probes.py --status   # hyperpart_scenarios planned_emitter / force=
# MCP (downstream + monorepo agents)
#   product_quality(operation=score, project_root=examples)
#   presentation(operation=cognition|opportunities|residual, app=…)
# KG: knowledge(operation=counter_prior, id=ref_as_repr)
# Doctrine: docs/reference/hyperpart-presentation.md
# Emitter package: improve/strategies/hyperpart_emitter.md + hyperpart_scenarios.toml
```

Unified OBSERVE for every example-apps cycle (and for `--status`):

```bash
python scripts/improve_example_probes.py --status
# product_maturity … residual=N next=…
# demo_fleet … residual=N next=…
# journey_maturity … residual=N next=…
# story_walk / trial_verdict …
# domain_cognition … residual=N next=…   # lifecycle/process priors
# example_probes residual_total=N next=… force=example-apps <strategy>
```

**Dig contracts & process sensors** (maps vs residual, contract PASS evidence,
divergence, epistemic `live_unproven`—design, pre-implementation):
`docs/superpowers/specs/2026-07-21-improve-dig-contracts-and-process-sensors-design.md`.

If `$ARGUMENTS` is `--status`: emit a status report across all lanes and exit (no cycle).
If `$ARGUMENTS` is `--reset-budget`: write `0` to `.dazzle/improve-explore-count`, log the manual reset, and exit (no cycle). Operator escape hatch — use when the cap was reached but exploration should continue (e.g. after a large framework change that a release signal didn't capture).

## Lanes

| Lane | Targets | Backlog section | Playbook |
|------|---------|-----------------|----------|
| framework-ux | Dazzle's UI layer (templates, contracts, fitness walks) | `## Lane: framework-ux` | `improve/lanes/framework-ux.md` |
| example-apps | example apps (product/demo/journey maturity probes, DSL gaps, lint, visual) | `## Lane: example-apps` | `improve/lanes/example-apps.md` |
| trials | qualitative persona scenarios (trial.toml) | `## Lane: trials` | `improve/lanes/trials.md` |
| ux-converge | example apps with nonzero UX contract failures | `## Lane: ux-converge` | `improve/lanes/ux-converge.md` |
| test-suite | test-suite redundancy-cluster collapse (#1530) | `## Lane: test-suite` | `improve/lanes/test-suite.md` |
| hm-convergence | HM ownership floors + dual-locks + **hyperpart coherence investigate/drain** + taste (Tailwind drain complete) | `## Lane: hm-convergence` | `improve/lanes/hm-convergence.md` |

## State files

| File | Purpose |
|------|---------|
| `dev_docs/improve-backlog.md` | All lanes' backlog tables, one `## Lane:` section each |
| `dev_docs/improve-log.md` | Append-only cycle log (single source of truth across all lanes) |
| `dev_docs/improve-backlog-archive.md` | Settled backlog rows (DONE/VERIFIED/CLEAN/RESOLVED/FILED-and-closed), moved by `scripts/improve_compact.py` |
| `dev_docs/improve-log-archive.md` | Cycle-log entries older than the last 25, moved by `scripts/improve_compact.py` |
| `.dazzle/improve.lock` | PID + timestamp; 15-min TTL |
| `.dazzle/improve-explore-count` | Single counter shared across all lanes' explore phases (cap 100) |
| `.dazzle/improve-schedule-state.json` | Last self-schedule decision (interval, reason, scheduler_create payload) |
| `.dazzle/improve-github-inbox.json` | Last issues+PRs poll (`scripts/improve_github_inbox.py`) |
| `.dazzle/signals/` | Cross-lane signal bus (existing `ux_cycle_signals` infrastructure) |

All gitignored (under `.dazzle/` or `dev_docs` local state as noted).

**State compaction.** The driver reads the backlog + log every cycle, so settled
material is pure context burn. When either working file exceeds **100 KB**, run
`python scripts/improve_compact.py` during Step 0d. The script is idempotent and
fail-safe (any row it can't parse unambiguously stays put); archives are append-only
and stay greppable. Archiving is a *driver housekeeping* action — it does not count
as a lane modifying DONE/VERIFIED rows. If a regression re-opens archived work,
copy the row back from the archive with status `REGRESSION`.

## Cycle

### Step 0a: Lock

1. If `.dazzle/improve.lock` exists and is < 15 min old → abort with the lock contents.
2. If older → delete as stale.
3. Create lock with `PID ISO-timestamp`.

### Step 0b: Preflight (always)

```bash
make preflight-surface   # structural/artifact debt (API/docs/import/ratchet/HM)
make test-ux-preflight
```

If either is red, **STOP and fix before continuing** — same rule as old /ux-cycle,
applies to every lane now. Do not start a product lane on unpaid surface debt
(that is the red-main stacking pattern).

When this cycle will **ship** product code (any lane that commits), also run
before push (or rely on `make ci-fast`, which includes it):

```bash
make ship-surface   # bandit + recurrent SPEC/IR/viewport pack (Tier 0.5)
# mid-edit optional: make ci-changed
```

Habit source: AGENTS.md **Ship Discipline** + `docs/contributing/local-ci-concordance.md`.

### Step 0c: CI badge gate (always)

Every cycle opens with a **snapshot** of the README badge workflow on `main` (not a long poll). Playbook: `improve/strategies/cimonitor.md` (thin wrapper around `.agents/skills/cimonitor/SKILL.md`).

```bash
gh run list --workflow ci.yml --branch main --limit 1 \
  --json status,conclusion,databaseId,url,displayTitle,updatedAt
```

| Snapshot | Driver action |
|----------|---------------|
| **Latest completed run `conclusion=failure` (or `cancelled` / `timed_out` that left the badge red)** | **This cycle is CI repair.** Do **not** pick a product/capability lane. Follow cimonitor: job breakdown → `gh run view <id> --log-failed` → fix root causes (including pre-existing) → **close the loop** (promote new failure class into ship-surface/preflight if Tier 0 would have missed it) → commit → **`python scripts/push_gate.py check --repair --min-tier 0`** → push → note follow-up. Log `lane: cimonitor`. `budget_consumed: 0`. Apply Step 3–4 (log, mark_run, release lock) and exit. Next `/improve` re-checks; if still red, repair again. |
| **Latest run `in_progress` / `queued`** | Record status + run URL under **ci:**. **Do not push a new product ship** while tip CI is still running (push_gate blocks this). Prefer digs that do not require push, or end the cycle early and self-schedule `INTERVAL_CI_POLL` (`15m`). Exception: cimonitor repair of a *completed* red tip uses `--repair`. |
| **Latest completed run `conclusion=success`** | Record **ci: green** (run id) in the cycle log; continue. |
| **`gh` unavailable / auth failure / no runs** | Log **ci: unavailable** with the error; continue the cycle (local preflight already ran). Do not invent a green badge. |

**Hard preemption:** a red completed badge outranks REGRESSION backlog rows, CodeQL, self-audit, capability-sweep, TR drain, and explore for **this** cycle — a broken main badge is fleet-visible shipped-broken. Product REGRESSION work resumes on the next green (or when CI is unavailable and cannot be repaired here).

Forceable via `/improve cimonitor` (always run the snapshot; only enter repair mode when red, unless already mid-fix from a prior red cycle).

### Step 0c2: CodeQL / code-scanning gate (always when 0c did not claim repair)

Cheap poll of open GitHub code-scanning alerts. Playbook: `improve/strategies/codeql.md`.

```bash
gh api "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/code-scanning/alerts" \
  --jq '[.[] | select(.state=="open")] | length'
```

| Snapshot | Driver action |
|----------|---------------|
| **Open alert(s) with `severity=error` or `security_severity_level` ∈ {`critical`,`high`}** | **This cycle is CodeQL repair.** Do **not** pick a product/capability lane. Follow `codeql.md`: list alerts → fix true positives (prefer root-cause + tests; model-pack for real barriers; dismiss only with reason) → commit → push. Log `lane: codeql`. `budget_consumed: 0`. Apply Step 3–4 and exit. |
| **Open alerts only warning/note** | Log `codeql: N open (low)`; **continue** unless ≥10 cycles since last `lane: codeql` and any remain open — then drain one. |
| **Zero open** | Log `codeql: clean`; continue. |
| **`gh` / API failure** | Log `codeql: unavailable`; continue. |

**Preemption order:** CI red (0c) > CodeQL high/error (0c2) > GitHub inbox (0c3) > REGRESSION > self-audit > … Fleet-visible Security findings outrank product explore but never jump ahead of a red CI badge.

Forceable via `/improve codeql` (always poll; remediate any open alerts, not only high).

### Step 0c3: GitHub inbox — consumer issues + PRs (always when 0c/0c2 did not claim repair)

Cheap poll of open issues and PRs. Machine probe:

```bash
uv run python scripts/improve_github_inbox.py
# JSON → stdout + .dazzle/improve-github-inbox.json
```

| Inbox heat / primary | Driver action |
|----------------------|---------------|
| **`dependabot_merge`** (Dependabot PR, checks green, not draft) | **This cycle is github-prs.** Follow `improve/strategies/github_prs.md`: re-confirm checks → `gh pr merge --squash --delete-branch` (up to 2 PRs). Log `lane: github-prs`. `budget_consumed: 0`. Apply Step 3–4 and exit (or continue only if nothing merged and heat cleared). |
| **`dependabot_ci_red`** | **This cycle is github-prs.** Investigate PR checks (flake re-run vs real break). Do not merge red. Log `lane: github-prs`. |
| **`consumer_bug`** (downstream author and/or consumer label, bug-shaped) | **This cycle is consumer-issues.** Follow `improve/strategies/consumer_issues.md`: one issue, Tier-1 fix if clear else analysis comment. Log `lane: consumer-issues`. |
| **`owner_bug`** (owner-filed bug-shaped, incl. `pilot:cyfuture` / pilot labels) | **This cycle is consumer-issues** (same playbook). Owner/pilot open bugs are **first-class** improve work — claim one issue, Tier-1 fix if clear. Do **not** leave them idle behind STALE map re-stamps or defer to a separate `/issues` session. Log `lane: consumer-issues`. |
| **`inbox_nonzero`** only (human PRs / non-bug consumer noise) | Log summary under **github:**; **continue** selection (do not burn the whole cycle unless nothing else is actionable). |
| **Probe failure / `gh` unavailable** | Log **github: unavailable**; continue. |

**Dependabot policy:** routine bot dependency bumps **auto-merge when CI is green** (see playbook gates — non-ignorable check failures block merge). Non-Dependabot PRs are **never** auto-merged by this strategy.

**Issue bug policy:** bug-shaped issues — whether from downstream authors **or** the project owner (including pilot-labeled CyFuture findings) — are **first-class improve work**. Step 0c3 claims the cycle when inbox heat is `consumer_bug` or `owner_bug`. Features / design-only / `future`-labeled work still skips implement. Quiet product state still self-schedules ~15m so Step 0c3 re-polls GitHub regularly rather than waiting multi-hour all-clear gaps.

**`future` / PARKED Deferred Decisions:** issues labeled `future` that link a
`docs/decisions/DD-*.md` with `status: PARKED` are **not** implementable until
the DD is `FORCED` with a named consumer (see `docs/decisions/INDEX.md`). Do not
“make progress” by speculative-building #1621/#1622-class work. If a real
consumer force appears in inbox or pilot signal, update the DD to `FORCED` first,
then implement.

Forceable via `/improve github-prs` or `/improve consumer-issues`.

### Step 0d: Read signals

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import since_last_run
signals = since_last_run(source="improve")
```

Categorise:
- `dazzle-updated` → **reset the explore budget**: write `0` to `.dazzle/improve-explore-count` and note the reset (with the release version) in this cycle's log entry. A published release means fresh explore territory — the cap is per-release, not per-lifetime. Also mark affected backlog rows for re-verification (delegated to each lane).
- `fix-deployed` → mark affected backlog rows for re-verification (delegated to each lane)
- `trial-friction` → bias next lane selection toward `framework-ux` (qualitative finding may need a contract)
- `ux-component-shipped` → bias toward `example-apps` (re-verify apps using that component)
- `ux-regression` → priority signal; jump straight to the relevant lane regardless of selection algorithm

### Step 0e: Compact state (only when oversized)

```bash
[ $(wc -c < dev_docs/improve-backlog.md) -gt 100000 ] || [ $(wc -c < dev_docs/improve-log.md) -gt 100000 ] \
  && python scripts/improve_compact.py
```

See **State compaction** above. Skip silently when both files are under the threshold.

### Step 1: Pick a lane

If Step 0c already claimed this cycle for CI repair, Step 0c2 for CodeQL repair, or Step 0c3 claimed it for github-prs / consumer-issues, skip Step 1–2 (already handled).

If `$ARGUMENTS` forces a lane, skip to Step 2.

**Configurable prioritisation** (`improve/improve-policy.yaml`):

```bash
python scripts/improve_policy.py --status
# improve_policy active_campaign=… pick force=… reason=…
python scripts/improve_policy.py --pick    # e.g. example-apps agent_qa_smoke
```

When `--pick` returns non-empty `force_args` (active **campaign** or **recurring**
L2.5 / `qa_smoke` residual), use that as the lane+strategy **unless** hard
preemption applies (REGRESSION rows, self-audit cadence, capability-sweep cadence,
fresh signal bias still listed below may reorder — campaign `yield_to` only
skips for CI/CodeQL/inbox/REGRESSION/self-audit). Near-term campaign
`land-l25-smoke` forces dig exercise on examples (gross bugs: 404 / empty main).

**Aggressive posture** (operator): activate `aggressive-change` when residual is
clear but the loop is stamp-thrashing smoke/map digs **or** when digs keep
passing without product/framework ships. Policy rotates mutation-first:

`framework-ux` → `hm-convergence hyperpart_coherence` → `story_walk` →
`agent_acceptance_panel` → `journey_dogfood` → `gallery_probes`
(→ `dual_lock_expand` only if queue depth > 0; → smoke only if residual > 0).

Rules the driver **must** honor under `posture=aggressive` / `require_mutation=1`:

1. **Ship or seed.** Dig cycles leave a code commit **or** an actionable
   `PENDING` backlog/auto_seed row. Map-only PASS / dual-lock defer-when-queue-0
   is not progress under this campaign.
2. **Fix friction in-cycle.** When a panel/walk finds product or framework
   friction, fix it in the same cycle (or seed PENDING and claim next). Do not
   re-panel the same harness thrash for >`max_consecutive_panels` (default 2).
3. **Skip drained queues.** dual_lock queue depth 0 → skip `dual_lock_expand`.
   smoke residual 0 → skip stamp-only smoke digs.
4. **Still yield** to red CI / CodeQL / REGRESSION / inbox. Does **not** bypass
   `densify_allowed=0` (WI clone desks stay banned — aggression is depth and
   real ships, not sprawl).

```bash
python scripts/improve_policy.py --activate aggressive-change
python scripts/improve_policy.py --status   # posture=aggressive require_mutation=1 + next force
python scripts/improve_policy.py --clear-campaign   # back to steady_state
```

Playbook: `improve/strategies/agent_qa_smoke.md`. Residual bar:
`python scripts/qa_smoke_bar.py --status`.

For each lane, compute two numbers from the unified backlog:

| Number | Method |
|--------|--------|
| `actionable_count(lane)` | Count rows in the lane's section with status ∈ {`REGRESSION`, `PENDING`, `IN_PROGRESS`, `DRAFT`, or qa:`PENDING`} |
| `last_run_at(lane)` | Most recent `improve-log.md` entry for that lane that wasn't a housekeeping idle tick |

**example-apps probe residual** (machine, free): also run
`python scripts/improve_example_probes.py --status` and add
`residual_total` to `actionable_count(example-apps)`. Prefer this lane when
`residual_total > 0` even if the markdown backlog table is empty — the
loop is agent-first, not backlog-table-first. Sub-strategy order inside the
lane: `product_maturity` → `demo_fleet` → `journey_dogfood` → `story_walk`
→ `agent_acceptance_panel` (see `improve/lanes/example-apps.md`).

Selection priority:

1. **Any lane with REGRESSION rows** → that lane (most urgent backlog — shipped broken). Note: a red CI badge or CodeQL high/error already preempted this step via 0c / 0c2; GitHub inbox (0c3) already ran if it claimed the cycle.
2. **Self-audit cadence**: if ≥15 cycles since the last `lane: self-audit` log entry (or none exists), run the self-audit strategy this cycle (playbook: `improve/strategies/self_audit.md` — adversarial review of recent `improve:` commits vs their log/backlog claims). Forceable via `/improve self-audit`. **Grok preferred:** `/workflow improve-self-audit` (or `{"apply":true}` to write AUD/REGRESSION rows in-workflow).
3. **Capability-sweep cadence**: if ≥20 cycles since the last `lane: capability-sweep` log entry (or none exists), run a capability sweep this cycle — re-derive inventory and reconcile `.claude/commands/improve/capability-map.md` **table only**: flag `UNOWNED`, recompute STALE-effective (lag ≥20), report **COGNITION vs HYGIENE** digs. Overwrite “Last sweep” one-liners (≤5); do **not** re-grow the map with ship narratives. Forceable via `/improve capability-sweep`. **Grok preferred:** `/workflow improve-capability-sweep`.
3b. **Semgrep hygiene cadence**: if ≥20 cycles since the last log entry mentioning `semgrep hygiene` / `lane: … semgrep` (or none exists), **and** 0c–0c3 did not claim the cycle, prefer a short HYGIENE dig via `improve/strategies/semgrep_hygiene.md` before pure STALE re-stamps — especially when `dazzle sentinel scan` is STALE. Forceable via `/improve semgrep`. Does **not** preempt REGRESSION / CI / CodeQL / inbox / self-audit / capability-sweep.
4. **Signal-biased pick**: if a `trial-friction` / `ux-component-shipped` / `ux-regression` signal is fresh, prefer the biased lane regardless of count
5. **Highest `actionable_count > 0`** → that lane; ties broken by oldest `last_run_at`
6. **TR-signal drain (autonomous-only).** If the trials backlog (`## Lane: trials`) has any **autonomous-actionable** TR row (see below), pick the owning lane for that row and run `improve/strategies/trial_signal_action.md` this cycle (log `picked {lane} for TR-N — {status}/{severity}`). Forceable via `/improve trial-signals`. Preempts pure capability re-stamps when product signal is sitting idle. Does **not** preempt REGRESSION / self-audit / capability-sweep / fresh signal bias.
7. **Explore phase, cognition-directed (not lag-only STALE).** Consult `.claude/commands/improve/capability-map.md` (**registry table**). Recompute lag as `current_cycle − last-exercised` (treat `USED` with lag ≥20 as **STALE-effective**). Read each row's **Class** (`COGNITION` | `HYGIENE` | `DRIVER` | `EXEMPT`).

   **Probe residual still outranks this rule** when `improve_example_probes.py` reports `residual_total > 0` — pick example-apps residual dig first (product → demo → journey → felt → **story_walk** → **trial_verdict**/acceptance → **process_dig** incomplete contracts).

   **#1637 hard stop on WI densify:** read `densify_allowed=` from product_maturity /
   warehouse_index status. When `densify_allowed=0` (residual=0 **and**
   `wi_fleet ≤ wi_floor`), **do not** pick ordinary explore WI D densify, do not
   add isomorphic `*_ops` desks, and do not cite soft-cap skip as progress.
   Prefer COGNITION / HYGIENE / `agent_acceptance_panel` instead.

   When residual is clear, pick **one** capability in this order (log `picked {lane} to exercise {capability} — {class}/{reason}`):
   1. Any `UNOWNED` (strongest gap)
   2. **COGNITION** STALE / STALE-effective — rank by **epistemic value**, not lag alone:
      prefer (in order) residual/risk signals, counter-priors, `domain` / `demo_world` /
      `product_quality` / `demo quality` / `reset-and-load` / `qa trial` / persona-home
      paths over pure re-touch. Among equal value, highest lag first.
   3. **When `densify_allowed=0`:** COGNITION-STALE (2) then HYGIENE (4) then
      `agent_acceptance_panel` — **never** WI D densify. Floor is a hard stop, not theater.
   4. **HYGIENE** STALE / STALE-effective (validate/prove/coverage/sentinel/MCP re-touch) —
      cheap CLI re-exercise; may stamp several related HYGIENE surfaces in one dig if
      they share a lane and a single app, but still one owning lane per cycle.
   5. Any `OWNED-IDLE` with `last-exercised = —` (never first-exercised), preferring
      **in-loop** owners; playbook: `improve/strategies/owned_idle_exercise.md`
   6. Any `OWNED-IDLE` exercised before but lag ≥20 (treat as its Class above)
   7. Else ordinary explore — **only if `densify_allowed=1`** may WI D/N/L feature_creep
      run (job-backed desks only; no isomorphic enum `*_ops` clones). Otherwise
      framework-ux edge cases / acceptance panel.

   **Metered vision policy:** never select `component-vision` / `property-vision` /
   `taste-panel` as “top STALE” on the metered API path. Always exercise the
   **subscription substitute** (`hm_visual_smoke` / host-Read / gallery probes) and
   stamp that free path. **Do not** idle or housekeeping-cite “vision STALE (metered)”.

   STALE is a **priority bias for explore**, not a product bar and not a reason to
   skip residual, domain rebuild, or CI repair.

8. **Explore budget at cap (100)** → housekeeping idle tick; log + release lock + exit.
   Log **must** say: `explore capped by policy — no digs` and name the two renewal
   routes (`dazzle-updated` release signal, or `/improve --reset-budget`).
   **Do not** list STALE rows as “deferred work the loop is blocked on” — STALE did
   not cause the stop; the budget did. Raw STALE counts in housekeeping are noise.

**GitHub inbox note:** Dependabot-ready merges, consumer bugs, and owner/pilot bugs are claimed in **Step 0c3** (before this list). If 0c3 only logged a non-blocking inbox summary, do not re-pick github-prs unless heat remains and product selection is empty.

Record the choice. Bias from signals, TR-drain, or capability-coverage must be logged ("picked example-apps because of fresh ux-component-shipped from cycle N"; "picked example-apps to exercise domain — COGNITION STALE"; "picked framework-ux for TR-50 OPEN_FRAMEWORK high") so future operators can audit.

### Autonomous TR eligibility (rule 6)

A TR row is **autonomous-actionable** when **all** of:

| Gate | Pass when |
|------|-----------|
| Status | ∈ {`OPEN`, `OPEN_FRAMEWORK`, `OPEN_DSL`, `FIXED-VERIFY`} — not `OPEN_UNKNOWN`, `NEEDS_REINFORCE`, `NOTED-POLLUTED`, `BLOCKED_ON→*`, praise-only |
| Severity | ∈ {`high`, `medium`} **or** status is `FIXED-VERIFY` (any severity — re-verify is cheap) |
| Clarity | Description names a concrete surface (URL, region, CLI flag, error string) **or** status is `FIXED-VERIFY` / already `→ #NNN` |
| No human fork | Fix does **not** require product/design intent (no tenancy/RBAC "what should we allow?" questions). If the only honest action is "ask the user", leave the row for a human session |

**Lane routing for TR rows:**

| Status / shape | Owning lane | Default action |
|----------------|-------------|----------------|
| `OPEN_FRAMEWORK` / filed `→ #N` | `framework-ux` (or `test-suite` if clearly test harness) | Reproduce → fix if local/clear → ship; else reinforce + leave filed |
| `OPEN_DSL` | `example-apps` | DSL/demo fix in the named app; validate+lint |
| `FIXED-VERIFY` | `trials` | Re-run the named scenario with `dazzle qa trial --fresh-db` (+ subscription driver); close or re-open |
| `OPEN` with clear bug + mechanism | best-fit lane | Same as OPEN_FRAMEWORK / OPEN_DSL by mechanism |

Skip (not autonomous): pure aesthetic/confusion without DOM/URL; same-trial contradictions (`NEEDS_REINFORCE`); anything that needs "author intent" (tenancy model, persona RBAC design). Full playbook: `improve/strategies/trial_signal_action.md`.

**Trials / LLM (cycle 666→715 lesson):** Do **not** sticky-skip `dazzle qa trial` or TR FIXED-VERIFY as "blocked on grok/LLM" when a subscription CLI is on PATH. `max turns reached` is product/config (raise grok-cli `max_turns`), not auth BLOCKED. Re-probe with `call_subscription_cli` before any multi-cycle skip; on Grok-only hosts use `--llm-driver grok-cli` even when examples pin `claude-cli`. See `improve/lanes/trials.md` outcome classification.

### Step 2: Hand off to lane

Read `improve/lanes/{name}.md` and follow its playbook end-to-end. The lane:

- Operates only on its own section of `improve-backlog.md`
- Returns an outcome: `{status: PASS|FAIL|BLOCKED|EXPLORED|HOUSEKEEPING, summary: str, signals_to_emit: list, budget_consumed: int}`
- Does **not** touch the lock, the preflight, the log, or other lanes' state

If the lane requires sub-strategy dispatch, the lane reads from
`improve/strategies/*.md` and picks one per its own rules:

- **example-apps** (agent-first maturity): run
  `python scripts/improve_example_probes.py --status` first; if
  `force=example-apps <strategy>` is non-empty, follow that strategy
  (`product_maturity` → `demo_fleet` → `journey_dogfood`). Else Tier 1–3
  gap discovery in `improve/lanes/example-apps.md`.
- **framework-ux** explore: `missing_contracts`, `edge_cases`, `contract_audit`,
  `framework_gap_analysis`, `finding_investigation`, `api_surface_audit`,
  `quality_intelligence_sweep`.
- **hm-convergence** when floors green: **`hyperpart_coherence`** drain if
  `python scripts/hm_coherence_queue.py --status` shows `queue>0` or PENDING
  `coherence_drain *` backlog rows, else **investigate** if `coherence.json`
  missing/stale (`improve/strategies/hyperpart_coherence.md`; force
  `/improve hm-convergence hyperpart_coherence [investigate|drain]`);
  **`gallery_probes`** — `python scripts/hm_gallery_probes.py --run` /
  `improve/strategies/gallery_probes.md`; **`dual_lock_expand`** —
  `python packages/hatchi-maxchi/tools/dual_lock_queue.py --top 5` /
  `improve/strategies/dual_lock_expand.md`; **`shadcn_parity`** —
  `python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only` /
  `improve/strategies/shadcn_parity.md`.

### Step 3: Apply outcome

1. **Increment explore budget** by `outcome.budget_consumed`
2. **Append log entry** to `improve-log.md`:
   ```
   ## Cycle N — YYYY-MM-DD — lane: {name} — outcome: {status}
   {outcome.summary}
   ```
3. **Emit signals**:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import emit
   for sig in outcome.signals_to_emit:
       emit(source="improve", kind=sig.kind, payload=sig.payload)
   ```
4. **Mark run**:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import mark_run
   mark_run(source="improve")
   ```
5. **Stamp capability coverage**: in `.claude/commands/improve/capability-map.md`,
   set **Last-exercised = N** and Status → `USED` for capabilities this cycle invoked.
   **Only the registry table** — never multi-paragraph cycle digests (those were oral
   history thrash; durable rules go in `improve/oral-history.md`). Capability-sweep may
   overwrite the short “Last sweep” block (≤5 one-liners). Commit the map when it changes.
6. **Commit** if the lane modified tracked files (the lane's playbook reports this). Use message format: `improve: cycle N {lane} — {summary}`
7. **Push (only if this cycle ships code to origin)** — mandatory gate, never ad-hoc:
   ```bash
   make preflight-surface
   make ship-surface
   make ci-fast                    # preferred; writes push stamp tier=0
   # or after surface-only: python scripts/push_gate.py record --tier surface
   make push-gate                  # min-tier 0; blocks throttle / CI wait / stale stamp
   # HM gallery/CSS/controller diff:
   #   python scripts/push_gate.py check --min-tier 0 --require-hm-green
   git push
   ```
   - **Refuse push** if `push_gate` exits non-zero (see remediation).
   - **Batch** micro gallery polish into one commit/push — do not land 5 pushes in 15 minutes.
   - **HM visual plane:** after push, wait sibling green before claiming cycle success on gallery work:
     `python scripts/hm_standalone_ci_status.py --prefer-completed`.

### Step 4: Release lock

```bash
rm -f .dazzle/improve.lock
```

### Step 5: Report

One-paragraph summary: lane chosen, outcome, what changed, budget remaining, next-cycle hint (which lane is likely next based on current backlog state).

### Step 6: Self-schedule (mandatory — keep the chain alive)

After Step 5 text is ready (lock already released). Port of CyFuture's one-shot
self-chain: each cycle arms the **next** fire rather than relying on a fixed
`/loop` ticker or a `recurring: true` improve job.

#### 6a. Decide

```bash
uv run python scripts/improve_schedule_next.py --result PASS
# or: --result FAIL
#     --deployed 1          # this cycle pushed code
#     --ci auto|green|red|in_progress|unavailable   # default auto via `gh`
#     --stop
```

JSON stdout is also written to `.dazzle/improve-schedule-state.json` (gitignored).
The script **probes main CI** (`gh run list --workflow ci.yml --branch main`) unless
`--ci` is set — do not invent a fixed 15–20m wait after every push.

#### 6b. Act

| `action` | What to do |
|----------|------------|
| `schedule` | Call **`scheduler_create`** with **all** fields from `scheduler_create` in the JSON (`interval`, `prompt`, `recurring`, **`fire_immediately`**, `durable`). Honor `fire_immediately: true` when present (CI green / repair / regression). |
| `stop` | Do **not** schedule. Note stop reason in the cycle log line below |

#### 6c. Log the chain

Append to this cycle's `improve-log.md` entry (or a trailing line):

```
**Next:** schedule {interval} fire_immediately={bool} job_id={id} reason={reason} ci={status}
# or: **Next:** STOP reason={reason}
```

#### Opportunistic intervals (encoded in the script)

Not a fixed ticker. Heat + **main CI badge** choose the delay:

| Situation | Interval | `fire_immediately` |
|-----------|----------|--------------------|
| REGRESSION / Dependabot / open bugs | `2m` | yes |
| CI **red** (repair soon) | `2m` | yes |
| CI **in_progress** after deploy | `15m` poll | no |
| CI **green** after **`--deployed 1`** + work | `45m` | no (full CI settle) |
| CI **green** + product residual / work | `20m` | no |
| Cycle failed | `15m` | no |
| Explore at cap + idle | `30m` inbox poll | no |
| Human/framework escalate (`--stop`) | — | — |

**Intent:** leave room for **complete main CI** between ship cycles. After a push,
wait ~45m (not 2m thrash). Product residual digs use ~20m spacing. Only
REGRESSION / red CI / inbox bugs stay hot.
#### Overlap hygiene

- Prefer **one** pending `/improve` one-shot at a time.
- Do **not** `scheduler_create(..., recurring=true)` for the main chain.
- If `scheduler_list` shows multiple competing `/improve` one-shots, delete extras and keep one.

#### Dead-man's switch (ops)

A **daily** durable recurring task should remain armed (create once if missing):

- Interval: `1d`, `recurring: true`, `durable: true`, `fire_immediately: false`
- Prompt: contents of `scripts/improve_watchdog_prompt.md`
- Purpose: if the self-chain dies (crash before Step 6, 7-day durable expiry), re-arm a one-shot

If no daily improve watchdog exists when you finish REPORT, create it once from that file.

`--status` and `--reset-budget` modes **skip** Step 6 (no cycle → no chain advance).

## Cross-lane signal contract

| Kind | Emitted by | Consumed by |
|------|-----------|-------------|
| `ux-component-shipped` | framework-ux | example-apps (re-verify), ux-converge (refresh contracts) |
| `ux-regression` | framework-ux | driver (priority pick) |
| `trial-friction` | trials / trial_signal_action | framework-ux (consider contract), driver (lane bias + rule 6 TR drain) |
| `gap-doc-written` | framework-ux | driver (informational; logged) |
| `app-fixed` | example-apps | framework-ux (re-walk if contract relates), trials (re-trial scenarios) |
| `convergence-clean` | ux-converge | example-apps (clear stale rows for that app) |
| `dazzle-updated` | (external — releases) | all lanes (mark affected rows) |
| `fix-deployed` | (external — /issues, /ship) | all lanes (mark affected rows) |

Lanes declare which kinds they emit and consume in their own files. Driver wires the consumption side.

## Hard rules

- **One lane per cycle.** Don't chain across lanes — the next /improve invocation handles that. Exception: Step 0c CI repair **is** the cycle (no second lane after a red-badge fix attempt).
- **Lock is mandatory.** No cycle without `.dazzle/improve.lock` held.
- **Always preflight.** Even for lanes whose strict checks don't seem relevant — preflight is the floor.
- **Always CI snapshot.** Step 0c every cycle; red completed badge → repair cycle, not explore.
- **Never push without push-gate.** `make push-gate` (or `python scripts/push_gate.py check …`) must exit 0 before `git push`. No ad-hoc pytest-only ships. Stamp is produced by `make ci-fast` / `make ci-core`.
- **No product push while main CI is in_progress.** Wait or self-schedule 15m; use `--repair` only for cimonitor.
- **Throttle product ships.** ≤4 main commits/hour and ≥8m gap (enforced by push_gate). Batch related fixes.
- **HM visual is a release plane.** Gallery CSS/JS/baseline changes require sibling `hatchi-maxchi` green before "done"; tags use `--require-hm-green`.
- **Commit every cycle that modifies tracked files.** Even failure cycles commit if they updated notes.
- **Explore budget is global.** A lane's explore phase always increments the shared counter. CI repair does not consume explore budget.
- **Self-schedule every full cycle.** Step 6 is mandatory after REPORT (except `--status` / `--reset-budget`). Use one-shots only; never `recurring: true` for the main chain.

## Status mode

When invoked with `--status`, skip the cycle and emit:

```
## /improve status — YYYY-MM-DD HH:MM

Budget: X/100
Lock: free | held by PID since TIME
CI badge (main): green | red (run #id) | in_progress | unavailable
GitHub inbox: heat=… consumer_bugs=N dependabot_ready=N (from improve_github_inbox.py)
Example probes: (paste output of python scripts/improve_example_probes.py --status)
Last cycle: N — lane: {name} — outcome: {status}

Lane:           Actionable    Last run     Likely next?
framework-ux    N             cycle M      yes/no
example-apps    N (+probe)    cycle M      yes/no
trials          N             cycle M      yes/no
ux-converge     N             cycle M      yes/no
test-suite      N             cycle M      yes/no
hm-convergence  N             cycle M      yes/no

Recent signals (last 24h):
- {kind} from {source} at TIME
```

Read-only — does not modify state, log, or lock. Status mode **does** run the
cheap `gh` CI snapshot so the badge line is live, and **does** run
`python scripts/improve_example_probes.py --status` so product/demo/journey
residual is visible without starting a cycle.

## Usage

```bash
/improve                                # one cycle + self-schedule next one-shot
/improve framework-ux                   # force a lane
/improve framework-ux contract_audit    # force lane + sub-strategy
/improve example-apps                   # force example-apps (OBSERVE runs probes)
/improve example-apps product_maturity  # anti-warehouse job desks
/improve example-apps demo_fleet        # #1626 felt bar / seeds / stills
/improve example-apps journey_dogfood   # bound stories + hubs
/improve example-apps distill           # Goal C coat residual (subtract)
/improve cimonitor                      # force CI snapshot (+ repair if red)
/improve github-prs                     # Dependabot / open PR processing
/improve consumer-issues                # downstream consumer bug intake
/improve --status                       # status report, no cycle (no schedule)
/improve --reset-budget                 # clear explore cap (no cycle)
# Prefer self-schedule (Step 6) over a fixed ticker. Alternatives:
#   /loop 6m /improve                   # session-bound fixed interval
# Daily dead-man: scripts/improve_watchdog_prompt.md (durable recurring 1d)
```

## Consolidation status

Consolidation is **complete**: the old /ux-cycle, /trial-cycle, /ux-converge, and standalone /improve skills have been removed; their playbook bodies now live in `improve/lanes/*.md`. `/improve` is the single entrypoint for all four lanes.

See `dev_docs/2026-04-25-improve-consolidation-design.md` for the rationale.
