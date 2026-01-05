"""
Unit tests for infrastructure versioning utilities.
"""

from __future__ import annotations

from pathlib import Path


class TestStackVersion:
    """Test StackVersion dataclass."""

    def test_stack_version_creation(self) -> None:
        """Should create StackVersion with all fields."""
        from dazzle.deploy.versioning import StackVersion

        sv = StackVersion(
            name="Network",
            checksum="abc123",
            generated_at="2024-01-01T00:00:00Z",
            file_path="stacks/network.py",
        )

        assert sv.name == "Network"
        assert sv.checksum == "abc123"
        assert sv.generated_at == "2024-01-01T00:00:00Z"
        assert sv.file_path == "stacks/network.py"


class TestInfraVersion:
    """Test InfraVersion dataclass."""

    def test_infra_version_to_dict(self) -> None:
        """Should serialize to dictionary."""
        from dazzle.deploy.versioning import InfraVersion, StackVersion

        sv = StackVersion(
            name="Network",
            checksum="abc123",
            generated_at="2024-01-01T00:00:00Z",
            file_path="stacks/network.py",
        )

        iv = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[sv],
        )

        result = iv.to_dict()

        assert result["version"] == "v1"
        assert result["dazzle_version"] == "0.5.0"
        assert result["environment"] == "staging"
        assert len(result["stacks"]) == 1
        assert result["stacks"][0]["name"] == "Network"

    def test_infra_version_from_dict(self) -> None:
        """Should deserialize from dictionary."""
        from dazzle.deploy.versioning import InfraVersion

        data = {
            "version": "v2",
            "dazzle_version": "0.5.0",
            "generated_at": "2024-01-01T00:00:00Z",
            "environment": "prod",
            "stacks": [
                {
                    "name": "Data",
                    "checksum": "def456",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "file_path": "stacks/data.py",
                }
            ],
        }

        iv = InfraVersion.from_dict(data)

        assert iv.version == "v2"
        assert iv.environment == "prod"
        assert len(iv.stacks) == 1
        assert iv.stacks[0].name == "Data"

    def test_roundtrip_serialization(self) -> None:
        """Should survive JSON roundtrip."""
        import json

        from dazzle.deploy.versioning import InfraVersion, StackVersion

        original = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion(
                    name="Network",
                    checksum="abc",
                    generated_at="2024-01-01T00:00:00Z",
                    file_path="stacks/network.py",
                ),
                StackVersion(
                    name="Data",
                    checksum="def",
                    generated_at="2024-01-01T00:00:00Z",
                    file_path="stacks/data.py",
                ),
            ],
        )

        # Serialize and deserialize
        json_str = json.dumps(original.to_dict())
        restored = InfraVersion.from_dict(json.loads(json_str))

        assert restored.version == original.version
        assert restored.environment == original.environment
        assert len(restored.stacks) == len(original.stacks)


