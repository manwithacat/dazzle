"""
Messaging parsing for DAZZLE DSL.

Handles message, channel, asset, document, and template declarations.
Part of v0.9.0 Messaging Channels feature.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class MessagingParserMixin:
    """
    Mixin providing messaging construct parsing.

    Parses:
    - message: Typed message schemas
    - channel: Communication pathways (email, queue, stream)
    - asset: Static file references
    - document: Dynamic document generators
    - template: Email templates

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any
        parse_type_spec: Any
        parse_field_modifiers: Any

    # =========================================================================
    # Message Parsing
    # =========================================================================

    def parse_message(self) -> ir.MessageSpec:
        """Parse message declaration.

        DSL syntax:
            message OrderConfirmation "Order Confirmation Email":
              '''Sent to customers when their order is confirmed'''
              to: email required
              order_number: str required
              items: list[OrderItem] required
              total: money required
        """
        self.expect(TokenType.MESSAGE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description = None
        fields: list[ir.MessageFieldSpec] = []

        # Check for docstring (triple-quoted string would be parsed as STRING)
        self.skip_newlines()
        if self.match(TokenType.STRING):
            # Could be a docstring - check if it starts with triple quotes
            # For now, treat any leading string as description
            description = self.advance().value
            self.skip_newlines()

        # Parse fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            field = self._parse_message_field()
            fields.append(field)
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.MessageSpec(
            name=name,
            title=title,
            description=description,
            fields=fields,
        )

    def _parse_message_field(self) -> ir.MessageFieldSpec:
        """Parse a message field.

        Format:
            field_name: type_name [required] [default=value]
        """
        field_name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)

        # Parse type - could be simple (email, str, uuid) or complex (list[T])
        type_name = self._parse_message_type_name()

        # Parse modifiers
        required = False
        default = None

        while True:
            if self.match(TokenType.IDENTIFIER):
                token = self.current_token()
                if token.value == "required":
                    self.advance()
                    required = True
                elif token.value == "optional":
                    self.advance()
                    required = False
                else:
                    break
            elif self.match(TokenType.EQUALS):
                self.advance()
                if self.match(TokenType.STRING):
                    default = self.advance().value
                elif self.match(TokenType.NUMBER):
                    default = self.advance().value
                elif self.match(TokenType.TRUE):
                    self.advance()
                    default = "true"
                elif self.match(TokenType.FALSE):
                    self.advance()
                    default = "false"
                else:
                    default = self.expect(TokenType.IDENTIFIER).value
            else:
                break

        return ir.MessageFieldSpec(
            name=field_name,
            type_name=type_name,
            required=required,
            default=default,
        )

    def _parse_message_type_name(self) -> str:
        """Parse a message field type name.

        Handles:
        - Simple types: str, email, uuid, bool, datetime, json
        - Parameterized types: str(200), decimal(10,2)
        - List types: list[OrderItem]
        - Reference types: ref Entity
        """
        # Check for list type
        if self.match(TokenType.LIST):
            self.advance()
            self.expect(TokenType.LBRACKET)
            inner_type = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.RBRACKET)
            return f"list[{inner_type}]"

        # Check for ref type (not a keyword, parse as identifier)
        type_token = self.expect_identifier_or_keyword()
        type_name: str = str(type_token.value)

        if type_name == "ref":
            ref_entity = self.expect(TokenType.IDENTIFIER).value
            return f"ref {ref_entity}"

        # Check for type parameters
        if self.match(TokenType.LPAREN):
            self.advance()
            params = []
            params.append(self.expect(TokenType.NUMBER).value)
            while self.match(TokenType.COMMA):
                self.advance()
                params.append(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            type_name = f"{type_name}({','.join(params)})"

        return type_name

    # =========================================================================
    # Channel Parsing
    # =========================================================================

    def parse_channel(self) -> ir.ChannelSpec:
        """Parse channel declaration.

        DSL syntax:
            channel notifications:
              kind: email
              provider: auto

              config:
                from_address: "noreply@example.com"

              send welcome:
                message: WelcomeEmail
                when: entity User created
                mapping:
                  to -> User.email

              receive support:
                message: InboundEmail
                match:
                  to: "support@example.com"
                action: create SupportTicket
        """
        self.expect(TokenType.CHANNEL)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        kind = ir.ChannelKind.EMAIL
        provider = "auto"
        config = ir.ChannelConfigSpec()
        provider_config = None
        send_operations: list[ir.SendOperationSpec] = []
        receive_operations: list[ir.ReceiveOperationSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # kind: email | queue | stream
            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                kind_token = self.expect_identifier_or_keyword()
                kind = ir.ChannelKind(kind_token.value)
                self.skip_newlines()

            # provider: auto | mailpit | sendgrid | ...
            elif self.match(TokenType.PROVIDER):
                self.advance()
                self.expect(TokenType.COLON)
                provider = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # config: block
            elif self.match(TokenType.CONFIG):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                config = self._parse_channel_config()
                self.expect(TokenType.DEDENT)

            # provider_config: block
            elif self.match(TokenType.PROVIDER_CONFIG):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                provider_config = self._parse_provider_config()
                self.expect(TokenType.DEDENT)

            # send operation:
            elif self.match(TokenType.SEND):
                send_op = self._parse_send_operation()
                send_operations.append(send_op)

            # receive operation:
            elif self.match(TokenType.RECEIVE):
                receive_op = self._parse_receive_operation()
                receive_operations.append(receive_op)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.ChannelSpec(
            name=name,
            title=title,
            kind=kind,
            provider=provider,
            config=config,
            provider_config=provider_config,
            send_operations=send_operations,
            receive_operations=receive_operations,
        )

    def _parse_channel_config(self) -> ir.ChannelConfigSpec:
        """Parse channel config block."""
        options: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if self.match(TokenType.STRING):
                options[key] = self.advance().value
            elif self.match(TokenType.NUMBER):
                options[key] = self.advance().value
            elif self.match(TokenType.IDENTIFIER):
                options[key] = self.advance().value
            else:
                token = self.current_token()
                raise make_parse_error(
                    f"Expected config value, got {token.type.value}",
                    self.file,
                    token.line,
                    token.column,
                )

            self.skip_newlines()

        return ir.ChannelConfigSpec(options=options)

    def _parse_provider_config(self) -> ir.ProviderConfigSpec:
        """Parse provider config block."""
        max_per_minute = None
        max_concurrent = None
        options: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if self.match(TokenType.NUMBER):
                value = self.advance().value
                if key == "max_per_minute":
                    max_per_minute = int(value)
                elif key == "max_concurrent":
                    max_concurrent = int(value)
                else:
                    options[key] = value
            elif self.match(TokenType.STRING):
                options[key] = self.advance().value
            elif self.match(TokenType.IDENTIFIER):
                options[key] = self.advance().value

            self.skip_newlines()

        return ir.ProviderConfigSpec(
            max_per_minute=max_per_minute,
            max_concurrent=max_concurrent,
            options=options,
        )

    def _parse_send_operation(self) -> ir.SendOperationSpec:
        """Parse send operation block.

        DSL syntax:
            send order_confirmation:
              message: OrderConfirmation
              when: entity Order status -> confirmed
              delivery_mode: outbox
              mapping:
                to -> Order.customer.email
              throttle:
                per_recipient:
                  window: 1h
                  max_messages: 5
        """
        self.expect(TokenType.SEND)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        message_name = ""
        trigger = None
        delivery_mode = ir.DeliveryMode.OUTBOX
        mappings: list[ir.MappingSpec] = []
        throttle = None
        options: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # message: MessageName
            if self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message_name = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # when: trigger
            elif self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                trigger = self._parse_send_trigger()
                self.skip_newlines()

            # delivery_mode: outbox | direct
            elif self.match(TokenType.DELIVERY_MODE):
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                delivery_mode = ir.DeliveryMode(mode_token.value)
                self.skip_newlines()

            # mapping: block
            elif self.match(TokenType.MAPPING):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                mappings = self._parse_send_mappings()
                self.expect(TokenType.DEDENT)

            # throttle: block
            elif self.match(TokenType.THROTTLE):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                throttle = self._parse_throttle()
                self.expect(TokenType.DEDENT)

            else:
                # Unknown directive - skip for extensibility
                break

        self.expect(TokenType.DEDENT)

        return ir.SendOperationSpec(
            name=name,
            message_name=message_name,
            trigger=trigger,
            delivery_mode=delivery_mode,
            mappings=mappings,
            throttle=throttle,
            options=options,
        )

    def _parse_send_trigger(self) -> ir.SendTriggerSpec:
        """Parse send trigger.

        Formats:
            entity Order created
            entity Order status -> shipped
            entity Order.status changed
            service process_payment succeeded
            every 1h
            cron "0 9 * * *"
        """
        # entity triggers
        if self.match(TokenType.ENTITY):
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value

            # Check for field.changed or status -> state
            if self.match(TokenType.DOT):
                self.advance()
                field_name = self.expect_identifier_or_keyword().value
                self.expect(TokenType.CHANGED)
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.ENTITY_FIELD_CHANGED,
                    entity_name=entity_name,
                    field_name=field_name,
                )

            # Check for status -> state or created/updated/deleted
            token = self.expect_identifier_or_keyword()

            if token.value in ("created", "updated", "deleted"):
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.ENTITY_EVENT,
                    entity_name=entity_name,
                    event=ir.EntityEvent(token.value),
                )

            # status -> state
            if token.value == "status" and self.match(TokenType.ARROW):
                self.advance()
                to_state = self.expect(TokenType.IDENTIFIER).value
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.ENTITY_STATUS_TRANSITION,
                    entity_name=entity_name,
                    to_state=to_state,
                )

            # field -> value (field changed to specific value)
            if self.match(TokenType.ARROW):
                self.advance()
                field_value = self.expect_identifier_or_keyword().value
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.ENTITY_FIELD_CHANGED,
                    entity_name=entity_name,
                    field_name=token.value,
                    field_value=field_value,
                )

        # service triggers
        elif self.match(TokenType.SERVICE):
            self.advance()
            service_name = self.expect(TokenType.IDENTIFIER).value

            # Check for service lifecycle events: called, succeeded, failed
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "called":
                self.advance()
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.SERVICE_CALLED,
                    service_name=service_name,
                )
            elif self.match(TokenType.SUCCEEDED):
                self.advance()
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.SERVICE_SUCCEEDED,
                    service_name=service_name,
                )
            elif self.match(TokenType.FAILED):
                self.advance()
                return ir.SendTriggerSpec(
                    kind=ir.SendTriggerKind.SERVICE_FAILED,
                    service_name=service_name,
                )

        # schedule triggers
        elif self.match(TokenType.EVERY):
            self.advance()
            # Parse duration like "1h", "30m", "5s"
            duration = self._parse_duration_seconds()
            return ir.SendTriggerSpec(
                kind=ir.SendTriggerKind.SCHEDULE,
                interval_seconds=duration,
            )

        elif self.match(TokenType.CRON):
            self.advance()
            cron_expr = self.expect(TokenType.STRING).value
            return ir.SendTriggerSpec(
                kind=ir.SendTriggerKind.SCHEDULE,
                cron_expression=cron_expr,
            )

        # Default to manual if nothing matched
        return ir.SendTriggerSpec(kind=ir.SendTriggerKind.MANUAL)

    def _parse_duration_seconds(self) -> int:
        """Parse duration like 1h, 30m, 5s and return seconds."""
        number = int(self.expect(TokenType.NUMBER).value)

        if self.match(TokenType.IDENTIFIER):
            unit = self.advance().value
            if unit == "h" or unit == "hours":
                return number * 3600
            elif unit == "m" or unit == "minutes":
                return number * 60
            elif unit == "s" or unit == "seconds":
                return number
            elif unit == "d" or unit == "days":
                return number * 86400

        # Check for time unit keywords
        if self.match(TokenType.HOURS):
            self.advance()
            return number * 3600
        elif self.match(TokenType.MINUTES):
            self.advance()
            return number * 60
        elif self.match(TokenType.DAYS):
            self.advance()
            return number * 86400

        # Default to seconds
        return number

    def _parse_send_mappings(self) -> list[ir.MappingSpec]:
        """Parse send operation mappings.

        Format:
            to -> Order.customer.email
            subject -> "Order {{Order.number}} confirmed"
        """
        mappings: list[ir.MappingSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            target_field = self.expect_identifier_or_keyword().value
            self.expect(TokenType.ARROW)

            # Source can be a path or a template string
            is_template = False
            if self.match(TokenType.STRING):
                source_path = self.advance().value
                is_template = "{{" in source_path
            else:
                # Parse dotted path
                parts = [self.expect_identifier_or_keyword().value]
                while self.match(TokenType.DOT):
                    self.advance()
                    parts.append(self.expect_identifier_or_keyword().value)
                source_path = ".".join(parts)

            mappings.append(
                ir.MappingSpec(
                    target_field=target_field,
                    source_path=source_path,
                    is_template=is_template,
                )
            )
            self.skip_newlines()

        return mappings

    def _parse_throttle(self) -> ir.ThrottleSpec:
        """Parse throttle configuration.

        Format:
            per_recipient:
              window: 1h
              max_messages: 5
              on_exceed: drop
        """
        # Parse scope
        scope = ir.ThrottleScope.PER_RECIPIENT
        if self.match(TokenType.PER_RECIPIENT):
            self.advance()
            scope = ir.ThrottleScope.PER_RECIPIENT
        elif self.match(TokenType.PER_ENTITY):
            self.advance()
            scope = ir.ThrottleScope.PER_ENTITY
        elif self.match(TokenType.PER_CHANNEL):
            self.advance()
            scope = ir.ThrottleScope.PER_CHANNEL
        elif self.match(TokenType.IDENTIFIER):
            scope_token = self.advance()
            scope = ir.ThrottleScope(scope_token.value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        window_seconds = 3600  # Default 1 hour
        max_messages = 10
        on_exceed = ir.ThrottleExceedAction.DROP

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.WINDOW):
                self.advance()
                self.expect(TokenType.COLON)
                window_seconds = self._parse_duration_seconds()
                self.skip_newlines()

            elif self.match(TokenType.MAX_MESSAGES):
                self.advance()
                self.expect(TokenType.COLON)
                max_messages = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.ON_EXCEED):
                self.advance()
                self.expect(TokenType.COLON)
                action_token = self.expect_identifier_or_keyword()
                on_exceed = ir.ThrottleExceedAction(action_token.value)
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.ThrottleSpec(
            scope=scope,
            window_seconds=window_seconds,
            max_messages=max_messages,
            on_exceed=on_exceed,
        )

    def _parse_receive_operation(self) -> ir.ReceiveOperationSpec:
        """Parse receive operation block.

        DSL syntax:
            receive support_ticket:
              message: InboundEmail
              match:
                to: "support@example.com"
              action: create SupportTicket
              mapping:
                from -> requester_email
                subject -> title
        """
        self.expect(TokenType.RECEIVE)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        message_name = ""
        match_patterns: list[ir.MatchPatternSpec] = []
        action = None
        mappings: list[ir.ReceiveMappingSpec] = []
        options: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # message: MessageName
            if self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message_name = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # match: block
            elif self.match(TokenType.MATCH):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                match_patterns = self._parse_match_patterns()
                self.expect(TokenType.DEDENT)

            # action: create Entity | update Entity | call service Name
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action = self._parse_receive_action()
                self.skip_newlines()

            # mapping: block
            elif self.match(TokenType.MAPPING):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                mappings = self._parse_receive_mappings()
                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.ReceiveOperationSpec(
            name=name,
            message_name=message_name,
            match_patterns=match_patterns,
            action=action,
            mappings=mappings,
            options=options,
        )

    def _parse_match_patterns(self) -> list[ir.MatchPatternSpec]:
        """Parse match patterns for receive operations.

        Format:
            to: "support@example.com"
            subject: "Help:*"
        """
        patterns: list[ir.MatchPatternSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Parse pattern value
            if self.match(TokenType.STRING):
                value = self.advance().value

                # Detect pattern kind from value
                if value.startswith("*") and value.endswith("*"):
                    kind = ir.MatchPatternKind.CONTAINS
                    value = value[1:-1]
                elif value.startswith("*"):
                    kind = ir.MatchPatternKind.SUFFIX
                    value = value[1:]
                elif value.endswith("*"):
                    kind = ir.MatchPatternKind.PREFIX
                    value = value[:-1]
                else:
                    kind = ir.MatchPatternKind.EXACT

                patterns.append(
                    ir.MatchPatternSpec(
                        field_name=field_name,
                        kind=kind,
                        value=value,
                    )
                )

            # regex("pattern")
            elif self.match(TokenType.REGEX):
                self.advance()
                self.expect(TokenType.LPAREN)
                regex_value = self.expect(TokenType.STRING).value
                self.expect(TokenType.RPAREN)
                patterns.append(
                    ir.MatchPatternSpec(
                        field_name=field_name,
                        kind=ir.MatchPatternKind.REGEX,
                        value=regex_value,
                    )
                )

            # in("val1", "val2", ...)
            elif self.match(TokenType.IN):
                self.advance()
                self.expect(TokenType.LPAREN)
                values = [self.expect(TokenType.STRING).value]
                while self.match(TokenType.COMMA):
                    self.advance()
                    values.append(self.expect(TokenType.STRING).value)
                self.expect(TokenType.RPAREN)
                patterns.append(
                    ir.MatchPatternSpec(
                        field_name=field_name,
                        kind=ir.MatchPatternKind.IN,
                        value=values,
                    )
                )

            self.skip_newlines()

        return patterns

    def _parse_receive_action(self) -> ir.ReceiveActionSpec:
        """Parse receive action.

        Formats:
            create SupportTicket
            update Customer
            upsert Customer on email
            call service process_inbound
        """
        if self.match(TokenType.CREATE):
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.ReceiveActionSpec(
                kind=ir.ReceiveActionKind.CREATE,
                entity_name=entity_name,
            )

        elif self.match(TokenType.UPDATE):
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.ReceiveActionSpec(
                kind=ir.ReceiveActionKind.UPDATE,
                entity_name=entity_name,
            )

        elif self.match(TokenType.UPSERT):
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            upsert_field = None
            if self.match(TokenType.ON):
                self.advance()
                upsert_field = self.expect(TokenType.IDENTIFIER).value
            return ir.ReceiveActionSpec(
                kind=ir.ReceiveActionKind.UPSERT,
                entity_name=entity_name,
                upsert_field=upsert_field,
            )

        elif self.match(TokenType.CALL):
            self.advance()
            self.expect(TokenType.SERVICE)
            service_name = self.expect(TokenType.IDENTIFIER).value
            return ir.ReceiveActionSpec(
                kind=ir.ReceiveActionKind.CALL_SERVICE,
                service_name=service_name,
            )

        token = self.current_token()
        raise make_parse_error(
            f"Expected action (create, update, upsert, call), got {token.value}",
            self.file,
            token.line,
            token.column,
        )

    def _parse_receive_mappings(self) -> list[ir.ReceiveMappingSpec]:
        """Parse receive operation mappings.

        Format:
            from -> requester_email
            subject -> title
        """
        mappings: list[ir.ReceiveMappingSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            source_field = self.expect_identifier_or_keyword().value
            self.expect(TokenType.ARROW)
            target_field = self.expect_identifier_or_keyword().value

            mappings.append(
                ir.ReceiveMappingSpec(
                    source_field=source_field,
                    target_field=target_field,
                )
            )
            self.skip_newlines()

        return mappings

    # =========================================================================
    # Asset Parsing
    # =========================================================================

    def parse_asset(self) -> ir.AssetSpec:
        """Parse asset declaration.

        DSL syntax:
            asset terms_of_service:
              kind: file
              path: "email/terms-of-service.pdf"
              description: "Current Terms of Service"
        """
        self.expect(TokenType.ASSET)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        kind = ir.AssetKind.FILE
        path = ""
        description = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                kind_token = self.expect_identifier_or_keyword()
                kind = ir.AssetKind(kind_token.value)
                self.skip_newlines()

            elif self.match(TokenType.PATH):
                self.advance()
                self.expect(TokenType.COLON)
                path = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.AssetSpec(
            name=name,
            kind=kind,
            path=path,
            description=description,
        )

    # =========================================================================
    # Document Parsing
    # =========================================================================

    def parse_document(self) -> ir.DocumentSpec:
        """Parse document declaration.

        DSL syntax:
            document invoice_pdf:
              for_entity: Order
              format: pdf
              layout: invoice_layout
              description: "Invoice PDF for an order"
        """
        self.expect(TokenType.DOCUMENT)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        for_entity = ""
        format_type = ir.DocumentFormat.PDF
        layout = ""
        description = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.FOR_ENTITY):
                self.advance()
                self.expect(TokenType.COLON)
                for_entity = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            elif self.match(TokenType.FORMAT):
                self.advance()
                self.expect(TokenType.COLON)
                format_token = self.expect(TokenType.IDENTIFIER)
                format_type = ir.DocumentFormat(format_token.value)
                self.skip_newlines()

            elif self.match(TokenType.LAYOUT):
                self.advance()
                self.expect(TokenType.COLON)
                layout = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.DocumentSpec(
            name=name,
            for_entity=for_entity,
            format=format_type,
            layout=layout,
            description=description,
        )

    # =========================================================================
    # Template Parsing
    # =========================================================================

    def parse_template(self) -> ir.TemplateSpec:
        """Parse template declaration.

        DSL syntax:
            template welcome_email:
              subject: "Welcome to {{app.name}}"
              body: |
                Hi {{user.name}},
                Thanks for joining!
              attachments:
                - asset: terms_of_service
                  filename: "terms.pdf"
        """
        self.expect(TokenType.TEMPLATE)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        subject = ""
        body = ""
        html_body = None
        attachments: list[ir.TemplateAttachmentSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SUBJECT):
                self.advance()
                self.expect(TokenType.COLON)
                subject = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif self.match(TokenType.BODY):
                self.advance()
                self.expect(TokenType.COLON)
                body = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif self.match(TokenType.HTML_BODY):
                self.advance()
                self.expect(TokenType.COLON)
                html_body = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif self.match(TokenType.ATTACHMENTS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                attachments = self._parse_template_attachments()
                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.TemplateSpec(
            name=name,
            subject=subject,
            body=body,
            html_body=html_body,
            attachments=attachments,
        )

    def _parse_template_attachments(self) -> list[ir.TemplateAttachmentSpec]:
        """Parse template attachments list."""
        attachments: list[ir.TemplateAttachmentSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # - asset: name or - document: name
            if self.match(TokenType.MINUS):
                self.advance()

                asset_name = None
                document_name = None
                entity_arg = None
                filename = ""

                # Parse attachment type
                if self.match(TokenType.ASSET):
                    self.advance()
                    self.expect(TokenType.COLON)
                    asset_name = self.expect(TokenType.IDENTIFIER).value
                elif self.match(TokenType.DOCUMENT):
                    self.advance()
                    self.expect(TokenType.COLON)
                    document_name = self.expect(TokenType.IDENTIFIER).value

                self.skip_newlines()

                # Parse optional entity and filename (on same or next lines)
                # Handle nested indentation for multi-line list items
                nested_indent = False
                if self.match(TokenType.INDENT):
                    self.advance()
                    nested_indent = True

                while not self.match(TokenType.MINUS) and not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.MINUS) or self.match(TokenType.DEDENT):
                        break

                    if self.match(TokenType.ENTITY_ARG) or self.match(TokenType.ENTITY):
                        self.advance()
                        self.expect(TokenType.COLON)
                        entity_arg = self.expect(TokenType.IDENTIFIER).value
                        self.skip_newlines()

                    elif self.match(TokenType.FILENAME):
                        self.advance()
                        self.expect(TokenType.COLON)
                        filename = self.expect(TokenType.STRING).value
                        self.skip_newlines()

                    else:
                        break

                if nested_indent and self.match(TokenType.DEDENT):
                    self.advance()

                attachments.append(
                    ir.TemplateAttachmentSpec(
                        asset_name=asset_name,
                        document_name=document_name,
                        entity_arg=entity_arg,
                        filename=filename,
                    )
                )
            else:
                break

        return attachments
