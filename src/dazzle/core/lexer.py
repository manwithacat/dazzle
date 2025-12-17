"""
Lexer/Tokenizer for DAZZLE DSL.

Converts raw DSL text into a stream of tokens with source location tracking.
Handles indentation-based blocks (Python-style) with INDENT/DEDENT tokens.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .errors import make_parse_error


class TokenType(Enum):
    """Token types in the DAZZLE DSL."""

    # Literals
    IDENTIFIER = "IDENTIFIER"
    STRING = "STRING"
    NUMBER = "NUMBER"

    # Keywords
    MODULE = "module"
    USE = "use"
    AS = "as"
    APP = "app"
    ENTITY = "entity"
    SURFACE = "surface"
    EXPERIENCE = "experience"
    SERVICE = "service"
    FOREIGN_MODEL = "foreign_model"
    INTEGRATION = "integration"
    FROM = "from"
    USES = "uses"
    MODE = "mode"
    SECTION = "section"
    FIELD = "field"
    ACTION = "action"
    STEP = "step"
    KIND = "kind"
    START = "start"
    AT = "at"
    ON = "on"
    WHEN = "when"
    CALL = "call"
    WITH = "with"
    MAP = "map"
    RESPONSE = "response"
    INTO = "into"
    MATCH = "match"
    SYNC = "sync"
    SCHEDULE = "schedule"
    SPEC = "spec"
    AUTH_PROFILE = "auth_profile"
    OWNER = "owner"
    KEY = "key"
    CONSTRAINT = "constraint"
    UNIQUE = "unique"
    INDEX = "index"
    URL = "url"
    INLINE = "inline"
    SUBMITTED = "submitted"

    # Integration Keywords
    OPERATION = "operation"
    MAPPING = "mapping"
    RULES = "rules"
    SCHEDULED = "scheduled"
    EVENT_DRIVEN = "event_driven"
    FOREIGN = "foreign"

    # Test DSL Keywords
    TEST = "test"
    SETUP = "setup"
    DATA = "data"
    EXPECT = "expect"
    STATUS = "status"
    CREATED = "created"
    FILTER = "filter"
    SEARCH = "search"
    ORDER_BY = "order_by"
    COUNT = "count"
    ERROR_MESSAGE = "error_message"
    FIRST = "first"
    LAST = "last"
    QUERY = "query"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    GET = "get"
    TRUE = "true"
    FALSE = "false"

    # Access Control Keywords
    ANONYMOUS = "anonymous"
    PERMISSIONS = "permissions"
    ACCESS = "access"
    READ = "read"
    WRITE = "write"

    # UX Semantic Layer Keywords
    UX = "ux"
    PURPOSE = "purpose"
    SHOW = "show"
    SORT = "sort"
    EMPTY = "empty"
    ATTENTION = "attention"
    CRITICAL = "critical"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    MESSAGE = "message"
    FOR = "for"
    SCOPE = "scope"
    HIDE = "hide"
    SHOW_AGGREGATE = "show_aggregate"
    ACTION_PRIMARY = "action_primary"
    READ_ONLY = "read_only"
    ALL = "all"
    WORKSPACE = "workspace"
    SOURCE = "source"
    LIMIT = "limit"
    DISPLAY = "display"
    AGGREGATE = "aggregate"
    LIST = "list"
    GRID = "grid"
    TIMELINE = "timeline"
    DETAIL = "detail"  # v0.3.1

    # Additional v0.2 keywords
    DEFAULTS = "defaults"
    FOCUS = "focus"
    GROUP_BY = "group_by"
    WHERE = "where"

    # v0.3.1 keywords
    ENGINE_HINT = "engine_hint"  # Deprecated: use STAGE instead
    STAGE = "stage"  # v0.8.0: Workspace layout stage (replaces engine_hint)

    # v0.5.0 Domain Service Keywords
    INPUT = "input"
    OUTPUT = "output"
    GUARANTEES = "guarantees"
    STUB = "stub"

    # v0.7.0 State Machine Keywords
    TRANSITIONS = "transitions"
    REQUIRES = "requires"
    AUTO = "auto"
    AFTER = "after"
    ROLE = "role"
    MANUAL = "manual"
    DAYS = "days"
    HOURS = "hours"
    MINUTES = "minutes"
    # v0.10.2 Date Arithmetic Keywords
    TODAY = "today"
    NOW = "now"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"
    DURATION_LITERAL = "DURATION_LITERAL"  # e.g., 7d, 24h, 30min

    # Computed Field Keywords
    COMPUTED = "computed"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DAYS_UNTIL = "days_until"
    DAYS_SINCE = "days_since"

    # Invariant Keywords
    INVARIANT = "invariant"
    CODE = "code"

    # v0.9.5 App Config Keywords
    DESCRIPTION = "description"
    MULTI_TENANT = "multi_tenant"
    AUDIT_TRAIL = "audit_trail"
    SECURITY_PROFILE = "security_profile"  # v0.11.0

    # v0.9.5 Field Type Keywords
    MONEY = "money"
    FILE_TYPE = "file"  # FILE conflicts with built-in, use FILE_TYPE
    VIA = "via"  # For many-to-many relationships through junction tables

    # v0.7.1 LLM Cognition Keywords
    INTENT = "intent"
    EXAMPLES = "examples"
    DOMAIN = "domain"
    PATTERNS = "patterns"
    EXTENDS = "extends"
    ARCHETYPE = "archetype"
    HAS_MANY = "has_many"
    HAS_ONE = "has_one"
    EMBEDS = "embeds"
    BELONGS_TO = "belongs_to"
    CASCADE = "cascade"
    RESTRICT = "restrict"
    NULLIFY = "nullify"
    READONLY = "readonly"
    DENY = "deny"
    SCENARIOS = "scenarios"
    GIVEN = "given"
    THEN = "then"

    # v0.8.5 Dazzle Bar Keywords
    SCENARIO = "scenario"
    DEMO = "demo"
    PERSONA = "persona"
    GOALS = "goals"
    PROFICIENCY = "proficiency"
    SEED_SCRIPT = "seed_script"
    START_ROUTE = "start_route"

    # v0.18.0 Event-First Architecture Keywords
    EVENT_MODEL = "event_model"
    PUBLISH = "publish"
    SUBSCRIBE = "subscribe"
    PROJECT = "project"
    TOPIC = "topic"
    RETENTION = "retention"
    # v0.18.0 Governance Keywords (Issue #25)
    POLICIES = "policies"
    TENANCY = "tenancy"
    INTERFACES = "interfaces"
    DATA_PRODUCTS = "data_products"
    CLASSIFY = "classify"
    ERASURE = "erasure"
    DATA_PRODUCT = "data_product"

    # v0.19.0 HLESS (High-Level Event Semantics) Keywords
    # RecordKind types (INTENT already exists in v0.7.1 LLM Cognition)
    FACT = "FACT"
    OBSERVATION = "OBSERVATION"
    DERIVATION = "DERIVATION"
    # Stream specification keywords
    PARTITION_KEY = "partition_key"
    ORDERING_SCOPE = "ordering_scope"
    IDEMPOTENCY = "idempotency"
    OUTCOMES = "outcomes"
    DERIVES_FROM = "derives_from"
    EMITS = "emits"
    SIDE_EFFECTS = "side_effects"
    ALLOWED = "allowed"
    SCHEMA = "schema"
    NOTE = "note"
    # Time semantics
    T_EVENT = "t_event"
    T_LOG = "t_log"
    T_PROCESS = "t_process"
    # HLESS pragma
    HLESS = "hless"
    STRICT = "strict"
    WARN = "warn"
    OFF = "off"

    # v0.21.0 LLM Jobs as First-Class Events (Issue #33)
    LLM_MODEL = "llm_model"
    LLM_CONFIG = "llm_config"
    LLM_INTENT = "llm_intent"
    TIER = "tier"
    MAX_TOKENS = "max_tokens"
    COST_PER_1K_INPUT = "cost_per_1k_input"
    COST_PER_1K_OUTPUT = "cost_per_1k_output"
    MODEL_ID = "model_id"
    ARTIFACT_STORE = "artifact_store"
    LOGGING = "logging"
    LOG_PROMPTS = "log_prompts"
    LOG_COMPLETIONS = "log_completions"
    REDACT_PII = "redact_pii"
    RATE_LIMITS = "rate_limits"
    DEFAULT_MODEL = "default_model"
    PROMPT = "prompt"
    OUTPUT_SCHEMA = "output_schema"
    TIMEOUT = "timeout"
    RETRY = "retry"
    PII = "pii"
    MAX_ATTEMPTS = "max_attempts"
    BACKOFF = "backoff"
    INITIAL_DELAY_MS = "initial_delay_ms"
    MAX_DELAY_MS = "max_delay_ms"
    SCAN = "scan"
    # Note: 'model' is NOT a keyword - it's a common field name.
    # Within llm_intent blocks, 'model:' is parsed as an identifier.
    # Note: PIIAction values (warn, redact, reject) and RetryBackoff values
    # (linear, exponential) are parsed as identifiers, not keywords

    # v0.9.0 Messaging Channel Keywords
    # Note: MESSAGE already defined above in UX keywords
    CHANNEL = "channel"
    SEND = "send"
    RECEIVE = "receive"
    PROVIDER = "provider"
    CONFIG = "config"
    PROVIDER_CONFIG = "provider_config"
    DELIVERY_MODE = "delivery_mode"
    OUTBOX = "outbox"
    DIRECT = "direct"
    THROTTLE = "throttle"
    PER_RECIPIENT = "per_recipient"
    PER_ENTITY = "per_entity"
    PER_CHANNEL = "per_channel"
    WINDOW = "window"
    MAX_MESSAGES = "max_messages"
    ON_EXCEED = "on_exceed"
    DROP = "drop"
    LOG = "log"
    QUEUE = "queue"
    STREAM = "stream"
    EMAIL = "email"
    ASSET = "asset"
    DOCUMENT = "document"
    TEMPLATE = "template"
    SUBJECT = "subject"
    BODY = "body"
    HTML_BODY = "html_body"
    ATTACHMENTS = "attachments"
    ASSET_REF = "asset_ref"
    DOCUMENT_REF = "document_ref"
    ENTITY_ARG = "entity_arg"
    FILENAME = "filename"
    FOR_ENTITY = "for_entity"
    FORMAT = "format"
    LAYOUT = "layout"
    PATH = "path"
    CHANGED = "changed"
    TO = "to"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EVERY = "every"
    CRON = "cron"
    UPSERT = "upsert"
    REGEX = "regex"

    # Flow/E2E Test Keywords (v0.3.2)
    # Note: Only include keywords that don't conflict with common DSL usage
    # Words like 'high', 'medium', 'low', 'priority', 'status' are NOT keywords
    # because they're commonly used as enum values or field names.
    FLOW = "flow"
    STEPS = "steps"
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    WAIT = "wait"
    SNAPSHOT = "snapshot"
    PRECONDITIONS = "preconditions"
    AUTHENTICATED = "authenticated"
    USER_ROLE = "user_role"
    FIXTURES = "fixtures"
    VIEW = "view"
    ENTITY_EXISTS = "entity_exists"
    ENTITY_NOT_EXISTS = "entity_not_exists"
    VALIDATION_ERROR = "validation_error"
    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"
    TEXT_CONTAINS = "text_contains"
    REDIRECTS_TO = "redirects_to"
    FIELD_VALUE = "field_value"
    # PRIORITY, HIGH, MEDIUM, LOW are handled as identifiers
    TAGS = "tags"

    # Comparison operators (for condition expressions)
    DOUBLE_EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    NOT = "not"
    IS = "is"
    AND = "and"
    OR = "or"

    # Additional tokens for expressions
    ASC = "asc"
    DESC = "desc"

    # Operators
    COLON = ":"
    ARROW = "->"
    LARROW = "<-"
    BIARROW = "<->"
    COMMA = ","
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    EQUALS = "="
    DOT = "."
    SLASH = "/"
    QUESTION = "?"

    # Arithmetic operators (for aggregate expressions)
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    PERCENT = "%"

    # Special
    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"


# Keywords mapping
KEYWORDS = {
    "module",
    "use",
    "as",
    "app",
    "entity",
    "surface",
    "experience",
    "service",
    "foreign_model",
    "integration",
    "from",
    "uses",
    "mode",
    "section",
    "field",
    "action",
    "step",
    "kind",
    "start",
    "at",
    "on",
    "when",
    "call",
    "with",
    "map",
    "response",
    "into",
    "match",
    "sync",
    "schedule",
    "spec",
    "auth_profile",
    "owner",
    "key",
    "constraint",
    "unique",
    "index",
    "url",
    "inline",
    "submitted",
    # Integration keywords
    "operation",
    "mapping",
    "rules",
    "scheduled",
    "event_driven",
    "foreign",
    # Test DSL keywords
    "test",
    "setup",
    "data",
    "expect",
    "status",
    "created",
    "filter",
    "search",
    "order_by",
    "count",
    "error_message",
    "first",
    "last",
    "query",
    "create",
    "update",
    "delete",
    "get",
    "true",
    "false",
    # UX Semantic Layer keywords
    "ux",
    "purpose",
    "show",
    "sort",
    "empty",
    "attention",
    "critical",
    "warning",
    "notice",
    "info",
    "message",
    "for",
    "scope",
    "hide",
    "show_aggregate",
    "action_primary",
    "read_only",
    "all",
    "workspace",
    "source",
    "limit",
    "display",
    "aggregate",
    "list",
    "grid",
    "timeline",
    "detail",
    # Additional v0.2 keywords
    "defaults",
    "focus",
    "group_by",
    "where",
    # v0.3.1 keywords
    "engine_hint",  # Deprecated: use stage instead
    "stage",
    # Flow/E2E Test keywords (v0.3.2)
    # Note: 'priority', 'high', 'medium', 'low' are NOT keywords
    # because they're commonly used as enum values or field names
    "flow",
    "steps",
    "navigate",
    "click",
    "fill",
    "wait",
    "snapshot",
    "preconditions",
    "authenticated",
    "anonymous",
    "permissions",
    "access",
    "read",
    "write",
    "user_role",
    "fixtures",
    "view",
    "entity_exists",
    "entity_not_exists",
    "validation_error",
    "visible",
    "not_visible",
    "text_contains",
    "redirects_to",
    "field_value",
    "tags",
    # Comparison/logical keywords
    "in",
    "not",
    "is",
    "and",
    "or",
    "asc",
    "desc",
    # v0.5.0 Domain Service keywords
    "input",
    "output",
    "guarantees",
    "stub",
    # v0.7.0 State Machine keywords
    "transitions",
    "requires",
    "auto",
    "after",
    "role",
    "manual",
    "days",
    "hours",
    "minutes",
    # v0.10.2 Date Arithmetic keywords
    "today",
    "now",
    "weeks",
    "months",
    "years",
    # Computed Field keywords
    "computed",
    "sum",
    "avg",
    "min",
    "max",
    "days_until",
    "days_since",
    # Invariant keywords
    "invariant",
    "code",
    # v0.9.5 App Config keywords
    "description",
    "multi_tenant",
    "audit_trail",
    "security_profile",  # v0.11.0
    # v0.9.5 Field Type keywords
    "money",
    "file",
    "via",
    # v0.7.1 LLM Cognition keywords
    "intent",
    "examples",
    "domain",
    "patterns",
    "extends",
    "archetype",
    "has_many",
    "has_one",
    "embeds",
    "belongs_to",
    "cascade",
    "restrict",
    "nullify",
    "readonly",
    "deny",
    "scenarios",
    "given",
    "then",
    # v0.8.5 Dazzle Bar keywords
    "scenario",
    "demo",
    "persona",
    "goals",
    "proficiency",
    "seed_script",
    "start_route",
    # v0.18.0 Event-First Architecture keywords
    "event_model",
    "publish",
    "subscribe",
    "project",
    "topic",
    "retention",
    # v0.18.0 Governance keywords (Issue #25)
    "policies",
    "tenancy",
    "interfaces",
    "data_products",
    "classify",
    "erasure",
    "data_product",
    # v0.19.0 HLESS (High-Level Event Semantics) keywords
    "FACT",
    "OBSERVATION",
    "DERIVATION",
    "partition_key",
    "ordering_scope",
    "idempotency",
    "outcomes",
    "derives_from",
    "emits",
    "side_effects",
    "allowed",
    "schema",
    "note",
    "t_event",
    "t_log",
    "t_process",
    "hless",
    "strict",
    "warn",
    "off",
    # v0.21.0 LLM Jobs as First-Class Events (Issue #33)
    "llm_model",
    "llm_config",
    "llm_intent",
    "tier",
    "max_tokens",
    "cost_per_1k_input",
    "cost_per_1k_output",
    "model_id",
    "artifact_store",
    "logging",
    "log_prompts",
    "log_completions",
    "redact_pii",
    "rate_limits",
    "default_model",
    "prompt",
    "output_schema",
    "timeout",
    "retry",
    "pii",
    "max_attempts",
    "backoff",
    "initial_delay_ms",
    "max_delay_ms",
    "scan",
    # Note: 'model' is not a keyword - it's a common field name
    # Note: enum values (redact, reject, linear, exponential) not in keywords
    # v0.9.0 Messaging Channel keywords
    # Note: "message" already in UX keywords
    "channel",
    "send",
    "receive",
    "provider",
    "config",
    "provider_config",
    "delivery_mode",
    "outbox",
    "direct",
    "throttle",
    "per_recipient",
    "per_entity",
    "per_channel",
    "window",
    "max_messages",
    "on_exceed",
    "drop",
    "log",
    "queue",
    "stream",
    "email",
    "asset",
    "document",
    "template",
    "subject",
    "body",
    "html_body",
    "attachments",
    "asset_ref",
    "document_ref",
    "entity_arg",
    "filename",
    "for_entity",
    "format",
    "layout",
    "path",
    "changed",
    "to",
    "succeeded",
    "failed",
    "every",
    "cron",
    "upsert",
    "regex",
}


@dataclass
class Token:
    """
    A single token in the DSL.

    Attributes:
        type: Type of token
        value: String value of the token
        line: Line number (1-indexed)
        column: Column number (1-indexed)
    """

    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.type.value}, {self.value!r}, {self.line}:{self.column})"


class Lexer:
    """
    Lexer for DAZZLE DSL.

    Converts source text into a stream of tokens with indentation tracking.
    """

    def __init__(self, text: str, file: Path):
        """
        Initialize lexer.

        Args:
            text: Source text to tokenize
            file: Source file path (for error reporting)
        """
        self.text = text
        self.file = file
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
        self.indent_stack = [0]  # Stack of indentation levels

    def current_char(self) -> str | None:
        """Get current character or None if at end."""
        if self.pos >= len(self.text):
            return None
        return self.text[self.pos]

    def peek_char(self, offset: int = 1) -> str | None:
        """Peek ahead at character."""
        pos = self.pos + offset
        if pos >= len(self.text):
            return None
        return self.text[pos]

    def advance(self) -> None:
        """Move to next character, updating line/column."""
        if self.pos < len(self.text):
            if self.text[self.pos] == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def skip_whitespace(self, skip_newlines: bool = False) -> None:
        """Skip whitespace characters."""
        while self.current_char() in (" ", "\t", "\r") or (
            skip_newlines and self.current_char() == "\n"
        ):
            self.advance()

    def skip_comment(self) -> None:
        """Skip comment (from # to end of line)."""
        if self.current_char() == "#":
            while self.current_char() and self.current_char() != "\n":
                self.advance()

    def read_string(self) -> str:
        """Read a quoted string."""
        start_line = self.line
        start_col = self.column
        quote = self.current_char()  # " or '
        self.advance()  # skip opening quote

        chars = []
        while True:
            current = self.current_char()
            if not current or current == quote:
                break

            if current == "\\":
                self.advance()
                # Handle escape sequences
                escape_char = self.current_char()
                if escape_char == "n":
                    chars.append("\n")
                elif escape_char == "t":
                    chars.append("\t")
                elif escape_char == "\\":
                    chars.append("\\")
                elif escape_char and escape_char == quote:
                    chars.append(quote if quote else "")
                elif escape_char:
                    chars.append(escape_char)
                self.advance()
            else:
                chars.append(current)
                self.advance()

        if self.current_char() != quote:
            raise make_parse_error(
                "Unterminated string literal",
                self.file,
                start_line,
                start_col,
            )

        self.advance()  # skip closing quote
        return "".join(chars)

    def read_number(self) -> tuple[str, bool]:
        """
        Read a number (integer or decimal), optionally followed by duration suffix.

        Returns:
            Tuple of (value, is_duration_literal)
            Duration suffixes: min, h, d, w, m, y (e.g., 7d, 24h, 30min)
        """
        chars = []
        current = self.current_char()
        while current and (current.isdigit() or current == "."):
            chars.append(current)
            self.advance()
            current = self.current_char()

        number_str = "".join(chars)

        # Check for duration suffix (compact syntax: 7d, 24h, 30min, 2w, 3m, 1y)
        # Only for integers (not decimals)
        if "." not in number_str and current and current.isalpha():
            suffix_start = self.pos
            suffix_chars = []
            while current and current.isalpha():
                suffix_chars.append(current)
                self.advance()
                current = self.current_char()

            suffix = "".join(suffix_chars)
            # Valid duration suffixes
            if suffix in ("min", "h", "d", "w", "m", "y"):
                return f"{number_str}{suffix}", True
            else:
                # Not a duration, reset position to after number
                self.pos = suffix_start
                self.column -= len(suffix_chars)  # Approximate column reset

        return number_str, False

    def read_identifier(self) -> str:
        """Read an identifier or keyword."""
        chars = []
        current = self.current_char()
        while current and (current.isalnum() or current == "_"):
            chars.append(current)
            self.advance()
            current = self.current_char()
        return "".join(chars)

    def handle_indentation(self, indent_level: int) -> None:
        """Generate INDENT/DEDENT tokens based on indentation level."""
        current_indent = self.indent_stack[-1]

        if indent_level > current_indent:
            self.indent_stack.append(indent_level)
            self.tokens.append(Token(TokenType.INDENT, "", self.line, 1))

        elif indent_level < current_indent:
            while self.indent_stack and self.indent_stack[-1] > indent_level:
                self.indent_stack.pop()
                self.tokens.append(Token(TokenType.DEDENT, "", self.line, 1))

            if self.indent_stack[-1] != indent_level:
                raise make_parse_error(
                    f"Inconsistent indentation (expected {self.indent_stack[-1]} spaces, got {indent_level})",
                    self.file,
                    self.line,
                    1,
                )

    def tokenize(self) -> list[Token]:
        """
        Tokenize the entire source text.

        Returns:
            List of tokens including INDENT/DEDENT and EOF

        Raises:
            ParseError: If syntax error encountered
        """
        at_line_start = True

        while self.pos < len(self.text):
            # Handle line start (indentation)
            if at_line_start:
                indent_level = 0
                while self.current_char() in (" ", "\t"):
                    if self.current_char() == " ":
                        indent_level += 1
                    elif self.current_char() == "\t":
                        indent_level += 4  # Treat tab as 4 spaces
                    self.advance()

                # Skip blank lines and comments
                if self.current_char() in ("\n", "#"):
                    if self.current_char() == "#":
                        self.skip_comment()
                    if self.current_char() == "\n":
                        self.tokens.append(Token(TokenType.NEWLINE, "\\n", self.line, self.column))
                        self.advance()
                    continue

                # Handle indentation changes
                if self.current_char() is not None:
                    self.handle_indentation(indent_level)

                at_line_start = False

            # Skip whitespace (but not newlines)
            self.skip_whitespace(skip_newlines=False)

            ch = self.current_char()
            if ch is None:
                break

            # Save position for token
            token_line = self.line
            token_col = self.column

            # Comments
            if ch == "#":
                self.skip_comment()
                continue

            # Newlines
            elif ch == "\n":
                self.tokens.append(Token(TokenType.NEWLINE, "\\n", token_line, token_col))
                self.advance()
                at_line_start = True

            # Strings
            elif ch in ('"', "'"):
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, token_line, token_col))

            # Numbers (and duration literals like 7d, 24h)
            elif ch.isdigit():
                value, is_duration = self.read_number()
                if is_duration:
                    self.tokens.append(
                        Token(TokenType.DURATION_LITERAL, value, token_line, token_col)
                    )
                else:
                    self.tokens.append(Token(TokenType.NUMBER, value, token_line, token_col))

            # Identifiers and keywords
            elif ch.isalpha() or ch == "_":
                value = self.read_identifier()
                if value in KEYWORDS:
                    token_type = TokenType(value)
                else:
                    token_type = TokenType.IDENTIFIER
                self.tokens.append(Token(token_type, value, token_line, token_col))

            # Operators
            elif ch == ":":
                self.advance()
                self.tokens.append(Token(TokenType.COLON, ":", token_line, token_col))

            elif ch == ",":
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ",", token_line, token_col))

            elif ch == "(":
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, "(", token_line, token_col))

            elif ch == ")":
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ")", token_line, token_col))

            elif ch == "[":
                self.advance()
                self.tokens.append(Token(TokenType.LBRACKET, "[", token_line, token_col))

            elif ch == "]":
                self.advance()
                self.tokens.append(Token(TokenType.RBRACKET, "]", token_line, token_col))

            elif ch == "=":
                if self.peek_char() == "=":
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.DOUBLE_EQUALS, "==", token_line, token_col))
                else:
                    self.advance()
                    self.tokens.append(Token(TokenType.EQUALS, "=", token_line, token_col))

            elif ch == "!":
                if self.peek_char() == "=":
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.NOT_EQUALS, "!=", token_line, token_col))
                else:
                    raise make_parse_error(
                        f"Unexpected character: {ch!r}",
                        self.file,
                        token_line,
                        token_col,
                    )

            elif ch == ">":
                if self.peek_char() == "=":
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.GREATER_EQUAL, ">=", token_line, token_col))
                else:
                    self.advance()
                    self.tokens.append(Token(TokenType.GREATER_THAN, ">", token_line, token_col))

            elif ch == ".":
                self.advance()
                self.tokens.append(Token(TokenType.DOT, ".", token_line, token_col))

            elif ch == "?":
                self.advance()
                self.tokens.append(Token(TokenType.QUESTION, "?", token_line, token_col))

            elif ch == "/":
                self.advance()
                self.tokens.append(Token(TokenType.SLASH, "/", token_line, token_col))

            elif ch == "-":
                if self.peek_char() == ">":
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.ARROW, "->", token_line, token_col))
                else:
                    # Standalone minus operator (for arithmetic)
                    self.advance()
                    self.tokens.append(Token(TokenType.MINUS, "-", token_line, token_col))

            elif ch == "<":
                if self.peek_char() == "-":
                    if self.peek_char(2) == ">":
                        self.advance()
                        self.advance()
                        self.advance()
                        self.tokens.append(Token(TokenType.BIARROW, "<->", token_line, token_col))
                    else:
                        self.advance()
                        self.advance()
                        self.tokens.append(Token(TokenType.LARROW, "<-", token_line, token_col))
                elif self.peek_char() == "=":
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.LESS_EQUAL, "<=", token_line, token_col))
                else:
                    self.advance()
                    self.tokens.append(Token(TokenType.LESS_THAN, "<", token_line, token_col))

            elif ch == "+":
                self.advance()
                self.tokens.append(Token(TokenType.PLUS, "+", token_line, token_col))

            elif ch == "*":
                self.advance()
                self.tokens.append(Token(TokenType.STAR, "*", token_line, token_col))

            elif ch == "%":
                self.advance()
                self.tokens.append(Token(TokenType.PERCENT, "%", token_line, token_col))

            else:
                raise make_parse_error(
                    f"Unexpected character: {ch!r}",
                    self.file,
                    token_line,
                    token_col,
                )

        # Emit remaining DEDENTs
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, "", self.line, self.column))

        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))

        return self.tokens


def tokenize(text: str, file: Path) -> list[Token]:
    """
    Convenience function to tokenize DSL text.

    Args:
        text: Source text
        file: Source file path

    Returns:
        List of tokens
    """
    lexer = Lexer(text, file)
    return lexer.tokenize()
