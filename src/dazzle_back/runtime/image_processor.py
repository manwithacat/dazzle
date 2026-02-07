"""
Image processing utilities for DNR.

Provides thumbnail generation and image optimization.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from PIL import Image


class ImageProcessingError(Exception):
    """Raised when image processing fails."""

    pass


class ImageProcessor:
    """Process images for thumbnails and optimization."""

    @staticmethod
    def is_available() -> bool:
        """Check if Pillow is available."""
        try:
            from PIL import Image  # noqa: F401

            return True
        except ImportError:
            return False

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
    def optimize_image(
        image_data: bytes,
        max_dimension: int = 2048,
        format: Literal["JPEG", "PNG", "WEBP"] = "JPEG",
        quality: int = 85,
    ) -> bytes:
        """
        Optimize image for web delivery.

        Resizes large images and compresses for optimal web performance.

        Args:
            image_data: Original image bytes
            max_dimension: Maximum width or height
            format: Output format
            quality: Compression quality

        Returns:
            Optimized image bytes

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

            # Resize if too large
            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to RGB for JPEG
            if format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background

            output = BytesIO()
            save_kwargs: dict[str, Any] = {"format": format}
            if format in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True

            img.save(output, **save_kwargs)
            output.seek(0)

            return output.read()

        except Exception as e:
            raise ImageProcessingError(f"Failed to optimize image: {e}")

    @staticmethod
    def get_dimensions(image_data: bytes) -> tuple[int, int]:
        """
        Get image dimensions.

        Args:
            image_data: Image bytes

        Returns:
            Tuple of (width, height)
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImageProcessingError("Pillow is required for image processing")

        try:
            img = Image.open(BytesIO(image_data))
            return img.size
        except Exception as e:
            raise ImageProcessingError(f"Failed to get dimensions: {e}")

    @staticmethod
    def get_format(image_data: bytes) -> str | None:
        """
        Detect image format.

        Args:
            image_data: Image bytes

        Returns:
            Format string (PNG, JPEG, etc.) or None
        """
        try:
            from PIL import Image
        except ImportError:
            return None

        try:
            img = Image.open(BytesIO(image_data))
            return img.format
        except Exception:
            return None

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

    @staticmethod
    def convert_format(
        image_data: bytes,
        target_format: Literal["JPEG", "PNG", "WEBP", "GIF"],
        quality: int = 85,
    ) -> bytes:
        """
        Convert image to a different format.

        Args:
            image_data: Original image bytes
            target_format: Target format
            quality: Compression quality (for JPEG/WEBP)

        Returns:
            Converted image bytes
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImageProcessingError("Pillow is required for image processing")

        try:
            img: Image.Image = Image.open(BytesIO(image_data))

            # Handle mode conversion
            if target_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background

            output = BytesIO()
            save_kwargs: dict[str, Any] = {"format": target_format}
            if target_format in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality

            img.save(output, **save_kwargs)
            output.seek(0)

            return output.read()

        except Exception as e:
            raise ImageProcessingError(f"Failed to convert format: {e}")

    @staticmethod
    def crop_to_square(
        image_data: bytes,
        size: int = 200,
        format: Literal["JPEG", "PNG", "WEBP"] = "JPEG",
        quality: int = 85,
    ) -> bytes:
        """
        Crop image to a square and resize.

        Crops from the center of the image.

        Args:
            image_data: Original image bytes
            size: Square dimension
            format: Output format
            quality: Compression quality

        Returns:
            Square cropped image bytes
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImageProcessingError("Pillow is required for image processing")

        try:
            img: Image.Image = Image.open(BytesIO(image_data))

            # Handle EXIF orientation
            img = ImageProcessor._apply_exif_orientation(img)

            # Determine crop box (center crop)
            width, height = img.size
            min_dim = min(width, height)

            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim

            img = img.crop((left, top, right, bottom))
            img = img.resize((size, size), Image.Resampling.LANCZOS)

            # Convert to RGB if necessary
            if format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background

            output = BytesIO()
            save_kwargs: dict[str, Any] = {"format": format}
            if format in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality

            img.save(output, **save_kwargs)
            output.seek(0)

            return output.read()

        except Exception as e:
            raise ImageProcessingError(f"Failed to crop image: {e}")


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
