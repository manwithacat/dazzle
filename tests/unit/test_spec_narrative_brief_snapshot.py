"""Golden snapshot of the simple_task brief.

Extraction changes are intentional and reviewable — they must not slip through
silently. To accept a change:
  1. Regenerate: dazzle spec brief -p examples/simple_task -f json \
       > tests/unit/baselines/spec_brief_simple_task.json
  2. Review the diff (and add a CHANGELOG entry if the public shape changed)
  3. Commit the regenerated baseline
"""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.spec_narrative.brief import build_brief

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).parent / "baselines" / "spec_brief_simple_task.json"


def test_simple_task_brief_matches_baseline():
    brief = build_brief(load_project_appspec(REPO_ROOT / "examples/simple_task"))
    current = brief.model_dump_json(indent=2) + "\n"
    assert BASELINE.exists(), (
        f"Baseline missing. Generate it with:\n"
        f"  dazzle spec brief -p examples/simple_task -f json > {BASELINE}"
    )
    expected = BASELINE.read_text(encoding="utf-8")
    assert current == expected, (
        "simple_task brief drifted from baseline. If intentional, regenerate:\n"
        f"  dazzle spec brief -p examples/simple_task -f json > {BASELINE}"
    )


def test_brief_is_deterministic():
    app = load_project_appspec(REPO_ROOT / "examples/simple_task")
    assert build_brief(app).model_dump_json() == build_brief(app).model_dump_json()
