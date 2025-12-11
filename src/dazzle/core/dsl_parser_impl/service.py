"""
Service parsing for DAZZLE DSL.

Handles external API and domain service declarations.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class ServiceParserMixin:
    """
    Mixin providing service and foreign model parsing.

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
        parse_type_spec: Any
        parse_field_modifiers: Any

    def parse_service(self) -> ir.APISpec | ir.DomainServiceSpec:
        """Parse service declaration (external API or domain service).

        External APIs have: spec, auth_profile, owner
        Domain services have: kind, input, output, guarantees, stub
        """
        self.expect(TokenType.SERVICE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Peek at first directive to determine service type
        self.skip_newlines()
        if self.match(TokenType.KIND):
            # Domain service (v0.5.0)
            return self._parse_domain_service_body(name, title)
        else:
            # External API (original behavior)
            return self._parse_external_api_body(name, title)

    def _parse_external_api_body(self, name: str, title: str | None) -> ir.APISpec:
        """Parse external API service body."""
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

        return ir.APISpec(
            name=name,
            title=title,
            spec_url=spec_url,
            spec_inline=spec_inline,
            auth_profile=auth_profile,
            owner=owner,
        )

    def _parse_domain_service_body(self, name: str, title: str | None) -> ir.DomainServiceSpec:
        """Parse domain service body (v0.5.0).

        DSL syntax:
            service calculate_vat "Calculate VAT":
              kind: domain_logic

              input:
                invoice_id: uuid required

              output:
                vat_amount: money
                breakdown: json

              guarantees:
                - "Must not mutate the invoice record."

              stub: python
        """
        kind = ir.DomainServiceKind.DOMAIN_LOGIC
        inputs: list[ir.ServiceFieldSpec] = []
        outputs: list[ir.ServiceFieldSpec] = []
        guarantees: list[str] = []
        stub_language = ir.StubLanguage.PYTHON

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # kind: domain_logic | validation | integration | workflow
            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                # Use expect_identifier_or_keyword since 'integration' is a keyword
                kind_token = self.expect_identifier_or_keyword()
                kind = ir.DomainServiceKind(kind_token.value)
                self.skip_newlines()

            # input:
            elif self.match(TokenType.INPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                inputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # output:
            elif self.match(TokenType.OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                outputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # guarantees:
            elif self.match(TokenType.GUARANTEES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                guarantees = self._parse_guarantee_list()
                self.expect(TokenType.DEDENT)

            # stub: python | typescript
            elif self.match(TokenType.STUB):
                self.advance()
                self.expect(TokenType.COLON)
                lang_token = self.expect(TokenType.IDENTIFIER)
                stub_language = ir.StubLanguage(lang_token.value)
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.DomainServiceSpec(
            name=name,
            title=title,
            kind=kind,
            inputs=inputs,
            outputs=outputs,
            guarantees=guarantees,
            stub_language=stub_language,
        )

    def _parse_service_fields(self) -> list[ir.ServiceFieldSpec]:
        """Parse service input/output fields.

        Format:
            field_name: type_name [required]
        """
        fields: list[ir.ServiceFieldSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field_name: type_name [required]
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Parse type - could be identifier or type keyword with params like decimal(10,2)
            type_name = self.expect_identifier_or_keyword().value

            # Check for type parameters like (10,2) or (200)
            if self.match(TokenType.LPAREN):
                self.advance()
                params = []
                params.append(self.expect(TokenType.NUMBER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    params.append(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.RPAREN)
                type_name = f"{type_name}({','.join(params)})"

            # Check for required modifier
            required = False
            if self.match(TokenType.IDENTIFIER):
                if self.current_token().value == "required":
                    self.advance()
                    required = True

            fields.append(
                ir.ServiceFieldSpec(
                    name=field_name,
                    type_name=type_name,
                    required=required,
                )
            )
            self.skip_newlines()

        return fields

    def _parse_guarantee_list(self) -> list[str]:
        """Parse guarantee list (strings prefixed with dash).

        Format:
            - "Guarantee text here"
            - "Another guarantee"
        """
        guarantees: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # - "guarantee text"
            if self.match(TokenType.MINUS):
                self.advance()
                guarantee_text = self.expect(TokenType.STRING).value
                guarantees.append(guarantee_text)
                self.skip_newlines()
            else:
                break

        return guarantees

    def parse_foreign_model(self) -> ir.ForeignModelSpec:
        """Parse foreign_model declaration."""
        self.expect(TokenType.FOREIGN_MODEL)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.FROM)
        api_ref = self.expect(TokenType.IDENTIFIER).value

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
            api_ref=api_ref,
            key_fields=key_fields,
            constraints=constraints,
            fields=fields,
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
