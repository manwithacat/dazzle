"""
DSL Parser for DAZZLE.

Converts token stream from lexer into IR (Internal Representation).
Implements recursive descent parsing for all DSL constructs.
"""

from pathlib import Path
from typing import Any

from . import ir
from .errors import make_parse_error
from .lexer import Token, TokenType, tokenize


class Parser:
    """
    Recursive descent parser for DAZZLE DSL.

    Consumes tokens from lexer and builds IR structures.
    """

    def __init__(self, tokens: list[Token], file: Path):
        """
        Initialize parser.

        Args:
            tokens: List of tokens from lexer
            file: Source file path (for error reporting)
        """
        self.tokens = tokens
        self.file = file
        self.pos = 0

    def current_token(self) -> Token:
        """Get current token."""
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[self.pos]

    def peek_token(self, offset: int = 1) -> Token:
        """Peek ahead at token."""
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # Return EOF
        return self.tokens[pos]

    def advance(self) -> Token:
        """Consume and return current token."""
        token = self.current_token()
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def expect(self, token_type: TokenType) -> Token:
        """
        Expect a specific token type and consume it.

        Raises:
            ParseError: If token doesn't match
        """
        token = self.current_token()
        if token.type != token_type:
            raise make_parse_error(
                f"Expected {token_type.value}, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
        return self.advance()

    def expect_identifier_or_keyword(self) -> Token:
        """
        Expect an identifier or accept a keyword as an identifier.

        This is useful for contexts where keywords can be used as values.
        """
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER:
            return self.advance()

        # Allow keywords to be used as identifiers in certain contexts
        if token.type in (
            TokenType.APP,
            TokenType.MODULE,
            TokenType.USE,
            TokenType.SURFACE,
            TokenType.ENTITY,
            TokenType.INTEGRATION,
            TokenType.EXPERIENCE,
            TokenType.SERVICE,
            TokenType.FOREIGN_MODEL,
            # Boolean literals (for default values)
            TokenType.TRUE,
            TokenType.FALSE,
            # Test DSL keywords (can be used as field names)
            TokenType.TEST,
            TokenType.SETUP,
            TokenType.DATA,
            TokenType.EXPECT,
            TokenType.STATUS,
            TokenType.CREATED,
            TokenType.FILTER,
            TokenType.SEARCH,
            TokenType.ORDER_BY,
            TokenType.COUNT,
            TokenType.ERROR_MESSAGE,
            TokenType.FIRST,
            TokenType.LAST,
            TokenType.QUERY,
            TokenType.CREATE,
            TokenType.UPDATE,
            TokenType.DELETE,
            TokenType.GET,
            # UX Semantic Layer keywords (can be used as identifiers)
            TokenType.UX,
            TokenType.PURPOSE,
            TokenType.SHOW,
            TokenType.SORT,
            TokenType.EMPTY,
            TokenType.ATTENTION,
            TokenType.CRITICAL,
            TokenType.WARNING,
            TokenType.NOTICE,
            TokenType.INFO,
            TokenType.MESSAGE,
            TokenType.FOR,
            TokenType.SCOPE,
            TokenType.HIDE,
            TokenType.SHOW_AGGREGATE,
            TokenType.ACTION_PRIMARY,
            TokenType.READ_ONLY,
            TokenType.ALL,
            TokenType.WORKSPACE,
            TokenType.SOURCE,
            TokenType.LIMIT,
            TokenType.DISPLAY,
            TokenType.AGGREGATE,
            TokenType.LIST,
            TokenType.GRID,
            TokenType.TIMELINE,
            TokenType.DETAIL,  # v0.3.1
            TokenType.ASC,
            TokenType.DESC,
            TokenType.IN,
            TokenType.NOT,
            TokenType.IS,
            TokenType.AND,
            TokenType.OR,
            # Flow/E2E Test keywords (v0.3.2) - can be used as semantic targets
            TokenType.FLOW,
            TokenType.STEPS,
            TokenType.NAVIGATE,
            TokenType.CLICK,
            TokenType.FILL,
            TokenType.WAIT,
            TokenType.SNAPSHOT,
            TokenType.PRECONDITIONS,
            TokenType.AUTHENTICATED,
            TokenType.USER_ROLE,
            TokenType.FIXTURES,
            TokenType.VIEW,
            TokenType.ENTITY_EXISTS,
            TokenType.ENTITY_NOT_EXISTS,
            TokenType.VALIDATION_ERROR,
            TokenType.VISIBLE,
            TokenType.NOT_VISIBLE,
            TokenType.TEXT_CONTAINS,
            TokenType.REDIRECTS_TO,
            TokenType.FIELD_VALUE,
            TokenType.TAGS,
            TokenType.FIELD,
            TokenType.ACTION,
            TokenType.ANONYMOUS,
            TokenType.PERMISSIONS,
            # Access control keywords (v0.5.0) - can be used as enum values
            TokenType.ACCESS,
            TokenType.READ,
            TokenType.WRITE,
            # State Machine keywords (v0.7.0) - can be used as field names
            TokenType.TRANSITIONS,
            TokenType.REQUIRES,
            TokenType.AUTO,
            TokenType.AFTER,
            TokenType.ROLE,
            TokenType.MANUAL,
            TokenType.DAYS,
            TokenType.HOURS,
            TokenType.MINUTES,
            # Access control keywords - can be used in dotted path expressions
            TokenType.OWNER,
            # v0.7.1 LLM Cognition keywords - can be used as field names
            TokenType.INTENT,
            TokenType.EXAMPLES,
            TokenType.DOMAIN,
            TokenType.PATTERNS,
            TokenType.EXTENDS,
            TokenType.ARCHETYPE,
            TokenType.HAS_MANY,
            TokenType.HAS_ONE,
            TokenType.EMBEDS,
            TokenType.BELONGS_TO,
            TokenType.CASCADE,
            TokenType.RESTRICT,
            TokenType.NULLIFY,
            TokenType.READONLY,
            TokenType.DENY,
            TokenType.SCENARIOS,
            TokenType.GIVEN,
            TokenType.THEN,
            TokenType.CODE,
        ):
            return self.advance()

        # v0.3.1: Provide helpful alternatives for common reserved keywords
        keyword_alternatives = {
            "url": "endpoint, uri, address, link",
            "source": "data_source, origin, provider, event_source",
            "error": "err, failure, fault",
            "warning": "warn, alert, caution",
            "mode": "display_mode, type, view_mode",
            "filter": "filter_by, where_clause, filters",
            "data": "record_data, content, payload",
            "status": "state, current_status, record_status",
            "created": "created_at, was_created",
            "key": "composite_key, key_field",
            "spec": "specification, api_spec",
            "from": "from_source, source_entity",
            "into": "into_target, target_entity",
        }

        keyword = token.type.value
        if keyword in keyword_alternatives:
            alternatives = keyword_alternatives[keyword]
            error_msg = (
                f"Field name '{keyword}' is a reserved keyword.\n"
                f"  Suggested alternatives: {alternatives}\n"
                f"  See docs/DSL_RESERVED_KEYWORDS.md for full list"
            )
        else:
            error_msg = f"Expected identifier or keyword, got {keyword}"

        raise make_parse_error(
            error_msg,
            self.file,
            token.line,
            token.column,
        )

    def match(self, *token_types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.current_token().type in token_types

    def skip_newlines(self) -> None:
        """Skip any NEWLINE tokens."""
        while self.match(TokenType.NEWLINE):
            self.advance()

    def parse_module_header(self) -> tuple[str | None, str | None, str | None, list[str]]:
        """
        Parse module header (module, app, use declarations).

        Returns:
            Tuple of (module_name, app_name, app_title, uses)
        """
        module_name = None
        app_name = None
        app_title = None
        uses = []

        self.skip_newlines()

        # Parse module declaration
        if self.match(TokenType.MODULE):
            self.advance()
            module_name = self.parse_module_name()
            self.skip_newlines()

        # Parse use declarations
        while self.match(TokenType.USE):
            self.advance()
            use_name = self.parse_module_name()
            uses.append(use_name)

            # Optional "as alias" - ignore for now
            if self.match(TokenType.AS):
                self.advance()
                self.expect(TokenType.IDENTIFIER)

            self.skip_newlines()

        # Parse app declaration
        if self.match(TokenType.APP):
            self.advance()
            app_name = self.expect_identifier_or_keyword().value

            if self.match(TokenType.STRING):
                app_title = self.advance().value

            self.skip_newlines()

        return module_name, app_name, app_title, uses

    def parse_module_name(self) -> str:
        """Parse dotted module name (e.g., foo.bar.baz)."""
        parts = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)

        return ".".join(parts)

    def parse_type_spec(self) -> ir.FieldType:
        """
        Parse field type specification.

        Examples:
            str(200)
            decimal(10,2)
            enum[draft,issued,paid]
            ref Client
        """
        token = self.current_token()

        # str(N)
        if token.value == "str":
            self.advance()
            self.expect(TokenType.LPAREN)
            max_len = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=max_len)

        # text
        elif token.value == "text":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.TEXT)

        # int
        elif token.value == "int":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.INT)

        # decimal(P,S)
        elif token.value == "decimal":
            self.advance()
            self.expect(TokenType.LPAREN)
            precision = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.COMMA)
            scale = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=precision, scale=scale)

        # bool
        elif token.value == "bool":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.BOOL)

        # date
        elif token.value == "date":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATE)

        # datetime
        elif token.value == "datetime":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATETIME)

        # uuid
        elif token.value == "uuid":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.UUID)

        # email
        elif token.value == "email":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.EMAIL)

        # enum[val1,val2,...]
        elif token.value == "enum":
            self.advance()
            self.expect(TokenType.LBRACKET)

            values = []
            values.append(self.expect_identifier_or_keyword().value)

            while self.match(TokenType.COMMA):
                self.advance()
                values.append(self.expect_identifier_or_keyword().value)

            self.expect(TokenType.RBRACKET)
            return ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=values)

        # ref EntityName
        elif token.value == "ref":
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=entity_name)

        # v0.7.1: has_many EntityName [cascade|restrict|nullify] [readonly]
        elif token.type == TokenType.HAS_MANY:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            behavior, readonly = self._parse_relationship_modifiers()
            return ir.FieldType(
                kind=ir.FieldTypeKind.HAS_MANY,
                ref_entity=entity_name,
                relationship_behavior=behavior,
                readonly=readonly,
            )

        # v0.7.1: has_one EntityName [cascade|restrict] [readonly]
        elif token.type == TokenType.HAS_ONE:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            behavior, readonly = self._parse_relationship_modifiers()
            return ir.FieldType(
                kind=ir.FieldTypeKind.HAS_ONE,
                ref_entity=entity_name,
                relationship_behavior=behavior,
                readonly=readonly,
            )

        # v0.7.1: embeds EntityName
        elif token.type == TokenType.EMBEDS:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.EMBEDS, ref_entity=entity_name)

        # v0.7.1: belongs_to EntityName
        elif token.type == TokenType.BELONGS_TO:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.BELONGS_TO, ref_entity=entity_name)

        else:
            raise make_parse_error(
                f"Unknown type: {token.value}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_relationship_modifiers(
        self,
    ) -> tuple[ir.RelationshipBehavior | None, bool]:
        """Parse optional relationship modifiers (cascade, restrict, nullify, readonly)."""
        behavior: ir.RelationshipBehavior | None = None
        readonly = False

        # Check for behavior modifier
        if self.match(TokenType.CASCADE):
            self.advance()
            behavior = ir.RelationshipBehavior.CASCADE
        elif self.match(TokenType.RESTRICT):
            self.advance()
            behavior = ir.RelationshipBehavior.RESTRICT
        elif self.match(TokenType.NULLIFY):
            self.advance()
            behavior = ir.RelationshipBehavior.NULLIFY

        # Check for readonly modifier
        if self.match(TokenType.READONLY):
            self.advance()
            readonly = True

        return behavior, readonly

    def parse_field_modifiers(
        self,
    ) -> tuple[list[ir.FieldModifier], str | int | float | bool | None]:
        """
        Parse field modifiers and default value.

        Returns:
            Tuple of (modifiers, default_value)
        """
        modifiers = []
        default: str | int | float | bool | None = None

        while True:
            token = self.current_token()

            if token.value == "required":
                self.advance()
                modifiers.append(ir.FieldModifier.REQUIRED)
            elif token.value == "optional":
                self.advance()
                modifiers.append(ir.FieldModifier.OPTIONAL)
            elif token.value == "pk":
                self.advance()
                modifiers.append(ir.FieldModifier.PK)
            elif token.value == "unique":
                self.advance()
                if self.match(TokenType.QUESTION):
                    self.advance()
                    modifiers.append(ir.FieldModifier.UNIQUE_NULLABLE)
                else:
                    modifiers.append(ir.FieldModifier.UNIQUE)
            elif token.value == "auto_add":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_ADD)
            elif token.value == "auto_update":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_UPDATE)
            elif self.match(TokenType.EQUALS):
                # default=value
                self.advance()
                if self.match(TokenType.STRING):
                    default = self.advance().value
                elif self.match(TokenType.NUMBER):
                    num_str = self.advance().value
                    default = float(num_str) if "." in num_str else int(num_str)
                elif self.match(TokenType.TRUE):
                    self.advance()
                    default = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    default = False
                elif self.match(TokenType.IDENTIFIER):
                    # Could be enum value or boolean (for backwards compatibility)
                    val = self.advance().value
                    if val in ("true", "false"):
                        default = val == "true"
                    else:
                        default = val
            else:
                break

        return modifiers, default

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

        fields: list[ir.FieldSpec] = []
        computed_fields: list[ir.ComputedFieldSpec] = []
        constraints: list[ir.Constraint] = []
        visibility_rules: list[ir.VisibilityRule] = []
        permission_rules: list[ir.PermissionRule] = []
        transitions: list[ir.StateTransition] = []
        invariants: list[ir.InvariantSpec] = []

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
            fields=fields,
            computed_fields=computed_fields,
            invariants=invariants,
            constraints=constraints,
            access=access,
            state_machine=state_machine,
            examples=examples,
        )

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
                    # Unknown token, break
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

    def _parse_field_path(self) -> list[str]:
        """
        Parse a field path like 'field' or 'relation.field' or 'relation.subrelation.field'.

        Returns a list of path components.
        """
        path = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.DOT):
            self.advance()
            path.append(self.expect_identifier_or_keyword().value)

        return path

    # =========================================================================
    # Archetype Parsing (v0.7.1)
    # =========================================================================

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

    # =========================================================================
    # Example Record Parsing (v0.7.1)
    # =========================================================================

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

        # Expect opening brace (we'll use LBRACKET for { since lexer might not have LBRACE)
        # Actually, let's check if we have a brace-like syntax or use a simpler approach
        # For now, parse key:value pairs until newline

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

    def _parse_literal_value(self) -> str | int | float | bool | None:
        """Parse a literal value (string, number, boolean, or null)."""
        if self.match(TokenType.STRING):
            return self.advance().value
        elif self.match(TokenType.NUMBER):
            num_str = self.advance().value
            if "." in num_str:
                return float(num_str)
            return int(num_str)
        elif self.match(TokenType.TRUE):
            self.advance()
            return True
        elif self.match(TokenType.FALSE):
            self.advance()
            return False
        elif self.match(TokenType.IDENTIFIER):
            val = self.current_token().value
            if val == "null" or val == "None":
                self.advance()
                return None
            # Treat as string value (for enum values etc)
            return self.advance().value
        else:
            # Allow keywords as values (e.g., enum values)
            if self._is_keyword_as_identifier():
                return self.advance().value
            token = self.current_token()
            raise make_parse_error(
                f"Expected literal value, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def _is_keyword_as_identifier(self) -> bool:
        """Check if current token is a keyword that can be used as identifier."""
        return self.current_token().type in (
            TokenType.TRUE,
            TokenType.FALSE,
            TokenType.CRITICAL,
            TokenType.WARNING,
            TokenType.NOTICE,
            TokenType.INFO,
            # Add more as needed
        )

    # =========================================================================
    # Invariant Expression Parsing
    # =========================================================================

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
            - Duration expressions: 14 days, 2 hours
            - Parenthesized expressions: (expr)

        Syntax:
            invariant_primary ::= field_ref | NUMBER | STRING | BOOL | duration | "(" invariant_expr ")"
        """
        # Check for parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self._parse_invariant_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Check for numeric literal
        if self.match(TokenType.NUMBER):
            token = self.advance()
            value = float(token.value) if "." in token.value else int(token.value)

            # Check if followed by duration unit
            duration_units = {
                TokenType.DAYS: ir.DurationUnit.DAYS,
                TokenType.HOURS: ir.DurationUnit.HOURS,
                TokenType.MINUTES: ir.DurationUnit.MINUTES,
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

        # Must be a field reference
        field_path = self._parse_field_path()
        return ir.InvariantFieldRef(path=field_path)

    def parse_surface(self) -> ir.SurfaceSpec:
        """Parse surface declaration."""
        self.expect(TokenType.SURFACE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        entity_ref = None
        mode = ir.SurfaceMode.CUSTOM
        sections = []
        actions = []
        ux_spec = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # uses entity EntityName
            if self.match(TokenType.USES):
                self.advance()
                self.expect(TokenType.ENTITY)
                entity_ref = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # mode: view|create|edit|list|custom
            elif self.match(TokenType.MODE):
                self.advance()
                self.expect(TokenType.COLON)
                mode_token = self.expect_identifier_or_keyword()
                mode = ir.SurfaceMode(mode_token.value)
                self.skip_newlines()

            # section name ["title"]:
            elif self.match(TokenType.SECTION):
                section = self.parse_surface_section()
                sections.append(section)

            # action name ["label"]:
            elif self.match(TokenType.ACTION):
                action = self.parse_surface_action()
                actions.append(action)

            # ux: (UX Semantic Layer block)
            elif self.match(TokenType.UX):
                ux_spec = self.parse_ux_block()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.SurfaceSpec(
            name=name,
            title=title,
            entity_ref=entity_ref,
            mode=mode,
            sections=sections,
            actions=actions,
            ux=ux_spec,
        )

    def parse_surface_section(self) -> ir.SurfaceSection:
        """Parse surface section."""
        self.expect(TokenType.SECTION)

        name = self.expect_identifier_or_keyword().value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        elements = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field field_name ["label"]
            if self.match(TokenType.FIELD):
                self.advance()
                field_name = self.expect_identifier_or_keyword().value
                label = None

                if self.match(TokenType.STRING):
                    label = self.advance().value

                elements.append(
                    ir.SurfaceElement(
                        field_name=field_name,
                        label=label,
                    )
                )

                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.SurfaceSection(
            name=name,
            title=title,
            elements=elements,
        )

    def parse_surface_action(self) -> ir.SurfaceAction:
        """Parse surface action."""
        self.expect(TokenType.ACTION)

        name = self.expect_identifier_or_keyword().value
        label = None

        if self.match(TokenType.STRING):
            label = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # on submit|click|auto -> outcome
        self.expect(TokenType.ON)
        trigger_token = self.expect(TokenType.IDENTIFIER)
        trigger = ir.SurfaceTrigger(trigger_token.value)

        self.expect(TokenType.ARROW)

        outcome = self.parse_outcome()

        self.skip_newlines()
        self.expect(TokenType.DEDENT)

        return ir.SurfaceAction(
            name=name,
            label=label,
            trigger=trigger,
            outcome=outcome,
        )

    def parse_outcome(self) -> ir.Outcome:
        """Parse action outcome."""
        # surface SurfaceName
        if self.match(TokenType.SURFACE):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            return ir.Outcome(kind=ir.OutcomeKind.SURFACE, target=target)

        # experience ExperienceName [step StepName]
        elif self.match(TokenType.EXPERIENCE):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            step = None

            if self.match(TokenType.STEP):
                self.advance()
                step = self.expect(TokenType.IDENTIFIER).value

            return ir.Outcome(kind=ir.OutcomeKind.EXPERIENCE, target=target, step=step)

        # integration IntegrationName action ActionName
        elif self.match(TokenType.INTEGRATION):
            self.advance()
            target = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ACTION)
            action = self.expect(TokenType.IDENTIFIER).value

            return ir.Outcome(kind=ir.OutcomeKind.INTEGRATION, target=target, action=action)

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected outcome (surface/experience/integration), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse_service(self) -> ir.APISpec | ir.DomainServiceSpec:
        """Parse service declaration (external API or domain service).

        External APIs have: spec, auth_profile, owner
        Domain services have: kind, input, output, guarantees, stub
        """
        self.expect(TokenType.SERVICE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Peek at first directive to determine service type
        self.skip_newlines()
        if self.match(TokenType.KIND):
            # Domain service (v0.5.0)
            return self._parse_domain_service_body(name, title)
        else:
            # External API (original behavior)
            return self._parse_external_api_body(name, title)

    def _parse_external_api_body(self, name: str, title: str | None) -> ir.APISpec:
        """Parse external API service body."""
        spec_url = None
        spec_inline = None
        auth_profile = None
        owner = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # spec: url "..."
            if self.match(TokenType.SPEC):
                self.advance()
                self.expect(TokenType.COLON)

                if self.match(TokenType.URL):
                    self.advance()
                    spec_url = self.expect(TokenType.STRING).value
                elif self.match(TokenType.INLINE):
                    self.advance()
                    spec_inline = self.expect(TokenType.STRING).value

                self.skip_newlines()

            # auth_profile: kind [options...]
            elif self.match(TokenType.AUTH_PROFILE):
                self.advance()
                self.expect(TokenType.COLON)

                auth_kind_token = self.expect(TokenType.IDENTIFIER)
                auth_kind = ir.AuthKind(auth_kind_token.value)

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)
                    value = self.expect(TokenType.STRING).value
                    options[key] = value

                auth_profile = ir.AuthProfile(kind=auth_kind, options=options)
                self.skip_newlines()

            # owner: "..."
            elif self.match(TokenType.OWNER):
                self.advance()
                self.expect(TokenType.COLON)
                owner = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if auth_profile is None:
            token = self.current_token()
            raise make_parse_error(
                "Service must have auth_profile",
                self.file,
                token.line,
                token.column,
            )

        return ir.APISpec(
            name=name,
            title=title,
            spec_url=spec_url,
            spec_inline=spec_inline,
            auth_profile=auth_profile,
            owner=owner,
        )

    def _parse_domain_service_body(self, name: str, title: str | None) -> ir.DomainServiceSpec:
        """Parse domain service body (v0.5.0).

        DSL syntax:
            service calculate_vat "Calculate VAT":
              kind: domain_logic

              input:
                invoice_id: uuid required

              output:
                vat_amount: money
                breakdown: json

              guarantees:
                - "Must not mutate the invoice record."

              stub: python
        """
        kind = ir.DomainServiceKind.DOMAIN_LOGIC
        inputs: list[ir.ServiceFieldSpec] = []
        outputs: list[ir.ServiceFieldSpec] = []
        guarantees: list[str] = []
        stub_language = ir.StubLanguage.PYTHON

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # kind: domain_logic | validation | integration | workflow
            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                # Use expect_identifier_or_keyword since 'integration' is a keyword
                kind_token = self.expect_identifier_or_keyword()
                kind = ir.DomainServiceKind(kind_token.value)
                self.skip_newlines()

            # input:
            elif self.match(TokenType.INPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                inputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # output:
            elif self.match(TokenType.OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                outputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # guarantees:
            elif self.match(TokenType.GUARANTEES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                guarantees = self._parse_guarantee_list()
                self.expect(TokenType.DEDENT)

            # stub: python | typescript
            elif self.match(TokenType.STUB):
                self.advance()
                self.expect(TokenType.COLON)
                lang_token = self.expect(TokenType.IDENTIFIER)
                stub_language = ir.StubLanguage(lang_token.value)
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.DomainServiceSpec(
            name=name,
            title=title,
            kind=kind,
            inputs=inputs,
            outputs=outputs,
            guarantees=guarantees,
            stub_language=stub_language,
        )

    def _parse_service_fields(self) -> list[ir.ServiceFieldSpec]:
        """Parse service input/output fields.

        Format:
            field_name: type_name [required]
        """
        fields: list[ir.ServiceFieldSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field_name: type_name [required]
            field_name = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.COLON)

            # Parse type - could be identifier or type with params like decimal(10,2)
            type_name = self.expect(TokenType.IDENTIFIER).value

            # Check for type parameters like (10,2) or (200)
            if self.match(TokenType.LPAREN):
                self.advance()
                params = []
                params.append(self.expect(TokenType.NUMBER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    params.append(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.RPAREN)
                type_name = f"{type_name}({','.join(params)})"

            # Check for required modifier
            required = False
            if self.match(TokenType.IDENTIFIER):
                if self.current_token().value == "required":
                    self.advance()
                    required = True

            fields.append(
                ir.ServiceFieldSpec(
                    name=field_name,
                    type_name=type_name,
                    required=required,
                )
            )
            self.skip_newlines()

        return fields

    def _parse_guarantee_list(self) -> list[str]:
        """Parse guarantee list (strings prefixed with dash).

        Format:
            - "Guarantee text here"
            - "Another guarantee"
        """
        guarantees: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # - "guarantee text"
            if self.match(TokenType.MINUS):
                self.advance()
                guarantee_text = self.expect(TokenType.STRING).value
                guarantees.append(guarantee_text)
                self.skip_newlines()
            else:
                break

        return guarantees

    def parse_experience(self) -> ir.ExperienceSpec:
        """Parse experience declaration."""
        self.expect(TokenType.EXPERIENCE)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # start at step StepName
        self.expect(TokenType.START)
        self.expect(TokenType.AT)
        self.expect(TokenType.STEP)
        start_step = self.expect(TokenType.IDENTIFIER).value
        self.skip_newlines()

        steps = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.STEP):
                step = self.parse_experience_step()
                steps.append(step)

        self.expect(TokenType.DEDENT)

        return ir.ExperienceSpec(
            name=name,
            title=title,
            start_step=start_step,
            steps=steps,
        )

    def parse_experience_step(self) -> ir.ExperienceStep:
        """Parse experience step."""
        self.expect(TokenType.STEP)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # kind: surface|process|integration
        self.expect(TokenType.KIND)
        self.expect(TokenType.COLON)
        kind_token = self.expect_identifier_or_keyword()
        kind = ir.StepKind(kind_token.value)
        self.skip_newlines()

        surface = None
        integration = None
        action = None

        # Parse step target based on kind
        if kind == ir.StepKind.SURFACE:
            self.expect(TokenType.SURFACE)
            surface = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()

        elif kind == ir.StepKind.INTEGRATION:
            self.expect(TokenType.INTEGRATION)
            integration = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ACTION)
            action = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()

        # Parse transitions
        transitions = []
        while self.match(TokenType.ON):
            self.advance()

            event_token = self.expect(TokenType.IDENTIFIER)
            event = ir.TransitionEvent(event_token.value)

            self.expect(TokenType.ARROW)
            self.expect(TokenType.STEP)
            next_step = self.expect(TokenType.IDENTIFIER).value

            transitions.append(
                ir.StepTransition(
                    event=event,
                    next_step=next_step,
                )
            )

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ExperienceStep(
            name=name,
            kind=kind,
            surface=surface,
            integration=integration,
            action=action,
            transitions=transitions,
        )

    def parse_foreign_model(self) -> ir.ForeignModelSpec:
        """Parse foreign_model declaration."""
        self.expect(TokenType.FOREIGN_MODEL)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.FROM)
        api_ref = self.expect(TokenType.IDENTIFIER).value

        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        key_fields = []
        constraints = []
        fields = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # key: field1[,field2,...]
            if self.match(TokenType.KEY):
                self.advance()
                self.expect(TokenType.COLON)

                key_fields.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    key_fields.append(self.expect(TokenType.IDENTIFIER).value)

                self.skip_newlines()

            # constraint kind [options...]
            elif self.match(TokenType.CONSTRAINT):
                self.advance()

                constraint_kind_token = self.expect(TokenType.IDENTIFIER)
                constraint_kind = ir.ForeignConstraintKind(constraint_kind_token.value)

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)

                    if self.match(TokenType.STRING):
                        options[key] = self.advance().value
                    elif self.match(TokenType.NUMBER):
                        options[key] = self.advance().value
                    elif self.match(TokenType.IDENTIFIER):
                        options[key] = self.advance().value

                constraints.append(
                    ir.ForeignConstraint(
                        kind=constraint_kind,
                        options=options,
                    )
                )

                self.skip_newlines()

            # field_name: type [modifiers...]
            else:
                field_name = self.expect_identifier_or_keyword().value
                self.expect(TokenType.COLON)

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

        return ir.ForeignModelSpec(
            name=name,
            title=title,
            api_ref=api_ref,
            key_fields=key_fields,
            constraints=constraints,
            fields=fields,
        )

    def parse_integration(self) -> ir.IntegrationSpec:
        """Parse integration declaration - simplified version for Stage 2."""
        self.expect(TokenType.INTEGRATION)

        name = self.expect(TokenType.IDENTIFIER).value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        api_refs = []
        foreign_model_refs = []
        actions = []
        syncs = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # uses service ServiceName[,ServiceName] (DSL keyword still "service", maps to API)
            if self.match(TokenType.USES):
                self.advance()

                if self.match(TokenType.SERVICE):
                    self.advance()
                    api_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    while self.match(TokenType.COMMA):
                        self.advance()
                        api_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    self.skip_newlines()

                # uses foreign ForeignName[,ForeignName]
                elif self.match(TokenType.FOREIGN):
                    self.advance()
                    foreign_model_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    while self.match(TokenType.COMMA):
                        self.advance()
                        foreign_model_refs.append(self.expect(TokenType.IDENTIFIER).value)

                    self.skip_newlines()

            # action action_name:
            elif self.match(TokenType.ACTION):
                self.advance()
                action_name = self.expect(TokenType.IDENTIFIER).value

                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                # Parse action body
                action = self._parse_action_body(action_name)
                actions.append(action)

                self.expect(TokenType.DEDENT)

            # sync sync_name:
            elif self.match(TokenType.SYNC):
                self.advance()
                sync_name = self.expect(TokenType.IDENTIFIER).value

                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                # Parse sync body
                sync = self._parse_sync_body(sync_name)
                syncs.append(sync)

                self.expect(TokenType.DEDENT)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.IntegrationSpec(
            name=name,
            title=title,
            api_refs=api_refs,
            foreign_model_refs=foreign_model_refs,
            actions=actions,
            syncs=syncs,
        )

    def _parse_action_body(self, action_name: str) -> ir.IntegrationAction:
        """Parse the body of an action block."""
        when_surface = None
        call_service = None
        call_operation = None
        call_mapping = []
        response_foreign_model = None
        response_entity = None
        response_mapping = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # when surface <name>
            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.SURFACE)
                when_surface = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # call service <name>
            elif self.match(TokenType.CALL):
                self.advance()
                if self.match(TokenType.SERVICE):
                    self.advance()
                    call_service = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # call operation <path>
                elif self.match(TokenType.OPERATION):
                    self.advance()
                    call_operation = self._parse_operation_path()
                    self.skip_newlines()

                # call mapping:
                elif self.match(TokenType.MAPPING):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    call_mapping = self._parse_mapping_rules()
                    self.expect(TokenType.DEDENT)

            # response foreign <name>
            elif self.match(TokenType.RESPONSE):
                self.advance()
                if self.match(TokenType.FOREIGN):
                    self.advance()
                    response_foreign_model = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # response entity <name>
                elif self.match(TokenType.ENTITY):
                    self.advance()
                    response_entity = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # response mapping:
                elif self.match(TokenType.MAPPING):
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    response_mapping = self._parse_mapping_rules()
                    self.expect(TokenType.DEDENT)

            else:
                # Skip unknown tokens
                self.advance()

        return ir.IntegrationAction(
            name=action_name,
            when_surface=when_surface or "unknown",
            call_service=call_service or "unknown",
            call_operation=call_operation or "unknown",
            call_mapping=call_mapping,
            response_foreign_model=response_foreign_model,
            response_entity=response_entity,
            response_mapping=response_mapping,
        )

    def _parse_sync_body(self, sync_name: str) -> ir.IntegrationSync:
        """Parse the body of a sync block."""
        mode = ir.SyncMode.SCHEDULED
        schedule = None
        from_service = None
        from_operation = None
        from_foreign_model = None
        into_entity = None
        match_rules = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # mode: scheduled "<cron>"
            if self.match(TokenType.MODE):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.SCHEDULED):
                    self.advance()
                    mode = ir.SyncMode.SCHEDULED
                    if self.match(TokenType.STRING):
                        schedule = self.advance().value
                elif self.match(TokenType.EVENT_DRIVEN):
                    self.advance()
                    mode = ir.SyncMode.EVENT_DRIVEN
                self.skip_newlines()

            # from service <name>
            elif self.match(TokenType.FROM):
                self.advance()
                if self.match(TokenType.SERVICE):
                    self.advance()
                    from_service = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

                # from operation <path>
                elif self.match(TokenType.OPERATION):
                    self.advance()
                    from_operation = self._parse_operation_path()
                    self.skip_newlines()

                # from foreign <name>
                elif self.match(TokenType.FOREIGN):
                    self.advance()
                    from_foreign_model = self.expect(TokenType.IDENTIFIER).value
                    self.skip_newlines()

            # into entity <name>
            elif self.match(TokenType.INTO):
                self.advance()
                self.expect(TokenType.ENTITY)
                into_entity = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # match rules:
            elif self.match(TokenType.MATCH):
                self.advance()
                self.expect(TokenType.RULES)
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                match_rules = self._parse_match_rules()
                self.expect(TokenType.DEDENT)

            else:
                # Skip unknown tokens
                self.advance()

        return ir.IntegrationSync(
            name=sync_name,
            mode=mode,
            schedule=schedule,
            from_service=from_service or "unknown",
            from_operation=from_operation or "unknown",
            from_foreign_model=from_foreign_model or "unknown",
            into_entity=into_entity or "unknown",
            match_rules=match_rules,
        )

    def _parse_operation_path(self) -> str:
        """Parse an operation path like /agents/search."""
        # Operation paths can be simple identifiers or slash-separated paths
        path_parts = []

        # Handle leading slash
        if self.match(TokenType.SLASH):
            self.advance()
            path_parts.append("/")

        # Parse path components (can be identifiers or keywords)
        while True:
            token = self.current_token()
            if token.type == TokenType.IDENTIFIER or token.type.value in [
                "search",
                "filter",
                "create",
                "update",
                "delete",
                "get",
            ]:
                path_parts.append(self.advance().value)
                if self.match(TokenType.SLASH):
                    path_parts.append(self.advance().value)
                else:
                    break
            else:
                break

        return "".join(path_parts) if path_parts else "unknown"

    def _parse_mapping_rules(self) -> list[ir.MappingRule]:
        """Parse mapping rules (target → source)."""
        rules = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse target field
            target = self.expect(TokenType.IDENTIFIER).value

            # Expect arrow (→)
            self.expect(TokenType.ARROW)

            # Parse source expression (path or literal)
            source = self._parse_expression()

            rules.append(
                ir.MappingRule(
                    target_field=target,
                    source=source,
                )
            )

            self.skip_newlines()

        return rules

    def _parse_match_rules(self) -> list[ir.MatchRule]:
        """Parse match rules (foreign_field ↔ entity_field)."""
        rules = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse foreign field
            foreign_field = self.expect(TokenType.IDENTIFIER).value

            # Expect bidirectional arrow (↔)
            self.expect(TokenType.BIARROW)

            # Parse entity field
            entity_field = self.expect(TokenType.IDENTIFIER).value

            rules.append(
                ir.MatchRule(
                    foreign_field=foreign_field,
                    entity_field=entity_field,
                )
            )

            self.skip_newlines()

        return rules

    def _parse_expression(self) -> ir.Expression:
        """Parse an expression (path or literal)."""
        # Try to parse as a path first (e.g., form.vrn, entity.id)
        # Need to check for keywords that can be used as path components
        token = self.current_token()
        if token.type == TokenType.IDENTIFIER or token.value in [
            "entity",
            "form",
            "foreign",
            "service",
        ]:
            parts = [self.advance().value]

            while self.match(TokenType.DOT):
                self.advance()
                parts.append(self.expect_identifier_or_keyword().value)

            return ir.Expression(path=".".join(parts))

        # Try to parse as a literal
        elif self.match(TokenType.STRING):
            return ir.Expression(literal=self.advance().value)

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            # Try to convert to int or float
            try:
                return ir.Expression(literal=int(value))
            except ValueError:
                return ir.Expression(literal=float(value))

        elif self.match(TokenType.TRUE) or self.match(TokenType.FALSE):
            return ir.Expression(literal=self.advance().value == "true")

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected expression, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

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
                        f"Expected action kind (create, update, delete, get), got {action_token.type.value}",
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
                                f"Expected true or false, got {self.current_token().type.value}",
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
                        operator_token = self.expect(TokenType.IDENTIFIER)  # equals, contains, etc.
                        operator = self.parse_comparison_operator(operator_token.value)

                        # Check if value is another field reference
                        if self.match(TokenType.FIELD):
                            self.advance()
                            other_field = self.expect_identifier_or_keyword().value
                            expected_value = f"field.{other_field}"
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

    def parse_value(self) -> Any:
        """Parse a value (string, number, identifier, boolean)."""
        token = self.current_token()

        if self.match(TokenType.STRING):
            return self.advance().value

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            if "." in value:
                return float(value)
            return int(value)

        elif self.match(TokenType.TRUE):
            self.advance()
            return True

        elif self.match(TokenType.FALSE):
            self.advance()
            return False

        elif self.match(TokenType.IDENTIFIER):
            # Could be a variable reference
            return self.advance().value

        else:
            raise make_parse_error(
                f"Expected value, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    # =========================================================================
    # E2E Flow Parsing (v0.3.2)
    # =========================================================================

    def parse_flow(self) -> ir.FlowSpec:
        """
        Parse flow declaration.

        Syntax:
            flow flow_name "Flow Description":
              priority: high|medium|low
              tags: tag1, tag2
              preconditions:
                authenticated: true
                user_role: admin
                view: task_list
                fixtures: fixture1, fixture2
              steps:
                navigate view:task_list
                fill field:Task.title "Test Value"
                click action:Task.save
                wait 1000
                assert entity_exists Task
                assert validation_error field:Task.title
        """
        self.expect(TokenType.FLOW)

        name = self.expect(TokenType.IDENTIFIER).value
        description = None

        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        priority = ir.FlowPriority.MEDIUM
        tags: list[str] = []
        preconditions: ir.FlowPrecondition | None = None
        steps: list[ir.FlowStep] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse priority: high|medium|low
            # Note: 'priority', 'high', 'medium', 'low' are identifiers, not keywords
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "priority":
                self.advance()  # consume 'priority'
                self.expect(TokenType.COLON)
                priority_token = self.expect_identifier_or_keyword()
                priority_value = priority_token.value.lower()
                if priority_value == "high":
                    priority = ir.FlowPriority.HIGH
                elif priority_value == "medium":
                    priority = ir.FlowPriority.MEDIUM
                elif priority_value == "low":
                    priority = ir.FlowPriority.LOW
                else:
                    raise make_parse_error(
                        f"Expected priority (high, medium, low), got {priority_value}",
                        self.file,
                        priority_token.line,
                        priority_token.column,
                    )
                self.skip_newlines()

            # Parse tags: tag1, tag2
            elif self.match(TokenType.TAGS):
                self.advance()
                self.expect(TokenType.COLON)
                tag = self.expect(TokenType.IDENTIFIER).value
                tags.append(tag)
                while self.match(TokenType.COMMA):
                    self.advance()
                    tag = self.expect(TokenType.IDENTIFIER).value
                    tags.append(tag)
                self.skip_newlines()

            # Parse preconditions block
            elif self.match(TokenType.PRECONDITIONS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                preconditions = self.parse_flow_preconditions()
                self.expect(TokenType.DEDENT)

            # Parse steps block
            elif self.match(TokenType.STEPS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    step = self.parse_flow_step()
                    steps.append(step)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            else:
                # Unknown token in flow, skip
                self.advance()

        self.expect(TokenType.DEDENT)

        return ir.FlowSpec(
            id=name,
            description=description,
            priority=priority,
            preconditions=preconditions,
            steps=steps,
            tags=tags,
        )

    def parse_flow_preconditions(self) -> ir.FlowPrecondition:
        """Parse flow preconditions block."""
        authenticated = False
        user_role: str | None = None
        view: str | None = None
        fixtures: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # authenticated: true|false
            if self.match(TokenType.AUTHENTICATED):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    authenticated = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    authenticated = False
                self.skip_newlines()

            # user_role: role_name
            elif self.match(TokenType.USER_ROLE):
                self.advance()
                self.expect(TokenType.COLON)
                user_role = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # view: view_name
            elif self.match(TokenType.VIEW):
                self.advance()
                self.expect(TokenType.COLON)
                view = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # fixtures: fixture1, fixture2
            elif self.match(TokenType.FIXTURES):
                self.advance()
                self.expect(TokenType.COLON)
                fixture = self.expect(TokenType.IDENTIFIER).value
                fixtures.append(fixture)
                while self.match(TokenType.COMMA):
                    self.advance()
                    fixture = self.expect(TokenType.IDENTIFIER).value
                    fixtures.append(fixture)
                self.skip_newlines()

            else:
                self.advance()

        return ir.FlowPrecondition(
            authenticated=authenticated,
            user_role=user_role,
            view=view,
            fixtures=fixtures,
        )

    def parse_flow_step(self) -> ir.FlowStep:
        """Parse a single flow step."""
        # navigate view:target
        if self.match(TokenType.NAVIGATE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowStep(kind=ir.FlowStepKind.NAVIGATE, target=target)

        # fill field:target "value" | fill field:target fixture_ref
        elif self.match(TokenType.FILL):
            self.advance()
            target = self.parse_semantic_target()
            value: str | None = None
            fixture_ref: str | None = None
            if self.match(TokenType.STRING):
                value = self.advance().value
            elif self.match(TokenType.IDENTIFIER):
                # Could be a fixture reference like Task_valid.title
                fixture_ref = self.advance().value
                if self.match(TokenType.DOT):
                    self.advance()
                    field = self.expect(TokenType.IDENTIFIER).value
                    fixture_ref = f"{fixture_ref}.{field}"
            return ir.FlowStep(
                kind=ir.FlowStepKind.FILL,
                target=target,
                value=value,
                fixture_ref=fixture_ref,
            )

        # click action:target
        elif self.match(TokenType.CLICK):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowStep(kind=ir.FlowStepKind.CLICK, target=target)

        # wait 1000 | wait view:target
        elif self.match(TokenType.WAIT):
            self.advance()
            if self.match(TokenType.NUMBER):
                value = self.advance().value
                return ir.FlowStep(kind=ir.FlowStepKind.WAIT, value=value)
            else:
                target = self.parse_semantic_target()
                return ir.FlowStep(kind=ir.FlowStepKind.WAIT, target=target)

        # snapshot
        elif self.match(TokenType.SNAPSHOT):
            self.advance()
            return ir.FlowStep(kind=ir.FlowStepKind.SNAPSHOT)

        # assert assertion_kind target [expected]
        elif self.match(TokenType.EXPECT):
            self.advance()
            assertion = self.parse_flow_assertion()
            return ir.FlowStep(kind=ir.FlowStepKind.ASSERT, assertion=assertion)

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected flow step (navigate, fill, click, wait, snapshot, expect), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse_semantic_target(self) -> str:
        """Parse a semantic target like view:task_list or field:Task.title."""
        # Format: type:identifier or type:Entity.field
        # target_type can be keywords like 'view', 'field', 'action', 'entity', 'row'
        target_type = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        identifier = self.expect_identifier_or_keyword().value

        # Check for dotted notation (Entity.field)
        if self.match(TokenType.DOT):
            self.advance()
            field = self.expect_identifier_or_keyword().value
            identifier = f"{identifier}.{field}"

        return f"{target_type}:{identifier}"

    def parse_flow_assertion(self) -> ir.FlowAssertion:
        """Parse a flow assertion."""
        # entity_exists Entity [where field=value]
        if self.match(TokenType.ENTITY_EXISTS):
            self.advance()
            entity = self.expect(TokenType.IDENTIFIER).value
            expected: dict[str, Any] | None = None
            if self.match(TokenType.WHERE):
                self.advance()
                expected = {}
                field = self.expect(TokenType.IDENTIFIER).value
                self.expect(TokenType.EQUALS)
                value = self.parse_value()
                expected[field] = value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.ENTITY_EXISTS,
                target=f"entity:{entity}",
                expected=expected,
            )

        # entity_not_exists Entity
        elif self.match(TokenType.ENTITY_NOT_EXISTS):
            self.advance()
            entity = self.expect(TokenType.IDENTIFIER).value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.ENTITY_NOT_EXISTS,
                target=f"entity:{entity}",
            )

        # validation_error field:Target.field
        elif self.match(TokenType.VALIDATION_ERROR):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.VALIDATION_ERROR,
                target=target,
            )

        # visible view:target | visible field:target
        elif self.match(TokenType.VISIBLE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.VISIBLE,
                target=target,
            )

        # not_visible target
        elif self.match(TokenType.NOT_VISIBLE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.NOT_VISIBLE,
                target=target,
            )

        # text_contains "expected text"
        elif self.match(TokenType.TEXT_CONTAINS):
            self.advance()
            expected_text = self.expect(TokenType.STRING).value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.TEXT_CONTAINS,
                expected=expected_text,
            )

        # redirects_to view:target
        elif self.match(TokenType.REDIRECTS_TO):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.REDIRECTS_TO,
                target=target,
            )

        # field_value field:target "expected"
        elif self.match(TokenType.FIELD_VALUE):
            self.advance()
            target = self.parse_semantic_target()
            expected_value = self.parse_value()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.FIELD_VALUE,
                target=target,
                expected=expected_value,
            )

        # count entity:Entity 5
        elif self.match(TokenType.COUNT):
            self.advance()
            target = self.parse_semantic_target()
            expected_count = int(self.expect(TokenType.NUMBER).value)
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.COUNT,
                target=target,
                expected=expected_count,
            )

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected assertion kind, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    # =========================================================================
    # UX Semantic Layer Parsing
    # =========================================================================

    def parse_ux_block(self) -> ir.UXSpec:
        """
        Parse UX block within a surface.

        Syntax:
            ux:
              purpose: "..."
              show: field1, field2
              sort: field1 desc, field2 asc
              filter: field1, field2
              search: field1, field2
              empty: "..."
              attention critical:
                when: condition
                message: "..."
                action: surface_name
              for persona_name:
                scope: ...
                ...
        """
        self.expect(TokenType.UX)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        purpose = None
        show: list[str] = []
        sort: list[ir.SortSpec] = []
        filter_fields: list[str] = []
        search_fields: list[str] = []
        empty_message = None
        attention_signals: list[ir.AttentionSignal] = []
        persona_variants: list[ir.PersonaVariant] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # purpose: "..."
            if self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # show: field1, field2
            elif self.match(TokenType.SHOW):
                self.advance()
                self.expect(TokenType.COLON)
                show = self.parse_field_list()
                self.skip_newlines()

            # sort: field1 desc, field2 asc
            elif self.match(TokenType.SORT):
                self.advance()
                self.expect(TokenType.COLON)
                sort = self.parse_sort_list()
                self.skip_newlines()

            # filter: field1, field2
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                filter_fields = self.parse_field_list()
                self.skip_newlines()

            # search: field1, field2
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                search_fields = self.parse_field_list()
                self.skip_newlines()

            # empty: "..."
            elif self.match(TokenType.EMPTY):
                self.advance()
                self.expect(TokenType.COLON)
                empty_message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # attention critical/warning/notice/info:
            elif self.match(TokenType.ATTENTION):
                signal = self.parse_attention_signal()
                attention_signals.append(signal)

            # for persona_name:
            elif self.match(TokenType.FOR):
                variant = self.parse_persona_variant()
                persona_variants.append(variant)

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.UXSpec(
            purpose=purpose,
            show=show,
            sort=sort,
            filter=filter_fields,
            search=search_fields,
            empty_message=empty_message,
            attention_signals=attention_signals,
            persona_variants=persona_variants,
        )

    def parse_field_list(self) -> list[str]:
        """Parse comma-separated list of field names."""
        fields = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.COMMA):
            self.advance()
            fields.append(self.expect_identifier_or_keyword().value)

        return fields

    def parse_sort_list(self) -> list[ir.SortSpec]:
        """Parse comma-separated list of sort expressions (field [asc|desc])."""
        sorts = []

        field = self.expect_identifier_or_keyword().value
        direction = "asc"
        if self.match(TokenType.ASC):
            self.advance()
            direction = "asc"
        elif self.match(TokenType.DESC):
            self.advance()
            direction = "desc"
        sorts.append(ir.SortSpec(field=field, direction=direction))

        while self.match(TokenType.COMMA):
            self.advance()
            field = self.expect_identifier_or_keyword().value
            direction = "asc"
            if self.match(TokenType.ASC):
                self.advance()
                direction = "asc"
            elif self.match(TokenType.DESC):
                self.advance()
                direction = "desc"
            sorts.append(ir.SortSpec(field=field, direction=direction))

        return sorts

    def parse_attention_signal(self) -> ir.AttentionSignal:
        """
        Parse attention signal block.

        Syntax:
            attention critical:
              when: condition_expr
              message: "..."
              action: surface_name
        """
        self.expect(TokenType.ATTENTION)

        # Parse signal level
        if self.match(TokenType.CRITICAL):
            level = ir.SignalLevel.CRITICAL
            self.advance()
        elif self.match(TokenType.WARNING):
            level = ir.SignalLevel.WARNING
            self.advance()
        elif self.match(TokenType.NOTICE):
            level = ir.SignalLevel.NOTICE
            self.advance()
        elif self.match(TokenType.INFO):
            level = ir.SignalLevel.INFO
            self.advance()
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected signal level (critical/warning/notice/info), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        condition = None
        message = None
        action = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # when: condition_expr
            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                self.skip_newlines()

            # message: "..."
            elif self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # action: surface_name
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if condition is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'when:' condition",
                self.file,
                token.line,
                token.column,
            )

        if message is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'message:'",
                self.file,
                token.line,
                token.column,
            )

        return ir.AttentionSignal(
            level=level,
            condition=condition,
            message=message,
            action=action,
        )

    def parse_persona_variant(self) -> ir.PersonaVariant:
        """
        Parse persona variant block.

        Syntax:
            for persona_name:
              scope: all | condition_expr
              purpose: "..."
              show: field1, field2
              hide: field1, field2
              show_aggregate: metric1, metric2
              action_primary: surface_name
              read_only: true|false
        """
        self.expect(TokenType.FOR)
        persona = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        scope = None
        scope_all = False
        purpose = None
        show: list[str] = []
        hide: list[str] = []
        show_aggregate: list[str] = []
        action_primary = None
        read_only = False
        defaults: dict[str, Any] = {}
        focus: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # scope: all | condition_expr
            if self.match(TokenType.SCOPE):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.ALL):
                    self.advance()
                    scope_all = True
                else:
                    scope = self.parse_condition_expr()
                self.skip_newlines()

            # purpose: "..."
            elif self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # show: field1, field2
            elif self.match(TokenType.SHOW):
                self.advance()
                self.expect(TokenType.COLON)
                show = self.parse_field_list()
                self.skip_newlines()

            # hide: field1, field2
            elif self.match(TokenType.HIDE):
                self.advance()
                self.expect(TokenType.COLON)
                hide = self.parse_field_list()
                self.skip_newlines()

            # show_aggregate: metric1, metric2
            elif self.match(TokenType.SHOW_AGGREGATE):
                self.advance()
                self.expect(TokenType.COLON)
                show_aggregate = self.parse_field_list()
                self.skip_newlines()

            # action_primary: surface_name
            elif self.match(TokenType.ACTION_PRIMARY):
                self.advance()
                self.expect(TokenType.COLON)
                action_primary = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # read_only: true|false
            elif self.match(TokenType.READ_ONLY):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    read_only = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    read_only = False
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Expected true or false, got {token.type.value}",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # defaults:
            elif self.match(TokenType.DEFAULTS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    # field_name: value
                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    # Parse value (could be identifier, string, etc.)
                    if self.match(TokenType.STRING):
                        defaults[field_name] = self.advance().value
                    else:
                        # For identifiers like current_user
                        defaults[field_name] = self.expect_identifier_or_keyword().value
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

            # focus: region1, region2
            elif self.match(TokenType.FOCUS):
                self.advance()
                self.expect(TokenType.COLON)
                focus = self.parse_field_list()
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.PersonaVariant(
            persona=persona,
            scope=scope,
            scope_all=scope_all,
            purpose=purpose,
            show=show,
            hide=hide,
            show_aggregate=show_aggregate,
            action_primary=action_primary,
            read_only=read_only,
            defaults=defaults,
            focus=focus,
        )

    def parse_condition_expr(self) -> ir.ConditionExpr:
        """
        Parse condition expression with full AST.

        Supports:
            - Simple comparisons: field = value, field in [a, b]
            - Function calls: days_since(field) > 30
            - Compound conditions: cond1 and cond2, cond1 or cond2
            - Parenthesized expressions: (cond1 and cond2) or cond3
        """
        return self._parse_or_expr()

    def _parse_or_expr(self) -> ir.ConditionExpr:
        """Parse OR expression (lowest precedence)."""
        left = self._parse_and_expr()

        while self.match(TokenType.OR):
            self.advance()
            right = self._parse_and_expr()
            left = ir.ConditionExpr(
                left=left,
                operator=ir.LogicalOperator.OR,
                right=right,
            )

        return left

    def _parse_and_expr(self) -> ir.ConditionExpr:
        """Parse AND expression."""
        left = self._parse_primary_condition()

        while self.match(TokenType.AND):
            self.advance()
            right = self._parse_primary_condition()
            left = ir.ConditionExpr(
                left=left,
                operator=ir.LogicalOperator.AND,
                right=right,
            )

        return left

    def _parse_primary_condition(self) -> ir.ConditionExpr:
        """Parse primary condition (comparison, role check, or parenthesized expr)."""
        # Handle parentheses
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self._parse_or_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Handle role(name) - standalone role check (v0.7.0)
        if self.match(TokenType.ROLE):
            self.advance()
            self.expect(TokenType.LPAREN)
            role_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.RPAREN)
            return ir.ConditionExpr(role_check=ir.RoleCheck(role_name=role_name))

        # Parse comparison
        comparison = self._parse_comparison()
        return ir.ConditionExpr(comparison=comparison)

    def _parse_comparison(self) -> ir.Comparison:
        """
        Parse a single comparison.

        Examples:
            field = value
            field in [a, b, c]
            field is null
            days_since(field) > 30
            owner.team = current_team  (v0.7.0 - relationship traversal)
        """
        # Check for function call
        function = None
        field = None

        token = self.current_token()
        if token.type == TokenType.IDENTIFIER:
            name = self.advance().value
            if self.match(TokenType.LPAREN):
                # Function call
                self.advance()
                arg = self.expect_identifier_or_keyword().value
                self.expect(TokenType.RPAREN)
                function = ir.FunctionCall(name=name, argument=arg)
            else:
                # Check for dotted path (owner.team) - v0.7.0
                field = name
                while self.match(TokenType.DOT):
                    self.advance()
                    next_part = self.expect_identifier_or_keyword().value
                    field = f"{field}.{next_part}"
        else:
            # Allow keywords as field names
            field = self.expect_identifier_or_keyword().value
            # Also check for dotted path after keyword field names
            while self.match(TokenType.DOT):
                self.advance()
                next_part = self.expect_identifier_or_keyword().value
                field = f"{field}.{next_part}"

        # Parse operator
        operator = self._parse_comparison_operator()

        # Parse value
        value = self._parse_condition_value()

        return ir.Comparison(
            field=field,
            function=function,
            operator=operator,
            value=value,
        )

    def _parse_comparison_operator(self) -> ir.ComparisonOperator:
        """Parse comparison operator."""
        token = self.current_token()

        if self.match(TokenType.EQUALS):
            self.advance()
            return ir.ComparisonOperator.EQUALS
        elif self.match(TokenType.NOT_EQUALS):
            self.advance()
            return ir.ComparisonOperator.NOT_EQUALS
        elif self.match(TokenType.GREATER_THAN):
            self.advance()
            return ir.ComparisonOperator.GREATER_THAN
        elif self.match(TokenType.LESS_THAN):
            self.advance()
            return ir.ComparisonOperator.LESS_THAN
        elif self.match(TokenType.GREATER_EQUAL):
            self.advance()
            return ir.ComparisonOperator.GREATER_EQUAL
        elif self.match(TokenType.LESS_EQUAL):
            self.advance()
            return ir.ComparisonOperator.LESS_EQUAL
        elif self.match(TokenType.IN):
            self.advance()
            return ir.ComparisonOperator.IN
        elif self.match(TokenType.NOT):
            self.advance()
            if self.match(TokenType.IN):
                self.advance()
                return ir.ComparisonOperator.NOT_IN
            else:
                raise make_parse_error(
                    "Expected 'in' after 'not'",
                    self.file,
                    token.line,
                    token.column,
                )
        elif self.match(TokenType.IS):
            self.advance()
            if self.match(TokenType.NOT):
                self.advance()
                return ir.ComparisonOperator.IS_NOT
            return ir.ComparisonOperator.IS
        else:
            raise make_parse_error(
                f"Expected comparison operator, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_condition_value(self) -> ir.ConditionValue:
        """Parse value in a condition (literal, identifier, or list)."""
        # List value: [a, b, c]
        if self.match(TokenType.LBRACKET):
            self.advance()
            values: list[str | int | float | bool] = []

            if not self.match(TokenType.RBRACKET):
                val = self._parse_literal_value()
                if val is not None:
                    values.append(val)
                while self.match(TokenType.COMMA):
                    self.advance()
                    val = self._parse_literal_value()
                    if val is not None:
                        values.append(val)

            self.expect(TokenType.RBRACKET)
            return ir.ConditionValue(values=values)

        # Single value
        value = self._parse_literal_value()
        return ir.ConditionValue(literal=value)

    # =========================================================================
    # Workspace Parsing
    # =========================================================================

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
        self.expect(TokenType.WORKSPACE)

        name = self.expect_identifier_or_keyword().value
        title = None

        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        purpose = None
        engine_hint = None
        regions: list[ir.WorkspaceRegion] = []
        ux_spec = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # purpose: "..."
            if self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # engine_hint: "archetype_name" (v0.3.1)
            elif self.match(TokenType.ENGINE_HINT):
                self.advance()
                self.expect(TokenType.COLON)
                engine_hint = self.expect(TokenType.STRING).value
                self.skip_newlines()

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
            engine_hint=engine_hint,
            regions=regions,
            ux=ux_spec,
        )

    def parse_workspace_region(self) -> ir.WorkspaceRegion:
        """Parse workspace region."""
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        source = None
        filter_expr = None
        sort: list[ir.SortSpec] = []
        limit = None
        display = ir.DisplayMode.LIST
        action = None
        empty_message = None
        group_by = None
        aggregates: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # source: EntityName
            if self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                source = self.expect_identifier_or_keyword().value
                self.skip_newlines()

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

            # group_by: field_name
            elif self.match(TokenType.GROUP_BY):
                self.advance()
                self.expect(TokenType.COLON)
                group_by = self.expect_identifier_or_keyword().value
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

            else:
                break

        self.expect(TokenType.DEDENT)

        if source is None:
            token = self.current_token()
            raise make_parse_error(
                f"Workspace region '{name}' requires 'source:'",
                self.file,
                token.line,
                token.column,
            )

        return ir.WorkspaceRegion(
            name=name,
            source=source,
            filter=filter_expr,
            sort=sort,
            limit=limit,
            display=display,
            action=action,
            empty_message=empty_message,
            group_by=group_by,
            aggregates=aggregates,
        )

    def parse(self) -> ir.ModuleFragment:
        """
        Parse entire module and return IR fragment.

        Returns:
            ModuleFragment with all parsed declarations
        """
        fragment = ir.ModuleFragment()

        self.skip_newlines()

        while not self.match(TokenType.EOF):
            self.skip_newlines()

            # v0.7.1: Check for archetype declaration
            if self.match(TokenType.ARCHETYPE):
                archetype = self.parse_archetype()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes + [archetype],
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.ENTITY):
                entity = self.parse_entity()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities + [entity],
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.SURFACE):
                surface = self.parse_surface()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces + [surface],
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.EXPERIENCE):
                experience = self.parse_experience()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences + [experience],
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.SERVICE):
                service = self.parse_service()
                # Route to apis or domain_services based on type
                if isinstance(service, ir.DomainServiceSpec):
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis,
                        domain_services=fragment.domain_services + [service],
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                    )
                else:
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis + [service],
                        domain_services=fragment.domain_services,
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                    )

            elif self.match(TokenType.FOREIGN_MODEL):
                foreign_model = self.parse_foreign_model()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models + [foreign_model],
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.INTEGRATION):
                integration = self.parse_integration()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations + [integration],
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.TEST):
                test = self.parse_test()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests + [test],
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.WORKSPACE):
                workspace = self.parse_workspace()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces + [workspace],
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                )

            elif self.match(TokenType.FLOW):
                flow = self.parse_flow()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows + [flow],
                    fixtures=fragment.fixtures,
                )

            else:
                token = self.current_token()
                if token.type == TokenType.EOF:
                    break
                # Skip unknown tokens
                self.advance()

        return fragment


def parse_dsl(
    text: str, file: Path
) -> tuple[str | None, str | None, str | None, list[str], ir.ModuleFragment]:
    """
    Parse complete DSL file.

    Args:
        text: DSL source text
        file: Source file path

    Returns:
        Tuple of (module_name, app_name, app_title, uses, fragment)
    """
    # Tokenize
    tokens = tokenize(text, file)

    # Parse
    parser = Parser(tokens, file)
    module_name, app_name, app_title, uses = parser.parse_module_header()
    fragment = parser.parse()

    return module_name, app_name, app_title, uses, fragment
