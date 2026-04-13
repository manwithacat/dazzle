"""EXPECT-before-ACTION interlock.

The interlock is ~30 lines and eliminates the "agent drifted off protocol"
failure class. Before any tool call, the ledger must have a ``current_step``
with a non-empty ``expected`` field — i.e. the agent committed an expectation
prior to acting. If it didn't, the tool call is rejected.

v1 is the "reject on missing intent" variant. v2 will replace rejection with
"synthesize EXPECT via a second LLM call, then execute" (never blocks, costs
more tokens).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class InterlockError(RuntimeError):
    """Raised when an action is attempted without a recorded EXPECT."""


class _LedgerLike(Protocol):
    def current_step(self) -> Any: ...


def interlocked_tool_call(
    ledger: _LedgerLike,
    tool: Callable[..., Any],
    args: dict[str, Any],
) -> Any:
    """Gate a tool call on EXPECT-having-been-recorded.

    Raises ``InterlockError`` if the ledger's ``current_step`` is missing or
    has an empty ``expected`` field. Otherwise forwards ``**args`` to ``tool``
    and returns its result.
    """
    last_step = ledger.current_step()
    expected = getattr(last_step, "expected", None) if last_step is not None else None
    if not expected or not str(expected).strip():
        raise InterlockError(
            "Tool call rejected: no EXPECT recorded for this step. "
            "Emit `expect: <what you think will happen>` before calling tools."
        )
    return tool(**args)
