"""
Workspace parsing for DAZZLE DSL.

Handles workspace declarations including regions, aggregates, and display modes.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType

if TYPE_CHECKING:
    pass

# Type alias for self in mixin methods - tells mypy this mixin
# will be combined with a class implementing ParserProtocol
_Self = Any  # At runtime, just Any; mypy sees the annotations


class WorkspaceParserMixin:
    """
    Mixin providing workspace parsing.

    Note: This mixin expects to be combined with BaseParser (or a class
    implementing ParserProtocol) via multiple inheritance.
    """

    # Declare the interface this mixin expects (for documentation)
    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        parse_condition_expr: Any
        parse_sort_list: Any
        parse_ux_block: Any
        current_token: Any
        file: Any

    def parse_workspace(self) -> ir.WorkspaceSpec:
        """
        Parse workspace declaration.

        Syntax:
            workspace name "Title":
              purpose: "..."
              region_name:
                source: EntityName
                filter: condition_expr
                sort: field desc
                limit: 10
                display: list|grid|timeline|map
                action: surface_name
                empty: "..."
                aggregate:
                  metric_name: expr
              ux:
                ...
        """
        self.expect(TokenType.WORKSPACE)

        name = self.expect_identifier_or_keyword().value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        purpose = None
        engine_hint = None
        regions: list[ir.WorkspaceRegion] = []
        ux_spec = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # purpose: "..."
            if self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # engine_hint: "archetype_name" (v0.3.1)
            elif self.match(TokenType.ENGINE_HINT):
                self.advance()
                self.expect(TokenType.COLON)
                engine_hint = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # ux: (optional workspace-level UX)
            elif self.match(TokenType.UX):
                ux_spec = self.parse_ux_block()

            # region_name: (workspace region)
            elif self.match(TokenType.IDENTIFIER):
                region = self.parse_workspace_region()
                regions.append(region)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.WorkspaceSpec(
            name=name,
            title=title,
            purpose=purpose,
            engine_hint=engine_hint,
            regions=regions,
            ux=ux_spec,
        )

    def parse_workspace_region(self) -> ir.WorkspaceRegion:
        """Parse workspace region."""
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        source = None
        filter_expr = None
        sort: list[ir.SortSpec] = []
        limit = None
        display = ir.DisplayMode.LIST
        action = None
        empty_message = None
        group_by = None
        aggregates: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # source: EntityName
            if self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                source = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # filter: condition_expr
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                filter_expr = self.parse_condition_expr()
                self.skip_newlines()

            # sort: field desc
            elif self.match(TokenType.SORT):
                self.advance()
                self.expect(TokenType.COLON)
                sort = self.parse_sort_list()
                self.skip_newlines()

            # limit: 10
            elif self.match(TokenType.LIMIT):
                self.advance()
                self.expect(TokenType.COLON)
                limit = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            # display: list|grid|timeline|map
            elif self.match(TokenType.DISPLAY):
                self.advance()
                self.expect(TokenType.COLON)
                display_token = self.expect_identifier_or_keyword()
                display = ir.DisplayMode(display_token.value)
                self.skip_newlines()

            # action: surface_name
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # empty: "..."
            elif self.match(TokenType.EMPTY):
                self.advance()
                self.expect(TokenType.COLON)
                empty_message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # group_by: field_name
            elif self.match(TokenType.GROUP_BY):
                self.advance()
                self.expect(TokenType.COLON)
                group_by = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # aggregate:
            elif self.match(TokenType.AGGREGATE):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    # metric_name: expr
                    metric_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    # For now, capture aggregate expression as string until newline
                    expr_parts = []
                    while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                        expr_parts.append(self.advance().value)
                    aggregates[metric_name] = " ".join(expr_parts)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        if source is None:
            token = self.current_token()
            raise make_parse_error(
                f"Workspace region '{name}' requires 'source:'",
                self.file,
                token.line,
                token.column,
            )

        return ir.WorkspaceRegion(
            name=name,
            source=source,
            filter=filter_expr,
            sort=sort,
            limit=limit,
            display=display,
            action=action,
            empty_message=empty_message,
            group_by=group_by,
            aggregates=aggregates,
        )
