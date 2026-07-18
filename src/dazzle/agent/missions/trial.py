"""Qualitative trial mission (gen-2).

A DazzleAgent mission that puts the LLM in the shoes of a real
business user evaluating a Dazzle app. Unlike the discovery /
entity_completeness / workflow_coherence missions — which ask
"does this component match the DSL?" — the trial mission asks
"does this software actually let me do my job?"

Gen-2 (2026-07) raises ambition for current-generation models:
longer careful-pilot sessions, recovery-before-give-up, optional
adoption criteria scoring, and richer friction metadata. Still
explicitly *not* a pass/fail CI gate.

See docs/reference/qa-trial-gen2.md, trial.toml under examples/*/,
and .agents/skills/qa-trial/SKILL.md.
"""

from __future__ import annotations

from typing import Any

from ..core import AgentTool, Mission
from ..models import ActionType, AgentAction, Step

# Defaults sized for current-gen models (Grok 4.x / Claude Sonnet-class).
# Older scenarios may still pin lower max_steps in trial.toml.
_DEFAULT_MAX_STEPS = 50
_DEFAULT_TOKEN_BUDGET = 400_000
# Wrap later than gen-1 (60%) — current models can finish tasks *and* verdict.
_WRAP_UP_FRACTION = 0.80

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SIGNING_FLOW_GUIDANCE = """

--- Signing flow (API-only)

This trial has signing tools available. When a task involves signing a
document, complete it via the signing tools ONLY:

  1. read_inbox — discover documents awaiting signature
  2. open_signing_link(entity, id, token) — fetch the signing page;
     the response shows the document text so you can read it
  3. sign_document(authority_confirmed=true) — accept and sign
     OR decline_signing(reason="...") — refuse

Do NOT use the navigate or click tools to visit the signing page. The
signing flow is API-driven from your perspective; the URL in the inbox
listing is for the tool to use, not for you to navigate to. If
open_signing_link returns successfully, the page is fully loaded —
go straight to sign_document or decline_signing.
"""

_TRIAL_SYSTEM_PROMPT = """\
You are a real business user evaluating a piece of software for a
serious pilot decision — not a five-minute drive-by.

--- Who you are ---
{user_identity}

--- Your business context ---
{business_context}

--- What you are trying to do today ---
You have a list of goals to attempt. They are not a test script and
there is no pass/fail score. Work them as a careful evaluator deciding
whether this software is fit for your business:

{task_list}
{criteria_block}{phases_block}
--- How to work ---
Explore like a competent professional:

1. **Orient** — land, read the primary workspace, form a first impression.
2. **Core jobs** — attempt each task using the obvious path first.
3. **Recover once** — if something fails or confuses you, try one
   alternate path (search, different nav label, filter, back, refresh).
   Then record friction and move on. Do not thrash the same dead end.
4. **Stress lightly** — when time allows: empty/filter miss, a deep
   link, an error or permission edge if you hit one naturally.
5. **Decide** — call `submit_verdict` with an honest recommendation.

You are NOT a QA engineer writing a test plan. You ARE more thorough
than a distracted founder with 5 minutes. Budget about 25–40 minutes
of careful evaluation energy.

When something would make you hesitate to recommend this to a colleague,
call `record_friction` with category, severity, description, URL, and
evidence. Prefer specific, reproducible observations.

Categories: bug | missing | confusion | aesthetic | praise | other.
Severity: low | medium | high.
Optional friction fields:
- blocks_pilot: true if this alone would block a pilot/go-live week.
- framework_vs_app: "framework" if this would bite any well-authored app
  of this class; "app" if it is this app's content/DSL; "unclear" otherwise.

--- Stopping ---
{stop_when}

You have a budget of **{max_steps} steps total**. Pace yourself — when
you've used ~80% of your steps (that is, step {wrap_up_at} of
{max_steps}), start wrapping up, whether or not every task is perfect.
A complete verdict with scored criteria beats a silent max_steps exit.
Call `submit_verdict` before the budget ends (not the builtin `done`).

--- Important grounding ---
- Stay in character. Placeholder text, TODOs, and fake demo names are
  real friction for a real evaluator — record them.
- Do NOT invent features. If you can't find a way, that *is* the signal.
- **Don't record the same friction twice.** One entry per distinct issue.
- Evidence matters: URL + enough detail to reproduce. Vague complaints die
  at triage.
- Distinguish product friction from fixture noise when you can (e.g.
  empty DB vs broken UI). Prefer product signal.
- The server is pre-authenticated as your persona — you do NOT need to
  log in. Start where you landed and follow your nose.
"""


