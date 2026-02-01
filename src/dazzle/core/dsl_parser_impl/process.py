"""
Process parser mixin for DAZZLE DSL.

Parses process and schedule blocks for durable workflow definitions.

DSL Syntax (v0.23.0):
    process order_fulfillment "Order Fulfillment":
      implements: [ST-001]

      trigger:
        when: entity Order status -> confirmed

      input:
        order_id: uuid required

      steps:
        - step validate:
            service: check_inventory
            timeout: 30s

        - step charge:
            service: process_payment
            timeout: 2m
            retry:
              max_attempts: 3
              backoff: exponential

      timeout: 24h

    schedule daily_report "Daily Report":
      cron: "0 8 * * *"
      timezone: "Europe/London"

      steps:
        - step generate:
            service: generate_report
            timeout: 5m
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


def parse_duration(s: str) -> int:
    """
    Parse duration string to seconds.

    Examples: "30s", "5m", "2h", "7d", "24h"
    """
    match = re.match(r"^(\d+)([smhd])$", s.strip())
    if not match:
        raise ValueError(f"Invalid duration format: {s}")

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }

    return value * multipliers[unit]


class ProcessParserMixin:
    """Parser mixin for process and schedule blocks."""

    # Type stubs for methods provided by BaseParser
    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_process(self) -> ir.ProcessSpec:
        """
        Parse a process block.

        Grammar:
            process IDENTIFIER STRING? COLON NEWLINE INDENT
              [implements COLON LBRACKET identifier_list RBRACKET NEWLINE]
              [trigger COLON NEWLINE trigger_block]
              [input COLON NEWLINE input_block]
              [output COLON NEWLINE output_block]
              [steps COLON NEWLINE steps_block]
              [compensations COLON NEWLINE compensations_block]
              [timeout COLON DURATION NEWLINE]
              [overlap COLON IDENTIFIER NEWLINE]
              [emits COLON NEWLINE emits_block]
            DEDENT

        Returns:
            ProcessSpec with parsed values
        """
        self.expect(TokenType.PROCESS)
        name = self.expect_identifier_or_keyword().value

        # Optional title
        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse description if present (docstring-style)
        description = None
        if self.match(TokenType.STRING):
            description = str(self.advance().value)
            self.skip_newlines()

        # Initialize fields
        implements: list[str] = []
        trigger: ir.ProcessTriggerSpec | None = None
        inputs: list[ir.ProcessInputField] = []
        outputs: list[ir.ProcessOutputField] = []
        steps: list[ir.ProcessStepSpec] = []
        compensations: list[ir.CompensationSpec] = []
        timeout_seconds: int = 86400  # Default 24h
        overlap_policy: ir.OverlapPolicy = ir.OverlapPolicy.SKIP
        events: ir.ProcessEventEmission = ir.ProcessEventEmission()

        # Parse process fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IMPLEMENTS):
                self.advance()
                self.expect(TokenType.COLON)
                implements = self._parse_process_identifier_list()
                self.skip_newlines()

            elif self.match(TokenType.TRIGGER):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                trigger = self._parse_process_trigger()

            elif self.match(TokenType.INPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                inputs = self._parse_process_inputs()

            elif self.match(TokenType.OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                outputs = self._parse_process_outputs()

            elif self.match(TokenType.STEPS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                steps = self._parse_process_steps()

            elif self.match(TokenType.COMPENSATIONS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                compensations = self._parse_compensations()

            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_str = self._parse_duration_value()
                timeout_seconds = parse_duration(timeout_str)
                self.skip_newlines()

            elif self.match(TokenType.OVERLAP):
                self.advance()
                self.expect(TokenType.COLON)
                overlap_str = self.expect_identifier_or_keyword().value
                overlap_policy = self._parse_overlap_policy(str(overlap_str))
                self.skip_newlines()

            elif self.match(TokenType.EMITS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                events = self._parse_process_emits()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_process_field()

        self.expect(TokenType.DEDENT)

        return ir.ProcessSpec(
            name=str(name),
            title=title,
            description=description,
            implements=implements,
            trigger=trigger,
            inputs=inputs,
            outputs=outputs,
            steps=steps,
            compensations=compensations,
            timeout_seconds=timeout_seconds,
            overlap_policy=overlap_policy,
            events=events,
        )

    def parse_schedule(self) -> ir.ScheduleSpec:
        """
        Parse a schedule block.

        Grammar:
            schedule IDENTIFIER STRING? COLON NEWLINE INDENT
              [implements COLON LBRACKET identifier_list RBRACKET NEWLINE]
              cron COLON STRING NEWLINE | interval COLON DURATION NEWLINE
              [timezone COLON STRING NEWLINE]
              [catch_up COLON BOOL NEWLINE]
              [overlap COLON IDENTIFIER NEWLINE]
              [steps COLON NEWLINE steps_block]
              [timeout COLON DURATION NEWLINE]
              [emits COLON NEWLINE emits_block]
            DEDENT

        Returns:
            ScheduleSpec with parsed values
        """
        self.expect(TokenType.SCHEDULE)
        name = self.expect_identifier_or_keyword().value

        # Optional title
        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse description if present
        description = None
        if self.match(TokenType.STRING):
            description = str(self.advance().value)
            self.skip_newlines()

        # Initialize fields
        implements: list[str] = []
        cron: str | None = None
        interval_seconds: int | None = None
        timezone: str = "UTC"
        catch_up: bool = False
        overlap: ir.OverlapPolicy = ir.OverlapPolicy.SKIP
        steps: list[ir.ProcessStepSpec] = []
        timeout_seconds: int = 3600  # Default 1h
        events: ir.ProcessEventEmission = ir.ProcessEventEmission()

        # Parse schedule fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IMPLEMENTS):
                self.advance()
                self.expect(TokenType.COLON)
                implements = self._parse_process_identifier_list()
                self.skip_newlines()

            elif self.match(TokenType.CRON):
                self.advance()
                self.expect(TokenType.COLON)
                cron = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif self.match(TokenType.INTERVAL):
                self.advance()
                self.expect(TokenType.COLON)
                interval_str = self._parse_duration_value()
                interval_seconds = parse_duration(interval_str)
                self.skip_newlines()

            elif self.match(TokenType.TIMEZONE):
                self.advance()
                self.expect(TokenType.COLON)
                timezone = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif self.match(TokenType.CATCH_UP):
                self.advance()
                self.expect(TokenType.COLON)
                catch_up_token = self.expect_identifier_or_keyword()
                catch_up = str(catch_up_token.value).lower() == "true"
                self.skip_newlines()

            elif self.match(TokenType.OVERLAP):
                self.advance()
                self.expect(TokenType.COLON)
                overlap_str = self.expect_identifier_or_keyword().value
                overlap = self._parse_overlap_policy(str(overlap_str))
                self.skip_newlines()

            elif self.match(TokenType.STEPS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                steps = self._parse_process_steps()

            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_str = self._parse_duration_value()
                timeout_seconds = parse_duration(timeout_str)
                self.skip_newlines()

            elif self.match(TokenType.EMITS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                events = self._parse_process_emits()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_process_field()

        self.expect(TokenType.DEDENT)

        return ir.ScheduleSpec(
            name=str(name),
            title=title,
            description=description,
            implements=implements,
            cron=cron,
            interval_seconds=interval_seconds,
            timezone=timezone,
            catch_up=catch_up,
            overlap=overlap,
            steps=steps,
            timeout_seconds=timeout_seconds,
            events=events,
        )

    def _parse_process_identifier_list(self) -> list[str]:
        """Parse a bracketed list of identifiers: [A, B, C] or inline identifier."""
        items: list[str] = []

        if self.match(TokenType.LBRACKET):
            self.advance()

            while not self.match(TokenType.RBRACKET):
                self.skip_newlines()
                if self.match(TokenType.RBRACKET):
                    break

                # Handle compound IDs like ST-001
                item = self._parse_process_compound_id()
                items.append(item)

                if self.match(TokenType.COMMA):
                    self.advance()
                else:
                    break

            self.expect(TokenType.RBRACKET)
        else:
            # Single identifier
            item = self._parse_process_compound_id()
            items.append(item)

        return items

    def _parse_process_compound_id(self) -> str:
        """Parse a compound ID like ST-001 or a simple identifier."""
        parts: list[str] = []

        while not self.match(
            TokenType.COMMA,
            TokenType.RBRACKET,
            TokenType.NEWLINE,
            TokenType.DEDENT,
            TokenType.EOF,
            TokenType.COLON,
        ):
            token = self.current_token()
            parts.append(str(token.value))
            self.advance()

        return "".join(parts)

    def _parse_process_trigger(self) -> ir.ProcessTriggerSpec:
        """
        Parse a process trigger specification.

        Grammar:
            INDENT
              when COLON trigger_expr NEWLINE
            DEDENT

        trigger_expr can be:
          - entity ENTITY_NAME created|updated|deleted
          - entity ENTITY_NAME status ARROW STATUS
          - manual
          - signal SIGNAL_NAME
          - process PROCESS_NAME completed
        """
        if not self.match(TokenType.INDENT):
            # Inline trigger
            return self._parse_trigger_expression()

        self.expect(TokenType.INDENT)

        trigger: ir.ProcessTriggerSpec | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                trigger = self._parse_trigger_expression()
                self.skip_newlines()
            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)

        if trigger is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Process trigger block missing 'when' clause",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return trigger

    def _parse_trigger_expression(self) -> ir.ProcessTriggerSpec:
        """Parse a trigger expression."""
        token = self.current_token()
        trigger_word = str(token.value).lower()

        if trigger_word == "entity":
            self.advance()
            entity_name = str(self.expect_identifier_or_keyword().value)

            # Check for status transition or simple event
            next_token = self.current_token()
            next_val = str(next_token.value).lower()

            if next_val == "status":
                self.advance()
                # Expect arrow syntax: -> status_name
                if self.match(TokenType.ARROW):
                    self.advance()
                    to_status = str(self.expect_identifier_or_keyword().value)
                    return ir.ProcessTriggerSpec(
                        kind=ir.ProcessTriggerKind.ENTITY_STATUS_TRANSITION,
                        entity_name=entity_name,
                        to_status=to_status,
                    )
                else:
                    from_status = str(self.expect_identifier_or_keyword().value)
                    self.expect(TokenType.ARROW)
                    to_status = str(self.expect_identifier_or_keyword().value)
                    return ir.ProcessTriggerSpec(
                        kind=ir.ProcessTriggerKind.ENTITY_STATUS_TRANSITION,
                        entity_name=entity_name,
                        from_status=from_status,
                        to_status=to_status,
                    )
            elif next_val in ("created", "updated", "deleted"):
                self.advance()
                return ir.ProcessTriggerSpec(
                    kind=ir.ProcessTriggerKind.ENTITY_EVENT,
                    entity_name=entity_name,
                    event_type=next_val,
                )
            else:
                from ..errors import make_parse_error

                raise make_parse_error(
                    "Invalid entity trigger: expected 'status', 'created',"
                    f" 'updated', or 'deleted', got '{next_val}'",
                    self.file,
                    next_token.line,
                    next_token.column,
                )

        elif trigger_word == "manual":
            self.advance()
            return ir.ProcessTriggerSpec(kind=ir.ProcessTriggerKind.MANUAL)

        elif trigger_word == "signal":
            self.advance()
            signal_name = str(self.expect_identifier_or_keyword().value)
            # Signal triggers don't have signal_name field in our model,
            # we use process_name field for signal name
            return ir.ProcessTriggerSpec(
                kind=ir.ProcessTriggerKind.SIGNAL,
                process_name=signal_name,
            )

        elif trigger_word == "process":
            self.advance()
            process_name = str(self.expect_identifier_or_keyword().value)
            # Expect "completed"
            self.expect_identifier_or_keyword()  # consume "completed"
            return ir.ProcessTriggerSpec(
                kind=ir.ProcessTriggerKind.PROCESS_COMPLETED,
                process_name=process_name,
            )

        else:
            from ..errors import make_parse_error

            raise make_parse_error(
                f"Invalid trigger type: {trigger_word}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_process_inputs(self) -> list[ir.ProcessInputField]:
        """Parse process input fields."""
        inputs: list[ir.ProcessInputField] = []

        if not self.match(TokenType.INDENT):
            return inputs

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            name = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)

            # Parse type
            field_type = str(self.expect_identifier_or_keyword().value)

            # Parse modifiers
            required = False
            default = None
            description = None

            while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                token = self.current_token()
                val = str(token.value).lower()
                if val == "required":
                    required = True
                    self.advance()
                elif self.match(TokenType.EQUALS):
                    self.advance()
                    default = str(self.expect(TokenType.STRING).value)
                elif self.match(TokenType.STRING):
                    description = str(self.advance().value)
                else:
                    self.advance()

            inputs.append(
                ir.ProcessInputField(
                    name=name,
                    type=field_type,
                    required=required,
                    default=default,
                    description=description,
                )
            )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return inputs

    def _parse_process_outputs(self) -> list[ir.ProcessOutputField]:
        """Parse process output fields."""
        outputs: list[ir.ProcessOutputField] = []

        if not self.match(TokenType.INDENT):
            return outputs

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            name = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)

            # Parse type
            field_type = str(self.expect_identifier_or_keyword().value)

            # Optional description
            description = None
            if self.match(TokenType.STRING):
                description = str(self.advance().value)

            outputs.append(
                ir.ProcessOutputField(
                    name=name,
                    type=field_type,
                    description=description,
                )
            )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return outputs

    def _parse_process_steps(self) -> list[ir.ProcessStepSpec]:
        """Parse process steps."""
        steps: list[ir.ProcessStepSpec] = []

        if not self.match(TokenType.INDENT):
            return steps

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Expect - step or - parallel
            if self.match(TokenType.MINUS):
                self.advance()

                if self.match(TokenType.STEP):
                    step = self._parse_single_step()
                    steps.append(step)
                elif self.match(TokenType.PARALLEL):
                    step = self._parse_parallel_block()
                    steps.append(step)
                else:
                    # Skip unknown
                    self.advance()
                    self._skip_to_next_step()
            else:
                # Skip unknown token
                self.advance()

        self.expect(TokenType.DEDENT)
        return steps

    def _parse_single_step(self) -> ir.ProcessStepSpec:
        """
        Parse a single step.

        Grammar:
            step IDENTIFIER COLON NEWLINE INDENT
              service COLON IDENTIFIER NEWLINE |
              channel COLON IDENTIFIER message COLON IDENTIFIER NEWLINE |
              wait COLON DURATION NEWLINE |
              human_task COLON NEWLINE human_task_block |
              subprocess COLON IDENTIFIER NEWLINE
              [timeout COLON DURATION NEWLINE]
              [retry COLON NEWLINE retry_block]
              [inputs COLON NEWLINE inputs_block]
              [on_success COLON IDENTIFIER|complete|fail NEWLINE]
              [on_failure COLON IDENTIFIER|complete|fail NEWLINE]
              [compensate COLON IDENTIFIER NEWLINE]
            DEDENT
        """
        self.expect(TokenType.STEP)
        name = str(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Initialize step fields
        kind: ir.ProcessStepKind = ir.ProcessStepKind.SERVICE
        service: str | None = None
        channel: str | None = None
        message: str | None = None
        wait_duration_seconds: int | None = None
        wait_for_signal: str | None = None
        human_task: ir.HumanTaskSpec | None = None
        subprocess: str | None = None
        inputs: list[ir.InputMapping] = []
        output_mapping: str | None = None
        timeout_seconds: int = 30
        retry: ir.RetryConfig | None = None
        on_success: str | None = None
        on_failure: str | None = None
        compensate_with: str | None = None
        condition: str | None = None
        on_true: str | None = None
        on_false: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SERVICE):
                self.advance()
                self.expect(TokenType.COLON)
                service = str(self.expect_identifier_or_keyword().value)
                kind = ir.ProcessStepKind.SERVICE
                self.skip_newlines()

            elif self.match(TokenType.CHANNEL):
                self.advance()
                self.expect(TokenType.COLON)
                channel = str(self.expect_identifier_or_keyword().value)
                kind = ir.ProcessStepKind.SEND
                self.skip_newlines()

            elif self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.WAIT):
                self.advance()
                self.expect(TokenType.COLON)
                kind = ir.ProcessStepKind.WAIT
                # Could be duration or signal
                wait_val = self._parse_duration_or_signal()
                if isinstance(wait_val, int):
                    wait_duration_seconds = wait_val
                else:
                    wait_for_signal = wait_val
                self.skip_newlines()

            elif self.match(TokenType.HUMAN_TASK):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                human_task = self._parse_human_task()
                kind = ir.ProcessStepKind.HUMAN_TASK

            elif self.match(TokenType.SUBPROCESS):
                self.advance()
                self.expect(TokenType.COLON)
                subprocess = str(self.expect_identifier_or_keyword().value)
                kind = ir.ProcessStepKind.SUBPROCESS
                self.skip_newlines()

            elif self.match(TokenType.CONDITION):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self._parse_condition_string()
                kind = ir.ProcessStepKind.CONDITION
                self.skip_newlines()

            elif self.match(TokenType.ON_TRUE):
                self.advance()
                self.expect(TokenType.COLON)
                on_true = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.ON_FALSE):
                self.advance()
                self.expect(TokenType.COLON)
                on_false = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.GOTO):
                self.advance()
                self.expect(TokenType.COLON)
                # Could be on_true or on_false in condition context
                # For now, treat as on_success
                on_success = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.ON_SUCCESS):
                self.advance()
                self.expect(TokenType.COLON)
                on_success = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.ON_FAILURE):
                self.advance()
                self.expect(TokenType.COLON)
                on_failure = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.COMPENSATE):
                self.advance()
                self.expect(TokenType.COLON)
                compensate_with = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_str = self._parse_duration_value()
                timeout_seconds = parse_duration(timeout_str)
                self.skip_newlines()

            elif self.match(TokenType.RETRY):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                retry = self._parse_retry_config()

            elif self.match(TokenType.INPUTS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                inputs = self._parse_input_mappings()

            elif self.match(TokenType.OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                output_mapping = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_step_field()

        self.expect(TokenType.DEDENT)

        return ir.ProcessStepSpec(
            name=name,
            kind=kind,
            service=service,
            channel=channel,
            message=message,
            wait_duration_seconds=wait_duration_seconds,
            wait_for_signal=wait_for_signal,
            human_task=human_task,
            subprocess=subprocess,
            condition=condition,
            on_true=on_true,
            on_false=on_false,
            inputs=inputs,
            output_mapping=output_mapping,
            timeout_seconds=timeout_seconds,
            retry=retry,
            on_success=on_success,
            on_failure=on_failure,
            compensate_with=compensate_with,
        )

    def _parse_parallel_block(self) -> ir.ProcessStepSpec:
        """
        Parse a parallel step block.

        Grammar:
            parallel IDENTIFIER COLON NEWLINE INDENT
              (- step IDENTIFIER COLON NEWLINE step_block)*
              [on_any_failure COLON IDENTIFIER NEWLINE]
            DEDENT
        """
        self.expect(TokenType.PARALLEL)
        name = str(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        parallel_steps: list[ir.ProcessStepSpec] = []
        parallel_policy: ir.ParallelFailurePolicy = ir.ParallelFailurePolicy.FAIL_FAST

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                if self.match(TokenType.STEP):
                    step = self._parse_single_step()
                    parallel_steps.append(step)
                else:
                    # Skip unknown
                    self.advance()
            elif self.match(TokenType.ON_ANY_FAILURE):
                self.advance()
                self.expect(TokenType.COLON)
                policy_str = str(self.expect_identifier_or_keyword().value)
                parallel_policy = self._parse_parallel_policy(policy_str)
                self.skip_newlines()
            else:
                # Skip unknown token
                self.advance()

        self.expect(TokenType.DEDENT)

        return ir.ProcessStepSpec(
            name=name,
            kind=ir.ProcessStepKind.PARALLEL,
            parallel_steps=parallel_steps,
            parallel_policy=parallel_policy,
        )

    def _parse_compensations(self) -> list[ir.CompensationSpec]:
        """Parse compensation handlers."""
        compensations: list[ir.CompensationSpec] = []

        if not self.match(TokenType.INDENT):
            return compensations

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                comp = self._parse_single_compensation()
                compensations.append(comp)
            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)
        return compensations

    def _parse_single_compensation(self) -> ir.CompensationSpec:
        """Parse a single compensation handler."""
        name = str(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.COLON)
        self.skip_newlines()

        service: str | None = None
        inputs: list[ir.InputMapping] = []
        timeout_seconds: int = 30

        if self.match(TokenType.INDENT):
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                if self.match(TokenType.SERVICE):
                    self.advance()
                    self.expect(TokenType.COLON)
                    service = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif self.match(TokenType.TIMEOUT):
                    self.advance()
                    self.expect(TokenType.COLON)
                    timeout_str = self._parse_duration_value()
                    timeout_seconds = parse_duration(timeout_str)
                    self.skip_newlines()

                elif self.match(TokenType.INPUTS):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    inputs = self._parse_input_mappings()

                else:
                    # Skip unknown
                    self.advance()

            self.expect(TokenType.DEDENT)

        return ir.CompensationSpec(
            name=name,
            service=service,
            inputs=inputs,
            timeout_seconds=timeout_seconds,
        )

    def _parse_human_task(self) -> ir.HumanTaskSpec:
        """Parse human task specification."""
        surface: str = ""
        entity_path: str | None = None
        assignee_role: str | None = None
        assignee_expression: str | None = None
        timeout_seconds: int = 604800  # Default 7 days
        escalation_timeout_seconds: int | None = None
        outcomes: list[ir.HumanTaskOutcome] = []

        if self.match(TokenType.INDENT):
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                if self.match(TokenType.SURFACE):
                    self.advance()
                    self.expect(TokenType.COLON)
                    surface = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif self.match(TokenType.ENTITY):
                    self.advance()
                    self.expect(TokenType.COLON)
                    entity_path = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif self.match(TokenType.ASSIGNEE_ROLE):
                    self.advance()
                    self.expect(TokenType.COLON)
                    assignee_role = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif self.match(TokenType.ASSIGNEE):
                    self.advance()
                    self.expect(TokenType.COLON)
                    assignee_expression = self._parse_condition_string()
                    self.skip_newlines()

                elif self.match(TokenType.TIMEOUT):
                    self.advance()
                    self.expect(TokenType.COLON)
                    timeout_str = self._parse_duration_value()
                    timeout_seconds = parse_duration(timeout_str)
                    self.skip_newlines()

                elif self.match(TokenType.OUTCOMES):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    outcomes = self._parse_task_outcomes()

                else:
                    # Skip unknown
                    self.advance()

            self.expect(TokenType.DEDENT)

        return ir.HumanTaskSpec(
            surface=surface,
            entity_path=entity_path,
            assignee_role=assignee_role,
            assignee_expression=assignee_expression,
            timeout_seconds=timeout_seconds,
            escalation_timeout_seconds=escalation_timeout_seconds,
            outcomes=outcomes,
        )

    def _parse_task_outcomes(self) -> list[ir.HumanTaskOutcome]:
        """Parse human task outcomes."""
        outcomes: list[ir.HumanTaskOutcome] = []

        if not self.match(TokenType.INDENT):
            return outcomes

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                outcome = self._parse_single_outcome()
                outcomes.append(outcome)
            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)
        return outcomes

    def _parse_single_outcome(self) -> ir.HumanTaskOutcome:
        """Parse a single task outcome."""
        name = str(self.expect_identifier_or_keyword().value)
        label = name  # Default label is the name
        goto = "complete"
        sets: list[ir.FieldAssignment] = []
        confirm: str | None = None
        style: str = "primary"

        if self.match(TokenType.STRING):
            label = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()

        if self.match(TokenType.INDENT):
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                token = self.current_token()
                field = str(token.value).lower()

                if field == "label":
                    self.advance()
                    self.expect(TokenType.COLON)
                    label = str(self.expect(TokenType.STRING).value)
                    self.skip_newlines()

                elif field == "goto" or self.match(TokenType.GOTO):
                    self.advance()
                    self.expect(TokenType.COLON)
                    goto = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif field == "sets" or self.match(TokenType.SETS):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    sets = self._parse_field_assignments()

                elif field == "confirm" or self.match(TokenType.CONFIRM):
                    self.advance()
                    self.expect(TokenType.COLON)
                    confirm = str(self.expect(TokenType.STRING).value)
                    self.skip_newlines()

                elif field == "style":
                    self.advance()
                    self.expect(TokenType.COLON)
                    style = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                else:
                    # Skip unknown
                    self.advance()

            self.expect(TokenType.DEDENT)

        return ir.HumanTaskOutcome(
            name=name,
            label=label,
            goto=goto,
            sets=sets,
            confirm=confirm,
            style=style,
        )

    def _parse_field_assignments(self) -> list[ir.FieldAssignment]:
        """Parse field assignment list."""
        assignments: list[ir.FieldAssignment] = []

        if not self.match(TokenType.INDENT):
            return assignments

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                # Parse Entity.field -> value
                field_path = self._parse_dotted_path()
                self.expect(TokenType.ARROW)
                value = self._parse_field_value()
                assignments.append(
                    ir.FieldAssignment(
                        field_path=field_path,
                        value=value,
                    )
                )
                self.skip_newlines()
            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)
        return assignments

    def _parse_input_mappings(self) -> list[ir.InputMapping]:
        """Parse input mapping list."""
        mappings: list[ir.InputMapping] = []

        if not self.match(TokenType.INDENT):
            return mappings

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                # Parse source -> target
                source = self._parse_dotted_path()
                self.expect(TokenType.ARROW)
                target = str(self.expect_identifier_or_keyword().value)
                mappings.append(
                    ir.InputMapping(
                        source=source,
                        target=target,
                    )
                )
                self.skip_newlines()
            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)
        return mappings

    def _parse_retry_config(self) -> ir.RetryConfig:
        """Parse retry configuration."""
        max_attempts: int = 3
        initial_interval_seconds: int = 1
        backoff: ir.ProcessRetryBackoff = ir.ProcessRetryBackoff.EXPONENTIAL
        backoff_coefficient: float = 2.0
        max_interval_seconds: int = 60

        if self.match(TokenType.INDENT):
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                if self.match(TokenType.MAX_ATTEMPTS):
                    self.advance()
                    self.expect(TokenType.COLON)
                    max_attempts = int(self.expect(TokenType.NUMBER).value)
                    self.skip_newlines()

                elif self.match(TokenType.BACKOFF):
                    self.advance()
                    self.expect(TokenType.COLON)
                    backoff_str = str(self.expect_identifier_or_keyword().value)
                    backoff = self._parse_backoff_strategy(backoff_str)
                    self.skip_newlines()

                elif self.match(TokenType.INTERVAL):
                    self.advance()
                    self.expect(TokenType.COLON)
                    interval_str = self._parse_duration_value()
                    initial_interval_seconds = parse_duration(interval_str)
                    self.skip_newlines()

                else:
                    # Skip unknown
                    self.advance()

            self.expect(TokenType.DEDENT)

        return ir.RetryConfig(
            max_attempts=max_attempts,
            initial_interval_seconds=initial_interval_seconds,
            backoff=backoff,
            backoff_coefficient=backoff_coefficient,
            max_interval_seconds=max_interval_seconds,
        )

    def _parse_process_emits(self) -> ir.ProcessEventEmission:
        """Parse process event emission configuration."""
        on_start: str | None = None
        on_complete: str | None = None
        on_failure: str | None = None

        if self.match(TokenType.INDENT):
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                token = self.current_token()
                field = str(token.value).lower()

                if field == "on_start":
                    self.advance()
                    self.expect(TokenType.COLON)
                    on_start = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif field == "on_complete":
                    self.advance()
                    self.expect(TokenType.COLON)
                    on_complete = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                elif field == "on_failure":
                    self.advance()
                    self.expect(TokenType.COLON)
                    on_failure = str(self.expect_identifier_or_keyword().value)
                    self.skip_newlines()

                else:
                    # Skip unknown
                    self.advance()

            self.expect(TokenType.DEDENT)

        return ir.ProcessEventEmission(
            on_start=on_start,
            on_complete=on_complete,
            on_failure=on_failure,
        )

    # Helper methods

    def _parse_duration_value(self) -> str:
        """Parse a duration value like 30s, 5m, 2h, 7d."""
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(str(token.value))
            self.advance()
        return "".join(parts)

    def _parse_duration_or_signal(self) -> int | str:
        """Parse either a duration or a signal name."""
        token = self.current_token()
        val = str(token.value)

        # Try to parse as duration
        if re.match(r"^\d+[smhd]$", val):
            self.advance()
            return parse_duration(val)

        # Otherwise treat as signal name
        self.advance()
        return val

    def _parse_overlap_policy(self, policy_str: str) -> ir.OverlapPolicy:
        """Parse overlap policy string."""
        policy_map = {
            "skip": ir.OverlapPolicy.SKIP,
            "queue": ir.OverlapPolicy.QUEUE,
            "cancel_previous": ir.OverlapPolicy.CANCEL_PREVIOUS,
            "allow": ir.OverlapPolicy.ALLOW,
        }
        return policy_map.get(policy_str.lower(), ir.OverlapPolicy.SKIP)

    def _parse_parallel_policy(self, policy_str: str) -> ir.ParallelFailurePolicy:
        """Parse parallel failure policy string."""
        policy_map = {
            "fail_fast": ir.ParallelFailurePolicy.FAIL_FAST,
            "wait_all": ir.ParallelFailurePolicy.WAIT_ALL,
            "rollback": ir.ParallelFailurePolicy.ROLLBACK,
        }
        return policy_map.get(policy_str.lower(), ir.ParallelFailurePolicy.FAIL_FAST)

    def _parse_backoff_strategy(self, backoff_str: str) -> ir.ProcessRetryBackoff:
        """Parse backoff strategy string."""
        backoff_map = {
            "fixed": ir.ProcessRetryBackoff.FIXED,
            "exponential": ir.ProcessRetryBackoff.EXPONENTIAL,
            "linear": ir.ProcessRetryBackoff.LINEAR,
        }
        return backoff_map.get(backoff_str.lower(), ir.ProcessRetryBackoff.EXPONENTIAL)

    def _parse_condition_string(self) -> str:
        """Parse a condition expression until newline."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(str(token.value))
            self.advance()

        return " ".join(parts)

    def _parse_dotted_path(self) -> str:
        """Parse a dotted path like Entity.field."""
        parts: list[str] = []
        parts.append(str(self.expect_identifier_or_keyword().value))

        while self.match(TokenType.DOT):
            self.advance()
            parts.append(str(self.expect_identifier_or_keyword().value))

        return ".".join(parts)

    def _parse_field_value(self) -> str:
        """Parse a field value (string or identifier)."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        return str(self.expect_identifier_or_keyword().value)

    def _skip_to_next_process_field(self) -> None:
        """Skip tokens until we reach the next process field or end of block."""
        while not self.match(
            TokenType.IMPLEMENTS,
            TokenType.TRIGGER,
            TokenType.INPUT,
            TokenType.OUTPUT,
            TokenType.STEPS,
            TokenType.COMPENSATIONS,
            TokenType.TIMEOUT,
            TokenType.OVERLAP,
            TokenType.EMITS,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()

    def _skip_to_next_step(self) -> None:
        """Skip tokens until we reach the next step or end of block."""
        while not self.match(
            TokenType.MINUS,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()

    def _skip_to_next_step_field(self) -> None:
        """Skip tokens until we reach the next step field or end of block."""
        while not self.match(
            TokenType.SERVICE,
            TokenType.CHANNEL,
            TokenType.MESSAGE,
            TokenType.WAIT,
            TokenType.HUMAN_TASK,
            TokenType.SUBPROCESS,
            TokenType.CONDITION,
            TokenType.GOTO,
            TokenType.ON_SUCCESS,
            TokenType.ON_FAILURE,
            TokenType.COMPENSATE,
            TokenType.TIMEOUT,
            TokenType.RETRY,
            TokenType.INPUTS,
            TokenType.OUTPUT,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()
