"""`load_manifest` parsing of the optional dazzle.toml sections.

One table per outcome: a section is absent (default), parsed, filtered, or
rejected loudly. Each row names the section and the issue that introduced it:
[extensions] routers (#786), [renderers] extra (#1116), [ui] app_scripts (#1515), [ui] topbar_title (#1794), [ui] page_purpose (#1811),
[auth.admin_capabilities] (admin-authz) and
[serve] app (ADR-0046), [auth.enterprise] protocols (DD-013),
[auth.two_factor] (DD-014).
"""

from pathlib import Path
from typing import Any

import pytest

from dazzle.core.errors import DazzleError
from dazzle.core.ir.security import TwoFactorConfig, TwoFactorMethod
from dazzle.core.manifest import load_manifest

_MINIMAL_TOML = '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["./dsl"]\n'


def _load(tmp_path: Path, extra: str = "") -> Any:
    path = tmp_path / "dazzle.toml"
    path.write_text(_MINIMAL_TOML + extra, encoding="utf-8")
    return load_manifest(path)


def _attr(obj: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.mark.parametrize(
    ("attr", "expected"),
    [
        pytest.param("extensions.routers", [], id="extensions_786"),
        pytest.param("renderers.extra", [], id="renderers_1116"),
        pytest.param("app_scripts", [], id="ui_app_scripts_1515"),
        pytest.param("topbar_title", "app", id="ui_topbar_title_1794"),
        pytest.param("page_purpose", True, id="ui_page_purpose_1811"),
        pytest.param("auth.admin_capabilities", {}, id="auth_admin_capabilities"),
        pytest.param("serve.app", None, id="serve_app_adr0046"),
        pytest.param("auth.enterprise.protocols", [], id="auth_enterprise_dd013"),
        pytest.param("auth.two_factor", TwoFactorConfig(), id="auth_two_factor_off_dd014"),
    ],
)
def test_absent_section_defaults_empty(tmp_path: Path, attr: str, expected: Any) -> None:
    assert _attr(_load(tmp_path), attr) == expected


@pytest.mark.parametrize(
    ("extra", "attr", "expected"),
    [
        pytest.param(
            '\n[extensions]\nrouters = ["app.routes.graph:router", "app.routes.search:router"]\n',
            "extensions.routers",
            ["app.routes.graph:router", "app.routes.search:router"],
            id="extensions_routers_in_order_786",
        ),
        pytest.param(
            "\n[extensions]\nrouters = []\n",
            "extensions.routers",
            [],
            id="extensions_empty_routers_786",
        ),
        pytest.param(
            '\n[renderers]\nextra = ["branch_compare", "cytoscape_graph"]\n',
            "renderers.extra",
            ["branch_compare", "cytoscape_graph"],
            id="renderers_extra_1116",
        ),
        pytest.param(
            '\n[ui]\napp_scripts = ["/static/js/dz-islands.js", "/static/js/charts.js"]\n',
            "app_scripts",
            ["/static/js/dz-islands.js", "/static/js/charts.js"],
            id="ui_app_scripts_in_order_1515",
        ),
        pytest.param(
            "\n[ui]\ntopbar_title = false\n",
            "topbar_title",
            "none",
            id="ui_topbar_title_false_1794",
        ),
        pytest.param(
            "\n[ui]\ntopbar_title = true\n", "topbar_title", "app", id="ui_topbar_title_true_1794"
        ),
        pytest.param(
            '\n[ui]\ntopbar_title = "page"\n',
            "topbar_title",
            "page",
            id="ui_topbar_title_page_1794",
        ),
        pytest.param(
            "\n[ui]\npage_purpose = false\n", "page_purpose", False, id="ui_page_purpose_off_1811"
        ),
        pytest.param(
            '\n[auth]\nenabled = true\norg_admin_roles = ["org_admin"]\n'
            '\n[auth.admin_capabilities]\nmanage_members = ["business_admin"]\n',
            "auth.admin_capabilities",
            {"manage_members": ["business_admin"]},
            id="auth_admin_capabilities",
        ),
        pytest.param(
            '\n[serve]\napp = "server:app"\n',
            "serve.app",
            "server:app",
            id="serve_app_adr0046",
        ),
        pytest.param(
            '\n[auth.enterprise]\nprotocols = ["oidc", "scim"]\n',
            "auth.enterprise.protocols",
            ["oidc", "scim"],
            id="auth_enterprise_protocols_dd013",
        ),
        pytest.param(
            '\n[auth.two_factor]\nenabled = true\nmethods = ["totp", "email_otp"]\n'
            'recovery_code_count = 10\nenforce_for_roles = ["accountant"]\n',
            "auth.two_factor",
            TwoFactorConfig(
                enabled=True,
                methods=(TwoFactorMethod.TOTP, TwoFactorMethod.EMAIL_OTP),
                recovery_code_count=10,
                enforce_for_roles=("accountant",),
            ),
            id="auth_two_factor_dd014",
        ),
        pytest.param(
            "\n[auth.two_factor]\nenabled = true\n",
            "auth.two_factor.methods",
            (TwoFactorMethod.TOTP,),
            id="auth_two_factor_default_totp_dd014",
        ),
    ],
)
def test_section_parsed(tmp_path: Path, extra: str, attr: str, expected: Any) -> None:
    assert _attr(_load(tmp_path, extra), attr) == expected


@pytest.mark.parametrize(
    ("extra", "attr", "expected"),
    [
        pytest.param(
            '\n[extensions]\nrouters = ["app.routes.graph:router", 42, "app.routes.search:router"]\n',
            "extensions.routers",
            ["app.routes.graph:router", "app.routes.search:router"],
            id="extensions_non_string_routers_dropped_786",
        ),
        pytest.param(
            '\n[renderers]\nextra = ["ok_name", 42, true, "another_ok"]\n',
            "renderers.extra",
            ["ok_name", "another_ok"],
            id="renderers_non_string_extras_dropped_1116",
        ),
        pytest.param(
            '\n[renderers]\nextra = "branch_compare"\n',
            "renderers.extra",
            [],
            id="renderers_scalar_extra_falls_back_to_empty_1116",
        ),
    ],
)
def test_lenient_section_filters_bad_entries(
    tmp_path: Path, extra: str, attr: str, expected: Any
) -> None:
    """A bad entry in these sections is dropped rather than breaking app startup."""
    assert _attr(_load(tmp_path, extra), attr) == expected


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        pytest.param(
            '\n[ui]\napp_scripts = "/static/js/one.js"\n',
            "app_scripts must be a list",
            id="ui_app_scripts_scalar_1515",
        ),
        pytest.param(
            '\n[ui]\napp_scripts = ["/static/js/ok.js", 42]\n',
            "app_scripts must be a list",
            id="ui_app_scripts_non_string_entry_1515",
        ),
        pytest.param(
            '\n[ui]\ntopbar_title = "breadcrumb"\n',
            "topbar_title must be true, false, or 'page'",
            id="ui_topbar_title_unknown_1794",
        ),
        pytest.param(
            '\n[auth.enterprise]\nprotocols = ["oidc", "saml"]\n',
            "DD-013",
            id="auth_enterprise_out_of_scope_protocol_dd013",
        ),
        pytest.param(
            '\n[auth.enterprise]\nprotocols = ["ldap"]\n',
            "DD-013",
            id="auth_enterprise_unknown_protocol_dd013",
        ),
        pytest.param(
            '\n[auth.enterprise]\nprotocols = "oidc"\n',
            "protocols must be a list",
            id="auth_enterprise_scalar_protocols_dd013",
        ),
        pytest.param(
            '\n[auth.two_factor]\nenabled = true\nmethods = ["webauthn"]\n',
            "DD-014",
            id="auth_two_factor_out_of_scope_method_dd014",
        ),
        pytest.param(
            '\n[auth.two_factor]\nenforce_for_roles = ["accountant"]\n',
            "requires enabled = true",
            id="auth_two_factor_enforce_without_enabled_dd014",
        ),
        pytest.param(
            "\n[auth.two_factor]\nenabled = true\nremember_device = true\n",
            "unknown keys",
            id="auth_two_factor_unknown_key_dd014",
        ),
        pytest.param(
            "\n[auth.two_factor]\nenabled = true\nrecovery_code_count = 0\n",
            "recovery_code_count",
            id="auth_two_factor_recovery_count_dd014",
        ),
    ],
)
def test_strict_section_rejects_malformed_value(tmp_path: Path, extra: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _load(tmp_path, extra)


def test_missing_dazzle_toml_raises_dazzle_error(tmp_path: Path) -> None:
    """#1414: a missing dazzle.toml raises a friendly DazzleError (which the CLI
    catches and prints cleanly) instead of a raw FileNotFoundError traceback."""
    with pytest.raises(DazzleError, match="No dazzle.toml found"):
        load_manifest(tmp_path / "dazzle.toml")
