"""Pass 1 mission builder — deterministic story walker.

Wraps :func:`dazzle.fitness.walker.walk_story` in a shape compatible with
the existing ``DazzleAgent`` mission protocol. Pass 1 is deterministic,
so the "agent" here is a thin loop rather than a reasoning model.
"""

from __future__ import annotations

from typing import Any

from dazzle.fitness.walker import WalkResult, walk_story


async def run_pass1_for_stories(stories: list[Any], executor: Any, ledger: Any) -> list[WalkResult]:
    """Run the deterministic walker across a list of stories, in order."""
    results: list[WalkResult] = []
    for s in stories:
        results.append(await walk_story(story=s, executor=executor, ledger=ledger))
    return results
