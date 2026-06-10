"""#1364: required-ref NULL counts + unanchored-row checks in verify/cleanup.

Refs compile to soft (un-constrained) columns and invariants are enforced at
app write-time only — so out-of-convention writes can leave required refs
NULL and at-least-one-anchor invariants violated, invisibly to the old
tooling. `db verify` now reports both; `db cleanup --unanchored` sweeps the
invariant violations (opt-in: unanchored rows may be mid-flow data).
"""

from pathlib import Path

import pytest

from dazzle.core.parser import parse_modules
from dazzle.db.cleanup import db_cleanup_impl
from dazzle.db.verify import db_verify_impl, unanchored_invariant_fields

from ._fake_pg import scalar_conn


def _parse_entity(tmp_path: Path, entity_dsl: str):
    src = f'module t\n\napp t "T"\n\n{entity_dsl}'
    f = tmp_path / "app.dsl"
    f.write_text(src, encoding="utf-8")
    (module,) = parse_modules([f])
    return module.fragment.entities


class TestUnanchoredInvariantRecognition:
    def test_or_of_not_null_recognised(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  matter_ref: ref Matter\n"
            "  invariant: case_ref != null or matter_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n'
            "\n"
            'entity Matter "Matter":\n  id: uuid pk\n',
        )
        (invariant,) = entities[0].invariants
        assert unanchored_invariant_fields(invariant) == ["case_ref", "matter_ref"]

    def test_comparison_invariant_not_translatable(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Job "Job":\n'
            "  id: uuid pk\n"
            "  started_at: datetime\n"
            "  ended_at: datetime\n"
            "  invariant: ended_at > started_at\n",
        )
        (invariant,) = entities[0].invariants
        assert unanchored_invariant_fields(invariant) is None

    def test_single_not_null_not_treated_as_anchor_set(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  invariant: case_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n',
        )
        (invariant,) = entities[0].invariants
        # A one-field not-null is `required`'s job, not an anchor set.
        assert unanchored_invariant_fields(invariant) is None


class TestVerifyRequiredNulls:
    @pytest.mark.asyncio
    async def test_required_ref_nulls_counted(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"}, required_refs={"school"})
        conn = scalar_conn([0, 4])  # orphan check → 0, required-null check → 4

        result = await db_verify_impl(entities=[school, student], conn=conn)
        required = [c for c in result["checks"] if c["status"] == "required_null"]
        assert len(required) == 1
        assert required[0]["null_count"] == 4
        assert result["total_issues"] == 4

    @pytest.mark.asyncio
    async def test_optional_ref_not_null_checked(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})  # optional ref
        conn = scalar_conn(0)

        result = await db_verify_impl(entities=[school, student], conn=conn)
        assert all("null_count" not in c for c in result["checks"])

    @pytest.mark.asyncio
    async def test_unanchored_rows_counted(self, make_entity, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  matter_ref: ref Matter\n"
            "  invariant: case_ref != null or matter_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n'
            "\n"
            'entity Matter "Matter":\n  id: uuid pk\n',
        )
        # 2 orphan checks (case_ref, matter_ref) → 0; unanchored count → 1179.
        conn = scalar_conn([0, 0, 1179])

        result = await db_verify_impl(entities=entities, conn=conn)
        unanchored = [c for c in result["checks"] if c["status"] == "unanchored"]
        assert len(unanchored) == 1
        assert unanchored[0]["unanchored_count"] == 1179
        assert unanchored[0]["anchor_fields"] == ["case_ref", "matter_ref"]
        assert result["total_issues"] == 1179


class TestCleanupUnanchored:
    @pytest.mark.asyncio
    async def test_dry_run_counts_unanchored(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  matter_ref: ref Matter\n"
            "  invariant: case_ref != null or matter_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n'
            "\n"
            'entity Matter "Matter":\n  id: uuid pk\n',
        )
        conn = scalar_conn([0, 0, 7])

        result = await db_cleanup_impl(entities=entities, conn=conn, dry_run=True, unanchored=True)
        assert result["would_delete"] == 7
        assert any("unanchored_count" in f for f in result["findings"])

    @pytest.mark.asyncio
    async def test_default_does_not_touch_unanchored(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  matter_ref: ref Matter\n"
            "  invariant: case_ref != null or matter_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n'
            "\n"
            'entity Matter "Matter":\n  id: uuid pk\n',
        )
        conn = scalar_conn(0)

        result = await db_cleanup_impl(entities=entities, conn=conn, dry_run=True)
        # Without --unanchored, only the two orphan checks run.
        assert result["would_delete"] == 0
        assert all("unanchored_count" not in f for f in result["findings"])

    @pytest.mark.asyncio
    async def test_sweep_deletes_unanchored(self, tmp_path: Path) -> None:
        entities = _parse_entity(
            tmp_path,
            'entity Doc "Doc":\n'
            "  id: uuid pk\n"
            "  case_ref: ref Case\n"
            "  matter_ref: ref Matter\n"
            "  invariant: case_ref != null or matter_ref != null\n"
            "\n"
            'entity Case "Case":\n  id: uuid pk\n'
            "\n"
            'entity Matter "Matter":\n  id: uuid pk\n',
        )
        # Iteration 1: orphans 0,0; unanchored count 5 (then DELETE).
        # Iteration 2: orphans 0,0; unanchored count 0 → loop ends.
        conn = scalar_conn([0, 0, 5, [], 0, 0, 0])

        result = await db_cleanup_impl(entities=entities, conn=conn, unanchored=True)
        assert result["total_deleted"] == 5
        deletions = [d for d in result["deletions"] if d.get("kind") == "unanchored"]
        assert len(deletions) == 1
        assert deletions[0]["deleted"] == 5
        # The DELETE actually executed.
        assert any("DELETE FROM" in sql for sql, _ in conn.executed)
