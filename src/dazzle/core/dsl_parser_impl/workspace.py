"""
Workspace parsing for DAZZLE DSL.

This mixin is composed into Parser via
src/dazzle/core/dsl_parser_impl/__init__.py — do not instantiate it
directly. Parsed `WorkspaceSpec` objects are defined in
src/dazzle/core/ir/workspaces.py and rendered by
src/dazzle/back/runtime/workspace_rendering.py (and its extracted
siblings in back/runtime/workspace_*.py).

Handles workspace declarations including regions, aggregates, and display modes.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from ._refresh import parse_refresh_interval_seconds
from .dispatch import KeywordParser, parse_block_with_dispatch

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
        parse_aggregate_ref: Any
        peek_is_aggregate_call: Any
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
                    value=self._coerce_reference_float(entry, "value", "reference_lines"),
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
                        "from": self._coerce_reference_float(entry, "from", "reference_bands"),
                        "to": self._coerce_reference_float(entry, "to", "reference_bands"),
                        "color": color,
                    }
                )
            )
            self.skip_newlines()
        return bands

    def _coerce_reference_float(
        self: _Self,
        entry: dict[str, Any],
        key: str,
        context: str,
    ) -> float:
        """Coerce an entry value to ``float`` with a parser-friendly error.

        ``_parse_reference_entry`` returns ``str | int | float`` — the
        plain ``float()`` cast crashes with ``ValueError`` when the
        parser is fed garbage (e.g. fuzz mutation puts the literal
        string ``"color"`` where a number is expected). This wrapper
        re-raises as a :class:`ParseError` so the fuzz invariant
        ("parser must never raise non-ParseErrors") holds and authors
        get a useful "<key>: must be a number" message instead of a
        traceback into a private helper.
        """
        raw = entry.get(key)
        try:
            return float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            tok = self.current_token()
            raise make_parse_error(
                f"{context}.{key} must be a number; got {raw!r}",
                self.file,
                tok.line,
                tok.column,
            ) from None

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

    def _parse_pipeline_stages_block(self) -> list[ir.PipelineStageSpec]:
        """Parse the indented body of a pipeline_steps ``stages:`` block (#890).

        Refactored to extract one helper per stage entry, leaving the
        outer block as a thin dash-list loop.

        Same dash-list shape as ``actions:``. Each entry leads with
        ``label:`` and carries optional ``caption:`` + ``value:``::

            stages:
              - label: "Scanned"
                caption: "complete pupil scripts"
                value: count(Manuscript where status = uploaded)
              - label: "Reviewed"
                caption: "manual triage"
                value: "Daily 02:00 UTC"

        v0.61.66 (AegisMark UX patterns #4): the ``value:`` key accepts
        either an aggregate expression (same vocabulary as region-level
        ``aggregate:``) OR a quoted literal string. Per ADR-0024 the
        parser shape-detects at parse time — :meth:`peek_is_aggregate_call`
        routes aggregate-shaped tokens through :meth:`parse_aggregate_ref`,
        otherwise the payload is captured as a literal string.
        v0.61.78 (#911): ``progress:`` shares the same acceptor —
        literal numeric or aggregate expression.

        Distinct from the legacy ``stages: [a, b, c]`` bracketed list
        used by ``progress`` mode — the calling parser branch shape-
        detects on the next token (LBRACKET → progress, INDENT →
        pipeline_steps).
        """
        stages: list[ir.PipelineStageSpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            stages.append(self._parse_pipeline_stage_entry())
        return stages

    def _parse_pipeline_stage_entry(self) -> ir.PipelineStageSpec:
        """Parse one ``- label: "..." [caption/value/progress: ...]`` entry."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                'pipeline stages entries must start with `- label: "..."`',
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()  # consume `-`
        label_str = self._parse_pipeline_stage_label()
        caption_str, value_payload, progress_payload = self._parse_pipeline_stage_kv_block()
        return ir.PipelineStageSpec(
            label=label_str,
            caption=caption_str,
            value=value_payload,
            progress=progress_payload,
        )

    def _parse_pipeline_stage_label(self) -> str:
        """Consume ``label: "<str>"`` — the required first key after the dash."""
        label_kw = self.expect_identifier_or_keyword().value
        if label_kw != "label":
            tok = self.current_token()
            raise make_parse_error(
                f"pipeline stages entry must start with `label:`, got {label_kw!r}",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.COLON)
        label_str: str = self.expect(TokenType.STRING).value
        self.skip_newlines()
        return label_str

    def _parse_pipeline_stage_kv_block(
        self,
    ) -> tuple[str, "ir.AggregateRef | str | None", "ir.AggregateRef | str | None"]:
        """Consume the optional indented ``caption/value/progress`` continuation.

        Returns ``(caption, value, progress)`` where ``value`` /
        ``progress`` are either an :class:`AggregateRef` (when the
        payload tokens form an aggregate call), a literal string (quoted
        literal or non-aggregate token sequence), or ``None`` when omitted.
        """
        caption_str = ""
        value_payload: ir.AggregateRef | str | None = None
        progress_payload: ir.AggregateRef | str | None = None
        if not self.match(TokenType.INDENT):
            return caption_str, value_payload, progress_payload
        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "caption":
                caption_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key in ("value", "progress"):
                payload = self._parse_pipeline_stage_payload()
                if key == "value":
                    value_payload = payload
                else:
                    progress_payload = payload
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown pipeline stages key {key!r}. "
                    f"Expected one of: caption, value, progress.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
        self.expect(TokenType.DEDENT)
        return caption_str, value_payload, progress_payload

    def _parse_pipeline_stage_payload(self) -> "ir.AggregateRef | str":
        """Consume a quoted literal OR unquoted aggregate expression.

        Three shapes:
          - **Quoted literal** (``"Daily 02:00 UTC"``) — returned as a
            ``str``, rendered verbatim by the template.
          - **Aggregate call** (``count(Task where ...)``) — returned as
            a typed :class:`AggregateRef` via :meth:`parse_aggregate_ref`
            (ADR-0024). Detected by shape-peeking on the token stream.
          - **Bare literal token sequence** (``"74"`` as a number, or
            an unquoted descriptive string) — joined with spaces and
            returned as a ``str``.
        """
        if self.match(TokenType.STRING):
            literal_str: str = self.advance().value
            return literal_str
        if self.peek_is_aggregate_call():
            agg_ref: ir.AggregateRef = self.parse_aggregate_ref()
            return agg_ref
        # Bare token sequence — captured as a literal string. Templates
        # render numeric values like "74" verbatim.
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
            parts.append(self.advance().value)
        return " ".join(parts)

    def _parse_profile_stats_block(self) -> list[ir.ProfileCardStatSpec]:
        """Parse the indented body of a profile_card ``stats:`` block (#892).

        Same dash-list shape as ``actions:``. Each entry leads with
        ``label:`` and carries one ``value:`` field reference::

            stats:
              - label: "Target"
                value: target_grade
              - label: "Projected"
                value: projected_grade
        """
        stats: list[ir.ProfileCardStatSpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'stats entries must start with `- label: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()
            label_kw = self.expect_identifier_or_keyword().value
            if label_kw != "label":
                tok = self.current_token()
                raise make_parse_error(
                    f"stats entry must start with `label:`, got {label_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            label_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            value_str = ""
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
                    if key == "value":
                        # Value is a field name or dotted path —
                        # capture as joined identifier-stream.
                        parts: list[str] = []
                        while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                            parts.append(self.advance().value)
                        value_str = "".join(parts)
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown stats key {key!r}. Expected: value.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)
            stats.append(ir.ProfileCardStatSpec(label=label_str, value=value_str))
        return stats

    def _parse_facts_block(self) -> list[str]:
        """Parse the indented body of a profile_card ``facts:`` block (#892).

        Each entry is a single quoted string supporting `{{ field }}`
        interpolation (resolved at runtime, not here)::

            facts:
              - "Tutor: {{ tutor.full_name }}"
              - "EAL: {{ eal_status }}"
        """
        facts: list[str] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "facts entries must be quoted strings led by `- `",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()
            facts.append(self.expect(TokenType.STRING).value)
            self.skip_newlines()
        return facts

    def _parse_action_cards_block(self) -> list[ir.ActionCardSpec]:
        """Parse the indented body of an ``actions:`` block (#891).

        Refactored to per-entry helper extraction. Outer loop drives the
        dash-list; ``_parse_action_card_entry`` consumes one entry.

        Syntax (each entry uses the same dash-list shape as
        ``overlay_series:`` — leading dash carries the inline ``label:``,
        then an INDENT block holds icon/count_aggregate/action/tone)::

            actions:
              - label: "Generate notes"
                icon: "file-text"
                count_aggregate: count(StudentProfile where pending = true)
                action: notes_create
                tone: positive

        Only ``label:`` is required. ``tone:`` defaults to ``neutral``.
        """
        cards: list[ir.ActionCardSpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            cards.append(self._parse_action_card_entry())
        return cards

    def _parse_action_card_entry(self) -> ir.ActionCardSpec:
        """Parse one ``- label: "..."`` action-card entry + its kv block."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                'actions entries must start with `- label: "..."`',
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()  # consume MINUS
        label_str = self._parse_dash_required_label("actions")
        icon_str, count_ref, action_str, tone_str = self._parse_action_card_kv_block(label_str)
        return ir.ActionCardSpec(
            label=label_str,
            icon=icon_str,
            count=count_ref,
            action=action_str,
            tone=tone_str,
        )

    def _parse_action_card_kv_block(
        self, label_str: str
    ) -> tuple[str, ir.AggregateRef | None, str, str]:
        """Consume the optional indented icon/count_aggregate/action/tone block.

        Returns ``(icon, count_ref, action, tone)`` — empty strings
        (or ``"neutral"`` for tone, ``None`` for count) when omitted.
        The ``count_aggregate:`` DSL key parses through
        :meth:`parse_aggregate_ref` (ADR-0024) into a typed
        :class:`AggregateRef`.
        """
        valid_tones = {"positive", "warning", "destructive", "neutral", "accent"}
        valid_keys = {"label", "icon", "count_aggregate", "action", "tone"}

        icon_str = ""
        count_ref: ir.AggregateRef | None = None
        action_str = ""
        tone_str = "neutral"

        if not self.match(TokenType.INDENT):
            return icon_str, count_ref, action_str, tone_str
        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "icon":
                icon_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "count_aggregate":
                count_ref = self.parse_aggregate_ref()
                self.skip_newlines()
            elif key == "action":
                # STRING (URL with `/`, `?`, `=`) OR IDENT (bare surface name).
                if self.match(TokenType.STRING):
                    action_str = self.advance().value
                else:
                    action_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "tone":
                tone_val = self.expect_identifier_or_keyword().value
                if tone_val not in valid_tones:
                    raise make_parse_error(
                        f"actions entry {label_str!r}: tone must be one of "
                        f"{sorted(valid_tones)}; got {tone_val!r}",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
                tone_str = tone_val
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown actions key {key!r}. Expected one of: {sorted(valid_keys)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
        self.expect(TokenType.DEDENT)
        return icon_str, count_ref, action_str, tone_str

    def _parse_dash_required_label(self, block_name: str) -> str:
        """Common helper: consume the required ``label: "<str>"`` first key.

        Shared across dash-list parsers (actions, overlay_series, etc.) —
        each entry's first key must be ``label``.
        """
        label_kw = self.expect_identifier_or_keyword().value
        if label_kw != "label":
            tok = self.current_token()
            raise make_parse_error(
                f"{block_name} entry must start with `label:`, got {label_kw!r}",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.COLON)
        label_str: str = self.expect(TokenType.STRING).value
        self.skip_newlines()
        return label_str

    def _parse_cohort_strip_config_block(self) -> ir.CohortStripConfig:
        """Parse the indented body of a ``cohort_strip_config:`` block (#1018).

        Syntax::

            cohort_strip_config:
              member_via: profile
              default_lens: status
              lenses:
                - id: status
                  label: Status
                  primary: status
                - id: response
                  label: "Response time"
                  primary: response_time_ms
                  threshold: 500

        ``member_via`` and ``lenses`` are required (the empty case is a
        config error — runtime degrades to "not configured" but we
        catch it here so the IR shape is honest). ``default_lens`` is
        optional; runtime defaults to the first declared lens id.
        """
        member_via_str: str | None = None
        default_lens_str: str = ""
        lenses: list[ir.CohortStripLens] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)

            if key == "member_via":
                # Field on source resolving to the member's profile entity.
                member_via_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif key == "default_lens":
                default_lens_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif key == "lenses":
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                lenses = self._parse_cohort_strip_lenses_block()
                self.expect(TokenType.DEDENT)

            else:
                raise make_parse_error(
                    f"Unknown cohort_strip_config key {key!r}. "
                    "Expected one of: member_via, default_lens, lenses.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        if member_via_str is None:
            tok = self.current_token()
            raise make_parse_error(
                "cohort_strip_config requires `member_via:` (field on source "
                "resolving to the member's profile entity).",
                self.file,
                tok.line,
                tok.column,
            )
        if not lenses:
            tok = self.current_token()
            raise make_parse_error(
                "cohort_strip_config requires at least one lens. Add a "
                "`lenses:` block with one or more dash-list entries.",
                self.file,
                tok.line,
                tok.column,
            )
        # Validate default_lens (when set) refers to a declared lens.
        if default_lens_str:
            declared_ids = {lens.id for lens in lenses}
            if default_lens_str not in declared_ids:
                tok = self.current_token()
                raise make_parse_error(
                    f"cohort_strip_config default_lens={default_lens_str!r} "
                    f"is not one of the declared lens ids "
                    f"({sorted(declared_ids)}).",
                    self.file,
                    tok.line,
                    tok.column,
                )
        return ir.CohortStripConfig(
            member_via=member_via_str,
            lenses=lenses,
            default_lens=default_lens_str,
        )

    def _parse_primary_aggregate_block(self) -> ir.LensAggregatePrimary:
        """#1144 part 3 phase 1: parse the indented body of a
        ``primary_aggregate:`` block.

        Syntax (ADR-0024 typed form)::

            primary_aggregate:
              aggregate: avg(MarkingResult.score where latest_for_event = true)
              via: ClassEnrolment(student_profile = id)

        ``aggregate:`` is required and parsed structurally via
        :meth:`parse_aggregate_ref` into a typed :class:`AggregateRef`
        — any row-level predicate rides inside the aggregate's own
        ``where:`` clause. ``via:`` is optional and reuses the
        junction-binding grammar from scope rules (#530).
        """
        _VALID_KEYS = {"aggregate", "via", "share", "format"}
        aggregate_ref: ir.AggregateRef | None = None
        via_cond: ir.ViaCondition | None = None
        share_entity: str | None = None
        share_tok = None
        format_spec: str = ""
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            if key not in _VALID_KEYS:
                raise make_parse_error(
                    f"Unknown primary_aggregate key {key!r}. "
                    f"Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)
            if key == "aggregate":
                aggregate_ref = self.parse_aggregate_ref()
                self.skip_newlines()
            elif key == "format":
                # #1300: per-lens render format for the aggregate value
                # (mirrors bar_track's `track_format:`). String literal.
                format_spec = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()
            elif key == "share":
                # #1216: shared-parent JOIN. The cohort source row and
                # the aggregated entity both reference the named pivot
                # entity. Mutually exclusive with `via:`.
                share_tok = self.expect_identifier_or_keyword()
                share_entity = str(share_tok.value)
                self.skip_newlines()
            else:  # via
                # Reuse the scope-rule via-binding grammar shape:
                # `JunctionEntity(field = expr, ...)`. The helpers
                # live on EntityParserMixin; both mixins compose
                # into the same parser class at runtime, so the
                # attr-defined ignores reflect mypy's mixin-aware
                # limitation, not a real attribute gap.
                # NOTE: skip `_validate_via_bindings` — that
                # validator enforces a `current_user` binding for
                # scope semantics, which doesn't apply to aggregate
                # joins (the join binds the member row to the
                # junction, not the current user).
                junction_entity = self._parse_via_junction_name()  # type: ignore[attr-defined]
                self._expect_via_lparen(junction_entity)  # type: ignore[attr-defined]
                bindings = self._parse_via_bindings()  # type: ignore[attr-defined]
                self.expect(TokenType.RPAREN)
                via_cond = ir.ViaCondition(junction_entity=junction_entity, bindings=bindings)
                self.skip_newlines()
        if aggregate_ref is None:
            tok = self.current_token()
            raise make_parse_error(
                "primary_aggregate requires an `aggregate:` expression",
                self.file,
                tok.line,
                tok.column,
            )
        if via_cond is not None and share_entity is not None and share_tok is not None:
            # via: (true-junction) and share: (shared-parent) are
            # different operations — refuse rather than guess intent.
            raise make_parse_error(
                "primary_aggregate cannot combine `via:` and `share:`. "
                "Use `via:` for true junction tables (junction has direct FK to "
                "aggregated entity), `share:` for the shared-parent shape "
                "(cohort row and aggregated row both reference the named pivot).",
                self.file,
                share_tok.line,
                share_tok.column,
            )
        return ir.LensAggregatePrimary(
            aggregate=aggregate_ref, via=via_cond, share=share_entity, format=format_spec
        )

    def _parse_primary_composite_block(self) -> ir.CompositePrimarySpec:
        """#1144 part 2: parse the indented body of a
        ``primary_composite:`` block.

        Syntax::

            primary_composite:
              separator: " / "
              parts:
                - field: ao1_score
                - field: ao2_score
                  tone: positive
                - field: ao3_score

        ``parts:`` is required and must be non-empty; the IR
        validator enforces. ``separator:`` defaults to ``" / "``.
        """
        _VALID_KEYS = {"separator", "parts"}
        separator = " / "
        parts: list[ir.CompositePrimaryPart] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            if key not in _VALID_KEYS:
                raise make_parse_error(
                    f"Unknown primary_composite key {key!r}. "
                    f"Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)
            if key == "separator":
                separator = self.expect(TokenType.STRING).value
                self.skip_newlines()
            else:  # parts
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                parts = self._parse_composite_parts_block()
                self.expect(TokenType.DEDENT)
        if not parts:
            tok = self.current_token()
            raise make_parse_error(
                "primary_composite requires a non-empty `parts:` list",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.CompositePrimarySpec(parts=parts, separator=separator)

    def _parse_composite_parts_block(self) -> list[ir.CompositePrimaryPart]:
        """#1144 part 2: parse the dash-list body of a
        ``primary_composite.parts:`` block. Each entry leads with
        ``- field: <ident>`` and may carry an optional ``tone:``
        sub-key.
        """
        parts: list[ir.CompositePrimaryPart] = []
        _VALID_KEYS = {"field", "tone"}
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "primary_composite parts entries must start with `- field: <name>`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            head_kw = self.expect_identifier_or_keyword().value
            if head_kw != "field":
                tok = self.current_token()
                raise make_parse_error(
                    f"parts entry must start with `field:`, got {head_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            field_val = self.expect_identifier_or_keyword().value
            self.skip_newlines()
            tone_val = ""
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
                    if key == "tone":
                        tone_val = self.expect_identifier_or_keyword().value
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown parts entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)
            parts.append(ir.CompositePrimaryPart(field=field_val, tone=tone_val))
        return parts

    def _parse_tone_bands_block(self) -> list[ir.ToneBandSpec]:
        """#1144 part 1: parse the indented dash-list body of a
        ``tone_bands:`` block.

        Each entry leads with ``- at: <number>`` carrying the threshold
        value, then a ``tone:`` sub-key on the same line or in an
        INDENT block::

            tone_bands:
              - at: 90
                tone: good
              - at: 70
                tone: warn
              - at: 0
                tone: bad

        Caller validates that ``threshold:`` and ``tone_bands:`` aren't
        both set on the same lens — the IR-level validator raises a
        clear error message on conflict.
        """
        bands: list[ir.ToneBandSpec] = []
        _VALID_KEYS = {"at", "tone"}
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "tone_bands entries must start with `- at: <number>`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            head_kw = self.expect_identifier_or_keyword().value
            if head_kw != "at":
                tok = self.current_token()
                raise make_parse_error(
                    f"tone_bands entry must start with `at:`, got {head_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            at_val = float(self.expect(TokenType.NUMBER).value)
            self.skip_newlines()
            tone_str: str | None = None
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
                    if key == "tone":
                        tone_str = self.expect_identifier_or_keyword().value
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown tone_bands entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)
            if tone_str is None:
                tok = self.current_token()
                raise make_parse_error(
                    f"tone_bands entry at:{at_val} requires a `tone:` field",
                    self.file,
                    tok.line,
                    tok.column,
                )
            bands.append(ir.ToneBandSpec(at=at_val, tone=tone_str))
        return bands

    def _parse_cohort_strip_lenses_block(self) -> list[ir.CohortStripLens]:
        """Parse the indented dash-list body of a ``lenses:`` block (#1018).

        Each entry must lead with ``- id:`` (the stable lens identifier
        used in URL params). The remaining keys land in the entry's
        INDENT block. ``label`` is required; the lens must declare
        either ``primary:`` (scalar) or ``primary_composite:`` (tuple
        display, #1144 part 2). ``threshold`` and ``tone_bands`` are
        optional and mutually exclusive (#1144 part 1).
        """
        lenses: list[ir.CohortStripLens] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "lenses entries must start with `- id: <lens-id>`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            id_kw = self.expect_identifier_or_keyword().value
            if id_kw != "id":
                tok = self.current_token()
                raise make_parse_error(
                    f"lenses entry must start with `id:`, got {id_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            id_str = self.expect_identifier_or_keyword().value
            self.skip_newlines()
            lenses.append(self._parse_cohort_strip_lens_entry_body(id_str))
        return lenses

    def _parse_cohort_strip_lens_entry_body(self, id_str: str) -> ir.CohortStripLens:
        """Parse the INDENT-block body of one ``lenses:`` entry.

        Extracted from :meth:`_parse_cohort_strip_lenses_block` so the
        outer dispatch loop stays within the per-function line cap.
        Handles ``label`` / ``primary`` / ``threshold`` / ``tone_bands``
        / ``primary_composite`` keys; validates the required-fields
        and mutex contracts at the end.
        """
        _VALID_KEYS = {
            "id",
            "label",
            "primary",
            "threshold",
            "tone_bands",
            "primary_composite",
            "primary_aggregate",
        }
        label_str: str | None = None
        primary_str: str | None = None
        threshold_val: float | None = None
        tone_bands_list: list[ir.ToneBandSpec] = []
        primary_composite: ir.CompositePrimarySpec | None = None
        primary_aggregate: ir.LensAggregatePrimary | None = None

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
                if key == "label":
                    # Quoted preferred (handles spaces, punctuation);
                    # bare identifier accepted for single-word labels.
                    if self.match(TokenType.STRING):
                        label_str = self.advance().value
                    else:
                        label_str = self.expect_identifier_or_keyword().value
                    self.skip_newlines()
                elif key == "primary":
                    primary_str = self.expect_identifier_or_keyword().value
                    self.skip_newlines()
                elif key == "threshold":
                    threshold_val = float(self.expect(TokenType.NUMBER).value)
                    self.skip_newlines()
                elif key == "tone_bands":
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    tone_bands_list = self._parse_tone_bands_block()
                    self.expect(TokenType.DEDENT)
                elif key == "primary_composite":
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    primary_composite = self._parse_primary_composite_block()
                    self.expect(TokenType.DEDENT)
                elif key == "primary_aggregate":
                    # #1144 part 3: aggregate-expression primary. IR
                    # + parser shipped here; runtime execution lands
                    # in subsequent slices.
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    primary_aggregate = self._parse_primary_aggregate_block()
                    self.expect(TokenType.DEDENT)
                else:
                    raise make_parse_error(
                        f"Unknown lenses key {key!r}. Expected one of: {sorted(_VALID_KEYS)}.",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
            self.expect(TokenType.DEDENT)

        if label_str is None:
            tok = self.current_token()
            raise make_parse_error(
                f"lens {id_str!r} requires a `label:` field",
                self.file,
                tok.line,
                tok.column,
            )
        if primary_str is None and primary_composite is None and primary_aggregate is None:
            tok = self.current_token()
            raise make_parse_error(
                f"lens {id_str!r} requires exactly one of `primary:` "
                "(scalar), `primary_composite:` (tuple display), or "
                "`primary_aggregate:` (cross-join aggregate)",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.CohortStripLens(
            id=id_str,
            label=label_str,
            primary=primary_str or "",
            threshold=threshold_val,
            tone_bands=tone_bands_list,
            primary_composite=primary_composite,
            primary_aggregate=primary_aggregate,
        )

    def _parse_day_timeline_config_block(self) -> ir.DayTimelineConfig:
        """Parse the indented body of a ``day_timeline_config:`` block (#1016).

        Syntax::

            day_timeline_config:
              starts_at: period_start
              ends_at: period_end
              card: lesson_card

        ``starts_at`` and ``ends_at`` are required (the runtime
        compares ``now`` against [starts_at, ends_at] to find the
        active slot — both ends must be named). ``card`` is the
        composite-card template name and is optional; runtime uses
        a minimal default body when omitted.
        """
        starts_at_str: str | None = None
        ends_at_str: str | None = None
        card_str: str = ""
        as_of_str: str = ""
        _VALID_KEYS = {"starts_at", "ends_at", "card", "as_of"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)

            if key == "starts_at":
                starts_at_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "ends_at":
                ends_at_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "card":
                card_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "as_of":
                # #1146 part 2: date anchor for HH:MM timetables.
                # Bare identifier — either the literal `today` or a
                # row field name holding the date component.
                as_of_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown day_timeline_config key {key!r}. "
                    f"Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        if starts_at_str is None or ends_at_str is None:
            tok = self.current_token()
            raise make_parse_error(
                "day_timeline_config requires both `starts_at:` and "
                "`ends_at:` (the runtime compares now against the slot's "
                "[starts_at, ends_at] window to find the active slot).",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.DayTimelineConfig(
            starts_at=starts_at_str,
            ends_at=ends_at_str,
            card=card_str,
            as_of=as_of_str,
        )

    def _parse_task_inbox_config_block(self) -> ir.TaskInboxConfig:
        """Parse the indented body of a ``task_inbox_config:`` block (#1015).

        Syntax::

            task_inbox_config:
              empty_state: "All caught up."
              order: [urgency, deadline]
              sources:
                - source: AssessmentEvent
                  filter: state = "due_today"
                  as_task:
                    icon: register
                    title: "Register {class.name}"
                    meta: "{period.label}"
                - source: ManuscriptFeedback
                  filter: state = "ready_for_review"
                  count_as: "manuscripts ready to review"

        ``sources`` is required (the inbox needs at least one
        contributing source). Each source must declare exactly one
        of ``as_task`` (per-row task template) or ``count_as``
        (collapsed-summary chip) — the mutex is enforced at parse
        time so the runtime adapter sees a clean shape.
        """
        empty_state_str: str | None = None
        order_keys: list[str] = []
        sources: list[ir.TaskSource] = []
        _VALID_KEYS = {"empty_state", "order", "sources"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)

            if key == "empty_state":
                empty_state_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "order":
                # Bracketed list of bare identifiers: [urgency, deadline]
                self.expect(TokenType.LBRACKET)
                while not self.match(TokenType.RBRACKET):
                    order_keys.append(self.expect_identifier_or_keyword().value)
                    if self.match(TokenType.COMMA):
                        self.advance()
                self.expect(TokenType.RBRACKET)
                self.skip_newlines()
            elif key == "sources":
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                sources = self._parse_task_inbox_sources_block()
                self.expect(TokenType.DEDENT)
            else:
                raise make_parse_error(
                    f"Unknown task_inbox_config key {key!r}. "
                    f"Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        if not sources:
            tok = self.current_token()
            raise make_parse_error(
                "task_inbox_config requires at least one source. Add a "
                "`sources:` block with one or more dash-list entries.",
                self.file,
                tok.line,
                tok.column,
            )
        # Build kwargs only including overrides — preserves the
        # config-level defaults (`order=["urgency","deadline"]`,
        # `empty_state="All caught up."`) when the DSL omits them.
        kwargs: dict[str, Any] = {"sources": sources}
        if order_keys:
            kwargs["order"] = order_keys
        if empty_state_str is not None:
            kwargs["empty_state"] = empty_state_str
        return ir.TaskInboxConfig(**kwargs)

    def _parse_task_inbox_sources_block(self) -> list[ir.TaskSource]:
        """Parse the indented dash-list body of a ``sources:`` block (#1015).

        Refactored to per-entry helper extraction. Outer loop drives the
        dash-list; ``_parse_task_inbox_source_entry`` consumes one entry.

        Each entry leads with ``- source: <EntityName>``; the rest of
        the entry's keys land in its INDENT block. Exactly one of
        ``as_task`` (nested template block) or ``count_as`` (string)
        must be set per entry.
        """
        sources: list[ir.TaskSource] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            sources.append(self._parse_task_inbox_source_entry())
        return sources

    def _parse_task_inbox_source_entry(self) -> ir.TaskSource:
        """Parse one ``- source: EntityName`` entry + its kv block + mutex check."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                "sources entries must start with `- source: <EntityName>`",
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()  # consume MINUS
        source_str = self._parse_task_inbox_source_head()
        filter_expr, as_task, count_as_str = self._parse_task_inbox_source_kv_block()
        self._validate_task_inbox_source_mutex(source_str, as_task, count_as_str)
        return ir.TaskSource(
            source=source_str,
            filter=filter_expr,
            as_task=as_task,
            count_as=count_as_str,
        )

    def _parse_task_inbox_source_head(self) -> str:
        """Consume the required ``source: <EntityName>`` first key after the dash."""
        head_kw = self.expect_identifier_or_keyword().value
        if head_kw != "source":
            tok = self.current_token()
            raise make_parse_error(
                f"sources entry must start with `source:`, got {head_kw!r}",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.COLON)
        source_str: str = self.expect_identifier_or_keyword().value
        self.skip_newlines()
        return source_str

    def _parse_task_inbox_source_kv_block(
        self,
    ) -> tuple["ir.ConditionExpr | None", "ir.TaskSourceTemplate | None", str]:
        """Consume the optional indented filter / as_task / count_as block."""
        valid_keys = {"source", "filter", "as_task", "count_as"}
        filter_expr: ir.ConditionExpr | None = None
        as_task: ir.TaskSourceTemplate | None = None
        count_as_str: str = ""

        if not self.match(TokenType.INDENT):
            return filter_expr, as_task, count_as_str
        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "filter":
                filter_expr = self.parse_condition_expr()
                self.skip_newlines()
            elif key == "as_task":
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                as_task = self._parse_task_source_template_block()
                self.expect(TokenType.DEDENT)
            elif key == "count_as":
                count_as_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown sources entry key {key!r}. Expected one of: {sorted(valid_keys)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
        self.expect(TokenType.DEDENT)
        return filter_expr, as_task, count_as_str

    def _validate_task_inbox_source_mutex(
        self,
        source_str: str,
        as_task: "ir.TaskSourceTemplate | None",
        count_as_str: str,
    ) -> None:
        """Enforce the as_task XOR count_as mutex on each sources entry."""
        if as_task is None and not count_as_str:
            tok = self.current_token()
            raise make_parse_error(
                f"sources entry source={source_str!r} requires exactly "
                "one of `as_task:` (per-row template) or `count_as:` "
                "(collapsed-summary chip).",
                self.file,
                tok.line,
                tok.column,
            )
        if as_task is not None and count_as_str:
            tok = self.current_token()
            raise make_parse_error(
                f"sources entry source={source_str!r}: `as_task:` and "
                "`count_as:` are mutually exclusive.",
                self.file,
                tok.line,
                tok.column,
            )

    def _parse_task_source_template_block(self) -> ir.TaskSourceTemplate:
        """Parse a per-row ``as_task:`` template block (#1015).

        Three string keys: ``icon`` (icon-token identifier),
        ``title`` (template string with ``{field}`` placeholders),
        ``meta`` (template string, optional).
        """
        icon_str: str = ""
        title_str: str = ""
        meta_str: str = ""
        via_joins: dict[str, str] = {}
        _VALID_KEYS = {"icon", "title", "meta", "via"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "icon":
                # Accept STRING (lucide-style names with hyphens are
                # not valid identifiers — `alert-triangle` etc.) or
                # bare identifier (`register`, `pupil`).
                if self.match(TokenType.STRING):
                    icon_str = self.advance().value
                else:
                    icon_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "title":
                # Always a template string (placeholders need quoting).
                title_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "meta":
                meta_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "via":
                # #1145 part 2: alias → dotted-path map. Indented
                # `alias: dotted.path` lines, no string quoting (paths
                # are bare identifier chains, same shape as scope
                # field refs).
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    alias = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    path_parts: list[str] = [self.expect_identifier_or_keyword().value]
                    while self.match(TokenType.DOT):
                        self.advance()
                        path_parts.append(self.expect_identifier_or_keyword().value)
                    via_joins[alias] = ".".join(path_parts)
                    self.skip_newlines()
                self.expect(TokenType.DEDENT)
            else:
                raise make_parse_error(
                    f"Unknown as_task key {key!r}. Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        if not icon_str or not title_str:
            tok = self.current_token()
            raise make_parse_error(
                "as_task template requires both `icon:` and `title:`.",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.TaskSourceTemplate(
            icon=icon_str, title=title_str, meta=meta_str, via_joins=via_joins
        )

    def _parse_entity_card_config_block(self) -> ir.EntityCardConfig:
        """Parse the indented body of an ``entity_card_config:`` block (#1017).

        Syntax::

            entity_card_config:
              scope_param: pupil_id
              sections:
                - name: halo
                  mode: halo
                  fields: [name, year, photo]
                - name: recent_marks
                  mode: mini_bars
                  source: ManuscriptFeedback
                  filter: pupil = current
                  limit: 5
                - name: quick_actions
                  mode: quick_actions
                  actions: [log_behaviour, message_parent]

        ``scope_param`` is optional (defaults ``"id"``). ``sections``
        is required and must be non-empty.
        """
        scope_param_str: str | None = None
        sections: list[ir.EntityCardSection] = []
        _VALID_KEYS = {"scope_param", "sections"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)

            if key == "scope_param":
                scope_param_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "sections":
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                sections = self._parse_entity_card_sections_block()
                self.expect(TokenType.DEDENT)
            else:
                raise make_parse_error(
                    f"Unknown entity_card_config key {key!r}. "
                    f"Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        if not sections:
            tok = self.current_token()
            raise make_parse_error(
                "entity_card_config requires at least one section. Add a "
                "`sections:` block with one or more dash-list entries.",
                self.file,
                tok.line,
                tok.column,
            )
        kwargs: dict[str, Any] = {"sections": sections}
        if scope_param_str is not None:
            kwargs["scope_param"] = scope_param_str
        return ir.EntityCardConfig(**kwargs)

    def _parse_entity_card_sections_block(self) -> list[ir.EntityCardSection]:
        """Parse the dash-list body of an entity_card ``sections:`` block.

        Refactored to per-entry helper extraction. Each entry must lead
        with ``- name:``. Required keys after ``name``: ``mode`` (one of
        halo / flags / mini_bars / stamps / thread_summary / quick_actions).
        Optional: source, filter, limit (1..100), fields (bracketed
        identifier list), actions (bracketed identifier list).
        """
        sections: list[ir.EntityCardSection] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            sections.append(self._parse_entity_card_section_entry())
        return sections

    def _parse_entity_card_section_entry(self) -> ir.EntityCardSection:
        """Parse one ``- name: <id>`` entity-card section entry + its kv block."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                "sections entries must start with `- name: <id>`",
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()
        name_str = self._parse_entity_card_section_head()
        kv = self._parse_entity_card_section_kv_block(name_str)
        mode_val, source_str, filter_expr, limit_val, fields_list, actions_list = kv
        if mode_val is None:
            tok = self.current_token()
            raise make_parse_error(
                f"sections entry name={name_str!r} requires `mode:`.",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.EntityCardSection(
            name=name_str,
            mode=ir.EntityCardSectionMode(mode_val),
            source=source_str,
            filter=filter_expr,
            limit=limit_val,
            fields=fields_list,
            actions=actions_list,
        )

    def _parse_entity_card_section_head(self) -> str:
        """Consume the required ``name: <id>`` first key after the dash."""
        head_kw = self.expect_identifier_or_keyword().value
        if head_kw != "name":
            tok = self.current_token()
            raise make_parse_error(
                f"sections entry must start with `name:`, got {head_kw!r}",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.COLON)
        name_str: str = self.expect_identifier_or_keyword().value
        self.skip_newlines()
        return name_str

    def _parse_entity_card_section_kv_block(
        self, name_str: str
    ) -> tuple[
        str | None,
        str | None,
        "ir.ConditionExpr | None",
        int | None,
        list[str],
        list[str],
    ]:
        """Consume the optional indented mode/source/filter/limit/fields/actions block.

        Returns ``(mode, source, filter, limit, fields, actions)``. ``mode``
        is None if omitted — the caller raises a required-field error.
        """
        valid_modes = {mode.value for mode in ir.EntityCardSectionMode}
        valid_keys = {"name", "mode", "source", "filter", "limit", "fields", "actions"}

        mode_val: str | None = None
        source_str: str | None = None
        filter_expr: ir.ConditionExpr | None = None
        limit_val: int | None = None
        fields_list: list[str] = []
        actions_list: list[str] = []

        if not self.match(TokenType.INDENT):
            return mode_val, source_str, filter_expr, limit_val, fields_list, actions_list
        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "mode":
                mode_val = self.expect_identifier_or_keyword().value
                if mode_val not in valid_modes:
                    raise make_parse_error(
                        f"sections entry name={name_str!r}: mode "
                        f"must be one of {sorted(valid_modes)}; "
                        f"got {mode_val!r}",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
                self.skip_newlines()
            elif key == "source":
                source_str = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "filter":
                filter_expr = self.parse_condition_expr()
                self.skip_newlines()
            elif key == "limit":
                limit_val = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()
            elif key == "fields":
                fields_list = self._parse_bracketed_ident_list()
                self.skip_newlines()
            elif key == "actions":
                actions_list = self._parse_bracketed_ident_list()
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown sections entry key {key!r}. Expected one of: {sorted(valid_keys)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
        self.expect(TokenType.DEDENT)
        return mode_val, source_str, filter_expr, limit_val, fields_list, actions_list

    def _parse_bracketed_ident_list(self) -> list[str]:
        """Consume ``[ident1, ident2, ...]`` and return the identifier list."""
        out: list[str] = []
        self.expect(TokenType.LBRACKET)
        while not self.match(TokenType.RBRACKET):
            out.append(self.expect_identifier_or_keyword().value)
            if self.match(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RBRACKET)
        return out

    def _parse_status_entries_block(self) -> list[ir.StatusListEntrySpec]:
        """Parse the indented body of a status_list ``entries:`` block (#3).

        Refactored to per-entry helper extraction. Each entry is a
        dash-list dict with ``title`` (required) plus optional
        ``caption`` / ``icon`` / ``state``::

            entries:
              - title: "Verified"
                caption: "Identity confirmed via SSO"
                icon: "check-circle"
                state: positive

        ``state`` reuses the action_grid + metrics + notice tone
        vocabulary (positive / warning / destructive / accent / neutral).
        """
        entries: list[ir.StatusListEntrySpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            entries.append(self._parse_status_entry())
        return entries

    def _parse_status_entry(self) -> ir.StatusListEntrySpec:
        """Parse one ``- title: "..."`` status_list entry + its kv block."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                'status_list entries must start with `- title: "..."`',
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()  # consume MINUS
        title_str = self._parse_status_entry_title()
        caption_str, icon_str, state_str = self._parse_status_entry_kv_block(title_str)
        return ir.StatusListEntrySpec(
            title=title_str,
            caption=caption_str,
            icon=icon_str,
            state=state_str,
        )

    def _parse_status_entry_title(self) -> str:
        """Consume the required ``title: "<str>"`` first key after the dash."""
        title_kw = self.expect_identifier_or_keyword().value
        if title_kw != "title":
            tok = self.current_token()
            raise make_parse_error(
                f"status_list entry must start with `title:`, got {title_kw!r}",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.COLON)
        title_str: str = self.expect(TokenType.STRING).value
        self.skip_newlines()
        return title_str

    def _parse_status_entry_kv_block(self, title_str: str) -> tuple[str, str, str]:
        """Consume the optional indented caption/icon/state block.

        Returns ``(caption, icon, state)``. ``state`` defaults to ``"neutral"``.
        """
        valid_states = {"positive", "warning", "destructive", "neutral", "accent"}
        valid_keys = {"title", "caption", "icon", "state"}

        caption_str = ""
        icon_str = ""
        state_str = "neutral"

        if not self.match(TokenType.INDENT):
            return caption_str, icon_str, state_str
        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if key == "caption":
                caption_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "icon":
                icon_str = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "state":
                state_val = self.expect_identifier_or_keyword().value
                if state_val not in valid_states:
                    raise make_parse_error(
                        f"status_list entry {title_str!r}: state must be one of "
                        f"{sorted(valid_states)}; got {state_val!r}",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
                state_str = state_val
                self.skip_newlines()
            else:
                raise make_parse_error(
                    f"Unknown status_list entry key {key!r}. "
                    f"Expected one of: {sorted(valid_keys)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
        self.expect(TokenType.DEDENT)
        return caption_str, icon_str, state_str

    def _parse_confirmations_block(self) -> list[ir.ConfirmationItemSpec]:
        """Parse the indented body of a confirm_action_panel
        ``confirmations:`` block (#6).

        Each entry is a dash-list dict with ``title:`` (required) plus
        optional ``caption:`` / ``required:`` (defaults to True)::

            confirmations:
              - title: "I confirm the school has signed the DPA"
                caption: "Recorded with my account, IP, timestamp"
              - title: "I authorise reviewed write-backs"
                required: true
              - title: "Audit trail will be visible to school admins"
                required: false

        v0.61.72 (AegisMark UX patterns roadmap item #6).
        """
        items: list[ir.ConfirmationItemSpec] = []
        _VALID_KEYS = {"title", "caption", "required"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'confirmations entries must start with `- title: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            title_kw = self.expect_identifier_or_keyword().value
            if title_kw != "title":
                tok = self.current_token()
                raise make_parse_error(
                    f"confirmations entry must start with `title:`, got {title_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            title_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            caption_str = ""
            required_bool = True

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
                    if key == "caption":
                        caption_str = self.expect(TokenType.STRING).value
                        self.skip_newlines()
                    elif key == "required":
                        # Accept `true` / `false` as bare identifiers
                        # (lexer doesn't emit BOOLEAN tokens here).
                        bool_val = self.expect_identifier_or_keyword().value
                        if bool_val not in ("true", "false"):
                            raise make_parse_error(
                                f"confirmations entry {title_str!r}: required must be "
                                f"`true` or `false`; got {bool_val!r}",
                                self.file,
                                key_tok.line,
                                key_tok.column,
                            )
                        required_bool = bool_val == "true"
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown confirmations entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            items.append(
                ir.ConfirmationItemSpec(
                    title=title_str,
                    caption=caption_str,
                    required=required_bool,
                )
            )
        return items

    def _parse_row_action_block(self) -> ir.RowActionSpec:
        """#1148: parse a typed ``row_action:`` block.

        Per-row click-to-POST action for row-oriented region displays
        (``list``, ``cohort_strip``, ``day_timeline``, ``status_list``).
        ``action_id`` references a project-declared surface action;
        the runtime resolves the POST URL via the same machinery
        ``entity_card.quick_actions`` uses at the card level.

        Syntax::

            row_action:
              label: "Approve & release"
              action_id: feedback_release
              bind:
                id: id
              visible_when: status != released
              confirm:
                title: "Release to school?"
                caption: "School admins will see the audit trail"

        ``label`` and ``action_id`` are required. ``bind:`` defaults
        to ``{}``. ``visible_when:`` parses as a standard condition
        expression. ``confirm:`` reuses the :class:`ir.ConfirmationItemSpec`
        shape from #1072.
        """
        _VALID_KEYS = {"label", "action_id", "bind", "visible_when", "confirm"}
        label: str | None = None
        action_id: str | None = None
        bind: dict[str, str] = {}
        visible_when: ir.ConditionExpr | None = None
        confirm: ir.ConfirmationItemSpec | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            key_tok = self.current_token()
            key = key_tok.value
            if key not in _VALID_KEYS:
                raise make_parse_error(
                    f"Unknown row_action key {key!r}. Expected one of: {sorted(_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)
            if key == "label":
                label = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif key == "action_id":
                action_id = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif key == "bind":
                bind = self._parse_row_action_bind_block()
            elif key == "visible_when":
                visible_when = self.parse_condition_expr()
                self.skip_newlines()
            elif key == "confirm":
                confirm = self._parse_row_action_confirm_block(key_tok)

        if label is None or action_id is None:
            tok = self.current_token()
            raise make_parse_error(
                "row_action requires both `label:` and `action_id:`",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.RowActionSpec(
            label=label,
            action_id=action_id,
            bind=bind,
            visible_when=visible_when,
            confirm=confirm,
        )

    def _parse_row_action_bind_block(self) -> dict[str, str]:
        """#1148: parse the indented ``bind:`` sub-block of row_action."""
        bind: dict[str, str] = {}
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            bind_key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            bind_val = self.expect_identifier_or_keyword().value
            bind[bind_key] = bind_val
            self.skip_newlines()
        self.expect(TokenType.DEDENT)
        return bind

    def _parse_row_action_confirm_block(self, key_tok: Any) -> ir.ConfirmationItemSpec:
        """#1148: parse the indented ``confirm:`` sub-block of row_action.

        Same shape as one entry in a ``confirmations:`` block — title
        required, caption + required optional.
        """
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        title: str | None = None
        caption = ""
        required = True
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            c_key_tok = self.current_token()
            c_key = c_key_tok.value
            self.advance()
            self.expect(TokenType.COLON)
            if c_key == "title":
                title = self.expect(TokenType.STRING).value
            elif c_key == "caption":
                caption = self.expect(TokenType.STRING).value
            elif c_key == "required":
                bool_val = self.expect_identifier_or_keyword().value
                if bool_val not in ("true", "false"):
                    raise make_parse_error(
                        f"row_action confirm.required must be `true` or `false`; got {bool_val!r}",
                        self.file,
                        c_key_tok.line,
                        c_key_tok.column,
                    )
                required = bool_val == "true"
            else:
                raise make_parse_error(
                    f"Unknown row_action confirm key {c_key!r}. "
                    "Expected one of: title, caption, required.",
                    self.file,
                    c_key_tok.line,
                    c_key_tok.column,
                )
            self.skip_newlines()
        self.expect(TokenType.DEDENT)
        if title is None:
            raise make_parse_error(
                "row_action confirm requires a `title:` field",
                self.file,
                key_tok.line,
                key_tok.column,
            )
        return ir.ConfirmationItemSpec(title=title, caption=caption, required=required)

    def _parse_overlay_series_block(self) -> list[ir.OverlaySeriesSpec]:
        """Parse the indented body of an ``overlay_series:`` block (#883).

        Refactored to per-entry helper extraction.

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
            series.append(self._parse_overlay_series_entry())
        return series

    def _parse_overlay_series_entry(self) -> ir.OverlaySeriesSpec:
        """Parse one ``- label: "..."`` overlay_series entry + its kv block."""
        if not self.match(TokenType.MINUS):
            tok = self.current_token()
            raise make_parse_error(
                'overlay_series entries must start with `- label: "..."`',
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()  # consume MINUS
        label_str = self._parse_dash_required_label("overlay_series")
        source_name, filter_expr, aggregate_ref = self._parse_overlay_series_kv_block()
        if aggregate_ref is None:
            tok = self.current_token()
            raise make_parse_error(
                f"overlay_series entry {label_str!r} requires `aggregate:`",
                self.file,
                tok.line,
                tok.column,
            )
        return ir.OverlaySeriesSpec(
            label=label_str,
            source=source_name,
            filter=filter_expr,
            aggregate=aggregate_ref,
        )

    def _parse_overlay_series_kv_block(
        self,
    ) -> tuple[str | None, "ir.ConditionExpr | None", "ir.AggregateRef | None"]:
        """Consume the optional indented source/filter/aggregate block.

        Returns ``(source, filter, aggregate)``. ``aggregate`` is required
        by the caller — ``None`` here signals omission. Per ADR-0024 the
        ``aggregate:`` value parses through :meth:`parse_aggregate_ref`
        into a typed :class:`AggregateRef`.
        """
        source_name: str | None = None
        filter_expr: ir.ConditionExpr | None = None
        aggregate_ref: ir.AggregateRef | None = None

        if not self.match(TokenType.INDENT):
            return source_name, filter_expr, aggregate_ref
        self.advance()  # consume INDENT
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
                aggregate_ref = self.parse_aggregate_ref()
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
        return source_name, filter_expr, aggregate_ref

    def parse_workspace(self) -> ir.WorkspaceSpec:
        """Parse a ``workspace <name> "Title":`` declaration.

        Refactored from a 104-line monolith into a thin orchestration
        sequence + 6 phase helpers. The outer loop dispatches on the
        next token type and falls through to the IDENTIFIER → region
        fallback for any unrecognised keyword.
        """
        name, title, loc = self._parse_construct_header(
            TokenType.WORKSPACE, allow_keyword_name=True
        )
        state = _WorkspaceState()

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self._dispatch_workspace_keyword(state):
                # Legacy `else: break` — unrecognised non-region token bails
                # the loop; surrounding expect(DEDENT) then raises if the
                # cursor isn't on a DEDENT.
                break

        self.expect(TokenType.DEDENT)
        return ir.WorkspaceSpec(
            name=name,
            title=title,
            purpose=state.purpose,
            stage=state.stage,
            regions=state.regions,
            nav_groups=state.nav_groups,
            nav_ref=state.nav_ref,
            ux=state.ux_spec,
            access=state.access_spec,
            context_selector=state.context_selector,
            primary_actions=state.primary_actions,
            source=loc,
        )

    # ---------- parse_workspace phase helpers ---------- #

    def _dispatch_workspace_keyword(self, state: "_WorkspaceState") -> bool:
        """One workspace-loop dispatch tick. Returns False to bail the loop.

        The `parse_block_with_dispatch` helper doesn't apply cleanly here:
        the legacy parser falls through to ``IDENTIFIER → region`` for
        ANY identifier (the region name), and breaks on anything else.
        Encoding both in a custom dispatch keeps the legacy semantics
        without a sentinel exception.
        """
        if self.match(TokenType.ACCESS):
            self.advance()
            self.expect(TokenType.COLON)
            state.access_spec = self._parse_workspace_access()
            self.skip_newlines()
            return True
        if self.match(TokenType.PURPOSE):
            self.advance()
            self.expect(TokenType.COLON)
            state.purpose = self.expect(TokenType.STRING).value
            self.skip_newlines()
            return True
        if self.match(TokenType.STAGE) or self.match(TokenType.ENGINE_HINT):
            # ENGINE_HINT is the deprecated v0.3.1 form of STAGE (v0.8.0+).
            self.advance()
            self.expect(TokenType.COLON)
            state.stage = self.expect(TokenType.STRING).value
            self.skip_newlines()
            return True
        if self.match(TokenType.CONTEXT_SELECTOR):
            state.context_selector = self._parse_context_selector()
            return True
        if self.match(TokenType.USES) and self.peek_token().type == TokenType.NAV:
            # `uses nav <name>` — bind a shared nav definition (#926).
            self.advance()  # consume `uses`
            self.advance()  # consume `nav`
            state.nav_ref = self.expect_identifier_or_keyword().value
            self.skip_newlines()
            return True
        if self.match(TokenType.NAV_GROUP, TokenType.GROUP):
            # Both keywords accepted at workspace top-level (lighter
            # visual weight inside `nav <name>:` blocks).
            state.nav_groups.append(self._parse_nav_group())
            return True
        if self.match(TokenType.UX):
            state.ux_spec = self.parse_ux_block()
            return True
        if (
            self.match(TokenType.IDENTIFIER)
            and self.current_token().value == "primary_actions"
            and self.peek_token().type == TokenType.COLON
        ):
            # #1324 FR-5: `primary_actions:` heading-CTA block. Intercepted
            # here (an IDENTIFIER, not a keyword token) BEFORE the region
            # fallback below; the COLON peek disambiguates it from a region
            # that an author happened to name `primary_actions`.
            state.primary_actions.extend(self._parse_workspace_primary_actions())
            return True
        if self.match(TokenType.IDENTIFIER):
            # Fallback: any unrecognised identifier names a workspace region.
            state.regions.append(self.parse_workspace_region())
            return True
        return False

    def _parse_workspace_primary_actions(
        self,
    ) -> list[ir.WorkspacePrimaryActionSpec]:
        """Parse a ``primary_actions:`` block (#1324 FR-5).

        Syntax::

            primary_actions:
              action "New Invoice" -> surface create_invoice
              action "Dashboard" -> workspace ops_dashboard

        Each line is ``action "<label>" -> (surface|workspace) <name>``.
        ``action`` is the ACTION keyword token; ``surface``/``workspace`` are
        the SURFACE/WORKSPACE keyword tokens; the name after them is an
        identifier-or-keyword (mirrors `uses nav <name>` / nav-item parsing).
        """
        self.advance()  # consume `primary_actions` identifier
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        actions: list[ir.WorkspacePrimaryActionSpec] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            self.expect(TokenType.ACTION)
            label = self.expect(TokenType.STRING).value
            self.expect(TokenType.ARROW)
            if self.match(TokenType.SURFACE):
                self.advance()
                target_kind: str = "surface"
            elif self.match(TokenType.WORKSPACE):
                self.advance()
                target_kind = "workspace"
            else:
                tok = self.current_token()
                raise make_parse_error(
                    "Expected `surface` or `workspace` after `->` in a "
                    f"primary_actions action, got {tok.value!r}.",
                    self.file,
                    tok.line,
                    tok.column,
                )
            target = self.expect_identifier_or_keyword().value
            actions.append(
                ir.WorkspacePrimaryActionSpec(
                    label=label,
                    target_kind=target_kind,  # type: ignore[arg-type]
                    target=target,
                )
            )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return actions

    # Parsed access specs are enforced at request time in
    # src/dazzle/ui/runtime/surface_access.py:check_surface_access().
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
            nav_group "Label" [icon=name] [collapsed] [when: <cond>]:
              entity_name [icon=name] [when: <cond>]
              ...

        ``when: <cond>`` (#1324 FR-4) is an optional render-time VISIBILITY
        condition on the group header and/or per item — the same
        ``ConditionExpr`` idiom as ``RowActionSpec.visible_when:``. It is
        parsed here but inert until slice B wires the render filter.
        """
        self.advance()  # consume nav_group

        # Label (required string)
        label = self.expect(TokenType.STRING).value

        # Optional inline attributes: icon=name, collapsed, when: <cond>
        icon = None
        collapsed = False
        when: ir.ConditionExpr | None = None
        while not self.match(TokenType.COLON):
            if self.match(TokenType.ICON):
                self.advance()
                self.expect(TokenType.EQUALS)
                icon = self._parse_hyphenated_identifier()
            elif self.match(TokenType.COLLAPSED):
                self.advance()
                collapsed = True
            elif self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                when = self.parse_condition_expr()
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
            item_when: ir.ConditionExpr | None = None

            # Optional icon=name and/or when: <cond> on nav item.
            while self.match(TokenType.ICON, TokenType.WHEN):
                if self.match(TokenType.ICON):
                    self.advance()
                    self.expect(TokenType.EQUALS)
                    item_icon = self._parse_hyphenated_identifier()
                else:  # WHEN
                    self.advance()
                    self.expect(TokenType.COLON)
                    item_when = self.parse_condition_expr()

            # #1328: a nav group lists ONE bare entity/workspace name per line —
            # there is NO `item` keyword. A stray trailing identifier (the classic
            # `item Contact` misuse, which previously parsed as a phantom `item`
            # entry plus `Contact` and was silently dropped) is now a hard parse
            # error directing the author to the canonical bare-name form.
            if not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                stray = self.current_token()
                if entity == "item":
                    msg = (
                        "nav groups list a bare entity or workspace name per line — "
                        f"there is no `item` keyword. Write `{stray.value}` instead of "
                        f"`item {stray.value}`."
                    )
                else:
                    msg = (
                        "nav group items take one entity or workspace name per line; "
                        f"unexpected `{stray.value}` after `{entity}`."
                    )
                raise make_parse_error(msg, self.file, stray.line, stray.column)

            items.append(ir.NavItemIR(entity=entity, icon=item_icon, when=item_when))
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.NavGroupSpec(
            label=label,
            icon=icon,
            collapsed=collapsed,
            items=items,
            when=when,
        )

    def parse_workspace_region(self) -> ir.WorkspaceRegion:
        """Parse a workspace region declaration.

        Refactored to dispatch-table style (#1098) — body collapses to a
        header parse, a ``parse_block_with_dispatch`` call against
        :data:`_WORKSPACE_REGION_KEYWORDS` / :data:`_WORKSPACE_REGION_IDENT_KEYWORDS`,
        and a :func:`_build_workspace_region` call. The 50+ legacy
        locals live on :class:`_WorkspaceRegionState`; each per-keyword
        branch is now a small free function (see ``_kw_*`` below).
        """
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _WorkspaceRegionState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_WORKSPACE_REGION_KEYWORDS,
            ident_keywords=_WORKSPACE_REGION_IDENT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_workspace_region(self, name, state)


# ============================================================== #
# parse_workspace_region (#1098) — keyword-dispatch decomposition #
# ============================================================== #
#
# The 859-line monolith above was replaced (v0.70.14) with the
# dispatch-table pattern shipped in #1097. Each former elif branch
# is now a small ``_kw_*`` free function below; the post-loop
# discriminated-union assembly lives in :func:`_build_workspace_region`.
# Per-keyword error messages match the original byte-for-byte.


@dataclass
class _WorkspaceState:
    """Accumulator for :meth:`WorkspaceParserMixin.parse_workspace`.

    Outer-workspace state — distinct from :class:`_WorkspaceRegionState`,
    which is the inner per-region accumulator.
    """

    purpose: str | None = None
    stage: str | None = None
    regions: list[ir.WorkspaceRegion] = field(default_factory=list)
    nav_groups: list[ir.NavGroupSpec] = field(default_factory=list)
    nav_ref: str | None = None
    ux_spec: ir.UXSpec | None = None
    access_spec: ir.WorkspaceAccessSpec | None = None
    context_selector: ir.ContextSelectorSpec | None = None
    # #1324 FR-5: authored heading-CTA buttons (primary_actions: block).
    primary_actions: list[ir.WorkspacePrimaryActionSpec] = field(default_factory=list)


@dataclass
class _WorkspaceRegionState:
    """Accumulator for :meth:`WorkspaceParserMixin.parse_workspace_region`.

    One field per legal keyword in a workspace ``region:`` block — mirrors
    the locals of the legacy monolith. :func:`_build_workspace_region`
    reads this and constructs the frozen :class:`ir.WorkspaceRegion`.
    """

    source: str | None = None
    sources: list[str] = field(default_factory=list)
    source_filters: dict[str, ir.ConditionExpr] = field(default_factory=dict)
    filter_expr: ir.ConditionExpr | None = None
    sort: list[ir.SortSpec] = field(default_factory=list)
    limit: int | None = None
    display: ir.DisplayMode = ir.DisplayMode.LIST
    render: str | None = None
    action: str | None = None
    empty_message: str | None = None
    group_by: str | ir.BucketRef | None = None
    group_by_dims: list[str | ir.BucketRef] | None = None
    aggregates: dict[str, ir.AggregateRef | ir.DerivedMetric] = field(default_factory=dict)
    date_field: str | None = None
    date_range: bool = False
    heatmap_rows: str | None = None
    heatmap_columns: str | None = None
    heatmap_value: str | None = None
    heatmap_thresholds: list[float] | ir.ParamRef = field(default_factory=list)
    progress_stages: list[str] = field(default_factory=list)
    progress_complete_at: str | None = None
    delta: ir.DeltaSpec | None = None
    reference_lines: list[ir.ReferenceLine] = field(default_factory=list)
    reference_bands: list[ir.ReferenceBand] = field(default_factory=list)
    bin_count: int | None = None
    show_outliers: bool = True
    bullet_label: str | None = None
    bullet_actual: str | None = None
    bullet_target: str | None = None
    overlay_series: list[ir.OverlaySeriesSpec] = field(default_factory=list)
    css_class: str | None = None
    eyebrow: str | None = None
    title_override: str | None = None
    width: int | None = None
    tones: dict[str, str] = field(default_factory=dict)
    notice: ir.NoticeSpec | None = None
    track_max: float | None = None
    track_format: str | None = None
    action_cards: list[ir.ActionCardSpec] = field(default_factory=list)
    status_entries: list[ir.StatusListEntrySpec] = field(default_factory=list)
    confirmations: list[ir.ConfirmationItemSpec] = field(default_factory=list)
    state_field: str | None = None
    revoke: str | None = None
    primary_action: str | None = None
    secondary_action: str | None = None
    avatar_field: str | None = None
    primary: str | None = None
    secondary: str | None = None
    profile_stats: list[ir.ProfileCardStatSpec] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    pipeline_stages: list[ir.PipelineStageSpec] = field(default_factory=list)
    cohort_strip_config: ir.CohortStripConfig | None = None
    day_timeline_config: ir.DayTimelineConfig | None = None
    task_inbox_config: ir.TaskInboxConfig | None = None
    entity_card_config: ir.EntityCardConfig | None = None
    row_action: ir.RowActionSpec | None = None  # #1148
    drill: str | None = None  # #1303 — per-row drill-to-detail (detail|none)
    refresh_interval: int | None = None  # #1391 — `refresh: every Ns` poll seconds


# ---------- Simple keyword-value branches ---------- #


def _kw_source(parser: Any, state: _WorkspaceRegionState) -> None:
    """``source: EntityName`` OR ``source: [Entity1, Entity2, ...]``."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.LBRACKET):
        parser.advance()  # consume [
        while not parser.match(TokenType.RBRACKET):
            parser.skip_newlines()
            if parser.match(TokenType.RBRACKET):
                break
            state.sources.append(parser.expect_identifier_or_keyword().value)
            if parser.match(TokenType.COMMA):
                parser.advance()
            parser.skip_newlines()
        parser.expect(TokenType.RBRACKET)
    else:
        state.source = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_filter_map(parser: Any, state: _WorkspaceRegionState) -> None:
    """``filter_map:`` — per-source filters for multi-source regions."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        entity_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)
        state.source_filters[entity_name] = parser.parse_condition_expr()
        parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


def _kw_filter(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.filter_expr = parser.parse_condition_expr()
    parser.skip_newlines()


def _kw_sort(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.sort = parser.parse_sort_list()
    parser.skip_newlines()


def _kw_limit(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.limit = int(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _kw_display(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.display = parser.enum_from_token(ir.DisplayMode, parser.expect_identifier_or_keyword())
    parser.skip_newlines()


def _kw_render(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.render = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_action(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.action = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_empty(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.empty_message = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_group_by(parser: Any, state: _WorkspaceRegionState) -> None:
    """``group_by: field`` (single-dim) or ``group_by: [a, b]`` (multi-dim)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.LBRACKET):
        parser.advance()  # consume [
        dims: list[str | ir.BucketRef] = []
        while not parser.match(TokenType.RBRACKET):
            parser.skip_newlines()
            if parser.match(TokenType.RBRACKET):
                break
            dims.append(parser._parse_group_by_element())
            if parser.match(TokenType.COMMA):
                parser.advance()
            parser.skip_newlines()
        parser.expect(TokenType.RBRACKET)
        state.group_by_dims = dims
    else:
        state.group_by = parser._parse_group_by_element()
    parser.skip_newlines()


def _kw_date_field(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.date_field = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_date_range(parser: Any, state: _WorkspaceRegionState) -> None:
    """``date_range`` — flag (no colon)."""
    parser.advance()
    state.date_range = True
    parser.skip_newlines()


def _kw_aggregate(parser: Any, state: _WorkspaceRegionState) -> None:
    """``aggregate:`` block — ``metric_name: <AggregateRef>`` per line.

    Per ADR-0024 each entry is parsed structurally via
    :meth:`parse_aggregate_ref` into a typed :class:`AggregateRef`.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        metric_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)
        # #1359: a metric line is either an aggregate call
        # (count/sum/avg/min/max followed by '(') or a derived expression
        # over the names declared EARLIER in this block.
        if parser.peek_is_aggregate_call():
            state.aggregates[metric_name] = parser.parse_aggregate_ref()
        else:
            state.aggregates[metric_name] = parser.parse_derived_metric(
                set(state.aggregates.keys())
            )
        parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


def _kw_rows(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    rows = parser.expect_identifier_or_keyword().value
    while parser.match(TokenType.DOT):
        parser.advance()
        rows += "." + parser.expect_identifier_or_keyword().value
    state.heatmap_rows = rows
    parser.skip_newlines()


def _kw_columns(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    cols = parser.expect_identifier_or_keyword().value
    while parser.match(TokenType.DOT):
        parser.advance()
        cols += "." + parser.expect_identifier_or_keyword().value
    state.heatmap_columns = cols
    parser.skip_newlines()


def _kw_value(parser: Any, state: _WorkspaceRegionState) -> None:
    """``value: <expression>`` — captured as a raw string until newline."""
    parser.advance()
    parser.expect(TokenType.COLON)
    value_parts: list[str] = []
    while not parser.match(TokenType.NEWLINE, TokenType.DEDENT):
        value_parts.append(parser.advance().value)
    state.heatmap_value = " ".join(value_parts)
    parser.skip_newlines()


def _kw_thresholds(parser: Any, state: _WorkspaceRegionState) -> None:
    """``thresholds: param("k")`` OR ``thresholds: [0.4, 0.6]``."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.PARAM):
        parser.advance()  # consume 'param'
        parser.expect(TokenType.LPAREN)
        ref_key = parser.expect(TokenType.STRING).value
        parser.expect(TokenType.RPAREN)
        state.heatmap_thresholds = ir.ParamRef(key=ref_key, param_type="list[float]", default=[])
    else:
        thresh_list: list[float] = []
        parser.expect(TokenType.LBRACKET)
        while not parser.match(TokenType.RBRACKET):
            parser.skip_newlines()
            if parser.match(TokenType.RBRACKET):
                break
            num_token = parser.expect(TokenType.NUMBER)
            num_str = num_token.value
            if parser.match(TokenType.DOT):
                parser.advance()
                frac = parser.expect(TokenType.NUMBER).value
                num_str = num_str + "." + frac
            thresh_list.append(float(num_str))
            if parser.match(TokenType.COMMA):
                parser.advance()
            parser.skip_newlines()
        parser.expect(TokenType.RBRACKET)
        state.heatmap_thresholds = thresh_list
    parser.skip_newlines()


def _kw_stages(parser: Any, state: _WorkspaceRegionState) -> None:
    """``stages: [a, b]`` → progress (legacy); indented dash-list → pipeline_steps (#890)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.LBRACKET):
        parser.advance()  # consume [
        while not parser.match(TokenType.RBRACKET):
            parser.skip_newlines()
            if parser.match(TokenType.RBRACKET):
                break
            state.progress_stages.append(parser.expect_identifier_or_keyword().value)
            if parser.match(TokenType.COMMA):
                parser.advance()
            parser.skip_newlines()
        parser.expect(TokenType.RBRACKET)
        parser.skip_newlines()
    else:
        parser.skip_newlines()
        parser.expect(TokenType.INDENT)
        state.pipeline_stages = parser._parse_pipeline_stages_block()
        parser.expect(TokenType.DEDENT)


def _kw_complete_at(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.progress_complete_at = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_delta(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.delta = parser._parse_delta_block()
    parser.expect(TokenType.DEDENT)


def _kw_reference_lines(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.reference_lines = parser._parse_reference_lines_block()
    parser.expect(TokenType.DEDENT)


def _kw_reference_bands(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.reference_bands = parser._parse_reference_bands_block()
    parser.expect(TokenType.DEDENT)


def _kw_bullet_label(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.bullet_label = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_bullet_actual(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.bullet_actual = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_bullet_target(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.bullet_target = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_css_class(parser: Any, state: _WorkspaceRegionState) -> None:
    """``class:`` accepts a quoted string or a bare identifier (#894)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.css_class = parser.advance().value
    else:
        state.css_class = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_eyebrow(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.eyebrow = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_width(parser: Any, state: _WorkspaceRegionState) -> None:
    """``width: <int 1..12>`` — grid-column span override (#914). Clamped at parse."""
    parser.advance()
    parser.expect(TokenType.COLON)
    w_token = parser.expect(TokenType.NUMBER)
    try:
        w_raw = int(w_token.value)
    except (TypeError, ValueError):
        w_raw = 12
    if w_raw < 1:
        w_raw = 1
    elif w_raw > 12:
        w_raw = 12
    state.width = w_raw
    parser.skip_newlines()


def _kw_tones(parser: Any, state: _WorkspaceRegionState) -> None:
    """``tones:`` block — ``metric_name: tone_token`` per line (v0.61.65)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        metric_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)
        tone_token = parser.expect_identifier_or_keyword().value
        state.tones[metric_name] = tone_token
        parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


def _kw_notice(parser: Any, state: _WorkspaceRegionState) -> None:
    """``notice: "..."`` (title-only) OR block form (title/body/tone)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.notice = ir.NoticeSpec(title=parser.advance().value)
        parser.skip_newlines()
        return
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    n_title = ""
    n_body = ""
    n_tone = "neutral"
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        key_tok = parser.current_token()
        key = key_tok.value
        parser.advance()
        parser.expect(TokenType.COLON)
        if key == "title":
            n_title = parser.expect(TokenType.STRING).value
            parser.skip_newlines()
        elif key == "body":
            n_body = parser.expect(TokenType.STRING).value
            parser.skip_newlines()
        elif key == "tone":
            n_tone = parser.expect_identifier_or_keyword().value
            parser.skip_newlines()
        else:
            raise make_parse_error(
                f"Unknown notice key {key!r}. Expected one of: title, body, tone.",
                parser.file,
                key_tok.line,
                key_tok.column,
            )
    parser.expect(TokenType.DEDENT)
    if not n_title:
        tok = parser.current_token()
        raise make_parse_error(
            "notice block requires `title:`",
            parser.file,
            tok.line,
            tok.column,
        )
    state.notice = ir.NoticeSpec(title=n_title, body=n_body, tone=n_tone)


def _kw_track_max(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.track_max = float(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _kw_track_format(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.track_format = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_actions(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.action_cards = parser._parse_action_cards_block()
    parser.expect(TokenType.DEDENT)


def _kw_entries(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.status_entries = parser._parse_status_entries_block()
    parser.expect(TokenType.DEDENT)


def _kw_confirmations(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.confirmations = parser._parse_confirmations_block()
    parser.expect(TokenType.DEDENT)


def _kw_row_action(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1148: ``row_action:`` block — per-row click-to-POST action."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.row_action = parser._parse_row_action_block()
    parser.expect(TokenType.DEDENT)


def _kw_drill(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1303: ``drill: detail | none`` — per-row drill-to-detail control.

    Unset → AUTO (link rows to the entity detail when a VIEW surface
    exists). ``detail`` → explicit auto. ``none`` → suppress row links.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    value_tok = parser.expect_identifier_or_keyword()
    value = str(value_tok.value)
    if value not in ("detail", "none"):
        raise make_parse_error(
            f"Unknown drill value {value!r}. Expected 'detail' or 'none'.",
            parser.file,
            value_tok.line,
            value_tok.column,
        )
    state.drill = value
    parser.skip_newlines()


def _kw_state_field(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.state_field = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_revoke(parser: Any, state: _WorkspaceRegionState) -> None:
    """``revoke: surface`` (IDENT) or ``revoke: "surface"`` (STRING) (#6)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.revoke = parser.advance().value
    else:
        state.revoke = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_avatar_field(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.avatar_field = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_primary(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.primary = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_secondary(parser: Any, state: _WorkspaceRegionState) -> None:
    """``secondary: "<template>"`` — quoted only ({{ field }} interpolation)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.secondary = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_stats(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.profile_stats = parser._parse_profile_stats_block()
    parser.expect(TokenType.DEDENT)


def _kw_facts(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.facts = parser._parse_facts_block()
    parser.expect(TokenType.DEDENT)


def _kw_overlay_series(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.overlay_series = parser._parse_overlay_series_block()
    parser.expect(TokenType.DEDENT)


def _kw_show_outliers(parser: Any, state: _WorkspaceRegionState) -> None:
    """``show_outliers: true|false`` — box plot toggle (#881)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.show_outliers = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.show_outliers = False
    else:
        token = parser.current_token()
        raise make_parse_error(
            f"show_outliers must be true or false; got {token.value!r}",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _kw_bins(parser: Any, state: _WorkspaceRegionState) -> None:
    """``bins: auto`` or ``bins: <positive int>`` — histogram (#882)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.NUMBER):
        bin_count = int(parser.advance().value)
        if bin_count < 1:
            token = parser.current_token()
            raise make_parse_error(
                f"bins must be a positive integer or 'auto'; got {bin_count}",
                parser.file,
                token.line,
                token.column,
            )
        state.bin_count = bin_count
    else:
        word_tok = parser.expect_identifier_or_keyword()
        if word_tok.value != "auto":
            raise make_parse_error(
                f"bins must be 'auto' or a positive integer; got {word_tok.value!r}",
                parser.file,
                word_tok.line,
                word_tok.column,
            )
        state.bin_count = None  # auto via Sturges
    parser.skip_newlines()


# ---------- IDENT-text-matched branches ---------- #
#
# These keywords are intentionally not lexer tokens — they share a name
# with bare identifiers used elsewhere in the grammar (`title` as an
# identifier in flow/demo blocks; `primary` / `secondary` as field
# names in profile_card; the `*_config` blocks as domain identifiers).
# Dispatched on IDENTIFIER value via _WORKSPACE_REGION_IDENT_KEYWORDS.


def _kw_title(parser: Any, state: _WorkspaceRegionState) -> None:
    """``title: "..."`` — explicit region title override (#903)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.title_override = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_primary_action(parser: Any, state: _WorkspaceRegionState) -> None:
    """``primary_action: surface`` (IDENT/STRING) — confirm_action_panel commit (#6)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.primary_action = parser.advance().value
    else:
        state.primary_action = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_secondary_action(parser: Any, state: _WorkspaceRegionState) -> None:
    """``secondary_action: surface`` (IDENT/STRING) — confirm_action_panel draft (#6)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.secondary_action = parser.advance().value
    else:
        state.secondary_action = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_cohort_strip_config(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.cohort_strip_config = parser._parse_cohort_strip_config_block()
    parser.expect(TokenType.DEDENT)


def _kw_day_timeline_config(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.day_timeline_config = parser._parse_day_timeline_config_block()
    parser.expect(TokenType.DEDENT)


def _kw_task_inbox_config(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.task_inbox_config = parser._parse_task_inbox_config_block()
    parser.expect(TokenType.DEDENT)


def _kw_entity_card_config(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.entity_card_config = parser._parse_entity_card_config_block()
    parser.expect(TokenType.DEDENT)


# ---------- Dispatch tables ---------- #


_WORKSPACE_REGION_KEYWORDS: dict[TokenType, KeywordParser[_WorkspaceRegionState]] = {
    TokenType.SOURCE: _kw_source,
    TokenType.FILTER_MAP: _kw_filter_map,
    TokenType.FILTER: _kw_filter,
    TokenType.SORT: _kw_sort,
    TokenType.LIMIT: _kw_limit,
    TokenType.DISPLAY: _kw_display,
    TokenType.RENDER: _kw_render,
    TokenType.ACTION: _kw_action,
    TokenType.EMPTY: _kw_empty,
    TokenType.GROUP_BY: _kw_group_by,
    TokenType.DATE_FIELD: _kw_date_field,
    TokenType.DATE_RANGE: _kw_date_range,
    TokenType.AGGREGATE: _kw_aggregate,
    TokenType.ROWS: _kw_rows,
    TokenType.COLUMNS: _kw_columns,
    TokenType.VALUE: _kw_value,
    TokenType.THRESHOLDS: _kw_thresholds,
    TokenType.STAGES: _kw_stages,
    TokenType.COMPLETE_AT: _kw_complete_at,
    TokenType.DELTA: _kw_delta,
    TokenType.REFERENCE_LINES: _kw_reference_lines,
    TokenType.REFERENCE_BANDS: _kw_reference_bands,
    TokenType.BULLET_LABEL: _kw_bullet_label,
    TokenType.BULLET_ACTUAL: _kw_bullet_actual,
    TokenType.BULLET_TARGET: _kw_bullet_target,
    TokenType.CSS_CLASS: _kw_css_class,
    TokenType.EYEBROW: _kw_eyebrow,
    TokenType.WIDTH: _kw_width,
    TokenType.TONES: _kw_tones,
    TokenType.NOTICE: _kw_notice,
    TokenType.TRACK_MAX: _kw_track_max,
    TokenType.TRACK_FORMAT: _kw_track_format,
    TokenType.ACTIONS: _kw_actions,
    TokenType.ENTRIES: _kw_entries,
    TokenType.CONFIRMATIONS: _kw_confirmations,
    TokenType.STATE_FIELD: _kw_state_field,
    TokenType.REVOKE: _kw_revoke,
    TokenType.AVATAR_FIELD: _kw_avatar_field,
    TokenType.PRIMARY: _kw_primary,
    TokenType.SECONDARY: _kw_secondary,
    TokenType.STATS: _kw_stats,
    TokenType.FACTS: _kw_facts,
    TokenType.OVERLAY_SERIES: _kw_overlay_series,
    TokenType.SHOW_OUTLIERS: _kw_show_outliers,
    TokenType.BINS: _kw_bins,
}


def _kw_refresh(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1391: ``refresh: every Ns`` — declarative live-refresh poll interval.

    Accepted forms: ``refresh: every 30s`` / ``refresh: every 30`` /
    ``refresh: 30s`` / ``refresh: 30`` (bare number = seconds). Stored as
    seconds; the region's dashboard card appends ``, every Ns`` to its HTMX
    trigger so the existing region-fetch endpoint re-renders on a poll.

    Seconds only in v1 — a non-``s`` unit (``5m``/``2h``) is a directed parse
    error pointing at seconds. Minimum 5s (load/cost floor, see
    docs/architecture/model-driven-failure-modes.md); a smaller value errors.
    """
    parser.advance()  # consume `refresh`
    parser.expect(TokenType.COLON)
    # Shared with the surface-refresh parser (#1399) so both stay in lockstep.
    state.refresh_interval = parse_refresh_interval_seconds(parser)
    parser.skip_newlines()


_WORKSPACE_REGION_IDENT_KEYWORDS: dict[str, KeywordParser[_WorkspaceRegionState]] = {
    "title": _kw_title,
    "primary_action": _kw_primary_action,
    "secondary_action": _kw_secondary_action,
    "cohort_strip_config": _kw_cohort_strip_config,
    "day_timeline_config": _kw_day_timeline_config,
    "task_inbox_config": _kw_task_inbox_config,
    "entity_card_config": _kw_entity_card_config,
    "row_action": _kw_row_action,  # #1148
    "drill": _kw_drill,  # #1303
    "refresh": _kw_refresh,  # #1391
}


# ---------- Post-loop builder ---------- #


def _build_workspace_region(
    parser: Any, name: str, state: _WorkspaceRegionState
) -> ir.WorkspaceRegion:
    """Construct the frozen :class:`ir.WorkspaceRegion` from parser state.

    Replicates the post-loop invariants of the legacy monolith:
      - Reject regions without ``source:`` AND any body-shape (aggregates,
        action_cards, pipeline_stages, status_entries, confirmations).
      - Reject combined single ``source:`` + multi-source list.
      - Auto-bump multi-source LIST display → TABBED_LIST.
      - Empty ``title`` string normalised to ``None`` (#903 fallback).
    """
    if (
        state.source is None
        and not state.sources
        and not state.aggregates
        and not state.action_cards
        and not state.pipeline_stages
        and not state.status_entries
        and not state.confirmations
    ):
        token = parser.current_token()
        raise make_parse_error(
            f"Workspace region '{name}' requires 'source:' or 'aggregate:' block",
            parser.file,
            token.line,
            token.column,
        )

    if state.source and state.sources:
        token = parser.current_token()
        raise make_parse_error(
            f"Workspace region '{name}' cannot have both 'source:' (single) and multi-source list",
            parser.file,
            token.line,
            token.column,
        )

    display = state.display
    if state.sources and display == ir.DisplayMode.LIST:
        display = ir.DisplayMode.TABBED_LIST

    return ir.WorkspaceRegion(
        name=name,
        source=state.source,
        sources=state.sources,
        source_filters=state.source_filters,
        filter=state.filter_expr,
        sort=state.sort,
        limit=state.limit,
        display=display,
        action=state.action,
        empty_message=state.empty_message,
        group_by=state.group_by,
        group_by_dims=state.group_by_dims,
        aggregates=state.aggregates,
        date_field=state.date_field,
        date_range=state.date_range,
        heatmap_rows=state.heatmap_rows,
        heatmap_columns=state.heatmap_columns,
        heatmap_value=state.heatmap_value,
        heatmap_thresholds=state.heatmap_thresholds,
        progress_stages=state.progress_stages,
        progress_complete_at=state.progress_complete_at,
        delta=state.delta,
        reference_lines=state.reference_lines,
        reference_bands=state.reference_bands,
        bin_count=state.bin_count,
        show_outliers=state.show_outliers,
        bullet_label=state.bullet_label,
        bullet_actual=state.bullet_actual,
        bullet_target=state.bullet_target,
        overlay_series=state.overlay_series,
        css_class=state.css_class,
        track_max=state.track_max,
        track_format=state.track_format,
        action_cards=state.action_cards,
        avatar_field=state.avatar_field,
        primary=state.primary,
        secondary=state.secondary,
        profile_stats=state.profile_stats,
        facts=state.facts,
        pipeline_stages=state.pipeline_stages,
        eyebrow=state.eyebrow,
        title=state.title_override or None,
        width=state.width,
        tones=state.tones,
        notice=state.notice,
        status_entries=state.status_entries,
        confirmations=state.confirmations,
        state_field=state.state_field,
        revoke=state.revoke,
        primary_action=state.primary_action,
        secondary_action=state.secondary_action,
        render=state.render,
        cohort_strip_config=state.cohort_strip_config,
        day_timeline_config=state.day_timeline_config,
        task_inbox_config=state.task_inbox_config,
        entity_card_config=state.entity_card_config,
        row_action=state.row_action,
        drill=state.drill,  # #1303
        refresh_interval=state.refresh_interval,  # #1391
    )
