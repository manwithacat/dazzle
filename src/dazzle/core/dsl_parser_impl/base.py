"""
Base parser class for DAZZLE DSL.

Provides common token manipulation and utility methods used by all parser mixins.
"""

from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, Protocol, runtime_checkable

from ..errors import make_parse_error
from ..ir.location import SourceLocation
from ..lexer import Token, TokenType

if TYPE_CHECKING:
    from .. import ir
    from ..ir.expressions import Expr


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
    def _source_location(self, token: Token | None = None) -> SourceLocation: ...
    def expect_identifier_or_keyword(self) -> Token: ...
    def match(self, *token_types: TokenType) -> bool: ...
    def error(self, message: str) -> NoReturn: ...
    def skip_newlines(self) -> None: ...
    def _parse_construct_header(
        self,
        token_type: TokenType,
        *,
        allow_keyword_name: bool = False,
    ) -> tuple[str, str | None, SourceLocation]: ...

    # Methods from other mixins that may be called cross-mixin
    def parse_type(self) -> "ir.FieldType": ...
    def _parse_field_spec(self) -> "ir.FieldSpec": ...
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

    def _source_location(self, token: Token | None = None) -> SourceLocation:
        """Create a SourceLocation from a token (defaults to current token)."""
        t = token or self.current_token()
        return SourceLocation(file=str(self.file), line=t.line, column=t.column)

    def _parse_construct_header(
        self,
        token_type: TokenType,
        *,
        allow_keyword_name: bool = False,
    ) -> tuple[str, str | None, SourceLocation]:
        """Parse standard construct header: KEYWORD name "title"? COLON INDENT."""
        loc = self._source_location()
        self.expect(token_type)
        if allow_keyword_name:
            name = self.expect_identifier_or_keyword().value
        else:
            name = self.expect(TokenType.IDENTIFIER).value
        title: str | None = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        return name, title, loc

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

    def error(self, message: str) -> NoReturn:
        """Raise a ParseError at the current token position."""
        token = self.current_token()
        raise make_parse_error(message, self.file, token.line, token.column)

    def collect_line_as_expr(self) -> "Expr | None":
        """Collect remaining tokens on current line and parse as typed expression.

        Consumes tokens until NEWLINE/INDENT/DEDENT/EOF, reconstructs text,
        and delegates to the expression parser. Returns None on parse failure.
        """
        from ..expression_lang.parser import ExpressionParseError, parse_expr

        _STOP_TOKENS = {TokenType.NEWLINE, TokenType.INDENT, TokenType.DEDENT, TokenType.EOF}
        # Map DSL token types to text representation
        _OP_TEXT = {
            TokenType.DOUBLE_EQUALS: "==",
            TokenType.NOT_EQUALS: "!=",
            TokenType.GREATER_THAN: ">",
            TokenType.LESS_THAN: "<",
            TokenType.GREATER_EQUAL: ">=",
            TokenType.LESS_EQUAL: "<=",
            TokenType.ARROW: "->",
        }
        # Map DSL word-form durations to compact notation for expression parser
        _DURATION_WORDS = {
            "days": "d",
            "hours": "h",
            "minutes": "min",
            "weeks": "w",
            "months": "m",
            "years": "y",
        }

        parts: list[str] = []
        while self.current_token().type not in _STOP_TOKENS:
            tok = self.current_token()
            if tok.type == TokenType.STRING:
                parts.append(f'"{tok.value}"')
            elif tok.type in _OP_TEXT:
                parts.append(_OP_TEXT[tok.type])
            elif tok.value in _DURATION_WORDS and parts and parts[-1].isdigit():
                # Merge "14 days" → "14d"
                parts[-1] = parts[-1] + _DURATION_WORDS[tok.value]
            else:
                parts.append(tok.value)
            self.advance()

        text = " ".join(parts).strip()
        if not text:
            return None

        try:
            return parse_expr(text)
        except ExpressionParseError:
            return None

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
                theme: str | None = None  # v0.61.43 (Phase B Patch 2)
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

                    # theme: <name>  (v0.61.43, #design-system Phase B Patch 2)
                    # Resolves via the registry at link time. DSL value
                    # wins over [ui] theme in dazzle.toml. Theme names
                    # commonly contain hyphens (linear-dark, my-brand)
                    # which the lexer splits into IDENT-MINUS-IDENT —
                    # rejoin them here so unquoted hyphenated names work.
                    elif self.match(TokenType.THEME):
                        self.advance()
                        self.expect(TokenType.COLON)
                        token = self.advance()
                        if token.type == TokenType.STRING:
                            theme = token.value
                        else:
                            parts = [token.value]
                            while self.match(TokenType.MINUS):
                                self.advance()
                                parts.append("-")
                                next_tok = self.advance()
                                parts.append(next_tok.value)
                            theme = "".join(parts)
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
                    theme=theme,
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
    # v0.61.25 (#884) added DELTA as a region-block keyword. It must
    # remain usable as an enum value / field name elsewhere — adding it
    # here lets `enum[alpha, beta, delta]` and `delta_field: …` parse.
    TokenType.DELTA,
    # v0.61.43 (Phase B Patch 2) added THEME as an app-block keyword.
    # Same reasoning — `theme` is a common field/enum name (e.g.
    # `enum[light, dark, theme_a]`) so it must remain usable as an
    # identifier outside the app block.
    TokenType.THEME,
    # v0.61.55 (#892) added profile_card region-block keywords. Per
    # #899 regression — these tokens must remain usable as identifiers
    # in enum literals (e.g. `enum[primary, secondary, all_through]`
    # for school phase) and field names. Same fix pattern as DELTA
    # above. See dsl/lexer.py for the full token list.
    TokenType.AVATAR_FIELD,
    TokenType.PRIMARY,
    TokenType.SECONDARY,
    TokenType.STATS,
    TokenType.FACTS,
    # v0.61.56 (#890) added pipeline_steps `caption:` keyword. Same
    # rationale — `caption` is a common field name.
    TokenType.CAPTION,
    # v0.61.60 added region-level `eyebrow:` keyword (AegisMark UX patterns
    # roadmap item #1). Common field name; must remain usable as identifier.
    TokenType.EYEBROW,
    # v0.61.65 added region-level `tones:` block (AegisMark UX patterns
    # roadmap item #2). `tones` is an unlikely field name but reserve the
    # escape hatch for parity with other keyword-shaped identifiers.
    TokenType.TONES,
    # v0.61.69 added status_list `entries:` / `state:` keywords (AegisMark
    # UX patterns roadmap item #3). Both are common field names —
    # `state` especially could clash with state machines, `entries`
    # with collection counters. (`caption` already in this list from
    # the pipeline_steps work.)
    TokenType.ENTRIES,
    TokenType.STATE,
    # v0.61.72 added confirm_action_panel keywords (AegisMark UX patterns
    # roadmap item #6). `state_field` could be a column name, `revoke`
    # could be an action name. (`required` deliberately NOT promoted —
    # it's a field modifier and must remain IDENTIFIER for the field
    # parser; the confirm_action_panel parser string-matches `required`
    # via its IDENTIFIER value instead.)
    TokenType.CONFIRMATIONS,
    TokenType.STATE_FIELD,
    TokenType.REVOKE,
    # v0.61.54 (#891) added action_grid keywords. ACTIONS is an
    # existing identifier-shaped name people commonly use for fields
    # and entity attributes. TONE is also a likely color/voice field
    # name. COUNT_AGGREGATE is fully snake-cased and unlikely to clash,
    # but for consistency keep them all here.
    TokenType.ACTIONS,
    TokenType.TONE,
    TokenType.COUNT_AGGREGATE,
    # v0.61.53 (#893) added bar_track keywords. `track_max` and
    # `track_format` are snake-cased and unlikely to clash, but enum
    # literals or field names like `track_max` could legitimately
    # appear in other domains.
    TokenType.TRACK_MAX,
    TokenType.TRACK_FORMAT,
    # v0.61.52 (#894) added the `class:` region keyword. CSS_CLASS is
    # the token name; the user-facing keyword is `class` which is a
    # Python keyword anyway, but enum values like `enum[primary,
    # class_a, class_b]` could shadow it.
    TokenType.CSS_CLASS,
    TokenType.LIST,
    TokenType.GRID,
    TokenType.TIMELINE,
    TokenType.DETAIL,
    TokenType.MAP,
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
    # ADR-0020 Lifecycle keyword (allowed as identifier in patterns tags etc.)
    TokenType.LIFECYCLE,
    # Agent-Led Fitness v1 — fitness keyword allowed as identifier (e.g. field name)
    TokenType.FITNESS,
    TokenType.DAYS,
    TokenType.HOURS,
    TokenType.MINUTES,
    TokenType.OWNER,
    # v0.29.0 Expression Guard keywords
    TokenType.GUARD,
    # v0.30.0 Surface when clause
    TokenType.WHEN,
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
    # Search-block keywords (#954) — also valid as CSS class identifiers
    # / field names elsewhere in the DSL.
    TokenType.HIGHLIGHT,
    TokenType.RANKING,
    TokenType.TOKENIZER,
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
    # v0.21.0 LLM Jobs keywords (can be values in config)
    TokenType.WARN,
    TokenType.LLM_MODEL,
    TokenType.LLM_CONFIG,
    TokenType.LLM_INTENT,
    TokenType.TIER,
    TokenType.MAX_TOKENS,
    TokenType.MODEL_ID,
    TokenType.ARTIFACT_STORE,
    TokenType.LOGGING,
    TokenType.LOG_PROMPTS,
    TokenType.LOG_COMPLETIONS,
    TokenType.REDACT_PII,
    TokenType.RATE_LIMITS,
    TokenType.DEFAULT_MODEL,
    TokenType.PROMPT,
    TokenType.OUTPUT_SCHEMA,
    TokenType.TIMEOUT,
    TokenType.RETRY,
    TokenType.PII,
    TokenType.MAX_ATTEMPTS,
    TokenType.BACKOFF,
    TokenType.INITIAL_DELAY_MS,
    TokenType.MAX_DELAY_MS,
    TokenType.SCAN,
    TokenType.STRICT,
    TokenType.OFF,
    # v0.22.0 Workspace access levels
    TokenType.PUBLIC,
    TokenType.AUTHENTICATED,
    # v0.23.0 Process Workflow keywords (can be field names)
    TokenType.PROCESS,
    TokenType.SCHEDULE,
    TokenType.TIMEZONE,
    TokenType.INTERVAL,
    TokenType.IMPLEMENTS,
    TokenType.PARALLEL,
    TokenType.SUBPROCESS,
    TokenType.HUMAN_TASK,
    TokenType.ASSIGNEE,
    TokenType.CATCH_UP,
    TokenType.COMPENSATE,
    TokenType.COMPENSATIONS,
    TokenType.ON_SUCCESS,
    TokenType.ON_FAILURE,
    TokenType.ON_TRUE,
    TokenType.ON_FALSE,
    TokenType.CONDITION,
    # v0.24.0 TigerBeetle Ledger keywords (can be field names)
    TokenType.LEDGER,
    TokenType.TRANSACTION,
    TokenType.TRANSFER,
    TokenType.DEBIT,
    TokenType.CREDIT,
    TokenType.AMOUNT,
    TokenType.ACCOUNT_CODE,
    TokenType.LEDGER_ID,
    TokenType.ACCOUNT_TYPE,
    TokenType.CURRENCY,
    TokenType.FLAGS,
    TokenType.SYNC_TO,
    TokenType.IDEMPOTENCY_KEY,
    TokenType.VALIDATION,
    TokenType.EXECUTION,
    TokenType.PRIORITY,
    TokenType.PENDING_ID,
    TokenType.USER_DATA,
    TokenType.TENANT_SCOPED,
    TokenType.METADATA_MAPPING,
    # v0.25.0 Top-Level Construct Keywords
    TokenType.ENUM,
    TokenType.WEBHOOK,
    TokenType.APPROVAL,
    TokenType.SLA,
    # Experience Orchestration Keywords
    TokenType.CONTEXT,
    TokenType.PREFILL,
    TokenType.SAVES_TO,
    TokenType.CREATES,
    TokenType.DEFAULTS,
    TokenType.FIELDS,
    # v0.37.0 LLM Trigger/Queue keywords (can be field names in input_map)
    TokenType.TRIGGER,
    # v0.34.0 Platform Capability Keywords
    TokenType.SOFT_DELETE,
    TokenType.DISPLAY_FIELD,
    TokenType.SEARCHABLE,
    TokenType.BULK,
    TokenType.IMPORT,
    TokenType.EXPORT,
    TokenType.NOTIFICATION,
    TokenType.NOTIFY,
    TokenType.CHANNELS,
    TokenType.IN_APP,
    TokenType.SMS,
    TokenType.SLACK,
    TokenType.PREFERENCES,
    TokenType.DATE_RANGE,
    TokenType.TIME_BUCKET,
    TokenType.DATE_FIELD,
    # v0.44.0 External action links
    TokenType.EXTERNAL,
    # v0.44.0 Runtime Parameters
    TokenType.PARAM,
    # v0.44.0 Heatmap / Progress / Activity Feed keywords (can be field names)
    TokenType.ACTIVITY_FEED,
    TokenType.TREE,
    TokenType.ROWS,
    TokenType.COLUMNS,
    TokenType.VALUE,
    TokenType.THRESHOLDS,
    TokenType.STAGES,
    TokenType.COMPLETE_AT,
    # v0.46.0 Graph Semantics keywords (can be field names)
    TokenType.GRAPH_EDGE,
    TokenType.GRAPH_NODE,
    TokenType.TARGET,
    TokenType.WEIGHT,
    TokenType.DIRECTED,
    TokenType.ACYCLIC,
    TokenType.EDGES,
    # v0.61.91 (#922) — reserved keywords from #918 (`help:`, `note:`) and
    # the older `question:` declaration must remain usable as identifiers
    # so they don't shadow hyphenated Lucide icon names like
    # `help-circle`, `file-question`, `sticky-note`. The hyphenated-icon
    # parser falls back to `expect_identifier_or_keyword`; the keyword
    # only resolves there if it appears in this list.
    TokenType.HELP,
    TokenType.QUESTION_DECL,
    TokenType.NOTE,
    # v0.61.95 (#926) — `nav` and `group` are shared-nav-definition
    # keywords. Both are common entity / field names (a domain might
    # define `entity Group`, `field nav_position`, an enum like
    # `enum[group_a, group_b]`, etc.) so promote them to identifier
    # status outside the `nav <name>:` declaration block.
    TokenType.NAV,
    TokenType.GROUP,
    # v0.61.102 (#923) — companion-region keywords. `companion` is
    # snake-case-only inside surface blocks; `position` and
    # `below_section` are common field/identifier shapes (e.g. a DSL
    # might have `field position int`) so they need to remain usable.
    TokenType.COMPANION,
    TokenType.POSITION,
    TokenType.BELOW_SECTION,
)
