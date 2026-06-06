"""`dazzle capability` CLI (#1342)."""

from typer.testing import CliRunner

from dazzle.cli.capability import capability_app

runner = CliRunner()


def _project(tmp_path, body: str = "") -> None:
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )


def test_list_shows_enterprise_capabilities(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["list"])
    assert result.exit_code == 0
    assert "auth.enterprise.oidc" in result.stdout
    assert "auth.enterprise.saml" in result.stdout


def test_enable_writes_manifest_entry(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "auth.enterprise.oidc"])
    assert result.exit_code == 0
    text = (tmp_path / "dazzle.toml").read_text()
    assert "auth.enterprise.oidc" in text
    assert "dazzle-dsl[sso]" in result.stdout  # runbook printed


def test_enable_rejects_unknown_id(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "auth.bogus"])
    assert result.exit_code != 0
    assert "Unknown capability" in result.stdout


def test_disable_removes_entry(tmp_path, monkeypatch):
    _project(tmp_path, '\n[capabilities]\nenabled = ["auth.enterprise.oidc"]\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["disable", "auth.enterprise.oidc"])
    assert result.exit_code == 0
    assert "auth.enterprise.oidc" not in (tmp_path / "dazzle.toml").read_text()
