"""Capability cognition gating (#1342 Phase 2)."""

import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities import active_capability_ids


def test_active_capability_ids_is_non_raising(monkeypatch):
    # OIDC available, SAML not. Unlike resolve_capabilities, this must NOT raise
    # when a declared capability's extra is missing — it just omits it.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)
    active = active_capability_ids(["auth.enterprise.oidc", "auth.enterprise.saml", "auth.bogus"])
    assert active == {"auth.enterprise.oidc"}  # available+declared only
    assert "auth.enterprise.saml" not in active  # declared but unavailable → omitted
    assert "auth.bogus" not in active  # unknown → omitted


def test_active_capabilities_for_reads_manifest(tmp_path, monkeypatch):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # all available
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n\n'
        '[capabilities]\nenabled = ["auth.enterprise.oidc"]\n',
        encoding="utf-8",
    )
    assert active_capabilities_for(tmp_path) == {"auth.enterprise.oidc"}


def test_active_capabilities_for_missing_manifest_is_empty(tmp_path):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    assert active_capabilities_for(tmp_path) == set()


def test_active_capabilities_for_malformed_manifest_is_empty(tmp_path):
    # A malformed manifest must NOT crash an advisory cognition read.
    from dazzle.core.capabilities.cognition import active_capabilities_for

    (tmp_path / "dazzle.toml").write_text("this is not valid toml = = =", encoding="utf-8")
    assert active_capabilities_for(tmp_path) == set()


def test_partition_by_capability_splits_surfaced_and_gated():
    from dazzle.core.capabilities.cognition import partition_by_capability

    items = [
        {"id": "a", "cap": None},
        {"id": "b", "cap": "auth.enterprise.oidc"},
        {"id": "c", "cap": "auth.enterprise.saml"},
    ]
    surfaced, gated = partition_by_capability(
        items, active={"auth.enterprise.oidc"}, capability_of=lambda it: it["cap"]
    )
    assert [i["id"] for i in surfaced] == ["a", "b"]  # ungated + active
    assert gated == [(items[2], "auth.enterprise.saml")]  # gated + inactive


def test_enable_suggestion_carries_runbook():
    from dazzle.core.capabilities.cognition import enable_suggestion

    s = enable_suggestion("auth.enterprise.oidc")
    assert s["capability"] == "auth.enterprise.oidc"
    assert s["enable"] == "dazzle capability enable auth.enterprise.oidc"
    assert "dazzle-dsl[sso]" in s["remediation"]
