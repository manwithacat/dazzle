"""Qualitative trial mission.

A DazzleAgent mission that puts the LLM in the shoes of a real
business user evaluating a Dazzle app. Unlike the discovery /
entity_completeness / workflow_coherence missions — which ask
"does this component match the DSL?" — the trial mission asks
"does this software actually let me do my job?"

The output is a set of ``friction`` observations: things the user
tried to do, whether they worked, and what felt off. It is
explicitly *not* a pass/fail CI gate. Different runs will surface
different things. That's the point — qualitative signal for human
triage, not regression detection.

See docs/reference/implicitness-audit.md for the post-mortem that
motivated this, and trial.toml files under examples/*/ for the
per-app scenario definitions.
"""

from __future__ import annotations

from typing import Any

from ..core import AgentTool, Mission
from ..models import ActionType, AgentAction, Step

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


_TRIAL_SYSTEM_PROMPT = """\
You are a real business user evaluating a piece of software.

--- Who you are ---
{user_identity}

--- Your business context ---
{business_context}

--- What you are trying to do today ---
You have a short list of tasks you want to attempt. They're not a test
and there's no scoring — you're trialling the software to decide if
it's a fit:

{task_list}

--- How to work ---
Explore the app. Try to do each task as a real user would: follow the
obvious path, click the things that look clickable, give up if something
feels unreasonably hard. When you notice friction — anything that would
make you hesitate to recommend this to a colleague — call the
`record_friction` tool with the category, a description, and evidence
(the URL you were on, a DOM snippet, the action that failed).

You are NOT a QA engineer. You are NOT trying to exhaustively cover
every feature. You are a busy founder giving this software 5-10 minutes
of your time. Report honestly — if something felt great, that's also
worth noting (category="praise"). If something is missing you'd expect,
note it (category="missing"). If something is broken, note it
(category="bug"). If the UX confused you, note it (category="confusion").
Aesthetic observations are welcome (category="aesthetic") — we trust
the triager to file them appropriately.

--- Stopping ---
{stop_when}

You have a budget of **{max_steps} steps total**. Pace yourself — when
you've used ~75% of your steps (that is, step {wrap_up_at} of
{max_steps}), start wrapping up, whether or not you've finished all the
tasks. A short-but-honest verdict is far more useful than running out
of budget with nothing recorded. Call the `submit_verdict` tool with
a one-paragraph verdict before your budget runs out. (Note: use
`submit_verdict`, not the builtin `done` action — the builtin
doesn't capture your verdict.)

--- Important grounding ---
- Stay in character. If the DOM shows placeholder text like "Lorem
  ipsum" or a TODO, note it as friction — that's real friction for a
  real evaluator.
- Do NOT invent features. If you can't find a way to do something,
  that's itself the signal. Record it as friction.
- **Don't record the same friction twice.** If you've already flagged
  that /dashboard 404s, don't re-record it on a retry — move on to a
  different task or call `submit_verdict`. A real user wouldn't file
  the same complaint four times.
- Evidence matters. Every friction record should have a URL and enough
  detail that a human could reproduce what you saw. Vague complaints
  get filtered out at triage time.
- The server is pre-authenticated as your persona — you do NOT need to
  log in. Start at the home page and follow your nose.
"""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _make_record_friction_tool(transcript_sink: dict[str, list[dict[str, Any]]]) -> AgentTool:
    """Tool: ``record_friction``.

    Captures a single friction observation into the mission's
    transcript_sink. The DazzleAgent harness reads transcript_sink
    after the run and promotes entries to ``Observation`` records
    on the transcript.
    """

    _CATEGORIES = ("bug", "missing", "confusion", "aesthetic", "praise", "other")

    def record_friction(
        category: str,
        description: str,
        url: str = "",
        evidence: str = "",
        severity: str = "medium",
    ) -> dict[str, Any]:
        cat = category if category in _CATEGORIES else "other"
        entry = {
            "category": cat,
            "description": description,
            "url": url,
            "evidence": evidence,
            "severity": severity,
        }
        transcript_sink.setdefault("friction", []).append(entry)
        return {
            "recorded": True,
            "count_so_far": len(transcript_sink["friction"]),
            "note": "Keep exploring. Call `submit_verdict` when ready to wrap up.",
        }

    return AgentTool(
        name="record_friction",
        description=(
            "Record a single friction observation from your trial. Call this "
            "every time you notice something worth flagging — good or bad. "
            "You can call it many times per run."
        ),
        schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "One of: bug, missing, confusion, aesthetic, praise, other.",
                    "enum": list(_CATEGORIES),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "First-person description of what you observed and how it "
                        "felt. 1-3 sentences."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "The URL you were on when this happened.",
                },
                "evidence": {
                    "type": "string",
                    "description": (
                        "Concrete evidence: DOM snippet, button label, error text, "
                        "or the precise sequence you tried. A human should be able "
                        "to reproduce what you saw."
                    ),
                },
                "severity": {
                    "type": "string",
                    "description": "low | medium | high — your gut feel.",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": ["category", "description"],
        },
        handler=record_friction,
    )


