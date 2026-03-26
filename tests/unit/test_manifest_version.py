"""Tests for framework version pinning (#440)."""

from unittest.mock import patch

import pytest

from dazzle.core.manifest import ProjectManifest, check_framework_version


def _make_manifest(framework_version: str | None = None) -> ProjectManifest:
    """Create a minimal ProjectManifest for testing."""
    return ProjectManifest(
        name="test",
        version="1.0.0",
        project_root=".",
        module_paths=["./dsl"],
        framework_version=framework_version,
    )


class TestCheckFrameworkVersion:
    """Tests for check_framework_version()."""

    def test_no_constraint_is_noop(self):
        """No framework_version set → no check, no error."""
        manifest = _make_manifest(None)
        check_framework_version(manifest)  # should not raise

    @patch("dazzle.core.manifest.version", return_value="0.38.1")
    def test_tilde_constraint_satisfied(self, mock_ver):
        """~0.38 allows 0.38.x."""
        manifest = _make_manifest("~0.38")
        check_framework_version(manifest)  # should not raise

    @patch("dazzle.core.manifest.version", return_value="0.39.0")
    def test_tilde_constraint_violated(self, mock_ver):
        """~0.38 rejects 0.39.0."""
        manifest = _make_manifest("~0.38")
        with pytest.raises(SystemExit, match="version mismatch"):
            check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="0.37.5")
    def test_tilde_constraint_too_old(self, mock_ver):
        """~0.38 rejects 0.37.5."""
        manifest = _make_manifest("~0.38")
        with pytest.raises(SystemExit, match="version mismatch"):
            check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="0.38.1")
    def test_specifier_set_satisfied(self, mock_ver):
        """>=0.38.0,<1.0 allows 0.38.1."""
        manifest = _make_manifest(">=0.38.0,<1.0")
        check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="1.0.0")
    def test_specifier_set_violated(self, mock_ver):
        """>=0.38.0,<1.0 rejects 1.0.0."""
        manifest = _make_manifest(">=0.38.0,<1.0")
        with pytest.raises(SystemExit, match="version mismatch"):
            check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="0.38.1")
    def test_exact_version_satisfied(self, mock_ver):
        """==0.38.1 is satisfied."""
        manifest = _make_manifest("==0.38.1")
        check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="0.38.2")
    def test_exact_version_violated(self, mock_ver):
        """==0.38.1 rejects 0.38.2."""
        manifest = _make_manifest("==0.38.1")
        with pytest.raises(SystemExit, match="version mismatch"):
            check_framework_version(manifest)

    @patch("dazzle.core.manifest.version", return_value="2.0.0")
    def test_tilde_major_only(self, mock_ver):
        """~1 allows 1.x but not 2.x."""
        manifest = _make_manifest("~1")
        with pytest.raises(SystemExit, match="version mismatch"):
            check_framework_version(manifest)
