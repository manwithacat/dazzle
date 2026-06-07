"""
Integration parsing for DAZZLE DSL.

Handles integration declarations including actions, syncs, and mappings.
v0.30.0: Added declarative mapping blocks with triggers, HTTP requests, and error strategies.
v0.33.1: Added transform blocks, function-call expressions, source/target directives.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch

# HTTP method identifiers mapped to enum
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})

# Auth type identifiers mapped to enum
_AUTH_TYPES = {
    "api_key": ir.AuthType.API_KEY,
    "oauth2": ir.AuthType.OAUTH2,
    "bearer": ir.AuthType.BEARER,
    "basic": ir.AuthType.BASIC,
}

# Trigger type identifiers mapped to enum
_TRIGGER_TYPES = {
    "on_create": ir.MappingTriggerType.ON_CREATE,
    "on_update": ir.MappingTriggerType.ON_UPDATE,
    "on_delete": ir.MappingTriggerType.ON_DELETE,
    "on_transition": ir.MappingTriggerType.ON_TRANSITION,
    "manual": ir.MappingTriggerType.MANUAL,
}

# Error action identifiers mapped to enum
_ERROR_ACTIONS = {
    "ignore": ir.ErrorAction.IGNORE,
    "log_warning": ir.ErrorAction.LOG_WARNING,
    "revert_transition": ir.ErrorAction.REVERT_TRANSITION,
    "retry": ir.ErrorAction.RETRY,
}


class IntegrationParserMixin:
    """
    Mixin providing integration parsing.

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
        collect_line_as_expr: Any
        _source_location: Any
        _parse_construct_header: Any

    def parse_integration(self) -> ir.IntegrationSpec:
        """Parse integration declaration."""
        name, title, loc = self._parse_construct_header(TokenType.INTEGRATION)

        base_url = None
        auth = None
        api_refs: list[str] = []
        foreign_model_refs: list[str] = []
        actions: list[ir.IntegrationAction] = []
        syncs: list[ir.IntegrationSync] = []
        mappings: list[ir.IntegrationMapping] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            tok = self.current_token()

            # uses service ServiceName[,ServiceName]
            if self.match(TokenType.USES):
                self.advance()

                if self.match(TokenType.SERVICE):
                    self.advance()
                    api_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    while self.match(TokenType.COMMA):
                        self.advance()
                        api_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    self.skip_newlines()

                # uses foreign ForeignName[,ForeignName]
                elif self.match(TokenType.FOREIGN):
                    self.advance()
                    foreign_model_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    while self.match(TokenType.COMMA):
                        self.advance()
                        foreign_model_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    self.skip_newlines()

            # action action_name:
            elif self.match(TokenType.ACTION):
                self.advance()
                action_name = self.expect(TokenType.IDENTIFIER).value

                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                action = self._parse_action_body(action_name)
                actions.append(action)

                self.expect(TokenType.DEDENT)

            # sync sync_name:
            elif self.match(TokenType.SYNC):
                self.advance()
                sync_name = self.expect(TokenType.IDENTIFIER).value

                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                sync = self._parse_sync_body(sync_name)
                syncs.append(sync)

                self.expect(TokenType.DEDENT)

            # mapping name on Entity: (v0.30.0)
            elif self.match(TokenType.MAPPING):
                mapping = self._parse_mapping_block()
                mappings.append(mapping)

            # base_url: "https://..." (v0.30.0)
            elif tok.type == TokenType.IDENTIFIER and tok.value == "base_url":
                self.advance()
                self.expect(TokenType.COLON)
                base_url = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # auth: api_key from env("KEY") (v0.30.0)
            elif tok.type == TokenType.IDENTIFIER and tok.value == "auth":
                self.advance()
                self.expect(TokenType.COLON)
                auth = self._parse_auth_spec()
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.IntegrationSpec(
            name=name,
            title=title,
            base_url=base_url,
            auth=auth,
            api_refs=api_refs,
            foreign_model_refs=foreign_model_refs,
            actions=actions,
            syncs=syncs,
            mappings=mappings,
            source=loc,
        )

    # --- v0.30.0: Declarative mapping blocks ---

    def _parse_auth_spec(self) -> ir.AuthSpec:
        """Parse auth specification.

        Syntax:
            auth: api_key from env("KEY")
            auth: oauth2 from env("CLIENT_ID"), env("CLIENT_SECRET")
            auth: bearer from env("TOKEN")
        """
        tok = self.current_token()
        if tok.type != TokenType.IDENTIFIER or tok.value not in _AUTH_TYPES:
            raise make_parse_error(
                f"Expected auth type (api_key, oauth2, bearer, basic), got '{tok.value}'",
                self.file,
                tok.line,
                tok.column,
            )
        auth_type = _AUTH_TYPES[self.advance().value]

        self.expect(TokenType.FROM)

        credentials: list[str] = []
        credentials.append(self._parse_env_ref())

        while self.match(TokenType.COMMA):
            self.advance()
            credentials.append(self._parse_env_ref())

        return ir.AuthSpec(auth_type=auth_type, credentials=credentials)

    def _parse_env_ref(self) -> str:
        """Parse env("KEY_NAME") and return the key name."""
        tok = self.current_token()
        if tok.type != TokenType.IDENTIFIER or tok.value != "env":
            raise make_parse_error(
                f"Expected env(\"KEY_NAME\"), got '{tok.value}'",
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()
        self.expect(TokenType.LPAREN)
        key: str = self.expect(TokenType.STRING).value
        self.expect(TokenType.RPAREN)
        return key

    def _parse_mapping_block(self) -> ir.IntegrationMapping:
        """Parse a ``mapping <name> [on Entity]:`` block.

        Refactored to dispatch-table style (follow-on to #1098). 3
        token-keyed (trigger/source/target) + 7 IDENT-text-matched
        (request/cache/map_request/map_response/transform/on_conflict/
        on_error) + a `_build_mapping` builder.

        Syntax (original — with ``on Entity``)::

            mapping fetch_company on Company:
              trigger: on_create when company_number != null
              request: GET "/company/{self.company_number}"
              map_response:
                field <- source
              on_error: ignore

        Syntax (v0.33.1 — with source/target/transform)::

            mapping financial_snapshot:
              source: Reports.ProfitAndLoss
              target: XeroIntegration
              transform:
                last_revenue: money(source.base_currency, source.Revenue)
              on_conflict: xero_invoice_id
        """
        self.expect(TokenType.MAPPING)
        mapping_name = self.expect_identifier_or_keyword().value

        # Optional ``on Entity`` — if absent, entity_ref set via ``target:``.
        entity_ref = ""
        if self.match(TokenType.ON):
            self.advance()
            entity_ref = self.expect_identifier_or_keyword().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _MappingState(entity_ref=entity_ref)
        parse_block_with_dispatch(
            self,
            first_class_keywords=_MAPPING_KEYWORDS,
            ident_keywords=_MAPPING_IDENT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_mapping(mapping_name, state)

    def _parse_mapping_trigger(self) -> ir.MappingTriggerSpec:
        """Parse a mapping trigger.

        Syntax:
            on_create [when <expr>]
            on_update [when <expr>]
            on_delete [when <expr>]
            on_transition <from_state> -> <to_state>
            manual "Label"
        """
        tok = self.current_token()

        # "manual" is a keyword token (TokenType.MANUAL), not IDENTIFIER
        if self.match(TokenType.MANUAL):
            self.advance()
            label = None
            if self.match(TokenType.STRING):
                label = self.advance().value
            return ir.MappingTriggerSpec(
                trigger_type=ir.MappingTriggerType.MANUAL,
                label=label,
            )

        # on_transition is a keyword token since v0.39.0
        if self.match(TokenType.ON_TRANSITION):
            self.advance()
            trigger_type = ir.MappingTriggerType.ON_TRANSITION
        elif tok.type == TokenType.IDENTIFIER and tok.value in _TRIGGER_TYPES:
            trigger_type = _TRIGGER_TYPES[self.advance().value]
        else:
            raise make_parse_error(
                f"Expected trigger type (on_create, on_update, on_delete, "
                f"on_transition, manual), got '{tok.value}'",
                self.file,
                tok.line,
                tok.column,
            )

        condition_expr = None
        from_state = None
        to_state = None

        if trigger_type == ir.MappingTriggerType.ON_TRANSITION:
            # on_transition from_state -> to_state
            from_state = self.expect_identifier_or_keyword().value
            self.expect(TokenType.ARROW)
            to_state = self.expect_identifier_or_keyword().value
        else:
            # on_create/on_update/on_delete [when <expr>]
            if self.match(TokenType.WHEN):
                self.advance()
                condition_expr = self.collect_line_as_expr()

        return ir.MappingTriggerSpec(
            trigger_type=trigger_type,
            condition_expr=condition_expr,
            from_state=from_state,
            to_state=to_state,
        )

    def _parse_http_request(self) -> ir.HttpRequestSpec:
        """Parse HTTP request specification.

        Syntax:
            GET "/path/{self.field}"
            POST "/path/to/resource"
        """
        tok = self.current_token()
        method_str = tok.value.upper() if tok.type == TokenType.IDENTIFIER else tok.value
        if method_str not in _HTTP_METHODS:
            raise make_parse_error(
                f"Expected HTTP method (GET, POST, PUT, DELETE, PATCH), got '{tok.value}'",
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()
        method = ir.HttpMethod(method_str)

        # URL template: either a string or collected tokens until newline
        if self.match(TokenType.STRING):
            url_template = self.advance().value
        else:
            url_template = self._collect_url_template()

        return ir.HttpRequestSpec(method=method, url_template=url_template)

    def _collect_url_template(self) -> str:
        """Collect tokens as a URL path until newline.

        Handles simple paths like /company/search. For templates with
        interpolation (e.g. /company/{self.number}), use a quoted string.
        """
        parts: list[str] = []
        while True:
            tok = self.current_token()
            if tok.type == TokenType.NEWLINE or tok.type == TokenType.DEDENT:
                break
            if tok.type == TokenType.SLASH:
                parts.append("/")
            elif tok.type == TokenType.DOT:
                parts.append(".")
            elif tok.type == TokenType.MINUS:
                parts.append("-")
            elif tok.type in (TokenType.IDENTIFIER, TokenType.NUMBER):
                parts.append(tok.value)
            else:
                # Include keyword token values (e.g. "search", "get")
                parts.append(tok.value)
            self.advance()
        return "".join(parts)

    def _parse_larrow_mapping_rules(self) -> list[ir.MappingRule]:
        """Parse mapping rules with <- (left arrow) syntax.

        Syntax:
            target_field <- source.path
            target_field <- "literal"
            target_field <- true
        """
        rules: list[ir.MappingRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            target = self.expect_identifier_or_keyword().value
            self.expect(TokenType.LARROW)
            source = self._parse_expression()

            rules.append(ir.MappingRule(target_field=target, source=source))
            self.skip_newlines()

        return rules

    def _parse_colon_mapping_rules(self) -> list[ir.MappingRule]:
        """Parse mapping rules with colon syntax (v0.33.1 transform blocks).

        Syntax:
            target_field: source.path
            target_field: money(source.currency, source.amount)
            target_field: "literal"
        """
        rules: list[ir.MappingRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            target = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            source = self._parse_expression()

            rules.append(ir.MappingRule(target_field=target, source=source))
            self.skip_newlines()

        return rules

    def _parse_dotted_name(self) -> str:
        """Parse a dotted identifier path (e.g., Reports.ProfitAndLoss)."""
        parts = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)
        return ".".join(parts)

    def _parse_error_strategy(self) -> ir.ErrorStrategy:
        """Parse error strategy.

        Syntax:
            on_error: ignore
            on_error: set integration_status = "failed", log_warning
            on_error: revert_transition
        """
        actions: list[ir.ErrorAction] = []
        set_fields: dict[str, str] = {}

        while True:
            tok = self.current_token()
            if tok.type == TokenType.NEWLINE or tok.type == TokenType.DEDENT:
                break

            if tok.type == TokenType.IDENTIFIER and tok.value == "set":
                # set field = "value"
                self.advance()
                field_name = self.expect_identifier_or_keyword().value
                self.expect(TokenType.EQUALS)
                value = self.expect(TokenType.STRING).value
                set_fields[field_name] = value
            elif tok.type == TokenType.IDENTIFIER and tok.value in _ERROR_ACTIONS:
                actions.append(_ERROR_ACTIONS[self.advance().value])
            else:
                break

            # Optional comma separator
            if self.match(TokenType.COMMA):
                self.advance()

        return ir.ErrorStrategy(actions=actions, set_fields=set_fields)

    # --- Legacy action/sync parsing ---

    def _parse_action_body(self, action_name: str) -> ir.IntegrationAction:
        """Parse the body of an action block."""
        when_surface = None
        call_service = None
        call_operation = None
        call_mapping: list[ir.MappingRule] = []
        response_foreign_model = None
        response_entity = None
        response_mapping: list[ir.MappingRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # when surface <name>
            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.SURFACE)
                when_surface = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # call service <name>
            elif self.match(TokenType.CALL):
                self.advance()
                if self.match(TokenType.SERVICE):
                    self.advance()
                    call_service = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # call operation <path>
                elif self.match(TokenType.OPERATION):
                    self.advance()
                    call_operation = self._parse_operation_path()
                    self.skip_newlines()

                # call mapping:
                elif self.match(TokenType.MAPPING):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    call_mapping = self._parse_mapping_rules()
                    self.expect(TokenType.DEDENT)

            # response foreign <name>
            elif self.match(TokenType.RESPONSE):
                self.advance()
                if self.match(TokenType.FOREIGN):
                    self.advance()
                    response_foreign_model = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # response entity <name>
                elif self.match(TokenType.ENTITY):
                    self.advance()
                    response_entity = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # response mapping:
                elif self.match(TokenType.MAPPING):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    response_mapping = self._parse_mapping_rules()
                    self.expect(TokenType.DEDENT)

            else:
                # Skip unknown tokens
                self.advance()

        return ir.IntegrationAction(
            name=action_name,
            when_surface=when_surface or "unknown",
            call_service=call_service or "unknown",
            call_operation=call_operation or "unknown",
            call_mapping=call_mapping,
            response_foreign_model=response_foreign_model,
            response_entity=response_entity,
            response_mapping=response_mapping,
        )

    def _parse_sync_body(self, sync_name: str) -> ir.IntegrationSync:
        """Parse the body of a sync block."""
        mode = ir.SyncMode.SCHEDULED
        schedule = None
        from_service = None
        from_operation = None
        from_foreign_model = None
        into_entity = None
        match_rules: list[ir.MatchRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # mode: scheduled "<cron>"
            if self.match(TokenType.MODE):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.SCHEDULED):
                    self.advance()
                    mode = ir.SyncMode.SCHEDULED
                    if self.match(TokenType.STRING):
                        schedule = self.advance().value
                elif self.match(TokenType.EVENT_DRIVEN):
                    self.advance()
                    mode = ir.SyncMode.EVENT_DRIVEN
                self.skip_newlines()

            # from service <name>
            elif self.match(TokenType.FROM):
                self.advance()
                if self.match(TokenType.SERVICE):
                    self.advance()
                    from_service = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # from operation <path>
                elif self.match(TokenType.OPERATION):
                    self.advance()
                    from_operation = self._parse_operation_path()
                    self.skip_newlines()

                # from foreign <name>
                elif self.match(TokenType.FOREIGN):
                    self.advance()
                    from_foreign_model = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

            # into entity <name>
            elif self.match(TokenType.INTO):
                self.advance()
                self.expect(TokenType.ENTITY)
                into_entity = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # match rules:
            elif self.match(TokenType.MATCH):
                self.advance()
                self.expect(TokenType.RULES)
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                match_rules = self._parse_match_rules()
                self.expect(TokenType.DEDENT)

            else:
                # Skip unknown tokens
                self.advance()

        return ir.IntegrationSync(
            name=sync_name,
            mode=mode,
            schedule=schedule,
            from_service=from_service or "unknown",
            from_operation=from_operation or "unknown",
            from_foreign_model=from_foreign_model or "unknown",
            into_entity=into_entity or "unknown",
            match_rules=match_rules,
        )

    def _parse_operation_path(self) -> str:
        """Parse an operation path like /agents/search."""
        path_parts: list[str] = []

        if self.match(TokenType.SLASH):
            self.advance()
            path_parts.append("/")

        while True:
            token = self.current_token()
            if token.type == TokenType.IDENTIFIER or token.type.value in [
                "search",
                "filter",
                "create",
                "update",
                "delete",
                "get",
            ]:
                path_parts.append(self.advance().value)
                if self.match(TokenType.SLASH):
                    path_parts.append(self.advance().value)
                else:
                    break
            else:
                break

        return "".join(path_parts) if path_parts else "unknown"

    def _parse_mapping_rules(self) -> list[ir.MappingRule]:
        """Parse mapping rules (target -> source)."""
        rules: list[ir.MappingRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            target = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ARROW)
            source = self._parse_expression()

            rules.append(ir.MappingRule(target_field=target, source=source))
            self.skip_newlines()

        return rules

    def _parse_match_rules(self) -> list[ir.MatchRule]:
        """Parse match rules (foreign_field <-> entity_field)."""
        rules: list[ir.MatchRule] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            foreign_field = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.BIARROW)
            entity_field = self.expect(TokenType.IDENTIFIER).value

            rules.append(ir.MatchRule(foreign_field=foreign_field, entity_field=entity_field))
            self.skip_newlines()

        return rules

    def _parse_expression(self) -> ir.Expression:
        """Parse an expression (path, literal, or function call).

        Function call syntax (v0.33.1):
            money(source.CurrencyCode, source.Amount)
            concat(source.first_name, " ", source.last_name)
        """
        token = self.current_token()

        # Literals first — check before identifiers since true/false are
        # in KEYWORD_AS_IDENTIFIER_TYPES but should be parsed as literals here
        if self.match(TokenType.STRING):
            return ir.Expression(literal=self.advance().value)

        if self.match(TokenType.NUMBER):
            value = self.advance().value
            try:
                return ir.Expression(literal=int(value))
            except ValueError:
                return ir.Expression(literal=float(value))

        if self.match(TokenType.TRUE) or self.match(TokenType.FALSE):
            return ir.Expression(literal=self.advance().value == "true")

        # Identifiers and keyword tokens that serve as path roots or function
        # names in mapping expressions.  Rather than maintaining an exhaustive
        # allow-list, we accept any token that is NOT a structural delimiter.
        _structural = {
            TokenType.COLON,
            TokenType.COMMA,
            TokenType.LPAREN,
            TokenType.RPAREN,
            TokenType.LARROW,
            TokenType.ARROW,
            TokenType.NEWLINE,
            TokenType.INDENT,
            TokenType.DEDENT,
            TokenType.EOF,
            TokenType.EQUALS,
        }
        if token.type not in _structural:
            first = self.advance().value

            # Function call: identifier followed by (
            if self.match(TokenType.LPAREN):
                self.advance()  # consume (
                args: list[ir.Expression] = []
                while not self.match(TokenType.RPAREN):
                    if args:
                        self.expect(TokenType.COMMA)
                    args.append(self._parse_expression())
                self.advance()  # consume )
                return ir.Expression(func_name=first, func_args=args)

            # Dotted path
            parts = [first]
            while self.match(TokenType.DOT):
                self.advance()
                parts.append(self.expect_identifier_or_keyword().value)

            return ir.Expression(path=".".join(parts))

        token = self.current_token()
        raise make_parse_error(
            f"Expected expression, got {token.type.value}",
            self.file,
            token.line,
            token.column,
        )


# ================================================================ #
# _parse_mapping_block — keyword-dispatch decomposition (#1098 template) #
# ================================================================ #
#
# The 146-line monolith was replaced (v0.70.31) with the dispatch
# pattern shipped in #1097. 3 token-keyed (trigger/source/target)
# + 7 IDENT-text-matched (request/cache/map_request/map_response/
# transform/on_conflict/on_error) + a `_build_mapping` builder.


@dataclass
class _MappingState:
    """Accumulator for :meth:`IntegrationParserMixin._parse_mapping_block`.

    ``entity_ref`` is pre-populated from the optional ``on Entity``
    header clause and may be overwritten by a later ``target:`` keyword.
    """

    entity_ref: str = ""
    source_ref: str = ""
    triggers: list[ir.MappingTriggerSpec] = field(default_factory=list)
    request: ir.HttpRequestSpec | None = None
    request_mapping: list[ir.MappingRule] = field(default_factory=list)
    response_mapping: list[ir.MappingRule] = field(default_factory=list)
    transform: list[ir.MappingRule] = field(default_factory=list)
    on_error: ir.ErrorStrategy | None = None
    on_conflict: str = ""
    cache_ttl: int | None = None


# ---------- Token-keyed keyword parsers ---------- #


def _m_kw_trigger(parser: Any, state: _MappingState) -> None:
    """``trigger: on_<event> [when <expr>]`` — appended to ``triggers``."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.triggers.append(parser._parse_mapping_trigger())
    parser.skip_newlines()


def _m_kw_source(parser: Any, state: _MappingState) -> None:
    """``source: DottedName`` (v0.33.1)"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.source_ref = parser._parse_dotted_name()
    parser.skip_newlines()


def _m_kw_target(parser: Any, state: _MappingState) -> None:
    """``target: EntityName`` (v0.33.1) — overrides any ``on Entity`` header."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.entity_ref = parser.expect(TokenType.IDENTIFIER).value
    parser.skip_newlines()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _m_kw_request(parser: Any, state: _MappingState) -> None:
    """``request: <METHOD> "/path"`` — HTTP request specification."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.request = parser._parse_http_request()
    parser.skip_newlines()


def _m_kw_cache(parser: Any, state: _MappingState) -> None:
    """``cache: "<duration>"`` — TTL string parsed via process.parse_duration."""
    from .process import parse_duration

    parser.advance()
    parser.expect(TokenType.COLON)
    duration_tok = parser.expect(TokenType.STRING)
    state.cache_ttl = parse_duration(duration_tok.value, parser=parser)
    parser.skip_newlines()


def _m_kw_map_request(parser: Any, state: _MappingState) -> None:
    """``map_request:`` — indented block of ``target <- source`` rules."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.request_mapping = parser._parse_larrow_mapping_rules()
    parser.expect(TokenType.DEDENT)


def _m_kw_map_response(parser: Any, state: _MappingState) -> None:
    """``map_response:`` — indented block of ``target <- source`` rules."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.response_mapping = parser._parse_larrow_mapping_rules()
    parser.expect(TokenType.DEDENT)


def _m_kw_transform(parser: Any, state: _MappingState) -> None:
    """``transform:`` — indented block of ``target: expr`` rules (v0.33.1)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.transform = parser._parse_colon_mapping_rules()
    parser.expect(TokenType.DEDENT)


def _m_kw_on_conflict(parser: Any, state: _MappingState) -> None:
    """``on_conflict: field_name`` (v0.33.1)"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.on_conflict = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _m_kw_on_error(parser: Any, state: _MappingState) -> None:
    """``on_error: ignore | set f = "v", log_warning | ...``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.on_error = parser._parse_error_strategy()
    parser.skip_newlines()


# ---------- Dispatch tables + builder ---------- #


_MAPPING_KEYWORDS: dict[TokenType, KeywordParser[_MappingState]] = {
    TokenType.TRIGGER: _m_kw_trigger,
    TokenType.SOURCE: _m_kw_source,
    TokenType.TARGET: _m_kw_target,
}


_MAPPING_IDENT_KEYWORDS: dict[str, KeywordParser[_MappingState]] = {
    "request": _m_kw_request,
    "cache": _m_kw_cache,
    "map_request": _m_kw_map_request,
    "map_response": _m_kw_map_response,
    "transform": _m_kw_transform,
    "on_conflict": _m_kw_on_conflict,
    "on_error": _m_kw_on_error,
}


def _build_mapping(mapping_name: str, state: _MappingState) -> ir.IntegrationMapping:
    return ir.IntegrationMapping(
        name=mapping_name,
        entity_ref=state.entity_ref,
        source_ref=state.source_ref,
        triggers=state.triggers,
        request=state.request,
        request_mapping=state.request_mapping,
        response_mapping=state.response_mapping,
        transform=state.transform,
        on_error=state.on_error,
        on_conflict=state.on_conflict,
        cache_ttl=state.cache_ttl,
    )
