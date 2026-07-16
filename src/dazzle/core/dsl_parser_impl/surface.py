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
from ._refresh import parse_refresh_interval_seconds
from .dispatch import KeywordParser, parse_block_with_dispatch


class SurfaceParserMixin:
    """
    Mixin providing surface parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        enum_from_token: Any
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
              columns: title, status, due_date   # optional projection
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
        columns: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            if token.value == "display":
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                display = self.enum_from_token(ir.RelatedDisplayMode, mode_token)
                self.skip_newlines()
            elif token.value == "show":
                self.advance()
                self.expect(TokenType.COLON)
                show.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    show.append(self.expect(TokenType.IDENTIFIER).value)
                self.skip_newlines()
            elif token.type == TokenType.COLUMNS or token.value == "columns":
                # Optional field projection for related tabs (#1600 P1).
                # Field names may be reserved words (status, type, …).
                self.advance()
                self.expect(TokenType.COLON)
                columns.append(self.expect_identifier_or_keyword().value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    columns.append(self.expect_identifier_or_keyword().value)
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
            columns=columns,
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
        """Parse a ``companion <name> ["title"] [position=<pos>]:`` block.

        Refactored to dispatch-table style (follow-on to #1098). 8
        token-keyed `_c_kw_*` parsers (eyebrow/display/source/limit/
        filter/aggregate/entries/stages) + 1 IDENT-text-matched
        (``title``) + a tolerant on_unknown that bails at EOF (mirrors
        the legacy ``DEDENT, EOF`` loop guard via a sentinel) + a
        `_build_companion` builder.

        Companion syntax (v0.61.102, #923 — Part D of #918)::

            companion summary "Batch summary" position=top:
              eyebrow: "Live"
              display: summary_row
              aggregate:
                pages: max(page_count)

            companion roster_preview "Cohort roster":
              source: StudentProfile
              display: list
              filter: teaching_group = matched_teaching_group
              limit: 5
        """
        self.advance()  # consume `companion`
        name = self.expect_identifier_or_keyword().value
        header_title: str | None = None
        if self.match(TokenType.STRING):
            header_title = self.advance().value

        position = ir.CompanionPosition.BOTTOM
        section_anchor: str | None = None
        if self.match(TokenType.POSITION):
            self.advance()
            self.expect(TokenType.EQUALS)
            position, section_anchor = self._parse_companion_position()

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _CompanionState(title=header_title)
        try:
            parse_block_with_dispatch(
                self,
                first_class_keywords=_COMPANION_KEYWORDS,
                ident_keywords=_COMPANION_IDENT_KEYWORDS,
                state=state,
                on_unknown=_on_unknown_companion,
            )
        except _StopCompanionLoop:
            pass

        if self.match(TokenType.DEDENT):
            self.advance()
        return _build_companion(name, position, section_anchor, state)

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
        """Parse a ``section <name> ["title"]:`` block inside a surface.

        Refactored from a 132-line monolith — the inline ``field``
        element parse moved to :meth:`_parse_surface_field_element`.

        Optional section-level keys (``visible:``, ``note:``) are
        consumed first, then the body is a list of ``field`` element
        declarations until the closing DEDENT.
        """
        self.expect(TokenType.SECTION)
        name = self.expect_identifier_or_keyword().value
        title = self.advance().value if self.match(TokenType.STRING) else None

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        visible_condition = None
        if self.match(TokenType.VISIBLE):
            self.advance()
            self.expect(TokenType.COLON)
            visible_condition = self.parse_condition_expr()
            self.skip_newlines()

        note: str | None = None
        if self.match(TokenType.NOTE):
            # v0.61.88 (#918): optional muted section-level note line.
            self.advance()
            self.expect(TokenType.COLON)
            note = self.expect(TokenType.STRING).value
            self.skip_newlines()

        # #1600: optional section layout (e.g. layout: strip for RAG/status row).
        # Allow mixed order with note/visible by scanning once more for layout.
        layout: str | None = None
        if self.match(TokenType.LAYOUT):
            self.advance()
            self.expect(TokenType.COLON)
            layout = self.expect_identifier_or_keyword().value
            if layout not in ("strip", "grid"):
                self.error(f"section layout must be 'strip' or 'grid', got {layout!r} (#1600)")
            if layout == "grid":
                layout = None  # default field grid
            self.skip_newlines()

        elements: list[ir.SurfaceElement] = []
        subtype_panel: ir.SubtypePanelSpec | None = None
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if self.match(TokenType.FIELD):
                elements.append(self._parse_surface_field_element())
                self.skip_newlines()
            elif self.match(TokenType.SUBTYPE_PANEL):
                # v0.71.184 (#1217 Phase 3e.v): polymorphic per-subtype dispatch.
                subtype_panel = self._parse_subtype_panel()
                self.skip_newlines()
            elif self.match(TokenType.LAYOUT):
                # Trailing layout: after fields is unusual; allow for author order.
                self.advance()
                self.expect(TokenType.COLON)
                layout = self.expect_identifier_or_keyword().value
                if layout not in ("strip", "grid"):
                    self.error(f"section layout must be 'strip' or 'grid', got {layout!r} (#1600)")
                if layout == "grid":
                    layout = None
                self.skip_newlines()
            else:
                token = self.current_token()
                self.error(
                    f"Unexpected '{token.value}' in surface section — "
                    f"only 'field', 'subtype_panel', and 'layout' are supported here"
                )

        self.expect(TokenType.DEDENT)
        return ir.SurfaceSection(
            name=name,
            title=title,
            elements=elements,
            visible=visible_condition,
            note=note,
            layout=layout,
            subtype_panel=subtype_panel,
        )

    def _parse_subtype_panel(self) -> ir.SubtypePanelSpec:
        """Parse a ``subtype_panel:`` block inside a section (#1217 Phase 3e.v).

        Syntax::

            subtype_panel:
              when kind = vehicle: include surface vehicle_detail
              when kind = building: include surface building_detail

        Each branch reads `when` + the literal identifier ``kind`` + ``=`` +
        a snake_case discriminator + ``:`` + the literal identifier
        ``include`` + ``surface`` + a surface name.
        """
        self.advance()  # consume `subtype_panel`
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        branches: list[ir.SubtypePanelBranch] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            self.expect(TokenType.WHEN)
            # `kind` is a reserved keyword (TokenType.KIND); match the literal token.
            self.expect(TokenType.KIND)
            self.expect(TokenType.EQUALS)
            kind_value = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            include_ident = self.expect_identifier_or_keyword()
            if include_ident.value != "include":
                self.error(
                    f"expected 'include' in subtype_panel branch, got {include_ident.value!r}"
                )
            self.expect(TokenType.SURFACE)
            surface_name = self.expect_identifier_or_keyword().value
            branches.append(
                ir.SubtypePanelBranch(
                    when_kind=kind_value,
                    include_surface=surface_name,
                )
            )
            self.skip_newlines()
        self.expect(TokenType.DEDENT)
        return ir.SubtypePanelSpec(branches=tuple(branches))

    def _parse_surface_field_element(self) -> ir.SurfaceElement:
        """Parse one ``field <name> ["label"] [k=v ...] [visible:/when:/help:]`` row.

        The field shape allows mixed-order trailing modifiers
        (visible:/when:/help: + ``key=value`` options) so projects can
        write e.g. ``field x "X" visible: role(admin) widget=picker`` or
        ``field x "X" widget=picker visible: role(admin)``.
        """
        self.advance()  # consume `field`
        field_name = self.expect_identifier_or_keyword().value
        label = self.advance().value if self.match(TokenType.STRING) else None

        # Initial run of ``key=value`` options before any visible/when/help.
        options = self._parse_field_key_value_options()
        # Then any mix of trailing visible:/when:/help:/format: + more key=value pairs.
        field_visible, when_expr, help_text, field_format = self._parse_field_trailing_modifiers(
            options
        )

        return ir.SurfaceElement(
            field_name=field_name,
            label=label,
            options=options,
            when_expr=when_expr,
            visible=field_visible,
            help=help_text,
            format=field_format,
        )

    def _parse_field_key_value_options(self) -> dict[str, Any]:
        """Consume the leading run of ``key=value`` field options.

        Value may be a STRING or a dotted-identifier path
        (``pack_name.operation``).
        """
        options: dict[str, Any] = {}
        while self.match(TokenType.SOURCE) or self.match(TokenType.IDENTIFIER):
            opt_key = self.advance().value
            self.expect(TokenType.EQUALS)
            options[opt_key] = self._parse_field_option_value()
        return options

    def _parse_field_option_value(self) -> str:
        """Consume one ``key=`` value — STRING or dotted-identifier path."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        opt_val: str = self.expect_identifier_or_keyword().value
        while self.match(TokenType.DOT):
            self.advance()
            opt_val += "." + self.expect_identifier_or_keyword().value
        return opt_val

    def _parse_field_trailing_modifiers(
        self, options: dict[str, Any]
    ) -> tuple["ir.ConditionExpr | None", Any, str | None, "ir.FieldFormatSpec | None"]:
        """Consume any mix of trailing ``visible:`` / ``when:`` / ``help:``
        / ``key=value`` modifiers in arbitrary order.

        Mutates ``options`` in-place for any trailing key=value pairs.
        Returns ``(visible, when_expr, help)``. ``when_expr`` is typed
        Any because ``collect_line_as_expr`` returns a forward-referenced
        ``Expr`` union not re-exported via ``ir.``.
        """
        field_visible: ir.ConditionExpr | None = None
        when_expr: Any = None
        help_text: str | None = None
        field_format: ir.FieldFormatSpec | None = None

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
                # v0.61.88 (#918): help: "<string>" — muted help text
                # rendered below the field label.
                self.advance()
                self.expect(TokenType.COLON)
                help_text = self.expect(TokenType.STRING).value
            elif self.match(TokenType.FORMAT):
                # #1470 Phase 2: format: kind[:arg] — explicit cell-format override
                # (e.g. `format: currency:GBP`, `format: percent:1`, `format: relative`).
                self.advance()
                self.expect(TokenType.COLON)
                field_format = self._parse_format_spec()
            elif self.match(TokenType.SOURCE) or self.match(TokenType.IDENTIFIER):
                # Trailing key=value option (e.g. widget=picker after visible:).
                peek = self.peek_token()
                if peek and peek.type == TokenType.EQUALS:
                    opt_key = self.advance().value
                    self.expect(TokenType.EQUALS)
                    options[opt_key] = self._parse_field_option_value()
                else:
                    break
            else:
                break

        return field_visible, when_expr, help_text, field_format

    def _parse_format_spec(self) -> "ir.FieldFormatSpec":
        """Parse a ``format:`` value: ``kind`` or ``kind:arg`` (#1470 Phase 2).

        ``currency:GBP`` → kind=currency arg=GBP; ``percent`` → kind=percent
        arg=None; ``percent:1`` → kind=percent arg="1".
        """
        kind = self.expect_identifier_or_keyword().value
        arg: str | None = None
        if self.match(TokenType.COLON):
            self.advance()  # consume the arg-separating ':'
            arg = str(self.advance().value)
        return ir.FieldFormatSpec(kind=kind, arg=arg)

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
        trigger = self.enum_from_token(ir.SurfaceTrigger, trigger_token)

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
    refresh_interval: int | None = None  # #1399 slice 3
    emits: list[str] = field(default_factory=list)  # #1392 item 3
    # #1494 (UX-maturity 2c): action-proximate detail mode. `None` = unset
    # (author wrote no `peek:`); `_kw_peek` sets the explicit value.
    peek: ir.PeekMode | None = None
    # #1603 — open: TargetEntity via fk_field
    # #1600 P2 — open: first_non_null(...) or pipe-chained hops
    open_entity: str | None = None
    open_via: str | None = None
    open_via_targets: list[ir.OpenViaTarget] = field(default_factory=list)


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
    state.mode = parser.enum_from_token(ir.SurfaceMode, parser.expect_identifier_or_keyword())
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


def _kw_peek(parser: Any, state: _SurfaceState) -> None:
    """``peek: expand|slide_over|off`` — action-proximate detail (#1494, 2c).

    Inline expand-in-place / side-panel / plain-drill for a list surface's rows.
    Setting any value (including ``off``) makes ``surface.peek`` non-``None``, so
    the render-time resolver (`resolve_peek_mode`) tells an explicit ``peek: off``
    from an unset surface (``peek is None``, resolved by the default-by-role step).
    An unknown value is a parse error via ``enum_from_token``.
    """
    parser.advance()  # consume `peek`
    parser.expect(TokenType.COLON)
    state.peek = parser.enum_from_token(ir.PeekMode, parser.expect_identifier_or_keyword())
    parser.skip_newlines()


def _kw_open(parser: Any, state: _SurfaceState) -> None:
    """List row FK hop(s) — single, pipe-chained, or first_non_null (#1603 / #1600 P2).

    Forms::

        open: Company via company
        open: Company via company | SoleTrader via sole_trader
        open: first_non_null(company, sole_trader, partnership)
        open: first_non_null(Company via company, SoleTrader via sole_trader)

    First non-null FK on the row wins at drill time; null chain falls back to
    same-entity detail (#1614).
    """
    parser.advance()  # consume `open`
    parser.expect(TokenType.COLON)
    targets: list[ir.OpenViaTarget] = []
    tok = parser.current_token()
    if tok is not None and tok.value == "first_non_null":
        parser.advance()
        parser.expect(TokenType.LPAREN)
        while not parser.match(TokenType.RPAREN):
            parser.skip_newlines()
            if parser.match(TokenType.RPAREN):
                break
            first = parser.expect_identifier_or_keyword().value
            if parser.match(TokenType.VIA):
                parser.advance()
                via = parser.expect_identifier_or_keyword().value
                targets.append(ir.OpenViaTarget(via=via, entity=first))
            else:
                # Bare field — entity inferred from ref target at link/compile.
                targets.append(ir.OpenViaTarget(via=first, entity=None))
            if parser.match(TokenType.COMMA):
                parser.advance()
                continue
            break
        parser.expect(TokenType.RPAREN)
    else:
        # Entity via field (| Entity via field)*
        while True:
            entity = parser.expect_identifier_or_keyword().value
            parser.expect(TokenType.VIA)
            via = parser.expect_identifier_or_keyword().value
            targets.append(ir.OpenViaTarget(via=via, entity=entity))
            if parser.match(TokenType.PIPE):
                parser.advance()
                continue
            break
    if not targets:
        parser.error("open: requires at least one hop (Entity via field or first_non_null(...))")
    state.open_via_targets = targets
    # Back-compat single-field views (validation, simple templates)
    state.open_entity = targets[0].entity
    state.open_via = targets[0].via
    parser.skip_newlines()


def _kw_refresh(parser: Any, state: _SurfaceState) -> None:
    """``refresh: every Ns`` — declarative live-refresh poll interval (#1399).

    Standalone-surface analogue of the workspace-region primitive (#1391): the
    list table's HTMX-loaded ``<tbody>`` appends ``, every Ns`` to its trigger so
    the existing list data endpoint re-renders on a poll. Shares the parser +
    5s floor with the region surface (``_refresh.parse_refresh_interval_seconds``).
    """
    parser.advance()  # consume `refresh`
    parser.expect(TokenType.COLON)
    state.refresh_interval = parse_refresh_interval_seconds(parser)
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
    state.priority = parser.enum_from_token(
        ir.BusinessPriority, parser.expect_identifier_or_keyword()
    )
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


def _kw_emits(parser: Any, state: _SurfaceState) -> None:
    """``emits: [surface_a, surface_b]`` — surfaces this custom surface links to (#1392 item 3).

    Each name must resolve to a declared surface (checked at validate time by
    ``validate_emits_targets``). The dead-target build gate for the custom escape hatch.
    """
    parser.advance()  # consume 'emits'
    parser.expect(TokenType.COLON)
    parser.expect(TokenType.LBRACKET)
    while not parser.match(TokenType.RBRACKET):
        state.emits.append(parser.expect_identifier_or_keyword().value)
        if parser.match(TokenType.COMMA):
            parser.advance()
    parser.expect(TokenType.RBRACKET)
    parser.skip_newlines()


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
    TokenType.EMITS: _kw_emits,  # #1392 item 3 — `emits` is a lexer keyword (TokenType.EMITS)
}


_SURFACE_IDENT_KEYWORDS: dict[str, KeywordParser[_SurfaceState]] = {
    "show_history": _kw_show_history,
    "refresh": _kw_refresh,  # #1399 slice 3 — live-refresh poll interval
    "peek": _kw_peek,  # #1494 (2c) — action-proximate detail mode
    "open": _kw_open,  # #1603 — list row open via FK hop
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
        refresh_interval=state.refresh_interval,
        emits=tuple(state.emits),
        peek=state.peek,
        open_via=state.open_via,
        open_entity=state.open_entity,
        open_via_targets=list(state.open_via_targets),
    )


# ============================================================ #
# _parse_companion — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 130-line monolith was replaced (v0.70.32) with the dispatch
# pattern shipped in #1097. 8 token-keyed `_c_kw_*` + 1 IDENT-keyed
# (`title`) + a `_StopCompanionLoop` sentinel for the legacy
# ``DEDENT, EOF`` loop guard + a `_build_companion` builder.


@dataclass
class _CompanionState:
    """Accumulator for :meth:`SurfaceParserMixin._parse_companion`.

    ``title`` is pre-populated from the optional header STRING and
    may be overwritten by a later ``title:`` keyword in the body.
    """

    title: str | None = None
    eyebrow: str | None = None
    display: str | None = None
    source: str | None = None
    filter: ir.ConditionExpr | None = None
    limit: int | None = None
    aggregate: dict[str, str] = field(default_factory=dict)
    entries: list[ir.CompanionEntrySpec] = field(default_factory=list)
    stages: list[ir.CompanionStageSpec] = field(default_factory=list)


class _StopCompanionLoop(Exception):
    """Sentinel — raised by ``_on_unknown_companion`` at EOF to bail
    the dispatch loop. Mirrors the legacy ``while not match(DEDENT, EOF)``
    guard (the helper only checks DEDENT)."""


# ---------- Token-keyed keyword parsers ---------- #


def _c_kw_eyebrow(parser: Any, state: _CompanionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.eyebrow = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _c_kw_display(parser: Any, state: _CompanionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.display = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _c_kw_source(parser: Any, state: _CompanionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.source = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _c_kw_limit(parser: Any, state: _CompanionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.limit = int(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _c_kw_filter(parser: Any, state: _CompanionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.filter = parser.parse_condition_expr()
    parser.skip_newlines()


def _c_kw_aggregate(parser: Any, state: _CompanionState) -> None:
    """``aggregate:`` — INDENT then mixin's metric-map helper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.aggregate = parser._parse_companion_aggregate()


def _c_kw_entries(parser: Any, state: _CompanionState) -> None:
    """``entries:`` — INDENT then mixin's dash-list-of-entries helper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.entries = parser._parse_companion_entries()


def _c_kw_stages(parser: Any, state: _CompanionState) -> None:
    """``stages:`` — INDENT then mixin's dash-list-of-stages helper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.stages = parser._parse_companion_stages()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _c_kw_title(parser: Any, state: _CompanionState) -> None:
    """``title: "..."`` — body override of the header-form title."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.title = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


# ---------- Dispatch tables + on_unknown + builder ---------- #


_COMPANION_KEYWORDS: dict[TokenType, KeywordParser[_CompanionState]] = {
    TokenType.EYEBROW: _c_kw_eyebrow,
    TokenType.DISPLAY: _c_kw_display,
    TokenType.SOURCE: _c_kw_source,
    TokenType.LIMIT: _c_kw_limit,
    TokenType.FILTER: _c_kw_filter,
    TokenType.AGGREGATE: _c_kw_aggregate,
    TokenType.ENTRIES: _c_kw_entries,
    TokenType.STAGES: _c_kw_stages,
}


_COMPANION_IDENT_KEYWORDS: dict[str, KeywordParser[_CompanionState]] = {
    "title": _c_kw_title,
}


def _on_unknown_companion(parser: Any) -> None:
    """Tolerate unknown keywords; bail the loop on EOF.

    Mirrors the legacy ``while not match(DEDENT, EOF)`` guard — the
    dispatch helper only checks DEDENT, so we raise the sentinel here
    when at EOF. The caller catches it and consumes any trailing
    DEDENT before assembly.
    """
    if parser.match(TokenType.EOF):
        raise _StopCompanionLoop()
    parser.advance()
    parser.skip_newlines()


def _build_companion(
    name: str,
    position: ir.CompanionPosition,
    section_anchor: str | None,
    state: _CompanionState,
) -> ir.CompanionSpec:
    return ir.CompanionSpec(
        name=name,
        title=state.title,
        eyebrow=state.eyebrow,
        display=state.display,
        position=position,
        section_anchor=section_anchor,
        source=state.source,
        filter=state.filter,
        limit=state.limit,
        aggregate=state.aggregate,
        entries=state.entries,
        stages=state.stages,
    )
