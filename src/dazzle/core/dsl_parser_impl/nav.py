"""
Shared nav definition parser mixin (v0.61.95, #926).

Top-level `nav <name>:` blocks declare a reusable list of nav groups
that workspaces reference via `uses nav <name>`. The shape inside the
block mirrors the existing per-workspace `nav_group` syntax — the only
difference is the `group` keyword (instead of `nav_group`) chosen for
lighter visual weight inside an already-namespaced block.

DSL Syntax::

    nav teacher_nav:
      group "My Classes" icon=users:
        TeachingGroup
      group "Insights" icon=target:
        CohortAnalysis
        TeachingRecommendation

The `group` keyword is also accepted as `nav_group` for parity with
the per-workspace syntax — both forms parse identically inside a
`nav` block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class NavParserMixin:
    """Parser mixin for top-level `nav <name>:` blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _parse_nav_group: Any

    def parse_nav_definition(self) -> ir.NavDefinitionSpec:
        """Parse a top-level `nav <name>:` block."""
        self.advance()  # consume `nav`
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        groups: list[ir.NavGroupSpec] = []
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            if self.match(TokenType.GROUP, TokenType.NAV_GROUP):
                groups.append(self._parse_nav_group())
            else:
                # Skip unknown lines defensively — keeps parse alive on
                # garbled input rather than aborting the whole file.
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.NavDefinitionSpec(name=name, groups=groups)
