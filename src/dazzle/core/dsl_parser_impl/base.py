"""
Base parser class for DAZZLE DSL.

Provides common token manipulation and utility methods used by all parser mixins.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..errors import make_parse_error
from ..lexer import Token, TokenType

if TYPE_CHECKING:
    from .. import ir


@runtime_checkable
class ParserProtocol(Protocol):
    """
    Protocol defining the interface available to parser mixins.

    This allows mypy to understand that mixins will have access to
    BaseParser methods when combined in the final Parser class.
    """

    tokens: list[Token]
    file: Path
    pos: int

    def current_token(self) -> Token: ...
    def peek_token(self, offset: int = 1) -> Token: ...
    def advance(self) -> Token: ...
    def expect(self, token_type: TokenType) -> Token: ...
    def expect_identifier_or_keyword(self) -> Token: ...
    def match(self, *token_types: TokenType) -> bool: ...
    def skip_newlines(self) -> None: ...

    # Methods from other mixins that may be called cross-mixin
    def parse_type(self) -> "ir.FieldType": ...
    def parse_condition_expr(self) -> "ir.ConditionExpr": ...
    def parse_sort_list(self) -> list[tuple[str, str]]: ...
    def parse_ux_block(self) -> "ir.UXSpec": ...

    # v0.10.2: Date/duration methods from TypeParserMixin
    def _parse_date_expr(self) -> "ir.DateLiteral | ir.DateArithmeticExpr": ...
    def _parse_duration_literal(self) -> "ir.DurationLiteral": ...


class BaseParser:
    """
    Base parser class with token manipulation utilities.

    This class provides the foundation for recursive descent parsing,
    including token navigation, matching, and error generation.
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
        if token.type in KEYWORD_AS_IDENTIFIER_TYPES:
            return self.advance()

        # v0.3.1: Provide helpful alternatives for common reserved keywords
        # v0.14.1: Expanded list based on user feedback
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
            # Added in v0.14.1
            "schedule": "timing, scheduled_at, appointment",
            "action": "action_type, operation, task_action",
            "view": "view_type, display_view, page_view",
            "access": "access_level, permissions, access_type",
            "role": "user_role, role_type, assigned_role",
            "input": "input_data, request_input, form_input",
            "output": "output_data, result, response_output",
            "query": "search_query, query_text, query_params",
            "message": "notification, msg, content_message",
            "sync": "synchronize, sync_status, is_synced",
            "test": "test_case, test_name, is_test",
            "flow": "workflow, process_flow, flow_type",
            "step": "step_number, workflow_step, process_step",
            "start": "start_at, begins_at, start_time",
            "scope": "scope_type, access_scope, data_scope",
            "limit": "max_limit, row_limit, limit_value",
            "count": "total_count, item_count, record_count",
            "display": "display_name, shown_as, label",
            "list": "items, listing, item_list",
            "sum": "total, sum_total, amount_sum",
        }

        keyword = token.type.value

        # v0.14.1: Distinguish between operators and reserved keywords
        # Only include tokens that actually exist in the lexer
        operator_tokens = {
            TokenType.SLASH,
            TokenType.STAR,
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.EQUALS,
            TokenType.NOT_EQUALS,
            TokenType.DOUBLE_EQUALS,
            TokenType.LESS_THAN,
            TokenType.GREATER_THAN,
            TokenType.LESS_EQUAL,
            TokenType.GREATER_EQUAL,
            TokenType.LPAREN,
            TokenType.RPAREN,
            TokenType.LBRACKET,
            TokenType.RBRACKET,
            TokenType.COLON,
            TokenType.COMMA,
            TokenType.DOT,
            TokenType.ARROW,
        }

        if token.type in operator_tokens:
            # It's an operator, not a keyword - likely a syntax error
            error_msg = (
                f"Unexpected '{token.value}' - expected identifier.\n"
                f'  If this is part of a string value, use quotes: "your value here"\n'
                f'  Example: mime_type: str(100)="application/pdf"'
            )
        elif keyword in keyword_alternatives:
            alternatives = keyword_alternatives[keyword]
            error_msg = (
                f"'{keyword}' is a reserved keyword and cannot be used as an identifier.\n"
                f"  Suggested alternatives: {alternatives}\n"
                f"  See docs/DSL_RESERVED_KEYWORDS.md for full list"
            )
        else:
            # Generic message for any reserved keyword
            error_msg = (
                f"'{keyword}' is a reserved keyword and cannot be used as an identifier.\n"
                f"  Try a different name like '{keyword}_value' or '{keyword}_field'.\n"
                f"  See docs/DSL_RESERVED_KEYWORDS.md for the full list of reserved keywords."
            )

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

    def parse_module_header(
        self,
    ) -> tuple[str | None, str | None, str | None, "ir.AppConfigSpec | None", list[str]]:
        """
        Parse module header (module, app, use declarations).

        Returns:
            Tuple of (module_name, app_name, app_title, app_config, uses)
        """
        from .. import ir

        module_name = None
        app_name = None
        app_title = None
        app_config = None
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

        # Parse app declaration (v0.9.5: with optional body)
        if self.match(TokenType.APP):
            self.advance()
            app_name = self.expect_identifier_or_keyword().value

            if self.match(TokenType.STRING):
                app_title = self.advance().value

            # v0.9.5: Optional app config body
            if self.match(TokenType.COLON):
                self.advance()
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                description = None
                multi_tenant = False
                audit_trail = False
                security_profile = "basic"  # v0.11.0
                features: dict[str, str | bool] = {}

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # description: "..."
                    if self.match(TokenType.DESCRIPTION):
                        self.advance()
                        self.expect(TokenType.COLON)
                        description = self.expect(TokenType.STRING).value
                        self.skip_newlines()

                    # multi_tenant: true|false
                    elif self.match(TokenType.MULTI_TENANT):
                        self.advance()
                        self.expect(TokenType.COLON)
                        token = self.advance()
                        multi_tenant = token.type == TokenType.TRUE
                        self.skip_newlines()

                    # audit_trail: true|false
                    elif self.match(TokenType.AUDIT_TRAIL):
                        self.advance()
                        self.expect(TokenType.COLON)
                        token = self.advance()
                        audit_trail = token.type == TokenType.TRUE
                        self.skip_newlines()

                    # security_profile: basic|standard|strict (v0.11.0)
                    elif self.match(TokenType.SECURITY_PROFILE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        # Accept identifier (basic, standard, strict) or string
                        token = self.advance()
                        if token.type == TokenType.STRING:
                            security_profile = token.value
                        else:
                            security_profile = token.value
                        self.skip_newlines()

                    # Any other identifier: value (for extensibility)
                    elif self.match(TokenType.IDENTIFIER):
                        key = self.advance().value
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.STRING):
                            features[key] = self.advance().value
                        elif self.match(TokenType.TRUE):
                            self.advance()
                            features[key] = True
                        elif self.match(TokenType.FALSE):
                            self.advance()
                            features[key] = False
                        else:
                            features[key] = self.advance().value
                        self.skip_newlines()

                    else:
                        break

                self.expect(TokenType.DEDENT)

                app_config = ir.AppConfigSpec(
                    description=description,
                    multi_tenant=multi_tenant,
                    audit_trail=audit_trail,
                    security_profile=security_profile,
                    features=features,
                )
            else:
                self.skip_newlines()

        return module_name, app_name, app_title, app_config, uses

    def parse_module_name(self) -> str:
        """Parse dotted module name (e.g., foo.bar.baz)."""
        parts = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)

        return ".".join(parts)

    def _is_keyword_as_identifier(self) -> bool:
        """Check if current token is a keyword that can be used as identifier."""
        return self.current_token().type in KEYWORD_AS_IDENTIFIER_TYPES


