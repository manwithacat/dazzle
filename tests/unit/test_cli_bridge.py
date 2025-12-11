"""
Tests for CLI bridge functions.

These tests verify that the CLI bridge functions can be imported
and called without import errors - catching broken references early.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestCliBridgeImports:
    """Test that all CLI bridge functions can be imported."""

    def test_validate_project_json_imports(self) -> None:
        """validate_project_json should import without errors."""
        from dazzle.core.cli_bridge import validate_project_json

        assert callable(validate_project_json)

    def test_get_project_info_json_imports(self) -> None:
        """get_project_info_json should import without errors."""
        from dazzle.core.cli_bridge import get_project_info_json

        assert callable(get_project_info_json)

    def test_init_project_json_imports(self) -> None:
        """init_project_json should import without errors."""
        from dazzle.core.cli_bridge import init_project_json

        assert callable(init_project_json)

    def test_build_project_json_imports(self) -> None:
        """build_project_json should import without errors."""
        from dazzle.core.cli_bridge import build_project_json

        assert callable(build_project_json)

    def test_eject_project_json_imports(self) -> None:
        """eject_project_json should import without errors."""
        from dazzle.core.cli_bridge import eject_project_json

        assert callable(eject_project_json)


class TestCliBridgeInternalImports:
    """Test that bridge functions' internal imports work.

    These tests mock external dependencies but verify the import
    statements inside each function don't raise ImportError.
    """

    def test_build_project_json_internal_imports(self, tmp_path: Path) -> None:
        """build_project_json should not have broken internal imports."""
        from dazzle.core.cli_bridge import build_project_json

        # Create minimal project structure
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text('module test\napp test "Test"')

        # Should not raise ImportError for internal imports
        # May raise other errors (missing DNR packages) but not ImportError
        try:
            build_project_json(path=str(tmp_path), output=str(tmp_path / "dist"))
        except ImportError as e:
            pytest.fail(f"build_project_json has broken import: {e}")
        except Exception:
            pass  # Other errors are OK (e.g., validation errors)

    def test_eject_project_json_internal_imports(self, tmp_path: Path) -> None:
        """eject_project_json should not have broken internal imports."""
        from dazzle.core.cli_bridge import eject_project_json

        # Create minimal project structure
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text('module test\napp test "Test"')

        # Should not raise ImportError for internal imports
        try:
            eject_project_json(path=str(tmp_path), output=str(tmp_path / "ejected"))
        except ImportError as e:
            pytest.fail(f"eject_project_json has broken import: {e}")
        except Exception:
            pass  # Other errors are OK


class TestValidateProjectJson:
    """Tests for validate_project_json function."""

    def test_returns_dict_structure(self, tmp_path: Path) -> None:
        """Should return dict with expected keys."""
        from dazzle.core.cli_bridge import validate_project_json

        # Create minimal valid project
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text(
            'module test\napp test "Test"\n\nentity Task "Task":\n  id: uuid pk\n  title: str required'
        )

        result = validate_project_json(path=str(tmp_path))

        assert isinstance(result, dict)
        assert "valid" in result
        assert "modules" in result
        assert "entities" in result
        assert "surfaces" in result
        assert "errors" in result
        assert "warnings" in result

    def test_invalid_project_returns_errors(self, tmp_path: Path) -> None:
        """Should return errors for invalid project."""
        from dazzle.core.cli_bridge import validate_project_json

        # Create invalid DSL
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text("invalid syntax here !!!")

        result = validate_project_json(path=str(tmp_path))

        assert isinstance(result, dict)
        assert result["valid"] is False or len(result["errors"]) > 0


class TestInitProjectJson:
    """Tests for init_project_json function."""

    def test_creates_project_directory(self, tmp_path: Path) -> None:
        """Should create project in target directory."""
        from dazzle.core.cli_bridge import init_project_json

        target = tmp_path / "new_project"

        result = init_project_json(
            name="test_project",
            template="simple_task",
            path=str(target),
        )

        assert isinstance(result, dict)
        assert "name" in result
        assert "path" in result
        assert target.exists()
        assert (target / "dazzle.toml").exists()


class TestNewBridgeFunctions:
    """Tests for newly added bridge functions (db, test, dev)."""

    def test_run_tests_json_imports(self) -> None:
        """run_tests_json should import without errors."""
        from dazzle.core.cli_bridge import run_tests_json

        assert callable(run_tests_json)

    def test_db_migrate_json_imports(self) -> None:
        """db_migrate_json should import without errors."""
        from dazzle.core.cli_bridge import db_migrate_json

        assert callable(db_migrate_json)

    def test_db_seed_json_imports(self) -> None:
        """db_seed_json should import without errors."""
        from dazzle.core.cli_bridge import db_seed_json

        assert callable(db_seed_json)

    def test_db_reset_json_imports(self) -> None:
        """db_reset_json should import without errors."""
        from dazzle.core.cli_bridge import db_reset_json

        assert callable(db_reset_json)

    def test_dev_server_json_imports(self) -> None:
        """dev_server_json should import without errors."""
        from dazzle.core.cli_bridge import dev_server_json

        assert callable(dev_server_json)

    def test_run_tests_json_internal_imports(self, tmp_path: Path) -> None:
        """run_tests_json should not have broken internal imports."""
        from dazzle.core.cli_bridge import run_tests_json

        # Create minimal project structure
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text('module test\napp test "Test"')

        # Should not raise ImportError for internal imports
        try:
            run_tests_json(path=str(tmp_path))
        except ImportError as e:
            pytest.fail(f"run_tests_json has broken import: {e}")
        except Exception:
            pass  # Other errors are OK (e.g., no test framework)

    def test_db_migrate_json_internal_imports(self, tmp_path: Path) -> None:
        """db_migrate_json should not have broken internal imports."""
        from dazzle.core.cli_bridge import db_migrate_json

        # Create minimal project structure
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"')
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text('module test\napp test "Test"')

        # Should not raise ImportError for internal imports
        try:
            db_migrate_json(path=str(tmp_path))
        except ImportError as e:
            pytest.fail(f"db_migrate_json has broken import: {e}")
        except Exception:
            pass  # Other errors are OK
