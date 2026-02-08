"""
Dazzle Agent Framework.

A mission-driven agent that can be purposed for testing, discovery,
auditing, or any task that involves navigating and interacting with
a Dazzle application.

Usage:
    from dazzle.agent import DazzleAgent, Mission
    from dazzle.agent.observer import PlaywrightObserver, HttpObserver
    from dazzle.agent.executor import PlaywrightExecutor, HttpExecutor

    # Build a mission
    mission = Mission(
        name="my_task",
        system_prompt="You are an agent that...",
        max_steps=20,
    )

    # Create agent with observer + executor backends
    agent = DazzleAgent(observer, executor, model="claude-sonnet-4-20250514")
    transcript = await agent.run(mission)
"""

from .client_factory import create_persona_client
from .compiler import NarrativeCompiler, Proposal
from .core import AgentTool, DazzleAgent, Mission
from .emitter import DslEmitter, EmitContext, EmitResult, EntityFieldInfo
from .executor import Executor, HttpExecutor, PlaywrightExecutor
from .models import ActionResult, ActionType, AgentAction, Element, PageState, Step
from .observer import HttpObserver, Observer, PlaywrightObserver
from .transcript import AgentTranscript, Observation

__all__ = [
    # Core
    "DazzleAgent",
    "Mission",
    "AgentTool",
    # Protocols
    "Observer",
    "Executor",
    # Observer backends
    "PlaywrightObserver",
    "HttpObserver",
    # Executor backends
    "PlaywrightExecutor",
    "HttpExecutor",
    # Models
    "ActionType",
    "AgentAction",
    "ActionResult",
    "Element",
    "PageState",
    "Step",
    # Transcript
    "AgentTranscript",
    "Observation",
    # Compiler
    "NarrativeCompiler",
    "Proposal",
    # Emitter
    "DslEmitter",
    "EmitContext",
    "EmitResult",
    "EntityFieldInfo",
    # Client factory
    "create_persona_client",
]
