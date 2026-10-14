"""Tests for typed empty-state messages (#807).

Covers:
- IR: EmptyMessages struct.
- Parser: legacy string form still works; block form populates the struct.
- Unknown sub-keys raise a parse error.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir


class TestIR:
    def test_empty_messages_all_optional(self) -> None:
        em = ir.EmptyMessages()
        assert em.collection is None
        assert em.filtered is None
        assert em.forbidden is None


# Parser tests — use parse_dsl against a minimal DSL snippet
_BASE = """\
module test_app
app test_app "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
  ux:
"""


class TestParser:
    def _parse_ux(self, ux_body: str) -> ir.UXSpec:
        """Parse a DSL snippet with the given ux: block body and return
        the first surface's UXSpec."""
        import tempfile
        from pathlib import Path

        from dazzle.core.linker import build_appspec
        from dazzle.core.parser import parse_modules

        dsl_text = _BASE + ux_body
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
            f.write(dsl_text)
            tmp_path = Path(f.name)
        modules = parse_modules([tmp_path])
        appspec = build_appspec(modules, root_module_name="test_app")
        assert appspec.surfaces
        surface = appspec.surfaces[0]
        assert surface.ux is not None
        return surface.ux

    def test_legacy_string_form(self) -> None:
        ux = self._parse_ux('    empty: "No tasks yet."\n')
        assert ux.empty_message == "No tasks yet."

    def test_block_form_all_three(self) -> None:
        ux = self._parse_ux(
            "    empty:\n"
            '      collection: "No tasks yet."\n'
            '      filtered: "No tasks match these filters."\n'
            '      forbidden: "You can\'t see any tasks."\n'
        )
        assert isinstance(ux.empty_message, ir.EmptyMessages)
        assert ux.empty_message.collection == "No tasks yet."
        assert ux.empty_message.filtered == "No tasks match these filters."
        assert ux.empty_message.forbidden == "You can't see any tasks."

    def test_block_form_partial(self) -> None:
        """Any subset of keys is valid — omitted ones use framework
        defaults at render time."""
        ux = self._parse_ux('    empty:\n      filtered: "No tasks match these filters."\n')
        assert isinstance(ux.empty_message, ir.EmptyMessages)
        assert ux.empty_message.collection is None
        assert ux.empty_message.filtered == "No tasks match these filters."
        assert ux.empty_message.forbidden is None

    def test_block_form_unknown_key_raises(self) -> None:
        with pytest.raises(Exception) as exc_info:
            self._parse_ux('    empty:\n      bogus: "oops"\n')
        # Parser raises ParseError with a helpful message
        assert "bogus" in str(exc_info.value) or "Unknown" in str(exc_info.value)
