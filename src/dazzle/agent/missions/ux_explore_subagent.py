"""Mission prompt templates for the subagent-driven explore substrate.

Cycle 198 replaced DazzleAgent-driven explore (v0.55.4) with Claude Code
Task-tool subagents driving a stateless Playwright helper via Bash. The
cognitive work happens inside the subagent's conversation turn and is
billed to the Claude Code host subscription (Max Pro 20) instead of the
metered Anthropic SDK path.

This module is the *prompt template* the subagent consumes. It's a sibling
to ``ux_explore.py`` (the DazzleAgent-era mission builder) and uses the
same parameter names where possible, so future readers can compare
substrates.

The template structure was validated empirically during the cycle 198
spike (2026-04-15): one subagent run against contact_manager with persona
user produced 4 proposals + 4 observations in 188s at ~60k subsidised
tokens — compared to 0 proposals across 11 DazzleAgent runs in cycle 197's
verification sweep.

Five strategies are supported (closes #789):

- ``missing_contracts`` — scan for recurring interaction patterns that
  should have a ux-architect contract but don't yet.
- ``edge_cases`` — probe friction, broken-state recovery, empty/error/
  boundary-state handling, nav dead-ends. Skews toward observations.
- ``persona_journey`` — walk the DSL persona's declared ``goals`` end
  to end and record friction points.
- ``cross_persona_consistency`` — check whether the same entity renders
  consistently across personas and whether visibility rules match the
  DSL's access declarations.
- ``regression_hunt`` — walk every workspace region and flag anything
  that differs from the assistant's expected behaviour (useful after a
  framework upgrade).
- ``create_flow_audit`` — for every creatable entity, attempt a create
  with valid + invalid data and record which flows silently fail.

In 0.57.10 the template was generalised from Dazzle's own ``examples/``
apps to any Dazzle project — the "Dazzle example app" wording was
replaced with a variable ``{app_descriptor}`` so downstream consumers
can brand the prompt for their own project (#789).
"""

from __future__ import annotations

from typing import Literal

Strategy = Literal[
    "missing_contracts",
    "edge_cases",
    "persona_journey",
    "cross_persona_consistency",
    "regression_hunt",
    "create_flow_audit",
]


def build_subagent_prompt(
    *,
    strategy: Strategy,
    app_name: str,
    persona_id: str,
    persona_label: str,
    site_url: str,
    helper_command: str,
    state_dir: str,
    findings_path: str,
    existing_components: list[str],
    start_route: str,
    budget_calls: int = 20,
    min_findings: int = 3,
    app_descriptor: str | None = None,
    persona_goals: list[str] | None = None,
) -> str:
    """Build the mission prompt for a subagent-driven explore run.

    Args:
        strategy: One of the six supported strategies (see module
            docstring).
        app_name: The Dazzle app name (e.g. "contact_manager" or
            "aegismark" for a downstream project).
        persona_id: DSL persona id the subagent walks as.
        persona_label: Human-readable label from ``PersonaSpec.label``.
        site_url: ``AppConnection.site_url`` from ModeRunner.
        helper_command: Shell command to invoke the Playwright helper,
            e.g. ``"python -m dazzle.agent.playwright_helper"``.
        state_dir: Per-run state directory path that the subagent passes
            via ``--state-dir`` on every helper call.
        findings_path: Absolute path to the findings JSON the subagent
            writes proposals/observations to.
        existing_components: Component names that already have
            ux-architect contracts (the subagent should NOT propose these).
        start_route: Expected landing route for the persona (e.g.
            ``"/app/workspaces/contacts"``). Included in the prompt so the
            subagent knows where to start observing.
        budget_calls: Target Bash helper-call count. The subagent is told
            this is a target, with a hard ceiling at 1.5x.
        min_findings: Minimum proposals+observations before the subagent
            is allowed to stop early.
        app_descriptor: Sentence describing the app (e.g. "Dazzle example
            app"). Defaults to ``f"Dazzle app `{app_name}`"`` for
            backward-compatible wording.
        persona_goals: DSL-declared persona goals, used by the
            ``persona_journey`` strategy to seed the walk. Optional for
            other strategies.

    Returns:
        The full prompt string ready to pass to the Task tool as its
        ``prompt`` field.

    Raises:
        ValueError: if ``strategy`` is not a recognised literal.
    """
    strategy_section = _STRATEGY_SECTIONS.get(strategy)
    if strategy_section is None:
        raise ValueError(
            f"unknown strategy {strategy!r}; expected one of: "
            f"{', '.join(_STRATEGY_SECTIONS.keys())}"
        )

    hard_ceiling = int(budget_calls * 1.5)
    existing_list = "\n".join(f"- {name}" for name in existing_components)

    if app_descriptor is None:
        app_descriptor = f"Dazzle app `{app_name}`"

    # Strategies that consume persona goals template them into their
    # prompt section themselves; pass a pre-formatted string in.
    goals_formatted = _format_persona_goals(persona_goals or [])

    return _PROMPT_TEMPLATE.format(
        app_name=app_name,
        app_descriptor=app_descriptor,
        persona_id=persona_id,
        persona_label=persona_label,
        site_url=site_url,
        helper_command=helper_command,
        state_dir=state_dir,
        findings_path=findings_path,
        existing_list=existing_list or "(none)",
        start_route=start_route,
        budget_calls=budget_calls,
        hard_ceiling=hard_ceiling,
        min_findings=min_findings,
        strategy_section=strategy_section.format(
            persona_id=persona_id,
            persona_goals=goals_formatted,
        ),
    )


