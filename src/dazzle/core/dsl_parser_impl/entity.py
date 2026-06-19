"""
Entity parsing for DAZZLE DSL.

Handles entity declarations including fields, constraints, state machines,
access rules, invariants, and LLM cognition features.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .fitness import parse_fitness_block
from .lifecycle import parse_lifecycle_block


@dataclass
class _EntityParseContext:
    """Accumulator for all sub-parts parsed inside an entity block."""

    # LLM cognition (v0.7.1)
    intent: str | None = None
    domain: str | None = None
    patterns: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    examples: list[ir.ExampleRecord] = field(default_factory=list)
    # Semantic archetype (v0.10.3)
    archetype_kind: ir.ArchetypeKind | None = None
    # Soft delete and bulk config (v0.34.0)
    soft_delete: bool = False
    # Native document signing primitive (v0.79.7, #1283 phase 3)
    signable: bool = False
    signing_validator: str | None = None
    # v0.79.12 (#1283 phase 6a)
    signing_template: str | None = None
    # Subtype-of polymorphism (v0.71.180, #1217 Phase 3e.i)
    subtype_of: str | None = None
    # Temporal / effective-dated spec (v0.71.161 / #1223 Phase 3a.i)
    temporal: ir.TemporalSpec | None = None
    # Tenant host routing spec (v0.80.7, #1289 slice 1)
    tenant_host: ir.TenantHostSpec | None = None
    # Declarative membership relation (ADR-0037, #1393 Phase C)
    membership: ir.MembershipSpec | None = None
    # Lifecycle-ownership marker (#1333): route/pipeline/wizard/external
    managed_by: ir.ManagedBy | None = None
    # #1420 Slice 2: per-op generated-REST allowlist (None = all ops, default)
    api_expose: tuple[str, ...] | None = None
    bulk_config: ir.BulkConfig | None = None
    # Seed template (v0.38.0)
    seed_template: ir.SeedTemplateSpec | None = None
    # Display field (v0.44.0)
    display_field: str | None = None
    # Graph semantics (v0.46.0)
    graph_edge: ir.GraphEdgeSpec | None = None
    graph_node: ir.GraphNodeSpec | None = None
    # Lifecycle (ADR-0020)
    lifecycle: ir.LifecycleSpec | None = None
    # Fitness (Agent-Led Fitness v1)
    fitness_spec: ir.FitnessSpec | None = None

    # Fields
    fields: list[ir.FieldSpec] = field(default_factory=list)
    computed_fields: list[ir.ComputedFieldSpec] = field(default_factory=list)
    constraints: list[ir.Constraint] = field(default_factory=list)
    visibility_rules: list[ir.VisibilityRule] = field(default_factory=list)
    permission_rules: list[ir.PermissionRule] = field(default_factory=list)
    scope_rules: list[ir.ScopeRule] = field(default_factory=list)
    transitions: list[ir.StateTransition] = field(default_factory=list)
    transition_effects: list[tuple[str, str, list[ir.StepEffect], ir.InvokeFlowSpec | None]] = (
        field(default_factory=list)
    )
    invariants: list[ir.InvariantSpec] = field(default_factory=list)
    publishes: list[ir.PublishSpec] = field(default_factory=list)
    audit_config: ir.AuditConfig | None = None


class EntityParserMixin:
    """
    Mixin providing entity and archetype parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    # Type stubs for methods provided by BaseParser and other mixins
    if TYPE_CHECKING:
        expect: Any
        enum_from_token: Any
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
        # v0.29.0: Expression bridge from BaseParser
        collect_line_as_expr: Any
        # v0.31.0: Source location helper from BaseParser
        _source_location: Any
        _parse_construct_header: Any

    def parse_entity(self) -> ir.EntitySpec:
        """Parse entity declaration.

        Dispatches each keyword to a dedicated ``_parse_entity_*`` helper,
        accumulating results in an ``_EntityParseContext``.
        """
        name, title, loc = self._parse_construct_header(TokenType.ENTITY)
        ctx = _EntityParseContext()

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.INTENT):
                ctx.intent = self._parse_entity_intent()
            elif self.match(TokenType.DOMAIN):
                ctx.domain = self._parse_entity_domain()
            elif self.match(TokenType.PATTERNS):
                ctx.patterns = self._parse_entity_patterns()
            elif self.match(TokenType.EXTENDS):
                ctx.extends = self._parse_entity_extends()
            elif self.match(TokenType.ARCHETYPE):
                ctx.archetype_kind = self._parse_entity_archetype()
            elif self.match(TokenType.EXAMPLES):
                ctx.examples.extend(self._parse_entity_examples())
            elif self.match(TokenType.UNIQUE, TokenType.INDEX):
                ctx.constraints.append(self._parse_entity_constraint())
            elif self.match(TokenType.INVARIANT):
                ctx.invariants.append(self._parse_entity_invariant())
            elif self.match(TokenType.VISIBLE):
                ctx.visibility_rules.extend(self._parse_entity_visible_block())
            elif self.match(TokenType.PERMISSIONS):
                ctx.permission_rules.extend(self._parse_entity_permissions_block())
            elif self.match(TokenType.ACCESS):
                self._parse_entity_access_block(ctx)
            elif self.match(TokenType.PERMIT):
                ctx.permission_rules.extend(self._parse_entity_policy_block(ir.PolicyEffect.PERMIT))
            elif self.match(TokenType.FORBID):
                ctx.permission_rules.extend(self._parse_entity_policy_block(ir.PolicyEffect.FORBID))
            elif self.match(TokenType.SCOPE):
                ctx.scope_rules.extend(self._parse_entity_scope_block())
            elif self.match(TokenType.AUDIT):
                ctx.audit_config = self._parse_entity_audit()
            elif self.match(TokenType.SOFT_DELETE):
                self.advance()
                ctx.soft_delete = True
            elif self.match(TokenType.SIGNABLE):
                ctx.signable = self._parse_entity_signable()
            elif self.match(TokenType.SIGNING_VALIDATOR):
                ctx.signing_validator = self._parse_entity_signing_validator()
            elif self.match(TokenType.SIGNING_TEMPLATE):
                ctx.signing_template = self._parse_entity_signing_template()
            elif self.match(TokenType.TEMPORAL):
                ctx.temporal = self._parse_entity_temporal()
            elif self.match(TokenType.SUBTYPE_OF):
                ctx.subtype_of = self._parse_entity_subtype_of()
            elif self.match(TokenType.BULK):
                ctx.bulk_config = self._parse_entity_bulk()
            elif self.match(TokenType.GRAPH_EDGE):
                ctx.graph_edge = self._parse_entity_graph_edge()
            elif self.match(TokenType.GRAPH_NODE):
                ctx.graph_node = self._parse_entity_graph_node()
            elif self.match(TokenType.TRANSITIONS):
                ctx.transitions.extend(self._parse_entity_transitions_block())
            elif self.match(TokenType.ON_TRANSITION):
                ctx.transition_effects.extend(self._parse_entity_on_transition_block())
            elif self.match(TokenType.SEED):
                ctx.seed_template = self._parse_entity_seed()
            elif self.match(TokenType.PUBLISH):
                ctx.publishes.append(self.parse_publish_directive(entity_name=name))
            elif self.match(TokenType.LIFECYCLE):
                ctx.lifecycle = self._parse_entity_lifecycle()
            elif self.match(TokenType.FITNESS):
                ctx.fitness_spec = self._parse_entity_fitness(ctx.fields)
            elif self.match(TokenType.DISPLAY_FIELD):
                ctx.display_field = self._parse_entity_display_field()
            elif self.match(TokenType.TENANT_HOST):
                self._parse_tenant_host_block(ctx)
                continue
            elif self.match(TokenType.MEMBERSHIP):
                self._parse_membership_block(ctx)
                continue
            elif self.match(TokenType.MANAGED_BY):
                ctx.managed_by = self._parse_entity_managed_by()
            elif self.match(TokenType.EXPOSE):
                ctx.api_expose = self._parse_entity_expose()
            else:
                self._parse_entity_field_declaration(ctx)
                continue  # field parsing handles its own skip_newlines

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return self._build_entity_spec(name, title, loc, ctx)

    # ------------------------------------------------------------------
    # Entity keyword helpers
    # ------------------------------------------------------------------

    def _parse_entity_intent(self) -> str:
        """Parse ``intent: "..."`` declaration."""
        self.advance()
        self.expect(TokenType.COLON)
        result: str = self.expect(TokenType.STRING).value
        return result

    def _parse_entity_domain(self) -> str:
        """Parse ``domain: name`` declaration."""
        self.advance()
        self.expect(TokenType.COLON)
        result: str = self.expect_identifier_or_keyword().value
        return result

    def _parse_entity_managed_by(self) -> ir.ManagedBy:
        """Parse ``managed_by: route|pipeline|wizard|external`` (#1333).

        Marks the entity's lifecycle as owned outside the nav graph, which
        exempts it and its surfaces from the dead-construct lint. Rejects
        any value outside the known set with a clear author-time error.
        """
        self.advance()
        self.expect(TokenType.COLON)
        tok = self.expect_identifier_or_keyword()
        try:
            return ir.ManagedBy(tok.value)
        except ValueError:
            allowed = ", ".join(m.value for m in ir.ManagedBy)
            raise make_parse_error(
                f"managed_by: expects one of [{allowed}], got {tok.value!r}",
                self.file,
                tok.line,
                tok.column,
            ) from None

    def _parse_entity_expose(self) -> tuple[str, ...]:
        """Parse ``expose: list, read`` / ``expose: none`` (#1420 Slice 2).

        Comma-separated allowlist of generated-REST ops (mirrors ``patterns:``).
        ``none`` ⇒ empty tuple (no generated public REST). Absent entirely ⇒ the
        ctx default ``None`` (all ops). Rejects any op outside the closed set.
        """
        valid = ("list", "read", "create", "update", "delete")
        self.advance()
        self.expect(TokenType.COLON)
        first = self.expect_identifier_or_keyword()
        if first.value == "none":
            return ()
        ops = [first.value]
        while self.match(TokenType.COMMA):
            self.advance()
            ops.append(self.expect_identifier_or_keyword().value)
        for op in ops:
            if op not in valid:
                raise make_parse_error(
                    f"expose: expects ops in [{', '.join(valid)}] or `none`, got {op!r}",
                    self.file,
                    first.line,
                    first.column,
                )
        return tuple(ops)

    def _parse_entity_patterns(self) -> list[str]:
        """Parse ``patterns: a, b, c`` declaration."""
        self.advance()
        self.expect(TokenType.COLON)
        patterns = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.COMMA):
            self.advance()
            patterns.append(self.expect_identifier_or_keyword().value)
        return patterns

    def _parse_entity_extends(self) -> list[str]:
        """Parse ``extends: A, B`` declaration."""
        self.advance()
        self.expect(TokenType.COLON)
        extends = [self.expect(TokenType.IDENTIFIER).value]
        while self.match(TokenType.COMMA):
            self.advance()
            extends.append(self.expect(TokenType.IDENTIFIER).value)
        return extends

    def _parse_entity_subtype_of(self) -> str:
        """Parse ``subtype_of: <Identifier>`` declaration (#1217 Phase 3e.i).

        Exactly one identifier — no multiple inheritance in v1.
        """
        self.advance()
        self.expect(TokenType.COLON)
        base_tok = self.expect(TokenType.IDENTIFIER)
        base: str = base_tok.value
        # Reject comma-separated lists: multiple inheritance is out of scope.
        if self.match(TokenType.COMMA):
            raise make_parse_error(
                f"subtype_of: expects exactly one identifier (got list starting with {base!r}). "
                "Multiple inheritance is not supported in v1.",
                self.file,
                base_tok.line,
                base_tok.column,
            )
        return base

    def _parse_entity_archetype(self) -> ir.ArchetypeKind:
        """Parse ``archetype: kind`` declaration."""
        self.advance()
        self.expect(TokenType.COLON)
        archetype_value = self.expect_identifier_or_keyword().value
        return self._map_archetype_kind(archetype_value)

    def _parse_entity_signable(self) -> bool:
        """Parse ``signable: true|false`` declaration (#1283 phase 3).

        Sets the entity flag that triggers the linker's auto-injection
        of the 11 signing fields and the audit default.
        """
        self.advance()
        self.expect(TokenType.COLON)
        if self.match(TokenType.TRUE):
            self.advance()
            return True
        if self.match(TokenType.FALSE):
            self.advance()
            return False
        tok = self.current_token()
        raise make_parse_error(
            f"signable: expects 'true' or 'false', got {tok.value!r}",
            self.file,
            tok.line,
            tok.column,
        )

    def _parse_entity_signing_validator(self) -> str:
        """Parse ``signing_validator: dotted.path.to.callable`` (#1283).

        Dotted-path string identifying a pre-sign hook that can raise
        ``SigningError(...)`` to block the signature. Resolved lazily at
        request time so the framework does not import project code at
        parse time.
        """
        self.advance()
        self.expect(TokenType.COLON)
        parts: list[str] = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)
        return ".".join(parts)

    def _parse_entity_signing_template(self) -> str:
        """Parse ``signing_template: dotted.path.to.callable`` (#1283 phase 6a).

        Dotted-path identifying a project-supplied callable that returns
        the document body HTML. Signature: ``(entity, row) -> str``.
        Resolved lazily at request time alongside ``signing_validator``.
        """
        self.advance()
        self.expect(TokenType.COLON)
        parts: list[str] = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)
        return ".".join(parts)

    def _parse_entity_examples(self) -> list[ir.ExampleRecord]:
        """Parse ``examples:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        examples: list[ir.ExampleRecord] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            examples.append(self._parse_example_record())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return examples

    def _parse_entity_constraint(self) -> ir.Constraint:
        """Parse ``unique`` or ``index`` constraint with field list."""
        constraint_kind = self.advance().type
        kind = (
            ir.ConstraintKind.UNIQUE
            if constraint_kind == TokenType.UNIQUE
            else ir.ConstraintKind.INDEX
        )
        field_names = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.COMMA):
            self.advance()
            field_names.append(self.expect_identifier_or_keyword().value)
        return ir.Constraint(kind=kind, fields=field_names)

    def _parse_entity_invariant(self) -> ir.InvariantSpec:
        """Parse ``invariant:`` with optional indented message/code."""
        self.advance()
        self.expect(TokenType.COLON)
        inv_expr = self.collect_line_as_expr()
        self.skip_newlines()

        inv_message: str | None = None
        inv_code: str | None = None

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
                    break
                self.skip_newlines()
            if self.match(TokenType.DEDENT):
                self.advance()

        return ir.InvariantSpec(
            invariant_expr=inv_expr,
            message=inv_message,
            code=inv_code,
        )

    def _parse_entity_visible_block(self) -> list[ir.VisibilityRule]:
        """Parse ``visible:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        rules: list[ir.VisibilityRule] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            rules.append(self._parse_visibility_rule())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return rules

    def _parse_entity_permissions_block(self) -> list[ir.PermissionRule]:
        """Parse ``permissions:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        rules: list[ir.PermissionRule] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            rules.append(self._parse_permission_rule())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return rules

    def _parse_entity_access_block(self, ctx: _EntityParseContext) -> None:
        """Parse ``access:`` shorthand block (read/write/create/delete/list).

        Mutates *ctx* in-place because ``read:`` produces both a visibility
        rule and a permission rule, and ``write:`` fans out to CREATE + UPDATE.
        """
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.READ):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                ctx.visibility_rules.append(
                    ir.VisibilityRule(
                        context=ir.AuthContext.AUTHENTICATED,
                        condition=condition,
                    )
                )
                ctx.permission_rules.append(
                    ir.PermissionRule(
                        operation=ir.PermissionKind.READ,
                        require_auth=True,
                        condition=condition,
                        effect=ir.PolicyEffect.PERMIT,
                    )
                )
            elif self.match(TokenType.WRITE):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                for op in [
                    ir.PermissionKind.CREATE,
                    ir.PermissionKind.UPDATE,
                ]:
                    ctx.permission_rules.append(
                        ir.PermissionRule(
                            operation=op,
                            require_auth=True,
                            condition=condition,
                            effect=ir.PolicyEffect.PERMIT,
                        )
                    )
            elif self.match(TokenType.DELETE):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                ctx.permission_rules.append(
                    ir.PermissionRule(
                        operation=ir.PermissionKind.DELETE,
                        require_auth=True,
                        condition=condition,
                        effect=ir.PolicyEffect.PERMIT,
                    )
                )
            elif self.match(TokenType.CREATE):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                ctx.permission_rules.append(
                    ir.PermissionRule(
                        operation=ir.PermissionKind.CREATE,
                        require_auth=True,
                        condition=condition,
                        effect=ir.PolicyEffect.PERMIT,
                    )
                )
            elif self.match(TokenType.LIST):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                ctx.permission_rules.append(
                    ir.PermissionRule(
                        operation=ir.PermissionKind.LIST,
                        require_auth=True,
                        condition=condition,
                        effect=ir.PolicyEffect.PERMIT,
                    )
                )
            else:
                token = self.current_token()
                raise make_parse_error(
                    f"Expected 'read', 'write', 'create', 'delete', or 'list' "
                    f"in access block, got {token.type.value}",
                    self.file,
                    token.line,
                    token.column,
                )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

    def _parse_entity_policy_block(self, effect: ir.PolicyEffect) -> list[ir.PermissionRule]:
        """Parse ``permit:`` or ``forbid:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        rules: list[ir.PermissionRule] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            rules.append(self._parse_policy_rule(effect))
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return rules

    def _parse_entity_scope_block(self) -> list[ir.ScopeRule]:
        """Parse ``scope:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        rules: list[ir.ScopeRule] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            rules.append(self._parse_scope_rule())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return rules

    def _parse_entity_audit(self) -> ir.AuditConfig:
        """Parse ``audit:`` directive."""
        self.advance()
        self.expect(TokenType.COLON)
        return self._parse_audit_directive()

    def _parse_entity_bulk(self) -> ir.BulkConfig:
        """Parse ``bulk:`` block."""
        self.advance()
        self.expect(TokenType.COLON)
        return self._parse_bulk_config()

    _TEMPORAL_VALID_KEYS: tuple[str, ...] = (
        "start_field",
        "end_field",
        "key_field",
        "default_filter",
        "as_of_param",
    )
    _TEMPORAL_DEFAULT_FILTER_VALUES: tuple[str, ...] = ("active", "none")

    def _parse_entity_temporal(self) -> ir.TemporalSpec:
        """Parse the entity-level ``temporal:`` block (#1223 Phase 3a.i).

        Syntax::

            temporal:
              start_field: start_date
              end_field: end_date
              key_field: person
              default_filter: active     # optional, default 'active'
              as_of_param: as_of         # optional, default 'as_of'
        """
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        start_field: str | None = None
        end_field: str | None = None
        key_field: str | None = None
        default_filter: str = "active"
        as_of_param: str = "as_of"

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.current_token()
            key = key_tok.value
            if key not in self._TEMPORAL_VALID_KEYS:
                raise make_parse_error(
                    f"Unknown temporal: key {key!r}. "
                    f"Expected one of: {', '.join(self._TEMPORAL_VALID_KEYS)}.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)
            value_tok = self.expect_identifier_or_keyword()
            value = str(value_tok.value)

            if key == "start_field":
                start_field = value
            elif key == "end_field":
                end_field = value
            elif key == "key_field":
                key_field = value
            elif key == "default_filter":
                if value not in self._TEMPORAL_DEFAULT_FILTER_VALUES:
                    raise make_parse_error(
                        f"Unknown temporal default_filter: {value!r}. "
                        f"Expected one of: {', '.join(self._TEMPORAL_DEFAULT_FILTER_VALUES)}.",
                        self.file,
                        value_tok.line,
                        value_tok.column,
                    )
                default_filter = value
            elif key == "as_of_param":
                as_of_param = value
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if start_field is None or end_field is None or key_field is None:
            tok = self.current_token()
            missing = [
                name
                for name, val in (
                    ("start_field", start_field),
                    ("end_field", end_field),
                    ("key_field", key_field),
                )
                if val is None
            ]
            raise make_parse_error(
                f"temporal: block missing required key(s): {', '.join(missing)}",
                self.file,
                tok.line,
                tok.column,
            )

        return ir.TemporalSpec(
            start_field=start_field,
            end_field=end_field,
            key_field=key_field,
            default_filter=default_filter,
            as_of_param=as_of_param,
        )

    def _parse_entity_graph_edge(self) -> ir.GraphEdgeSpec:
        """Parse ``graph_edge:`` indented block (v0.46.0, #619)."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        ge_block_line = self.current_token().line
        ge_block_column = self.current_token().column
        ge_source: str | None = None
        ge_target: str | None = None
        ge_type: str | None = None
        ge_weight: str | None = None
        ge_directed: bool = True
        ge_acyclic: bool = False

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                ge_source = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.TARGET):
                self.advance()
                self.expect(TokenType.COLON)
                ge_target = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "type":
                self.advance()
                self.expect(TokenType.COLON)
                ge_type = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.WEIGHT):
                self.advance()
                self.expect(TokenType.COLON)
                ge_weight = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.DIRECTED):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    ge_directed = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    ge_directed = False
                else:
                    raise make_parse_error(
                        "Expected true or false for directed",
                        self.file,
                        self.current_token().line,
                        self.current_token().column,
                    )
            elif self.match(TokenType.ACYCLIC):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    ge_acyclic = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    ge_acyclic = False
                else:
                    raise make_parse_error(
                        "Expected true or false for acyclic",
                        self.file,
                        self.current_token().line,
                        self.current_token().column,
                    )
            else:
                raise make_parse_error(
                    f"Unexpected token in graph_edge: block: {self.current_token().value}",
                    self.file,
                    self.current_token().line,
                    self.current_token().column,
                )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if ge_source is None or ge_target is None:
            raise make_parse_error(
                "graph_edge: requires both source and target fields",
                self.file,
                ge_block_line,
                ge_block_column,
            )

        return ir.GraphEdgeSpec(
            source=ge_source,
            target=ge_target,
            type_field=ge_type,
            weight_field=ge_weight,
            directed=ge_directed,
            acyclic=ge_acyclic,
        )

    def _parse_entity_graph_node(self) -> ir.GraphNodeSpec:
        """Parse ``graph_node:`` indented block (v0.46.0, #619)."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        gn_block_line = self.current_token().line
        gn_block_column = self.current_token().column
        gn_edges: str | None = None
        gn_display: str | None = None
        gn_parent: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.EDGES):
                self.advance()
                self.expect(TokenType.COLON)
                gn_edges = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.DISPLAY):
                self.advance()
                self.expect(TokenType.COLON)
                gn_display = self.expect_identifier_or_keyword().value
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "parent":
                # parent: <ref_field> — closes #781
                self.advance()
                self.expect(TokenType.COLON)
                gn_parent = self.expect_identifier_or_keyword().value
            else:
                raise make_parse_error(
                    f"Unexpected token in graph_node: block: {self.current_token().value}",
                    self.file,
                    self.current_token().line,
                    self.current_token().column,
                )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if gn_edges is None:
            raise make_parse_error(
                "graph_node: requires an edges field",
                self.file,
                gn_block_line,
                gn_block_column,
            )

        return ir.GraphNodeSpec(
            edge_entity=gn_edges,
            display=gn_display,
            parent_field=gn_parent,
        )

    def _parse_entity_transitions_block(self) -> list[ir.StateTransition]:
        """Parse ``transitions:`` indented block."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        transitions: list[ir.StateTransition] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            transitions.append(self._parse_state_transition())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return transitions

    def _parse_entity_on_transition_block(
        self,
    ) -> list[tuple[str, str, list[ir.StepEffect], ir.InvokeFlowSpec | None]]:
        """Parse ``on_transition:`` indented block (v0.39.0)."""
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        effects: list[tuple[str, str, list[ir.StepEffect], ir.InvokeFlowSpec | None]] = []
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            effects.append(self._parse_transition_effect())
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return effects

    def _parse_entity_seed(self) -> ir.SeedTemplateSpec:
        """Parse ``seed:`` block (v0.38.0)."""
        self.advance()
        self.expect(TokenType.COLON)
        return self._parse_seed_template()

    def _parse_entity_lifecycle(self) -> ir.LifecycleSpec:
        """Parse ``lifecycle:`` block (ADR-0020)."""
        self.advance()
        self.expect(TokenType.COLON)
        return parse_lifecycle_block(self)  # type: ignore[arg-type]

    def _parse_entity_fitness(self, fields: list[ir.FieldSpec]) -> ir.FitnessSpec:
        """Parse ``fitness:`` block (Agent-Led Fitness v1)."""
        self.advance()
        self.expect(TokenType.COLON)
        declared_field_names = {f.name for f in fields}
        return parse_fitness_block(
            self,  # type: ignore[arg-type]
            declared_field_names,
        )

    def _parse_entity_display_field(self) -> str:
        """Parse ``display_field: name`` declaration (v0.44.0)."""
        self.advance()
        self.expect(TokenType.COLON)
        result: str = self.expect_identifier_or_keyword().value
        return result

    _TENANT_HOST_ALLOWED_KEYS: frozenset[str] = frozenset(
        {
            "domain",
            "slug_field",
            "canonical_hosts",
            "cookie_scope",
            "super_admin_role",
            "history_entity",
            "not_found_template",
            "expired_template",
            "order",
            "parent",  # ADR-0036 (#1394 L2): tenant-hierarchy parent FK field
        }
    )

    def _parse_tenant_host_block(self, ctx: _EntityParseContext) -> None:
        """Parse the ``tenant_host:`` indented sub-field block (#1289 slice 1)."""
        self.advance()  # consume TENANT_HOST
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        fields: dict[str, object] = {}
        last_key_tok = None
        while not self.match(TokenType.DEDENT) and not self.match(TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT) or self.match(TokenType.EOF):
                break
            last_key_tok = self.expect_identifier_or_keyword()
            key = last_key_tok.value
            self.expect(TokenType.COLON)
            if key == "canonical_hosts":
                # Parse bracketed comma-separated list of domain-like values: [a.b.c, d.e]
                # Each item may be a dotted sequence (www.example.com) so we join
                # consecutive IDENTIFIER/DOT tokens until we hit COMMA or RBRACKET.
                self.expect(TokenType.LBRACKET)
                items: list[str] = []
                while not self.match(TokenType.RBRACKET):
                    parts: list[str] = [self.expect_identifier_or_keyword().value]
                    while self.match(TokenType.DOT):
                        self.advance()
                        parts.append(self.expect_identifier_or_keyword().value)
                    items.append(".".join(parts))
                    if self.match(TokenType.COMMA):
                        self.advance()
                self.expect(TokenType.RBRACKET)
                fields[key] = items
            elif key == "order":
                fields[key] = int(self.expect(TokenType.NUMBER).value)
            else:
                # Scalar: collect remaining tokens on line as a compact string.
                # Handles simple identifiers (e.g. "host", "admin"), dotted paths
                # (e.g. "example.com"), and module:callable paths (e.g. "pkg.tpl:render_404").
                # We join without spaces so colons and dots stay glued.
                scalar_parts: list[str] = []
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                    scalar_parts.append(str(self.advance().value))
                fields[key] = "".join(scalar_parts)
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        extra = set(fields) - self._TENANT_HOST_ALLOWED_KEYS
        if extra:
            tok_line = last_key_tok.line if last_key_tok else 0
            tok_col = last_key_tok.column if last_key_tok else 0
            raise make_parse_error(
                f"Unknown sub-field(s) in tenant_host: block: {sorted(extra)}",
                self.file,
                tok_line,
                tok_col,
            )
        if "domain" not in fields or "slug_field" not in fields:
            tok_line = last_key_tok.line if last_key_tok else 0
            tok_col = last_key_tok.column if last_key_tok else 0
            raise make_parse_error(
                "tenant_host: requires `domain:` and `slug_field:` sub-fields",
                self.file,
                tok_line,
                tok_col,
            )
        ctx.tenant_host = ir.TenantHostSpec(**fields)  # type: ignore[arg-type]

    _MEMBERSHIP_ALLOWED_KEYS: frozenset[str] = frozenset({"roles"})

    def _parse_membership_block(self, ctx: _EntityParseContext) -> None:
        """Parse the ``membership:`` indented sub-field block (ADR-0037, #1393 Phase C).

        v1 carries a single optional scalar ``roles:`` (the per-tenant role source
        field). The principal is always the framework ``User`` — `identity:` is
        deliberately omitted (ADR-0037 acceptance decision).
        """
        self.advance()  # consume MEMBERSHIP
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        fields: dict[str, object] = {}
        last_key_tok = None
        while not self.match(TokenType.DEDENT) and not self.match(TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT) or self.match(TokenType.EOF):
                break
            last_key_tok = self.expect_identifier_or_keyword()
            key = last_key_tok.value
            self.expect(TokenType.COLON)
            # Scalar: collect the remaining tokens on the line as a compact string.
            scalar_parts: list[str] = []
            while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                scalar_parts.append(str(self.advance().value))
            fields[key] = "".join(scalar_parts)
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        extra = set(fields) - self._MEMBERSHIP_ALLOWED_KEYS
        if extra:
            tok_line = last_key_tok.line if last_key_tok else 0
            tok_col = last_key_tok.column if last_key_tok else 0
            raise make_parse_error(
                f"Unknown sub-field(s) in membership: block: {sorted(extra)}",
                self.file,
                tok_line,
                tok_col,
            )
        ctx.membership = ir.MembershipSpec(**fields)  # type: ignore[arg-type]

    def _parse_entity_field_declaration(self, ctx: _EntityParseContext) -> None:
        """Parse a regular or computed field declaration (the default branch)."""
        field_name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)

        if self.match(TokenType.COMPUTED):
            self.advance()
            comp_expr = self.collect_line_as_expr()
            ctx.computed_fields.append(
                ir.ComputedFieldSpec(
                    name=field_name,
                    computed_expr=comp_expr,
                )
            )
        else:
            field_type = self.parse_type_spec()
            modifiers, default, default_expr, pii, storage = self.parse_field_modifiers()
            ctx.fields.append(
                ir.FieldSpec(
                    name=field_name,
                    type=field_type,
                    modifiers=modifiers,
                    default=default,
                    default_expr=default_expr,
                    pii=pii,
                    storage=storage,
                )
            )

        self.skip_newlines()

    # ------------------------------------------------------------------
    # Entity construction
    # ------------------------------------------------------------------

    def _build_entity_spec(
        self,
        name: str,
        title: str,
        loc: ir.SourceLocation,
        ctx: _EntityParseContext,
    ) -> ir.EntitySpec:
        """Assemble the final EntitySpec from parsed context."""
        # Build access spec if any rules were defined
        access = None
        if ctx.visibility_rules or ctx.permission_rules or ctx.scope_rules:
            access = ir.AccessSpec(
                visibility=ctx.visibility_rules,
                permissions=ctx.permission_rules,
                scopes=ctx.scope_rules,
            )

        # Merge on_transition effects into transitions
        transitions = ctx.transitions
        if ctx.transition_effects:
            transitions = _merge_transition_effects(
                transitions,
                ctx.transition_effects,
                self.file,
                self.current_token().line,
            )

        # Build state machine spec if transitions were defined
        state_machine = None
        if transitions:
            # Find the enum field whose values contain all transition states.
            # This handles entities where the state machine field is not named
            # "status" (e.g. dunning_stage on SubscriptionInvoice).
            status_field_name = None
            states: list[str] = []
            all_transition_states = {t.from_state for t in transitions} | {
                t.to_state for t in transitions
            }
            for f in ctx.fields:
                if f.type.kind == ir.FieldTypeKind.ENUM and f.type.enum_values:
                    if all_transition_states.issubset(set(f.type.enum_values)):
                        status_field_name = f.name
                        states = f.type.enum_values
                        break
            # Fallback: field named "status" (backward compat)
            if not status_field_name:
                for f in ctx.fields:
                    if f.name == "status" and f.type.kind == ir.FieldTypeKind.ENUM:
                        status_field_name = f.name
                        states = f.type.enum_values or []
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
            intent=ctx.intent,
            domain=ctx.domain,
            patterns=ctx.patterns,
            extends=ctx.extends,
            archetype_kind=ctx.archetype_kind,
            fields=ctx.fields,
            computed_fields=ctx.computed_fields,
            invariants=ctx.invariants,
            constraints=ctx.constraints,
            access=access,
            audit=ctx.audit_config,
            soft_delete=ctx.soft_delete,
            signable=ctx.signable,
            signing_validator=ctx.signing_validator,
            signing_template=ctx.signing_template,
            subtype_of=ctx.subtype_of,
            temporal=ctx.temporal,
            bulk=ctx.bulk_config,
            state_machine=state_machine,
            lifecycle=ctx.lifecycle,
            fitness=ctx.fitness_spec,
            examples=ctx.examples,
            publishes=ctx.publishes,
            seed_template=ctx.seed_template,
            display_field=ctx.display_field,
            graph_edge=ctx.graph_edge,
            graph_node=ctx.graph_node,
            tenant_host=ctx.tenant_host,
            membership=ctx.membership,
            managed_by=ctx.managed_by,
            api_expose=ctx.api_expose,
            source=loc,
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
            "profile": ir.ArchetypeKind.PROFILE,  # auth Plan 3c
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

    def _parse_policy_rule(self, effect: ir.PolicyEffect) -> ir.PermissionRule:
        """
        Parse a policy rule inside a permit: or forbid: block.

        Syntax:
            read: role(viewer) or role(admin)
            create: role(editor) or role(admin)
            update: owner_id = current_user and role(editor)
            delete: role(admin)
            list: authenticated
        """
        # Parse operation kind
        op_map = {
            TokenType.CREATE: ir.PermissionKind.CREATE,
            TokenType.READ: ir.PermissionKind.READ,
            TokenType.UPDATE: ir.PermissionKind.UPDATE,
            TokenType.DELETE: ir.PermissionKind.DELETE,
            TokenType.LIST: ir.PermissionKind.LIST,
        }

        token = self.current_token()
        operation = None
        for token_type, kind in op_map.items():
            if self.match(token_type):
                self.advance()
                operation = kind
                break

        if operation is None:
            # Try as identifier (e.g. "write" which maps to create+update)
            if self.match(TokenType.WRITE):
                raise make_parse_error(
                    f"'write' is not valid in {effect.value}: blocks. "
                    f"Use 'create' and 'update' separately.",
                    self.file,
                    token.line,
                    token.column,
                )
            raise make_parse_error(
                f"Expected 'create', 'read', 'update', 'delete', or 'list' "
                f"in {effect.value}: block, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)

        # #1281: `false` short-form. `permit: update: false` explicitly
        # forbids the operation for all callers (append-only entities)
        # rather than relying on the soft-deny `role(nobody)` workaround.
        # Only valid in `permit:` blocks — `forbid: <op>: false` would
        # be ambiguous (does it mean "permit everyone"?). The IR carries
        # `deny_all=True`; the runtime's existing default-deny then
        # excludes the op, and the validator/audit matrix can
        # distinguish intentional prohibition from accidental omission.
        if self.match(TokenType.FALSE):
            bool_token = self.current_token()
            self.advance()
            if effect != ir.PolicyEffect.PERMIT:
                raise make_parse_error(
                    f"`false` short-form is only valid in `permit:` blocks, "
                    f"not `{effect.value}:`. Use a role/condition expression "
                    f"instead.",
                    self.file,
                    bool_token.line,
                    bool_token.column,
                )
            return ir.PermissionRule(
                operation=operation,
                require_auth=True,
                condition=None,
                effect=effect,
                deny_all=True,
            )

        # Check for simple "authenticated" (no condition)
        if self.match(TokenType.AUTHENTICATED):
            self.advance()
            return ir.PermissionRule(
                operation=operation,
                require_auth=True,
                effect=effect,
            )

        # Check for "anonymous" (no auth required)
        if self.match(TokenType.ANONYMOUS):
            self.advance()
            return ir.PermissionRule(
                operation=operation,
                require_auth=False,
                condition=None,
                effect=effect,
            )

        # Otherwise parse condition expression (implies authenticated)
        condition = self.parse_condition_expr()

        # Reject field conditions in permit: blocks — they define row filtering,
        # not authorization. Field conditions must live in scope: blocks.
        if effect == ir.PolicyEffect.PERMIT and self._has_field_condition(condition):
            token = self.current_token()
            raise make_parse_error(
                "Field condition in permit: block. "
                "Field conditions define row filtering, not authorization. "
                "Move to a scope: block.",
                self.file,
                token.line,
                token.column,
            )

        return ir.PermissionRule(
            operation=operation,
            require_auth=True,
            condition=condition,
            effect=effect,
        )

    def _has_field_condition(self, condition: ir.ConditionExpr) -> bool:
        """Return True if condition contains a Comparison (field condition).

        Role checks and grant checks are pure authorization — not field conditions.
        A Comparison (e.g. school = current_user.school) is a field condition.
        """
        if condition.comparison is not None:
            return True
        if condition.left is not None and self._has_field_condition(condition.left):
            return True
        if condition.right is not None and self._has_field_condition(condition.right):
            return True
        return False

    def _parse_scope_rule(self) -> ir.ScopeRule:
        """Parse a single rule inside a scope: block.

        Syntax:
            list: school = current_user.school
              for: teacher, school_admin
            list: all
              for: oracle
            read: owner = current_user
              for: *
        """
        op_map = {
            TokenType.CREATE: ir.PermissionKind.CREATE,
            TokenType.READ: ir.PermissionKind.READ,
            TokenType.UPDATE: ir.PermissionKind.UPDATE,
            TokenType.DELETE: ir.PermissionKind.DELETE,
            TokenType.LIST: ir.PermissionKind.LIST,
        }

        token = self.current_token()
        operation = None
        for token_type, kind in op_map.items():
            if self.match(token_type):
                self.advance()
                operation = kind
                break

        if operation is None:
            raise make_parse_error(
                f"Expected 'create', 'read', 'update', 'delete', or 'list' "
                f"in scope: block, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)

        # Check for 'all' keyword — means no row filter
        condition: ir.ConditionExpr | None
        if self.match(TokenType.ALL):
            self.advance()
            condition = None
        elif self.match(TokenType.VIA):
            condition = self._parse_via_condition()
        elif self.match(TokenType.NOT) and self.peek_token().type == TokenType.VIA:
            # `not via Entity(...)` — VIA is not a token the general
            # expression parser knows, so the negated-junction form stays on
            # its dedicated path. A leading `not (...)` falls through to
            # `parse_condition_expr` instead, so it can compose with
            # `and`/`or` like any other primary (#1180).
            condition = self._parse_not_via_condition()
        else:
            condition = self.parse_condition_expr()

        self.skip_newlines()

        # Parse `as:` clause (indented one level deeper). Renamed from
        # `for:` to remove the overloaded `for` keyword — `as` is a
        # consistent binding-introducer across persona/scope contexts.
        self.expect(TokenType.INDENT)
        self.skip_newlines()

        as_token = self.current_token()
        if not self.match(TokenType.AS):
            raise make_parse_error(
                f"Expected 'as:' clause in scope rule, got {as_token.type.value}",
                self.file,
                as_token.line,
                as_token.column,
            )
        self.advance()
        self.expect(TokenType.COLON)

        # Parse comma-separated role names or '*'
        personas: list[str] = []
        if self.match(TokenType.STAR):
            self.advance()
            personas = ["*"]
        else:
            personas.append(self.expect_identifier_or_keyword().value)
            while self.match(TokenType.COMMA):
                self.advance()
                personas.append(self.expect_identifier_or_keyword().value)

        self.skip_newlines()
        self.expect(TokenType.DEDENT)

        return ir.ScopeRule(
            operation=operation,
            condition=condition,
            personas=personas,
        )

    def _parse_not_via_condition(self) -> ir.ConditionExpr:
        """Parse a negated junction condition: ``not via Entity(bindings)``.

        Parses the via clause and sets ``negated=True`` on the resulting
        ``ViaCondition``.  Produces a ``ConditionExpr(via_condition=...)``
        where ``via_condition.negated is True``.

        The other negation form — ``not (condition)`` — is handled by the
        general expression parser (``_parse_primary_condition`` in
        ``conditions.py``), so a negated group composes with ``and``/``or``
        like any other primary (#1180). The caller only routes here when the
        token after ``not`` is ``via``.
        """
        self.expect(TokenType.NOT)
        inner = self._parse_via_condition()
        # The inner expr has a via_condition; rebuild it with negated=True
        assert inner.via_condition is not None
        negated_via = ir.ViaCondition(
            junction_entity=inner.via_condition.junction_entity,
            bindings=inner.via_condition.bindings,
            negated=True,
        )
        return ir.ConditionExpr(via_condition=negated_via)

    def _parse_via_condition(self) -> ir.ConditionExpr:
        """Parse a ``via JunctionEntity(...)`` clause inside a ``scope:`` rule.

        Refactored from a 153-line flat function into a thin orchestration
        sequence + four extracted helpers (junction name, binding loop,
        post-loop validation, and the per-binding parser).

        Syntax::

            via JunctionEntity(field = current_user.attr, field = id, field = null)

        Returns a :class:`ir.ConditionExpr` with ``via_condition`` populated.
        """
        self.expect(TokenType.VIA)
        junction_entity = self._parse_via_junction_name()
        self._expect_via_lparen(junction_entity)
        bindings = self._parse_via_bindings()
        self.expect(TokenType.RPAREN)
        self._validate_via_bindings(bindings)
        return ir.ConditionExpr(
            via_condition=ir.ViaCondition(junction_entity=junction_entity, bindings=bindings)
        )

    # ---------- _parse_via_condition phase helpers ---------- #

    def _parse_via_junction_name(self) -> str:
        """Phase: consume the ``JunctionEntity`` IDENT after ``via``."""
        junction_token = self.current_token()
        if junction_token.type != TokenType.IDENTIFIER:
            raise make_parse_error(
                f"Expected junction entity name after 'via', got {junction_token.type.value!r}",
                self.file,
                junction_token.line,
                junction_token.column,
            )
        self.advance()
        name: str = junction_token.value
        return name

    def _expect_via_lparen(self, junction_entity: str) -> None:
        """Phase: consume the ``(`` after the junction-entity name."""
        lparen_token = self.current_token()
        if not self.match(TokenType.LPAREN):
            raise make_parse_error(
                f"Expected '(' after junction entity name '{junction_entity}'",
                self.file,
                lparen_token.line,
                lparen_token.column,
            )
        self.advance()

    def _parse_via_bindings(self) -> list[ir.ViaBinding]:
        """Phase: consume the comma-separated bindings up to (but not past) ``)``."""
        bindings: list[ir.ViaBinding] = []
        while not self.match(TokenType.RPAREN):
            bindings.append(self._parse_via_binding())
            if self.match(TokenType.COMMA):
                self.advance()
        return bindings

    def _parse_via_binding(self) -> ir.ViaBinding:
        """Phase: parse one ``<field[.path]> <op> <target>`` binding."""
        junction_field = self._parse_via_field_path()
        operator = self._parse_via_operator()
        target = self._parse_via_target()
        return ir.ViaBinding(junction_field=junction_field, target=target, operator=operator)

    def _parse_via_field_path(self) -> str:
        """Phase: parse ``field`` or ``field.path.segments`` (#858)."""
        field_token = self.current_token()
        if field_token.type != TokenType.IDENTIFIER and not self._is_keyword_as_identifier():
            raise make_parse_error(
                f"Expected field name in via binding, got {field_token.type.value!r}",
                self.file,
                field_token.line,
                field_token.column,
            )
        path: str = field_token.value
        self.advance()
        # Dotted continuation: #858 — JOIN-chain through the junction's FK graph.
        while self.match(TokenType.DOT):
            self.advance()
            segment_token = self.current_token()
            if segment_token.type != TokenType.IDENTIFIER:
                raise make_parse_error(
                    f"Expected field name after '.' in via binding, "
                    f"got {segment_token.type.value!r}",
                    self.file,
                    segment_token.line,
                    segment_token.column,
                )
            path = f"{path}.{segment_token.value}"
            self.advance()
        return path

    def _parse_via_operator(self) -> str:
        """Phase: consume ``=`` or ``!=`` between field and target."""
        op_token = self.current_token()
        if self.match(TokenType.EQUALS):
            self.advance()
            return "="
        if self.match(TokenType.NOT_EQUALS):
            self.advance()
            return "!="
        raise make_parse_error(
            f"Expected '=' or '!=' in via binding, got {op_token.type.value!r}",
            self.file,
            op_token.line,
            op_token.column,
        )

    def _parse_via_target(self) -> str:
        """Phase: parse ``current_user[.attr]`` / ``null`` / field name target.

        Normalises ``None`` → ``null`` (legacy lenient form).
        """
        target_token = self.current_token()
        if target_token.type != TokenType.IDENTIFIER:
            raise make_parse_error(
                f"Expected target value in via binding, got {target_token.type.value!r}",
                self.file,
                target_token.line,
                target_token.column,
            )
        target: str = target_token.value
        self.advance()
        # current_user.attr form
        if target == "current_user" and self.match(TokenType.DOT):
            self.advance()
            attr_token = self.current_token()
            if attr_token.type != TokenType.IDENTIFIER:
                raise make_parse_error(
                    f"Expected attribute name after 'current_user.', got {attr_token.type.value!r}",
                    self.file,
                    attr_token.line,
                    attr_token.column,
                )
            target = f"current_user.{attr_token.value}"
            self.advance()
        # Normalise None → null
        if target == "None":
            target = "null"
        return target

    def _validate_via_bindings(self, bindings: list[ir.ViaBinding]) -> None:
        """Phase: require at least one entity binding and one user binding.

        Entity bindings link the junction table back to the scoped entity
        (e.g. ``contact = id``). User bindings tie the rule to the requester
        (e.g. ``agent = current_user`` or ``agent = current_user.contact``).
        """
        entity_bindings = [
            b
            for b in bindings
            if b.target not in ("null", "None") and not b.target.startswith("current_user")
        ]
        user_bindings = [b for b in bindings if b.target.startswith("current_user")]

        if not entity_bindings:
            tok = self.current_token()
            raise make_parse_error(
                "via clause must have at least one entity binding "
                "(e.g. 'contact = id') linking the junction table back to the scoped entity",
                self.file,
                tok.line,
                tok.column,
            )

        if not user_bindings:
            tok = self.current_token()
            raise make_parse_error(
                "via clause must have at least one user binding "
                "(e.g. 'agent = current_user' or 'agent = current_user.contact')",
                self.file,
                tok.line,
                tok.column,
            )

    def _parse_bulk_config(self) -> ir.BulkConfig:
        """
        Parse bulk: block.

        Syntax:
            bulk: all                          # import + export, csv
            bulk: import                       # import only
            bulk: export                       # export only
            bulk:
              import: true
              export: true
              formats: [csv, json, xlsx]
        """
        # Simple forms: bulk: all / bulk: import / bulk: export
        if self.match(TokenType.ALL):
            self.advance()
            return ir.BulkConfig(import_enabled=True, export_enabled=True)

        if self.match(TokenType.IMPORT):
            self.advance()
            return ir.BulkConfig(import_enabled=True, export_enabled=False)

        if self.match(TokenType.EXPORT):
            self.advance()
            return ir.BulkConfig(import_enabled=False, export_enabled=True)

        if self.match(TokenType.TRUE):
            self.advance()
            return ir.BulkConfig(import_enabled=True, export_enabled=True)

        # Block form
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        import_enabled = True
        export_enabled = True
        formats: list[ir.BulkFormat] = [ir.BulkFormat.CSV]

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if key == "import":
                if self.match(TokenType.TRUE):
                    self.advance()
                    import_enabled = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    import_enabled = False
                else:
                    import_enabled = True

            elif key == "export":
                if self.match(TokenType.TRUE):
                    self.advance()
                    export_enabled = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    export_enabled = False
                else:
                    export_enabled = True

            elif key == "formats":
                formats = []
                self.expect(TokenType.LBRACKET)
                while not self.match(TokenType.RBRACKET):
                    fmt_token = self.expect_identifier_or_keyword()
                    formats.append(self.enum_from_token(ir.BulkFormat, fmt_token))
                    if self.match(TokenType.COMMA):
                        self.advance()
                self.expect(TokenType.RBRACKET)

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.BulkConfig(
            import_enabled=import_enabled,
            export_enabled=export_enabled,
            formats=formats,
        )

    def _parse_seed_template(self) -> ir.SeedTemplateSpec:
        """
        Parse seed: block.

        Syntax:
            seed:
              strategy: rolling_window
              window_start: -1
              window_end: 3
              month_anchor: 9
              match_field: name
              fields:
                name: "{y}/{y1_short}"
                start_date: "{y}-09-01"
                end_date: "{y1}-08-31"
                is_current: "y == current_year"
        """
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        strategy = ir.SeedStrategy.ROLLING_WINDOW
        window_start = -1
        window_end = 3
        month_anchor = 1
        match_field: str | None = None
        field_templates: list[ir.SeedFieldTemplate] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if key == "strategy":
                val = self.expect_identifier_or_keyword().value
                if val == "rolling_window":
                    strategy = ir.SeedStrategy.ROLLING_WINDOW
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Unknown seed strategy '{val}'",
                        self.file,
                        token.line,
                        token.column,
                    )

            elif key in ("window_start", "window_end"):
                sign = 1
                if self.match(TokenType.MINUS):
                    self.advance()
                    sign = -1
                elif self.match(TokenType.PLUS):
                    self.advance()
                num_tok = self.expect(TokenType.NUMBER)
                val = sign * int(num_tok.value)
                if key == "window_start":
                    window_start = val
                else:
                    window_end = val

            elif key == "month_anchor":
                month_tok = self.expect(TokenType.NUMBER)
                month_anchor = int(month_tok.value)

            elif key == "match_field":
                match_field = self.expect_identifier_or_keyword().value

            elif key == "fields":
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    field_name = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.COLON)
                    template_val = self.expect(TokenType.STRING).value
                    field_templates.append(
                        ir.SeedFieldTemplate(field=field_name, template=template_val)
                    )
                    self.skip_newlines()
                self.expect(TokenType.DEDENT)

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.SeedTemplateSpec(
            strategy=strategy,
            window_start=window_start,
            window_end=window_end,
            month_anchor=month_anchor,
            match_field=match_field,
            fields=field_templates,
        )

    def _parse_audit_directive(self) -> ir.AuditConfig:
        """
        Parse audit: directive.

        Syntax:
            audit: all
            audit: [create, update, delete]
        """
        # Check for "all" keyword
        if self.match(TokenType.ALL):
            self.advance()
            return ir.AuditConfig(enabled=True, operations=[])

        # Check for bracket list of operations
        if self.match(TokenType.LBRACKET):
            self.advance()
            operations: list[ir.PermissionKind] = []
            op_map = {
                "create": ir.PermissionKind.CREATE,
                "read": ir.PermissionKind.READ,
                "update": ir.PermissionKind.UPDATE,
                "delete": ir.PermissionKind.DELETE,
                "list": ir.PermissionKind.LIST,
            }

            while not self.match(TokenType.RBRACKET):
                token = self.expect_identifier_or_keyword()
                if token.value not in op_map:
                    raise make_parse_error(
                        f"Expected operation name (create/read/update/delete/list), "
                        f"got '{token.value}'",
                        self.file,
                        token.line,
                        token.column,
                    )
                operations.append(op_map[token.value])
                if self.match(TokenType.COMMA):
                    self.advance()

            self.expect(TokenType.RBRACKET)
            return ir.AuditConfig(enabled=True, operations=operations)

        # Single boolean-like: true/false
        if self.match(TokenType.TRUE):
            self.advance()
            return ir.AuditConfig(enabled=True, operations=[])
        if self.match(TokenType.FALSE):
            self.advance()
            return ir.AuditConfig(enabled=False, operations=[])

        token = self.current_token()
        raise make_parse_error(
            f"Expected 'all', 'true', 'false', or [operations] after 'audit:', "
            f"got {token.type.value}",
            self.file,
            token.line,
            token.column,
        )

    def _parse_transition_inline_guard(
        self,
    ) -> tuple[
        list[ir.TransitionGuard],
        ir.TransitionTrigger,
        ir.AutoTransitionSpec | None,
    ]:
        """Parse inline guards/triggers on a single transition line.

        Returns (guards, trigger, auto_spec).
        """
        trigger = ir.TransitionTrigger.MANUAL
        guards: list[ir.TransitionGuard] = []
        auto_spec: ir.AutoTransitionSpec | None = None

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
                    delay_value = int(self.expect(TokenType.NUMBER).value)

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
                        delay_unit = ir.TimeUnit.DAYS

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
                token = self.current_token()
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
                        f"    guard: <expression>     # Expression guard (v0.29.0)\n"
                        f"  Example: open -> assigned: requires assignee",
                        self.file,
                        token.line,
                        token.column,
                    )
                elif token.type == TokenType.IDENTIFIER:
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
                break

        return guards, trigger, auto_spec

    def _parse_state_transition(self) -> ir.StateTransition:
        """
        Parse a state transition rule.

        Syntax (inline):
            open -> assigned: requires assignee
            published -> canonical requires summary  # colon-free form
            resolved -> closed: auto after 7 days OR manual
            * -> open: role(admin)

        Syntax (block, v0.29.0):
            sent -> signed:
              guard: self->signatory->aml_status == "completed"
                message: "Signatory must pass AML checks"
              requires assignee
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

        if self.match(TokenType.REQUIRES):
            # Colon-free inline guard: `published -> canonical requires summary`
            guards, trigger, auto_spec = self._parse_transition_inline_guard()
        elif self.match(TokenType.COLON):
            self.advance()

            # v0.29.0: Check for indented block (guard: expression syntax)
            if self.match(TokenType.NEWLINE):
                self.skip_newlines()
                if self.match(TokenType.INDENT):
                    self.advance()
                    guards, trigger, auto_spec = self._parse_transition_block()
                    self.expect(TokenType.DEDENT)
                # else: empty transition body, no guards
            else:
                # Inline guards on same line
                guards, trigger, auto_spec = self._parse_transition_inline_guard()

        return ir.StateTransition(
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            guards=guards,
            auto_spec=auto_spec,
        )

    def _parse_transition_block(
        self,
    ) -> tuple[
        list[ir.TransitionGuard],
        ir.TransitionTrigger,
        ir.AutoTransitionSpec | None,
    ]:
        """Parse an indented transition sub-block with guard: expressions.

        Supports:
            guard: <expression>
              message: "human-readable failure message"
            requires <field>
            role(<role_name>)
            auto after N days [OR manual]
            manual
        """
        trigger = ir.TransitionTrigger.MANUAL
        guards: list[ir.TransitionGuard] = []
        auto_spec: ir.AutoTransitionSpec | None = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            # v0.29.0: guard: <expression>
            if self.match(TokenType.GUARD):
                self.advance()
                self.expect(TokenType.COLON)
                guard_expr = self.collect_line_as_expr()
                guard_message: str | None = None

                # Check for optional indented message:
                self.skip_newlines()
                if self.match(TokenType.INDENT):
                    self.advance()
                    if self.match(TokenType.MESSAGE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        if self.match(TokenType.STRING):
                            guard_message = self.advance().value
                    self.skip_newlines()
                    self.expect(TokenType.DEDENT)

                guards.append(
                    ir.TransitionGuard(
                        guard_expr=guard_expr,
                        guard_message=guard_message,
                    )
                )

            # requires field_name
            elif self.match(TokenType.REQUIRES):
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
                    delay_value = int(self.expect(TokenType.NUMBER).value)

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
                        delay_unit = ir.TimeUnit.DAYS

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

            else:
                # Skip unknown tokens within block
                break

            self.skip_newlines()

        return guards, trigger, auto_spec

    def _parse_transition_effect(
        self,
    ) -> tuple[str, str, list[ir.StepEffect], ir.InvokeFlowSpec | None]:
        """Parse a single on_transition effect entry.

        Syntax:
            from_state -> to_state:
              create EntityName:
                field: value
              update EntityName:
                where: field = self.id
                field: value
              invoke flow_name(arg: self, other: input.x)   # #1319, ADR-0032
        """
        # Parse from_state (* for wildcard, or identifier)
        if self.match(TokenType.STAR):
            self.advance()
            from_state = "*"
        else:
            from_state = self.expect_identifier_or_keyword().value

        self.expect(TokenType.ARROW)
        to_state = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        effects: list[ir.StepEffect] = []
        invoke_flow: ir.InvokeFlowSpec | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse action keyword (create / update / invoke)
            action_token = self.current_token()
            action_str = str(action_token.value).lower()
            if action_str == "invoke":
                # `invoke flow_name(arg: <self|input.x|literal>, ...)` (#1319).
                if invoke_flow is not None:
                    raise make_parse_error(
                        "a transition may declare at most one `invoke` in this release",
                        self.file,
                        action_token.line,
                        action_token.column,
                    )
                invoke_flow = self._parse_transition_invoke()
                self.skip_newlines()
                continue
            if action_str == "create":
                action = ir.EffectAction.CREATE
            elif action_str == "update":
                action = ir.EffectAction.UPDATE
            else:
                raise make_parse_error(
                    "Expected 'create', 'update', or 'invoke' in on_transition effect, "
                    f"got '{action_str}'",
                    self.file,
                    action_token.line,
                    action_token.column,
                )
            self.advance()

            # Parse entity name
            entity_name = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)
            self.skip_newlines()

            # Parse effect body: field assignments + optional where
            where_clause: str | None = None
            assignments: list[ir.FieldAssignment] = []

            if self.match(TokenType.INDENT):
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    token = self.current_token()
                    field_name = str(token.value)

                    if field_name.lower() == "where" or self.match(TokenType.WHERE):
                        self.advance()
                        self.expect(TokenType.COLON)
                        where_clause = self._collect_line_text()
                        self.skip_newlines()
                    else:
                        # field: value assignment
                        self.advance()
                        self.expect(TokenType.COLON)
                        value = self._collect_line_text()
                        assignments.append(
                            ir.FieldAssignment(
                                field_path=field_name,
                                value=value,
                            )
                        )
                        self.skip_newlines()

                self.expect(TokenType.DEDENT)

            effects.append(
                ir.StepEffect(
                    action=action,
                    entity_name=entity_name,
                    where=where_clause,
                    assignments=assignments,
                )
            )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return (from_state, to_state, effects, invoke_flow)

    def _parse_transition_invoke(self) -> ir.InvokeFlowSpec:
        """Parse ``invoke flow_name(arg: <self|input.x|literal>, ...)`` (#1319, ADR-0032)."""
        self.advance()  # consume `invoke`
        flow_name = str(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.LPAREN)
        bindings: list[ir.InvokeBinding] = []
        while not self.match(TokenType.RPAREN):
            arg = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)
            src = self.current_token()
            src_val = str(src.value)
            if src_val == "self":
                self.advance()
                bindings.append(
                    ir.InvokeBinding(flow_input=arg, source_kind=ir.InvokeSourceKind.SELF)
                )
            elif src_val == "input":
                self.advance()
                self.expect(TokenType.DOT)
                name = str(self.expect_identifier_or_keyword().value)
                bindings.append(
                    ir.InvokeBinding(
                        flow_input=arg,
                        source_kind=ir.InvokeSourceKind.INPUT,
                        source_name=name,
                    )
                )
            else:
                # Literal: a number or a bare identifier/string.
                self.advance()
                literal: str | int | float | bool = src_val
                if src.type == TokenType.NUMBER:
                    literal = int(src_val) if "." not in src_val else float(src_val)
                bindings.append(
                    ir.InvokeBinding(
                        flow_input=arg,
                        source_kind=ir.InvokeSourceKind.LITERAL,
                        literal=literal,
                    )
                )
            if self.match(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RPAREN)
        return ir.InvokeFlowSpec(flow_name=flow_name, bindings=bindings)

    def _collect_line_text(self) -> str:
        """Collect remaining tokens on the current line as a single string value.

        Preserves string literal quoting and merges dots without spaces.
        """
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.advance()
            # Re-add quotes for string tokens so SideEffectExecutor can identify them
            if token.type == TokenType.STRING:
                val = f'"{token.value}"'
            else:
                val = str(token.value)
            # Merge dots without spaces (e.g. self.field)
            if val == "." and parts:
                parts[-1] = parts[-1] + "."
            elif parts and parts[-1].endswith("."):
                parts[-1] = parts[-1] + val
            else:
                parts.append(val)
        return " ".join(parts).strip()

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
            invariant_primary ::= field_ref | NUMBER | STRING | BOOL
                | duration | date_expr | "(" invariant_expr ")"
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
            # Simplification; full support would need a dedicated InvariantDateExpr type
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
                # v0.30.0: Use unified expression language
                comp_expr = self.collect_line_as_expr()
                computed_fields.append(
                    ir.ComputedFieldSpec(
                        name=field_name,
                        computed_expr=comp_expr,
                    )
                )
            else:
                field_type = self.parse_type_spec()
                modifiers, default, default_expr, pii, storage = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                        default_expr=default_expr,
                        pii=pii,
                        storage=storage,
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


