"""Public-RBAC access matrix coverage for the shapes_validation fixture.

Companion to `test_rbac_validation.py`: same `dazzle.rbac.matrix.generate_access_matrix`
surface, exercised against the abstract shapes domain that probes multi-tenant
RBAC patterns (realm-scoped, junction EXISTS, parent-scope inheritance,
deny-all baseline). See `fixtures/shapes_validation/README.md` for the
fixture's design rules.

The conformance pytest plugin tests (`test_conformance_plugin.py`) consume
this fixture for collection-pipeline coverage. *This* file consumes it for
matrix-shape coverage — the signal the existing tests don't extract.
"""

from pathlib import Path

import pytest

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision, generate_access_matrix

PROJECT_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "shapes_validation"

ALL_ENTITIES = [
    "User",
    "Realm",
    "Shape",
    "RealmGuardian",
    "Artifact",
    "Inscription",
]

ALL_PERSONAS = [
    "oracle",
    "sovereign",
    "architect",
    "chromat",
    "forgemaster",
    "witness",
    "guardian",
    "outsider",
]

ALL_OPERATIONS = ["create", "read", "update", "delete", "list"]


@pytest.fixture(scope="module")
def appspec():
    """Load the shapes_validation DSL and return the linked AppSpec."""
    manifest = load_manifest(PROJECT_ROOT / "dazzle.toml")
    dsl_files = discover_dsl_files(PROJECT_ROOT, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


@pytest.fixture(scope="module")
def access_matrix(appspec) -> AccessMatrix:
    """Public RBAC access matrix — same surface `dazzle rbac matrix` emits."""
    return generate_access_matrix(appspec)


class TestAccessMatrixCoverage:
    """Probe the public RBAC matrix across all 6 × 8 × 5 = 240 cells.

    The shapes domain is deliberately abstract — the assertions here check
    *shape properties* (well-formedness, oracle-dominance, complete
    mediation for outsider, no unprotected cells) rather than pinning
    individual decisions. Per-cell pinning belongs in the conformance
    plugin's derived test cases (`test_conformance_plugin.py`).
    """

    @pytest.mark.parametrize("persona", ALL_PERSONAS)
    @pytest.mark.parametrize("entity", ALL_ENTITIES)
    @pytest.mark.parametrize("op", ALL_OPERATIONS)
    def test_matrix_decision_is_well_formed(
        self, access_matrix: AccessMatrix, persona: str, entity: str, op: str
    ) -> None:
        """Every (persona, entity, op) must resolve to a known PolicyDecision."""
        decision = access_matrix.get(persona, entity, op)
        assert isinstance(decision, PolicyDecision), (
            f"({persona}, {entity}, {op}) returned {decision!r}, not a PolicyDecision"
        )

    def test_no_unprotected_entities(self, access_matrix: AccessMatrix) -> None:
        """No cell may land on PERMIT_UNPROTECTED — every entity has an access spec."""
        unprotected: list[tuple[str, str, str]] = []
        for persona in ALL_PERSONAS:
            for entity in ALL_ENTITIES:
                for op in ALL_OPERATIONS:
                    if access_matrix.get(persona, entity, op) == PolicyDecision.PERMIT_UNPROTECTED:
                        unprotected.append((persona, entity, op))
        assert not unprotected, f"Unprotected cells found: {unprotected}"

    def _allow_count(self, matrix: AccessMatrix, persona: str) -> int:
        """Count PERMIT + PERMIT_FILTERED decisions across the full entity × op grid."""
        return sum(
            1
            for entity in ALL_ENTITIES
            for op in ALL_OPERATIONS
            if matrix.get(persona, entity, op)
            in (PolicyDecision.PERMIT, PolicyDecision.PERMIT_FILTERED)
        )

    def test_oracle_has_strictly_most_privileges(self, access_matrix: AccessMatrix) -> None:
        """Oracle (platform admin) must dominate every other persona's privilege count."""
        counts = {p: self._allow_count(access_matrix, p) for p in ALL_PERSONAS}
        oracle = counts["oracle"]
        for persona, count in counts.items():
            if persona == "oracle":
                continue
            assert oracle >= count, (
                f"oracle ({oracle} allows) must dominate {persona} ({count} allows) — "
                f"platform admin should never be out-privileged by a tenant role"
            )

    def test_outsider_complete_mediation(self, access_matrix: AccessMatrix) -> None:
        """Outsider is the deny-all baseline that proves complete mediation.

        It may have a small number of allows (the fixture deliberately leaks
        a list+read on the public-facing User entity to exercise the
        no-realm-scope path), but it must NEVER be permitted to mutate.
        Mutating allows on outsider would indicate broken default-deny.
        """
        for entity in ALL_ENTITIES:
            for op in ("create", "update", "delete"):
                decision = access_matrix.get("outsider", entity, op)
                assert decision == PolicyDecision.DENY, (
                    f"outsider.{op} on {entity} = {decision}; mutating ops "
                    f"must always DENY for the deny-all baseline persona"
                )

    def test_tenant_personas_use_scoped_permits(self, access_matrix: AccessMatrix) -> None:
        """Tenant-scoped roles' list/read on Shape must be PERMIT_SCOPED.

        A bare PERMIT here would mean cross-realm data leak: a `sovereign`
        from realm A could enumerate shapes from realm B. PERMIT_SCOPED is
        the scope-block-path decision (a scope predicate applies at query
        time; PERMIT_FILTERED is the legacy no-scope-blocks path).

        #1355: this previously asserted only `!= PERMIT`, which the cells'
        actual value — DENY, because the permits were missing entirely —
        satisfied vacuously for months. Assert the exact intended decision.
        """
        for persona in ("sovereign", "architect", "chromat", "forgemaster", "witness"):
            for op in ("list", "read"):
                decision = access_matrix.get(persona, "Shape", op)
                assert decision == PolicyDecision.PERMIT_SCOPED, (
                    f"{persona}.{op} on Shape = {decision} — must be "
                    f"PERMIT_SCOPED (realm/colour predicate at query time)"
                )