def _format_persona_goals(goals: list[str]) -> str:
    if not goals:
        return "(no goals declared in the DSL for this persona)"
    return "\n".join(f"- {goal}" for goal in goals)


_MISSING_CONTRACTS_STRATEGY_SECTION = """\
You are looking for UX component patterns that should have a ux-architect
contract but don't yet. A UX component is a *recurring interaction pattern
with its own internal state and behavior*. Examples of things you might
find without contracts:

- tree views, kanban boards, inline editors, command palettes, side drawers,
  stepper wizards, breadcrumbs, activity timelines, tag inputs, anything
  else that looks like a reusable interaction pattern

You are NOT looking for: trivial UI (buttons, links, headings) or
composition patterns the framework governs at the layout level (cards in a
dashboard grid).

For each pattern you find, write a proposal with a specific selector hint
and a description that would let another engineer (or another subagent)
reproduce what you saw.

If you don't find anything without a contract, that's a legitimate finding
— record it as an observation with severity=minor."""


_EDGE_CASES_STRATEGY_SECTION = """\
You are probing for UX friction and edge-case defects — places where the
app does the wrong thing, misleads the user, or silently drops into a
broken state. The previous cycles have already catalogued the recurring
component patterns; your job is to stress-test what's there.

Concrete things to try:

- **Empty states** — visit list/table/dashboard pages that have zero rows
  for this persona. Is the empty state helpful? Does it suggest a next
  action? Is there a call-to-action that actually works?
- **Error states** — submit a form with invalid/missing input. Does the
  validation surface inline, in a toast, or silently? Does the form
  recover its state, or do you lose what you typed?
- **Boundary conditions** — very long text, zero/negative numbers, the
  past/future dates, huge file uploads. Look for layout overflow, silent
  truncation, and unhandled errors.
- **Dead-end navigation** — click every sidebar link, every breadcrumb,
  every "open full page" affordance. Find links that 403/404, lead to
  blank pages, or loop back on themselves. Find links the persona can
  see but can't use.
- **Affordance mismatches** — a button that looks clickable but does
  nothing; a hover state on an element that's read-only; a loading
  spinner that never resolves; a toast that claims success after a
  silent failure.
- **Copy/persona mismatches** — text that reads as if a different persona
  is viewing ("welcome, administrator" when you're a customer).
- **State leaks** — navigate away mid-action, come back, and see stale
  state (draft drafts, in-flight HTMX requests, open drawers).

Record each finding as an **observation**, not a proposal. The shape is
the same; just use the observation schema below. Set ``severity`` to:

- ``concerning`` if data loss, broken auth/permissions, or a hard-stuck
  state is possible
- ``notable`` for missing affordances or copy/behaviour mismatches
- ``minor`` for polish issues (wording, alignment, single-character
  typos, ambiguous labels)

Proposals are still accepted but should be rare — only if you stumble
across a genuinely uncontracted component pattern along the way.

If the app holds up against everything you try, that's itself a finding:
record a single ``minor`` observation saying the persona's reachable
surface had no edge-case defects in this cycle."""


_PERSONA_JOURNEY_STRATEGY_SECTION = """\
You are walking {persona_id}'s declared goals end-to-end. Your job is to
check whether the app actually lets the persona accomplish each goal —
without surprise, without dead-ends, and without fighting the UI.

The DSL declares these goals for this persona:

{persona_goals}

For each goal, attempt the following sequence:

1. **Locate** — find the entry point the persona would plausibly use.
   Look for obvious affordances (sidebar, dashboard cards, call-to-action
   buttons). Don't fall back to typing URLs unless an affordance is
   clearly expected but missing.
2. **Walk** — click through the flow end-to-end. Fill forms with
   reasonable data, submit, follow any redirects, observe the confirmation.
3. **Verify** — confirm the result is visible somewhere the persona
   would naturally check (their workspace, an activity feed, a
   detail page).

Record an observation for each goal you walk, even if it succeeds. Include:

- The path you actually took (sidebar → workspace → form → submit)
- Whether the UI made the next step obvious at each checkpoint
- Whether the confirmation pattern matches the persona's expectations
- Friction points (forced field order, unclear wording, missing defaults,
  extra clicks that don't match the goal intent)

Severity:
- ``concerning`` — goal is impossible or requires a workaround the persona
  shouldn't have to know
- ``notable`` — goal works but with friction that reduces trust or
  adoption
- ``minor`` — goal works cleanly, with nits

Proposals are rare for this strategy — only record one if the journey
exposes a missing UX component contract (e.g. a custom flow that should
reuse an existing pattern)."""


