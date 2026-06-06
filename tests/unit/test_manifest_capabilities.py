"""Manifest [capabilities] parsing (#1342)."""

from pathlib import Path

from dazzle.core.manifest import load_manifest


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )
    return p


def test_capabilities_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, ""))
    assert m.capabilities.enabled == []


def test_non_list_enabled_is_rejected(tmp_path):
    import pytest

    # A scalar instead of a list must fail loud, not shred into characters.
    with pytest.raises(ValueError, match="must be a list"):
        load_manifest(_write(tmp_path, '\n[capabilities]\nenabled = "auth.enterprise.oidc"\n'))


def test_capabilities_parsed(tmp_path):
    m = load_manifest(
        _write(
            tmp_path,
            '\n[capabilities]\nenabled = ["auth.enterprise.oidc", "auth.enterprise.scim"]\n',
        )
    )
    assert m.capabilities.enabled == [
        "auth.enterprise.oidc",
        "auth.enterprise.scim",
    ]
