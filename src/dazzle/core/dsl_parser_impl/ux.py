"""
UX semantic layer parsing for DAZZLE DSL.

Handles UX block parsing including attention signals, persona variants,
and surface-level UX specifications.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class UXParserMixin:
    """
    Mixin providing UX semantic layer parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any
        parse_condition_expr: Any

    def parse_ux_block(self) -> ir.UXSpec:
        """
        Parse UX block within a surface.

        Syntax:
            ux:
              purpose: "..."
              show: field1, field2
              sort: field1 desc, field2 asc
              filter: field1, field2
              search: field1, field2
              empty: "..."
              attention critical:
                when: condition
                message: "..."
                action: surface_name
              for persona_name:
                scope: ...
                ...
        """
        self.expect(TokenType.UX)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        purpose = None
        show: list[str] = []
        sort: list[ir.SortSpec] = []
        filter_fields: list[str] = []
        search_fields: list[str] = []
        empty_message = None
        search_first = False
        attention_signals: list[ir.AttentionSignal] = []
        persona_variants: list[ir.PersonaVariant] = []

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

            # show: field1, field2
            elif self.match(TokenType.SHOW):
                self.advance()
                self.expect(TokenType.COLON)
                show = self.parse_field_list()
                self.skip_newlines()

            # sort: field1 desc, field2 asc
            elif self.match(TokenType.SORT):
                self.advance()
                self.expect(TokenType.COLON)
                sort = self.parse_sort_list()
                self.skip_newlines()

            # filter: field1, field2
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                filter_fields = self.parse_field_list()
                self.skip_newlines()

            # search: field1, field2
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                search_fields = self.parse_field_list()
                self.skip_newlines()

            # empty: "..."
            elif self.match(TokenType.EMPTY):
                self.advance()
                self.expect(TokenType.COLON)
                empty_message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # search_first: true|false
            elif self.match(TokenType.SEARCH_FIRST):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    search_first = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    search_first = False
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Expected true or false, got {token.type.value}",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # attention critical/warning/notice/info:
            elif self.match(TokenType.ATTENTION):
                signal = self.parse_attention_signal()
                attention_signals.append(signal)

            # for persona_name:
            elif self.match(TokenType.FOR):
                variant = self.parse_persona_variant()
                persona_variants.append(variant)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.UXSpec(
            purpose=purpose,
            show=show,
            sort=sort,
            filter=filter_fields,
            search=search_fields,
            empty_message=empty_message,
            search_first=search_first,
            attention_signals=attention_signals,
            persona_variants=persona_variants,
        )

    def parse_field_list(self) -> list[str]:
        """Parse comma-separated list of field names."""
        fields = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.COMMA):
            self.advance()
            fields.append(self.expect_identifier_or_keyword().value)

        return fields

    def parse_sort_list(self) -> list[ir.SortSpec]:
        """Parse comma-separated list of sort expressions (field [asc|desc])."""
        sorts = []

        field = self.expect_identifier_or_keyword().value
        direction = "asc"
        if self.match(TokenType.ASC):
            self.advance()
            direction = "asc"
        elif self.match(TokenType.DESC):
            self.advance()
            direction = "desc"
        sorts.append(ir.SortSpec(field=field, direction=direction))

        while self.match(TokenType.COMMA):
            self.advance()
            field = self.expect_identifier_or_keyword().value
            direction = "asc"
            if self.match(TokenType.ASC):
                self.advance()
                direction = "asc"
            elif self.match(TokenType.DESC):
                self.advance()
                direction = "desc"
            sorts.append(ir.SortSpec(field=field, direction=direction))

        return sorts

    def parse_attention_signal(self) -> ir.AttentionSignal:
        """
        Parse attention signal block.

        Syntax:
            attention critical:
              when: condition_expr
              message: "..."
              action: surface_name
        """
        self.expect(TokenType.ATTENTION)

        # Parse signal level
        if self.match(TokenType.CRITICAL):
            level = ir.SignalLevel.CRITICAL
            self.advance()
        elif self.match(TokenType.WARNING):
            level = ir.SignalLevel.WARNING
            self.advance()
        elif self.match(TokenType.NOTICE):
            level = ir.SignalLevel.NOTICE
            self.advance()
        elif self.match(TokenType.INFO):
            level = ir.SignalLevel.INFO
            self.advance()
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected signal level (critical/warning/notice/info), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        condition = None
        message = None
        action = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # when: condition_expr
            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                self.skip_newlines()

            # message: "..."
            elif self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # action: surface_name
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if condition is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'when:' condition",
                self.file,
                token.line,
                token.column,
            )

        if message is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'message:'",
                self.file,
                token.line,
                token.column,
            )

        return ir.AttentionSignal(
            level=level,
            condition=condition,
            message=message,
            action=action,
        )

    def parse_persona_variant(self) -> ir.PersonaVariant:
        """
        Parse persona variant block.

        Syntax:
            for persona_name:
              scope: all | condition_expr
              purpose: "..."
              show: field1, field2
              hide: field1, field2
              show_aggregate: metric1, metric2
              action_primary: surface_name
              read_only: true|false
        """
        self.expect(TokenType.FOR)
        persona = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        scope = None
        scope_all = False
        purpose = None
        show: list[str] = []
        hide: list[str] = []
        show_aggregate: list[str] = []
        action_primary = None
        read_only = False
        defaults: dict[str, Any] = {}
        focus: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # scope: all | condition_expr
            if self.match(TokenType.SCOPE):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.ALL):
                    self.advance()
                    scope_all = True
                else:
                    scope = self.parse_condition_expr()
                self.skip_newlines()

            # purpose: "..."
            elif self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # show: field1, field2
            elif self.match(TokenType.SHOW):
                self.advance()
                self.expect(TokenType.COLON)
                show = self.parse_field_list()
                self.skip_newlines()

            # hide: field1, field2
            elif self.match(TokenType.HIDE):
                self.advance()
                self.expect(TokenType.COLON)
                hide = self.parse_field_list()
                self.skip_newlines()

            # show_aggregate: metric1, metric2
            elif self.match(TokenType.SHOW_AGGREGATE):
                self.advance()
                self.expect(TokenType.COLON)
                show_aggregate = self.parse_field_list()
                self.skip_newlines()

            # action_primary: surface_name
            elif self.match(TokenType.ACTION_PRIMARY):
                self.advance()
                self.expect(TokenType.COLON)
                action_primary = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # read_only: true|false
            elif self.match(TokenType.READ_ONLY):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    read_only = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    read_only = False
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Expected true or false, got {token.type.value}",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # defaults:
            elif self.match(TokenType.DEFAULTS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    # field_name: value
                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    # Parse value (could be identifier, string, etc.)
                    if self.match(TokenType.STRING):
                        defaults[field_name] = self.advance().value
                    else:
                        # For identifiers like current_user
                        defaults[field_name] = self.expect_identifier_or_keyword().value
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # focus: region1, region2
            elif self.match(TokenType.FOCUS):
                self.advance()
                self.expect(TokenType.COLON)
                focus = self.parse_field_list()
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.PersonaVariant(
            persona=persona,
            scope=scope,
            scope_all=scope_all,
            purpose=purpose,
            show=show,
            hide=hide,
            show_aggregate=show_aggregate,
            action_primary=action_primary,
            read_only=read_only,
            defaults=defaults,
            focus=focus,
        )
