"""Tests for #988 fix — `check_unused_imports` walks audit entity refs.

Pre-fix, splitting framework-runtime declarations into a separate
DSL file:

    module project.runtime
    use project.core

    audit on Ticket: ...

…triggered a false-positive "imports but never uses it" warning,
even though `audit on Ticket` references the imported entity.

Now the checker walks `module.fragment.audits` (each `AuditSpec.entity`)
so cross-module references count.
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

                # No audit / surface / etc. references — genuinely unused.
                """,
            ),
            tmp_path=tmp_path,
        )
        assert any("proj.core" in w and "never uses" in w for w in warnings)


# ---------------------------------------------------------------------------
# Defensive: missing entity name (malformed spec) doesn't crash checker
# ---------------------------------------------------------------------------


class TestDefensive:
    def test_full_appspec_build_works(self, tmp_path):
        # End-to-end build_appspec to confirm the audit
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


# ---------------------------------------------------------------------------
# Guide references count (#1379)
# ---------------------------------------------------------------------------


class TestGuideReference:
    def test_guide_targeting_imported_surface_counts_as_use(self, tmp_path):
        """#1379: a guides module that `use`s core and decorates a core surface
        (step target / on_complete.redirect) must NOT warn 'never uses'."""
        warnings = _link_and_check(
            (
                "core.dsl",
                """
                module proj.core
                app a "A"

                entity Task "T":
                  id: uuid pk
                  title: str(50)

                surface task_list "Tasks":
                  uses entity Task
                  mode: list
                  section main:
                    field title "Title"
                """,
            ),
            (
                "guides.dsl",
                """
                module proj.guides
                use proj.core

                guide member_onboarding "Onboarding":
                  audience: persona = member

                  step welcome:
                    kind: spotlight
                    target: surface.task_list
                    title: "Welcome"
                    body: "Your tasks live here."
                    complete_on: dismiss

                  step_order: [welcome]

                  on_complete:
                    redirect: surface.task_list
                """,
            ),
            tmp_path=tmp_path,
        )
        for w in warnings:
            assert "never uses" not in w, f"unexpected: {w}"
