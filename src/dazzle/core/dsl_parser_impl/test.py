"""
Test parsing for DAZZLE DSL.

Handles test and assertion declarations for API contract tests.
"""

from typing import Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class TestParserMixin:
    """Mixin providing test parsing."""

    def parse_test(self) -> ir.TestSpec:
        """Parse test declaration."""
        self.expect(TokenType.TEST)

        name = self.expect(TokenType.IDENTIFIER).value
        description = None

        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        setup_steps = []
        action = None
        data = {}
        filter_data = {}
        assertions = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse setup block
            if self.match(TokenType.SETUP):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # Parse: var: create Entity with field=value, field=value
                    var_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    self.expect(TokenType.CREATE)
                    entity_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.WITH)

                    # Parse field assignments
                    step_data = {}
                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.EQUALS)
                    field_value = self.parse_value()
                    step_data[field_name] = field_value

                    while self.match(TokenType.COMMA):
                        self.advance()
                        field_name = self.expect_identifier_or_keyword().value
                        self.expect(TokenType.EQUALS)
                        field_value = self.parse_value()
                        step_data[field_name] = field_value

                    setup_steps.append(
                        ir.TestSetupStep(
                            variable_name=var_name,
                            action=ir.TestActionKind.CREATE,
                            entity_name=entity_name,
                            data=step_data,
                        )
                    )

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse action block
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)

                # Parse action kind (create, update, delete, get)
                action_token = self.current_token()
                if self.match(TokenType.CREATE):
                    kind = ir.TestActionKind.CREATE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.UPDATE):
                    kind = ir.TestActionKind.UPDATE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.DELETE):
                    kind = ir.TestActionKind.DELETE
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                elif self.match(TokenType.GET):
                    kind = ir.TestActionKind.GET
                    self.advance()
                    target = self.expect_identifier_or_keyword().value
                else:
                    raise make_parse_error(
                        f"Expected action kind (create, update, delete, get), "
                        f"got {action_token.type.value}",
                        self.file,
                        action_token.line,
                        action_token.column,
                    )

                action = ir.TestAction(
                    kind=kind,
                    target=target,
                    data={},
                )

                self.skip_newlines()

            # Parse data block
            elif self.match(TokenType.DATA):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    field_value = self.parse_value()
                    data[field_name] = field_value

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse filter block
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    field_value = self.parse_value()
                    filter_data[field_name] = field_value

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # Parse search block
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                self.expect(TokenType.QUERY)
                self.expect(TokenType.COLON)
                self.parse_value()

                self.skip_newlines()
                self.expect(TokenType.DEDENT)

            # Parse order_by
            elif self.match(TokenType.ORDER_BY):
                self.advance()
                self.expect(TokenType.COLON)
                self.parse_value()
                self.skip_newlines()

            # Parse expect block
            elif self.match(TokenType.EXPECT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # Parse different assertion types
                    if self.match(TokenType.STATUS):
                        self.advance()
                        self.expect(TokenType.COLON)
                        status_value = self.expect(TokenType.IDENTIFIER).value
                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.STATUS,
                                expected_value=status_value,
                            )
                        )

                    elif self.match(TokenType.CREATED):
                        self.advance()
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.TRUE):
                            self.advance()
                            created_value = True
                        elif self.match(TokenType.FALSE):
                            self.advance()
                            created_value = False
                        else:
                            raise make_parse_error(
                                f"Expected true or false, "
                                f"got {self.current_token().type.value}",
                                self.file,
                                self.current_token().line,
                                self.current_token().column,
                            )
                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.CREATED,
                                expected_value=created_value,
                            )
                        )

                    elif self.match(TokenType.FIELD):
                        # field <name> <operator> <value>
                        # or field <name> <operator> field <other_field>
                        self.advance()
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)

                        # Check if value is another field reference
                        if self.match(TokenType.FIELD):
                            self.advance()
                            other_field = self.expect_identifier_or_keyword().value
                            expected_value: Any = f"field.{other_field}"
                        else:
                            expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=field_name,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.ERROR_MESSAGE):
                        # error_message <operator> <value>
                        self.advance()
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.ERROR,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.COUNT):
                        # count <operator> <value>
                        self.advance()
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.COUNT,
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.FIRST):
                        # first field <name> <operator> <value>
                        self.advance()
                        self.expect(TokenType.FIELD)
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=f"first.{field_name}",
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    elif self.match(TokenType.LAST):
                        # last field <name> <operator> <value>
                        self.advance()
                        self.expect(TokenType.FIELD)
                        field_name = self.expect_identifier_or_keyword().value
                        operator_token = self.expect(TokenType.IDENTIFIER)
                        operator = self.parse_comparison_operator(operator_token.value)
                        expected_value = self.parse_value()

                        assertions.append(
                            ir.TestAssertion(
                                kind=ir.TestAssertionKind.FIELD,
                                field_name=f"last.{field_name}",
                                operator=operator,
                                expected_value=expected_value,
                            )
                        )

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            else:
                # Unknown block, skip it
                self.advance()

        self.expect(TokenType.DEDENT)

        # Set action data
        if action:
            action = ir.TestAction(
                kind=action.kind,
                target=action.target,
                data=data,
            )

        if not action:
            raise make_parse_error(
                f"Test {name} must have an action",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.TestSpec(
            name=name,
            description=description,
            setup_steps=setup_steps,
            action=action,
            assertions=assertions,
        )

    def parse_comparison_operator(self, op_str: str) -> ir.TestComparisonOperator:
        """Parse comparison operator string to enum."""
        op_map = {
            "equals": ir.TestComparisonOperator.EQUALS,
            "not_equals": ir.TestComparisonOperator.NOT_EQUALS,
            "greater_than": ir.TestComparisonOperator.GREATER_THAN,
            "less_than": ir.TestComparisonOperator.LESS_THAN,
            "contains": ir.TestComparisonOperator.CONTAINS,
            "not_contains": ir.TestComparisonOperator.NOT_CONTAINS,
        }
        if op_str not in op_map:
            raise make_parse_error(
                f"Unknown comparison operator: {op_str}",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        return op_map[op_str]
