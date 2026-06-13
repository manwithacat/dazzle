"""Drift gate: per-project ``dazzle validate`` baseline.

What this gate enforces:
    Every project under ``examples/`` and ``fixtures/`` that has a
    ``dazzle.toml`` is loaded and ``lint_appspec()`` is run. The
    resulting (errors, warnings) counts are compared against
    ``fixtures/dazzle_validate_baseline.json``.

    Bidirectional drift catches both regressions and silent fixes:
    - actual errors > baseline → FAIL (new validation error introduced)
    - actual errors < baseline → FAIL (issue resolved; remove from baseline)
    - warnings: baseline lists a floor; +10 grace before failing
    - expected_error_patterns: each substring must appear in the error
      list (so the FIXTURE FAILS if its kitchen-sink intent breaks too —
      e.g. the deliberate decimal-in-stream-schema lines getting
      auto-fixed by an aggressive refactor)

Why this exists:
    Some examples (notably ``fixtures/pra``) are deliberate
    kitchen-sink test data that exercise grammar shapes the
    validator's semantic rules reject (e.g. ``decimal`` in stream
    schemas, ``permit:`` without ``scope:``). Without a baseline,
    every parser/refactor sweep flags pra as red, drowning real
    regressions in expected-noise. With a baseline, only DRIFT
    is reported — pra's known 7 errors stay quiet; a single new
    error anywhere fires immediately.

How to adjust the baseline:
    Edit ``tests/unit/fixtures/dazzle_validate_baseline.json``.
    Projects without an entry are required to be clean (zero
    errors). To add a project, declare ``expected_errors``,
    ``expected_warnings_min``, and ``expected_error_patterns``
    (each substring is asserted to appear in the actual error
    list — they describe the *intentional* failures so a baseline
    can't mask unrelated regressions).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "unit" / "fixtures" / "dazzle_validate_baseline.json"
SCAN_ROOTS = ("examples", "fixtures")
WARNING_GRACE = 10


def _projects() -> Iterator[Path]:
    """Yield each subdirectory containing ``dazzle.toml`` under SCAN_ROOTS."""
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for child in sorted(root.iterdir()):
            if (child / "dazzle.toml").is_file():
                yield child


def _load_baseline() -> dict[str, dict[str, Any]]:
    with BASELINE_PATH.open() as f:
        data = json.load(f)
    return dict(data.get("baselines") or {})


def _project_validate(project: Path) -> tuple[list[str], list[str]]:
    """Run the full parse → link → lint pipeline; return (errors, warnings).

    Imports inside the function to keep test collection cheap.
    """
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.lint import lint_appspec

    appspec = load_project_appspec(project)
    errors, warnings, _relevance = lint_appspec(appspec)
    return errors, warnings


@pytest.mark.parametrize(
    "project",
    list(_projects()),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_validate_matches_baseline(project: Path) -> None:
    """Each project's validation output must match its baseline (or be clean)."""
    baselines = _load_baseline()
    key = str(project.relative_to(REPO_ROOT))
    entry = baselines.get(key, {})

    errors, warnings = _project_validate(project)

    expected_errors = int(entry.get("expected_errors") or 0)
    expected_warnings_min = int(entry.get("expected_warnings_min") or 0)
    expected_patterns = list(entry.get("expected_error_patterns") or [])

    problems: list[str] = []

    if len(errors) != expected_errors:
        if len(errors) > expected_errors:
            problems.append(
                f"NEW ERRORS: got {len(errors)} errors, baseline expects "
                f"{expected_errors}. New unexpected errors:\n  "
                + "\n  ".join(errors[expected_errors:][:5])
            )
        else:
            problems.append(
                f"BASELINE STALE: got {len(errors)} errors, baseline expects "
                f"{expected_errors}. Issue(s) fixed — update "
                f"`tests/unit/fixtures/dazzle_validate_baseline.json` to "
                f"reduce expected_errors."
            )

    for pattern in expected_patterns:
        if not any(pattern in err for err in errors):
            problems.append(
                f"BASELINE STALE: expected_error_patterns includes "
                f"{pattern!r} but no error in the actual list contains it. "
                "The fixture's deliberate failure may have been silently "
                "fixed by a recent change — remove the pattern from baseline."
            )

    if len(warnings) > expected_warnings_min + WARNING_GRACE:
        problems.append(
            f"NEW WARNINGS: got {len(warnings)} warnings, baseline floor "
            f"is {expected_warnings_min} (+{WARNING_GRACE} grace). "
            f"Sample new warnings:\n  " + "\n  ".join(warnings[expected_warnings_min:][:5])
        )

    if problems:
        pytest.fail(f"{key}:\n" + "\n\n".join(problems))
