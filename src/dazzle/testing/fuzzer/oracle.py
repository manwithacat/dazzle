"""Classification oracle for the DSL parser fuzzer.

Runs parse_dsl() on generated input and classifies the result:
- VALID: parsed successfully
- CLEAN_ERROR: ParseError with actionable message
- BAD_ERROR: ParseError with unhelpful message
- HANG: timeout exceeded
- CRASH: unhandled exception (not ParseError)
"""

from __future__ import annotations

import multiprocessing
import queue
from dataclasses import dataclass, field
from enum import Enum

# #1501: the parse worker lives under dazzle.core (NOT dazzle.testing) so the
# spawn child re-imports only the parser, never dazzle/testing/__init__.py →
# httpx → http.client (a heavy/fragile chain that could fail to import in the
# child under a full-suite run, mis-classifying valid DSL as CRASH).
from dazzle.core._fuzz_parse_worker import parse_worker


class Classification(Enum):
    VALID = "valid"
    CLEAN_ERROR = "clean_error"
    BAD_ERROR = "bad_error"
    HANG = "hang"
    CRASH = "crash"


@dataclass
class FuzzResult:
    dsl_input: str
    classification: Classification
    error_message: str | None = None
    error_type: str | None = None
    constructs_hit: list[str] = field(default_factory=list)


def classify(dsl: str, timeout_seconds: float = 5.0) -> FuzzResult:
    """Classify a DSL input by running it through the parser.

    Args:
        dsl: DSL source text to parse.
        timeout_seconds: Maximum time before classifying as HANG.

    Returns:
        FuzzResult with classification and metadata.
    """
    # Explicit spawn context (#1501): a fresh interpreter per worker, independent
    # of any test that mutated the global start method, and re-importing only the
    # lightweight parser module (see dazzle.core._fuzz_parse_worker).
    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue = ctx.Queue()  # type: ignore[type-arg]
    proc = ctx.Process(target=parse_worker, args=(dsl, result_queue))
    proc.start()
    proc.join(timeout=timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.HANG,
            error_message=f"Parser did not complete within {timeout_seconds}s",
        )

    try:
        kind, msg, err_type, constructs = result_queue.get_nowait()
    except queue.Empty:
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CRASH,
            error_message="Worker process exited without result",
        )

    if kind == "valid":
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.VALID,
            constructs_hit=constructs,
        )
    elif kind == "parse_error":
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CLEAN_ERROR,
            error_message=msg,
            error_type=err_type,
        )
    else:  # crash
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CRASH,
            error_message=msg,
            error_type=err_type,
        )
