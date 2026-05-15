"""
Surface parsing for DAZZLE DSL.

Handles surface declarations including sections, actions, and outcomes.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..ir.location import SourceLocation
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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
        """Parse a ``surface:`` declaration.

        Refactored to dispatch-table style (follow-on to #1098). The 16
        outer keyword branches become module-level ``_kw_*`` functions
        registered in :data:`_SURFACE_KEYWORDS` / :data:`_SURFACE_IDENT_KEYWORDS`;
        the post-loop persona-variant merge + IR assembly live in
        :func:`_build_surface`.
        """
        name, title, loc = self._parse_construct_header(TokenType.SURFACE)

        state = _SurfaceState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_SURFACE_KEYWORDS,
            ident_keywords=_SURFACE_IDENT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_surface(name, title, loc, state)

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

    def _parse_companion(self) -> ir.CompanionSpec:
        """Parse a `companion <name> ["title"] [position=<pos>]:` block.

        Companion syntax (v0.61.102, #923 — Part D of #918)::

            companion summary "Batch summary" position=top:
              eyebrow: "Live"
              display: summary_row
              aggregate:
                pages: max(page_count)
                strands: count(AssessmentObjective)

            companion job_plan "What this upload creates" position=below_section[automation]:
              display: status_list
              entries:
                - title: "Classify the batch"
                  caption: "Match paper, subject, year group..."

            companion roster_preview "Cohort roster":
              source: StudentProfile
              display: list
              filter: teaching_group = matched_teaching_group
              limit: 5
        """
        self.advance()  # consume `companion`
        name = self.expect_identifier_or_keyword().value
        title: str | None = None
        if self.match(TokenType.STRING):
            title = self.advance().value

        position = ir.CompanionPosition.BOTTOM
        section_anchor: str | None = None

        # Optional inline `position=<top|bottom|below_section[<name>]>`
        # before the colon.
        if self.match(TokenType.POSITION):
            self.advance()
            self.expect(TokenType.EQUALS)
            position, section_anchor = self._parse_companion_position()

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        eyebrow: str | None = None
        display: str | None = None
        source: str | None = None
        filter_expr: ir.ConditionExpr | None = None
        limit: int | None = None
        aggregate: dict[str, str] = {}
        entries: list[ir.CompanionEntrySpec] = []
        stages: list[ir.CompanionStageSpec] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            key = tok.value

            if key == "title":
                self.advance()
                self.expect(TokenType.COLON)
                title = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "eyebrow":
                self.advance()
                self.expect(TokenType.COLON)
                eyebrow = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "display":
                self.advance()
                self.expect(TokenType.COLON)
                display = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "source":
                self.advance()
                self.expect(TokenType.COLON)
                source = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "limit":
                self.advance()
                self.expect(TokenType.COLON)
                limit = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()
            elif key == "filter":
                self.advance()
                self.expect(TokenType.COLON)
                filter_expr = self.parse_condition_expr()
                self.skip_newlines()
            elif key == "aggregate":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                aggregate = self._parse_companion_aggregate()
            elif key == "entries":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                entries = self._parse_companion_entries()
            elif key == "stages":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                stages = self._parse_companion_stages()
            else:
                # Unknown key — advance defensively rather than abort.
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.CompanionSpec(
            name=name,
            title=title,
            eyebrow=eyebrow,
            display=display,
            position=position,
            section_anchor=section_anchor,
            source=source,
            filter=filter_expr,
            limit=limit,
            aggregate=aggregate,
            entries=entries,
            stages=stages,
        )

    def _parse_companion_position(self) -> tuple[ir.CompanionPosition, str | None]:
        """Parse the value of a companion `position=...` attribute.

        Accepts: `top`, `bottom`, `below_section[<section_name>]`.
        Returns the position enum + the section anchor (None when not
        a `below_section` form)."""
        if self.match(TokenType.BELOW_SECTION):
            self.advance()
            self.expect(TokenType.LBRACKET)
            anchor = self.expect_identifier_or_keyword().value
            self.expect(TokenType.RBRACKET)
            return ir.CompanionPosition.BELOW_SECTION, anchor

        token = self.expect_identifier_or_keyword()
        try:
            return ir.CompanionPosition(token.value), None
        except ValueError as exc:
            raise make_parse_error(
                f"companion position must be 'top', 'bottom', or "
                f"'below_section[<section>]', got {token.value!r}",
                self.file,
                token.line,
                token.column,
            ) from exc

    def _parse_companion_aggregate(self) -> dict[str, str]:
        """Parse `metric_name: <expression>` lines inside a companion's
        `aggregate:` block until DEDENT. The right-hand side is captured
        verbatim as a string — runtime evaluation happens elsewhere
        (mirrors the workspace-region aggregate flow)."""
        result: dict[str, str] = {}
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            metric_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            # Capture the rest of the line as a free-form expression
            # string. Use the underlying token stream to read until
            # newline.
            expr_tokens: list[str] = []
            while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                expr_tokens.append(self.current_token().value)
                self.advance()
            result[metric_name] = " ".join(expr_tokens).strip()
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return result

    def _parse_companion_dash_block(self) -> dict[str, str]:
        """Parse a single dash-prefixed YAML-style entry inside a
        companion `entries:` / `stages:` block. Token stream looks like:

            MINUS  IDENTIFIER  COLON  STRING  [NEWLINE
              INDENT
              IDENTIFIER  COLON  STRING  NEWLINE
              ...
              DEDENT]

        Returns the collected key→string-value mapping. Caller maps
        the keys onto the relevant Spec class."""
        self.advance()  # consume `-`
        data: dict[str, str] = {}
        # First key/value on the same line as the dash.
        first_key = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        data[first_key] = self.expect(TokenType.STRING).value
        self.skip_newlines()
        # Optional indented continuation block with more `key: value`
        # pairs. The lexer emits INDENT when subsequent lines are
        # indented further than the dash.
        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break
                key = self.expect_identifier_or_keyword().value
                self.expect(TokenType.COLON)
                data[key] = self.expect(TokenType.STRING).value
                self.skip_newlines()
            if self.match(TokenType.DEDENT):
                self.advance()
        return data

    def _parse_companion_entries(self) -> list[ir.CompanionEntrySpec]:
        """Parse `- title: ... caption: ...` entries inside a companion's
        `entries:` block."""
        entries: list[ir.CompanionEntrySpec] = []
        while self.match(TokenType.MINUS):
            data = self._parse_companion_dash_block()
            entries.append(
                ir.CompanionEntrySpec(
                    title=data.get("title", ""),
                    caption=data.get("caption"),
                    state=data.get("state"),
                    icon=data.get("icon"),
                )
            )
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return entries

    def _parse_companion_stages(self) -> list[ir.CompanionStageSpec]:
        """Parse `- label: ... caption: ...` stages inside a companion's
        `stages:` block."""
        stages: list[ir.CompanionStageSpec] = []
        while self.match(TokenType.MINUS):
            data = self._parse_companion_dash_block()
            stages.append(
                ir.CompanionStageSpec(
                    label=data.get("label", ""),
                    caption=data.get("caption"),
                )
            )
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return stages

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


# ============================================================ #
# parse_surface — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 205-line monolith was replaced (v0.70.17) with the dispatch
# pattern shipped in #1097. Each former branch is a small ``_kw_*``
# free function below; the post-loop persona-variant merge into the
# ``ux`` spec + IR assembly live in :func:`_build_surface`.


@dataclass
class _SurfaceState:
    """Accumulator for :meth:`SurfaceParserMixin.parse_surface`.

    One field per legal keyword in a ``surface:`` block, mirroring the
    locals of the legacy monolith. ``persona_variants`` accumulates
    surface-level ``as <persona>:`` variants which the builder folds
    into ``ux_spec.persona_variants`` post-loop.
    """

    entity_ref: str | None = None
    view_ref: str | None = None
    mode: ir.SurfaceMode = ir.SurfaceMode.CUSTOM
    priority: ir.BusinessPriority = ir.BusinessPriority.MEDIUM
    sections: list[ir.SurfaceSection] = field(default_factory=list)
    actions: list[ir.SurfaceAction] = field(default_factory=list)
    ux_spec: ir.UXSpec | None = None
    access_spec: ir.SurfaceAccessSpec | None = None
    search_fields: list[str] = field(default_factory=list)
    persona_variants: list[ir.PersonaVariant] = field(default_factory=list)
    related_groups: list[ir.RelatedGroup] = field(default_factory=list)
    layout: str = "wizard"  # v0.61.88 (#918)
    companions: list[ir.CompanionSpec] = field(default_factory=list)  # v0.61.102 (#923)
    display: str | None = None  # v0.61.126 (#942)
    show_history: bool = False  # #956 cycle 8
    render: str | None = None  # Plan 2


# ---------- Token-keyed keyword parsers ---------- #


def _kw_uses(parser: Any, state: _SurfaceState) -> None:
    """``uses entity EntityName`` — entity binding for the surface."""
    parser.advance()
    parser.expect(TokenType.ENTITY)
    state.entity_ref = parser.expect(TokenType.IDENTIFIER).value
    parser.skip_newlines()


def _kw_mode(parser: Any, state: _SurfaceState) -> None:
    """``mode: view|create|edit|list|custom``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.mode = ir.SurfaceMode(parser.expect_identifier_or_keyword().value)
    parser.skip_newlines()


def _kw_layout(parser: Any, state: _SurfaceState) -> None:
    """``layout: wizard|single_page`` — multi-section render strategy (#918)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    layout_token = parser.expect_identifier_or_keyword()
    if layout_token.value not in ("wizard", "single_page"):
        parser.error(f"layout must be 'wizard' or 'single_page', got {layout_token.value!r}")
    state.layout = layout_token.value
    parser.skip_newlines()


def _kw_render(parser: Any, state: _SurfaceState) -> None:
    """``render: <renderer-name>`` — surface-level renderer override (Plan 2)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.render = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_source(parser: Any, state: _SurfaceState) -> None:
    """``source: ViewName`` — view reference for field projection."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.view_ref = parser.expect(TokenType.IDENTIFIER).value
    parser.skip_newlines()


def _kw_priority(parser: Any, state: _SurfaceState) -> None:
    """``priority: critical|high|medium|low``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.priority = ir.BusinessPriority(parser.expect_identifier_or_keyword().value)
    parser.skip_newlines()


def _kw_access(parser: Any, state: _SurfaceState) -> None:
    """``access: public | authenticated | persona(name1, name2)``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.access_spec = parser._parse_surface_access()
    parser.skip_newlines()


def _kw_section(parser: Any, state: _SurfaceState) -> None:
    """``section name ["title"]:`` — helper consumes its own keyword + body."""
    state.sections.append(parser.parse_surface_section())


def _kw_action(parser: Any, state: _SurfaceState) -> None:
    """``action name ["label"]:`` — helper consumes its own keyword + body."""
    state.actions.append(parser.parse_surface_action())


def _kw_ux(parser: Any, state: _SurfaceState) -> None:
    """``ux:`` — UX Semantic Layer block, helper consumes its own keyword."""
    state.ux_spec = parser.parse_ux_block()


def _kw_search(parser: Any, state: _SurfaceState) -> None:
    """``search: field`` OR ``search: [f1, f2]``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.LBRACKET):
        parser.advance()
        while not parser.match(TokenType.RBRACKET):
            state.search_fields.append(parser.expect_identifier_or_keyword().value)
            if parser.match(TokenType.COMMA):
                parser.advance()
        parser.expect(TokenType.RBRACKET)
    else:
        state.search_fields.append(parser.expect_identifier_or_keyword().value)
    parser.skip_newlines()


def _kw_as(parser: Any, state: _SurfaceState) -> None:
    """``as <persona>:`` — surface-level persona variant.

    Renamed from ``for <persona>:`` in #998 — ``as`` is the canonical
    persona binding introducer. The helper consumes its own keyword.
    """
    state.persona_variants.append(parser.parse_persona_variant())


def _kw_related(parser: Any, state: _SurfaceState) -> None:
    """``related name "title":`` — related display group block."""
    state.related_groups.append(parser._parse_related_group())


def _kw_companion(parser: Any, state: _SurfaceState) -> None:
    """``companion <name> ["title"] [position=<pos>]:`` — read-only side panel (#923)."""
    state.companions.append(parser._parse_companion())


def _kw_display(parser: Any, state: _SurfaceState) -> None:
    """``display: pdf_viewer`` — VIEW-mode display override (#942).

    Only ``pdf_viewer`` is recognised today; the parser validates that.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    display_token = parser.expect_identifier_or_keyword()
    if display_token.value != "pdf_viewer":
        parser.error(f"surface display must be 'pdf_viewer', got {display_token.value!r}")
    state.display = display_token.value
    parser.skip_newlines()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _kw_show_history(parser: Any, state: _SurfaceState) -> None:
    """``show_history: true|false`` — opt-in audit-history region (#956 cycle 8)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.show_history = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.show_history = False
    else:
        parser.error(
            f"show_history must be 'true' or 'false', got {parser.current_token().value!r}"
        )
    parser.skip_newlines()


# ---------- Dispatch tables + unknown handler ---------- #


_SURFACE_KEYWORDS: dict[TokenType, KeywordParser[_SurfaceState]] = {
    TokenType.USES: _kw_uses,
    TokenType.MODE: _kw_mode,
    TokenType.LAYOUT: _kw_layout,
    TokenType.RENDER: _kw_render,
    TokenType.SOURCE: _kw_source,
    TokenType.PRIORITY: _kw_priority,
    TokenType.ACCESS: _kw_access,
    TokenType.SECTION: _kw_section,
    TokenType.ACTION: _kw_action,
    TokenType.UX: _kw_ux,
    TokenType.SEARCH: _kw_search,
    TokenType.AS: _kw_as,
    TokenType.RELATED: _kw_related,
    TokenType.COMPANION: _kw_companion,
    TokenType.DISPLAY: _kw_display,
}


_SURFACE_IDENT_KEYWORDS: dict[str, KeywordParser[_SurfaceState]] = {
    "show_history": _kw_show_history,
}


# ---------- Post-loop builder ---------- #
#
# Unknown keywords fall through to the dispatch helper's default —
# a ``Unknown keyword in block: 'X'`` parse error, strictly better
# diagnostics than the legacy ``Expected DEDENT, got X`` that the
# original ``else: break`` + ``expect(DEDENT)`` produced.


def _build_surface(
    name: str,
    title: str | None,
    loc: SourceLocation,
    state: _SurfaceState,
) -> ir.SurfaceSpec:
    """Merge surface-level persona variants into the ``ux`` spec, build IR.

    If both an inline ``as <persona>:`` block and a ``ux: persona_variants:``
    block are present, the surface-level variants are *appended* to the
    block-level ones — order preserved from the legacy monolith.
    """
    ux_spec = state.ux_spec
    if state.persona_variants:
        if ux_spec is None:
            ux_spec = ir.UXSpec(persona_variants=state.persona_variants)
        else:
            ux_spec = ir.UXSpec(
                purpose=ux_spec.purpose,
                show=ux_spec.show,
                sort=ux_spec.sort,
                filter=ux_spec.filter,
                search=ux_spec.search,
                empty_message=ux_spec.empty_message,
                attention_signals=ux_spec.attention_signals,
                persona_variants=list(ux_spec.persona_variants) + state.persona_variants,
            )

    return ir.SurfaceSpec(
        name=name,
        title=title,
        entity_ref=state.entity_ref,
        view_ref=state.view_ref,
        mode=state.mode,
        priority=state.priority,
        sections=state.sections,
        actions=state.actions,
        ux=ux_spec,
        access=state.access_spec,
        search_fields=state.search_fields,
        related_groups=state.related_groups,
        source=loc,
        layout=state.layout,
        companions=state.companions,
        display=state.display,
        show_history=state.show_history,
        render=state.render,
    )