def _merge_transition_effects(
    transitions: list[ir.StateTransition],
    effects: list[tuple[str, str, list[ir.StepEffect], ir.InvokeFlowSpec | None]],
    file: Path,
    line: int,
) -> list[ir.StateTransition]:
    """Merge on_transition effects + invoke into existing StateTransition objects.

    Matches (from_state, to_state) pairs and reconstructs frozen models
    with effects + invoke_flow attached. Raises ParseError for unmatched references.
    """
    # Index transitions by (from_state, to_state)
    by_key: dict[tuple[str, str], int] = {}
    for i, t in enumerate(transitions):
        by_key[(t.from_state, t.to_state)] = i

    result = list(transitions)
    for from_state, to_state, step_effects, invoke_flow in effects:
        key = (from_state, to_state)
        idx = by_key.get(key)
        if idx is None:
            raise make_parse_error(
                f"on_transition references undefined transition: {from_state} -> {to_state}",
                file,
                line,
                0,
            )
        old = result[idx]
        result[idx] = ir.StateTransition(
            from_state=old.from_state,
            to_state=old.to_state,
            trigger=old.trigger,
            guards=old.guards,
            auto_spec=old.auto_spec,
            effects=list(old.effects) + step_effects,
            invoke_flow=invoke_flow if invoke_flow is not None else old.invoke_flow,
        )

    return result
