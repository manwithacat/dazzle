"""
Surface parsing for DAZZLE DSL.

Handles surface declarations including sections, actions, and outcomes.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class SurfaceParserMixin:
    """
    Mixin providing surface parsing.

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
        parse_ux_block: Any
        parse_persona_variant: Any  # From UXParserMixin
        _parse_workspace_access: Any  # From WorkspaceParserMixin

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
        ux_spec = None
        access_spec = None
        persona_variants: list[ir.PersonaVariant] = []

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

            # access: public | authenticated | persona(name1, name2)
            elif self.match(TokenType.ACCESS):
                self.advance()
                self.expect(TokenType.COLON)
                access_spec = self._parse_surface_access()
                self.skip_newlines()

            # section name ["title"]:
            elif self.match(TokenType.SECTION):
                section = self.parse_surface_section()
                sections.append(section)

            # action name ["label"]:
            elif self.match(TokenType.ACTION):
                action = self.parse_surface_action()
                actions.append(action)

            # ux: (UX Semantic Layer block)
            elif self.match(TokenType.UX):
                ux_spec = self.parse_ux_block()

            # for persona_name: (persona variant at surface level)
            elif self.match(TokenType.FOR):
                variant = self.parse_persona_variant()
                persona_variants.append(variant)

            else:
                break

        self.expect(TokenType.DEDENT)

        # Merge persona_variants into ux_spec (create one if needed)
        if persona_variants:
            if ux_spec is None:
                ux_spec = ir.UXSpec(persona_variants=persona_variants)
            else:
                # Combine surface-level variants with ux block variants
                ux_spec = ir.UXSpec(
                    purpose=ux_spec.purpose,
                    show=ux_spec.show,
                    sort=ux_spec.sort,
                    filter=ux_spec.filter,
                    search=ux_spec.search,
                    empty_message=ux_spec.empty_message,
                    attention_signals=ux_spec.attention_signals,
                    persona_variants=list(ux_spec.persona_variants) + persona_variants,
                )

        return ir.SurfaceSpec(
            name=name,
            title=title,
            entity_ref=entity_ref,
            mode=mode,
            sections=sections,
            actions=actions,
            ux=ux_spec,
            access=access_spec,
        )

    def _parse_surface_access(self) -> ir.SurfaceAccessSpec:
        """
        Parse surface access specification.

        Syntax:
            access: public
            access: authenticated
            access: persona(name1, name2, ...)
        """
        if self.match(TokenType.PUBLIC):
            self.advance()
            return ir.SurfaceAccessSpec(require_auth=False)

        if self.match(TokenType.AUTHENTICATED):
            self.advance()
            return ir.SurfaceAccessSpec(require_auth=True)

        if self.match(TokenType.PERSONA):
            self.advance()
            self.expect(TokenType.LPAREN)
            personas: list[str] = []
            personas.append(self.expect_identifier_or_keyword().value)
            while self.match(TokenType.COMMA):
                self.advance()
                personas.append(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.RPAREN)
            return ir.SurfaceAccessSpec(
                require_auth=True,
                allow_personas=personas,
            )

        token = self.current_token()
        raise make_parse_error(
            f"Expected 'public', 'authenticated', or 'persona(...)' but got '{token.value}'",
            self.file,
            token.line,
            token.column,
        )

    def parse_surface_section(self) -> ir.SurfaceSection:
        """Parse surface section."""
        self.expect(TokenType.SECTION)

        name = self.expect_identifier_or_keyword().value
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

            # field field_name ["label"] [key=value ...]
            if self.match(TokenType.FIELD):
                self.advance()
                field_name = self.expect_identifier_or_keyword().value
                label = None

                if self.match(TokenType.STRING):
                    label = self.advance().value

                # Parse optional key=value options (e.g. source=pack.operation)
                options: dict[str, Any] = {}
                while self.match(TokenType.SOURCE) or self.match(TokenType.IDENTIFIER):
                    opt_key = self.advance().value
                    self.expect(TokenType.EQUALS)
                    # Value can be identifier.identifier (dotted) or a string
                    if self.match(TokenType.STRING):
                        opt_val = self.advance().value
                    else:
                        opt_val = self.expect_identifier_or_keyword().value
                        # Support dotted values: pack_name.operation
                        while self.match(TokenType.DOT):
                            self.advance()
                            opt_val += "." + self.expect_identifier_or_keyword().value
                    options[opt_key] = opt_val

                elements.append(
                    ir.SurfaceElement(
                        field_name=field_name,
                        label=label,
                        options=options,
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

        name = self.expect_identifier_or_keyword().value
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
