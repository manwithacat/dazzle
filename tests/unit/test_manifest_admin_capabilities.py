"""Manifest [auth.admin_capabilities] parsing (admin-authz)."""

from pathlib import Path

from dazzle.core.manifest import load_manifest


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n' + body,
        encoding="utf-8",
    )
    return p


def test_admin_capabilities_default_empty(tmp_path):
    m = load_manifest(_write(tmp_path, ""))
    assert m.auth.admin_capabilities == {}


def test_admin_capabilities_parsed(tmp_path):
    m = load_manifest(
        _write(
            tmp_path,
            '\n[auth]\nenabled = true\norg_admin_roles = ["org_admin"]\n'
            "\n[auth.admin_capabilities]\n"
            'manage_members = ["business_admin"]\n'
            'manage_connections = ["it_admin"]\n',
        )
    )
    assert m.auth.admin_capabilities == {
        "manage_members": ["business_admin"],
        "manage_connections": ["it_admin"],
    }
