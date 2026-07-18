---
name: qa-trial
description: Use when authoring or revising trial.toml scenarios for dazzle qa trial — puts an LLM in the shoes of a real business user evaluating a Dazzle app. Use when the user asks to "set up qa trials", "write a trial scenario", "evaluate this app as a user", or mentions qualitative/trial/business-user testing. Also use when a trial report is sparse or unhelpful — the scenario itself is usually the root cause. Gen-2: longer careful-pilot sessions, adoption_criteria scoring, phases.
---

# qa-trial (gen-2)

`dazzle qa trial` runs an LLM agent through a Dazzle app as a real business user deciding whether to **pilot** the software. Output is a markdown report: recommend decision, optional adoption-criteria scores, friction observations, verdict. It's a **qualitative signal generator** — not pass/fail, not CI, not coverage.

**Gen-2 posture (current models):** careful 25–40 minute pilot evaluator, one recovery attempt before recording failure, wrap-up at ~80% of step budget, default 50 steps / 400k tokens. See `docs/reference/qa-trial-gen2.md`.

This skill helps you author the `trial.toml` that drives the harness. A good scenario produces scorable pilot criteria + actionable friction; a weak scenario produces "the app looks fine" with empty criteria.

## When to invoke

- The user runs `dazzle qa trial` and the output is thin, generic, or clearly failing to probe their actual domain
- The user is setting up a new Dazzle project and wants qualitative evaluation
- The user asks about "business-user testing", "evaluation", "friction testing", or "qa trial"
- The user is writing `trial.toml` from scratch

## What the harness does (so you can aim scenarios at it)

The agent:
1. Logs in as `login_persona` via `/__test__/authenticate`
2. Reads `user_identity` + `business_context` as first-person context ("You are Sarah…")
3. Optionally follows `phases` (orient → core jobs → stress → decide)
4. Works through `tasks` as goals (free to reorder; try one recovery path on failure)
5. Calls `record_friction(...)` with optional `blocks_pilot`, `framework_vs_app`
6. Calls `submit_verdict(verdict, recommend, criteria_scores, pilot_blockers_summary)` when `stop_when` is satisfied
7. Report clusters near-duplicates; renders Recommend + Adoption criteria when present

Friction categories: `bug`, `missing`, `confusion`, `aesthetic`, `praise`, `other`. Severity: `low` | `medium` | `high`.

## Authoring rules

### Rule 1: Identity is specific, not generic

Bad:

```toml
user_identity = "You are a user evaluating a task tracker."
```

Good:

```toml
user_identity = """
You are Sarah, founder of a 50-customer B2B SaaS. You handle escalations
while Alex handles first-line support. Your current setup is Gmail plus a
shared Notion doc. You're trialling this today to decide whether to switch.
You're logged in as the "manager" account — same role you'd use in prod.
"""
```

Specific identities produce specific friction. The LLM needs to *inhabit* the role, not just read it. Name, company size, existing tooling, the decision at stake — all of it matters.

### Rule 2: Business context anchors urgency

The LLM needs numbers and stakes. "You see about 10-20 support requests a week, about a third are critical" tells the agent what pressure they're under and what to look for. "You care about SLA" tells them what questions to ask the UI.

### Rule 3: Tasks are goals, not click-paths

Bad:

```toml
tasks = [
    "Click 'New Ticket'",
    "Fill in the title field",
    "Click Submit",
]
```

This is a Playwright script, not a trial.

Good:

```toml
tasks = [
    "One customer just called about a 2-day-old ticket that hasn't been resolved. Can the software help you find overdue tickets — not by scrolling manually but with a filter or sort that makes urgency obvious?",
]
```

The LLM should have to *figure out* how to do the thing. That's where friction surfaces. If you tell them every step, you'll get a report that says "I did the thing, it worked".

### Rule 4: Stop_when + adoption_criteria protect signal quality

```toml
adoption_criteria = [
    "Urgency of open work is visible without spreadsheet mental math",
    "Would run a two-week pilot as-is or with minor fixes",
]

stop_when = """
Stop when you can score the adoption criteria and form a pilot decision
(yes / conditional / no). Call submit_verdict with recommend=… and
criteria_scores (pass|partial|fail|untested) for each criterion.
"""
```

