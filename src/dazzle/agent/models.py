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


class ObserverMode(StrEnum):
    """How the observer captures page state."""

    DOM = "dom"
    ACCESSIBILITY = "accessibility"


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
    console_messages: list[dict[str, Any]] = field(default_factory=list)
    network_errors: list[dict[str, Any]] = field(default_factory=list)
    accessibility_tree: list[dict[str, Any]] = field(default_factory=list)

    def to_prompt(self, include_screenshot: bool = True) -> str:
        """Convert page state to a prompt for the LLM."""
        lines = [
            "## Current Page State",
            f"URL: {self.url}",
            f"Title: {self.title}",
            "",
        ]

        if self.accessibility_tree:
            lines.append("### Interactive Elements")
            for i, node in enumerate(self.accessibility_tree[:30]):
                role = node.get("role", "unknown")
                name = node.get("name", "")
                selector = node.get("selector", "")
                name_preview = name[:50] + "..." if len(name) > 50 else name
                lines.append(f'  [{i}] {role}: "{name_preview}" (selector: {selector})')
        else:
            lines.append("### Clickable Elements")
            for i, el in enumerate(self.clickables[:20]):
                text_preview = el.text[:50] + "..." if len(el.text) > 50 else el.text
                # Include href/hx-get/hx-post so the LLM can reason about targets
                attr_parts = []
                for key in ("href", "hx-get", "hx-post"):
                    val = el.attributes.get(key)
                    if val:
                        attr_parts.append(f"{key}={val}")
                attr_info = f" [{', '.join(attr_parts)}]" if attr_parts else ""
                lines.append(
                    f'  [{i}] {el.tag}: "{text_preview}"{attr_info} (selector: {el.selector})'
                )

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

        if self.console_messages:
            lines.append("")
            lines.append("### Console Messages")
            for msg in self.console_messages[:10]:
                level = msg.get("level", "error")
                text = msg.get("text", "")[:200]
                lines.append(f"  [{level}] {text}")

        if self.network_errors:
            lines.append("")
            lines.append("### Network Errors")
            for err in self.network_errors[:10]:
                method = err.get("method", "GET")
                url = err.get("url", "")[:100]
                status = err.get("status", 0)
                lines.append(f"  {method} {url} -> {status}")

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
