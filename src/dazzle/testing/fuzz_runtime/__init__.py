"""Headless-browser interactive fuzz for Dazzle apps.

Complements the static `/fuzz` slash-command sweep with real browser
interactions against bootable apps, targeting JavaScript components
the static sweep cannot exercise: dz-richtext, optimistic-UI forms,
Alpine widget lifecycles, htmx swap timing.

Spike that motivated this module: the cycle-1 dz-richtext editor
shipped 5 cycles of source-grep tests that proved the SHAPE of the
JS was right (no `execCommand`, has `aria-pressed`, etc.) but proved
nothing about its BEHAVIOUR. The first interactive sweep caught a
schema-vs-nesting bug — `<strong>` wrapping a `<p>` block — that no
static check could see (#1000).

Pattern: per app, per widget, drive a deterministic-but-aggressive
interaction sequence; record console errors, page errors, DOM state
divergence (e.g. hidden-input not in sync with editor DOM); report a
terse pass/fail summary.

Public entry point: `run_app_fuzz(project_root)` — see runner.py.
"""

from dazzle.testing.fuzz_runtime.runner import FuzzReport, run_app_fuzz

__all__ = ["FuzzReport", "run_app_fuzz"]
