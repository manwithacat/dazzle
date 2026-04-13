"""Pass 1 deterministic story walker (v1 fitness task 12).

The walker drives an external async executor (e.g. Playwright) through
each action step declared on a story. It is deterministic — no LLM calls
— and records intent + observation against a sync fitness ledger (see
Task 4).

The walker itself is async because it must await the executor; the
ledger calls (``record_intent``, ``observe_step``) are sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class WalkResult:
    story_id: str
    persona: str
    steps_executed: int
    errors: list[str] = field(default_factory=list)


class _ExecutorLike(Protocol):
    async def goto(self, url: str) -> None: ...
    async def click(self, selector: str) -> None: ...
    async def fill(self, selector: str, value: str) -> None: ...


class _LedgerLike(Protocol):
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...
    def observe_step(self, step: int, observed_ui: str) -> None: ...


async def walk_story(story: Any, executor: _ExecutorLike, ledger: _LedgerLike) -> WalkResult:
    """Drive the executor through a story's declared action steps.

    Each step has the shape::

        {"action": "goto|click|fill",
         "url"|"selector": ...,
         "expect": "...",
         "value": <only for fill>}

    The walker is deterministic — no LLM calls. It records the intent
    (EXPECT + action description) against the ledger, runs the action,
    then records the observation.
    """
    result = WalkResult(
        story_id=getattr(story, "id", "?"),
        persona=getattr(story, "persona", "?"),
        steps_executed=0,
    )

    for idx, step_def in enumerate(getattr(story, "steps", []), start=1):
        action = step_def.get("action", "").lower()
        expect = step_def.get("expect", f"step {idx} runs")
        action_desc = f"{action} {step_def}"

        ledger.record_intent(step=idx, expect=expect, action_desc=action_desc)
        result.steps_executed += 1

        try:
            if action == "goto":
                await executor.goto(step_def["url"])
            elif action == "click":
                await executor.click(step_def["selector"])
            elif action == "fill":
                await executor.fill(step_def["selector"], step_def["value"])
            else:
                raise ValueError(f"unknown action {action!r}")
            observed = f"{action} ok"
        except Exception as e:  # noqa: BLE001 — surfacing the error into the ledger is the point
            observed = f"error: {e}"
            result.errors.append(f"step {idx}: {e}")

        ledger.observe_step(step=idx, observed_ui=observed)

    return result
