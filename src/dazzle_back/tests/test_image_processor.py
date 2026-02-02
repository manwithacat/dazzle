"""
Tests for image processor.

Tests thumbnail generation, optimization, and format conversion.
"""

from io import BytesIO

import pytest

# Check if Pillow is available
try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from dazzle_back.runtime.image_processor import (
    ImageProcessingError,
    ImageProcessor,
    ThumbnailService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_image():
    """Create a sample image."""
    if not PILLOW_AVAILABLE:
        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (800, 600), color="blue")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def rgba_image():
    """Create an RGBA image with transparency."""
    if not PILLOW_AVAILABLE:
        pytest.skip("Pillow not installed")

    img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def large_image():
    """Create a large image for optimization testing."""
    if not PILLOW_AVAILABLE:
        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (4000, 3000), color="green")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


# =============================================================================
# ImageProcessor Tests
# =============================================================================


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestImageProcessor:
    """Tests for ImageProcessor."""

    def test_is_available(self):
        """Test availability check."""
        assert ImageProcessor.is_available() is True

    def test_generate_thumbnail(self, sample_image):
        """Test thumbnail generation."""
        thumbnail = ImageProcessor.generate_thumbnail(sample_image, width=200, height=200)

        # Verify it's a valid image
        img = Image.open(BytesIO(thumbnail))
        assert img.size[0] <= 200
        assert img.size[1] <= 200

    def test_thumbnail_preserves_aspect_ratio(self, sample_image):
        """Test thumbnail preserves aspect ratio."""
        thumbnail = ImageProcessor.generate_thumbnail(sample_image, width=200, height=200)

        img = Image.open(BytesIO(thumbnail))
        # Original is 800x600 (4:3), so thumbnail should be ~200x150 or ~267x200
        assert img.size[0] <= 200
        assert img.size[1] <= 200
        # Check aspect ratio is approximately preserved
        ratio = img.size[0] / img.size[1]
        assert 1.2 < ratio < 1.5  # Should be ~1.33 (4:3)

    def test_thumbnail_with_rgba(self, rgba_image):
        """Test thumbnail with transparent image."""
        thumbnail = ImageProcessor.generate_thumbnail(
            rgba_image, width=100, height=100, format="JPEG"
        )

        img = Image.open(BytesIO(thumbnail))
        # JPEG should be RGB, not RGBA
        assert img.mode == "RGB"

    def test_thumbnail_png_format(self, sample_image):
        """Test thumbnail in PNG format."""
        thumbnail = ImageProcessor.generate_thumbnail(
            sample_image, width=100, height=100, format="PNG"
        )

        img = Image.open(BytesIO(thumbnail))
        assert img.format == "PNG"

    def test_thumbnail_webp_format(self, sample_image):
        """Test thumbnail in WebP format."""
        thumbnail = ImageProcessor.generate_thumbnail(
            sample_image, width=100, height=100, format="WEBP"
        )

        img = Image.open(BytesIO(thumbnail))
        assert img.format == "WEBP"

    def test_optimize_image(self, large_image):
        """Test image optimization."""
        optimized = ImageProcessor.optimize_image(large_image, max_dimension=1024)

        img = Image.open(BytesIO(optimized))
        assert max(img.size) <= 1024
        assert len(optimized) < len(large_image)

    def test_optimize_preserves_aspect_ratio(self, large_image):
        """Test optimization preserves aspect ratio."""
        optimized = ImageProcessor.optimize_image(large_image, max_dimension=1000)

        img = Image.open(BytesIO(optimized))
        # Original was 4000x3000 (4:3)
        ratio = img.size[0] / img.size[1]
        assert 1.3 < ratio < 1.4  # Should be ~1.33

    def test_optimize_small_image_unchanged(self, sample_image):
        """Test small image not resized during optimization."""
        optimized = ImageProcessor.optimize_image(sample_image, max_dimension=2048)

        img = Image.open(BytesIO(optimized))
        # Should not be larger than original dimensions
        assert img.size[0] <= 800
        assert img.size[1] <= 600

    def test_get_dimensions(self, sample_image):
        """Test getting image dimensions."""
        width, height = ImageProcessor.get_dimensions(sample_image)

        assert width == 800
        assert height == 600

    def test_get_format(self, sample_image):
        """Test format detection."""
        format_name = ImageProcessor.get_format(sample_image)

        assert format_name == "PNG"

    def test_convert_format_png_to_jpeg(self, sample_image):
        """Test converting PNG to JPEG."""
        converted = ImageProcessor.convert_format(sample_image, "JPEG")

        img = Image.open(BytesIO(converted))
        assert img.format == "JPEG"

    def test_convert_format_with_transparency(self, rgba_image):
        """Test converting transparent image to JPEG."""
        converted = ImageProcessor.convert_format(rgba_image, "JPEG")

        img = Image.open(BytesIO(converted))
        assert img.format == "JPEG"
        assert img.mode == "RGB"  # No alpha

    def test_crop_to_square(self, sample_image):
        """Test square crop."""
        cropped = ImageProcessor.crop_to_square(sample_image, size=150)

        img = Image.open(BytesIO(cropped))
        assert img.size == (150, 150)

    def test_crop_to_square_from_portrait(self):
        """Test square crop from portrait image."""
        if not PILLOW_AVAILABLE:
            pytest.skip("Pillow not installed")

        # Create portrait image
        img = Image.new("RGB", (300, 500), color="red")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        cropped = ImageProcessor.crop_to_square(buffer.getvalue(), size=100)

        result = Image.open(BytesIO(cropped))
        assert result.size == (100, 100)

    def test_invalid_image_data(self):
        """Test handling invalid image data."""
        with pytest.raises(ImageProcessingError):
            ImageProcessor.generate_thumbnail(b"not an image", 100, 100)


