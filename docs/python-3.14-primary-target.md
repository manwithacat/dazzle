# Python 3.14 as the Primary Target — Feasibility & Decision

**Status:** decided + executed (2026-06-09). **Floor unchanged:** `requires-python = ">=3.12"`.
**Prior context:** the Python version-support initiative (`docs/migration-findings.md`) — 3.13 and 3.14
were added to CI; this report is the follow-up that promotes **3.14 to the primary runtime/deploy target**.

---

## 1. Decision

Make **Python 3.14 the primary deploy/runtime target** while **keeping the floor at `>=3.12`** (full support
matrix 3.12 / 3.13 / 3.14). Rationale: it's Heroku's default interpreter, it's measurably faster on Dazzle's
CPU-bound paths via the uv-built tail-call interpreter, and the 3.14.5 GC revert removed the one regression that
would have mattered for a long-lived web process. The realistic gain is **low single digits**, so this is taken
because it's nearly free and rides the ecosystem default — not because it's a step-change.

## 2. Performance evidence

### Measured — Dazzle's own parse→IR path (`examples/pra`, 8.3k lines, best-of-40)

| Interpreter | min | median |
|---|---|---|
| 3.12.11 | 93.1 ms | 102.8 ms |
| 3.13.13 | 94.4 ms | 97.5 ms |
| **3.14.5** (`Py_TAIL_CALL_INTERP=1`) | **87.7 ms** | **90.0 ms** |

→ **3.14 is ~6% faster (min) to ~12% (median)** than 3.12 on parse→IR. Parsing/lexing/IR construction is
bytecode-dispatch-heavy — exactly the tail-call interpreter's sweet spot — so it beats the generic figure
slightly. (Benchmark: `scripts/bench_interp.py`, run via `uv run --python 3.X --extra dev`.)

### Research — honest, sourced figures

- **3.14 tail-call interpreter ≈ 3–5% geomean** ([python.org What's New 3.14](https://docs.python.org/3/whatsnew/3.14.html)).
  The original ~10–15% claim was [an LLVM-19 miscompilation artifact](https://blog.nelhage.com/post/cpython-tail-call/), since corrected.
- **3.13 vs 3.12 ≈ flat** in the default (no-JIT) build; wins concentrated in **async** paths (relevant to our
  Starlette runtime); a notable `coverage` 3.85× regression affects CI test runtime, not prod.
- **3.14.5 reverted the incremental GC** that caused [memory-pressure regressions in long-lived processes](https://pydevtools.com/blog/python-3145-rolls-back-the-incremental-garbage-collector/) —
  and `uv python install 3.14` resolves to 3.14.5+, so we dodge it.

### The caveat that shapes the rollout

The tail-call speedup exists **only in uv / python-build-standalone interpreters** (Clang-19 built; confirmed by
[Astral](https://astral.sh/blog/python-3.14) and our local `Py_TAIL_CALL_INTERP=1` probe). It needs a
Clang-19-built interpreter with the tail-call interpreter enabled; GCC-built stock interpreters ship it opt-in
(`--with-tail-call-interp`, off by default). This is exactly what makes the house deploy target well-placed:

- **Heroku via the uv path (slice 4b) captures the speedup.** ✅ The uv buildpack installs a
  python-build-standalone interpreter — Clang-19-built with the tail-call interpreter on — so the deploy target
  gets both 3.14 *correctness* and the interpreter speedup.

The gain is on **parse / validate / bootstrap / startup** (CPU), **not per-request serving** (I/O-bound on
Postgres/HTTP). So the felt impact is CLI/agent loops and boot time, not request latency.

## 3. Feasibility — all clear

- **Dependencies:** every dep (incl. the once-feared `lxml`/`python-xmlsec`) ships 3.14 wheels; `uv sync` is clean.
- **Tests:** the full suite is **17,604 passed / 0 failed on 3.14.5** after clearing the two reds below.
- **Deploy:** [Heroku made 3.14 the default in Dec 2025](https://devcenter.heroku.com/changelog-items/3505); `python:3.14-slim` exists.
- **Free-threading:** *not* adopted — separate `cp314t` ABI, no `abi3` wheel reuse, single-thread penalty;
  irrelevant without a CPU-bound *parallel* bottleneck.

## 4. The two reds that were cleared (so 3.14 is hard-green, not allow-fail)

Both were non-Dazzle issues; both fixed portably with **no api-surface baseline regeneration**:

1. **pygls' `asyncio.iscoroutinefunction` deprecation** (removal in 3.16) tripped the LSP import test's blanket
   `-W error`. Fix: scope-ignore that single upstream message in `tests/unit/test_lsp.py` (no-op on <3.14). Our
   own code already uses `inspect.iscoroutinefunction`.
2. **CPython 3.14's `typing.ForwardRef` repr gained `is_class=`**, drifting the floor-pinned api-surface
   baseline. Fix: `_format_annotation` (`api_surface/dsl_constructs.py`) now renders ForwardRefs from
   `__forward_arg__`, reproducing the pre-3.14 `ForwardRef('X')` form on every interpreter — so the committed
   `docs/api-surface/ir-types.txt` is unchanged and stable across 3.12/3.13/3.14.

## 5. What changed in this promotion

- **CI:** `python-tests` matrix is now `["3.12","3.13","3.14"]`, **all hard-required** (the allow-failure
  `include`/`continue-on-error` for 3.14 is gone). lint + type-check stay 3.12-pinned (floor-governed).
- **Trove classifier:** added `Programming Language :: Python :: 3.14`.
- **Primary deploy/runtime defaults → 3.14** (floor stays 3.12): repo `runtime.txt` + `.python-version`; the
  `dazzle deploy heroku` `runtime.txt` (pip path) and `.python-version` (uv path). The generated
  Heroku `pyproject.toml` keeps `requires-python = ">=3.12"` — apps still *support* 3.12, they *deploy* on 3.14.

## 6. Not done (deliberately)

- **Floor move to `>=3.13`/`>=3.14`** — still a separate product decision (drops older support; unlocks PEP 695
  + `from __future__ import annotations` cleanup). See `docs/migration-findings.md` §8 slice 6.
