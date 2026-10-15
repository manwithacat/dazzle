"""Run the `dazzle` Typer app in-process for CLI tests.

`run_cli` returns the combined output after checking the exit code the
caller names (default 0), so a calling test's case table reads as
"command -> exit code -> fragments in the output".
"""

from collections.abc import Sequence

from click.testing import Result
from typer.testing import CliRunner

from dazzle.cli import app


def invoke(args: Sequence[str]) -> Result:
    """Invoke `dazzle <args>` and return the raw Click result."""
    return CliRunner().invoke(app, [str(a) for a in args])


def run_cli(args: Sequence[str], *, exit_code: int = 0) -> str:
    """Invoke `dazzle <args>`, require ``exit_code``, return stdout + stderr."""
    result = invoke(args)
    assert result.exit_code == exit_code, (
        f"dazzle {' '.join(map(str, args))} exited {result.exit_code}, "
        f"expected {exit_code}:\n{result.output}"
    )
    return result.output
