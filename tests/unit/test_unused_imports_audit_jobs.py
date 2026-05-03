"""Tests for #988 fix — `check_unused_imports` walks audit/job entity refs.

Pre-fix, splitting framework-runtime declarations into a separate
DSL file:

    module project.runtime
    use project.core

    audit on Ticket: ...
    job x: trigger: on_create Ticket ...

…triggered a false-positive "imports but never uses it" warning,
even though `audit on Ticket` and `trigger: on_create Ticket`
both reference the imported entity.

Now the checker walks `module.fragment.audits` (each
`AuditSpec.entity`) and `module.fragment.jobs` (each
`JobTrigger.entity`) so cross-module references count.
"""

from __future__ import annotations

import pathlib
import textwrap

from dazzle.core.linker import build_appspec
from dazzle.core.linker_impl import (
    build_symbol_table,
    check_unused_imports,
    resolve_dependencies,
)
from dazzle.core.parser import parse_modules


def _link_and_check(*sources: tuple[str, str], tmp_path: pathlib.Path) -> list[str]:
    """Parse a multi-module project and return any unused-import warnings."""
    paths = []
    for filename, src in sources:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(src).lstrip())
        paths.append(p)
    modules = parse_modules(paths)
    sorted_modules = resolve_dependencies(modules)
    symbols = build_symbol_table(sorted_modules)
    return check_unused_imports(sorted_modules, symbols)


# ---------------------------------------------------------------------------
# Audit references count
# ---------------------------------------------------------------------------


class TestAuditReference:
    def test_audit_on_imported_entity_counts_as_use(self, tmp_path):
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                audit on Ticket:
                  track: status
                  show_to: persona(admin)
                  retention: 90d
                """,
            ),
            tmp_path=tmp_path,
        )
        # No "never uses" warning — audit block IS a use.
        for w in warnings:
            assert "never uses" not in w, f"unexpected: {w}"

    def test_unused_import_still_warns_without_reference(self, tmp_path):
        # Sanity: the checker still flags genuinely unused imports.
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                # No audit / job / surface / etc. references — genuinely unused.
                """,
            ),
            tmp_path=tmp_path,
        )
        assert any("proj.core" in w and "never uses" in w for w in warnings)


# ---------------------------------------------------------------------------
# Job-trigger references count
# ---------------------------------------------------------------------------


class TestJobTriggerReference:
    def test_on_create_trigger_counts_as_use(self, tmp_path):
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                job notify "Notify":
                  trigger: on_create Ticket
                  run: app.jobs:notify
                """,
            ),
            tmp_path=tmp_path,
        )
        for w in warnings:
            assert "never uses" not in w, f"unexpected: {w}"

    def test_field_changed_trigger_counts_as_use(self, tmp_path):
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                job survey "Survey":
                  trigger: on_field_changed Ticket.status
                  run: app.jobs:send_survey
                """,
            ),
            tmp_path=tmp_path,
        )
        for w in warnings:
            assert "never uses" not in w, f"unexpected: {w}"

    def test_scheduled_only_job_no_trigger_does_not_save_import(self, tmp_path):
        # A job with only a `schedule:` block (no triggers) doesn't
        # reference any entity. If the runtime module imports core
        # but only has scheduled jobs and no other refs, the import
        # SHOULD still be flagged unused.
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                job rollup "Daily rollup":
                  schedule: cron("0 1 * * *")
                  run: app.jobs:rollup
                """,
            ),
            tmp_path=tmp_path,
        )
        assert any("proj.core" in w and "never uses" in w for w in warnings)


# ---------------------------------------------------------------------------
# End-to-end against the dogfood support_tickets DSL pattern
# ---------------------------------------------------------------------------


class TestEndToEndCombined:
    def test_combined_audit_and_jobs_in_one_runtime_module(self, tmp_path):
        # Mirrors the actual examples/support_tickets/dsl/runtime.dsl
        # pattern — a single runtime module with both audit blocks
        # and triggered jobs, all referencing core entities.
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)
                  priority: str(50)

                entity Comment "C":
                  id: uuid pk
                  content: text
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                audit on Ticket:
                  track: status
                  show_to: persona(admin)
                  retention: 90d

                audit on Comment:
                  track: content
                  show_to: persona(admin)

                job notify "Notify":
                  trigger: on_create Ticket
                  run: app.jobs:notify

                job survey "Survey":
                  trigger: on_field_changed Ticket.status
                  run: app.jobs:survey
                """,
            ),
            tmp_path=tmp_path,
        )
        for w in warnings:
            assert "never uses" not in w, f"unexpected: {w}"


# ---------------------------------------------------------------------------
# Defensive: missing entity name (malformed spec) doesn't crash checker
# ---------------------------------------------------------------------------


class TestDefensive:
    def test_full_appspec_build_works(self, tmp_path):
        # End-to-end build_appspec to confirm the audit + job
        # references survive linker rebuilds.
        for fname, src in [
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)
                """,
            ),
            (
                "runtime.dsl",
                """
                module proj.runtime
                use proj.core

                audit on Ticket:
                  track: status
                  show_to: persona(admin)
                """,
            ),
        ]:
            (tmp_path / fname).write_text(textwrap.dedent(src).lstrip())

        modules = parse_modules([tmp_path / "core.dsl", tmp_path / "runtime.dsl"])
        appspec = build_appspec(modules, "proj.runtime")
        # Sanity: the audit was captured + applied.
        assert len(appspec.audits) == 1
        assert appspec.audits[0].entity == "Ticket"
