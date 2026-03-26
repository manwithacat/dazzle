"""Tests for dazzle dbshell command (#695)."""

from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


class TestDbshellCommand:
    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_basic_invocation(self, mock_url, mock_which, mock_subprocess):
        from dazzle.cli import app

        runner.invoke(app, ["dbshell"])
        mock_subprocess.run.assert_called_once()
        args = mock_subprocess.run.call_args[0][0]
        assert args[0] == "psql"
        assert "postgresql://localhost/myapp" in args

    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_single_query(self, mock_url, mock_which, mock_subprocess):
        from dazzle.cli import app

        runner.invoke(app, ["dbshell", "-c", "SELECT 1"])
        args = mock_subprocess.run.call_args[0][0]
        assert "-c" in args
        assert "SELECT 1" in args

    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_read_only(self, mock_url, mock_which, mock_subprocess):
        from dazzle.cli import app

        runner.invoke(app, ["dbshell", "--read-only"])
        args = mock_subprocess.run.call_args[0][0]
        assert "-v" in args
        assert "default_transaction_read_only=on" in args

    @patch("dazzle.cli.dbshell.shutil.which", return_value=None)
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_psql_not_found(self, mock_url, mock_which):
        from dazzle.cli import app

        result = runner.invoke(app, ["dbshell"])
        assert result.exit_code == 1
        assert "psql" in result.output.lower()
