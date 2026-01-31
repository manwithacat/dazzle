"""
Entity parsing for DAZZLE DSL.

Handles entity declarations including fields, constraints, state machines,
access rules, invariants, and LLM cognition features.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class EntityParserMixin:
    """
    Mixin providing entity and archetype parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    # Type stubs for methods provided by BaseParser and other mixins
    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        peek_token: Any
        file: Any
        parse_type: Any
        parse_condition_expr: Any
        _is_keyword_as_identifier: Any
        _parse_literal_value: Any
        _parse_field_path: Any
        parse_type_spec: Any
        parse_field_modifiers: Any
        # v0.10.2: Date/duration methods from TypeParserMixin
        _parse_date_expr: Any
        _parse_duration_literal: Any
        # v0.18.0: Publish directive from EventingParserMixin
        parse_publish_directive: Any

    def parse_entity(self) -> ir.EntitySpec:
        """Parse entity declaration."""
        self.expect(TokenType.ENTITY)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # v0.7.1: New fields for LLM cognition
        intent: str | None = None
        domain: str | None = None
        patterns: list[str] = []
        extends: list[str] = []
        examples: list[ir.ExampleRecord] = []
        # v0.10.3: Semantic archetype
        archetype_kind: ir.ArchetypeKind | None = None

        fields: list[ir.FieldSpec] = []
        computed_fields: list[ir.ComputedFieldSpec] = []
        constraints: list[ir.Constraint] = []
        visibility_rules: list[ir.VisibilityRule] = []
        permission_rules: list[ir.PermissionRule] = []
        transitions: list[ir.StateTransition] = []
        invariants: list[ir.InvariantSpec] = []
        publishes: list[ir.PublishSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # v0.7.1: Check for intent: declaration
            if self.match(TokenType.INTENT):
                self.advance()
                self.expect(TokenType.COLON)
                intent = self.expect(TokenType.STRING).value
                self.skip_newlines()
                continue

            # v0.7.1: Check for domain: declaration
            if self.match(TokenType.DOMAIN):
                self.advance()
                self.expect(TokenType.COLON)
                domain = self.expect_identifier_or_keyword().value
                self.skip_newlines()
                continue

            # v0.7.1: Check for patterns: declaration
            if self.match(TokenType.PATTERNS):
                self.advance()
                self.expect(TokenType.COLON)
                patterns = [self.expect_identifier_or_keyword().value]
                while self.match(TokenType.COMMA):
                    self.advance()
                    patterns.append(self.expect_identifier_or_keyword().value)
                self.skip_newlines()
                continue

            # v0.7.1: Check for extends: declaration
            if self.match(TokenType.EXTENDS):
                self.advance()
                self.expect(TokenType.COLON)
                extends = [self.expect(TokenType.IDENTIFIER).value]
                while self.match(TokenType.COMMA):
                    self.advance()
                    extends.append(self.expect(TokenType.IDENTIFIER).value)
                self.skip_newlines()
                continue

            # v0.10.3: Check for archetype: declaration (semantic archetype)
            if self.match(TokenType.ARCHETYPE):
                self.advance()
                self.expect(TokenType.COLON)
                archetype_value = self.expect_identifier_or_keyword().value
                archetype_kind = self._map_archetype_kind(archetype_value)
                self.skip_newlines()
                continue

            # v0.7.1: Check for examples: block
            if self.match(TokenType.EXAMPLES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    example = self._parse_example_record()
                    examples.append(example)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for constraints
            if self.match(TokenType.UNIQUE, TokenType.INDEX):
                constraint_kind = self.advance().type
                kind = (
                    ir.ConstraintKind.UNIQUE
                    if constraint_kind == TokenType.UNIQUE
                    else ir.ConstraintKind.INDEX
                )

                # Parse field list
                field_names = [self.expect_identifier_or_keyword().value]
                while self.match(TokenType.COMMA):
                    self.advance()
                    field_names.append(self.expect_identifier_or_keyword().value)

                constraints.append(ir.Constraint(kind=kind, fields=field_names))
                self.skip_newlines()
                continue

            # Check for invariant declaration (with optional message/code)
            if self.match(TokenType.INVARIANT):
                self.advance()
                self.expect(TokenType.COLON)
                expr = self._parse_invariant_expr()
                self.skip_newlines()

                # v0.7.1: Check for optional message: and code: on next lines
                inv_message: str | None = None
                inv_code: str | None = None

                # Check for indented message/code block
                if self.match(TokenType.INDENT):
                    self.advance()
                    while not self.match(TokenType.DEDENT):
                        self.skip_newlines()
                        if self.match(TokenType.DEDENT):
                            break
                        if self.match(TokenType.MESSAGE):
                            self.advance()
                            self.expect(TokenType.COLON)
                            inv_message = self.expect(TokenType.STRING).value
                        elif self.match(TokenType.CODE):
                            self.advance()
                            self.expect(TokenType.COLON)
                            inv_code = self.expect_identifier_or_keyword().value
                        else:
                            # Not message or code, break out
                            break
                        self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        self.advance()

                invariants.append(
                    ir.InvariantSpec(expression=expr, message=inv_message, code=inv_code)
                )
                continue

            # Check for visible: block
            if self.match(TokenType.VISIBLE):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    visibility_rules.append(self._parse_visibility_rule())
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for permissions: block
            if self.match(TokenType.PERMISSIONS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    permission_rules.append(self._parse_permission_rule())
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for access: block (shorthand for read/write rules)
            if self.match(TokenType.ACCESS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # Parse read:, write:, or delete: rule
                    if self.match(TokenType.READ):
                        self.advance()
                        self.expect(TokenType.COLON)
                        condition = self.parse_condition_expr()
                        # read: maps to visibility rule for authenticated users
                        visibility_rules.append(
                            ir.VisibilityRule(
                                context=ir.AuthContext.AUTHENTICATED,
                                condition=condition,
                            )
                        )
                    elif self.match(TokenType.WRITE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        condition = self.parse_condition_expr()
                        # write: maps to CREATE, UPDATE permissions (not DELETE in v0.7.0)
                        for op in [
                            ir.PermissionKind.CREATE,
                            ir.PermissionKind.UPDATE,
                        ]:
                            permission_rules.append(
                                ir.PermissionRule(
                                    operation=op,
                                    require_auth=True,
                                    condition=condition,
                                )
                            )
                    elif self.match(TokenType.DELETE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        condition = self.parse_condition_expr()
                        # delete: maps to DELETE permission only
                        permission_rules.append(
                            ir.PermissionRule(
                                operation=ir.PermissionKind.DELETE,
                                require_auth=True,
                                condition=condition,
                            )
                        )
                    else:
                        token = self.current_token()
                        raise make_parse_error(
                            f"Expected 'read', 'write', or 'delete' in access block, "
                            f"got {token.type.value}",
                            self.file,
                            token.line,
                            token.column,
                        )
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for transitions: block (state machines)
            if self.match(TokenType.TRANSITIONS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    transition = self._parse_state_transition()
                    transitions.append(transition)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # v0.18.0: Check for publish declaration
            if self.match(TokenType.PUBLISH):
                publish_spec = self.parse_publish_directive(entity_name=name)
                publishes.append(publish_spec)
                self.skip_newlines()
                continue

            # Parse field
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Check for computed field
            if self.match(TokenType.COMPUTED):
                self.advance()
                computed_expr = self._parse_computed_expr()
                computed_fields.append(
                    ir.ComputedFieldSpec(
                        name=field_name,
                        expression=computed_expr,
                    )
                )
            else:
                field_type = self.parse_type_spec()
                modifiers, default = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                    )
                )

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        # Build access spec if any rules were defined
        access = None
        if visibility_rules or permission_rules:
            access = ir.AccessSpec(
                visibility=visibility_rules,
                permissions=permission_rules,
            )

        # Build state machine spec if transitions were defined
        state_machine = None
        if transitions:
            # Find the status field - look for enum field named 'status'
            status_field_name = None
            states: list[str] = []
            for field in fields:
                if field.name == "status" and field.type.kind == ir.FieldTypeKind.ENUM:
                    status_field_name = field.name
                    states = field.type.enum_values or []
                    break

            if status_field_name:
                state_machine = ir.StateMachineSpec(
                    status_field=status_field_name,
                    states=states,
                    transitions=transitions,
                )

        return ir.EntitySpec(
            name=name,
            title=title,
            intent=intent,
            domain=domain,
            patterns=patterns,
            extends=extends,
            archetype_kind=archetype_kind,
            fields=fields,
            computed_fields=computed_fields,
            invariants=invariants,
            constraints=constraints,
            access=access,
            state_machine=state_machine,
            examples=examples,
            publishes=publishes,
        )

    def _map_archetype_kind(self, value: str) -> ir.ArchetypeKind:
        """
        Map archetype string value to ArchetypeKind enum.

        v0.10.3: Supports settings, tenant, tenant_settings semantic archetypes.
        v0.10.4: Added user, user_membership for user management.
        """
        mapping = {
            "settings": ir.ArchetypeKind.SETTINGS,
            "tenant": ir.ArchetypeKind.TENANT,
            "tenant_settings": ir.ArchetypeKind.TENANT_SETTINGS,
            "user": ir.ArchetypeKind.USER,
            "user_membership": ir.ArchetypeKind.USER_MEMBERSHIP,
        }
        if value in mapping:
            return mapping[value]
        # Default to CUSTOM for user-defined archetype names
        # (though this is typically used with extends: instead)
        return ir.ArchetypeKind.CUSTOM

    def _parse_visibility_rule(self) -> ir.VisibilityRule:
        """
        Parse a visibility rule.

        Syntax:
            when anonymous: is_public = true
            when authenticated: is_public = true or created_by = current_user
        """
        self.expect(TokenType.WHEN)

        # Parse auth context (anonymous or authenticated)
        if self.match(TokenType.ANONYMOUS):
            self.advance()
            context = ir.AuthContext.ANONYMOUS
        elif self.match(TokenType.AUTHENTICATED):
            self.advance()
            context = ir.AuthContext.AUTHENTICATED
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected 'anonymous' or 'authenticated', got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)

        # Parse condition expression
        condition = self.parse_condition_expr()

        return ir.VisibilityRule(context=context, condition=condition)

    def _parse_permission_rule(self) -> ir.PermissionRule:
        """
        Parse a permission rule.

        Syntax:
            create: authenticated
            update: created_by = current_user or assigned_to = current_user
            delete: created_by = current_user
        """
        # Parse operation (create, update, delete)
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER:
            op_name = self.advance().value
        else:
            op_name = self.expect_identifier_or_keyword().value

        # Map to PermissionKind
        op_map = {
            "create": ir.PermissionKind.CREATE,
            "update": ir.PermissionKind.UPDATE,
            "delete": ir.PermissionKind.DELETE,
        }
        if op_name not in op_map:
            raise make_parse_error(
                f"Expected 'create', 'update', or 'delete', got '{op_name}'",
                self.file,
                token.line,
                token.column,
            )
        operation = op_map[op_name]

        self.expect(TokenType.COLON)

        # Check for simple "authenticated" (no condition)
        if self.match(TokenType.AUTHENTICATED):
            self.advance()
            return ir.PermissionRule(operation=operation, require_auth=True)

        # Check for "anonymous" (no auth required, no condition)
        if self.match(TokenType.ANONYMOUS):
            self.advance()
            return ir.PermissionRule(operation=operation, require_auth=False, condition=None)

        # Otherwise, parse a condition expression (implies authenticated)
        condition = self.parse_condition_expr()
        return ir.PermissionRule(operation=operation, require_auth=True, condition=condition)

    def _parse_state_transition(self) -> ir.StateTransition:
        """
        Parse a state transition rule.

        Syntax:
            open -> assigned: requires assignee
            assigned -> resolved: requires resolution_note
            resolved -> closed: auto after 7 days OR manual
            * -> open: role(admin)
        """
        # Parse from_state (* for wildcard, or identifier)
        if self.match(TokenType.STAR):
            self.advance()
            from_state = "*"
        else:
            from_state = self.expect_identifier_or_keyword().value

        # Expect arrow
        self.expect(TokenType.ARROW)

        # Parse to_state
        to_state = self.expect_identifier_or_keyword().value

        # Optional colon and guards/modifiers
        trigger = ir.TransitionTrigger.MANUAL
        guards: list[ir.TransitionGuard] = []
        auto_spec: ir.AutoTransitionSpec | None = None

        if self.match(TokenType.COLON):
            self.advance()

            # Parse guard/trigger specifications
            while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                # requires field_name
                if self.match(TokenType.REQUIRES):
                    self.advance()
                    field_name = self.expect_identifier_or_keyword().value
                    guards.append(ir.TransitionGuard(requires_field=field_name))

                # role(role_name)
                elif self.match(TokenType.ROLE):
                    self.advance()
                    self.expect(TokenType.LPAREN)
                    role_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.RPAREN)
                    guards.append(ir.TransitionGuard(requires_role=role_name))

                # auto after N days/hours/minutes
                elif self.match(TokenType.AUTO):
                    self.advance()
                    trigger = ir.TransitionTrigger.AUTO

                    if self.match(TokenType.AFTER):
                        self.advance()
                        # Parse delay: N days/hours/minutes
                        delay_value = int(self.expect(TokenType.NUMBER).value)

                        # Parse time unit
                        if self.match(TokenType.DAYS):
                            self.advance()
                            delay_unit = ir.TimeUnit.DAYS
                        elif self.match(TokenType.HOURS):
                            self.advance()
                            delay_unit = ir.TimeUnit.HOURS
                        elif self.match(TokenType.MINUTES):
                            self.advance()
                            delay_unit = ir.TimeUnit.MINUTES
                        else:
                            # Default to days
                            delay_unit = ir.TimeUnit.DAYS

                        # Check for OR manual
                        allow_manual = False
                        if self.match(TokenType.OR):
                            self.advance()
                            if self.match(TokenType.MANUAL):
                                self.advance()
                                allow_manual = True

                        auto_spec = ir.AutoTransitionSpec(
                            delay_value=delay_value,
                            delay_unit=delay_unit,
                            allow_manual=allow_manual,
                        )

                # manual
                elif self.match(TokenType.MANUAL):
                    self.advance()
                    trigger = ir.TransitionTrigger.MANUAL

                # OR connector
                elif self.match(TokenType.OR):
                    self.advance()
                    continue

                else:
                    # v0.14.1: Provide helpful error for unsupported syntax
                    token = self.current_token()
                    # Check for common unsupported patterns
                    if token.type in (
                        TokenType.NOT_EQUALS,
                        TokenType.DOUBLE_EQUALS,
                        TokenType.LESS_THAN,
                        TokenType.GREATER_THAN,
                    ):
                        raise make_parse_error(
                            f"Transition conditions don't support comparison operators "
                            f"like '{token.value}'.\n"
                            f"  Supported syntax:\n"
                            f"    requires field_name     # Field must not be null\n"
                            f"    role(role_name)         # User must have role\n"
                            f"    auto after N days       # Auto-transition with delay\n"
                            f"  Example: open -> assigned: requires assignee",
                            self.file,
                            token.line,
                            token.column,
                        )
                    elif token.type == TokenType.IDENTIFIER:
                        # User might be trying to use field name directly
                        raise make_parse_error(
                            f"Unexpected identifier '{token.value}' in transition condition.\n"
                            f"  Did you mean: requires {token.value}\n"
                            f"  Supported syntax:\n"
                            f"    requires field_name     # Field must not be null\n"
                            f"    role(role_name)         # User must have role",
                            self.file,
                            token.line,
                            token.column,
                        )
                    # For other unexpected tokens, break (might be end of transition)
                    break

        return ir.StateTransition(
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            guards=guards,
            auto_spec=auto_spec,
        )

    def _parse_computed_expr(self) -> ir.ComputedExpr:
        """
        Parse a computed field expression.

        Handles additive operators (+, -) with correct precedence.

        Syntax:
            computed_expr ::= computed_term (("+" | "-") computed_term)*
        """
        left = self._parse_computed_term()

        while self.match(TokenType.PLUS, TokenType.MINUS):
            op_token = self.advance()
            if op_token.type == TokenType.PLUS:
                operator = ir.ArithmeticOperator.ADD
            else:
                operator = ir.ArithmeticOperator.SUBTRACT

            right = self._parse_computed_term()
            left = ir.ArithmeticExpr(left=left, operator=operator, right=right)

        return left

    def _parse_computed_term(self) -> ir.ComputedExpr:
        """
        Parse a multiplicative computed expression.

        Handles *, / with higher precedence than +, -.

        Syntax:
            computed_term ::= computed_primary (("*" | "/") computed_primary)*
        """
        left = self._parse_computed_primary()

        while self.match(TokenType.STAR, TokenType.SLASH):
            op_token = self.advance()
            if op_token.type == TokenType.STAR:
                operator = ir.ArithmeticOperator.MULTIPLY
            else:
                operator = ir.ArithmeticOperator.DIVIDE

            right = self._parse_computed_primary()
            left = ir.ArithmeticExpr(left=left, operator=operator, right=right)

        return left

    def _parse_computed_primary(self) -> ir.ComputedExpr:
        """
        Parse a primary computed expression.

        Handles:
            - Aggregate function calls: sum(field), count(items), days_since(date)
            - Field references: field or relation.field
            - Numeric literals: 1.5, 100
            - Parenthesized expressions: (expr)

        Syntax:
            computed_primary ::= aggregate_call | field_path | NUMBER | "(" computed_expr ")"
        """
        # Check for parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self._parse_computed_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Check for numeric literal
        if self.match(TokenType.NUMBER):
            token = self.advance()
            value = float(token.value) if "." in token.value else int(token.value)
            return ir.LiteralValue(value=value)

        # Check for aggregate function call
        # Only treat it as a function call if followed by '('
        # Otherwise, it's a field name that happens to match a keyword
        aggregate_tokens = {
            TokenType.COUNT: ir.AggregateFunction.COUNT,
            TokenType.SUM: ir.AggregateFunction.SUM,
            TokenType.AVG: ir.AggregateFunction.AVG,
            TokenType.MIN: ir.AggregateFunction.MIN,
            TokenType.MAX: ir.AggregateFunction.MAX,
            TokenType.DAYS_UNTIL: ir.AggregateFunction.DAYS_UNTIL,
            TokenType.DAYS_SINCE: ir.AggregateFunction.DAYS_SINCE,
        }

        for token_type, func in aggregate_tokens.items():
            if self.match(token_type) and self.peek_token().type == TokenType.LPAREN:
                self.advance()
                self.expect(TokenType.LPAREN)
                # Parse field path inside parentheses
                field_path = self._parse_field_path()
                self.expect(TokenType.RPAREN)
                return ir.AggregateCall(
                    function=func,
                    field=ir.FieldReference(path=field_path),
                )

        # Must be a field reference (possibly with dots for relation traversal)
        field_path = self._parse_field_path()
        return ir.FieldReference(path=field_path)

    def _parse_invariant_expr(self) -> ir.InvariantExpr:
        """
        Parse an invariant expression with logical OR (lowest precedence).

        Syntax:
            invariant_expr ::= invariant_and ("or" invariant_and)*

        Examples:
            - end_date > start_date
            - status == "active" or status == "pending"
        """
        left = self._parse_invariant_and()

        while self.match(TokenType.OR):
            self.advance()
            right = self._parse_invariant_and()
            left = ir.LogicalExpr(
                left=left,
                operator=ir.InvariantLogicalOperator.OR,
                right=right,
            )

        return left

    def _parse_invariant_and(self) -> ir.InvariantExpr:
        """
        Parse AND expressions (higher precedence than OR).

        Syntax:
            invariant_and ::= invariant_not ("and" invariant_not)*
        """
        left = self._parse_invariant_not()

        while self.match(TokenType.AND):
            self.advance()
            right = self._parse_invariant_not()
            left = ir.LogicalExpr(
                left=left,
                operator=ir.InvariantLogicalOperator.AND,
                right=right,
            )

        return left

    def _parse_invariant_not(self) -> ir.InvariantExpr:
        """
        Parse NOT expressions (unary negation).

        Syntax:
            invariant_not ::= "not" invariant_not | invariant_comparison
        """
        if self.match(TokenType.NOT):
            self.advance()
            operand = self._parse_invariant_not()
            return ir.NotExpr(operand=operand)

        return self._parse_invariant_comparison()

    def _parse_invariant_comparison(self) -> ir.InvariantExpr:
        """
        Parse comparison expressions.

        Syntax:
            invariant_comparison ::= invariant_primary (comp_op invariant_primary)?
            comp_op ::= "=" | "==" | "!=" | ">" | "<" | ">=" | "<="

        Note: Both "=" and "==" are accepted for equality to maintain consistency
        with access rule syntax. This makes the DSL more LLM-friendly.

        Examples:
            - end_date > start_date
            - quantity >= 0
            - status = "active"
            - status == "active"  (also valid)
        """
        left = self._parse_invariant_primary()

        # Check for comparison operator
        # Note: Both EQUALS (=) and DOUBLE_EQUALS (==) map to EQ for consistency
        comparison_ops = {
            TokenType.EQUALS: ir.InvariantComparisonOperator.EQ,
            TokenType.DOUBLE_EQUALS: ir.InvariantComparisonOperator.EQ,
            TokenType.NOT_EQUALS: ir.InvariantComparisonOperator.NE,
            TokenType.GREATER_THAN: ir.InvariantComparisonOperator.GT,
            TokenType.LESS_THAN: ir.InvariantComparisonOperator.LT,
            TokenType.GREATER_EQUAL: ir.InvariantComparisonOperator.GE,
            TokenType.LESS_EQUAL: ir.InvariantComparisonOperator.LE,
        }

        for token_type, op in comparison_ops.items():
            if self.match(token_type):
                self.advance()
                right = self._parse_invariant_primary()
                return ir.ComparisonExpr(left=left, operator=op, right=right)

        return left

    def _parse_invariant_primary(self) -> ir.InvariantExpr:
        """
        Parse primary invariant expressions.

        Handles:
            - Field references: field_name or path.to.field
            - Numeric literals: 0, 1.5, -10
            - String literals: "active"
            - Boolean literals: true, false
            - Duration expressions: 14 days, 2 hours, 7d, 2w (v0.10.2)
            - Date literals: today, now (v0.10.2)
            - Date arithmetic: today + 7d (v0.10.2)
            - Parenthesized expressions: (expr)

        Syntax:
            invariant_primary ::= field_ref | NUMBER | STRING | BOOL | duration | date_expr | "(" invariant_expr ")"
        """
        # Check for parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self._parse_invariant_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # v0.10.2: Check for date literals (today, now)
        if self.match(TokenType.TODAY) or self.match(TokenType.NOW):
            date_expr = self._parse_date_expr()
            # Return the date expression - it will be used in comparisons
            # For invariants, we wrap it in InvariantLiteral with the __str__ representation
            # This is a simplification; for full support we'd need a dedicated InvariantDateExpr type
            return ir.InvariantLiteral(value=str(date_expr))

        # v0.10.2: Check for compact duration literal (7d, 2w, 30min)
        if self.match(TokenType.DURATION_LITERAL):
            duration = self._parse_duration_literal()
            return ir.DurationExpr(value=duration.value, unit=duration.unit)

        # Check for numeric literal
        if self.match(TokenType.NUMBER):
            token = self.advance()
            value = float(token.value) if "." in token.value else int(token.value)

            # Check if followed by duration unit (verbose syntax: 14 days)
            duration_units = {
                TokenType.DAYS: ir.DurationUnit.DAYS,
                TokenType.HOURS: ir.DurationUnit.HOURS,
                TokenType.MINUTES: ir.DurationUnit.MINUTES,
                TokenType.WEEKS: ir.DurationUnit.WEEKS,
                TokenType.MONTHS: ir.DurationUnit.MONTHS,
                TokenType.YEARS: ir.DurationUnit.YEARS,
            }
            for unit_token, unit in duration_units.items():
                if self.match(unit_token):
                    self.advance()
                    return ir.DurationExpr(value=int(value), unit=unit)

            return ir.InvariantLiteral(value=value)

        # Check for string literal
        if self.match(TokenType.STRING):
            token = self.advance()
            return ir.InvariantLiteral(value=token.value)

        # Check for boolean literals (true, false)
        if self.match(TokenType.TRUE):
            self.advance()
            return ir.InvariantLiteral(value=True)
        if self.match(TokenType.FALSE):
            self.advance()
            return ir.InvariantLiteral(value=False)

        # Check for null literal (handle as identifier with value "null" or "None")
        if self.match(TokenType.IDENTIFIER):
            token = self.current_token()
            if token.value in ("null", "None"):
                self.advance()
                return ir.InvariantLiteral(value=None)

        # Must be a field reference
        field_path = self._parse_field_path()
        return ir.InvariantFieldRef(path=field_path)

    def _parse_example_record(self) -> ir.ExampleRecord:
        """
        Parse an example record in the examples: block.

        Syntax:
            - {field1: value1, field2: value2, ...}

        Values can be:
            - strings (quoted)
            - numbers (int or float)
            - booleans (true/false)
            - null
        """
        self.expect(TokenType.MINUS)

        values: dict[str, str | int | float | bool | None] = {}

        # Check for { syntax
        if self.match(TokenType.IDENTIFIER) or self._is_keyword_as_identifier():
            # No braces, just key: value pairs on the line
            while True:
                key = self.expect_identifier_or_keyword().value
                self.expect(TokenType.COLON)
                value = self._parse_literal_value()
                values[key] = value

                if self.match(TokenType.COMMA):
                    self.advance()
                else:
                    break

        return ir.ExampleRecord(values=values)

    def parse_archetype(self) -> ir.ArchetypeSpec:
        """
        Parse archetype declaration.

        Syntax:
            archetype <ArchetypeName>:
              field1: type
              field2: type
              [computed fields]
              [invariants]
        """
        self.expect(TokenType.ARCHETYPE)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        fields: list[ir.FieldSpec] = []
        computed_fields: list[ir.ComputedFieldSpec] = []
        invariants: list[ir.InvariantSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Check for invariant declaration
            if self.match(TokenType.INVARIANT):
                self.advance()
                self.expect(TokenType.COLON)
                expr = self._parse_invariant_expr()
                invariants.append(ir.InvariantSpec(expression=expr))
                self.skip_newlines()
                continue

            # Parse field
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Check for computed field
            if self.match(TokenType.COMPUTED):
                self.advance()
                computed_expr = self._parse_computed_expr()
                computed_fields.append(
                    ir.ComputedFieldSpec(
                        name=field_name,
                        expression=computed_expr,
                    )
                )
            else:
                field_type = self.parse_type_spec()
                modifiers, default = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                    )
                )

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ArchetypeSpec(
            name=name,
            fields=fields,
            computed_fields=computed_fields,
            invariants=invariants,
        )
