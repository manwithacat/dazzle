"""Tests for the composition reference library (Phase 5).

Covers:
- composition_references.py: loader, manifest, promotion, token estimation
- composition_references_bootstrap.py: synthetic image generation
- composition_visual.py: reference injection into evaluation
- composition handler: bootstrap MCP operation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ── ReferenceImage Tests ─────────────────────────────────────────────


class TestReferenceImage:
    """Test the ReferenceImage dataclass."""

    def test_to_manifest_entry(self) -> None:
        from dazzle.core.composition_references import ReferenceImage

        ref = ReferenceImage(
            filename="good-test.png",
            label="good",
            section_type="hero",
            dimensions=["content_rendering", "visual_hierarchy"],
            description="Test reference",
            source="unit-test",
        )
        entry = ref.to_manifest_entry()

        assert entry["filename"] == "good-test.png"
        assert entry["label"] == "good"
        assert entry["section_type"] == "hero"
        assert entry["dimensions"] == ["content_rendering", "visual_hierarchy"]
        assert "_base64_cache" not in entry

    def test_base64_raises_when_not_loaded(self) -> None:
        from dazzle.core.composition_references import ReferenceImage

        ref = ReferenceImage(
            filename="good-test.png",
            label="good",
            section_type="hero",
            dimensions=[],
            description="",
            source="test",
        )
        with pytest.raises(ValueError, match="base64 not loaded"):
            _ = ref.base64

    def test_base64_returns_cached_value(self) -> None:
        from dazzle.core.composition_references import ReferenceImage

        ref = ReferenceImage(
            filename="good-test.png",
            label="good",
            section_type="hero",
            dimensions=[],
            description="",
            source="test",
            _base64_cache="abc123",
        )
        assert ref.base64 == "abc123"


# ── Loader Tests ─────────────────────────────────────────────────────


class TestLoadReferences:
    """Test loading references from disk."""

    def _setup_refs(self, tmp_path: Path) -> None:
        """Create a minimal reference directory."""
        hero_dir = tmp_path / "hero"
        hero_dir.mkdir()

        # Create a small PNG (1x1 pixel)
        import struct
        import zlib

        def _minimal_png() -> bytes:
            # Minimal valid PNG
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
            raw = zlib.compress(b"\x00\x00\x00\x00")
            idat_crc = zlib.crc32(b"IDAT" + raw)
            idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
            iend_crc = zlib.crc32(b"IEND")
            iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
            return sig + ihdr + idat + iend

        (hero_dir / "good-test.png").write_bytes(_minimal_png())
        (hero_dir / "bad-test.png").write_bytes(_minimal_png())

        manifest = {
            "section_type": "hero",
            "references": [
                {
                    "filename": "good-test.png",
                    "label": "good",
                    "section_type": "hero",
                    "dimensions": ["content_rendering"],
                    "description": "Good hero",
                    "source": "test",
                },
                {
                    "filename": "bad-test.png",
                    "label": "bad",
                    "section_type": "hero",
                    "dimensions": ["content_rendering"],
                    "description": "Bad hero",
                    "source": "test",
                },
            ],
        }
        (hero_dir / "manifest.json").write_text(json.dumps(manifest))

    def test_load_all(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        self._setup_refs(tmp_path)
        refs = load_references(tmp_path)

        assert "hero" in refs
        assert len(refs["hero"]) == 2
        assert refs["hero"][0].label == "good"
        assert refs["hero"][1].label == "bad"
        # base64 should be loaded
        assert len(refs["hero"][0].base64) > 0

    def test_load_with_label_filter(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        self._setup_refs(tmp_path)
        refs = load_references(tmp_path, label_filter="good")

        assert len(refs["hero"]) == 1
        assert refs["hero"][0].label == "good"

    def test_load_with_section_filter(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        self._setup_refs(tmp_path)
        refs = load_references(tmp_path, section_types=["features"])

        assert "hero" not in refs
        assert refs == {}

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        refs = load_references(tmp_path / "nonexistent")
        assert refs == {}

    def test_max_per_section(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        self._setup_refs(tmp_path)
        refs = load_references(tmp_path, max_per_section=1)

        assert len(refs["hero"]) == 1

    def test_missing_image_skipped(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        hero_dir = tmp_path / "hero"
        hero_dir.mkdir()
        manifest = {
            "section_type": "hero",
            "references": [
                {
                    "filename": "missing.png",
                    "label": "good",
                    "section_type": "hero",
                    "dimensions": [],
                    "description": "",
                    "source": "test",
                }
            ],
        }
        (hero_dir / "manifest.json").write_text(json.dumps(manifest))

        refs = load_references(tmp_path)
        assert refs == {}

    def test_bad_manifest_json_skipped(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references

        hero_dir = tmp_path / "hero"
        hero_dir.mkdir()
        (hero_dir / "manifest.json").write_text("not json{")

        refs = load_references(tmp_path)
        assert refs == {}


# ── Manifest Writer Tests ────────────────────────────────────────────


class TestSaveManifest:
    """Test manifest writing."""

    def test_creates_manifest(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import ReferenceImage, save_manifest

        section_dir = tmp_path / "hero"
        refs = [
            ReferenceImage(
                filename="good.png",
                label="good",
                section_type="hero",
                dimensions=["content_rendering"],
                description="Test",
                source="unit",
            )
        ]

        path = save_manifest(section_dir, refs)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["section_type"] == "hero"
        assert len(data["references"]) == 1
        assert data["references"][0]["filename"] == "good.png"

    def test_creates_directory(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import save_manifest

        section_dir = tmp_path / "nested" / "dir"
        save_manifest(section_dir, [])
        assert section_dir.exists()


# ── Promotion Tests ──────────────────────────────────────────────────


class TestShouldPromote:
    """Test auto-promotion threshold logic."""

    def test_both_above_threshold(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert should_promote(dom_score=96, visual_score=91) is True

    def test_dom_below_threshold(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert should_promote(dom_score=90, visual_score=95) is False

    def test_visual_below_threshold(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert should_promote(dom_score=96, visual_score=85) is False

    def test_visual_none(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert should_promote(dom_score=100, visual_score=None) is False

    def test_custom_thresholds(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert (
            should_promote(dom_score=80, visual_score=80, dom_threshold=80, visual_threshold=80)
            is True
        )

    def test_exact_threshold(self) -> None:
        from dazzle.core.composition_references import should_promote

        assert should_promote(dom_score=95, visual_score=90) is True


class TestPromoteSection:
    """Test section promotion to reference library."""

    def test_promotes_existing_image(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import promote_section

        # Create a fake screenshot
        img_path = tmp_path / "screenshot.png"
        img_path.write_bytes(b"\x89PNG fake data")

        ref_dir = tmp_path / "refs"
        result = promote_section(
            image_path=img_path,
            section_type="hero",
            ref_dir=ref_dir,
            source="test-project",
            description="A great hero section",
        )

        assert result is not None
        assert result.label == "good"
        assert result.section_type == "hero"
        assert result.source == "test-project"

        # Check manifest was created
        manifest = json.loads((ref_dir / "hero" / "manifest.json").read_text())
        assert len(manifest["references"]) == 1

    def test_nonexistent_image_returns_none(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import promote_section

        result = promote_section(
            image_path=tmp_path / "missing.png",
            section_type="hero",
            ref_dir=tmp_path / "refs",
        )
        assert result is None

    def test_appends_to_existing_manifest(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import promote_section

        ref_dir = tmp_path / "refs"
        hero_dir = ref_dir / "hero"
        hero_dir.mkdir(parents=True)

        # Existing manifest
        manifest = {
            "section_type": "hero",
            "references": [
                {
                    "filename": "old.png",
                    "label": "good",
                    "section_type": "hero",
                    "dimensions": [],
                    "description": "old",
                    "source": "old",
                }
            ],
        }
        (hero_dir / "manifest.json").write_text(json.dumps(manifest))

        img_path = tmp_path / "new.png"
        img_path.write_bytes(b"\x89PNG data")

        promote_section(
            image_path=img_path,
            section_type="hero",
            ref_dir=ref_dir,
        )

        data = json.loads((hero_dir / "manifest.json").read_text())
        assert len(data["references"]) == 2


# ── Token Estimation Tests ───────────────────────────────────────────


class TestEstimateTokens:
    """Test token cost estimation."""

    def test_empty_references(self) -> None:
        from dazzle.core.composition_references import estimate_reference_tokens

        assert estimate_reference_tokens({}) == 0

    def test_single_section(self) -> None:
        from dazzle.core.composition_references import ReferenceImage, estimate_reference_tokens

        refs = {
            "hero": [
                ReferenceImage("a.png", "good", "hero", [], "", ""),
                ReferenceImage("b.png", "bad", "hero", [], "", ""),
            ]
        }
        assert estimate_reference_tokens(refs) == 2 * 680

    def test_multiple_sections(self) -> None:
        from dazzle.core.composition_references import ReferenceImage, estimate_reference_tokens

        refs = {
            "hero": [ReferenceImage("a.png", "good", "hero", [], "", "")],
            "features": [
                ReferenceImage("b.png", "good", "features", [], "", ""),
                ReferenceImage("c.png", "bad", "features", [], "", ""),
            ],
        }
        assert estimate_reference_tokens(refs) == 3 * 680

    def test_custom_tokens_per_image(self) -> None:
        from dazzle.core.composition_references import ReferenceImage, estimate_reference_tokens

        refs = {"hero": [ReferenceImage("a.png", "good", "hero", [], "", "")]}
        assert estimate_reference_tokens(refs, tokens_per_image=1000) == 1000


# ── Bootstrap Tests ──────────────────────────────────────────────────


class TestBootstrapReferences:
    """Test synthetic reference image generation."""

    def test_creates_all_section_types(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        result = bootstrap_references(tmp_path)

        expected_types = {"hero", "features", "pricing", "cta", "testimonials", "steps"}
        assert set(result.keys()) == expected_types

    def test_creates_correct_counts(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        result = bootstrap_references(tmp_path)

        total = sum(len(refs) for refs in result.values())
        assert total == 18

        good = sum(1 for refs in result.values() for r in refs if r.label == "good")
        bad = sum(1 for refs in result.values() for r in refs if r.label == "bad")
        assert good == 10
        assert bad == 8

    def test_creates_manifest_files(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        bootstrap_references(tmp_path)

        for section_type in ["hero", "features", "pricing", "cta", "testimonials", "steps"]:
            manifest_path = tmp_path / section_type / "manifest.json"
            assert manifest_path.exists(), f"Missing manifest for {section_type}"
            data = json.loads(manifest_path.read_text())
            assert data["section_type"] == section_type
            assert len(data["references"]) > 0

    def test_creates_png_files(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        bootstrap_references(tmp_path)

        total_pngs = 0
        for section_dir in tmp_path.iterdir():
            if section_dir.is_dir():
                pngs = list(section_dir.glob("*.png"))
                total_pngs += len(pngs)
                for png in pngs:
                    data = png.read_bytes()
                    assert data[:4] == b"\x89PNG", f"{png} is not valid PNG"

        assert total_pngs == 18

    def test_images_have_correct_dimensions(self, tmp_path: Path) -> None:
        from PIL import Image

        from dazzle.core.composition_references_bootstrap import SECTION_WIDTH, bootstrap_references

        bootstrap_references(tmp_path)

        for section_dir in tmp_path.iterdir():
            if section_dir.is_dir():
                for png in section_dir.glob("*.png"):
                    with Image.open(png) as img:
                        assert img.size[0] == SECTION_WIDTH, f"{png.name} width != {SECTION_WIDTH}"
                        assert img.size[1] > 0

    def test_reference_images_have_dimensions_list(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        result = bootstrap_references(tmp_path)

        for refs in result.values():
            for ref in refs:
                assert len(ref.dimensions) > 0, f"{ref.filename} has no dimensions"
                for dim in ref.dimensions:
                    assert dim in {
                        "content_rendering",
                        "icon_media",
                        "color_consistency",
                        "layout_overflow",
                        "visual_hierarchy",
                        "responsive_fidelity",
                    }

    def test_idempotent_overwrite(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        result1 = bootstrap_references(tmp_path)
        result2 = bootstrap_references(tmp_path)

        # Should produce same structure
        assert set(result1.keys()) == set(result2.keys())
        for sec_type in result1:
            assert len(result1[sec_type]) == len(result2[sec_type])

    def test_loadable_after_bootstrap(self, tmp_path: Path) -> None:
        from dazzle.core.composition_references import load_references
        from dazzle.core.composition_references_bootstrap import bootstrap_references

        bootstrap_references(tmp_path)
        loaded = load_references(tmp_path)

        assert "hero" in loaded
        assert "features" in loaded
        # All should have base64 loaded
        for refs in loaded.values():
            for ref in refs:
                assert len(ref.base64) > 0


# ── Reference Integration in Visual Eval Tests ──────────────────────


class TestReferenceIntegration:
    """Test that references are passed through the visual eval pipeline."""

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_references_included_in_api_call(self, mock_api: Any) -> None:
        from dazzle.core.composition_capture import CapturedSection
        from dazzle.core.composition_references import ReferenceImage
        from dazzle.core.composition_visual import _evaluate_section_dimension

        mock_api.return_value = ('{"findings": []}', 100)

        # Create a fake section screenshot
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Minimal 1x1 PNG
            from PIL import Image

            img = Image.new("RGB", (100, 100), (255, 255, 255))
            img.save(f.name)
            section_path = f.name

        section = CapturedSection(
            section_type="hero",
            path=section_path,
            width=100,
            height=100,
            tokens_est=100,
        )

        ref = ReferenceImage(
            filename="good-test.png",
            label="good",
            section_type="hero",
            dimensions=["content_rendering"],
            description="A good hero section",
            source="test",
            _base64_cache="REFBASE64DATA",
        )

        _evaluate_section_dimension(
            section=section,
            dimension="content_rendering",
            spec_context={},
            references=[ref],
            api_key="test-key",
            model="test-model",
        )

        # Verify API was called with reference image + target image
        assert mock_api.called
        call_args = mock_api.call_args
        images = call_args.kwargs.get("images") or call_args[0][0]
        assert len(images) == 2  # 1 reference + 1 target
        assert images[0][0] == "REFBASE64DATA"  # reference first
        # Prompt should mention references
        prompt = call_args.kwargs.get("prompt") or call_args[0][1]
        assert "reference examples" in prompt.lower()

        # Cleanup
        Path(section_path).unlink(missing_ok=True)

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_irrelevant_references_excluded(self, mock_api: Any) -> None:
        from dazzle.core.composition_capture import CapturedSection
        from dazzle.core.composition_references import ReferenceImage
        from dazzle.core.composition_visual import _evaluate_section_dimension

        mock_api.return_value = ('{"findings": []}', 100)

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            from PIL import Image

            img = Image.new("RGB", (100, 100), (255, 255, 255))
            img.save(f.name)
            section_path = f.name

        section = CapturedSection(
            section_type="hero",
            path=section_path,
            width=100,
            height=100,
            tokens_est=100,
        )

        # Reference only relevant to "icon_media", not "content_rendering"
        ref = ReferenceImage(
            filename="icon-ref.png",
            label="good",
            section_type="hero",
            dimensions=["icon_media"],
            description="Icon reference",
            source="test",
            _base64_cache="ICONBASE64",
        )

        _evaluate_section_dimension(
            section=section,
            dimension="content_rendering",
            spec_context={},
            references=[ref],
            api_key="test-key",
            model="test-model",
        )

        # Only the target image should be sent (ref doesn't match dimension)
        call_args = mock_api.call_args
        images = call_args.kwargs.get("images") or call_args[0][0]
        assert len(images) == 1  # Only target, no matching refs
        # Prompt should NOT mention references
        prompt = call_args.kwargs.get("prompt") or call_args[0][1]
        assert "reference examples" not in prompt.lower()

        Path(section_path).unlink(missing_ok=True)

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_no_references_works(self, mock_api: Any) -> None:
        from dazzle.core.composition_capture import CapturedSection
        from dazzle.core.composition_visual import _evaluate_section_dimension

        mock_api.return_value = ('{"findings": []}', 100)

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            from PIL import Image

            img = Image.new("RGB", (100, 100), (255, 255, 255))
            img.save(f.name)
            section_path = f.name

        section = CapturedSection(
            section_type="hero",
            path=section_path,
            width=100,
            height=100,
            tokens_est=100,
        )

        _evaluate_section_dimension(
            section=section,
            dimension="content_rendering",
            spec_context={},
            references=None,
            api_key="test-key",
            model="test-model",
        )

        call_args = mock_api.call_args
        images = call_args.kwargs.get("images") or call_args[0][0]
        assert len(images) == 1  # Just the target

        Path(section_path).unlink(missing_ok=True)

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_evaluate_captures_passes_references(self, mock_api: Any) -> None:
        from dazzle.core.composition_capture import CapturedPage, CapturedSection
        from dazzle.core.composition_references import ReferenceImage
        from dazzle.core.composition_visual import evaluate_captures

        mock_api.return_value = ('{"findings": []}', 100)

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            from PIL import Image

            img = Image.new("RGB", (100, 100), (255, 255, 255))
            img.save(f.name)
            section_path = f.name

        page = CapturedPage(route="/", viewport="desktop")
        page.sections.append(
            CapturedSection(
                section_type="hero",
                path=section_path,
                width=100,
                height=100,
                tokens_est=100,
            )
        )

        refs = {
            "hero": [
                ReferenceImage(
                    filename="good.png",
                    label="good",
                    section_type="hero",
                    dimensions=["content_rendering"],
                    description="A good hero",
                    source="test",
                    _base64_cache="REFDATA",
                )
            ]
        }

        evaluate_captures(
            [page],
            dimensions=["content_rendering"],
            references=refs,
            api_key="test-key",
        )

        # Verify the reference was passed through
        assert mock_api.called
        call_args = mock_api.call_args
        images = call_args.kwargs.get("images") or call_args[0][0]
        assert len(images) == 2  # ref + target

        Path(section_path).unlink(missing_ok=True)


# ── Bootstrap MCP Handler Tests ──────────────────────────────────────


class TestBootstrapHandler:
    """Test the bootstrap MCP operation."""

    def test_bootstrap_creates_references(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.composition import bootstrap_composition_handler

        result = bootstrap_composition_handler(tmp_path, {"operation": "bootstrap"})
        data = json.loads(result)

        assert data["status"] == "created"
        assert data["total_references"] == 18
        assert data["good"] == 10
        assert data["bad"] == 8
        assert len(data["section_types"]) == 6
        assert data["estimated_tokens"] > 0
        assert "Bootstrapped" in data["summary"]

    def test_bootstrap_existing_no_overwrite(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.composition import bootstrap_composition_handler

        # First bootstrap
        bootstrap_composition_handler(tmp_path, {"operation": "bootstrap"})

        # Second without overwrite
        result = bootstrap_composition_handler(tmp_path, {"operation": "bootstrap"})
        data = json.loads(result)

        assert data["status"] == "exists"
        assert "already exists" in data["summary"]

    def test_bootstrap_overwrite(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.composition import bootstrap_composition_handler

        # First bootstrap
        bootstrap_composition_handler(tmp_path, {"operation": "bootstrap"})

        # Second with overwrite
        result = bootstrap_composition_handler(
            tmp_path, {"operation": "bootstrap", "overwrite": True}
        )
        data = json.loads(result)

        assert data["status"] == "created"
        assert data["total_references"] == 18


# ── Drawing Helper Tests ─────────────────────────────────────────────


class TestDrawingHelpers:
    """Test PIL drawing helpers don't crash."""

    def test_draw_rect(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_rect

        img = Image.new("RGB", (100, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_rect(draw, 10, 10, 50, 50, (0, 0, 0))
        # No assertion — just verify it doesn't crash

    def test_draw_text_block(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_text_block

        img = Image.new("RGB", (200, 200), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_text_block(draw, 10, 10, 100, 40, (0, 0, 0), lines=3)

    def test_draw_button(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_button

        img = Image.new("RGB", (200, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_button(draw, 10, 10, 80, 40, (0, 0, 255))

    def test_draw_icon_circle(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_icon_circle

        img = Image.new("RGB", (100, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_icon_circle(draw, 50, 50, 20, (0, 128, 0))

    def test_draw_card(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_card

        img = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_card(draw, 10, 10, 200, 150, has_icon=True, highlighted=True)

    def test_draw_card_without_icon(self) -> None:
        from PIL import Image, ImageDraw

        from dazzle.core.composition_references_bootstrap import _draw_card

        img = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        _draw_card(draw, 10, 10, 200, 150, has_icon=False)
