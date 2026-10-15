"""
Tests for image processor.

Tests thumbnail generation, optimization, and format conversion. Sizes are
pinned exactly: Pillow's ``thumbnail`` fits inside the box, keeps the aspect
ratio and never upscales.
"""

from io import BytesIO

import pytest

# Pillow ships with the `signing` / `viewport` extras, not core.
Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")

from dazzle.http.runtime.image_processor import (  # noqa: E402
    ImageProcessingError,
    ImageProcessor,
    ThumbnailService,
)


def _png(width: int, height: int, mode: str = "RGB", color: object = "blue") -> bytes:
    buffer = BytesIO()
    if mode == "P":
        Image.new(mode, (width, height)).save(buffer, format="PNG")
    else:
        Image.new(mode, (width, height), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _open(data: bytes) -> tuple[tuple[int, int], str, str]:
    img = Image.open(BytesIO(data))
    return img.size, img.format, img.mode


LANDSCAPE = (800, 600, "RGB")
RGBA = (200, 200, "RGBA")


# =============================================================================
# ImageProcessor
# =============================================================================


def test_is_available() -> None:
    assert ImageProcessor.is_available() is True


@pytest.mark.parametrize(
    ("source", "box", "fmt", "expected"),
    [
        pytest.param(
            LANDSCAPE, 200, None, ((200, 150), "JPEG", "RGB"), id="default-jpeg-keeps-4x3"
        ),
        pytest.param(LANDSCAPE, 100, "PNG", ((100, 75), "PNG", "RGB"), id="png"),
        pytest.param(LANDSCAPE, 100, "WEBP", ((100, 75), "WEBP", "RGB"), id="webp"),
        pytest.param(LANDSCAPE, 10, "JPEG", ((10, 8), "JPEG", "RGB"), id="tiny-box"),
        pytest.param(LANDSCAPE, 2000, "JPEG", ((800, 600), "JPEG", "RGB"), id="no-upscale"),
        pytest.param((1, 1, "RGB"), 100, None, ((1, 1), "JPEG", "RGB"), id="single-pixel"),
        pytest.param(RGBA, 100, "JPEG", ((100, 100), "JPEG", "RGB"), id="rgba-to-jpeg-drops-alpha"),
        pytest.param((100, 100, "P"), 50, "JPEG", ((50, 50), "JPEG", "RGB"), id="palette-to-rgb"),
    ],
)
def test_generate_thumbnail(source, box, fmt, expected) -> None:
    kwargs = {"format": fmt} if fmt else {}
    thumbnail = ImageProcessor.generate_thumbnail(_png(*source), width=box, height=box, **kwargs)
    assert _open(thumbnail) == expected


def test_invalid_image_data_raises() -> None:
    with pytest.raises(ImageProcessingError):
        ImageProcessor.generate_thumbnail(b"not an image", 100, 100)


@pytest.mark.parametrize(
    ("source", "max_dimension", "size"),
    [
        pytest.param((4000, 3000, "RGB"), 1024, (1024, 768), id="downscale-to-max-1024"),
        pytest.param((4000, 3000, "RGB"), 1000, (1000, 750), id="downscale-keeps-4x3"),
        pytest.param(LANDSCAPE, 2048, (800, 600), id="small-image-not-resized"),
    ],
)
def test_optimize_image(source, max_dimension, size) -> None:
    original = _png(*source)
    optimized = ImageProcessor.optimize_image(original, max_dimension=max_dimension)
    assert _open(optimized)[0] == size
    if size != source[:2]:
        assert len(optimized) < len(original)


def test_get_dimensions_and_format() -> None:
    data = _png(*LANDSCAPE)
    assert ImageProcessor.get_dimensions(data) == (800, 600)
    assert ImageProcessor.get_format(data) == "PNG"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(LANDSCAPE, ((800, 600), "JPEG", "RGB"), id="png-to-jpeg"),
        pytest.param(RGBA, ((200, 200), "JPEG", "RGB"), id="rgba-to-jpeg-drops-alpha"),
    ],
)
def test_convert_format(source, expected) -> None:
    assert _open(ImageProcessor.convert_format(_png(*source), "JPEG")) == expected


@pytest.mark.parametrize(
    ("source", "size"),
    [
        pytest.param(LANDSCAPE, 150, id="from-landscape"),
        pytest.param((300, 500, "RGB"), 100, id="from-portrait"),
    ],
)
def test_crop_to_square(source, size) -> None:
    assert _open(ImageProcessor.crop_to_square(_png(*source), size=size))[0] == (size, size)


# =============================================================================
# ThumbnailService
# =============================================================================


@pytest.mark.parametrize(
    ("kwargs", "settings"),
    [
        pytest.param({}, (200, 200, "JPEG", 85), id="defaults"),
        pytest.param(
            {"width": 300, "height": 300, "format": "PNG", "quality": 90},
            (300, 300, "PNG", 90),
            id="custom",
        ),
    ],
)
def test_thumbnail_service_settings(kwargs, settings) -> None:
    service = ThumbnailService(**kwargs)
    assert (service.width, service.height, service.format, service.quality) == settings


@pytest.mark.parametrize(
    ("service_box", "call_box", "size"),
    [
        pytest.param(100, None, (100, 75), id="service-size"),
        pytest.param(200, 50, (50, 38), id="per-call-override"),
    ],
)
def test_thumbnail_service_generate(service_box, call_box, size) -> None:
    service = ThumbnailService(width=service_box, height=service_box)
    kwargs = {"width": call_box, "height": call_box} if call_box else {}
    assert _open(service.generate(_png(*LANDSCAPE), **kwargs))[0] == size


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        pytest.param("image/jpeg", True, id="jpeg"),
        pytest.param("image/png", True, id="png"),
        pytest.param("image/gif", True, id="gif"),
        pytest.param("image/webp", True, id="webp"),
        pytest.param("IMAGE/JPEG", True, id="case-insensitive"),
        pytest.param("application/pdf", False, id="pdf"),
        pytest.param("text/plain", False, id="text"),
        pytest.param("video/mp4", False, id="video"),
    ],
)
def test_should_generate(content_type, expected) -> None:
    assert ThumbnailService().should_generate(content_type) is expected
