---
name: qa-trial
description: Use when authoring or revising trial.toml scenarios for dazzle qa trial — puts an LLM in the shoes of a real business user evaluating a Dazzle app. Use when the user asks to "set up qa trials", "write a trial scenario", "evaluate this app as a user", or mentions qualitative/trial/business-user testing. Also use when a trial report is sparse or unhelpful — the scenario itself is usually the root cause.
---

# qa-trial

`dazzle qa trial` runs an LLM agent through a Dazzle app as a real business user evaluating whether to adopt the software. Output is a markdown report of friction observations plus a one-paragraph verdict. It's a **qualitative signal generator** — not pass/fail, not CI, not coverage.

This skill helps you author the `trial.toml` that drives the harness. A good scenario produces actionable friction; a weak scenario produces "the app looks fine" verdicts that are useless.

## When to invoke

- The user runs `dazzle qa trial` and the output is thin, generic, or clearly failing to probe their actual domain
- The user is setting up a new Dazzle project and wants qualitative evaluation
- The user asks about "business-user testing", "evaluation", "friction testing", or "qa trial"
- The user is writing `trial.toml` from scratch

## What the harness does (so you can aim scenarios at it)

The agent:
1. Logs in as `login_persona` via `/__test__/authenticate`
2. Reads `user_identity` + `business_context` as first-person context ("You are Sarah…")
3. Works through `tasks` in order, but is free to skip, reorder, or improvise
4. Calls `record_friction(category, severity, description, url, evidence)` when something makes them hesitate
5. Calls `submit_verdict` when `stop_when` is satisfied
6. The report post-processor clusters near-duplicates and sorts by category/severity

Friction categories the agent can record: `bug`, `missing`, `confusion`, `aesthetic`, `praise`, `other`. Severity: `low`, `medium`, `high`.

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

### Rule 4: Stop_when protects signal quality

```toml
stop_when = """
Stop when you've formed a rounded opinion on whether this software would
work for Sarah's business. Don't feel obliged to try every feature — the
aim is honest friction reporting, not exhaustive coverage.
"""
```

Without a stop condition, agents either exhaust their step budget doing nothing useful, or they keep re-exercising the same surface hoping to find more friction (surfaced as #812 — dedup made this tolerable but stop_when prevents it upstream).

### Rule 5: One persona per scenario — but multiple scenarios per trial.toml

A trial tests a single `(user_identity, tasks)` pair against a single persona. If your app has 3 personas (admin, agent, customer) and you want to evaluate for all of them, write 3 `[[scenario]]` blocks in one `trial.toml`. The CLI picks the first by default; pass `--scenario <name>` to select.

## Template

See `templates/trial-toml-template.toml` for a blank form to fill in. Copy it to your project root, edit, then:

```bash
dazzle qa trial --fresh-db
```

Use `--fresh-db` to avoid stale rows from prior trials corrupting the signal (#810).

## Reading the output

The report has three sections:

1. **Verdict** — the agent's bottom-line opinion. If it's clearly negative, take it seriously; the agent isn't adversarial, it's trying to evaluate the software fairly.
2. **Run metadata** — steps, duration, tokens. Low step counts (<10) often mean the agent gave up early; look for why.
3. **Friction observations** — grouped by category (bug > missing > confusion > aesthetic > praise), sorted by severity within each. Counts like `reported: ×4` mean dedup collapsed that many similar entries; treat those as stronger signals than one-offs.

## Framework-level vs app-level friction

Not all friction means the framework is broken:

- **Framework-level**: 403 page with no explanation of why, filter dropdown silently empty, 404 with no suggestion, alphabetized irrelevant list
- **App-level**: Missing CRUD surface, scope rule with wrong personas, copy that reads poorly

When triaging a trial report, ask: *would this friction exist in a well-crafted app of the same category?* If yes, it's a framework gap. If no, it's DSL authoring. Only framework-level friction should drive upstream issues.

## References

- `references/authoring-guide.md` — deeper patterns per domain (SaaS, finserv, healthcare, logistics)
- `templates/trial-toml-template.toml` — blank scenario form
- `examples/support_tickets/trial.toml` in the Dazzle repo — reference implementation
