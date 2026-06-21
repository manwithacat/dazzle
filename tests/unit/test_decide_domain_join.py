from dazzle.http.runtime.auth.domain_join import (
    AutoJoin,
    NeedsApproval,
    Noop,
    Off,
    decide_domain_join,
)


def test_unverified_email_never_joins():
    assert isinstance(
        decide_domain_join("auto_join", email_verified=False, has_membership=False), Noop
    )


def test_existing_membership_is_noop():
    assert isinstance(
        decide_domain_join("auto_join", email_verified=True, has_membership=True), Noop
    )


def test_off_policy():
    assert isinstance(decide_domain_join("off", email_verified=True, has_membership=False), Off)


def test_auto_join():
    assert isinstance(
        decide_domain_join("auto_join", email_verified=True, has_membership=False), AutoJoin
    )


def test_admin_approval():
    assert isinstance(
        decide_domain_join("admin_approval", email_verified=True, has_membership=False),
        NeedsApproval,
    )
