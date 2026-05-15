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
        ``aggregate:``) OR a quoted literal string. The runtime
        distinguishes via `_AGGREGATE_RE` — matches fire a query,
        non-matches render verbatim. Replaces the v0.61.56 ``aggregate:``
        key (clean break, no shim per project policy).

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
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'pipeline stages entries must start with `- label: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()
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
            label_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            caption_str = ""
            value_str = ""
            progress_str = ""

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
                    elif key in ("value", "progress"):
                        # v0.61.66: accept either a quoted literal
                        # string or an unquoted aggregate expression.
                        # Quoted shape — common for flow-card labels
                        # like "Daily 02:00 UTC". Unquoted shape — same
                        # as region-level `aggregate:` parser.
                        # v0.61.78 (#911): `progress:` shares the same
                        # acceptor — literal numeric ("74") or aggregate
                        # expression. Runtime clamps 0-100.
                        if self.match(TokenType.STRING):
                            payload = self.advance().value
                        else:
                            parts: list[str] = []
                            while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                                parts.append(self.advance().value)
                            payload = " ".join(parts)
                        if key == "value":
                            value_str = payload
                        else:
                            progress_str = payload
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

            stages.append(
                ir.PipelineStageSpec(
                    label=label_str,
                    caption=caption_str,
                    value=value_str,
                    progress=progress_str,
                )
            )
        return stages

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
        _VALID_TONES = {"positive", "warning", "destructive", "neutral", "accent"}
        _VALID_KEYS = {"label", "icon", "count_aggregate", "action", "tone"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'actions entries must start with `- label: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
            label_kw = self.expect_identifier_or_keyword().value
            if label_kw != "label":
                tok = self.current_token()
                raise make_parse_error(
                    f"actions entry must start with `label:`, got {label_kw!r}",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.expect(TokenType.COLON)
            label_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            icon_str = ""
            count_aggregate = ""
            action_str = ""
            tone_str = "neutral"

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
                    if key == "icon":
                        icon_str = self.expect(TokenType.STRING).value
                        self.skip_newlines()
                    elif key == "count_aggregate":
                        # Same approach as `aggregate:` parser — capture
                        # tokens until newline/dedent and join.
                        parts: list[str] = []
                        while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                            parts.append(self.advance().value)
                        count_aggregate = " ".join(parts)
                        self.skip_newlines()
                    elif key == "action":
                        # Accept STRING (for URLs with `/`, `?`, `=`) OR
                        # IDENT (bare surface name). Required for examples
                        # like `action: "marking_result_list?status=flagged"`
                        # whose `?` and `=` don't tokenise as identifiers.
                        if self.match(TokenType.STRING):
                            action_str = self.advance().value
                        else:
                            action_str = self.expect_identifier_or_keyword().value
                        self.skip_newlines()
                    elif key == "tone":
                        tone_val = self.expect_identifier_or_keyword().value
                        if tone_val not in _VALID_TONES:
                            raise make_parse_error(
                                f"actions entry {label_str!r}: tone must be one of "
                                f"{sorted(_VALID_TONES)}; got {tone_val!r}",
                                self.file,
                                key_tok.line,
                                key_tok.column,
                            )
                        tone_str = tone_val
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown actions key {key!r}. Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            cards.append(
                ir.ActionCardSpec(
                    label=label_str,
                    icon=icon_str,
                    count_aggregate=count_aggregate,
                    action=action_str,
                    tone=tone_str,
                )
            )
        return cards

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

    def _parse_cohort_strip_lenses_block(self) -> list[ir.CohortStripLens]:
        """Parse the indented dash-list body of a ``lenses:`` block (#1018).

        Each entry must lead with ``- id:`` (the stable lens identifier
        used in URL params). The remaining keys land in the entry's
        INDENT block. ``label`` and ``primary`` are required;
        ``threshold`` is optional.
        """
        lenses: list[ir.CohortStripLens] = []
        _VALID_KEYS = {"id", "label", "primary", "threshold"}

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

            label_str: str | None = None
            primary_str: str | None = None
            threshold_val: float | None = None

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
                        # Quoted-string preferred (handles spaces, punctuation);
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
                    else:
                        raise make_parse_error(
                            f"Unknown lenses key {key!r}. Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            if label_str is None or primary_str is None:
                tok = self.current_token()
                raise make_parse_error(
                    f"lens {id_str!r} requires both `label:` and `primary:`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            lenses.append(
                ir.CohortStripLens(
                    id=id_str,
                    label=label_str,
                    primary=primary_str,
                    threshold=threshold_val,
                )
            )

        return lenses

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
        _VALID_KEYS = {"starts_at", "ends_at", "card"}

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

        Each entry leads with ``- source: <EntityName>``; the rest of
        the entry's keys land in its INDENT block. Exactly one of
        ``as_task`` (nested template block) or ``count_as`` (string)
        must be set per entry.
        """
        sources: list[ir.TaskSource] = []
        _VALID_KEYS = {"source", "filter", "as_task", "count_as"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "sources entries must start with `- source: <EntityName>`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
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
            source_str = self.expect_identifier_or_keyword().value
            self.skip_newlines()

            filter_expr: ir.ConditionExpr | None = None
            as_task: ir.TaskSourceTemplate | None = None
            count_as_str: str = ""

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
                            f"Unknown sources entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            # Mutex enforcement: as_task XOR count_as.
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
            sources.append(
                ir.TaskSource(
                    source=source_str,
                    filter=filter_expr,
                    as_task=as_task,
                    count_as=count_as_str,
                )
            )

        return sources

    def _parse_task_source_template_block(self) -> ir.TaskSourceTemplate:
        """Parse a per-row ``as_task:`` template block (#1015).

        Three string keys: ``icon`` (icon-token identifier),
        ``title`` (template string with ``{field}`` placeholders),
        ``meta`` (template string, optional).
        """
        icon_str: str = ""
        title_str: str = ""
        meta_str: str = ""
        _VALID_KEYS = {"icon", "title", "meta"}

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
        return ir.TaskSourceTemplate(icon=icon_str, title=title_str, meta=meta_str)

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

        Each entry must lead with ``- name:``. Required keys after
        ``name``: ``mode`` (one of halo / flags / mini_bars / stamps
        / thread_summary / quick_actions). Optional: source, filter,
        limit (1..100), fields (bracketed identifier list), actions
        (bracketed identifier list).
        """
        sections: list[ir.EntityCardSection] = []
        _VALID_MODES = {mode.value for mode in ir.EntityCardSectionMode}
        _VALID_KEYS = {"name", "mode", "source", "filter", "limit", "fields", "actions"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    "sections entries must start with `- name: <id>`",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()
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
            name_str = self.expect_identifier_or_keyword().value
            self.skip_newlines()

            mode_val: str | None = None
            source_str: str | None = None
            filter_expr: ir.ConditionExpr | None = None
            limit_val: int | None = None
            fields_list: list[str] = []
            actions_list: list[str] = []

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
                    if key == "mode":
                        mode_val = self.expect_identifier_or_keyword().value
                        if mode_val not in _VALID_MODES:
                            raise make_parse_error(
                                f"sections entry name={name_str!r}: mode "
                                f"must be one of {sorted(_VALID_MODES)}; "
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
                        self.expect(TokenType.LBRACKET)
                        while not self.match(TokenType.RBRACKET):
                            fields_list.append(self.expect_identifier_or_keyword().value)
                            if self.match(TokenType.COMMA):
                                self.advance()
                        self.expect(TokenType.RBRACKET)
                        self.skip_newlines()
                    elif key == "actions":
                        self.expect(TokenType.LBRACKET)
                        while not self.match(TokenType.RBRACKET):
                            actions_list.append(self.expect_identifier_or_keyword().value)
                            if self.match(TokenType.COMMA):
                                self.advance()
                        self.expect(TokenType.RBRACKET)
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown sections entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            if mode_val is None:
                tok = self.current_token()
                raise make_parse_error(
                    f"sections entry name={name_str!r} requires `mode:`.",
                    self.file,
                    tok.line,
                    tok.column,
                )
            sections.append(
                ir.EntityCardSection(
                    name=name_str,
                    mode=ir.EntityCardSectionMode(mode_val),
                    source=source_str,
                    filter=filter_expr,
                    limit=limit_val,
                    fields=fields_list,
                    actions=actions_list,
                )
            )

        return sections

    def _parse_status_entries_block(self) -> list[ir.StatusListEntrySpec]:
        """Parse the indented body of a status_list ``entries:`` block (#3).

        Each entry is a dash-list dict with ``title`` (required) plus
        optional ``copy`` / ``icon`` / ``state``::

            entries:
              - title: "Verified"
                copy: "Identity confirmed via SSO"
                icon: "check-circle"
                state: positive
              - title: "Pending review"
                copy: "Awaiting school admin sign-off"
                icon: "clock"
                state: warning

        ``state`` reuses the action_grid + metrics + notice tone
        vocabulary (positive / warning / destructive / accent / neutral).
        v0.61.69 (AegisMark UX patterns roadmap item #3). Source-bound
        variant deferred to a later cycle.
        """
        entries: list[ir.StatusListEntrySpec] = []
        _VALID_STATES = {"positive", "warning", "destructive", "neutral", "accent"}
        _VALID_KEYS = {"title", "caption", "icon", "state"}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            if not self.match(TokenType.MINUS):
                tok = self.current_token()
                raise make_parse_error(
                    'status_list entries must start with `- title: "..."`',
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()  # consume MINUS
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
            title_str = self.expect(TokenType.STRING).value
            self.skip_newlines()

            caption_str = ""
            icon_str = ""
            state_str = "neutral"

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
                    elif key == "icon":
                        icon_str = self.expect(TokenType.STRING).value
                        self.skip_newlines()
                    elif key == "state":
                        state_val = self.expect_identifier_or_keyword().value
                        if state_val not in _VALID_STATES:
                            raise make_parse_error(
                                f"status_list entry {title_str!r}: state must be one of "
                                f"{sorted(_VALID_STATES)}; got {state_val!r}",
                                self.file,
                                key_tok.line,
                                key_tok.column,
                            )
                        state_str = state_val
                        self.skip_newlines()
                    else:
                        raise make_parse_error(
                            f"Unknown status_list entry key {key!r}. "
                            f"Expected one of: {sorted(_VALID_KEYS)}.",
                            self.file,
                            key_tok.line,
                            key_tok.column,
                        )
                self.expect(TokenType.DEDENT)

            entries.append(
                ir.StatusListEntrySpec(
                    title=title_str,
                    caption=caption_str,
                    icon=icon_str,
                    state=state_str,
                )
            )
        return entries

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
        nav_ref: str | None = None
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

            # uses nav <name> — bind a shared nav definition (v0.61.95, #926)
            elif self.match(TokenType.USES) and self.peek_token().type == TokenType.NAV:
                self.advance()  # consume `uses`
                self.advance()  # consume `nav`
                nav_ref = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # nav_group "Label" [icon=name] [collapsed]:
            # group "Label" [icon=name] [collapsed]: (same shape, lighter
            # visual weight inside `nav <name>:` blocks but also accepted
            # inline so projects can use the shorter keyword everywhere)
            elif self.match(TokenType.NAV_GROUP, TokenType.GROUP):
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
            nav_ref=nav_ref,
            ux=ux_spec,
            access=access_spec,
            context_selector=context_selector,
            source=loc,
        )

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
    aggregates: dict[str, str] = field(default_factory=dict)
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
    state.display = ir.DisplayMode(parser.expect_identifier_or_keyword().value)
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
    """``aggregate:`` block — ``metric_name: expr`` per line (expr captured raw)."""
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
        expr_parts: list[str] = []
        while not parser.match(TokenType.NEWLINE, TokenType.DEDENT):
            expr_parts.append(parser.advance().value)
        state.aggregates[metric_name] = " ".join(expr_parts)
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


_WORKSPACE_REGION_IDENT_KEYWORDS: dict[str, KeywordParser[_WorkspaceRegionState]] = {
    "title": _kw_title,
    "primary_action": _kw_primary_action,
    "secondary_action": _kw_secondary_action,
    "cohort_strip_config": _kw_cohort_strip_config,
    "day_timeline_config": _kw_day_timeline_config,
    "task_inbox_config": _kw_task_inbox_config,
    "entity_card_config": _kw_entity_card_config,
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
    )