# =============================================================================
# ThumbnailService Tests
# =============================================================================


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestThumbnailService:
    """Tests for ThumbnailService."""

    def test_default_settings(self):
        """Test default thumbnail settings."""
        service = ThumbnailService()

        assert service.width == 200
        assert service.height == 200
        assert service.format == "JPEG"
        assert service.quality == 85

    def test_custom_settings(self):
        """Test custom thumbnail settings."""
        service = ThumbnailService(width=300, height=300, format="PNG", quality=90)

        assert service.width == 300
        assert service.height == 300
        assert service.format == "PNG"
        assert service.quality == 90

    def test_generate(self, sample_image):
        """Test thumbnail generation via service."""
        service = ThumbnailService(width=100, height=100)
        thumbnail = service.generate(sample_image)

        img = Image.open(BytesIO(thumbnail))
        assert img.size[0] <= 100
        assert img.size[1] <= 100

    def test_generate_custom_size(self, sample_image):
        """Test generation with custom size override."""
        service = ThumbnailService(width=200, height=200)
        thumbnail = service.generate(sample_image, width=50, height=50)

        img = Image.open(BytesIO(thumbnail))
        assert img.size[0] <= 50
        assert img.size[1] <= 50

    def test_should_generate_image_types(self):
        """Test supported image types."""
        service = ThumbnailService()

        assert service.should_generate("image/jpeg") is True
        assert service.should_generate("image/png") is True
        assert service.should_generate("image/gif") is True
        assert service.should_generate("image/webp") is True
        assert service.should_generate("IMAGE/JPEG") is True  # Case insensitive

    def test_should_not_generate_non_images(self):
        """Test non-image types are rejected."""
        service = ThumbnailService()

        assert service.should_generate("application/pdf") is False
        assert service.should_generate("text/plain") is False
        assert service.should_generate("video/mp4") is False


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_very_small_thumbnail(self, sample_image):
        """Test generating very small thumbnail."""
        thumbnail = ImageProcessor.generate_thumbnail(sample_image, width=10, height=10)

        img = Image.open(BytesIO(thumbnail))
        assert img.size[0] <= 10
        assert img.size[1] <= 10

    def test_very_large_dimensions(self, sample_image):
        """Test with dimensions larger than image."""
        thumbnail = ImageProcessor.generate_thumbnail(sample_image, width=2000, height=2000)

        img = Image.open(BytesIO(thumbnail))
        # Should not upscale
        assert img.size[0] <= 800
        assert img.size[1] <= 600

    def test_single_pixel_image(self):
        """Test with minimal image."""
        if not PILLOW_AVAILABLE:
            pytest.skip("Pillow not installed")

        img = Image.new("RGB", (1, 1), color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        thumbnail = ImageProcessor.generate_thumbnail(buffer.getvalue(), width=100, height=100)

        result = Image.open(BytesIO(thumbnail))
        assert result.size == (1, 1)  # Can't upscale

    def test_palette_mode_image(self):
        """Test with palette mode image."""
        if not PILLOW_AVAILABLE:
            pytest.skip("Pillow not installed")

        # Create palette mode image
        img = Image.new("P", (100, 100))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        # Should convert to RGB for JPEG
        thumbnail = ImageProcessor.generate_thumbnail(
            buffer.getvalue(), width=50, height=50, format="JPEG"
        )

        result = Image.open(BytesIO(thumbnail))
        assert result.mode == "RGB"