class TestVersionDiff:
    """Test VersionDiff dataclass."""

    def test_has_changes_with_additions(self) -> None:
        """Should detect changes when stacks added."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff(added=["Network"])

        assert diff.has_changes() is True

    def test_has_changes_with_modifications(self) -> None:
        """Should detect changes when stacks modified."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff(modified=["Data"])

        assert diff.has_changes() is True

    def test_has_changes_with_removals(self) -> None:
        """Should detect changes when stacks removed."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff(removed=["Compute"])

        assert diff.has_changes() is True

    def test_no_changes(self) -> None:
        """Should not detect changes when nothing changed."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff(unchanged=["Network", "Data"])

        assert diff.has_changes() is False

    def test_summary_no_changes(self) -> None:
        """Summary should indicate no changes."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff()

        assert diff.summary() == "No changes"

    def test_summary_with_changes(self) -> None:
        """Summary should list all changes."""
        from dazzle.deploy.versioning import VersionDiff

        diff = VersionDiff(
            added=["TigerBeetle"],
            modified=["Data"],
            removed=["Messaging"],
        )

        summary = diff.summary()

        assert "Added: TigerBeetle" in summary
        assert "Modified: Data" in summary
        assert "Removed: Messaging" in summary


class TestChecksums:
    """Test checksum computation."""

    def test_compute_file_checksum(self, tmp_path: Path) -> None:
        """Should compute consistent checksum for file."""
        from dazzle.deploy.versioning import compute_file_checksum

        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        checksum1 = compute_file_checksum(test_file)
        checksum2 = compute_file_checksum(test_file)

        assert checksum1 == checksum2
        assert len(checksum1) == 16  # Shortened checksum

    def test_checksum_changes_with_content(self, tmp_path: Path) -> None:
        """Checksum should change when file content changes."""
        from dazzle.deploy.versioning import compute_file_checksum

        test_file = tmp_path / "test.py"

        test_file.write_text("version 1")
        checksum1 = compute_file_checksum(test_file)

        test_file.write_text("version 2")
        checksum2 = compute_file_checksum(test_file)

        assert checksum1 != checksum2

    def test_compute_content_checksum(self) -> None:
        """Should compute consistent checksum for string content."""
        from dazzle.deploy.versioning import compute_content_checksum

        checksum1 = compute_content_checksum("hello world")
        checksum2 = compute_content_checksum("hello world")

        assert checksum1 == checksum2
        assert len(checksum1) == 16


class TestVersionComparison:
    """Test version comparison."""

    def test_compare_versions_first_deploy(self) -> None:
        """First deploy should show all stacks as added."""
        from dazzle.deploy.versioning import InfraVersion, StackVersion, compare_versions

        new = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-01T00:00:00Z", "stacks/network.py"),
                StackVersion("Data", "def", "2024-01-01T00:00:00Z", "stacks/data.py"),
            ],
        )

        diff = compare_versions(None, new)

        assert diff.added == ["Data", "Network"]
        assert diff.modified == []
        assert diff.removed == []
        assert diff.unchanged == []

    def test_compare_versions_no_changes(self) -> None:
        """Same checksums should show no changes."""
        from dazzle.deploy.versioning import InfraVersion, StackVersion, compare_versions

        old = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-01T00:00:00Z", "stacks/network.py"),
            ],
        )

        new = InfraVersion(
            version="v2",
            dazzle_version="0.5.0",
            generated_at="2024-01-02T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-02T00:00:00Z", "stacks/network.py"),
            ],
        )

        diff = compare_versions(old, new)

        assert diff.added == []
        assert diff.modified == []
        assert diff.removed == []
        assert diff.unchanged == ["Network"]

    def test_compare_versions_with_modifications(self) -> None:
        """Changed checksums should show as modified."""
        from dazzle.deploy.versioning import InfraVersion, StackVersion, compare_versions

        old = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-01T00:00:00Z", "stacks/network.py"),
            ],
        )

        new = InfraVersion(
            version="v2",
            dazzle_version="0.5.0",
            generated_at="2024-01-02T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "xyz", "2024-01-02T00:00:00Z", "stacks/network.py"),
            ],
        )

        diff = compare_versions(old, new)

        assert diff.added == []
        assert diff.modified == ["Network"]
        assert diff.removed == []
        assert diff.unchanged == []

    def test_compare_versions_with_additions_and_removals(self) -> None:
        """Should detect added and removed stacks."""
        from dazzle.deploy.versioning import InfraVersion, StackVersion, compare_versions

        old = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-01T00:00:00Z", "stacks/network.py"),
                StackVersion("Messaging", "def", "2024-01-01T00:00:00Z", "stacks/messaging.py"),
            ],
        )

        new = InfraVersion(
            version="v2",
            dazzle_version="0.5.0",
            generated_at="2024-01-02T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-02T00:00:00Z", "stacks/network.py"),
                StackVersion("TigerBeetle", "ghi", "2024-01-02T00:00:00Z", "stacks/tigerbeetle.py"),
            ],
        )

        diff = compare_versions(old, new)

        assert diff.added == ["TigerBeetle"]
        assert diff.modified == []
        assert diff.removed == ["Messaging"]
        assert diff.unchanged == ["Network"]


class TestVersionFileIO:
    """Test version file save/load."""

    def test_save_and_load_version_file(self, tmp_path: Path) -> None:
        """Should save and load version file correctly."""
        from dazzle.deploy.versioning import (
            InfraVersion,
            StackVersion,
            load_version_file,
            save_version_file,
        )

        version = InfraVersion(
            version="v1",
            dazzle_version="0.5.0",
            generated_at="2024-01-01T00:00:00Z",
            environment="staging",
            stacks=[
                StackVersion("Network", "abc", "2024-01-01T00:00:00Z", "stacks/network.py"),
            ],
        )

        save_version_file(version, tmp_path)
        loaded = load_version_file(tmp_path)

        assert loaded is not None
        assert loaded.version == version.version
        assert loaded.environment == version.environment
        assert len(loaded.stacks) == 1
        assert loaded.stacks[0].name == "Network"

    def test_load_version_file_not_found(self, tmp_path: Path) -> None:
        """Should return None when version file doesn't exist."""
        from dazzle.deploy.versioning import load_version_file

        loaded = load_version_file(tmp_path)

        assert loaded is None


class TestCreateInfraVersion:
    """Test create_infra_version function."""

    def test_create_version_from_stacks(self, tmp_path: Path) -> None:
        """Should create version metadata from generated stacks."""
        from dazzle.deploy.versioning import create_infra_version

        # Create stacks directory with some files
        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()

        (stacks_dir / "network.py").write_text("class NetworkStack: pass")
        (stacks_dir / "data.py").write_text("class DataStack: pass")
        (stacks_dir / "__init__.py").write_text("")  # Should be ignored

        version = create_infra_version(tmp_path, "staging", "0.5.0")

        assert version.environment == "staging"
        assert version.dazzle_version == "0.5.0"
        assert len(version.stacks) == 2

        stack_names = {s.name for s in version.stacks}
        assert "Network" in stack_names
        assert "Data" in stack_names

    def test_create_version_empty_dir(self, tmp_path: Path) -> None:
        """Should handle empty or missing stacks directory."""
        from dazzle.deploy.versioning import create_infra_version

        version = create_infra_version(tmp_path, "dev", "0.5.0")

        assert version.environment == "dev"
        assert len(version.stacks) == 0


class TestCheckForChanges:
    """Test check_for_changes function."""

    def test_first_generation_has_changes(self, tmp_path: Path) -> None:
        """First generation should report changes (all stacks added)."""
        from dazzle.deploy.versioning import check_for_changes

        # Create stacks directory with one stack
        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()
        (stacks_dir / "network.py").write_text("class NetworkStack: pass")

        has_changes, diff, new_version = check_for_changes(tmp_path, "staging")

        assert has_changes is True
        assert "Network" in diff.added

    def test_no_changes_after_save(self, tmp_path: Path) -> None:
        """Should report no changes when stacks haven't changed."""
        from dazzle.deploy.versioning import check_for_changes, save_version_file

        # Create stacks directory
        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()
        (stacks_dir / "network.py").write_text("class NetworkStack: pass")

        # First check and save
        _, _, first_version = check_for_changes(tmp_path, "staging")
        save_version_file(first_version, tmp_path)

        # Second check should show no changes
        has_changes, diff, _ = check_for_changes(tmp_path, "staging")

        assert has_changes is False
        assert diff.unchanged == ["Network"]
