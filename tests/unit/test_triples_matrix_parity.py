"""#1520: triples ⊆ matrix — the static-permission invariant.

``get_permitted_personas`` (core/ir/triples.py) and ``generate_access_matrix``
(rbac/matrix.py) are two evaluators over the same PermissionRule set; they
diverged when #1281's deny-all short-form and Cedar FORBID handling were taught
to the matrix but not the triples helpers. This gate pins the containment
invariant across every example app: any persona the triples layer reports as
permitted must map to a role the matrix does not DENY.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.domain import PermissionKind
from dazzle.core.ir.triples import get_permitted_personas
from dazzle.rbac.matrix import PolicyDecision, generate_access_matrix

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def _examples() -> list[str]:
    return sorted(p.name for p in EXAMPLES_DIR.iterdir() if (p / "dazzle.toml").is_file())


@pytest.mark.parametrize("app", _examples())
def test_triples_permitted_is_subset_of_matrix_permitted(app: str) -> None:
    appspec = load_project_appspec(EXAMPLES_DIR / app)
    if not appspec.personas:
        pytest.skip("app declares no personas")
    matrix = generate_access_matrix(appspec)
    role_of = {p.id: p.effective_role for p in appspec.personas}
    entities = list(appspec.domain.entities)

    violations: list[str] = []
    for entity in entities:
        for op in PermissionKind:
            permitted = get_permitted_personas(entities, appspec.personas, entity.name, op)
            for pid in permitted:
                decision = matrix.get(role_of[pid], entity.name, op.value)
                if decision == PolicyDecision.DENY:
                    violations.append(
                        f"{entity.name}.{op.value}: triples permit persona {pid!r} "
                        f"(role {role_of[pid]!r}) but the matrix says DENY"
                    )
    assert not violations, f"{app}: triples over-report vs matrix:\n" + "\n".join(violations)
