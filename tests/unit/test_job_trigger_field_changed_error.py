"""Tests for #987 fix — `on_field_changed` requires a field name.

Pre-fix, `on_field_changed Ticket status` parsed cleanly with
`field=None` and the runtime trigger silently never fired.
Now the parser raises with a targeted message that points at
the missing DOT separator.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from dazzle.core.errors import ParseError
from dazzle.core.parser import parse_modules


def _parse(source: str, tmp_path: pathlib.Path):
    dsl_path = tmp_path / "test.dsl"
    dsl_path.write_text(textwrap.dedent(source).lstrip())
    return parse_modules([dsl_path])


# ---------------------------------------------------------------------------
# Error: space-separated field name
# ---------------------------------------------------------------------------


class TestSpaceSeparatedRejected:
    def test_keyword_field_name_rejected(self, tmp_path):
        # `status` lexes as a reserved STATUS token but the parser
        # still recognises it as a candidate field name and surfaces
        # the targeted "use DOT" message rather than a generic one.
        with pytest.raises(ParseError, match="DOT separator"):
            _parse(
                """
                module test
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)

                job x "X":
                  trigger: on_field_changed Ticket status
                  run: app.jobs:x
                """,
                tmp_path,
            )

    def test_identifier_field_name_rejected(self, tmp_path):
        # `priority` is a plain identifier — same DOT message.
        with pytest.raises(ParseError, match="DOT separator"):
            _parse(
                """
                module test
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  priority: str(50)

                job x "X":
                  trigger: on_field_changed Ticket priority
                  run: app.jobs:x
                """,
                tmp_path,
            )

    def test_error_message_includes_correct_form(self, tmp_path):
        # The error must include the suggested fix so the author can
        # copy-paste rather than hunt for the syntax.
        with pytest.raises(ParseError, match=r"on_field_changed Ticket\.status"):
            _parse(
                """
                module test
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)

                job x "X":
                  trigger: on_field_changed Ticket status
                  run: app.jobs:x
                """,
                tmp_path,
            )


# ---------------------------------------------------------------------------
# Error: missing field entirely
# ---------------------------------------------------------------------------


class TestMissingFieldRejected:
    def test_no_field_after_entity(self, tmp_path):
        # `on_field_changed Ticket` (newline immediately) — generic
        # missing-field message, not the DOT one.
        with pytest.raises(ParseError, match="requires a field name"):
            _parse(
                """
                module test
                app a "A"

                entity Ticket "T":
                  id: uuid pk

                job x "X":
                  trigger: on_field_changed Ticket
                  run: app.jobs:x
                """,
                tmp_path,
            )


# ---------------------------------------------------------------------------
# Happy path: DOT form still works
# ---------------------------------------------------------------------------


class TestDotFormStillWorks:
    def test_dot_form_parses(self, tmp_path):
        modules = _parse(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
              status: str(50)

            job x "X":
              trigger: on_field_changed Ticket.status
              run: app.jobs:x
            """,
            tmp_path,
        )
        # Trigger captured with the field set.
        job = modules[0].fragment.jobs[0]
        trigger = job.triggers[0]
        assert trigger.entity == "Ticket"
        assert trigger.event == "field_changed"
        assert trigger.field == "status"

    def test_dot_form_with_when_condition(self, tmp_path):
        # DOT field + when clause — nothing about the fix should
        # have broken the existing combined form.
        modules = _parse(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
              status: str(50)
              priority: str(50)

            job x "X":
              trigger: on_field_changed Ticket.status when priority is_set
              run: app.jobs:x
            """,
            tmp_path,
        )
        trigger = modules[0].fragment.jobs[0].triggers[0]
        assert trigger.field == "status"
        assert trigger.when_condition == "priority is_set"


# ---------------------------------------------------------------------------
# Other event kinds unaffected
# ---------------------------------------------------------------------------


class TestOtherEventsUnchanged:
    def test_on_create_no_field_required(self, tmp_path):
        # `on_create Ticket` (no field, no DOT) must still work —
        # the new error path is only for field_changed.
        modules = _parse(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk

            job x "X":
              trigger: on_create Ticket
              run: app.jobs:x
            """,
            tmp_path,
        )
        trigger = modules[0].fragment.jobs[0].triggers[0]
        assert trigger.event == "created"
        assert trigger.field is None

    def test_on_update_no_field_required(self, tmp_path):
        modules = _parse(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk

            job x "X":
              trigger: on_update Ticket
              run: app.jobs:x
            """,
            tmp_path,
        )
        assert modules[0].fragment.jobs[0].triggers[0].event == "updated"

    def test_on_delete_no_field_required(self, tmp_path):
        modules = _parse(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk

            job x "X":
              trigger: on_delete Ticket
              run: app.jobs:x
            """,
            tmp_path,
        )
        assert modules[0].fragment.jobs[0].triggers[0].event == "deleted"
