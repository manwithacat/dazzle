"""Tests for the pure in-app connection-creation helpers (#1342)."""

import pytest

from dazzle.back.runtime.auth.connection_create_form import (
    CreateFormError,
    assemble_saml_config,
    parse_group_map,
    plan_oidc,
    plan_saml,
    plan_scim,
)

# ---- group-map parsing (lenient free-text field) ----


def test_parse_group_map_basic():
    assert parse_group_map("eng=engineer, ops=operator") == {"eng": "engineer", "ops": "operator"}


def test_parse_group_map_newline_separated():
    assert parse_group_map("eng=engineer\nops=operator") == {"eng": "engineer", "ops": "operator"}


def test_parse_group_map_skips_malformed_and_blank():
    # lenient: a stray token / blank / half-pair is skipped, not a hard error
    assert parse_group_map("eng=engineer, garbage, =role, group=, ,") == {"eng": "engineer"}


def test_parse_group_map_empty():
    assert parse_group_map("") == {}


# ---- OIDC ----


def test_plan_oidc_ok():
    plan = plan_oidc(issuer="https://idp.test", client_id="cid", group_map="eng=engineer")
    assert plan.type == "oidc"
    assert plan.config == {"issuer": "https://idp.test", "client_id": "cid"}
    assert plan.group_mapping == {"eng": "engineer"} and plan.show_bearer_once is False


def test_plan_oidc_requires_https_issuer():
    with pytest.raises(CreateFormError, match="https"):
        plan_oidc(issuer="http://idp.test", client_id="cid", group_map="")


def test_plan_oidc_requires_issuer_and_client_id():
    with pytest.raises(CreateFormError, match="Issuer"):
        plan_oidc(issuer="  ", client_id="cid", group_map="")
    with pytest.raises(CreateFormError, match="Client id"):
        plan_oidc(issuer="https://idp.test", client_id="", group_map="")


# ---- SCIM ----


def test_plan_scim_mints_nothing_here_but_flags_show_once():
    plan = plan_scim(group_map="eng=engineer")
    assert plan.type == "scim" and plan.config == {} and plan.show_bearer_once is True
    assert plan.group_mapping == {"eng": "engineer"}


# ---- SAML config assembly ----


def test_assemble_saml_explicit():
    cfg = assemble_saml_config(
        metadata=None,
        idp_entity_id="https://idp/meta",
        idp_sso_url="https://idp/sso",
        idp_x509_cert="CERTPEM",
    )
    assert cfg == {
        "idp_entity_id": "https://idp/meta",
        "idp_sso_url": "https://idp/sso",
        "idp_x509_cert": "CERTPEM",
    }


def test_assemble_saml_from_metadata_plus_optional_slo_and_attrs():
    md = {
        "idp_entity_id": "https://idp/meta",
        "idp_sso_url": "https://idp/sso",
        "idp_x509_cert": "CERTPEM",
        "idp_slo_url": "https://idp/slo",
    }
    cfg = assemble_saml_config(
        metadata=md,
        idp_entity_id="",
        idp_sso_url="",
        idp_x509_cert="",
        email_attribute="mail",
        groups_attribute="memberOf",
    )
    assert cfg["idp_slo_url"] == "https://idp/slo"
    assert cfg["email_attribute"] == "mail" and cfg["groups_attribute"] == "memberOf"


def test_assemble_saml_explicit_overrides_metadata():
    md = {
        "idp_entity_id": "https://meta/entity",
        "idp_sso_url": "https://meta/sso",
        "idp_x509_cert": "META_CERT",
    }
    cfg = assemble_saml_config(
        metadata=md,
        idp_entity_id="https://explicit/entity",
        idp_sso_url="",
        idp_x509_cert="",
    )
    assert cfg["idp_entity_id"] == "https://explicit/entity"  # explicit wins
    assert cfg["idp_sso_url"] == "https://meta/sso"  # falls back to metadata


def test_assemble_saml_missing_reports_all_gaps():
    with pytest.raises(CreateFormError) as exc:
        assemble_saml_config(metadata=None, idp_entity_id="", idp_sso_url="", idp_x509_cert="")
    msg = str(exc.value)
    assert "entity id" in msg and "SSO URL" in msg and "signing cert" in msg


def test_plan_saml_wraps_config():
    cfg = {"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c"}
    plan = plan_saml(config=cfg, group_map="eng=engineer")
    assert plan.type == "saml" and plan.config is cfg
    assert plan.group_mapping == {"eng": "engineer"} and plan.show_bearer_once is False