def _format_task_list(tasks: list[str]) -> str:
    if not tasks:
        return "(no tasks declared — explore freely)"
    return "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(tasks))


def _format_criteria_block(criteria: list[Any]) -> str:
    """Render optional adoption_criteria into the system prompt."""
    items = [str(c).strip() for c in (criteria or []) if str(c).strip()]
    if not items:
        return ""
    body = "\n".join(f"  - {c}" for c in items)
    return f"""
--- Adoption criteria (score these in submit_verdict) ---
For each criterion below, decide pass / partial / fail and note why
in criteria_scores. These drive pilot decisions more than vibes alone:

{body}
"""


def _format_phases_block(phases: list[Any]) -> str:
    """Render optional multi-phase guidance."""
    items = [str(p).strip() for p in (phases or []) if str(p).strip()]
    if not items:
        return ""
    body = "\n".join(f"  {i + 1}. {p}" for i, p in enumerate(items))
    return f"""
--- Suggested phases (use as a guide, not a rigid script) ---
{body}
"""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_CATEGORIES = ("bug", "missing", "confusion", "aesthetic", "praise", "other")
_FRAMEWORK_VS_APP = ("framework", "app", "unclear")
_CRITERION_SCORES = ("pass", "partial", "fail", "untested")


def _make_record_friction_tool(transcript_sink: dict[str, list[dict[str, Any]]]) -> AgentTool:
    """Tool: ``record_friction`` — one observation into the transcript sink."""

    def record_friction(
        category: str,
        description: str,
        url: str = "",
        evidence: str = "",
        severity: str = "medium",
        blocks_pilot: bool = False,
        framework_vs_app: str = "unclear",
    ) -> dict[str, Any]:
        cat = category if category in _CATEGORIES else "other"
        fva = framework_vs_app if framework_vs_app in _FRAMEWORK_VS_APP else "unclear"
        entry: dict[str, Any] = {
            "category": cat,
            "description": description,
            "url": url,
            "evidence": evidence,
            "severity": severity if severity in ("low", "medium", "high") else "medium",
            "blocks_pilot": bool(blocks_pilot),
            "framework_vs_app": fva,
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
            "You can call it many times per run. Prefer URL + reproducible "
            "evidence; set blocks_pilot=true only for true pilot blockers."
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
                        "felt. 1-4 sentences; be specific."
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
                "blocks_pilot": {
                    "type": "boolean",
                    "description": (
                        "true if this issue alone would block a pilot or go-live week."
                    ),
                },
                "framework_vs_app": {
                    "type": "string",
                    "description": (
                        "framework | app | unclear — would this bite any well-authored "
                        "app of this class, or is it this app's content?"
                    ),
                    "enum": list(_FRAMEWORK_VS_APP),
                },
            },
            "required": ["category", "description"],
        },
        handler=record_friction,
    )


# Negative-sentiment tokens that indicate a verdict contains real
# complaints. When `submit_verdict` is called with any of these present
# AND `record_friction` was never called, the tool rejects and nudges.
_NEGATIVE_VERDICT_TOKENS: frozenset[str] = frozenset(
    {
        "broken",
        "cannot",
        "can't",
        "404",
        "unusable",
        "fail",
        "failed",
        "failing",
        "missing",
        "nowhere",
        "dead",
        "doesn't work",
        "does not work",
        "non-functional",
        "nonfunctional",
        "deeply broken",
        "inferior",
        "blocker",
        "unresponsive",
        "timeout",
        "times out",
    }
)


