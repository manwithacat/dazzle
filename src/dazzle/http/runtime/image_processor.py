"""
Image processing utilities for the Dazzle runtime.

Provides thumbnail generation.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal

logger = logging.getLogger(__name__)
if TYPE_CHECKING:
    from PIL import Image


class ImageProcessingError(Exception):
    """Raised when image processing fails."""

    pass


class ImageProcessor:
    """Process images for thumbnails and optimization."""

    @staticmethod
    def generate_thumbnail(
        image_data: bytes,
        width: int = 200,
        height: int = 200,
        format: Literal["JPEG", "PNG", "WEBP"] = "JPEG",
        quality: int = 85,
    ) -> bytes:
        """
        Generate a thumbnail from image data.

        The thumbnail preserves aspect ratio and fits within the
        specified dimensions.

        Args:
            image_data: Original image bytes
            width: Maximum width
            height: Maximum height
            format: Output format
            quality: JPEG quality (1-100)

        Returns:
            Thumbnail image bytes

        Raises:
            ImageProcessingError: If processing fails
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImageProcessingError(
                "Pillow is required for image processing. Install with: pip install Pillow"
            )

        try:
            img: Image.Image = Image.open(BytesIO(image_data))

            # Handle EXIF orientation
            img = ImageProcessor._apply_exif_orientation(img)

            # Convert to RGB if necessary (for JPEG)
            if format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparent images
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background

            # Thumbnail preserves aspect ratio
            img.thumbnail((width, height), Image.Resampling.LANCZOS)

            output = BytesIO()
            save_kwargs: dict[str, Any] = {"format": format}
            if format in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality
            if format == "JPEG":
                save_kwargs["optimize"] = True

            img.save(output, **save_kwargs)
            output.seek(0)

            return output.read()

        except Exception as e:
            raise ImageProcessingError(f"Failed to generate thumbnail: {e}")

    @staticmethod
    def _apply_exif_orientation(img: Image.Image) -> Image.Image:
        """Apply EXIF orientation to image."""
        try:
            from PIL import ExifTags

            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == "Orientation":
                    break

            exif = img.getexif()
            if exif is None:
                return img

            orientation_value = exif.get(orientation)
            if orientation_value is None:
                return img

            if orientation_value == 3:
                img = img.rotate(180, expand=True)
            elif orientation_value == 6:
                img = img.rotate(270, expand=True)
            elif orientation_value == 8:
                img = img.rotate(90, expand=True)

            return img

        except Exception:
            # If anything goes wrong, return original
            return img


# =============================================================================
# Thumbnail Service
# =============================================================================


class ThumbnailService:
    """
    Service for managing thumbnails.

    Integrates with FileService to generate and store thumbnails.
    """

    def __init__(
        self,
        width: int = 200,
        height: int = 200,
        format: Literal["JPEG", "PNG", "WEBP"] = "JPEG",
        quality: int = 85,
    ):
        """
        Initialize thumbnail service.

        Args:
            width: Default thumbnail width
            height: Default thumbnail height
            format: Default output format
            quality: Default compression quality
        """
        self.width = width
        self.height = height
        self.format = format
        self.quality = quality

    def generate(
        self,
        image_data: bytes,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes:
        """
        Generate a thumbnail.

        Args:
            image_data: Original image bytes
            width: Optional custom width
            height: Optional custom height

        Returns:
            Thumbnail bytes
        """
        return ImageProcessor.generate_thumbnail(
            image_data,
            width=width or self.width,
            height=height or self.height,
            format=self.format,
            quality=self.quality,
        )

    def should_generate(self, content_type: str) -> bool:
        """
        Check if thumbnail should be generated for content type.

        Args:
            content_type: MIME type

        Returns:
            True if thumbnail should be generated
        """
        supported = {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/bmp",
            "image/tiff",
        }
        return content_type.lower() in supported