# Keywords that can be used as identifiers in certain contexts
KEYWORD_AS_IDENTIFIER_TYPES = (
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
    TokenType.DETAIL,
    TokenType.ASC,
    TokenType.DESC,
    TokenType.IN,
    TokenType.NOT,
    TokenType.IS,
    TokenType.AND,
    TokenType.OR,
    # Flow/E2E Test keywords (v0.3.2)
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
    # Access control keywords (v0.5.0)
    TokenType.ACCESS,
    TokenType.READ,
    TokenType.WRITE,
    # State Machine keywords (v0.7.0)
    TokenType.TRANSITIONS,
    TokenType.REQUIRES,
    TokenType.AUTO,
    TokenType.AFTER,
    TokenType.ROLE,
    TokenType.MANUAL,
    TokenType.DAYS,
    TokenType.HOURS,
    TokenType.MINUTES,
    TokenType.OWNER,
    # v0.7.1 LLM Cognition keywords
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
    # v0.9.5 App Config keywords (can be field names)
    TokenType.DESCRIPTION,
    TokenType.MULTI_TENANT,
    TokenType.AUDIT_TRAIL,
    # v0.9.5 Field Type keywords (can be field names)
    TokenType.MONEY,
    TokenType.FILE_TYPE,
    # v0.9.0 Messaging keywords (can be field names)
    TokenType.CHANNEL,
    TokenType.SEND,
    TokenType.RECEIVE,
    TokenType.PROVIDER,
    TokenType.CONFIG,
    TokenType.PROVIDER_CONFIG,
    TokenType.DELIVERY_MODE,
    TokenType.OUTBOX,
    TokenType.DIRECT,
    TokenType.THROTTLE,
    TokenType.PER_RECIPIENT,
    TokenType.PER_ENTITY,
    TokenType.PER_CHANNEL,
    TokenType.WINDOW,
    TokenType.MAX_MESSAGES,
    TokenType.ON_EXCEED,
    TokenType.DROP,
    TokenType.LOG,
    TokenType.QUEUE,
    TokenType.STREAM,
    TokenType.EMAIL,
    TokenType.ASSET,
    TokenType.DOCUMENT,
    TokenType.TEMPLATE,
    TokenType.SUBJECT,
    TokenType.BODY,
    TokenType.HTML_BODY,
    TokenType.ATTACHMENTS,
    TokenType.ASSET_REF,
    TokenType.DOCUMENT_REF,
    TokenType.ENTITY_ARG,
    TokenType.FILENAME,
    TokenType.FOR_ENTITY,
    TokenType.FORMAT,
    TokenType.LAYOUT,
    TokenType.PATH,
    TokenType.CHANGED,
    TokenType.TO,
    TokenType.SUCCEEDED,
    TokenType.FAILED,
    TokenType.EVERY,
    TokenType.CRON,
    TokenType.UPSERT,
    TokenType.REGEX,
    # Field types that are also keywords
    TokenType.URL,
    # Workspace keywords that can be field names
    TokenType.STAGE,
    # Commonly needed as enum values (v0.9.1)
    TokenType.SUBMITTED,
    TokenType.OPERATION,
    TokenType.KEY,
    TokenType.START,
    TokenType.ON,
    TokenType.AT,
    TokenType.SPEC,
    TokenType.INLINE,
    TokenType.MAPPING,
    TokenType.RULES,
    TokenType.SCHEDULED,
    TokenType.EVENT_DRIVEN,
    TokenType.FOREIGN,
    TokenType.INPUT,
    TokenType.OUTPUT,
    TokenType.GUARANTEES,
    TokenType.STUB,
    TokenType.INVARIANT,
    TokenType.COMPUTED,
    TokenType.SUM,
    TokenType.AVG,
    TokenType.MIN,
    TokenType.MAX,
    TokenType.DAYS_UNTIL,
    TokenType.DAYS_SINCE,
)