def _normalize_criteria_scores(raw: Any) -> list[dict[str, str]]:
    """Accept list[{criterion,score,note}] or dict{criterion: score|note}."""
    if not raw:
        return []
    out: list[dict[str, str]] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                score = str(v.get("score", v.get("result", "untested"))).lower()
                note = str(v.get("note", v.get("why", "")) or "")
            else:
                score = str(v).lower()
                note = ""
            if score not in _CRITERION_SCORES:
                score = "untested"
            out.append({"criterion": str(k), "score": score, "note": note})
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            criterion = str(
                item.get("criterion") or item.get("name") or item.get("id") or ""
            ).strip()
            if not criterion:
                continue
            score = str(item.get("score", item.get("result", "untested"))).lower()
            if score not in _CRITERION_SCORES:
                score = "untested"
            note = str(item.get("note", item.get("why", "")) or "")
            out.append({"criterion": criterion, "score": score, "note": note})
    return out


def _make_submit_verdict_tool(
    transcript_sink: dict[str, list[dict[str, Any]]],
    *,
    expected_criteria: list[str] | None = None,
) -> AgentTool:
    """Tool: ``submit_verdict`` — wrap up with verdict + optional scores."""

    def submit_verdict(
        verdict: str = "",
        recommend: str = "unclear",
        criteria_scores: Any = None,
        pilot_blockers_summary: str = "",
    ) -> dict[str, Any]:
        verdict_lower = verdict.lower()
        has_negative = any(tok in verdict_lower for tok in _NEGATIVE_VERDICT_TOKENS)
        friction_count = len(transcript_sink.get("friction", []))

        if has_negative and friction_count == 0:
            return {
                "rejected": True,
                "reason": (
                    "Your verdict describes concrete failures (e.g. 'broken', "
                    "'404', 'missing', 'unusable') but you have not called "
                    "`record_friction` once. Before you submit the verdict, "
                    "record each specific failure as its own friction entry "
                    "with a URL and evidence snippet, so a human triager can "
                    "reproduce what you saw. Then call `submit_verdict` again."
                ),
                "friction_count": friction_count,
                "hint": (
                    "Look at your verdict paragraph — every distinct complaint "
                    "should be its own `record_friction` call. Example: '404 on "
                    "/app/task' is one entry; 'no Create button on Task Board' "
                    "is a separate entry."
                ),
            }

        rec = (recommend or "unclear").strip().lower()
        if rec not in ("yes", "no", "conditional", "unclear"):
            rec = "unclear"

        scores = _normalize_criteria_scores(criteria_scores)
        # If scenario declared criteria and agent skipped scoring, leave empty
        # for the report (do not invent scores). Soft hint only when empty.
        soft_hint = ""
        if expected_criteria and not scores:
            soft_hint = (
                "Note: this scenario declared adoption_criteria but none were "
                "scored. Consider re-submitting with criteria_scores if you can."
            )

        transcript_sink["verdict"] = [
            {
                "text": verdict,
                "recommend": rec,
                "criteria_scores": scores,
                "pilot_blockers_summary": (pilot_blockers_summary or "").strip(),
            }
        ]
        result: dict[str, Any] = {"ended": True, "recommend": rec, "criteria_count": len(scores)}
        if soft_hint:
            result["hint"] = soft_hint
        return result

    return AgentTool(
        name="submit_verdict",
        description=(
            "End the trial by submitting your verdict. Provide an honest "
            "paragraph from your business user's perspective: would you pilot "
            "or recommend this software? What must change first? "
            "Also set recommend=yes|no|conditional|unclear. If the scenario "
            "listed adoption criteria, fill criteria_scores (pass|partial|fail|"
            "untested per criterion). Do NOT use the `done` page action. "
            "If your verdict describes concrete failures but you haven't "
            "called `record_friction` for them, this tool will reject."
        ),
        schema={
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "description": (
                        "1-3 paragraph verdict. Honest — positive and negative. "
                        "Lead with the pilot decision."
                    ),
                },
                "recommend": {
                    "type": "string",
                    "description": "yes | no | conditional | unclear",
                    "enum": ["yes", "no", "conditional", "unclear"],
                },
                "criteria_scores": {
                    "description": (
                        "Optional. List of {criterion, score, note} or a map of "
                        "criterion → score. score ∈ pass|partial|fail|untested."
                    ),
                },
                "pilot_blockers_summary": {
                    "type": "string",
                    "description": (
                        "Optional one-liner of issues that would block a pilot, or empty if none."
                    ),
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
    """Stop when the agent calls submit_verdict (or builtin done)."""
    if action.type == ActionType.DONE:
        return True
    if action.type == ActionType.TOOL and action.target == "submit_verdict":
        return True
    return False


# ---------------------------------------------------------------------------
# Mission builder
# ---------------------------------------------------------------------------


def build_trial_mission(
    scenario: dict[str, Any],
    base_url: str,
    transcript_sink: dict[str, list[dict[str, Any]]],
    max_steps: int | None = None,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    signing_tools: list[AgentTool] | None = None,
) -> Mission:
    """Build a :class:`Mission` for a qualitative trial (gen-2 defaults).

    Args:
        scenario: Parsed scenario dict from ``trial.toml``. Expected
            keys: ``name``, ``login_persona``, ``user_identity``,
            ``business_context``, ``tasks``, ``stop_when``,
            ``max_steps`` (optional), ``time_budget_seconds`` (optional),
            ``token_budget`` (optional), ``adoption_criteria`` (optional
            list[str]), ``phases`` (optional list[str]).
        base_url: Base URL of the running application.
        transcript_sink: Mutable dict tools write into
            (``friction``, ``verdict``).
        max_steps: Override the scenario's ``max_steps`` budget.
        token_budget: Default LLM token budget; overridden by
            scenario ``token_budget`` when set.
        signing_tools: Optional signing harness tools.
    """
    user_identity = scenario.get("user_identity", "").strip()
    business_context = scenario.get("business_context", "").strip()
    tasks = scenario.get("tasks", [])
    stop_when = scenario.get("stop_when", "").strip() or (
        "When you feel you've explored enough to form an opinion, call "
        "`submit_verdict` with a verdict and recommend=yes|no|conditional."
    )

    starting_url_raw = (scenario.get("starting_url") or "").strip()
    if starting_url_raw:
        if starting_url_raw.startswith(("http://", "https://")):
            effective_start_url = starting_url_raw
        else:
            effective_start_url = f"{base_url.rstrip('/')}/{starting_url_raw.lstrip('/')}"
    else:
        effective_start_url = f"{base_url}/app"

    if max_steps is not None:
        effective_max_steps = int(max_steps)
    elif scenario.get("max_steps") is not None:
        effective_max_steps = int(scenario["max_steps"])
    else:
        effective_max_steps = _DEFAULT_MAX_STEPS

    try:
        effective_token_budget = int(scenario.get("token_budget") or token_budget)
    except (TypeError, ValueError):
        effective_token_budget = token_budget

    wrap_up_at = max(1, int(effective_max_steps * _WRAP_UP_FRACTION))

    raw_criteria = scenario.get("adoption_criteria") or scenario.get("criteria") or []
    if isinstance(raw_criteria, str):
        criteria_list = [raw_criteria]
    else:
        criteria_list = [str(c) for c in raw_criteria]

    raw_phases = scenario.get("phases") or []
    if isinstance(raw_phases, str):
        phases_list = [raw_phases]
    else:
        phases_list = [str(p) for p in raw_phases]

    system_prompt = _TRIAL_SYSTEM_PROMPT.format(
        user_identity=user_identity or "(not specified)",
        business_context=business_context or "(not specified)",
        task_list=_format_task_list(tasks),
        criteria_block=_format_criteria_block(criteria_list),
        phases_block=_format_phases_block(phases_list),
        stop_when=stop_when,
        max_steps=effective_max_steps,
        wrap_up_at=wrap_up_at,
    )

    if signing_tools:
        system_prompt = system_prompt + _SIGNING_FLOW_GUIDANCE

    base_tools = [
        _make_record_friction_tool(transcript_sink),
        _make_submit_verdict_tool(transcript_sink, expected_criteria=criteria_list or None),
    ]
    if signing_tools:
        base_tools.extend(signing_tools)

    return Mission(
        name=f"trial:{scenario.get('name', 'unnamed')}",
        system_prompt=system_prompt,
        tools=base_tools,
        completion_criteria=_trial_completion,
        max_steps=effective_max_steps,
        token_budget=effective_token_budget,
        start_url=effective_start_url,
        terminal_tools=["submit_verdict"],
        context={
            "mode": "trial",
            "persona": scenario.get("login_persona", ""),
            "scenario": scenario.get("name", "unnamed"),
            "gen": 2,
        },
    )
