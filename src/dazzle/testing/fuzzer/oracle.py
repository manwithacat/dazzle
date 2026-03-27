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
from pathlib import Path


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


def _parse_worker(dsl: str, result_queue: multiprocessing.Queue) -> None:  # type: ignore[type-arg]
    """Worker function that runs in a subprocess to parse DSL with isolation."""
    try:
        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.errors import ParseError

        _, _, _, _, _, fragment = parse_dsl(dsl, Path("fuzz.dsl"))
        # Collect which construct types were parsed
        constructs: list[str] = []
        for attr in (
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
        ):
            if getattr(fragment, attr, None):
                constructs.append(attr)
        result_queue.put(("valid", None, None, constructs))
    except ParseError as e:
        result_queue.put(("parse_error", str(e), "ParseError", []))
    except Exception as e:
        result_queue.put(("crash", str(e), type(e).__name__, []))


def classify(dsl: str, timeout_seconds: float = 5.0) -> FuzzResult:
    """Classify a DSL input by running it through the parser.

    Args:
        dsl: DSL source text to parse.
        timeout_seconds: Maximum time before classifying as HANG.

    Returns:
        FuzzResult with classification and metadata.
    """
    result_queue: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    proc = multiprocessing.Process(target=_parse_worker, args=(dsl, result_queue))
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
