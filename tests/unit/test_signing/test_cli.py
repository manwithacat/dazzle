"""Tests for `dazzle signing init` CLI (#1283 phase 4)."""

from __future__ import annotations

import base64

import pytest
from typer.testing import CliRunner

from dazzle.cli.signing import signing_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _clear_signing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`init` refuses to overwrite an existing cert unless --force.

    Tests run with the env var cleared so every invocation hits the
    fresh-mint path; the refusal behaviour is covered in its own test.
    """
    monkeypatch.delenv("SIGNING_CERT_PFX_B64", raising=False)
    monkeypatch.delenv("SIGNING_CERT_PASSWORD", raising=False)
    monkeypatch.delenv("SIGNING_TOKEN_SECRET", raising=False)


def test_init_emits_three_env_vars(runner: CliRunner) -> None:
    result = runner.invoke(signing_app, ["init", "--project-name", "Acme Ltd"])
    assert result.exit_code == 0, result.output
    assert "SIGNING_CERT_PFX_B64=" in result.output
    assert "SIGNING_CERT_PASSWORD=" in result.output
    assert "SIGNING_TOKEN_SECRET=" in result.output


def test_init_pkcs12_is_loadable(runner: CliRunner) -> None:
    """The minted PKCS#12 must be loadable with the emitted password."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    result = runner.invoke(signing_app, ["init", "--project-name", "Acme Ltd"])
    assert result.exit_code == 0

    pfx_line = next(
        line for line in result.output.splitlines() if line.startswith("SIGNING_CERT_PFX_B64=")
    )
    pwd_line = next(
        line for line in result.output.splitlines() if line.startswith("SIGNING_CERT_PASSWORD=")
    )
    b64 = pfx_line.split("=", 1)[1].strip('"')
    pwd = pwd_line.split("=", 1)[1].strip('"')

    key, cert, chain = pkcs12.load_key_and_certificates(base64.b64decode(b64), pwd.encode())
    assert key is not None
    assert cert is not None
    assert len(chain) == 1


def test_init_with_heroku_app_flag_emits_config_set_lines(
    runner: CliRunner,
) -> None:
    result = runner.invoke(
        signing_app, ["init", "--project-name", "Acme Ltd", "--heroku-app", "my-app"]
    )
    assert result.exit_code == 0
    assert "heroku config:set SIGNING_CERT_PFX_B64" in result.output
    assert "-a my-app" in result.output


def test_init_refuses_when_cert_env_already_set(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", "already-set")
    result = runner.invoke(signing_app, ["init", "--project-name", "Acme Ltd"])
    assert result.exit_code == 1
    assert "already set" in result.output


def test_init_force_overrides_refusal(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", "already-set")
    result = runner.invoke(signing_app, ["init", "--project-name", "Acme Ltd", "--force"])
    assert result.exit_code == 0
    assert "SIGNING_CERT_PFX_B64=" in result.output


def test_init_uses_country_override(runner: CliRunner) -> None:
    """The --country flag must thread through to the cert subject."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import pkcs12

    result = runner.invoke(signing_app, ["init", "--project-name", "Acme Ltd", "--country", "US"])
    assert result.exit_code == 0

    b64 = next(
        line.split("=", 1)[1].strip('"')
        for line in result.output.splitlines()
        if line.startswith("SIGNING_CERT_PFX_B64=")
    )
    pwd = next(
        line.split("=", 1)[1].strip('"')
        for line in result.output.splitlines()
        if line.startswith("SIGNING_CERT_PASSWORD=")
    )
    _, cert, _ = pkcs12.load_key_and_certificates(base64.b64decode(b64), pwd.encode())
    country = cert.subject.get_attributes_for_oid(x509.NameOID.COUNTRY_NAME)
    assert country[0].value == "US"
