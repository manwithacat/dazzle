"""
Tests for the DAZZLE LSP server module.

These tests verify:
1. Clean module loading (no duplicate imports/warnings)
2. Proper entry point behavior
3. Server instantiation
4. CLI commands (check, grammar-path)
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from dazzle.cli.lsp import lsp_app


class TestLspModuleLoading:
    """Test that LSP module loads cleanly without warnings."""

    def test_lsp_module_imports_cleanly(self) -> None:
        """Verify 'python -m dazzle.lsp' doesn't produce RuntimeWarnings."""
        # Run the module with a short timeout - we just want to check startup
        result = subprocess.run(
            [sys.executable, "-W", "error", "-c", "import dazzle.lsp"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Should import without warnings (we used -W error to turn warnings into errors)
        assert result.returncode == 0, f"Import failed with stderr: {result.stderr}"
        assert "RuntimeWarning" not in result.stderr

    def test_lsp_entry_point_no_duplicate_registration(self) -> None:
        """Verify running 'python -m dazzle.lsp' doesn't register features twice."""
        # Start the LSP server briefly and capture its output
        result = subprocess.run(
            [sys.executable, "-m", "dazzle.lsp"],
            capture_output=True,
            text=True,
            timeout=2,  # Will timeout since server waits for stdin
            input="",  # Empty stdin causes immediate exit attempt
        )

        # Count feature registrations - each should appear only once
        stderr = result.stderr
        initialize_count = stderr.count('Registered "initialize"')
        hover_count = stderr.count('Registered "textDocument/hover"')

        # With proper module loading, each feature is registered exactly once
        assert initialize_count == 1, (
            f"'initialize' registered {initialize_count} times (expected 1). "
            "This indicates duplicate module loading."
        )
        assert hover_count == 1, (
            f"'textDocument/hover' registered {hover_count} times (expected 1). "
            "This indicates duplicate module loading."
        )

    def test_lsp_server_module_not_double_loaded(self) -> None:
        """Verify dazzle.lsp.server isn't in sys.modules before execution warning."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzle.lsp"],
            capture_output=True,
            text=True,
            timeout=2,
            input="",
        )

        # The specific warning we're checking for
        assert "found in sys.modules after import" not in result.stderr, (
            "Module double-loading warning detected. "
            "The entry point should use 'python -m dazzle.lsp' not 'python -m dazzle.lsp.server'"
        )


class TestLspServerInstance:
    """Test LSP server instantiation."""

    def test_server_can_be_imported(self) -> None:
        """Verify the server module can be imported."""
        from dazzle.lsp import start_server

        assert callable(start_server)

    def test_server_class_exists(self) -> None:
        """Verify DazzleLanguageServer class exists."""
        from dazzle.lsp.server import DazzleLanguageServer

        assert DazzleLanguageServer is not None

    def test_server_has_expected_features(self) -> None:
        """Verify server registers expected LSP features."""
        from dazzle.lsp.server import server

        # Check that the server is a LanguageServer instance with workspace state
        assert hasattr(server, "workspace_root")
        assert hasattr(server, "appspec")


runner = CliRunner()


class TestLspCli:
    """Tests for dazzle lsp CLI subcommands."""

    def test_lsp_check_succeeds(self) -> None:
        """lsp check prints version info when deps are installed."""
        result = runner.invoke(lsp_app, ["check"])
        assert result.exit_code == 0
        assert "pygls:" in result.output
        assert "lsprotocol:" in result.output
        assert "All LSP dependencies installed" in result.output

    def test_lsp_check_missing_pygls(self) -> None:
        """lsp check fails gracefully when pygls is missing."""
        with patch.dict("sys.modules", {"pygls": None}):
            result = runner.invoke(lsp_app, ["check"])
            assert result.exit_code == 1

    def test_lsp_grammar_path_returns_valid_path(self) -> None:
        """lsp grammar-path prints a path to an existing JSON file."""
        result = runner.invoke(lsp_app, ["grammar-path"])
        assert result.exit_code == 0
        path = Path(result.output.strip())
        assert path.exists()
        assert path.suffix == ".json"
        assert "tmLanguage" in path.name

    def test_lsp_run_missing_deps(self) -> None:
        """lsp run fails gracefully when LSP deps are missing."""
        with patch.dict("sys.modules", {"dazzle.lsp": None}):
            result = runner.invoke(lsp_app, ["run"])
            assert result.exit_code == 1
            assert "LSP dependencies not installed" in result.output
