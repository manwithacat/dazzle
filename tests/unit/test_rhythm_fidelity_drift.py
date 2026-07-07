"""#1558 (2a): `dazzle rhythm fidelity` surfaces answer-first landing drift —
one advisory line per persona whose declared default_workspace contradicts its
rhythm-inferred landing.
"""

from dazzle.cli.rhythm import landing_drift_lines
from dazzle.core import ir
from dazzle.core.ir.rhythm import PhaseKind


def _ws(*names):  # type: ignore[no-untyped-def]
    return [ir.WorkspaceSpec(name=n) for n in names]


def _rhythm_active(persona, surface):  # type: ignore[no-untyped-def]
    return ir.RhythmSpec(
        name=f"{persona}_daily",
        persona=persona,
        phases=[
            ir.PhaseSpec(
                name="active",
                kind=PhaseKind.ACTIVE,
                scenes=[ir.SceneSpec(name="s", surface=surface)],
            )
        ],
    )


def test_landing_drift_lines_reports_contradiction():
    p = ir.PersonaSpec(id="agent", label="Agent", default_workspace="reports")
    r = _rhythm_active("agent", "queue")
    lines = landing_drift_lines([p], [r], _ws("queue", "reports"), [])
    assert len(lines) == 1 and "queue" in lines[0] and "reports" in lines[0]


def test_landing_drift_lines_empty_when_coherent():
    p = ir.PersonaSpec(id="agent", label="Agent", default_workspace="queue")
    r = _rhythm_active("agent", "queue")
    assert landing_drift_lines([p], [r], _ws("queue"), []) == []


def test_landing_drift_lines_empty_without_declaration():
    p = ir.PersonaSpec(id="agent", label="Agent")  # no default_workspace
    r = _rhythm_active("agent", "queue")
    assert landing_drift_lines([p], [r], _ws("queue"), []) == []
