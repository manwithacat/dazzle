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
        peek_token: Any
        skip_newlines: Any
        error: Any
        file: Any
        parse_ux_block: Any
        parse_persona_variant: Any  # From UXParserMixin
        _parse_workspace_access: Any  # From WorkspaceParserMixin
        collect_line_as_expr: Any  # From BaseParser
        parse_condition_expr: Any  # From ConditionParserMixin
        _source_location: Any  # v0.31.0: Source location helper from BaseParser
        _parse_construct_header: Any

    def parse_surface(self) -> ir.SurfaceSpec:
        """Parse surface declaration."""
        name, title, loc = self._parse_construct_header(TokenType.SURFACE)

        entity_ref = None
        view_ref = None
        mode = ir.SurfaceMode.CUSTOM
        priority = ir.BusinessPriority.MEDIUM
        sections = []
        actions = []
        ux_spec = None
        access_spec = None
        search_fields: list[str] = []
        persona_variants: list[ir.PersonaVariant] = []
        related_groups: list[ir.RelatedGroup] = []
        layout = "wizard"  # v0.61.88 (#918): default render mode for create/edit

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

            # v0.61.88 (#918): layout: wizard|single_page — controls how
            # multi-section create/edit surfaces render. wizard (default)
            # = multi-step. single_page = stacked sections, one submit at end.
            elif self.match(TokenType.LAYOUT):
                self.advance()
                self.expect(TokenType.COLON)
                layout_token = self.expect_identifier_or_keyword()
                if layout_token.value not in ("wizard", "single_page"):
                    self.error(
                        f"layout must be 'wizard' or 'single_page', got {layout_token.value!r}"
                    )
                layout = layout_token.value
                self.skip_newlines()

            # source: ViewName (view reference for field projection)
            elif self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                view_ref = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # priority: critical|high|medium|low
            elif self.match(TokenType.PRIORITY):
                self.advance()
                self.expect(TokenType.COLON)
                priority_token = self.expect_identifier_or_keyword()
                priority = ir.BusinessPriority(priority_token.value)
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

            # search: [field1, field2]
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.LBRACKET):
                    self.advance()
                    while not self.match(TokenType.RBRACKET):
                        search_fields.append(self.expect_identifier_or_keyword().value)
                        if self.match(TokenType.COMMA):
                            self.advance()
                    self.expect(TokenType.RBRACKET)
                else:
                    search_fields.append(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            # for persona_name: (persona variant at surface level)
            elif self.match(TokenType.FOR):
                variant = self.parse_persona_variant()
                persona_variants.append(variant)

            # related name "title": (related display group)
            elif self.match(TokenType.RELATED):
                group = self._parse_related_group()
                related_groups.append(group)

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
            view_ref=view_ref,
            mode=mode,
            priority=priority,
            sections=sections,
            actions=actions,
            ux=ux_spec,
            access=access_spec,
            search_fields=search_fields,
            related_groups=related_groups,
            source=loc,
            layout=layout,  # v0.61.88 (#918)
        )

    def _parse_related_group(self) -> ir.RelatedGroup:
        """Parse a related block inside a surface.

        Syntax::

            related name "Title":
              display: table|status_cards|file_list
              show: EntityA, EntityB
        """
        self.advance()  # consume 'related'
        name = self.expect(TokenType.IDENTIFIER).value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        display = None
        show: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            if token.value == "display":
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                display = ir.RelatedDisplayMode(mode_token.value)
                self.skip_newlines()
            elif token.value == "show":
                self.advance()
                self.expect(TokenType.COLON)
                show.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    show.append(self.expect(TokenType.IDENTIFIER).value)
                self.skip_newlines()
            else:
                break

        self.expect(TokenType.DEDENT)

        if display is None:
            self.error("related block requires a 'display:' field")
        if not show:
            self.error("related block requires a 'show:' field with at least one entity")

        assert display is not None  # narrowing for mypy (error() raises above)
        return ir.RelatedGroup(
            name=name,
            title=title,
            display=display,
            show=show,
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

        # v0.42.0: Optional section-level visible: condition
        visible_condition = None
        if self.match(TokenType.VISIBLE):
            self.advance()
            self.expect(TokenType.COLON)
            visible_condition = self.parse_condition_expr()
            self.skip_newlines()

        # v0.61.88 (#918): optional section-level note: "<text>"
        note: str | None = None
        if self.match(TokenType.NOTE):
            self.advance()
            self.expect(TokenType.COLON)
            note = self.expect(TokenType.STRING).value
            self.skip_newlines()

        elements = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field field_name ["label"] [key=value ...] [visible: cond] [when: expr]
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

                # Parse optional visible:, when:, help:, and trailing
                # key=value options in any order.  This allows e.g.:
                #   field x "X" visible: role(admin) widget=picker
                #   field x "X" widget=picker visible: role(admin)
                #   field x "X" help: "Pick from the cohort roster" widget=combobox
                field_visible = None
                when_expr = None
                help_text: str | None = None  # v0.61.88 (#918)
                while True:
                    if self.match(TokenType.VISIBLE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        field_visible = self.parse_condition_expr()
                    elif self.match(TokenType.WHEN):
                        self.advance()
                        self.expect(TokenType.COLON)
                        when_expr = self.collect_line_as_expr()
                    elif self.match(TokenType.HELP):
                        # v0.61.88 (#918): help: "<string>" — muted help
                        # text rendered below the field label.
                        self.advance()
                        self.expect(TokenType.COLON)
                        help_text = self.expect(TokenType.STRING).value
                    elif self.match(TokenType.SOURCE) or self.match(TokenType.IDENTIFIER):
                        # Trailing key=value option (e.g. widget=picker after visible:)
                        peek = self.peek_token()
                        if peek and peek.type == TokenType.EQUALS:
                            opt_key = self.advance().value
                            self.expect(TokenType.EQUALS)
                            if self.match(TokenType.STRING):
                                opt_val = self.advance().value
                            else:
                                opt_val = self.expect_identifier_or_keyword().value
                                while self.match(TokenType.DOT):
                                    self.advance()
                                    opt_val += "." + self.expect_identifier_or_keyword().value
                            options[opt_key] = opt_val
                        else:
                            break
                    else:
                        break

                elements.append(
                    ir.SurfaceElement(
                        field_name=field_name,
                        label=label,
                        options=options,
                        when_expr=when_expr,
                        visible=field_visible,
                        help=help_text,  # v0.61.88 (#918)
                    )
                )

                self.skip_newlines()

            else:
                token = self.current_token()
                self.error(
                    f"Unexpected '{token.value}' in surface section — "
                    f"only 'field' declarations are supported here"
                )

        self.expect(TokenType.DEDENT)

        return ir.SurfaceSection(
            name=name,
            title=title,
            elements=elements,
            visible=visible_condition,
            note=note,  # v0.61.88 (#918)
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
        trigger_token = self.expect_identifier_or_keyword()
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
        # "url" external — external link outcome
        if self.match(TokenType.STRING):
            url = self.advance().value
            self.expect(TokenType.EXTERNAL)
            return ir.Outcome(
                kind=ir.OutcomeKind.EXTERNAL,
                target="",
                url=url,
                new_tab=True,
            )

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
                f'Expected outcome (surface/experience/integration/"url" external), '
                f"got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
