"""No-op Observer/Executor backends for the investigator mission.

The investigator doesn't interact with a browser or any page — it only uses
tools. These backends satisfy the DazzleAgent contract with empty state and
an error on page-action execution (which should never happen if the system
prompt is doing its job).
"""

from __future__ import annotations

from dazzle.agent.models import ActionResult, AgentAction, PageState


class NullObserver:
    """Returns an empty PageState; navigate is a no-op."""

    async def observe(self) -> PageState:
        # PageState requires url: str and title: str; all other fields have defaults.
        return PageState(url="", title="")

    async def navigate(self, url: str) -> None:
        return None

    @property
    def current_url(self) -> str:
        return ""


class NullExecutor:
    """Rejects all page actions — the investigator is tool-only."""

    async def execute(self, action: AgentAction) -> ActionResult:
        return ActionResult(
            message=f"NullExecutor rejected {action.type}",
            error="investigator is tool-only; no page actions allowed",
        )
