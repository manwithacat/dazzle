"""Job parser mixin for the DAZZLE DSL (#953 cycle 1).

Parses ``job`` blocks — generic deferred-task definitions. Either
``trigger:`` (entity-event firing) or ``schedule:`` (cron) is required;
both can be present (entity event AND scheduled fallback). Cycle 1
covers parsing only — runtime worker / queue come in cycle 3.

DSL shape::

    job thumbnail_render "Generate thumbnail":
      trigger: on_create Manuscript when source_pdf is_set
      run: scripts/render_thumbnail.py
      retry: 3
      retry_backoff: exponential
      dead_letter: ManuscriptDeadLetter
      timeout: 60s

    job daily_summary "Daily metrics roll-up":
      schedule: cron("0 1 * * *")
      run: scripts/daily_summary.py
      timeout: 5m
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


class JobParserMixin:
    """Parser mixin for ``job`` blocks (#953)."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _is_keyword_as_identifier: Any

    def parse_job(self) -> ir.JobSpec:
        """Parse a ``job <name> "Title"?:`` block (#953).

        Refactored to dispatch-table style (follow-on to #1098). 6
        token-keyed `_j_kw_*` parsers + 1 IDENT-text-matched (`run`) +
        a tolerant `_on_unknown_job` that also bails the loop on EOF
        (mirrors the legacy ``DEDENT, EOF`` loop guard) + a
        `_build_job` builder enforcing at least one ``trigger:`` or
        ``schedule:`` clause.
        """
        self.expect(TokenType.JOB)
        name = self.expect_identifier_or_keyword().value

        title: str | None = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _JobState()
        try:
            parse_block_with_dispatch(
                self,
                first_class_keywords=_JOB_KEYWORDS,
                ident_keywords=_JOB_IDENT_KEYWORDS,
                state=state,
                on_unknown=_on_unknown_job,
            )
        except _StopJobLoop:
            pass

        # Legacy tolerates a missing DEDENT at EOF — only consume when present.
        if self.match(TokenType.DEDENT):
            self.advance()
        return _build_job(self, name, title, state)

    def _parse_job_trigger(self) -> ir.JobTrigger:
        """Parse `on_<event> <Entity> [when <condition>]`.

        Supported event keywords: ``on_create``, ``on_update``,
        ``on_delete``, ``on_field_changed``. Condition is captured as
        raw text up to end-of-line; cycle 3's worker evaluates it
        against the entity row.
        """
        head = self.expect_identifier_or_keyword().value
        event_map = {
            "on_create": "created",
            "on_update": "updated",
            "on_delete": "deleted",
            "on_field_changed": "field_changed",
        }
        if head not in event_map:
            tok = self.current_token()
            raise make_parse_error(
                f"Unknown job trigger event {head!r}; expected one of: {sorted(event_map.keys())}.",
                self.file,
                tok.line,
                tok.column,
            )
        event = event_map[head]
        entity = self.expect_identifier_or_keyword().value

        field: str | None = None
        when_condition: str | None = None

        if self.match(TokenType.DOT):
            self.advance()
            field = self.expect_identifier_or_keyword().value
        elif event == "field_changed":
            # #987 fix: `on_field_changed` requires a field name.
            # Pre-fix, `on_field_changed Ticket status` would parse
            # cleanly with field=None, then silently never fire at
            # runtime (cycle-6 should_fire returns False without a
            # field name). Two common-mistake forms hit this branch:
            #   1. `on_field_changed Ticket status` — space-separated
            #      (intuitive but wrong)
            #   2. `on_field_changed Ticket` — entirely missing
            tok = self.current_token()
            # If the next token is anything that *could* be a field
            # name (identifier or keyword-as-identifier), point the
            # author at the missing DOT. Otherwise give the generic
            # "missing field" message.
            looks_like_field = self.match(TokenType.IDENTIFIER) or self._is_keyword_as_identifier()
            if looks_like_field:
                raise make_parse_error(
                    f"`on_field_changed` requires a field name with "
                    f"DOT separator. Use `on_field_changed {entity}.{tok.value}`, "
                    f"not `on_field_changed {entity} {tok.value}`.",
                    self.file,
                    tok.line,
                    tok.column,
                )
            raise make_parse_error(
                f"`on_field_changed` requires a field name. "
                f"Use `on_field_changed {entity}.<field>` "
                "(e.g. `on_field_changed Ticket.status`).",
                self.file,
                tok.line,
                tok.column,
            )

        # Optional `when <condition...>` — slurp tokens up to newline.
        # Stored as raw text; cycle 3 wires the evaluator. `when` is a
        # keyword token in the DAZZLE lexer (not an identifier).
        if self.match(TokenType.WHEN):
            self.advance()
            condition_parts: list[str] = []
            while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                condition_parts.append(str(self.advance().value))
            when_condition = " ".join(condition_parts).strip() or None

        return ir.JobTrigger(
            entity=entity,
            event=event,
            field=field,
            when_condition=when_condition,
        )

    def _parse_job_schedule(self) -> ir.JobSchedule:
        """Parse `cron("0 1 * * *")` form. Other schedule forms can
        join in later cycles."""
        head = self.expect_identifier_or_keyword().value
        if head != "cron":
            tok = self.current_token()
            raise make_parse_error(
                f"Unknown schedule form {head!r}; only `cron(...)` is supported in cycle 1.",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.LPAREN)
        cron_token = self.expect(TokenType.STRING)
        self.expect(TokenType.RPAREN)
        return ir.JobSchedule(cron=str(cron_token.value))

    def _parse_path_value(self) -> str:
        """Parse a `run:` value — quoted string or bare path of
        identifiers, slashes, and dots."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        parts: list[str] = []
        while True:
            tok = self.current_token()
            if tok.type == TokenType.IDENTIFIER:
                parts.append(str(self.advance().value))
            elif tok.type == TokenType.SLASH:
                parts.append("/")
                self.advance()
            elif tok.type == TokenType.DOT:
                parts.append(".")
                self.advance()
            else:
                break
        return "".join(parts)

    def _parse_job_timeout(self) -> int:
        """Parse a duration token like ``60s``, ``5m``, ``1h``.

        Falls back to plain integer (interpreted as seconds) so
        ``timeout: 60`` still works.
        """
        tok = self.current_token()
        # The lexer emits DURATION_LITERAL for tokens like `5m`.
        if tok.type == TokenType.DURATION_LITERAL:
            self.advance()
            text = str(tok.value).strip()
            return _duration_to_seconds(text, file=self.file, line=tok.line, column=tok.column)
        if tok.type == TokenType.NUMBER:
            self.advance()
            return int(tok.value)
        raise make_parse_error(
            f"Expected duration (e.g. 60s, 5m) or integer seconds; got {tok.type.value}.",
            self.file,
            tok.line,
            tok.column,
        )


def _duration_to_seconds(text: str, *, file: Any, line: int, column: int) -> int:
    """Convert ``5m`` / ``60s`` / ``1h`` / ``2d`` into seconds."""
    if not text:
        raise make_parse_error("Empty duration literal.", file, line, column)
    suffix = text[-1].lower()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86_400}
    if suffix not in multipliers:
        # Fall through — treat as plain seconds (e.g. lexer may emit `60`)
        try:
            return int(text)
        except ValueError as exc:
            raise make_parse_error(
                f"Invalid duration {text!r}; expected suffix s|m|h|d or plain integer.",
                file,
                line,
                column,
            ) from exc
    try:
        magnitude = int(text[:-1])
    except ValueError as exc:
        raise make_parse_error(f"Invalid duration {text!r}.", file, line, column) from exc
    return magnitude * multipliers[suffix]


# ============================================================ #
# parse_job — keyword-dispatch decomposition (#1098 template)   #
# ============================================================ #
#
# The 118-line monolith was replaced (v0.70.27) with the dispatch
# pattern shipped in #1097. 6 token-keyed `_j_kw_*` + 1 IDENT-keyed
# (`run`) + a tolerant on_unknown that also bails the loop on EOF
# (mirrors the legacy ``DEDENT, EOF`` loop guard via a sentinel
# exception caught in `parse_job`) + a `_build_job` builder.


@dataclass
class _JobState:
    """Accumulator for :meth:`JobParserMixin.parse_job`."""

    triggers: list[ir.JobTrigger] = field(default_factory=list)
    schedule: ir.JobSchedule | None = None
    run: str = ""
    retry: int = 3
    retry_backoff: ir.JobBackoff = ir.JobBackoff.EXPONENTIAL
    dead_letter: str = ""
    timeout_seconds: int = 60


class _StopJobLoop(Exception):
    """Sentinel raised by ``_on_unknown_job`` at EOF to bail the dispatch loop.

    The dispatch helper's `while not match(DEDENT)` doesn't account for
    files that end without an emitted DEDENT (legitimate at top level).
    Raising here mirrors the legacy ``while not match(DEDENT, EOF)`` guard.
    """


# ---------- Keyword parsers ---------- #


def _j_kw_trigger(parser: Any, state: _JobState) -> None:
    """``trigger: on_<event> <Entity> [when <condition>]``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.triggers.append(parser._parse_job_trigger())
    parser.skip_newlines()


def _j_kw_schedule(parser: Any, state: _JobState) -> None:
    """``schedule: cron("...")``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.schedule = parser._parse_job_schedule()
    parser.skip_newlines()


def _j_kw_retry(parser: Any, state: _JobState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.retry = int(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _j_kw_retry_backoff(parser: Any, state: _JobState) -> None:
    """``retry_backoff: linear | exponential | none`` — enum-validated."""
    parser.advance()
    parser.expect(TokenType.COLON)
    backoff_token = parser.expect_identifier_or_keyword()
    try:
        state.retry_backoff = ir.JobBackoff(backoff_token.value)
    except ValueError as exc:
        raise make_parse_error(
            f"Invalid retry_backoff {backoff_token.value!r}; "
            f"must be one of: none, linear, exponential.",
            parser.file,
            backoff_token.line,
            backoff_token.column,
        ) from exc
    parser.skip_newlines()


def _j_kw_dead_letter(parser: Any, state: _JobState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.dead_letter = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _j_kw_timeout(parser: Any, state: _JobState) -> None:
    """``timeout: <duration>`` (10s, 5m, 1h) via the mixin's duration parser."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.timeout_seconds = parser._parse_job_timeout()
    parser.skip_newlines()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _j_kw_run(parser: Any, state: _JobState) -> None:
    """``run: <path>`` — IDENT-keyed because ``run`` is not a lexer keyword."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.run = parser._parse_path_value()
    parser.skip_newlines()


# ---------- Dispatch tables + on_unknown + builder ---------- #


_JOB_KEYWORDS: dict[TokenType, KeywordParser[_JobState]] = {
    TokenType.TRIGGER: _j_kw_trigger,
    TokenType.SCHEDULE: _j_kw_schedule,
    TokenType.RETRY: _j_kw_retry,
    TokenType.RETRY_BACKOFF: _j_kw_retry_backoff,
    TokenType.DEAD_LETTER: _j_kw_dead_letter,
    TokenType.TIMEOUT: _j_kw_timeout,
}


_JOB_IDENT_KEYWORDS: dict[str, KeywordParser[_JobState]] = {
    "run": _j_kw_run,
}


def _on_unknown_job(parser: Any) -> None:
    """Tolerate unknown keywords; bail the loop on EOF (mirrors legacy guard).

    The original ``while not match(DEDENT, EOF)`` exited cleanly at end
    of file; the dispatch helper only checks for DEDENT. Raise the
    sentinel here so ``parse_job`` can catch and consume any trailing
    DEDENT before assembling the IR.
    """
    if parser.match(TokenType.EOF):
        raise _StopJobLoop()
    parser.advance()
    parser.skip_newlines()


def _build_job(parser: Any, name: str, title: str | None, state: _JobState) -> ir.JobSpec:
    """Enforce trigger OR schedule, then assemble the IR."""
    if not state.triggers and state.schedule is None:
        tok = parser.current_token()
        raise make_parse_error(
            f"Job '{name}' requires either a `trigger:` or a `schedule:` clause.",
            parser.file,
            tok.line,
            tok.column,
        )

    return ir.JobSpec(
        name=name,
        title=title,
        run=state.run,
        triggers=state.triggers,
        schedule=state.schedule,
        retry=state.retry,
        retry_backoff=state.retry_backoff,
        dead_letter=state.dead_letter,
        timeout_seconds=state.timeout_seconds,
    )