_CROSS_PERSONA_CONSISTENCY_STRATEGY_SECTION = """\
You are checking that the same underlying entity renders consistently
across personas, and that visibility/permission rules actually match the
DSL's declared access rules.

You are only logged in as one persona ({persona_id}) for this run, so the
check is: record what *this* persona sees on shared entities, and flag
anything that contradicts what the DSL declares (access rules, scope
filters, workspace membership).

For each workspace region or list surface you encounter:

1. **Note the row count** — does it match what the persona's scope rule
   should permit? (You don't have the other persona's view — you're
   checking for obvious over- or under-visibility, not comparing
   directly.)
2. **Note visible columns** — does the persona see columns marked
   "hidden" for their role? Does a column that should be visible appear
   blank or missing?
3. **Note action affordances** — create/edit/delete buttons that are
   visible but shouldn't be (based on DSL permit: rules), or missing
   when they should be present.
4. **Note linked navigation** — sidebar entries and workspace links that
   this persona can see. Follow each one: does it lead to a 403/404 or
   to content this persona shouldn't have?

Each finding is an observation with severity:

- ``concerning`` — persona sees data they shouldn't, or can take an
  action the access rules forbid
- ``notable`` — UI reveals something the persona can't act on (sidebar
  link that 403s, workspace link with no entries), wastes their time
- ``minor`` — labels or affordances that don't match the persona's role
  (copy, iconography, empty-state messaging)

Proposals are rare for this strategy. Only propose if you notice a
component pattern that exists specifically to handle cross-persona
differences (persona-conditional renderer, persona-specific sidebar
widget) that should have a contract."""


_REGRESSION_HUNT_STRATEGY_SECTION = """\
You are walking every major workspace region and flagging anything that
looks surprising, broken, or inconsistent with how the framework should
behave. This strategy is useful after a framework upgrade, a theme
change, or a big refactor: you're hunting for things that *used to
work* and no longer do.

You don't have a baseline to compare against directly. You're doing a
fast, broad sweep and relying on your own judgement about what Dazzle
apps are supposed to look like. Bias toward "this looks off" rather
than "this is definitely broken."

For each workspace region:

1. **Visit the region** via its sidebar entry or dashboard card.
2. **Check the basics** — does the region render without console errors
   or blank placeholders? Do expected affordances (create button, filter
   bar, search) appear? Does the column set look right for the entity?
3. **Open one row** — follow the first row's detail link. Does the
   detail page load? Do the tabs/actions look complete? Do related
   entities render?
4. **Return** — use the back/breadcrumb. Does scroll position or
   filter state persist?

Record observations for anything that looks off. Severity:

- ``concerning`` — a region fails to render, throws a 500, or loses
  state unexpectedly
- ``notable`` — visible regressions from usual Dazzle behaviour
  (missing filters, broken breadcrumbs, unstyled elements, obvious
  layout problems)
- ``minor`` — polish that's likely a regression (spacing, iconography,
  alignment) but could also be an intentional recent change

Proposals are rare for this strategy. The priority is coverage — walk
as many regions as your budget allows."""


_CREATE_FLOW_AUDIT_STRATEGY_SECTION = """\
You are auditing the app's create flows. For each entity that this
persona can create, attempt a create with both valid and invalid data,
and record how the flow behaves.

For each creatable entity you can reach:

1. **Find the create affordance** — workspace "New" button, sidebar
   "+ Add", dashboard call-to-action. Note where you had to look.
2. **Valid create** — fill the form with reasonable data and submit.
   Observe:
   - Does the form surface sensible defaults?
   - Does validation fire inline before submit?
   - On success, where does the UI take you? (Detail page, list with
     the new row highlighted, toast + stay?)
   - Does the new record actually appear in the list afterwards?
3. **Invalid create** — submit with a required field empty, an invalid
   email, a negative number, an absurdly long string. Observe:
   - Does validation surface inline, in a toast, or silently on submit?
   - Does the form preserve the user's input, or reset it?
   - Is the error message actionable?
4. **Cancel** — abandon a half-filled form mid-way (close drawer,
   navigate away). Is there a confirm prompt? Does it persist a draft?

Record an observation for each entity's create flow, covering both the
valid and invalid paths. Severity:

- ``concerning`` — create silently fails, validation is missing for
  required fields, the form loses user input on validation errors,
  the new record doesn't appear in the list
- ``notable`` — missing affordance, unclear validation messages, no
  success feedback, confusing post-create navigation
- ``minor`` — defaults, copy, iconography, form field order

Proposals are rare for this strategy — only if you see a pattern that
should be a shared create-flow component (multi-step wizard, upload
drop-zone)."""


