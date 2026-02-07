"""
Shared data models for the Dazzle Agent framework.

These models are used by both the agent core and the observer/executor
backends. They define the interface between observation and action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# =============================================================================
# Action Types
# =============================================================================


class ActionType(StrEnum):
    """Types of actions the agent can take on a page."""

    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    ASSERT = "assert"
    DONE = "done"
    TOOL = "tool"  # Invoke a mission-specific tool


# =============================================================================
# Page State
# =============================================================================


@dataclass
class Element:
    """A UI element on the page."""

    tag: str
    text: str
    selector: str
    role: str | None = None
    rect: dict[str, float] | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class PageState:
    """Captured state of a page for agent observation."""

    url: str
    title: str
    clickables: list[Element] = field(default_factory=list)
    inputs: list[Element] = field(default_factory=list)
    visible_text: str = ""
    screenshot_b64: str | None = None
    dazzle_attributes: dict[str, list[str]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_prompt(self, include_screenshot: bool = True) -> str:
        """Convert page state to a prompt for the LLM."""
        lines = [
            "## Current Page State",
            f"URL: {self.url}",
            f"Title: {self.title}",
            "",
            "### Clickable Elements",
        ]

        for i, el in enumerate(self.clickables[:20]):
            text_preview = el.text[:50] + "..." if len(el.text) > 50 else el.text
            lines.append(f'  [{i}] {el.tag}: "{text_preview}" (selector: {el.selector})')

        lines.append("")
        lines.append("### Input Fields")

        for i, el in enumerate(self.inputs[:15]):
            placeholder = el.attributes.get("placeholder", "")
            lines.append(f"  [{i}] {el.tag}: {placeholder} (selector: {el.selector})")

        if self.dazzle_attributes:
            lines.append("")
            lines.append("### Dazzle Semantic Context")
            for attr, values in self.dazzle_attributes.items():
                lines.append(f"  {attr}: {', '.join(values[:5])}")

        if self.visible_text:
            lines.append("")
            lines.append("### Visible Text (excerpt)")
            lines.append(self.visible_text[:500])

        return "\n".join(lines)


# =============================================================================
# Actions
# =============================================================================


@dataclass
class AgentAction:
    """An action decided by the agent."""

    type: ActionType
    target: str | None = None  # Selector, URL, or tool name
    value: str | None = None  # Text to type, option to select, tool args JSON
    reasoning: str = ""
    success: bool = True  # For DONE action


@dataclass
class ActionResult:
    """Result of executing an action."""

    message: str
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


# =============================================================================
# Steps
# =============================================================================


@dataclass
class Step:
    """A single step in the agent's execution."""

    state: PageState
    action: AgentAction
    result: ActionResult
    step_number: int = 0
    duration_ms: float = 0.0
    prompt_text: str = ""
    response_text: str = ""
    tokens_used: int = 0
