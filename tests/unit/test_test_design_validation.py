"""Unit tests for the test design persistence helpers."""

import tempfile
from pathlib import Path


class TestTestDesignIdCollisionHandling:
    """Tests for test design ID collision detection and auto-reassignment."""

    def test_no_collision_preserves_ids(self) -> None:
        """Test that designs with unique IDs are preserved."""
        from dazzle.core.ir.test_design import TestDesignSpec, TestDesignStatus
        from dazzle.testing.test_design_persistence import add_test_designs

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Create dsl/tests directory
            (project_root / "dsl" / "tests").mkdir(parents=True)

            designs = [
                TestDesignSpec(
                    test_id="TD-001",
                    title="Test 1",
                    status=TestDesignStatus.PROPOSED,
                ),
                TestDesignSpec(
                    test_id="TD-002",
                    title="Test 2",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]

            result = add_test_designs(project_root, designs, to_dsl=True)

            assert result.added_count == 2
            assert len(result.remapped_ids) == 0
            assert len(result.all_designs) == 2
            # IDs should be preserved
            ids = {d.test_id for d in result.all_designs}
            assert ids == {"TD-001", "TD-002"}

    def test_collision_auto_assigns_new_ids(self) -> None:
        """Test that colliding IDs are auto-reassigned."""
        from dazzle.core.ir.test_design import TestDesignSpec, TestDesignStatus
        from dazzle.testing.test_design_persistence import add_test_designs

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "dsl" / "tests").mkdir(parents=True)

            # First batch
            batch1 = [
                TestDesignSpec(
                    test_id="TD-001",
                    title="Test 1",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            add_test_designs(project_root, batch1, to_dsl=True)

            # Second batch with collision
            batch2 = [
                TestDesignSpec(
                    test_id="TD-001",  # Collision!
                    title="Test 2",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            result = add_test_designs(project_root, batch2, to_dsl=True)

            assert result.added_count == 1
            assert len(result.remapped_ids) == 1
            assert "TD-001" in result.remapped_ids
            assert result.remapped_ids["TD-001"] == "TD-002"
            # Total should be 2 designs with unique IDs
            assert len(result.all_designs) == 2
            ids = {d.test_id for d in result.all_designs}
            assert ids == {"TD-001", "TD-002"}

    def test_multiple_collisions_in_same_batch(self) -> None:
        """Test handling multiple collisions from same proposal batch."""
        from dazzle.core.ir.test_design import TestDesignSpec, TestDesignStatus
        from dazzle.testing.test_design_persistence import add_test_designs

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "dsl" / "tests").mkdir(parents=True)

            # First batch: TD-001, TD-002
            batch1 = [
                TestDesignSpec(
                    test_id="TD-001",
                    title="Batch1 Test 1",
                    status=TestDesignStatus.PROPOSED,
                ),
                TestDesignSpec(
                    test_id="TD-002",
                    title="Batch1 Test 2",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            add_test_designs(project_root, batch1, to_dsl=True)

            # Second batch: same IDs (simulating propose_persona called twice)
            batch2 = [
                TestDesignSpec(
                    test_id="TD-001",  # Collision
                    title="Batch2 Test 1",
                    status=TestDesignStatus.PROPOSED,
                ),
                TestDesignSpec(
                    test_id="TD-002",  # Collision
                    title="Batch2 Test 2",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            result = add_test_designs(project_root, batch2, to_dsl=True)

            assert result.added_count == 2
            assert len(result.remapped_ids) == 2
            # TD-001 -> TD-003, TD-002 -> TD-004
            assert result.remapped_ids["TD-001"] == "TD-003"
            assert result.remapped_ids["TD-002"] == "TD-004"
            # Total should be 4 designs
            assert len(result.all_designs) == 4

    def test_overwrite_mode_replaces_instead_of_remapping(self) -> None:
        """Test that overwrite=True replaces instead of remapping."""
        from dazzle.core.ir.test_design import TestDesignSpec, TestDesignStatus
        from dazzle.testing.test_design_persistence import add_test_designs

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "dsl" / "tests").mkdir(parents=True)

            batch1 = [
                TestDesignSpec(
                    test_id="TD-001",
                    title="Original",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            add_test_designs(project_root, batch1, to_dsl=True)

            batch2 = [
                TestDesignSpec(
                    test_id="TD-001",
                    title="Replacement",
                    status=TestDesignStatus.PROPOSED,
                ),
            ]
            result = add_test_designs(project_root, batch2, overwrite=True, to_dsl=True)

            assert result.added_count == 1
            assert len(result.remapped_ids) == 0  # No remapping in overwrite mode
            assert len(result.all_designs) == 1
            assert result.all_designs[0].title == "Replacement"
