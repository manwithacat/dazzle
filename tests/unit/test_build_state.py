"""
Unit tests for the build state module.

Tests state management for incremental generation including:
- File hashing
- State persistence
- AppSpec snapshot generation
"""

import json
from pathlib import Path

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
)
from dazzle.core.state import (
    BuildState,
    StateError,
    clear_state,
    compute_dsl_hashes,
    compute_file_hash,
    get_state_file_path,
    load_state,
    save_state,
    simplify_appspec,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_entity() -> EntitySpec:
    """Create a simple entity for testing."""
    return EntitySpec(
        name="Task",
        title="A task item",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
        ],
    )


@pytest.fixture
def simple_appspec(simple_entity: EntitySpec) -> AppSpec:
    """Create a simple AppSpec for testing."""
    return AppSpec(
        name="Test App",
        title="A test application",
        version="1.0.0",
        domain=DomainSpec(entities=[simple_entity]),
    )


@pytest.fixture
def project_with_dsl(tmp_path: Path) -> Path:
    """Create a temporary project with DSL files."""
    # Create DSL files
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()

    (dsl_dir / "app.dsl").write_text("""
module test
app test "Test App"
""")

    (dsl_dir / "entities.dsl").write_text("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
""")

    return tmp_path


# =============================================================================
# BuildState Tests
# =============================================================================


class TestBuildState:
    """Test BuildState dataclass."""

    def test_create_build_state(self) -> None:
        """Test creating a BuildState."""
        state = BuildState(
            timestamp="2024-01-01T00:00:00Z",
            backend="fastapi",
            output_dir="generated",
            dsl_file_hashes={"app.dsl": "abc123"},
            appspec_snapshot={"app": {"name": "Test"}},
        )

        assert state.timestamp == "2024-01-01T00:00:00Z"
        assert state.backend == "fastapi"
        assert state.output_dir == "generated"
        assert state.dsl_file_hashes == {"app.dsl": "abc123"}
        assert state.appspec_snapshot == {"app": {"name": "Test"}}

    def test_to_dict(self) -> None:
        """Test converting BuildState to dict."""
        state = BuildState(
            timestamp="2024-01-01T00:00:00Z",
            backend="fastapi",
            output_dir="generated",
            dsl_file_hashes={"app.dsl": "abc123"},
            appspec_snapshot=None,
        )

        result = state.to_dict()

        assert isinstance(result, dict)
        assert result["timestamp"] == "2024-01-01T00:00:00Z"
        assert result["backend"] == "fastapi"
        assert result["output_dir"] == "generated"
        assert result["dsl_file_hashes"] == {"app.dsl": "abc123"}
        assert result["appspec_snapshot"] is None

    def test_from_dict(self) -> None:
        """Test creating BuildState from dict."""
        data = {
            "timestamp": "2024-01-01T00:00:00Z",
            "backend": "fastapi",
            "output_dir": "generated",
            "dsl_file_hashes": {"app.dsl": "abc123"},
            "appspec_snapshot": {"app": {"name": "Test"}},
        }

        state = BuildState.from_dict(data)

        assert state.timestamp == "2024-01-01T00:00:00Z"
        assert state.backend == "fastapi"
        assert state.output_dir == "generated"
        assert state.dsl_file_hashes == {"app.dsl": "abc123"}
        assert state.appspec_snapshot == {"app": {"name": "Test"}}

    def test_roundtrip_dict(self) -> None:
        """Test roundtrip conversion to/from dict."""
        original = BuildState(
            timestamp="2024-01-01T00:00:00Z",
            backend="django",
            output_dir="/output",
            dsl_file_hashes={"a.dsl": "x", "b.dsl": "y"},
            appspec_snapshot={"key": "value"},
        )

        roundtrip = BuildState.from_dict(original.to_dict())

        assert roundtrip.timestamp == original.timestamp
        assert roundtrip.backend == original.backend
        assert roundtrip.output_dir == original.output_dir
        assert roundtrip.dsl_file_hashes == original.dsl_file_hashes
        assert roundtrip.appspec_snapshot == original.appspec_snapshot


# =============================================================================
# File Hashing Tests
# =============================================================================


class TestFileHashing:
    """Test file hashing functions."""

    def test_compute_file_hash(self, tmp_path: Path) -> None:
        """Test computing hash of a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        hash_result = compute_file_hash(test_file)

        # SHA256 of "hello world"
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA256 hex string length
        # Same content should produce same hash
        assert hash_result == compute_file_hash(test_file)

    def test_compute_file_hash_different_content(self, tmp_path: Path) -> None:
        """Test that different content produces different hashes."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content one")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content two")

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)

        assert hash1 != hash2

    def test_compute_file_hash_nonexistent(self, tmp_path: Path) -> None:
        """Test hashing nonexistent file raises error."""
        nonexistent = tmp_path / "nonexistent.txt"

        with pytest.raises(StateError) as excinfo:
            compute_file_hash(nonexistent)

        assert "Failed to hash file" in str(excinfo.value)

    def test_compute_dsl_hashes(self, project_with_dsl: Path) -> None:
        """Test computing hashes for multiple DSL files."""
        dsl_files = list((project_with_dsl / "dsl").glob("*.dsl"))

        hashes = compute_dsl_hashes(dsl_files, project_with_dsl)

        assert len(hashes) == 2
        assert "dsl/app.dsl" in hashes
        assert "dsl/entities.dsl" in hashes
        # Each hash should be valid SHA256
        for hash_value in hashes.values():
            assert len(hash_value) == 64

    def test_compute_dsl_hashes_empty_list(self, tmp_path: Path) -> None:
        """Test computing hashes for empty file list."""
        hashes = compute_dsl_hashes([], tmp_path)

        assert hashes == {}


# =============================================================================
# AppSpec Snapshot Tests
# =============================================================================


class TestAppSpecSnapshot:
    """Test AppSpec snapshot generation."""

    def test_simplify_appspec_basic(self, simple_appspec: AppSpec) -> None:
        """Test generating a simplified AppSpec snapshot."""
        snapshot = simplify_appspec(simple_appspec)

        assert isinstance(snapshot, dict)
        assert "app" in snapshot
        assert "entities" in snapshot
        assert "surfaces" in snapshot
        assert "apis" in snapshot
        assert "experiences" in snapshot

    def test_simplify_appspec_app_info(self, simple_appspec: AppSpec) -> None:
        """Test app info in snapshot."""
        snapshot = simplify_appspec(simple_appspec)

        assert snapshot["app"]["name"] == "Test App"
        assert snapshot["app"]["title"] == "A test application"
        assert snapshot["app"]["version"] == "1.0.0"

    def test_simplify_appspec_entities(self, simple_appspec: AppSpec) -> None:
        """Test entity info in snapshot."""
        snapshot = simplify_appspec(simple_appspec)

        assert "Task" in snapshot["entities"]
        task = snapshot["entities"]["Task"]
        assert task["title"] == "A task item"
        assert "fields" in task
        assert "id" in task["fields"]
        assert "title" in task["fields"]
        assert "completed" in task["fields"]

    def test_simplify_appspec_field_details(self, simple_appspec: AppSpec) -> None:
        """Test field details in snapshot."""
        snapshot = simplify_appspec(simple_appspec)

        task = snapshot["entities"]["Task"]

        # Check title field
        title_field = task["fields"]["title"]
        assert title_field["required"] is True
        assert isinstance(title_field["type"], str)
        assert isinstance(title_field["modifiers"], list)

    def test_simplify_appspec_empty_collections(self) -> None:
        """Test snapshot with empty collections."""
        appspec = AppSpec(
            name="Empty App",
            domain=DomainSpec(entities=[]),
        )

        snapshot = simplify_appspec(appspec)

        assert snapshot["entities"] == {}
        assert snapshot["surfaces"] == {}
        assert snapshot["apis"] == {}
        assert snapshot["experiences"] == {}


# =============================================================================
# State File Path Tests
# =============================================================================


class TestStateFilePath:
    """Test state file path resolution."""

    def test_get_state_file_path(self, tmp_path: Path) -> None:
        """Test getting state file path."""
        state_path = get_state_file_path(tmp_path)

        assert state_path == tmp_path / ".dazzle" / "state.json"

    def test_get_state_file_path_absolute(self) -> None:
        """Test state file path is absolute when project root is absolute."""
        project = Path("/some/project")
        state_path = get_state_file_path(project)

        assert state_path == Path("/some/project/.dazzle/state.json")


# =============================================================================
# State Persistence Tests
# =============================================================================


class TestStatePersistence:
    """Test state save/load operations."""

    def test_load_state_nonexistent(self, tmp_path: Path) -> None:
        """Test loading state when no state file exists."""
        state = load_state(tmp_path)

        assert state is None

    def test_save_and_load_state(
        self,
        project_with_dsl: Path,
        simple_appspec: AppSpec,
    ) -> None:
        """Test saving and loading state."""
        dsl_files = list((project_with_dsl / "dsl").glob("*.dsl"))
        output_dir = project_with_dsl / "generated"

        # Save state
        save_state(
            project_root=project_with_dsl,
            backend="fastapi",
            output_dir=output_dir,
            dsl_files=dsl_files,
            appspec=simple_appspec,
        )

        # Verify state file was created
        state_file = get_state_file_path(project_with_dsl)
        assert state_file.exists()

        # Load state
        loaded = load_state(project_with_dsl)

        assert loaded is not None
        assert loaded.backend == "fastapi"
        assert loaded.output_dir == "generated"
        assert len(loaded.dsl_file_hashes) == 2
        assert loaded.appspec_snapshot is not None

    def test_save_state_creates_directory(
        self,
        tmp_path: Path,
        simple_appspec: AppSpec,
    ) -> None:
        """Test that save_state creates .dazzle directory."""
        output_dir = tmp_path / "output"

        save_state(
            project_root=tmp_path,
            backend="django",
            output_dir=output_dir,
            dsl_files=[],
            appspec=simple_appspec,
        )

        assert (tmp_path / ".dazzle").exists()
        assert (tmp_path / ".dazzle" / "state.json").exists()

    def test_load_state_corrupted(self, tmp_path: Path) -> None:
        """Test loading corrupted state file."""
        state_dir = tmp_path / ".dazzle"
        state_dir.mkdir()
        state_file = state_dir / "state.json"
        state_file.write_text("invalid json {{{")

        with pytest.raises(StateError) as excinfo:
            load_state(tmp_path)

        assert "Failed to load build state" in str(excinfo.value)

    def test_clear_state(
        self,
        project_with_dsl: Path,
        simple_appspec: AppSpec,
    ) -> None:
        """Test clearing build state."""
        # First save state
        save_state(
            project_root=project_with_dsl,
            backend="fastapi",
            output_dir=project_with_dsl / "output",
            dsl_files=[],
            appspec=simple_appspec,
        )

        # Verify it exists
        state_file = get_state_file_path(project_with_dsl)
        assert state_file.exists()

        # Clear state
        clear_state(project_with_dsl)

        # Verify it's gone
        assert not state_file.exists()

    def test_clear_state_nonexistent(self, tmp_path: Path) -> None:
        """Test clearing state when no state exists (should not error)."""
        # Should not raise any exception
        clear_state(tmp_path)

    def test_state_contains_timestamp(
        self,
        project_with_dsl: Path,
        simple_appspec: AppSpec,
    ) -> None:
        """Test that saved state contains valid timestamp."""
        save_state(
            project_root=project_with_dsl,
            backend="fastapi",
            output_dir=project_with_dsl / "output",
            dsl_files=[],
            appspec=simple_appspec,
        )

        loaded = load_state(project_with_dsl)

        assert loaded is not None
        assert loaded.timestamp.endswith("Z")
        # Should be parseable as ISO format
        assert "T" in loaded.timestamp

    def test_state_file_is_valid_json(
        self,
        project_with_dsl: Path,
        simple_appspec: AppSpec,
    ) -> None:
        """Test that state file is valid JSON."""
        save_state(
            project_root=project_with_dsl,
            backend="fastapi",
            output_dir=project_with_dsl / "output",
            dsl_files=[],
            appspec=simple_appspec,
        )

        state_file = get_state_file_path(project_with_dsl)
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "timestamp" in data
        assert "backend" in data
        assert "output_dir" in data
        assert "dsl_file_hashes" in data
        assert "appspec_snapshot" in data
