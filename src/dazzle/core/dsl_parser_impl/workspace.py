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

    _REFERENCE_LINE_VALID_STYLES: frozenset[str] = frozenset(  # noqa: RUF012
        {"solid", "dashed", "dotted"}
    )
    _REFERENCE_BAND_VALID_COLORS: frozenset[str] = frozenset(  # noqa: RUF012
        {"target", "positive", "warning", "destructive", "muted"}
    )

    def _parse_reference_lines_block(self) -> list[ir.ReferenceLine]:
        """Parse a list of reference lines for line/area charts (#883).

        Syntax (one entry per line, comma-separated keys — same shape as
        ``demo`` records):

            reference_lines:
              - label: "Target (6)", value: 56, style: dashed
              - label: "Boundary",   value: 50

        ``style:`` is optional and defaults to ``solid``. Other keys raise
        a parse error so typos surface at validate time.
        """
        lines: list[ir.ReferenceLine] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "reference_lines entries must start with `- ` "
                    '(e.g. `- label: "Target", value: 56`)',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            entry = self._parse_reference_entry({"label", "value", "style"})
            if "label" not in entry or "value" not in entry:
                tok = self.current_token()
                raise make_parse_error(
                    "reference_lines entry requires both `label:` and `value:`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            style = entry.get("style", "solid")
            if style not in self._REFERENCE_LINE_VALID_STYLES:
                tok = self.current_token()
                raise make_parse_error(
                    f"reference_lines.style must be one of "
                    f"{sorted(self._REFERENCE_LINE_VALID_STYLES)}; got {style!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            lines.append(
                ir.ReferenceLine(
                    label=str(entry["label"]),
                    value=float(entry["value"]),
                    style=str(style),
                )
            )
            self.skip_newlines()
        return lines

    def _parse_reference_bands_block(self) -> list[ir.ReferenceBand]:
        """Parse a list of reference bands for line/area charts (#883).

        Syntax (one entry per line, comma-separated keys):

            reference_bands:
              - label: "Target band", from: 50, to: 56, color: target

        ``color:`` is optional and defaults to ``target``. Both ``from:``
        and ``to:`` are required. Other keys raise a parse error.
        """
        bands: list[ir.ReferenceBand] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "reference_bands entries must start with `- ` "
                    '(e.g. `- label: "Target", from: 50, to: 56`)',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            entry = self._parse_reference_entry({"label", "from", "to", "color"})
            if "label" not in entry or "from" not in entry or "to" not in entry:
                tok = self.current_token()
                raise make_parse_error(
                    "reference_bands entry requires `label:`, `from:`, and `to:`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            color = str(entry.get("color", "target"))
            if color not in self._REFERENCE_BAND_VALID_COLORS:
                tok = self.current_token()
                raise make_parse_error(
                    f"reference_bands.color must be one of "
                    f"{sorted(self._REFERENCE_BAND_VALID_COLORS)}; got {color!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            bands.append(
                ir.ReferenceBand.model_validate(
                    {
                        "label": str(entry["label"]),
                        "from": float(entry["from"]),
                        "to": float(entry["to"]),
                        "color": color,
                    }
                )
            )
            self.skip_newlines()
        return bands

    def _parse_reference_entry(self, allowed_keys: set[str]) -> dict[str, str | int | float]:
        """Parse one comma-separated `key: value` line for reference_lines/bands.

        Stops at NEWLINE / DEDENT / EOF. Raises on unknown keys so authors
        catch typos at validate time. Accepts reserved keywords (``from``,
        ``to``) as keys here — the strict identifier guard would reject
        them, but they're the natural user-facing names and the
        ``allowed_keys`` set already constrains what's legal.
        """
        entry: dict[str, str | int | float] = {}
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            key_tok = self.current_token()
            key = key_tok.value
            if key not in allowed_keys:
                raise make_parse_error(
                    f"Unknown key {key!r}. Expected one of: {sorted(allowed_keys)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)
            entry[key] = self._parse_reference_value()
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break
        return entry

    def _parse_reference_value(self) -> str | int | float:
        """Parse a single value token: STRING, NUMBER, or bare identifier/keyword."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        if self.match(TokenType.NUMBER):
            raw = self.advance().value
            try:
                return float(raw) if "." in raw else int(raw)
            except ValueError:
                return str(raw)
        return str(self.expect_identifier_or_keyword().value)

    def _parse_overlay_series_block(self) -> list[ir.OverlaySeriesSpec]:
        """Parse the indented body of an ``overlay_series:`` block (#883).

        Syntax (each entry uses YAML-style indented sub-keys — the
        leading dash carries the inline ``label:``, then an INDENT
        block holds source/filter/aggregate)::

            overlay_series:
              - label: "Cohort average"
                source: MarkingResult
                filter: assessment_objective = ao3 and tg = current_context
                aggregate: avg(scaled_mark)

        ``source:`` is optional (defaults to the parent region's source
        at runtime). ``filter:`` is optional. ``aggregate:`` is required.
        """
        series: list[ir.OverlaySeriesSpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'overlay_series entries must start with `- label: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            # Inline `label: "..."` on the dash line
            label_kw = self.expect_identifier_or_keyword().value
            if label_kw != "label":
                tok = self.current_token()
                raise make_parse_error(
                    f"overlay_series entry must start with `label:`, got {label_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            label_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            source_name: str | None = None
            filter_expr: ir.ConditionExpr | None = None
            aggregate_expr: str = ""

            # Sub-block — INDENT after the dash line carries source /
            # filter / aggregate keys.
            if self.match(TokenType.INDENT):
                self.advance()
                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    key_tok = self.current_token()
                    key = key_tok.value
                    self.advance()
                    self.expect(TokenType.COLON)
                    if key == "source":
                        source_name = self.expect_identifier_or_keyword().value
                        self.skip_newlines()
                    elif key == "filter":
                        filter_expr = self.parse_condition_expr()
                        self.skip_newlines()
                    elif key == "aggregate":
                        # Capture as joined token string until newline —
                        # same shape as the region-level `aggregate:` parser.
                        parts: list[str] = []
                        while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                            parts.append(self.advance().value)
                        aggregate_expr = " ".join(parts)
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown overlay_series key {key!r}. "
                            f"Expected one of: source, filter, aggregate.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            if not aggregate_expr:
                tok = self.current_token()
                raise make_parse_error(
                    f"overlay_series entry {label_str!r} requires `aggregate:`",
                    self.file,
                    tok.line,
                    tok.column,
                )

            series.append(
                ir.OverlaySeriesSpec(
                    label=label_str,
                    source=source_name,
                    filter=filter_expr,
                    aggregate_expr=aggregate_expr,
                )
            )
        return series

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
        reference_lines: list[ir.ReferenceLine] = []
        reference_bands: list[ir.ReferenceBand] = []
        bin_count: int | None = None  # None = "auto" (Sturges) when display=histogram
        show_outliers: bool = True  # box plot toggle (#881)
        bullet_label: str | None = None  # bullet chart label column (#880)
        bullet_actual: str | None = None  # bullet chart actual-value column (#880)
        bullet_target: str | None = None  # bullet chart target column (#880)
        overlay_series: list[ir.OverlaySeriesSpec] = []  # line/area overlay series (#883)
        css_class: str | None = None  # region wrapper CSS class hook (#894)

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

            # reference_lines / reference_bands — line/area chart overlays (#883)
            elif self.match(TokenType.REFERENCE_LINES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                reference_lines = self._parse_reference_lines_block()
                self.expect(TokenType.DEDENT)

            elif self.match(TokenType.REFERENCE_BANDS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                reference_bands = self._parse_reference_bands_block()
                self.expect(TokenType.DEDENT)

            # bullet_label / bullet_actual / bullet_target — bullet chart
            # row column references (#880). Each names a column on the source
            # entity that the bullet template reads off every item.
            elif self.match(TokenType.BULLET_LABEL):
                self.advance()
                self.expect(TokenType.COLON)
                bullet_label = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.BULLET_ACTUAL):
                self.advance()
                self.expect(TokenType.COLON)
                bullet_actual = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.BULLET_TARGET):
                self.advance()
                self.expect(TokenType.COLON)
                bullet_target = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # class: <css-class-string> — project CSS hook on the region's
            # outer wrapper (#894). Pure presentation; no data semantics.
            # Accepts a quoted string OR a bare identifier (single class
            # name). Multiple classes via the quoted-string form
            # (`class: "metrics-strip dense"`).
            elif self.match(TokenType.CSS_CLASS):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.STRING):
                    css_class = self.advance().value
                else:
                    css_class = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # overlay_series: indented dash-list of {label, source?,
            # filter?, aggregate} entries — additional line/area chart
            # series with their own scope (#883).
            elif self.match(TokenType.OVERLAY_SERIES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                overlay_series = self._parse_overlay_series_block()
                self.expect(TokenType.DEDENT)

            # show_outliers: true|false  — box plot outlier toggle (#881)
            elif self.match(TokenType.SHOW_OUTLIERS):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    show_outliers = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    show_outliers = False
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"show_outliers must be true or false; got {token.value!r}",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # bins: auto | <int>  — histogram bin count (#882)
            elif self.match(TokenType.BINS):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.NUMBER):
                    bin_count = int(self.advance().value)
                    if bin_count < 1:
                        token = self.current_token()
                        raise make_parse_error(
                            f"bins must be a positive integer or 'auto'; got {bin_count}",
                            self.file,
                            token.line,
                            token.column,
                        )
                else:
                    word_tok = self.expect_identifier_or_keyword()
                    if word_tok.value != "auto":
                        raise make_parse_error(
                            f"bins must be 'auto' or a positive integer; got {word_tok.value!r}",
                            self.file,
                            word_tok.line,
                            word_tok.column,
                        )
                    bin_count = None  # auto via Sturges
                self.skip_newlines()

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
            reference_lines=reference_lines,
            reference_bands=reference_bands,
            bin_count=bin_count,
            show_outliers=show_outliers,
            bullet_label=bullet_label,
            bullet_actual=bullet_actual,
            bullet_target=bullet_target,
            overlay_series=overlay_series,
            css_class=css_class,
        )
