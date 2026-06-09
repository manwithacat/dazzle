"""Micro-benchmark: Dazzle DSL parse -> IR (AppSpec) across Python interpreters.

Measures the CPU-bound parse path only (no I/O) — the part interpreter speedups
(e.g. the 3.14 tail-call interpreter) actually affect. Used for the
"3.14 as primary target" evaluation (docs/python-3.14-primary-target.md).

Usage (compare interpreters via uv):

    for v in 3.12 3.13 3.14; do
        uv run --python $v --extra dev python scripts/bench_interp.py
    done

Reports best-of-N (most stable) plus median/mean. Best-of-N minimises machine
noise; treat single-digit-% differences as indicative, not rigorous.
"""

import statistics
import sys
import sysconfig
import time
from pathlib import Path

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names

PROJECT = Path("examples/pra")  # heaviest example (~8.3k DSL lines)
WARMUP = 5
N = 40


def main() -> None:
    manifest = load_manifest((PROJECT / "dazzle.toml").resolve())
    dsl_files = discover_dsl_files(PROJECT, manifest)
    renderers = known_renderer_names(manifest)

    def once() -> None:
        modules = parse_modules(dsl_files)
        build_appspec(modules, manifest.project_root, known_renderers=renderers)

    for _ in range(WARMUP):
        once()

    times = []
    for _ in range(N):
        t0 = time.perf_counter()
        once()
        times.append(time.perf_counter() - t0)

    tail_call = sysconfig.get_config_var("Py_TAIL_CALL_INTERP")
    print(
        f"py{sys.version.split()[0]} (tail_call={tail_call}): "
        f"min={min(times) * 1000:.1f}ms  median={statistics.median(times) * 1000:.1f}ms  "
        f"mean={statistics.mean(times) * 1000:.1f}ms  (N={N}, {len(dsl_files)} files)"
    )


if __name__ == "__main__":
    main()
