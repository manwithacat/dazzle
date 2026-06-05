"""auto_provision_single_org flows manifest -> ServerConfig (Plan 1d)."""

from dazzle.back.runtime.server import ServerConfig
from dazzle.core.manifest import AuthConfig


def test_authconfig_default_off() -> None:
    assert AuthConfig().auto_provision_single_org is False


def test_authconfig_can_opt_in() -> None:
    cfg = AuthConfig(enabled=True, auto_provision_single_org=True)
    assert cfg.auto_provision_single_org is True


def test_serverconfig_field_exists_default_off() -> None:
    assert ServerConfig().auto_provision_single_org is False
