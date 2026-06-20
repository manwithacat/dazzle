"""#1216 / #1217 Phase 2: regression tests for the shared_parent_aggregate fixture.

The `fixtures/shared_parent_aggregate/` directory carries a minimal
diamond schema (ProjectMember + Contribution both reference Person)
plus a cohort_strip workspace whose `primary_aggregate` uses
`share: Person` to compute per-member contribution rollups. These
tests pin:

1. The fixture parses without errors.
2. The IR carries `share: "Person"` on the lens's primary_aggregate.
3. The compute path resolves the FKs on both sides (no ambiguity
   in this schema) and routes through `_batched_share_cohort_aggregate`.

Together they're the agent-discoverable proof that `share:` works,
and the test surface guards against regression as the cohort_strip
compute path evolves.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

_FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "shared_parent_aggregate"


def _load_fixture() -> ir.AppSpec:
    dsl_files = sorted((_FIXTURE_ROOT / "dsl").glob("*.dsl"))
    return build_appspec(parse_modules(dsl_files), "shared_parent_aggregate")


class TestFixtureParses:
    def test_fixture_builds_an_appspec(self) -> None:
        appspec = _load_fixture()
        entity_names = {e.name for e in appspec.domain.entities}
        # The four entities forming the diamond — Person is the pivot.
        for expected in ("Person", "Project", "ProjectMember", "Contribution"):
            assert expected in entity_names

    def test_diamond_shape_assembles(self) -> None:
        """Both sides of the diamond declare a single `ref Person`."""
        appspec = _load_fixture()
        entities = {e.name: e for e in appspec.domain.entities}

        def _ref_targets(entity: ir.EntitySpec) -> list[str]:
            return [
                f.type.ref_entity
                for f in entity.fields
                if f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity
            ]

        # ProjectMember has Person + Project FKs; Contribution has only Person.
        assert _ref_targets(entities["ProjectMember"]).count("Person") == 1
        assert _ref_targets(entities["Contribution"]).count("Person") == 1


class TestShareKeywordReachesIR:
    def test_cohort_strip_lens_carries_share_person(self) -> None:
        appspec = _load_fixture()
        workspace = next(
            (ws for ws in appspec.workspaces if ws.name == "project_dashboard"),
            None,
        )
        assert workspace is not None

        region = next(
            (r for r in workspace.regions if r.name == "contributions_strip"),
            None,
        )
        assert region is not None
        assert region.cohort_strip_config is not None

        lenses = region.cohort_strip_config.lenses
        # Two lenses: count(Contribution) + sum(Contribution.weight).
        assert len(lenses) == 2

        for lens in lenses:
            spec = lens.primary_aggregate
            assert spec is not None
            assert spec.share == "Person"
            # share: alone — no via: junction (that's the whole point of share:).
            assert spec.via is None


class TestComputePathDispatches:
    """The compute path resolves the FKs and routes through
    `_batched_share_cohort_aggregate`. We don't exercise SQL here —
    `test_cohort_aggregate_compute.py::test_share_builds_shared_parent_join_sql`
    does the SQL-shape assertions. This test just confirms the
    fixture's IR shape is consumed without warnings about missing
    FKs or ambiguity (the two failure modes for `share:`).
    """

    def test_fixture_compute_dispatch_is_quiet(self, caplog) -> None:
        import asyncio
        from unittest.mock import MagicMock

        from dazzle.http.runtime.workspace_region_computes import (
            compute_cohort_aggregate_primary,
        )

        appspec = _load_fixture()
        workspace = next(ws for ws in appspec.workspaces if ws.name == "project_dashboard")
        region = next(r for r in workspace.regions if r.name == "contributions_strip")
        lens = region.cohort_strip_config.lenses[0]  # count(Contribution)

        def _mock_repo(entity: ir.EntitySpec, table: str) -> MagicMock:
            cursor = MagicMock()
            cursor.execute = MagicMock()
            cursor.fetchall = MagicMock(return_value=[])
            conn = MagicMock()
            conn.cursor = MagicMock(return_value=cursor)
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=conn)
            ctx.__exit__ = MagicMock(return_value=False)
            repo = MagicMock()
            repo.entity_spec = entity
            repo.table_name = table
            repo.db = MagicMock()
            repo.db.placeholder = "%s"
            repo.db.connection = MagicMock(return_value=ctx)
            return repo

        entities = {e.name: e for e in appspec.domain.entities}
        repos = {
            "Contribution": _mock_repo(entities["Contribution"], "contribution"),
            "ProjectMember": _mock_repo(entities["ProjectMember"], "project_member"),
        }

        # Cohort items: two ProjectMember rows by id.
        items = [{"id": "pm1"}, {"id": "pm2"}]

        with caplog.at_level("WARNING"):
            asyncio.run(
                compute_cohort_aggregate_primary(
                    items=items,
                    lens=lens,
                    source_entity="ProjectMember",
                    repositories=repos,
                    scope_only_filters=None,
                )
            )

        # The compute path should NOT log "not reachable" or "ambiguous"
        # — both indicate the FK resolution failed.
        share_warnings = [
            r.message
            for r in caplog.records
            if "share=" in r.message and ("not reachable" in r.message or "ambiguous" in r.message)
        ]
        assert share_warnings == []