def _make_submit_verdict_tool(transcript_sink: dict[str, list[dict[str, Any]]]) -> AgentTool:
    """Tool: ``submit_verdict`` — wrap up the trial with a verdict.

    Named ``submit_verdict`` (not ``done``) specifically to avoid
    colliding with the builtin ``done`` page action. During the first
    two trials the agent called ``done`` expecting our handler, but
    the SDK routed the tool_use to the builtin page action (which
    takes no verdict arg), so our handler never fired and the verdict
    was never captured. The core framework does warn about the
    collision — we now heed that warning by picking a unique name.
    """

    def submit_verdict(verdict: str = "") -> dict[str, Any]:
        transcript_sink["verdict"] = [{"text": verdict}]
        return {"ended": True}

    return AgentTool(
        name="submit_verdict",
        description=(
            "End the trial by submitting your verdict. Provide a one-paragraph "
            "verdict from your business user's perspective: would you recommend "
            "this software to a colleague? What would need to change? This is "
            "how you end the trial — do NOT use the `done` page action, which "
            "won't capture your verdict."
        ),
        schema={
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "description": ("One-paragraph verdict. Honest — positive and negative."),
                },
            },
            "required": ["verdict"],
        },
        handler=submit_verdict,
    )


# ---------------------------------------------------------------------------
# Completion criterion
# ---------------------------------------------------------------------------


def _trial_completion(action: AgentAction, history: list[Step]) -> bool:
    """Stop when the agent calls the ``done`` tool.

    The agent can also be stopped by the ``max_steps`` budget (handled
    by the harness). There is no stagnation detector — a trial run
    that stops pressing buttons and just thinks is still productive
    qualitative data.
    """
    if action.type == ActionType.DONE:
        return True
    # The `submit_verdict` mission tool shows up as a tool action;
    # the handler has already stashed the verdict, and the framework
    # records this as a mission-tool call. Treat it as a stop signal.
    if action.type == ActionType.TOOL and action.target == "submit_verdict":
        return True
    return False


# ---------------------------------------------------------------------------
# Scenario parsing
# ---------------------------------------------------------------------------


def _format_task_list(tasks: list[str]) -> str:
    if not tasks:
        return "(no tasks declared — explore freely)"
    return "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(tasks))


# ---------------------------------------------------------------------------
# Mission builder
# ---------------------------------------------------------------------------


def build_trial_mission(
    scenario: dict[str, Any],
    base_url: str,
    transcript_sink: dict[str, list[dict[str, Any]]],
    max_steps: int | None = None,
    token_budget: int = 200_000,
) -> Mission:
    """Build a :class:`Mission` for a qualitative trial.

    Args:
        scenario: Parsed scenario dict from ``trial.toml``. Expected
            keys: ``name``, ``login_persona``, ``user_identity``,
            ``business_context``, ``tasks``, ``stop_when``,
            ``max_steps`` (optional), ``time_budget_seconds`` (optional).
        base_url: Base URL of the running application (e.g.
            ``http://localhost:3969``).
        transcript_sink: Mutable dict the tools write into. The harness
            reads ``transcript_sink["friction"]`` and
            ``transcript_sink["verdict"]`` after the run.
        max_steps: Override the scenario's ``max_steps`` budget.
        token_budget: LLM token budget for the run.
    """
    user_identity = scenario.get("user_identity", "").strip()
    business_context = scenario.get("business_context", "").strip()
    tasks = scenario.get("tasks", [])
    stop_when = scenario.get("stop_when", "").strip() or (
        "When you feel you've explored enough to form an opinion, call "
        "`submit_verdict` with a verdict."
    )

    effective_max_steps = max_steps or int(scenario.get("max_steps", 35))
    # Wrap-up at 60% — trials 1-3 all ran out of budget at 75% wrap-up
    # because exploration + recording takes more steps than the LLM
    # estimates. Budget safety matters more than full coverage; the
    # fallback verdict synthesiser picks up the slack either way.
    wrap_up_at = max(1, int(effective_max_steps * 0.60))

    system_prompt = _TRIAL_SYSTEM_PROMPT.format(
        user_identity=user_identity or "(not specified)",
        business_context=business_context or "(not specified)",
        task_list=_format_task_list(tasks),
        stop_when=stop_when,
        max_steps=effective_max_steps,
        wrap_up_at=wrap_up_at,
    )

    return Mission(
        name=f"trial:{scenario.get('name', 'unnamed')}",
        system_prompt=system_prompt,
        tools=[
            _make_record_friction_tool(transcript_sink),
            _make_submit_verdict_tool(transcript_sink),
        ],
        completion_criteria=_trial_completion,
        max_steps=effective_max_steps,
        token_budget=token_budget,
        start_url=f"{base_url}/app",
        terminal_tools=["submit_verdict"],
        context={
            "mode": "trial",
            "persona": scenario.get("login_persona", ""),
            "scenario": scenario.get("name", "unnamed"),
        },
    )
