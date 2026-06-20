from dazzle.http.runtime.auth.org_settings import OrgSettings


def test_defaults_admin_approval_and_unrestricted():
    s = OrgSettings.from_dict({})
    assert s.domain_join_policy == "admin_approval"
    assert s.restrict_membership_to_verified_domains is False


def test_unknown_policy_coerced_to_default():
    s = OrgSettings.from_dict({"domain_join_policy": "garbage"})
    assert s.domain_join_policy == "admin_approval"


def test_roundtrip():
    s = OrgSettings(domain_join_policy="auto_join", restrict_membership_to_verified_domains=True)
    assert OrgSettings.from_dict(s.to_dict()) == s
