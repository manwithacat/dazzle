"""Lightweight parse worker for the fuzzer oracle's subprocess isolation (#1501).

This lives under ``dazzle.core`` — NOT ``dazzle.testing`` — on purpose. The fuzzer
oracle (`dazzle.testing.fuzzer.oracle.classify`) runs each parse in a spawned
subprocess for timeout/crash isolation. multiprocessing **spawn** re-imports the
module that defines the worker target; if that worker lived in
``dazzle.testing.fuzzer.oracle``, the child would run ``dazzle/testing/__init__.py``,
which eagerly imports the whole test toolkit (``e2e_runner`` → ``httpx`` →
``urllib`` → ``http.client`` …). Under a full-suite run that heavy/fragile chain
could fail to import in the child → the worker exited without a result → the parse
was mis-classified as CRASH (the #1501 flake).

Defining the worker here means the spawn child imports only ``dazzle.core`` (the
parser), never ``dazzle.testing``/httpx — immunising it against that whole class of
import-time pollution. Keep this module's imports to the parser only.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError

# Construct buckets reported back to the oracle (kept in sync with the AppSpec
# fragment attributes the fuzzer cares about).
_CONSTRUCT_ATTRS: tuple[str, ...] = (
    "entities",
    "surfaces",
    "workspaces",
    "experiences",
    "processes",
    "stories",
    "rhythms",
    "integrations",
    "apis",
    "ledgers",
    "webhooks",
    "approvals",
    "slas",
    "personas",
    "scenarios",
    "enums",
    "views",
)


def parse_worker(dsl: str, result_queue: multiprocessing.Queue) -> None:  # type: ignore[type-arg]
    """Parse *dsl* in this subprocess and put a result tuple on *result_queue*.

    Result shapes: ``("valid", None, None, constructs)`` |
    ``("parse_error", msg, "ParseError", [])`` | ``("crash", msg, type, [])``.
    """
    try:
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("fuzz.dsl"))
        constructs = [a for a in _CONSTRUCT_ATTRS if getattr(fragment, a, None)]
        result_queue.put(("valid", None, None, constructs))
    except ParseError as e:
        result_queue.put(("parse_error", str(e), "ParseError", []))
    except Exception as e:  # noqa: BLE001 — the whole point is to catch arbitrary crashes
        result_queue.put(("crash", str(e), type(e).__name__, []))
