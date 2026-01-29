"""Tests for PitchSpec extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.pitch.extractor import PitchContext, extract_pitch_context
from dazzle.pitch.ir import CompanySpec, PitchSpec


class TestPitchContext:
    def test_defaults(self):
        spec = PitchSpec()
        ctx = PitchContext(spec=spec)
        assert ctx.app_name is None
        assert ctx.entities == []
        assert ctx.surfaces == []
        assert ctx.personas == []
        assert ctx.story_count == 0


class TestExtractPitchContext:
    def test_no_manifest(self, tmp_path: Path):
        """Extract should succeed even without dazzle.toml."""
        spec = PitchSpec(company=CompanySpec(name="Test"))
        ctx = extract_pitch_context(tmp_path, spec)
        assert ctx.spec.company.name == "Test"
        assert ctx.entities == []

    def test_with_simple_task(self):
        """Extract from simple_task example if available."""
        # Find the examples directory
        import dazzle

        examples_dir = Path(dazzle.__file__).parent / "examples" / "simple_task"
        if not (examples_dir / "dazzle.toml").exists():
            pytest.skip("simple_task example not available")

        spec = PitchSpec()
        ctx = extract_pitch_context(examples_dir, spec)
        # simple_task should have at least one entity
        assert len(ctx.entities) > 0
