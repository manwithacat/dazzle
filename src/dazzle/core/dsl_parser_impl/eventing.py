"""
Eventing parsing for DAZZLE DSL.

Handles event_model, subscribe, and project declarations.
Part of v0.18.0 Event-First Architecture feature.

DSL syntax examples:

    event_model:
      topic orders:
        retention: 7d
        partition_key: order_id

      event OrderCreated:
        topic: orders
        payload: Order

    subscribe app.orders as notification_handler:
      on OrderCreated:
        call service send_confirmation_email

    project OrderDashboard from app.orders:
      on OrderCreated:
        upsert with order_id, status="pending"
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class EventingParserMixin:
    """
    Mixin providing eventing construct parsing.

    Parses:
    - event_model: Topic and event definitions
    - subscribe: Event subscription handlers
    - project: Projection from event streams

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

    # =========================================================================
    # Event Model Parsing
    # =========================================================================

    def parse_event_model(self) -> ir.EventModelSpec:
        """Parse event_model declaration.

        DSL syntax:
            event_model:
              topic orders:
                retention: 7d
                partition_key: order_id

              event OrderCreated:
                topic: orders
                payload: Order
        """
        self.expect(TokenType.EVENT_MODEL)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        topics: list[ir.TopicSpec] = []
        events: list[ir.EventSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.TOPIC):
                topic = self._parse_topic_definition()
                topics.append(topic)
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "event":
                event = self._parse_event_definition()
                events.append(event)
            else:
                # Skip unknown
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.EventModelSpec(topics=topics, events=events)

    def _parse_topic_definition(self) -> ir.TopicSpec:
        """Parse a topic definition.

        DSL syntax:
            topic orders:
              retention: 7d
              partition_key: order_id
        """
        self.expect(TokenType.TOPIC)
        name = self.expect(TokenType.IDENTIFIER).value

        retention_days = 7
        partition_key = "entity_id"

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.RETENTION):
                self.advance()
                self.expect(TokenType.COLON)
                # Accept DURATION_LITERAL (e.g., 30d) or IDENTIFIER or NUMBER
                if self.match(TokenType.DURATION_LITERAL):
                    retention_value = self.advance().value
                    # Parse retention like "7d" or "30d"
                    if retention_value.endswith("d"):
                        retention_days = int(retention_value[:-1])
                    elif retention_value.endswith("w"):
                        retention_days = int(retention_value[:-1]) * 7
                    elif retention_value.endswith("m"):
                        retention_days = int(retention_value[:-1]) * 30
                    elif retention_value.endswith("y"):
                        retention_days = int(retention_value[:-1]) * 365
                    else:
                        retention_days = int(retention_value)
                elif self.match(TokenType.NUMBER):
                    retention_days = int(self.advance().value)
                else:
                    retention_value = self.expect(TokenType.IDENTIFIER).value
                    if retention_value.endswith("d"):
                        retention_days = int(retention_value[:-1])
                    else:
                        retention_days = int(retention_value)
            elif self.match(TokenType.IDENTIFIER):
                key = self.advance().value
                if key == "partition_key":
                    self.expect(TokenType.COLON)
                    partition_key = self.expect(TokenType.IDENTIFIER).value
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.TopicSpec(
            name=name,
            retention_days=retention_days,
            partition_key=partition_key,
        )

    def _parse_event_definition(self) -> ir.EventSpec:
        """Parse an event definition.

        DSL syntax:
            event OrderCreated:
              topic: orders
              payload: Order

            event OrderStatusChanged:
              topic: orders
              fields:
                order_id: uuid required
                old_status: str required
                new_status: str required
        """
        # "event" is just an identifier, not a reserved keyword
        event_keyword = self.expect(TokenType.IDENTIFIER)
        assert event_keyword.value == "event"

        name = self.expect(TokenType.IDENTIFIER).value

        topic: str | None = None
        payload_entity: str | None = None
        custom_fields: list[ir.EventFieldSpec] = []

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.TOPIC):
                self.advance()
                self.expect(TokenType.COLON)
                topic = self.expect(TokenType.IDENTIFIER).value
            elif self.match(TokenType.IDENTIFIER):
                key = self.current_token().value
                if key == "payload":
                    self.advance()
                    self.expect(TokenType.COLON)
                    payload_entity = self.expect(TokenType.IDENTIFIER).value
                elif key == "fields":
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    custom_fields = self._parse_event_fields()
                    self.expect(TokenType.DEDENT)
                else:
                    self.advance()
            elif self.match(TokenType.FIELDS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                custom_fields = self._parse_event_fields()
                self.expect(TokenType.DEDENT)
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.EventSpec(
            name=name,
            topic=topic or "default",
            payload_entity=payload_entity,
            custom_fields=custom_fields,
        )

    def _parse_event_fields(self) -> list[ir.EventFieldSpec]:
        """Parse custom event fields."""
        fields: list[ir.EventFieldSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Parse type
            field_type = self.expect(TokenType.IDENTIFIER).value

            # Check for required modifier
            required = False
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "required":
                self.advance()
                required = True

            fields.append(
                ir.EventFieldSpec(
                    name=field_name,
                    field_type=field_type,
                    required=required,
                )
            )

            self.skip_newlines()

        return fields

    # =========================================================================
    # Subscribe Parsing
    # =========================================================================

    def parse_subscribe(self) -> ir.SubscribeSpec:
        """Parse subscribe declaration.

        DSL syntax:
            subscribe app.orders as notification_handler:
              on OrderCreated:
                call service send_confirmation_email
              on OrderStatusChanged:
                when new_status = "shipped":
                  call service send_shipping_notification
        """
        self.expect(TokenType.SUBSCRIBE)

        # Parse topic (can be dotted like app.orders)
        topic = self.expect(TokenType.IDENTIFIER).value
        while self.match(TokenType.DOT):
            self.advance()
            topic += "." + self.expect(TokenType.IDENTIFIER).value

        # Parse group ID
        group_id = topic.replace(".", "_")  # Default
        if self.match(TokenType.AS):
            self.advance()
            group_id = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        handlers: list[ir.EventHandlerSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.ON):
                self.advance()
                event_name = self.expect(TokenType.IDENTIFIER).value
                handler = self._parse_event_handler(event_name)
                handlers.append(handler)
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.SubscribeSpec(
            topic=topic,
            group_id=group_id,
            handlers=handlers,
        )

    def _parse_event_handler(self, event_name: str) -> ir.EventHandlerSpec:
        """Parse an event handler block.

        DSL syntax:
            on OrderCreated:
              call service send_confirmation_email

            on OrderStatusChanged:
              when new_status = "shipped":
                call service send_shipping_notification
        """
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        service_name: str | None = None
        service_method: str | None = None
        condition: str | None = None
        field_mappings: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.CALL):
                self.advance()
                if self.match(TokenType.SERVICE):
                    self.advance()
                service_name = self.expect(TokenType.IDENTIFIER).value
                # Check for method name
                if self.match(TokenType.DOT):
                    self.advance()
                    service_method = self.expect(TokenType.IDENTIFIER).value

            elif self.match(TokenType.WHEN):
                self.advance()
                # Parse condition expression (simplified)
                condition_parts: list[str] = []
                while not self.match(TokenType.COLON):
                    condition_parts.append(self.advance().value)
                condition = " ".join(condition_parts)
                # Skip nested block for now
                self.expect(TokenType.COLON)
                self.skip_newlines()
                if self.match(TokenType.INDENT):
                    self._skip_block()

            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.EventHandlerSpec(
            event_name=event_name,
            service_name=service_name,
            service_method=service_method,
            condition=condition,
            field_mappings=field_mappings,
        )

    # =========================================================================
    # Projection Parsing
    # =========================================================================

    def parse_projection(self) -> ir.ProjectionSpec:
        """Parse projection declaration.

        DSL syntax:
            project OrderDashboard from app.orders:
              on OrderCreated:
                upsert with order_id, status="pending"
              on OrderStatusChanged:
                update status=new_status
        """
        self.expect(TokenType.PROJECT)

        name = self.expect(TokenType.IDENTIFIER).value

        # Parse "from topic"
        if self.match(TokenType.FROM):
            self.advance()

        source_topic = self.expect(TokenType.IDENTIFIER).value
        while self.match(TokenType.DOT):
            self.advance()
            source_topic += "." + self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        handlers: list[ir.ProjectionHandlerSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.ON):
                self.advance()
                event_name = self.expect(TokenType.IDENTIFIER).value
                handler = self._parse_projection_handler(event_name)
                handlers.append(handler)
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ProjectionSpec(
            name=name,
            source_topic=source_topic,
            handlers=handlers,
        )

    def _parse_projection_handler(self, event_name: str) -> ir.ProjectionHandlerSpec:
        """Parse a projection handler block.

        DSL syntax:
            on OrderCreated:
              upsert with order_id, status="pending"

            on OrderStatusChanged:
              update status=new_status
        """
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        action = ir.ProjectionAction.UPSERT
        key_field: str | None = None
        field_mappings: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER):
                keyword = self.current_token().value

                if keyword == "upsert":
                    self.advance()
                    action = ir.ProjectionAction.UPSERT
                    # Parse "with key_field, field=value"
                    if self.match(TokenType.IDENTIFIER) and self.current_token().value == "with":
                        self.advance()
                        key_field = self.expect(TokenType.IDENTIFIER).value
                        while self.match(TokenType.COMMA):
                            self.advance()
                            mapping = self._parse_field_mapping()
                            if mapping:
                                field_mappings[mapping[0]] = mapping[1]

                elif keyword == "update":
                    self.advance()
                    action = ir.ProjectionAction.UPDATE
                    # Parse field=value mappings
                    while not self.match(TokenType.NEWLINE) and not self.match(TokenType.DEDENT):
                        mapping = self._parse_field_mapping()
                        if mapping:
                            field_mappings[mapping[0]] = mapping[1]
                        if self.match(TokenType.COMMA):
                            self.advance()
                        elif not self.match(TokenType.NEWLINE) and not self.match(TokenType.DEDENT):
                            break

                elif keyword == "delete":
                    self.advance()
                    action = ir.ProjectionAction.DELETE

                else:
                    self.advance()
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ProjectionHandlerSpec(
            event_name=event_name,
            action=action,
            key_field=key_field,
            field_mappings=field_mappings,
        )

    def _parse_field_mapping(self) -> tuple[str, str] | None:
        """Parse a field=value mapping."""
        if not self.match(TokenType.IDENTIFIER):
            return None

        field_name = self.advance().value

        if self.match(TokenType.EQUALS):
            self.advance()
            if self.match(TokenType.STRING):
                value = self.advance().value
            elif self.match(TokenType.IDENTIFIER):
                value = self.advance().value
            else:
                value = str(self.advance().value)
            return (field_name, value)

        return (field_name, field_name)  # Identity mapping

    def _skip_block(self) -> None:
        """Skip an indented block."""
        self.expect(TokenType.INDENT)
        depth = 1
        while depth > 0:
            if self.match(TokenType.INDENT):
                self.advance()
                depth += 1
            elif self.match(TokenType.DEDENT):
                self.advance()
                depth -= 1
            elif self.match(TokenType.EOF):
                break
            else:
                self.advance()

    # =========================================================================
    # Publish Directive Parsing (for entity blocks)
    # =========================================================================

    def parse_publish_directive(self, entity_name: str = "") -> ir.PublishSpec:
        """Parse publish directive within an entity.

        DSL syntax:
            publish OrderCreated when created
            publish OrderStatusChanged when status changed

        Args:
            entity_name: Name of the entity this publish belongs to
        """
        self.expect(TokenType.PUBLISH)

        event_name = self.expect(TokenType.IDENTIFIER).value

        # Parse trigger
        trigger = ir.EventTriggerKind.CREATED  # Default
        field_name: str | None = None

        if self.match(TokenType.WHEN):
            self.advance()
            # Trigger can be: created, updated, deleted, or <field_name> changed
            trigger_name = self.expect_identifier_or_keyword().value

            if trigger_name == "created":
                trigger = ir.EventTriggerKind.CREATED
            elif trigger_name == "updated":
                trigger = ir.EventTriggerKind.UPDATED
            elif trigger_name == "deleted":
                trigger = ir.EventTriggerKind.DELETED
            else:
                # Could be field name for field_changed (e.g., "status changed")
                if self.match(TokenType.CHANGED):
                    self.advance()
                    trigger = ir.EventTriggerKind.FIELD_CHANGED
                    field_name = trigger_name

        return ir.PublishSpec(
            event_name=event_name,
            trigger=trigger,
            entity_name=entity_name,
            field_name=field_name,
        )
