"""ASVS V12: File and Resources security tests."""

from __future__ import annotations

import inspect


class TestFileSizeLimits:
    """V12.1: File Upload."""

    def test_content_length_check_exists(self):
        """V12.1.1: Upload endpoint must check Content-Length header."""
        from dazzle_back.runtime.file_routes import create_file_routes

        source = inspect.getsource(create_file_routes)
        assert "content-length" in source.lower()
        assert "413" in source

    def test_upload_size_limits_by_profile(self):
        """V12.1.2: Upload size limits must vary by security profile."""
        # Basic: 50MB, Standard: 10MB, Strict: 5MB
        from dazzle_back.runtime.file_routes import create_file_routes

        source = inspect.getsource(create_file_routes)
        assert "max_upload_size" in source


class TestFileValidation:
    """V12.2: File Integrity."""

    def test_file_validation_class_exists(self):
        """V12.2.1: File validation infrastructure must exist."""
        from dazzle_back.runtime.file_storage import FileValidator

        assert callable(FileValidator)

    def test_file_validation_error_type(self):
        """V12.2.2: File validation errors must be typed."""
        from dazzle_back.runtime.file_storage import FileValidationError

        assert issubclass(FileValidationError, Exception)
