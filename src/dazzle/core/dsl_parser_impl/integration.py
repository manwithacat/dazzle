"""
Integration parsing for DAZZLE DSL.

Handles integration declarations including actions, syncs, and mappings.
v0.30.0: Added declarative mapping blocks with triggers, HTTP requests, and error strategies.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType

# HTTP method identifiers mapped to enum
_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}

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

    def parse_integration(self) -> ir.IntegrationSpec:
        """Parse integration declaration."""
        self.expect(TokenType.INTEGRATION)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

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
        """Parse a mapping block.

        Syntax:
            mapping fetch_company on Company:
              trigger: on_create when company_number != null
              trigger: manual "Look up company"
              request: GET "/company/{self.company_number}"
              map_request:
                field <- source
              map_response:
                field <- source
              on_error: ignore
        """
        self.expect(TokenType.MAPPING)
        mapping_name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.ON)
        entity_ref = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        triggers: list[ir.MappingTriggerSpec] = []
        request: ir.HttpRequestSpec | None = None
        request_mapping: list[ir.MappingRule] = []
        response_mapping: list[ir.MappingRule] = []
        on_error: ir.ErrorStrategy | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            tok = self.current_token()

            # trigger: on_create when condition
            if self.match(TokenType.TRIGGER):
                self.advance()
                self.expect(TokenType.COLON)
                trigger = self._parse_mapping_trigger()
                triggers.append(trigger)
                self.skip_newlines()

            # request: GET "/path/{self.field}"
            elif tok.type == TokenType.IDENTIFIER and tok.value == "request":
                self.advance()
                self.expect(TokenType.COLON)
                request = self._parse_http_request()
                self.skip_newlines()

            # map_request: (indented block of field <- source)
            elif tok.type == TokenType.IDENTIFIER and tok.value == "map_request":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                request_mapping = self._parse_larrow_mapping_rules()
                self.expect(TokenType.DEDENT)

            # map_response: (indented block of field <- source)
            elif tok.type == TokenType.IDENTIFIER and tok.value == "map_response":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                response_mapping = self._parse_larrow_mapping_rules()
                self.expect(TokenType.DEDENT)

            # on_error: ignore | set field = "value", log_warning
            elif tok.type == TokenType.IDENTIFIER and tok.value == "on_error":
                self.advance()
                self.expect(TokenType.COLON)
                on_error = self._parse_error_strategy()
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.IntegrationMapping(
            name=mapping_name,
            entity_ref=entity_ref,
            triggers=triggers,
            request=request,
            request_mapping=request_mapping,
            response_mapping=response_mapping,
            on_error=on_error,
        )

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

        if tok.type != TokenType.IDENTIFIER or tok.value not in _TRIGGER_TYPES:
            raise make_parse_error(
                f"Expected trigger type (on_create, on_update, on_delete, "
                f"on_transition, manual), got '{tok.value}'",
                self.file,
                tok.line,
                tok.column,
            )
        trigger_type = _TRIGGER_TYPES[self.advance().value]

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
        """Parse an expression (path or literal)."""
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER or token.value in [
            "entity",
            "form",
            "foreign",
            "service",
            "response",
            "self",
        ]:
            parts = [self.advance().value]

            while self.match(TokenType.DOT):
                self.advance()
                parts.append(self.expect_identifier_or_keyword().value)

            return ir.Expression(path=".".join(parts))

        elif self.match(TokenType.STRING):
            return ir.Expression(literal=self.advance().value)

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            try:
                return ir.Expression(literal=int(value))
            except ValueError:
                return ir.Expression(literal=float(value))

        elif self.match(TokenType.TRUE) or self.match(TokenType.FALSE):
            return ir.Expression(literal=self.advance().value == "true")

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected expression, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
