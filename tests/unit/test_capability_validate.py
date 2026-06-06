"""`dazzle validate` rejects unknown [capabilities] ids (#1342)."""

import pytest
import typer

from dazzle.cli.project import validate_command


def _toml(tmp_path, capability_line: str) -> str:
    p = tmp_path / "dazzle.toml"
    p.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n\n'
        + capability_line,
        encoding="utf-8",
    )
    return str(p)


def test_validate_rejects_unknown_capability(tmp_path, capsys):
    path = _toml(tmp_path, '[capabilities]\nenabled = ["auth.enterprize.oidc"]\n')
    with pytest.raises(typer.Exit) as exc:
        validate_command(manifest=path, format="human")
    assert exc.value.exit_code == 1
    out = capsys.readouterr()
    combined = out.out + out.err
    assert "Unknown capability" in combined
    assert "auth.enterprise.oidc" in combined  # did-you-mean suggestion
