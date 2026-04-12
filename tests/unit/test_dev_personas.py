"""Tests for dev persona provisioning (#768)."""

from unittest.mock import MagicMock

from dazzle.cli.runtime_impl.dev_personas import (
    provision_dev_personas,
)


def _make_persona(id: str, label: str = "", description: str | None = None):
    """Build a minimal persona-like object for tests."""
    p = MagicMock()
    p.id = id
    p.label = label or id.title()
    p.description = description
    return p


def _make_appspec(personas: list, stories: list | None = None):
    spec = MagicMock()
    spec.personas = personas
    spec.stories = stories or []
    return spec


class TestProvisionDevPersonas:
    def test_empty_personas_returns_empty_list(self):
        """AppSpec with no personas → returns []."""
        appspec = _make_appspec([])
        result = provision_dev_personas(appspec, auth_store=MagicMock())
        assert result == []

    def test_creates_missing_users(self):
        """Personas with no existing user → create_user called for each."""
        appspec = _make_appspec(
            [
                _make_persona("admin", "Administrator"),
                _make_persona("accountant", "Accountant"),
            ]
        )
        auth_store = MagicMock()
        # No existing users
        auth_store.get_user_by_email = MagicMock(return_value=None)

        # create_user returns a user-like object
        def make_user(email, **kwargs):
            u = MagicMock()
            u.id = f"user-{email}"
            u.email = email
            return u

        auth_store.create_user = MagicMock(side_effect=make_user)

        result = provision_dev_personas(appspec, auth_store=auth_store)

        assert len(result) == 2
        assert result[0].persona_id == "admin"
        assert result[0].email == "admin@example.test"
        assert result[0].display_name == "Administrator"
        assert result[1].persona_id == "accountant"
        assert result[1].email == "accountant@example.test"

        # Both users should have been created
        assert auth_store.create_user.call_count == 2

    def test_idempotent_existing_users_not_recreated(self):
        """If user already exists, don't call create_user."""
        appspec = _make_appspec([_make_persona("admin", "Administrator")])
        auth_store = MagicMock()
        existing_user = MagicMock()
        existing_user.id = "user-admin-existing"
        auth_store.get_user_by_email = MagicMock(return_value=existing_user)
        auth_store.create_user = MagicMock()

        result = provision_dev_personas(appspec, auth_store=auth_store)

        assert len(result) == 1
        assert result[0].user_id == "user-admin-existing"
        auth_store.create_user.assert_not_called()

    def test_create_user_receives_persona_role(self):
        """create_user should be called with roles=[persona.id]."""
        appspec = _make_appspec([_make_persona("accountant")])
        auth_store = MagicMock()
        auth_store.get_user_by_email = MagicMock(return_value=None)
        auth_store.create_user = MagicMock()
        auth_store.create_user.return_value = MagicMock(id="new-user")

        provision_dev_personas(appspec, auth_store=auth_store)

        call_kwargs = auth_store.create_user.call_args.kwargs
        assert call_kwargs["email"] == "accountant@example.test"
        assert call_kwargs["roles"] == ["accountant"]

    def test_provisioning_failure_logged_not_raised(self, capsys):
        """If create_user raises, log warning and continue with other personas."""
        appspec = _make_appspec(
            [
                _make_persona("good"),
                _make_persona("bad"),
            ]
        )
        auth_store = MagicMock()
        auth_store.get_user_by_email = MagicMock(return_value=None)

        def create_maybe_fail(email, **kwargs):
            if email == "bad@example.test":
                raise RuntimeError("simulated failure")
            u = MagicMock()
            u.id = f"user-{email}"
            return u

        auth_store.create_user = MagicMock(side_effect=create_maybe_fail)

        result = provision_dev_personas(appspec, auth_store=auth_store)

        # Only the good persona should be in the result
        assert len(result) == 1
        assert result[0].persona_id == "good"

        # A warning should have been printed
        captured = capsys.readouterr()
        assert "bad" in captured.err
        assert "simulated failure" in captured.err

    def test_description_pulled_from_persona(self):
        """persona.description is copied to ProvisionedPersona.description."""
        appspec = _make_appspec(
            [_make_persona("admin", "Administrator", description="Full system access")]
        )
        auth_store = MagicMock()
        auth_store.get_user_by_email = MagicMock(return_value=None)
        auth_store.create_user = MagicMock(return_value=MagicMock(id="u"))

        result = provision_dev_personas(appspec, auth_store=auth_store)

        assert result[0].description == "Full system access"

    def test_description_fallback_when_missing(self):
        """If persona has no description, use a sensible default."""
        appspec = _make_appspec([_make_persona("admin", description=None)])
        auth_store = MagicMock()
        auth_store.get_user_by_email = MagicMock(return_value=None)
        auth_store.create_user = MagicMock(return_value=MagicMock(id="u"))

        result = provision_dev_personas(appspec, auth_store=auth_store)

        assert result[0].description  # non-empty
