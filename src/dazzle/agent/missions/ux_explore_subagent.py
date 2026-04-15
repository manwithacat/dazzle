"""Mission prompt templates for cycle 198's subagent-driven explore.

Cycle 198 replaces DazzleAgent-driven explore (v0.55.4) with Claude Code
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

Only ``MISSING_CONTRACTS`` is implemented in cycle 198. ``EDGE_CASES`` is
scaffolded with a stub that raises NotImplementedError; it'll be filled in
a later cycle once the MISSING_CONTRACTS path is proven at scale.
"""

from __future__ import annotations

from typing import Literal

Strategy = Literal["missing_contracts", "edge_cases"]


def build_subagent_prompt(
    *,
    strategy: Strategy,
    example_name: str,
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
) -> str:
    """Build the mission prompt for a subagent-driven explore run.

    Args:
        strategy: "missing_contracts" (the primary cycle 198 mode) or
            "edge_cases" (scaffolded but not yet implemented).
        example_name: The Dazzle example app name (e.g. "contact_manager").
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

    Returns:
        The full prompt string ready to pass to the Task tool as its
        ``prompt`` field.

    Raises:
        NotImplementedError: if ``strategy == "edge_cases"`` — that
            strategy is scaffolded but deliberately left unimplemented
            for cycle 198.
    """
    if strategy == "edge_cases":
        raise NotImplementedError(
            "edge_cases strategy is not implemented in cycle 198; use missing_contracts"
        )

    hard_ceiling = int(budget_calls * 1.5)
    existing_list = "\n".join(f"- {name}" for name in existing_components)

    strategy_section = _MISSING_CONTRACTS_STRATEGY_SECTION

    return _PROMPT_TEMPLATE.format(
        example_name=example_name,
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
        strategy_section=strategy_section,
    )


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


_PROMPT_TEMPLATE = """\
# Mission: explore {example_name} as {persona_label}

You are exploring the Dazzle `{example_name}` example app as the
`{persona_id}` persona ({persona_label}). Your mission is described
under "Mission-specific guidance" below.

This run is part of a /ux-cycle explore cycle. The cognitive work happens
inside this Claude Code session and is billed to the Max Pro subscription,
so don't over-optimise for token count — quality of findings beats
quantity of calls.

## How to drive the browser

The `{example_name}` app is already running at `{site_url}` and your
session is already logged in as `{persona_id}`. DO NOT try to start
servers or log in.

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
