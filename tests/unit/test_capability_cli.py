"""`dazzle capability` CLI (#1342)."""

import pytest
from typer.testing import CliRunner

from dazzle.cli.capability import capability_app
from tests.unit._fake_capabilities import fake_capabilities  # noqa: F401  (fixture)

runner = CliRunner()


def _project(tmp_path, body: str = "") -> None:
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )


@pytest.mark.usefixtures("fake_capabilities")
def test_list_shows_registered_capabilities(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["list"])
    assert result.exit_code == 0
    assert "demo.alpha" in result.stdout
    assert "demo.beta" in result.stdout


@pytest.mark.usefixtures("fake_capabilities")
def test_enable_writes_manifest_entry(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "demo.alpha"])
    assert result.exit_code == 0
    text = (tmp_path / "dazzle.toml").read_text()
    assert "demo.alpha" in text
    assert "dazzle-dsl[sso]" in result.stdout  # runbook printed


@pytest.mark.usefixtures("fake_capabilities")
def test_enable_rejects_unknown_id(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "demo.bogus"])
    assert result.exit_code != 0
    assert "Unknown capability" in result.stdout


@pytest.mark.usefixtures("fake_capabilities")
def test_enable_into_section_without_enabled_key(tmp_path, monkeypatch):
    # [capabilities] table present but no `enabled` key — enable must insert it,
    # not silently no-op (review finding).
    _project(tmp_path, "\n[capabilities]\n# we'll add enabled below\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "demo.alpha"])
    assert result.exit_code == 0
    text = (tmp_path / "dazzle.toml").read_text()
    assert 'enabled = ["demo.alpha"]' in text


@pytest.mark.usefixtures("fake_capabilities")
def test_enable_does_not_clobber_enabled_in_other_table(tmp_path, monkeypatch):
    # A list-valued `enabled` in an unrelated table must be left untouched
    # (section-awareness review finding).
    _project(
        tmp_path,
        '\n[other]\nenabled = ["keep-me"]\n\n[capabilities]\nenabled = []\n',
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["enable", "demo.gamma"])
    assert result.exit_code == 0
    text = (tmp_path / "dazzle.toml").read_text()
    assert 'enabled = ["keep-me"]' in text  # other table preserved
    assert 'enabled = ["demo.gamma"]' in text


@pytest.mark.usefixtures("fake_capabilities")
def test_disable_removes_entry(tmp_path, monkeypatch):
    _project(tmp_path, '\n[capabilities]\nenabled = ["demo.alpha"]\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(capability_app, ["disable", "demo.alpha"])
    assert result.exit_code == 0
    assert "demo.alpha" not in (tmp_path / "dazzle.toml").read_text()
