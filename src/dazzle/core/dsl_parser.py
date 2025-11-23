"""
DSL Parser for DAZZLE.

Converts token stream from lexer into IR (Internal Representation).
Implements recursive descent parsing for all DSL constructs.
"""

from pathlib import Path
from typing import Any

from . import ir
from .errors import make_parse_error
from .lexer import Token, TokenType, tokenize


class Parser:
    """
    Recursive descent parser for DAZZLE DSL.

    Consumes tokens from lexer and builds IR structures.
    """

    def __init__(self, tokens: list[Token], file: Path):
        """
        Initialize parser.

        Args:
            tokens: List of tokens from lexer
            file: Source file path (for error reporting)
        """
        self.tokens = tokens
        self.file = file
        self.pos = 0

    def current_token(self) -> Token:
        """Get current token."""
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[self.pos]

    def peek_token(self, offset: int = 1) -> Token:
        """Peek ahead at token."""
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[pos]

    def advance(self) -> Token:
        """Consume and return current token."""
        token = self.current_token()
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def expect(self, token_type: TokenType) -> Token:
        """
        Expect a specific token type and consume it.

        Raises:
            ParseError: If token doesn't match
        """
        token = self.current_token()
        if token.type != token_type:
            raise make_parse_error(
                f"Expected {token_type.value}, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
        return self.advance()

    def expect_identifier_or_keyword(self) -> Token:
        """
        Expect an identifier or accept a keyword as an identifier.

        This is useful for contexts where keywords can be used as values.
        """
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER:
            return self.advance()

        # Allow keywords to be used as identifiers in certain contexts
        if token.type in (
            TokenType.APP,
            TokenType.MODULE,
            TokenType.USE,
            TokenType.SURFACE,
            TokenType.ENTITY,
            TokenType.INTEGRATION,
            TokenType.EXPERIENCE,
            TokenType.SERVICE,
            TokenType.FOREIGN_MODEL,
            # Boolean literals (for default values)
            TokenType.TRUE,
            TokenType.FALSE,
            # Test DSL keywords (can be used as field names)
            TokenType.TEST,
            TokenType.SETUP,
            TokenType.DATA,
            TokenType.EXPECT,
            TokenType.STATUS,
            TokenType.CREATED,
            TokenType.FILTER,
            TokenType.SEARCH,
            TokenType.ORDER_BY,
            TokenType.COUNT,
            TokenType.ERROR_MESSAGE,
            TokenType.FIRST,
            TokenType.LAST,
            TokenType.QUERY,
            TokenType.CREATE,
            TokenType.UPDATE,
            TokenType.DELETE,
            TokenType.GET,
        ):
            return self.advance()

        raise make_parse_error(
            f"Expected identifier or keyword, got {token.type.value}",
            self.file,
            token.line,
            token.column,
        )

    def match(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.current_token().type in token_types

    def skip_newlines(self) -> None:
        """Skip any NEWLINE tokens."""
        while self.match(TokenType.NEWLINE):
            self.advance()

    def parse_module_header(self) -> tuple[str | None, str | None, str | None, list[str]]:
        """
        Parse module header (module, app, use declarations).

        Returns:
            Tuple of (module_name, app_name, app_title, uses)
        """
        module_name = None
        app_name = None
        app_title = None
        uses = []

        self.skip_newlines()

        # Parse module declaration
        if self.match(TokenType.MODULE):
            self.advance()
            module_name = self.parse_module_name()
            self.skip_newlines()

        # Parse use declarations
        while self.match(TokenType.USE):
            self.advance()
            use_name = self.parse_module_name()
            uses.append(use_name)

            # Optional "as alias" - ignore for now
            if self.match(TokenType.AS):
                self.advance()
                self.expect(TokenType.IDENTIFIER)

            self.skip_newlines()

        # Parse app declaration
        if self.match(TokenType.APP):
            self.advance()
            app_name = self.expect_identifier_or_keyword().value

            if self.match(TokenType.STRING):
                app_title = self.advance().value

            self.skip_newlines()

        return module_name, app_name, app_title, uses

    def parse_module_name(self) -> str:
        """Parse dotted module name (e.g., foo.bar.baz)."""
        parts = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)

        return ".".join(parts)

    def parse_type_spec(self) -> ir.FieldType:
        """
        Parse field type specification.

        Examples:
            str(200)
            decimal(10,2)
            enum[draft,issued,paid]
            ref Client
        """
        token = self.current_token()

        # str(N)
        if token.value == "str":
            self.advance()
            self.expect(TokenType.LPAREN)
            max_len = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=max_len)

        # text
        elif token.value == "text":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.TEXT)

        # int
        elif token.value == "int":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.INT)

        # decimal(P,S)
        elif token.value == "decimal":
            self.advance()
            self.expect(TokenType.LPAREN)
            precision = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.COMMA)
            scale = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=precision, scale=scale)

        # bool
        elif token.value == "bool":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.BOOL)

        # date
        elif token.value == "date":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATE)

        # datetime
        elif token.value == "datetime":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATETIME)

        # uuid
        elif token.value == "uuid":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.UUID)

        # email
        elif token.value == "email":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.EMAIL)

        # enum[val1,val2,...]
        elif token.value == "enum":
            self.advance()
            self.expect(TokenType.LBRACKET)

            values = []
            values.append(self.expect(TokenType.IDENTIFIER).value)

            while self.match(TokenType.COMMA):
                self.advance()
                values.append(self.expect(TokenType.IDENTIFIER).value)

            self.expect(TokenType.RBRACKET)
            return ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=values)

        # ref EntityName
        elif token.value == "ref":
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=entity_name)

        else:
            raise make_parse_error(
                f"Unknown type: {token.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse_field_modifiers(
        self,
    ) -> tuple[list[ir.FieldModifier], str | int | float | bool | None]:
        """
        Parse field modifiers and default value.

        Returns:
            Tuple of (modifiers, default_value)
        """
        modifiers = []
        default: str | int | float | bool | None = None

        while True:
            token = self.current_token()

            if token.value == "required":
                self.advance()
                modifiers.append(ir.FieldModifier.REQUIRED)
            elif token.value == "optional":
                self.advance()
                modifiers.append(ir.FieldModifier.OPTIONAL)
            elif token.value == "pk":
                self.advance()
                modifiers.append(ir.FieldModifier.PK)
            elif token.value == "unique":
                self.advance()
                if self.match(TokenType.QUESTION):
                    self.advance()
                    modifiers.append(ir.FieldModifier.UNIQUE_NULLABLE)
                else:
                    modifiers.append(ir.FieldModifier.UNIQUE)
            elif token.value == "auto_add":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_ADD)
            elif token.value == "auto_update":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_UPDATE)
            elif self.match(TokenType.EQUALS):
                # default=value
                self.advance()
                if self.match(TokenType.STRING):
                    default = self.advance().value
                elif self.match(TokenType.NUMBER):
                    num_str = self.advance().value
                    default = float(num_str) if "." in num_str else int(num_str)
                elif self.match(TokenType.TRUE):
                    self.advance()
                    default = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    default = False
                elif self.match(TokenType.IDENTIFIER):
                    # Could be enum value or boolean (for backwards compatibility)
                    val = self.advance().value
                    if val in ("true", "false"):
                        default = val == "true"
                    else:
                        default = val
            else:
                break

        return modifiers, default

    def parse_entity(self) -> ir.EntitySpec:
        """Parse entity declaration."""
        self.expect(TokenType.ENTITY)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        fields = []
        constraints = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Check for constraints
            if self.match(TokenType.UNIQUE, TokenType.INDEX):
                constraint_kind = self.advance().type
                kind = (
                    ir.ConstraintKind.UNIQUE
                    if constraint_kind == TokenType.UNIQUE
                    else ir.ConstraintKind.INDEX
                )

                # Parse field list
                field_names = [self.expect(TokenType.IDENTIFIER).value]
                while self.match(TokenType.COMMA):
                    self.advance()
                    field_names.append(self.expect(TokenType.IDENTIFIER).value)

                constraints.append(ir.Constraint(kind=kind, fields=field_names))
                self.skip_newlines()
                continue

            # Parse field
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            field_type = self.parse_type_spec()
            modifiers, default = self.parse_field_modifiers()

            fields.append(
                ir.FieldSpec(
                    name=field_name,
                    type=field_type,
                    modifiers=modifiers,
                    default=default,
                )
            )

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.EntitySpec(
            name=name,
            title=title,
            fields=fields,
            constraints=constraints,
        )

    def parse_surface(self) -> ir.SurfaceSpec:
        """Parse surface declaration."""
        self.expect(TokenType.SURFACE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        entity_ref = None
        mode = ir.SurfaceMode.CUSTOM
        sections = []
        actions = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # uses entity EntityName
            if self.match(TokenType.USES):
                self.advance()
                self.expect(TokenType.ENTITY)
                entity_ref = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # mode: view|create|edit|list|custom
            elif self.match(TokenType.MODE):
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                mode = ir.SurfaceMode(mode_token.value)
                self.skip_newlines()

            # section name ["title"]:
            elif self.match(TokenType.SECTION):
                section = self.parse_surface_section()
                sections.append(section)

            # action name ["label"]:
            elif self.match(TokenType.ACTION):
                action = self.parse_surface_action()
                actions.append(action)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.SurfaceSpec(
            name=name,
            title=title,
            entity_ref=entity_ref,
            mode=mode,
            sections=sections,
            actions=actions,
        )

    def parse_surface_section(self) -> ir.SurfaceSection:
        """Parse surface section."""
        self.expect(TokenType.SECTION)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        elements = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field field_name ["label"]
            if self.match(TokenType.FIELD):
                self.advance()
                field_name = self.expect_identifier_or_keyword().value
                label = None

                if self.match(TokenType.STRING):
                    label = self.advance().value

                elements.append(
                    ir.SurfaceElement(
                        field_name=field_name,
                        label=label,
                    )
                )

                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.SurfaceSection(
            name=name,
            title=title,
            elements=elements,
        )

    def parse_surface_action(self) -> ir.SurfaceAction:
        """Parse surface action."""
        self.expect(TokenType.ACTION)

        name = self.expect(TokenType.IDENTIFIER).value
        label = None

        if self.match(TokenType.STRING):
            label = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # on submit|click|auto -> outcome
        self.expect(TokenType.ON)
        trigger_token = self.expect(TokenType.IDENTIFIER)
        trigger = ir.SurfaceTrigger(trigger_token.value)

        self.expect(TokenType.ARROW)

        outcome = self.parse_outcome()

        self.skip_newlines()
        self.expect(TokenType.DEDENT)

        return ir.SurfaceAction(
            name=name,
            label=label,
            trigger=trigger,
            outcome=outcome,
        )

    def parse_outcome(self) -> ir.Outcome:
        """Parse action outcome."""
        # surface SurfaceName
        if self.match(TokenType.SURFACE):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            return ir.Outcome(kind=ir.OutcomeKind.SURFACE, target=target)

        # experience ExperienceName [step StepName]
        elif self.match(TokenType.EXPERIENCE):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            step = None

            if self.match(TokenType.STEP):
                self.advance()
                step = self.expect(TokenType.IDENTIFIER).value

            return ir.Outcome(kind=ir.OutcomeKind.EXPERIENCE, target=target, step=step)

        # integration IntegrationName action ActionName
        elif self.match(TokenType.INTEGRATION):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ACTION)
            action = self.expect(TokenType.IDENTIFIER).value

            return ir.Outcome(kind=ir.OutcomeKind.INTEGRATION, target=target, action=action)

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected outcome (surface/experience/integration), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse_service(self) -> ir.ServiceSpec:
        """Parse service declaration."""
        self.expect(TokenType.SERVICE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        spec_url = None
        spec_inline = None
        auth_profile = None
        owner = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # spec: url "..."
            if self.match(TokenType.SPEC):
                self.advance()
                self.expect(TokenType.COLON)

                if self.match(TokenType.URL):
                    self.advance()
                    spec_url = self.expect(TokenType.STRING).value
                elif self.match(TokenType.INLINE):
                    self.advance()
                    spec_inline = self.expect(TokenType.STRING).value

                self.skip_newlines()

            # auth_profile: kind [options...]
            elif self.match(TokenType.AUTH_PROFILE):
                self.advance()
                self.expect(TokenType.COLON)

                auth_kind_token = self.expect(TokenType.IDENTIFIER)
                auth_kind = ir.AuthKind(auth_kind_token.value)

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)
                    value = self.expect(TokenType.STRING).value
                    options[key] = value

                auth_profile = ir.AuthProfile(kind=auth_kind, options=options)
                self.skip_newlines()

            # owner: "..."
            elif self.match(TokenType.OWNER):
                self.advance()
                self.expect(TokenType.COLON)
                owner = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if auth_profile is None:
            token = self.current_token()
            raise make_parse_error(
                "Service must have auth_profile",
                self.file,
                token.line,
                token.column,
            )

        return ir.ServiceSpec(
            name=name,
            title=title,
            spec_url=spec_url,
            spec_inline=spec_inline,
            auth_profile=auth_profile,
            owner=owner,
        )

    def parse_experience(self) -> ir.ExperienceSpec:
        """Parse experience declaration."""
        self.expect(TokenType.EXPERIENCE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # start at step StepName
        self.expect(TokenType.START)
        self.expect(TokenType.AT)
        self.expect(TokenType.STEP)
        start_step = self.expect(TokenType.IDENTIFIER).value
        self.skip_newlines()

        steps = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.STEP):
                step = self.parse_experience_step()
                steps.append(step)

        self.expect(TokenType.DEDENT)

        return ir.ExperienceSpec(
            name=name,
            title=title,
            start_step=start_step,
            steps=steps,
        )

    def parse_experience_step(self) -> ir.ExperienceStep:
        """Parse experience step."""
        self.expect(TokenType.STEP)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # kind: surface|process|integration
        self.expect(TokenType.KIND)
        self.expect(TokenType.COLON)
        kind_token = self.expect_identifier_or_keyword()
        kind = ir.StepKind(kind_token.value)
        self.skip_newlines()

        surface = None
        integration = None
        action = None

        # Parse step target based on kind
        if kind == ir.StepKind.SURFACE:
            self.expect(TokenType.SURFACE)
            surface = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()

        elif kind == ir.StepKind.INTEGRATION:
            self.expect(TokenType.INTEGRATION)
            integration = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ACTION)
            action = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()

        # Parse transitions
        transitions = []
        while self.match(TokenType.ON):
            self.advance()

            event_token = self.expect(TokenType.IDENTIFIER)
            event = ir.TransitionEvent(event_token.value)

            self.expect(TokenType.ARROW)
            self.expect(TokenType.STEP)
            next_step = self.expect(TokenType.IDENTIFIER).value

            transitions.append(
                ir.StepTransition(
                    event=event,
                    next_step=next_step,
                )
            )

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ExperienceStep(
            name=name,
            kind=kind,
            surface=surface,
            integration=integration,
            action=action,
            transitions=transitions,
        )

    def parse_foreign_model(self) -> ir.ForeignModelSpec:
        """Parse foreign_model declaration."""
        self.expect(TokenType.FOREIGN_MODEL)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.FROM)
        service_ref = self.expect(TokenType.IDENTIFIER).value

        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        key_fields = []
        constraints = []
        fields = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # key: field1[,field2,...]
            if self.match(TokenType.KEY):
                self.advance()
                self.expect(TokenType.COLON)

                key_fields.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    key_fields.append(self.expect(TokenType.IDENTIFIER).value)

                self.skip_newlines()

            # constraint kind [options...]
            elif self.match(TokenType.CONSTRAINT):
                self.advance()

                constraint_kind_token = self.expect(TokenType.IDENTIFIER)
                constraint_kind = ir.ForeignConstraintKind(constraint_kind_token.value)

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)

                    if self.match(TokenType.STRING):
                        options[key] = self.advance().value
                    elif self.match(TokenType.NUMBER):
                        options[key] = self.advance().value
                    elif self.match(TokenType.IDENTIFIER):
                        options[key] = self.advance().value

                constraints.append(
                    ir.ForeignConstraint(
                        kind=constraint_kind,
                        options=options,
                    )
                )

                self.skip_newlines()

            # field_name: type [modifiers...]
            else:
                field_name = self.expect_identifier_or_keyword().value
                self.expect(TokenType.COLON)

                field_type = self.parse_type_spec()
                modifiers, default = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                    )
                )

                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ForeignModelSpec(
            name=name,
            title=title,
            service_ref=service_ref,
            key_fields=key_fields,
            constraints=constraints,
            fields=fields,
        )

    def parse_integration(self) -> ir.IntegrationSpec:
        """Parse integration declaration - simplified version for Stage 2."""
        self.expect(TokenType.INTEGRATION)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        service_refs = []
        foreign_model_refs = []
        actions = []
        syncs = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # uses service ServiceName[,ServiceName]
            if self.match(TokenType.USES):
                self.advance()

                if self.match(TokenType.SERVICE):
                    self.advance()
                    service_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    while self.match(TokenType.COMMA):
                        self.advance()
                        service_refs.append(self.expect(TokenType.IDENTIFIER).value)

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

                # Parse action body
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

                # Parse sync body
                sync = self._parse_sync_body(sync_name)
                syncs.append(sync)

                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.IntegrationSpec(
            name=name,
            title=title,
            service_refs=service_refs,
            foreign_model_refs=foreign_model_refs,
            actions=actions,
            syncs=syncs,
        )

    def _parse_action_body(self, action_name: str) -> ir.IntegrationAction:
        """Parse the body of an action block."""
        when_surface = None
        call_service = None
        call_operation = None
        call_mapping = []
        response_foreign_model = None
        response_entity = None
        response_mapping = []

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
        match_rules = []

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
        # Operation paths can be simple identifiers or slash-separated paths
        path_parts = []

        # Handle leading slash
        if self.match(TokenType.SLASH):
            self.advance()
            path_parts.append("/")

        # Parse path components (can be identifiers or keywords)
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
        """Parse mapping rules (target → source)."""
        rules = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse target field
            target = self.expect(TokenType.IDENTIFIER).value

            # Expect arrow (→)
            self.expect(TokenType.ARROW)

            # Parse source expression (path or literal)
            source = self._parse_expression()

            rules.append(
                ir.MappingRule(
                    target_field=target,
                    source=source,
                )
            )

            self.skip_newlines()

        return rules

    def _parse_match_rules(self) -> list[ir.MatchRule]:
        """Parse match rules (foreign_field ↔ entity_field)."""
        rules = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse foreign field
            foreign_field = self.expect(TokenType.IDENTIFIER).value

            # Expect bidirectional arrow (↔)
            self.expect(TokenType.BIARROW)

            # Parse entity field
            entity_field = self.expect(TokenType.IDENTIFIER).value

            rules.append(
                ir.MatchRule(
                    foreign_field=foreign_field,
                    entity_field=entity_field,
                )
            )

            self.skip_newlines()

        return rules

    def _parse_expression(self) -> ir.Expression:
        """Parse an expression (path or literal)."""
        # Try to parse as a path first (e.g., form.vrn, entity.id)
        # Need to check for keywords that can be used as path components
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER or token.value in [
            "entity",
            "form",
            "foreign",
            "service",
        ]:
            parts = [self.advance().value]

            while self.match(TokenType.DOT):
                self.advance()
                parts.append(self.expect_identifier_or_keyword().value)

            return ir.Expression(path=".".join(parts))

        # Try to parse as a literal
        elif self.match(TokenType.STRING):
            return ir.Expression(literal=self.advance().value)

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            # Try to convert to int or float
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

    def parse_test(self) -> ir.TestSpec:
        """Parse test declaration."""
        self.expect(TokenType.TEST)

        name = self.expect(TokenType.IDENTIFIER).value
        description = None

        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        setup_steps = []
        action = None
        data = {}
        filter_data = {}
        assertions = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse setup block
            if self.match(TokenType.SETUP):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # Parse: var: create Entity with field=value, field=value
                    var_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    self.expect(TokenType.CREATE)
                    entity_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.WITH)

                    # Parse field assignments
                    step_data = {}
                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.EQUALS)
                    field_value = self.parse_value()
                    step_data[field_name] = field_value

                    while self.match(TokenType.COMMA):
                        self.advance()
                        field_name = self.expect_identifier_or_keyword().value
                        self.expect(TokenType.EQUALS)
                        field_value = self.parse_value()
                        step_data[field_name] = field_value

                    setup_steps.append(
                        ir.TestSetupStep(
                            variable_name=var_name,
                            action=ir.TestActionKind.CREATE,
                            entity_name=entity_name,
                            data=step_data,
                        )
                    )

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse action block
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)

                # Parse action kind (create, update, delete, get)
                action_token = self.current_token()
                if self.match(TokenType.CREATE):
                    kind = ir.TestActionKind.CREATE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.UPDATE):
                    kind = ir.TestActionKind.UPDATE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.DELETE):
                    kind = ir.TestActionKind.DELETE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.GET):
                    kind = ir.TestActionKind.GET
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                else:
                    raise make_parse_error(
                        f"Expected action kind (create, update, delete, get), got {action_token.type.value}",
                        self.file,
                        action_token.line,
                        action_token.column,
                    )

                action = ir.TestAction(
                    kind=kind,
                    target=target,
                    data={},
                )

                self.skip_newlines()

            # Parse data block
            elif self.match(TokenType.DATA):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    field_value = self.parse_value()
                    data[field_name] = field_value

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse filter block
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    field_value = self.parse_value()
                    filter_data[field_name] = field_value

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse search block
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                self.expect(TokenType.QUERY)
                self.expect(TokenType.COLON)
                self.parse_value()

                self.skip_newlines()
                self.expect(TokenType.DEDENT)

            # Parse order_by
            elif self.match(TokenType.ORDER_BY):
                self.advance()
                self.expect(TokenType.COLON)
                self.parse_value()
                self.skip_newlines()

            # Parse expect block
            elif self.match(TokenType.EXPECT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # Parse different assertion types
                    if self.match(TokenType.STATUS):
                        self.advance()
                        self.expect(TokenType.COLON)
                        status_value = self.expect(TokenType.IDENTIFIER).value
                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.STATUS,
                                expected_value=status_value,
                            )
                        )

                    elif self.match(TokenType.CREATED):
                        self.advance()
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.TRUE):
                            self.advance()
                            created_value = True
                        elif self.match(TokenType.FALSE):
                            self.advance()
                            created_value = False
                        else:
                            raise make_parse_error(
                                f"Expected true or false, got {self.current_token().type.value}",
                                self.file,
                                self.current_token().line,
                                self.current_token().column,
                            )
                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.CREATED,
                                expected_value=created_value,
                            )
                        )

                    elif self.match(TokenType.FIELD):
                        # field <name> <operator> <value>
                        # or field <name> <operator> field <other_field>
                        self.advance()
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)  # equals, contains, etc.
                        operator = self.parse_comparison_operator(operator_token.value)

                        # Check if value is another field reference
                        if self.match(TokenType.FIELD):
                            self.advance()
                            other_field = self.expect_identifier_or_keyword().value
                            expected_value = f"field.{other_field}"
                        else:
                            expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=field_name,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.ERROR_MESSAGE):
                        # error_message <operator> <value>
                        self.advance()
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.ERROR,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.COUNT):
                        # count <operator> <value>
                        self.advance()
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.COUNT,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.FIRST):
                        # first field <name> <operator> <value>
                        self.advance()
                        self.expect(TokenType.FIELD)
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=f"first.{field_name}",
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.LAST):
                        # last field <name> <operator> <value>
                        self.advance()
                        self.expect(TokenType.FIELD)
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=f"last.{field_name}",
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            else:
                # Unknown block, skip it
                self.advance()

        self.expect(TokenType.DEDENT)

        # Set action data
        if action:
            action = ir.TestAction(
                kind=action.kind,
                target=action.target,
                data=data,
            )

        if not action:
            raise make_parse_error(
                f"Test {name} must have an action",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.TestSpec(
            name=name,
            description=description,
            setup_steps=setup_steps,
            action=action,
            assertions=assertions,
        )

    def parse_comparison_operator(self, op_str: str) -> ir.TestComparisonOperator:
        """Parse comparison operator string to enum."""
        op_map = {
            "equals": ir.TestComparisonOperator.EQUALS,
            "not_equals": ir.TestComparisonOperator.NOT_EQUALS,
            "greater_than": ir.TestComparisonOperator.GREATER_THAN,
            "less_than": ir.TestComparisonOperator.LESS_THAN,
            "contains": ir.TestComparisonOperator.CONTAINS,
            "not_contains": ir.TestComparisonOperator.NOT_CONTAINS,
        }
        if op_str not in op_map:
            raise make_parse_error(
                f"Unknown comparison operator: {op_str}",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        return op_map[op_str]

    def parse_value(self) -> Any:
        """Parse a value (string, number, identifier, boolean)."""
        token = self.current_token()

        if self.match(TokenType.STRING):
            return self.advance().value

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            if "." in value:
                return float(value)
            return int(value)

        elif self.match(TokenType.TRUE):
            self.advance()
            return True

        elif self.match(TokenType.FALSE):
            self.advance()
            return False

        elif self.match(TokenType.IDENTIFIER):
            # Could be a variable reference
            return self.advance().value

        else:
            raise make_parse_error(
                f"Expected value, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse(self) -> ir.ModuleFragment:
        """
        Parse entire module and return IR fragment.

        Returns:
            ModuleFragment with all parsed declarations
        """
        fragment = ir.ModuleFragment()

        self.skip_newlines()

        while not self.match(TokenType.EOF):
            self.skip_newlines()

            if self.match(TokenType.ENTITY):
                entity = self.parse_entity()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities + [entity],
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences,
                    services=fragment.services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                )

            elif self.match(TokenType.SURFACE):
                surface = self.parse_surface()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces + [surface],
                    experiences=fragment.experiences,
                    services=fragment.services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                )

            elif self.match(TokenType.EXPERIENCE):
                experience = self.parse_experience()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences + [experience],
                    services=fragment.services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                )

            elif self.match(TokenType.SERVICE):
                service = self.parse_service()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences,
                    services=fragment.services + [service],
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                )

            elif self.match(TokenType.FOREIGN_MODEL):
                foreign_model = self.parse_foreign_model()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences,
                    services=fragment.services,
                    foreign_models=fragment.foreign_models + [foreign_model],
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                )

            elif self.match(TokenType.INTEGRATION):
                integration = self.parse_integration()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences,
                    services=fragment.services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations + [integration],
                    tests=fragment.tests,
                )

            elif self.match(TokenType.TEST):
                test = self.parse_test()
                fragment = ir.ModuleFragment(
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    experiences=fragment.experiences,
                    services=fragment.services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests + [test],
                )

            else:
                token = self.current_token()
                if token.type == TokenType.EOF:
                    break
                # Skip unknown tokens
                self.advance()

        return fragment


def parse_dsl(
    text: str, file: Path
) -> tuple[str | None, str | None, str | None, list[str], ir.ModuleFragment]:
    """
    Parse complete DSL file.

    Args:
        text: DSL source text
        file: Source file path

    Returns:
        Tuple of (module_name, app_name, app_title, uses, fragment)
    """
    # Tokenize
    tokens = tokenize(text, file)

    # Parse
    parser = Parser(tokens, file)
    module_name, app_name, app_title, uses = parser.parse_module_header()
    fragment = parser.parse()

    return module_name, app_name, app_title, uses, fragment
