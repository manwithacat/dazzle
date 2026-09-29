# Strategy: codeql (driver-level CodeQL / code-scanning gate)

Poll GitHub code-scanning (CodeQL) for **open** alerts on this repo and
remediate real findings. Complements the CI badge gate: green tests can still
leave high-severity CodeQL open on Security → Code scanning.

**Driver step:** Step 0c2 in `improve.md` (after CI snapshot; only claims the
cycle when open actionable alerts exist, or when forced).
**Force path:** `/improve codeql`
**budget_consumed:** `0` — security / verification, not exploration.

## Snapshot (always after Step 0c continues — cheap)

```bash
# Open alerts (paginate if needed; default page is enough for small queues)
gh api "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/code-scanning/alerts" \
  --jq '[.[] | select(.state=="open") | {
    number, rule: .rule.id,
    severity: .rule.severity,
    security: .rule.security_severity_level,
    path: .most_recent_instance.location.path,
    line: .most_recent_instance.location.start_line,
    msg: .most_recent_instance.message.text,
    url: .html_url
  }]'
```

| Snapshot | Driver action |
|----------|---------------|
| **≥1 open alert** with `rule.severity` ∈ {`error`} **or** `security_severity_level` ∈ {`critical`,`high`} **or** any open alert when forced via `/improve codeql` | **This cycle is CodeQL repair** (unless Step 0c already claimed CI repair). Fix root causes → commit → push. Log `lane: codeql`. |
| **Open alerts only `warning`/`note` and not forced** | Log `codeql: N open (low)` and **continue** the product cycle — do not burn the whole cycle unless the queue has been idle ≥ **10** cycles since last `lane: codeql` (then drain one finding). |
| **Zero open alerts** | Log `codeql: clean`; continue. |
| **`gh` / API unavailable** | Log `codeql: unavailable (<error>)`; continue (do not invent a clean Security tab). |

**Hard preemption (when table says repair):** open high/error CodeQL outranks REGRESSION, self-audit, capability-sweep, TR drain, and explore for **this** cycle — same spirit as a red CI badge. **CI red still outranks CodeQL** (fix the badge first; Security can wait one cycle).

## Remediate mode

1. **List** open alerts (table: number / rule / path:line / severity / url).
2. **Triage each** (or the top few if many — prefer `error` + `high` security first):
   - **True positive** → fix the code (sanitize, validate, barrier, model pack row if a real guard already exists). Prefer fixing once at the source over dismissing.
   - **False positive / by-design** → dismiss via API only with a concrete reason:

     ```bash
     gh api -X PATCH "repos/OWNER/REPO/code-scanning/alerts/NNN" \
       -f state=dismissed -f dismissed_reason=false_positive \
       -f dismissed_comment='…why safe…'
     ```

     Allowed `dismissed_reason`: `false_positive` | `won't_fix` | `used_in_tests` | `acceptable_risk`.
   - **Reusable sanitizer already in tree** (e.g. `is_safe_redirect_path`) → prefer extending the **CodeQL model pack** (`.github/codeql/extensions/…`, bump + publish + pin) over per-alert dismissals. See CHANGELOG history for the dazzle-python-models pack.
3. **Do not** dismiss high severity without fixing or a written by-design rationale in the dismiss comment.
4. **Tests** — add/adjust unit tests that lock the control (path containment, regex end forms, etc.).
5. **Commit** — `fix(security): …` or `improve: cycle N codeql — …`.
6. **Push** when this session already has main push authority (same as cimonitor).
7. **Log** — append improve-log:

```
## Cycle N — YYYY-MM-DD — lane: codeql — outcome: PASS|PARTIAL|BLOCKED

- **preflight:** PASS
- **ci:** green | in_progress | … (from 0c)
- **codeql:** open alerts → remediate
- **alerts:** #NNN rule path:line — fixed|dismissed|deferred
- **fix:** …
- **budget_consumed:** 0 → explore budget **X/100**
- **next:** re-poll Security tab after CodeQL workflow runs; else normal lane pick
```

Outcomes:
- `PASS` — no remaining open high/error alerts after this cycle (or clean).
- `PARTIAL` — some fixed; others deferred (document why).
- `BLOCKED` — no `gh` auth, cannot push, or needs human product intent.

## Observe mode (clean / low-only / unavailable)

One line in the cycle log is enough:

```
- **codeql:** clean | N open low (deferred) | unavailable (gh: …)
```

## Hard rules

- **Never invent a green Security tab** when the API failed.
- **Fix truth over dismiss.** Dismiss only false-positive / by-design / tests / accepted risk.
- **CI red owns the cycle first** (Step 0c). CodeQL runs only when 0c does not claim repair.
- **Model pack over mass dismiss** for framework barriers that CodeQL does not see.
- Keep remediation scoped: one cluster of related alerts per cycle when the queue is large.
