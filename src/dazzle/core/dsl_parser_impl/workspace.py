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
        peek_token: Any
        file: Any
        _source_location: Any
        _parse_construct_header: Any

    # v0.60.0: Valid units for bucket(field, unit) — keep in sync with
    # aggregate.TruncateUnit. The parser rejects other units at parse
    # time so the runtime never sees an invalid truncate string.
    _BUCKET_UNITS: frozenset[str] = frozenset({"day", "week", "month", "quarter", "year"})

    def _parse_group_by_element(self) -> str | ir.BucketRef:
        """Parse one group_by entry — either a bare field name or bucket().

        Supports:
          ``status`` → returns "status"
          ``bucket(created_at, day)`` → returns BucketRef(field, unit)

        The ``bucket`` keyword is recognised by identifier value followed
        by ``(`` — it's not a reserved token so normal fields named
        anything else are unaffected.
        """
        tok = self.current_token()
        if (
            tok.type == TokenType.IDENTIFIER
            and tok.value == "bucket"
            and self.peek_token().type == TokenType.LPAREN
        ):
            self.advance()  # consume `bucket`
            self.expect(TokenType.LPAREN)
            field = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COMMA)
            unit_tok = self.expect_identifier_or_keyword()
            unit = unit_tok.value
            if unit not in self._BUCKET_UNITS:
                raise make_parse_error(
                    f"Invalid bucket unit {unit!r}. Expected one of {sorted(self._BUCKET_UNITS)}.",
                    self.file,
                    unit_tok.line,
                    unit_tok.column,
                )
            self.expect(TokenType.RPAREN)
            return ir.BucketRef(field=field, unit=unit)
        name: str = self.expect_identifier_or_keyword().value
        return name

    # v0.61.25 (#884): supported relative-duration units for `delta.period`.
    # Maps the unit name (singular OR plural) to seconds. Calendar-aligned
    # periods (`current_week`, `current_month`) are deferred to a follow-up.
    _DELTA_PERIOD_UNITS: dict[str, int] = {  # noqa: RUF012
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800,
        "month": 2592000,  # 30d approximation; calendar-aligned in follow-up
        "months": 2592000,
        "quarter": 7776000,  # 90d approximation
        "quarters": 7776000,
        "year": 31536000,  # 365d approximation
        "years": 31536000,
    }

    # Human-readable label for a delta period — used in the rendered
    # ``vs <label>`` suffix. Falls back to the period spec verbatim.
    _DELTA_PERIOD_LABELS: dict[tuple[int, str], str] = {  # noqa: RUF012
        (1, "day"): "yesterday",
        (1, "week"): "last week",
        (1, "month"): "last month",
        (1, "quarter"): "last quarter",
        (1, "year"): "last year",
    }

    _DELTA_VALID_SENTIMENTS: frozenset[str] = frozenset(  # noqa: RUF012
        {"positive_up", "positive_down", "neutral"}
    )

    def _parse_delta_block(self) -> ir.DeltaSpec:
        """Parse a ``delta:`` block inside a workspace region (#884).

        Syntax (inside the indented body):
            period: <int> <unit>          # required; e.g. 1 day, 7 days
            sentiment: positive_up|positive_down|neutral   # default positive_up
            field: <column>               # optional; defaults to created_at
        """
        period_seconds: int | None = None
        period_label: str = "prior period"
        sentiment: str = "positive_up"
        date_field: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.expect_identifier_or_keyword()
            key = key_tok.value
            self.expect(TokenType.COLON)

            if key == "period":
                qty_tok = self.advance()
                try:
                    quantity = int(qty_tok.value)
                except (TypeError, ValueError):
                    raise make_parse_error(
                        f"delta.period quantity must be an integer, got {qty_tok.value!r}",
                        self.file,
                        qty_tok.line,
                        qty_tok.column,
                    ) from None
                unit_tok = self.expect_identifier_or_keyword()
                unit = unit_tok.value
                if unit not in self._DELTA_PERIOD_UNITS:
                    raise make_parse_error(
                        f"delta.period unit must be one of "
                        f"{sorted(self._DELTA_PERIOD_UNITS)}; got {unit!r}",
                        self.file,
                        unit_tok.line,
                        unit_tok.column,
                    )
                period_seconds = quantity * self._DELTA_PERIOD_UNITS[unit]
                # Singularize the unit for the label key lookup
                singular_unit = unit.rstrip("s") if unit not in {"weeks"} else "week"
                # Re-map plurals back to canonical singular for label lookup
                singular_unit = {
                    "second": "second",
                    "minute": "minute",
                    "hour": "hour",
                    "day": "day",
                    "week": "week",
                    "month": "month",
                    "quarter": "quarter",
                    "year": "year",
                }.get(unit.rstrip("s"), unit.rstrip("s"))
                period_label = self._DELTA_PERIOD_LABELS.get(
                    (quantity, singular_unit),
                    f"prior {quantity} {unit}",
                )
            elif key == "sentiment":
                sentiment_tok = self.expect_identifier_or_keyword()
                sentiment = sentiment_tok.value
                if sentiment not in self._DELTA_VALID_SENTIMENTS:
                    raise make_parse_error(
                        f"delta.sentiment must be one of "
                        f"{sorted(self._DELTA_VALID_SENTIMENTS)}; got {sentiment!r}",
                        self.file,
                        sentiment_tok.line,
                        sentiment_tok.column,
                    )
            elif key == "field":
                date_field = self.expect_identifier_or_keyword().value
            else:
                raise make_parse_error(
                    f"Unknown delta block key {key!r}. Expected one of: period, sentiment, field.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

            self.skip_newlines()

        if period_seconds is None:
            tok = self.current_token()
            raise make_parse_error(
                "delta block requires `period: <int> <unit>` (e.g. `period: 1 day`)",
                self.file,
                tok.line,
                tok.column,
            )

        return ir.DeltaSpec(
            period_seconds=period_seconds,
            sentiment=sentiment,
            date_field=date_field,
            period_label=period_label,
        )

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
        name, title, loc = self._parse_construct_header(
            TokenType.WORKSPACE, allow_keyword_name=True
        )

        purpose = None
        stage = None
        regions: list[ir.WorkspaceRegion] = []
        nav_groups: list[ir.NavGroupSpec] = []
        ux_spec = None
        access_spec = None
        context_selector = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # access: public | authenticated | persona(name1, name2)
            if self.match(TokenType.ACCESS):
                self.advance()
                self.expect(TokenType.COLON)
                access_spec = self._parse_workspace_access()
                self.skip_newlines()

            # purpose: "..."
            elif self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # stage: "stage_name" (v0.8.0) - preferred
            # engine_hint: "archetype_name" (v0.3.1) - deprecated, use stage instead
            elif self.match(TokenType.STAGE) or self.match(TokenType.ENGINE_HINT):
                self.advance()
                self.expect(TokenType.COLON)
                stage = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # context_selector:
            elif self.match(TokenType.CONTEXT_SELECTOR):
                context_selector = self._parse_context_selector()

            # nav_group "Label" [icon=name] [collapsed]:
            elif self.match(TokenType.NAV_GROUP):
                nav_groups.append(self._parse_nav_group())

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
            stage=stage,
            regions=regions,
            nav_groups=nav_groups,
            ux=ux_spec,
            access=access_spec,
            context_selector=context_selector,
            source=loc,
        )

    def _parse_workspace_access(self) -> ir.WorkspaceAccessSpec:
        """
        Parse workspace access specification.

        Syntax:
            access: public
            access: authenticated
            access: persona(name1, name2, ...)
        """
        # Check for access level keywords
        if self.match(TokenType.PUBLIC):
            self.advance()
            return ir.WorkspaceAccessSpec(level=ir.WorkspaceAccessLevel.PUBLIC)

        if self.match(TokenType.AUTHENTICATED):
            self.advance()
            return ir.WorkspaceAccessSpec(level=ir.WorkspaceAccessLevel.AUTHENTICATED)

        # persona(name1, name2, ...)
        if self.match(TokenType.PERSONA):
            self.advance()
            self.expect(TokenType.LPAREN)
            personas: list[str] = []
            personas.append(self.expect_identifier_or_keyword().value)
            while self.match(TokenType.COMMA):
                self.advance()
                personas.append(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.RPAREN)
            return ir.WorkspaceAccessSpec(
                level=ir.WorkspaceAccessLevel.PERSONA,
                allow_personas=personas,
            )

        # Default to authenticated if unrecognized
        token = self.current_token()
        raise make_parse_error(
            f"Expected 'public', 'authenticated', or 'persona(...)' but got '{token.value}'",
            self.file,
            token.line,
            token.column,
        )

    def _parse_context_selector(self) -> ir.ContextSelectorSpec:
        """
        Parse context_selector block within a workspace.

        Syntax:
            context_selector:
              entity: School
              display_field: name
              scope_field: trust
        """
        self.advance()  # consume context_selector
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        entity: str | None = None
        display_field = "name"
        scope_field: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_token = self.expect_identifier_or_keyword()
            key = key_token.value
            self.expect(TokenType.COLON)

            if key == "entity":
                entity = self.expect_identifier_or_keyword().value
            elif key == "display_field":
                display_field = self.expect_identifier_or_keyword().value
            elif key == "scope_field":
                scope_field = self.expect_identifier_or_keyword().value
            else:
                # Skip unknown keys — consume tokens until newline
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                    self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if not entity:
            token = self.current_token()
            raise make_parse_error(
                "context_selector requires 'entity:' field",
                self.file,
                token.line,
                token.column,
            )

        return ir.ContextSelectorSpec(
            entity=entity,
            display_field=display_field,
            scope_field=scope_field,
        )

    def _parse_hyphenated_identifier(self) -> str:
        """Parse an identifier that may contain hyphens (e.g. Lucide icon names like check-circle)."""
        parts = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.MINUS):
            self.advance()
            if self.match(TokenType.NUMBER):
                parts.append(self.current_token().value)
                self.advance()
            elif self.match(TokenType.IDENTIFIER):
                parts.append(self.current_token().value)
                self.advance()
            else:
                parts.append(self.expect_identifier_or_keyword().value)
        return "-".join(parts)

    def _parse_nav_group(self) -> ir.NavGroupSpec:
        """
        Parse a nav_group block within a workspace.

        Syntax:
            nav_group "Label" [icon=name] [collapsed]:
              entity_name [icon=name]
              ...
        """
        self.advance()  # consume nav_group

        # Label (required string)
        label = self.expect(TokenType.STRING).value

        # Optional inline attributes: icon=name, collapsed
        icon = None
        collapsed = False
        while not self.match(TokenType.COLON):
            if self.match(TokenType.ICON):
                self.advance()
                self.expect(TokenType.EQUALS)
                icon = self._parse_hyphenated_identifier()
            elif self.match(TokenType.COLLAPSED):
                self.advance()
                collapsed = True
            else:
                break

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        items: list[ir.NavItemIR] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            entity = self.expect_identifier_or_keyword().value
            item_icon = None

            # Optional icon=name on nav item
            if self.match(TokenType.ICON):
                self.advance()
                self.expect(TokenType.EQUALS)
                item_icon = self._parse_hyphenated_identifier()

            items.append(ir.NavItemIR(entity=entity, icon=item_icon))
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.NavGroupSpec(
            label=label,
            icon=icon,
            collapsed=collapsed,
            items=items,
        )

    def parse_workspace_region(self) -> ir.WorkspaceRegion:
        """Parse workspace region."""
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        source = None
        sources: list[str] = []
        source_filters: dict[str, ir.ConditionExpr] = {}
        filter_expr = None
        sort: list[ir.SortSpec] = []
        limit = None
        display = ir.DisplayMode.LIST
        action = None
        empty_message = None
        group_by: str | ir.BucketRef | None = None
        group_by_dims: list[str | ir.BucketRef] | None = None
        aggregates: dict[str, str] = {}
        date_field: str | None = None
        date_range: bool = False
        heatmap_rows: str | None = None
        heatmap_columns: str | None = None
        heatmap_value: str | None = None
        heatmap_thresholds: list[float] | ir.ParamRef = []
        progress_stages: list[str] = []
        progress_complete_at: str | None = None
        delta: ir.DeltaSpec | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # source: EntityName  OR  source: [Entity1, Entity2, ...]
            if self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.LBRACKET):
                    # Multi-source: source: [Entity1, Entity2, Entity3]
                    self.advance()  # consume [
                    while not self.match(TokenType.RBRACKET):
                        self.skip_newlines()
                        if self.match(TokenType.RBRACKET):
                            break
                        entity_name = self.expect_identifier_or_keyword().value
                        sources.append(entity_name)
                        if self.match(TokenType.COMMA):
                            self.advance()
                        self.skip_newlines()
                    self.expect(TokenType.RBRACKET)
                else:
                    source = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # filter_map: per-source filters for multi-source regions
            elif self.match(TokenType.FILTER_MAP):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    entity_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    source_filters[entity_name] = self.parse_condition_expr()
                    self.skip_newlines()
                self.expect(TokenType.DEDENT)

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

            # group_by: field_name        (single-dim, bar_chart)
            # group_by: [field_a, field_b] (multi-dim, pivot_table — cycle 25)
            # group_by: bucket(field, unit) or [bucket(field, unit), scalar]
            #                             (time-bucketing, line_chart — cycle 28)
            elif self.match(TokenType.GROUP_BY):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.LBRACKET):
                    self.advance()  # consume [
                    dims: list[str | ir.BucketRef] = []
                    while not self.match(TokenType.RBRACKET):
                        self.skip_newlines()
                        if self.match(TokenType.RBRACKET):
                            break
                        dims.append(self._parse_group_by_element())
                        if self.match(TokenType.COMMA):
                            self.advance()
                        self.skip_newlines()
                    self.expect(TokenType.RBRACKET)
                    group_by_dims = dims
                else:
                    group_by = self._parse_group_by_element()
                self.skip_newlines()

            # date_field: created_at
            elif self.match(TokenType.DATE_FIELD):
                self.advance()
                self.expect(TokenType.COLON)
                date_field = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # date_range (flag — no colon needed)
            elif self.match(TokenType.DATE_RANGE):
                self.advance()
                date_range = True
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

            # rows: field.path (heatmap row grouping)
            elif self.match(TokenType.ROWS):
                self.advance()
                self.expect(TokenType.COLON)
                heatmap_rows = self.expect_identifier_or_keyword().value
                while self.match(TokenType.DOT):
                    self.advance()
                    heatmap_rows += "." + self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # columns: field.path (heatmap column grouping)
            elif self.match(TokenType.COLUMNS):
                self.advance()
                self.expect(TokenType.COLON)
                heatmap_columns = self.expect_identifier_or_keyword().value
                while self.match(TokenType.DOT):
                    self.advance()
                    heatmap_columns += "." + self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # value: expression (capture as string until newline)
            elif self.match(TokenType.VALUE):
                self.advance()
                self.expect(TokenType.COLON)
                value_parts: list[str] = []
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                    value_parts.append(self.advance().value)
                heatmap_value = " ".join(value_parts)
                self.skip_newlines()

            # thresholds: param("key") OR thresholds: [0.4, 0.6]
            elif self.match(TokenType.THRESHOLDS):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.PARAM):
                    self.advance()  # consume 'param'
                    self.expect(TokenType.LPAREN)
                    ref_key = self.expect(TokenType.STRING).value
                    self.expect(TokenType.RPAREN)
                    heatmap_thresholds = ir.ParamRef(
                        key=ref_key, param_type="list[float]", default=[]
                    )
                else:
                    thresh_list: list[float] = []
                    self.expect(TokenType.LBRACKET)
                    while not self.match(TokenType.RBRACKET):
                        self.skip_newlines()
                        if self.match(TokenType.RBRACKET):
                            break
                        num_token = self.expect(TokenType.NUMBER)
                        # Handle decimal: NUMBER DOT NUMBER
                        num_str = num_token.value
                        if self.match(TokenType.DOT):
                            self.advance()
                            frac = self.expect(TokenType.NUMBER).value
                            num_str = num_str + "." + frac
                        thresh_list.append(float(num_str))
                        if self.match(TokenType.COMMA):
                            self.advance()
                        self.skip_newlines()
                    self.expect(TokenType.RBRACKET)
                    heatmap_thresholds = thresh_list
                self.skip_newlines()

            # stages: [uploaded, queued, processing, marked, reviewed, flagged]
            elif self.match(TokenType.STAGES):
                self.advance()
                self.expect(TokenType.COLON)
                self.expect(TokenType.LBRACKET)
                while not self.match(TokenType.RBRACKET):
                    self.skip_newlines()
                    if self.match(TokenType.RBRACKET):
                        break
                    progress_stages.append(self.expect_identifier_or_keyword().value)
                    if self.match(TokenType.COMMA):
                        self.advance()
                    self.skip_newlines()
                self.expect(TokenType.RBRACKET)
                self.skip_newlines()

            # complete_at: reviewed
            elif self.match(TokenType.COMPLETE_AT):
                self.advance()
                self.expect(TokenType.COLON)
                progress_complete_at = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # delta: { period: 1 day, sentiment: positive_up, field: created_at } (#884)
            elif self.match(TokenType.DELTA):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                delta = self._parse_delta_block()
                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        # v0.9.5: Allow aggregate-only regions without source
        # Traditional regions require source, but pure metric regions don't
        if source is None and not sources and not aggregates:
            token = self.current_token()
            raise make_parse_error(
                f"Workspace region '{name}' requires 'source:' or 'aggregate:' block",
                self.file,
                token.line,
                token.column,
            )

        # Cannot have both source and sources
        if source and sources:
            token = self.current_token()
            raise make_parse_error(
                f"Workspace region '{name}' cannot have both 'source:' (single) and multi-source list",
                self.file,
                token.line,
                token.column,
            )

        # Multi-source regions default to tabbed_list display
        if sources and display == ir.DisplayMode.LIST:
            display = ir.DisplayMode.TABBED_LIST

        return ir.WorkspaceRegion(
            name=name,
            source=source,
            sources=sources,
            source_filters=source_filters,
            filter=filter_expr,
            sort=sort,
            limit=limit,
            display=display,
            action=action,
            empty_message=empty_message,
            group_by=group_by,
            group_by_dims=group_by_dims,
            aggregates=aggregates,
            date_field=date_field,
            date_range=date_range,
            heatmap_rows=heatmap_rows,
            heatmap_columns=heatmap_columns,
            heatmap_value=heatmap_value,
            heatmap_thresholds=heatmap_thresholds,
            progress_stages=progress_stages,
            progress_complete_at=progress_complete_at,
            delta=delta,
        )
