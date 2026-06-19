"""Framework structural-fitness (B2) — the broad-exception-swallow ratchet.

Drift gate (same posture as test_complexity_ratchet): the count of broad-exception
swallows may not grow. Adding a new ``except Exception: logger.debug(...)`` or
``except (Exception | ImportError): pass`` fails CI — narrow the exception type, raise
the log level to warning/exception, or let it propagate. Burning some down? Lower the
baseline in the same commit (the one-way valve tightens).

Origin: the 2026-06-19 smells round flagged these as the dominant semantic debt
(silent + debug-only swallows). This stops the bleeding while the burn-down happens.
"""

from pathlib import Path

from dazzle.fitness.swallows import count_swallows

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"

# Census at the gate's introduction (v0.83.30). LOWER these as swallows are burned
# down; never raise them — a new broad swallow must be narrowed, not baselined in.
_BASELINE = {"silent": 44, "debug_only": 181}


def test_broad_exception_swallows_do_not_grow() -> None:
    current = count_swallows(_SRC)
    grown = {
        kind: (current[kind], base) for kind, base in _BASELINE.items() if current[kind] > base
    }
    assert not grown, (
        "Broad-exception-swallow count grew "
        + ", ".join(f"{k}: {base}→{cur}" for k, (cur, base) in grown.items())
        + ". A new `except Exception: logger.debug(...)` / `except (Exception|ImportError): "
        "pass` is not allowed — narrow the exception type, log at warning/exception, or let "
        "it propagate. (If you burned some down, lower the baseline in this test to "
        "lock in the win — that's encouraged, just not forced.)"
    )