_STRATEGY_SECTIONS: dict[Strategy, str] = {
    "missing_contracts": _MISSING_CONTRACTS_STRATEGY_SECTION,
    "edge_cases": _EDGE_CASES_STRATEGY_SECTION,
    "persona_journey": _PERSONA_JOURNEY_STRATEGY_SECTION,
    "cross_persona_consistency": _CROSS_PERSONA_CONSISTENCY_STRATEGY_SECTION,
    "regression_hunt": _REGRESSION_HUNT_STRATEGY_SECTION,
    "create_flow_audit": _CREATE_FLOW_AUDIT_STRATEGY_SECTION,
}


_PROMPT_TEMPLATE = """\
# Mission: explore {app_name} as {persona_label}

You are exploring the {app_descriptor} as the `{persona_id}` persona
({persona_label}). Your mission is described under "Mission-specific
guidance" below.

This run is part of an explore cycle. The cognitive work happens inside
this Claude Code session and is billed to the Max Pro subscription, so
don't over-optimise for token count — quality of findings beats quantity
of calls.

## How to drive the browser

The app is already running at `{site_url}` and your session is already
logged in as `{persona_id}`. DO NOT try to start servers or log in.

A stateless Playwright helper is your driver. Invoke it via the Bash tool:

- Observe the current page:
  `{helper_command} --state-dir {state_dir} observe`

- Navigate to a path:
  `{helper_command} --state-dir {state_dir} navigate /app/contacts`

- Click a selector:
  `{helper_command} --state-dir {state_dir} click 'button.create-contact'`

- Type into an input:
  `{helper_command} --state-dir {state_dir} type '#field-name' 'example'`

- Wait for a selector to appear:
  `{helper_command} --state-dir {state_dir} wait '.loading-done'`

Each call is a one-shot subprocess (~2-3s overhead) that loads your
session from `{state_dir}/state.json`, performs the action, saves the
state back, and exits. Your session cookie persists across calls — you do
not need to re-login between actions.

Each call returns a single JSON object on stdout. On success: the action
outputs (url, title, interactive_elements, visible_text, etc.). On error:
`{{"error": "...", "error_type": "..."}}`. A click or navigate includes
`state_changed: bool` so you can tell whether your action actually did
anything.

## Starting point

Start with an `observe` call to see where you are. You should be on the
`{start_route}` page (that's the persona's default workspace). Then
explore from there.

Prefer id/href/text-matcher selectors (`a[href="/app/contact/1"]`,
`button:has-text('Create')`) over brittle positional ones
(`:nth-child(3)`).

## Mission-specific guidance

{strategy_section}

## Existing component contracts (do NOT propose these)

These components already have ux-architect contracts; don't record them
as proposals even if you see them:

{existing_list}

## What to record

Your findings live in `{findings_path}`. Read it to see its current state
(it starts as `{{"proposals": [], "observations": []}}`) and use the Write
tool to update it as you work. Don't batch up findings for the end — write
them to the file as soon as you're confident about them.

**Proposals** — UX components that look like they need a ux-architect
contract. Shape:

```json
{{
  "component_name": "kebab-case-name",
  "description": "One paragraph explaining what it does, the state model, the interaction grammar, and why it deserves a contract.",
  "observed_on_page": "/path/where/you/saw/it",
  "selector_hint": "a CSS selector pointing at the component root",
  "persona_id": "{persona_id}"
}}
```

**Observations** — anything else worth recording: cross-surface data
inconsistencies, friction you ran into, missing affordances, edge cases
that surprised you. Shape:

```json
{{
  "page": "/path",
  "note": "What you saw and why it matters",
  "severity": "minor | notable | concerning",
  "persona_id": "{persona_id}"
}}
```

## Budget

- Aim for {budget_calls} or fewer Bash helper calls total.
- Stop when you have {min_findings}+ meaningful findings (proposals +
  observations combined) OR when you've explored the main pages and don't
  see anything new.
- Do NOT exceed {hard_ceiling} Bash helper calls. If you hit that ceiling
  without enough findings, record an observation explaining why
  ("hit budget, explored X pages, nothing notable") and stop.

## Report back

A concise summary:
1. How many Bash helper calls you made
2. Which pages you visited
3. Summary of findings (proposal + observation counts with one line each)
4. Mission assessment: successful / partially successful / blocked
5. Friction notes — anything you'd change about the helper or mission
   prompt if you were to run this again

The findings file is the durable record; your report is the
interpretation. Both matter.

Begin.
"""
