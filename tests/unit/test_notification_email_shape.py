"""Tests for the email-shaped `notification` DSL block (#952 cycle 1).

The block extends the existing notification primitive with `subject:`
and `template:` (file path) fields so transactional email sends can
be expressed in DSL. The parser, IR, and AppSpec wiring are validated
end-to-end here. Runtime delivery (SMTP / SES / SendGrid) is cycle
2+ and tracked separately on #952.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest


@pytest.fixture()
def parse_dsl():
    """Return a callable that parses DSL source and returns an AppSpec."""
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path) -> object:
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


class TestEmailShapedNotification:
    """`subject:` and `template:` (file path) fields parse + land in IR."""

    def test_subject_field_parses(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app notification_test "Notification Test"

            entity User "User":
              id: uuid pk
              email: str(200) required

            notification welcome_email "Welcome":
              on: User created
              channels: [email]
              subject: "Welcome to the app"
              message: "Hello!"
              recipients: field(email)
              preferences: mandatory
            """,
            tmp_path,
        )
        notif = next(n for n in appspec.notifications if n.name == "welcome_email")
        assert notif.subject == "Welcome to the app"
        assert notif.message == "Hello!"
        assert notif.template == ""

    def test_template_field_parses_quoted_path(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app notification_test "Notification Test"

            entity User "User":
              id: uuid pk
              email: str(200) required

            notification welcome_email "Welcome":
              on: User created
              channels: [email]
              subject: "Welcome"
              template: "emails/welcome.html"
              recipients: field(email)
              preferences: mandatory
            """,
            tmp_path,
        )
        notif = next(n for n in appspec.notifications if n.name == "welcome_email")
        assert notif.template == "emails/welcome.html"

    def test_template_field_parses_bare_path(self, parse_dsl, tmp_path):
        """Unquoted `emails/welcome.html` should also work — common form."""
        appspec = parse_dsl(
            """
            module test
            app notification_test "Notification Test"

            entity User "User":
              id: uuid pk
              email: str(200) required

            notification welcome_email "Welcome":
              on: User created
              channels: [email]
              subject: "Welcome"
              template: emails/welcome.html
              recipients: field(email)
              preferences: mandatory
            """,
            tmp_path,
        )
        notif = next(n for n in appspec.notifications if n.name == "welcome_email")
        assert notif.template == "emails/welcome.html"

    def test_subject_and_template_default_to_empty(self, parse_dsl, tmp_path):
        """Existing notifications without `subject:` / `template:` keep
        their previous shape — no breakage for in-app/sms/slack callers."""
        appspec = parse_dsl(
            """
            module test
            app notification_test "Notification Test"

            entity Invoice "Invoice":
              id: uuid pk
              status: str(20) required

            notification overdue_alert "Overdue Alert":
              on: Invoice.status -> overdue
              channels: [in_app]
              message: "Invoice {{title}} is overdue"
              recipients: role(accountant)
              preferences: opt_out
            """,
            tmp_path,
        )
        notif = next(n for n in appspec.notifications if n.name == "overdue_alert")
        assert notif.message == "Invoice {{title}} is overdue"
        assert notif.subject == ""
        assert notif.template == ""

    def test_template_takes_precedence_documented_in_spec(self):
        """The IR docstring documents that `template` wins over `message`
        for the email body when both are set. Pin the contract here so
        cycle 2's runtime can rely on it."""
        from dazzle.core.ir.notifications import NotificationSpec

        # Both set — runtime must prefer template (cycle 2 will assert this
        # when the dispatcher lands; cycle 1 only documents the contract).
        spec = NotificationSpec(
            name="x",
            trigger={"entity": "User", "event": "created"},
            message="inline body",
            subject="subject",
            template="emails/x.html",
        )
        assert spec.template == "emails/x.html"
        assert spec.message == "inline body"

    def test_immutability_preserved(self):
        """NotificationSpec was frozen pre-#952; the new fields preserve
        that — frozen enforces `==` semantics that downstream caches rely on."""
        from dazzle.core.ir.notifications import NotificationSpec

        spec = NotificationSpec(
            name="x",
            trigger={"entity": "User", "event": "created"},
            subject="hi",
            template="emails/x.html",
        )
        # Pydantic frozen → mutation raises ValidationError or AttributeError
        # depending on Pydantic version; either is acceptable as "frozen".
        with pytest.raises((Exception,)):
            spec.subject = "different"  # type: ignore[misc]
        # Round-trip equality
        spec2 = NotificationSpec(
            name="x",
            trigger={"entity": "User", "event": "created"},
            subject="hi",
            template="emails/x.html",
        )
        assert spec == spec2


# Import-time gate: ensure the new fields are exported from the IR
# package so `from dazzle.core.ir import NotificationSpec` keeps working.
def test_ir_notification_spec_has_new_fields() -> None:
    from dazzle.core.ir import NotificationSpec

    fields = NotificationSpec.model_fields
    assert "subject" in fields
    assert "template" in fields
    assert fields["subject"].default == ""
    assert fields["template"].default == ""
