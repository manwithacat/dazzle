"""Import-boundary gates for the back↔ui cycle + IR fan-in (issue #1086).

Three structural rules locked in by the #1086 sub-workstream sequence:

1. ``dazzle.back/`` must not import from the modules that workstreams
   A/B/D explicitly migrated to ``dazzle.render``:

   - ``dazzle.ui.runtime.template_renderer`` (filter helpers — #1090)
   - ``dazzle.ui.runtime.template_context`` (PageContext + friends — #1091)
   - ``dazzle.ui.runtime.surface_access`` (pure access types — #1091)
   - ``dazzle.back.runtime.renderers.page_builder`` (dispatch — #1094)
   - ``dazzle.back.runtime.renderers.dispatch`` (dispatch — #1094)
   - ``dazzle.back.runtime.access_evaluator`` (now ``render.access_evaluator`` — #1094)

   New code that needs these helpers should import from ``dazzle.render``.

   Note: a broader ``back/`` ↛ ``dazzle.ui.*`` ban remains aspirational
   — back/ still imports ui-side helpers like ``theme``, ``css_loader``,
   ``asset_fingerprint``, ``htmx``, ``app_chrome``, ``site_renderer``,
   ``workspace_renderer``, ``condition_eval``, etc. Those need their own
   migrate-to-``render`` workstreams; tracked as future work in the
   #1086 plan.

2. ``dazzle.ui/`` must not import from ``dazzle.back.*`` — with one
   documented exception, ``ui/runtime/combined_server.py``, whose job
   is to glue both layers together at the entry point (#1086 plan).

3. ``dazzle.back/`` must not import from the three banned
   ``dazzle.core.ir.*`` submodules (``appspec``, ``surfaces``,
   ``domain``). Use the ``dazzle.core.ir`` re-export facade or the
   ``dazzle.core.ir.protocols`` adapter layer instead — adding new
   concrete-submodule imports under ``back/`` defeats the work that
   landed in #1092 and #1093.

Gates run against any ``.py`` file under ``src/dazzle/back/`` or
``src/dazzle/ui/`` (production AND test code in those subtrees).
``tests/`` at the repo root is intentionally out of scope — unit
tests there sometimes need concrete IR classes for fixtures.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ui/ entry-point glue — legitimately bridges back/ and ui/ at startup.
# Filed in the #1086 migration plan as the documented exemption.
_UI_TO_BACK_EXEMPT: frozenset[str] = frozenset(
    {
        "src/dazzle/ui/runtime/combined_server.py",
    }
)

# Modules from ui/ and back/ whose contents moved to dazzle.render
# during #1090, #1091, #1094. New back/ code referencing these paths
# is a regression and must move to the dazzle.render replacement.
_BACK_BANNED_FROM_UI_MIGRATED = re.compile(
    r"^\s*from dazzle\.ui\.runtime\.(template_renderer|template_context|surface_access)\b"
)
_BACK_BANNED_FROM_BACK_RENDERERS = re.compile(
    r"^\s*from dazzle\.back\.runtime\."
    r"(renderers\.page_builder|renderers\.dispatch|access_evaluator)\b"
)

_UI_FROM_BACK = re.compile(r"^\s*from dazzle\.back[\.\s]")
_BACK_FROM_BANNED_IR = re.compile(r"^\s*from dazzle\.core\.ir\.(appspec|surfaces|domain)\b")


def _scan(root: Path, pattern: re.Pattern[str]) -> list[str]:
    """Return ``rel_path:lineno: line`` for every match of *pattern*."""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(lines, start=1):
            if pattern.match(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    return offenders


def test_back_does_not_import_migrated_render_modules() -> None:
    """``back/`` must not import from the helper modules that A/B/D
    explicitly migrated to ``dazzle.render`` (#1086 workstreams A, B, D).

    The migrated modules: ``ui.runtime.template_renderer``,
    ``template_context``, ``surface_access``, plus
    ``back.runtime.renderers.page_builder``,
    ``renderers.dispatch``, and ``back.runtime.access_evaluator``.
    All are now in ``dazzle.render``.
    """
    back_root = REPO_ROOT / "src" / "dazzle" / "back"
    offenders = _scan(back_root, _BACK_BANNED_FROM_UI_MIGRATED) + _scan(
        back_root, _BACK_BANNED_FROM_BACK_RENDERERS
    )
    assert not offenders, (
        "back/ must not import from the modules that moved to dazzle.render "
        "in #1090/#1091/#1094. Update the import path to dazzle.render.*. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )


def test_ui_does_not_import_from_back() -> None:
    """``dazzle.ui/`` must not import from ``dazzle.back.*`` (#1086).

    Exception: ``ui/runtime/combined_server.py`` is entry-point glue
    that intentionally pulls both layers together — see the #1086
    migration plan.
    """
    offenders = _scan(REPO_ROOT / "src" / "dazzle" / "ui", _UI_FROM_BACK)
    offenders = [
        line
        for line in offenders
        if not any(line.startswith(f"{exempt}:") for exempt in _UI_TO_BACK_EXEMPT)
    ]
    assert not offenders, (
        "ui/ must not import from back/ (outside combined_server.py). "
        "Use dazzle.render or dazzle.core. Offenders:\n  " + "\n  ".join(offenders)
    )


def test_back_does_not_import_concrete_ir_submodules() -> None:
    """``dazzle.back/`` must not import from ``dazzle.core.ir.appspec``,
    ``surfaces``, or ``domain`` directly (#1086 pattern P5).

    These three modules were the 30+-importer fan-in that the smells
    run flagged as the codebase's biggest change-amplifier. Use:

    - ``from dazzle.core.ir import X`` — the public re-export facade.
    - ``from dazzle.core.ir.protocols import XLike`` — narrow read-only
      adapter when only a few attrs are needed.
    """
    offenders = _scan(
        REPO_ROOT / "src" / "dazzle" / "back",
        _BACK_FROM_BANNED_IR,
    )
    assert not offenders, (
        "back/ must not import from dazzle.core.ir.{appspec,surfaces,domain} "
        "directly. Use `from dazzle.core.ir import X` (the facade) or "
        "`from dazzle.core.ir.protocols import XLike` (the protocol adapter). "
        "Offenders:\n  " + "\n  ".join(offenders)
    )
