"""`dazzle signing init` (#1283 phase 4)."""

from __future__ import annotations

import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from typer.testing import CliRunner

from dazzle.cli.signing import signing_app

_VARS = ("SIGNING_CERT_PFX_B64", "SIGNING_CERT_PASSWORD", "SIGNING_TOKEN_SECRET")


@pytest.fixture(autouse=True)
def _clear_signing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def _init(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(signing_app, ["init", "--project-name", "Acme Ltd", *args])
    return result.exit_code, result.output


def _emitted(output: str) -> dict[str, str]:
    return {
        name: value.strip('"')
        for name, _, value in (line.partition("=") for line in output.splitlines())
        if name in _VARS
    }


def test_init_emits_a_loadable_chain_for_the_requested_country() -> None:
    code, output = _init("--country", "US")
    assert code == 0, output
    env = _emitted(output)
    assert set(env) == set(_VARS)
    key, cert, chain = pkcs12.load_key_and_certificates(
        base64.b64decode(env["SIGNING_CERT_PFX_B64"]), env["SIGNING_CERT_PASSWORD"].encode()
    )
    assert key is not None
    assert len(chain) == 1
    assert cert.subject.get_attributes_for_oid(x509.NameOID.COUNTRY_NAME)[0].value == "US"


def test_init_with_heroku_app_emits_config_set_lines() -> None:
    code, output = _init("--heroku-app", "my-app")
    assert code == 0
    assert "heroku config:set SIGNING_CERT_PFX_B64" in output
    assert "-a my-app" in output


@pytest.mark.parametrize(
    ("args", "code", "fragment"),
    [
        pytest.param((), 1, "already set", id="refuses-to-overwrite-existing-cert"),
        pytest.param(("--force",), 0, "SIGNING_CERT_PFX_B64=", id="force-overrides-refusal"),
    ],
)
def test_init_with_cert_already_configured(
    args: tuple[str, ...], code: int, fragment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", "already-set")
    exit_code, output = _init(*args)
    assert exit_code == code
    assert fragment in output
