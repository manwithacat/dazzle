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

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


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
        """Parse a `job <name> "title": ...` block."""
        self.expect(TokenType.JOB)
        name = self.expect_identifier_or_keyword().value

        title: str | None = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        triggers: list[ir.JobTrigger] = []
        schedule: ir.JobSchedule | None = None
        run = ""
        retry = 3
        retry_backoff = ir.JobBackoff.EXPONENTIAL
        dead_letter = ""
        timeout_seconds = 60

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            # trigger: on_<event> <Entity> [when <condition>]
            if self.match(TokenType.TRIGGER):
                self.advance()
                self.expect(TokenType.COLON)
                triggers.append(self._parse_job_trigger())
                self.skip_newlines()

            # schedule: cron("...")
            elif self.match(TokenType.SCHEDULE):
                self.advance()
                self.expect(TokenType.COLON)
                schedule = self._parse_job_schedule()
                self.skip_newlines()

            # run: <path>
            elif tok.type == TokenType.IDENTIFIER and tok.value == "run":
                self.advance()
                self.expect(TokenType.COLON)
                run = self._parse_path_value()
                self.skip_newlines()

            # retry: <int>
            elif self.match(TokenType.RETRY):
                self.advance()
                self.expect(TokenType.COLON)
                retry_token = self.expect(TokenType.NUMBER)
                retry = int(retry_token.value)
                self.skip_newlines()

            # retry_backoff: linear | exponential | none
            elif self.match(TokenType.RETRY_BACKOFF):
                self.advance()
                self.expect(TokenType.COLON)
                backoff_token = self.expect_identifier_or_keyword()
                try:
                    retry_backoff = ir.JobBackoff(backoff_token.value)
                except ValueError as exc:
                    raise make_parse_error(
                        f"Invalid retry_backoff {backoff_token.value!r}; "
                        f"must be one of: none, linear, exponential.",
                        self.file,
                        backoff_token.line,
                        backoff_token.column,
                    ) from exc
                self.skip_newlines()

            # dead_letter: <EntityName>
            elif self.match(TokenType.DEAD_LETTER):
                self.advance()
                self.expect(TokenType.COLON)
                dead_letter = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # timeout: <duration> (10s, 5m, 1h)
            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_seconds = self._parse_job_timeout()
                self.skip_newlines()

            else:
                # Unknown attribute — advance to keep parser making
                # progress. The validator surfaces this separately;
                # keeping the parser tolerant matches the existing
                # convention in notification.py.
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if not triggers and schedule is None:
            tok = self.current_token()
            raise make_parse_error(
                f"Job '{name}' requires either a `trigger:` or a `schedule:` clause.",
                self.file,
                tok.line,
                tok.column,
            )

        return ir.JobSpec(
            name=name,
            title=title,
            run=run,
            triggers=triggers,
            schedule=schedule,
            retry=retry,
            retry_backoff=retry_backoff,
            dead_letter=dead_letter,
            timeout_seconds=timeout_seconds,
        )

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