Without stop_when, agents thrash the same surface (#812). Without
`adoption_criteria`, gen-2 still works but you get vibes instead of a
scorable pilot gate. Prefer criteria that a human founder would actually
use to say yes/no to a two-week pilot.

### Rule 4b: Budgets for current models

| Scenario type | max_steps | token_budget |
|---------------|-----------|--------------|
| Signing micro-path | 20–30 | 200k–300k |
| Hub / workspace evaluation (gen-2 default) | 50–60 | 400k |
| Deep multi-region stress | 70–80 | 500k |

Do **not** pin gen-1 “25 steps / busy founder” budgets unless the scenario
is intentionally tiny. Current models waste less on thrash and use the
extra budget for recovery + criteria scoring.

### Rule 5: One persona per scenario — but multiple scenarios per trial.toml

A trial tests a single `(user_identity, tasks)` pair against a single persona. If your app has 3 personas (admin, agent, customer) and you want to evaluate for all of them, write 3 `[[scenario]]` blocks in one `trial.toml`. The CLI picks the first by default; pass `--scenario <name>` to select.

### Rule 6: `starting_url` when the trial targets one region (v0.60.2+)

Default landing is `/app` — fine for "can the persona navigate the whole app" trials. Useless for "can the persona read this chart" trials, because the agent burns its step budget scrolling past a dozen regions before ever reaching the one you wanted tested.

```toml
# Scenario targeting a specific chart region
starting_url = "/app/workspaces/command_center#region-alerts_timeseries"
```

The path is relative to the app's base URL. Fragment anchors work because workspace region cards emit `id="region-<name>"` — the browser auto-scrolls on load so the persona lands with the target visible. For discoverability trials leave `starting_url` unset and let the persona navigate from `/app`; for focused feature trials set it and save 10+ steps of scroll noise.

Rule of thumb: if your tasks start with "Find the X chart…", you probably want `starting_url` to drop the persona at X. Otherwise you're testing page layout, not the chart.

### Rule 7: `signing_token_state` for expired-link scenarios (v0.82.42+)

Apps with `signable: true` entities get the signing harness automatically (ephemeral cert, mock inbox, `read_inbox`/`open_signing_link`/`sign_document` tools). By default the seeded token is fresh and signable. To trial the *expired-link experience* — what a signer sees when they open a two-week-old email — set:

```toml
signing_token_state = "expired"   # default: "fresh"
```

The harness then mints an already-expired token, the signing page renders the real "Invalid or expired link" response, and the post-trial verifier expects the document row to stay untouched (any sign/decline attempt must be rejected). Without this key, a `*_token_expired` scenario silently tests the happy path: the persona gets a valid token and the expiry narrative is pure fiction (TR-51).

### Rule 8: `signing_token_state = "already_signed"` for re-open scenarios (TR-50)

If the persona's identity says they *already signed* and they are re-opening the
link for a copy or confirmation, set:

```toml
signing_token_state = "already_signed"   # default: "fresh"
```

The harness seeds a normal token, then immediately signs the row through the
production `POST /api/sign/...` path (stub signature PNG). Re-open hits the real
#1571 completion page + signed-copy download instead of a still-pending form.
Without this key, `*_already_signed` scenarios are pure fiction: the fixture is
still `status=sent`, so observations become fixture artifacts (TR-50).

Mutually exclusive with `signing_validator_reject` and with
`signing_token_state = "expired"`.

## Template

See `templates/trial-toml-template.toml` for a blank form to fill in. Copy it to your project root, edit, then:

```bash
dazzle qa trial --fresh-db
```

Use `--fresh-db` to avoid stale rows from prior trials corrupting the signal (#810).

## Reading the output

1. **Recommend** — `yes` / `conditional` / `no` / `unclear` (gen-2).
2. **Verdict** — prose decision. Negative framing is serious; the agent is not adversarial by default.
3. **Adoption criteria** — pass/partial/fail/untested per criterion when declared.
4. **Run metadata** — steps, duration, tokens. Very low step counts still mean early abort.
5. **Friction** — by category/severity; `blocks_pilot` and `scope: framework|app` when set; `reported: ×N` is dedup strength.

## Framework-level vs app-level friction

Not all friction means the framework is broken:

- **Framework-level**: 403 page with no explanation of why, filter dropdown silently empty, 404 with no suggestion, alphabetized irrelevant list
- **App-level**: Missing CRUD surface, scope rule with wrong personas, copy that reads poorly

When triaging a trial report, ask: *would this friction exist in a well-crafted app of the same category?* If yes, it's a framework gap. If no, it's DSL authoring. Only framework-level friction should drive upstream issues.

## References

- `docs/reference/qa-trial-gen2.md` — harness posture and schema
- `references/authoring-guide.md` — deeper patterns per domain (SaaS, finserv, healthcare, logistics)
- `templates/trial-toml-template.toml` — blank gen-2 scenario form
- `examples/support_tickets/trial.toml` — flagship gen-2 reference (`manager_evaluation`)
