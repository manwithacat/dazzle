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
        # v0.29.0: Expression bridge from BaseParser
        collect_line_as_expr: Any
        # v0.31.0: Source location helper from BaseParser
        _source_location: Any

    def parse_entity(self) -> ir.EntitySpec:
        """Parse entity declaration."""
        name, title, loc = self._parse_construct_header(TokenType.ENTITY)

        # v0.7.1: New fields for LLM cognition
        intent: str | None = None
        domain: str | None = None
        patterns: list[str] = []
        extends: list[str] = []
        examples: list[ir.ExampleRecord] = []
        # v0.10.3: Semantic archetype
        archetype_kind: ir.ArchetypeKind | None = None
        # v0.34.0: Soft delete and bulk config
        soft_delete: bool = False
        bulk_config: ir.BulkConfig | None = None

        fields: list[ir.FieldSpec] = []
        computed_fields: list[ir.ComputedFieldSpec] = []
        constraints: list[ir.Constraint] = []
        visibility_rules: list[ir.VisibilityRule] = []
        permission_rules: list[ir.PermissionRule] = []
        transitions: list[ir.StateTransition] = []
        invariants: list[ir.InvariantSpec] = []
        publishes: list[ir.PublishSpec] = []
        audit_config: ir.AuditConfig | None = None

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
                # v0.30.0: Use unified expression language
                inv_expr = self.collect_line_as_expr()
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
                    ir.InvariantSpec(
                        invariant_expr=inv_expr,
                        message=inv_message,
                        code=inv_code,
                    )
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

                    # Parse read:, write:, delete:, create:, or list: rule
                    if self.match(TokenType.READ):
                        self.advance()
                        self.expect(TokenType.COLON)
                        condition = self.parse_condition_expr()
                        # read: maps to both visibility rule AND permit READ
                        visibility_rules.append(
                            ir.VisibilityRule(
                                context=ir.AuthContext.AUTHENTICATED,
                                condition=condition,
                            )
                        )
                        permission_rules.append(
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
                        # write: maps to CREATE, UPDATE permissions
                        for op in [
                            ir.PermissionKind.CREATE,
                            ir.PermissionKind.UPDATE,
                        ]:
                            permission_rules.append(
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
                        permission_rules.append(
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
                        permission_rules.append(
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
                        permission_rules.append(
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
                self.skip_newlines()
                continue

            # Check for permit: block (Cedar-style explicit permit rules)
            if self.match(TokenType.PERMIT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    rule = self._parse_policy_rule(ir.PolicyEffect.PERMIT)
                    permission_rules.append(rule)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for forbid: block (Cedar-style explicit forbid rules)
            if self.match(TokenType.FORBID):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    rule = self._parse_policy_rule(ir.PolicyEffect.FORBID)
                    permission_rules.append(rule)
                    self.skip_newlines()

                self.expect(TokenType.DEDENT)
                self.skip_newlines()
                continue

            # Check for audit: directive
            if self.match(TokenType.AUDIT):
                self.advance()
                self.expect(TokenType.COLON)
                audit_config = self._parse_audit_directive()
                self.skip_newlines()
                continue

            # v0.34.0: Check for soft_delete flag
            if self.match(TokenType.SOFT_DELETE):
                self.advance()
                soft_delete = True
                self.skip_newlines()
                continue

            # v0.34.0: Check for bulk: block
            if self.match(TokenType.BULK):
                self.advance()
                self.expect(TokenType.COLON)
                bulk_config = self._parse_bulk_config()
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
                modifiers, default, default_expr = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                        default_expr=default_expr,
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
            # Find the enum field whose values contain all transition states.
            # This handles entities where the state machine field is not named
            # "status" (e.g. dunning_stage on SubscriptionInvoice).
            status_field_name = None
            states: list[str] = []
            all_transition_states = {t.from_state for t in transitions} | {
                t.to_state for t in transitions
            }
            for field in fields:
                if field.type.kind == ir.FieldTypeKind.ENUM and field.type.enum_values:
                    if all_transition_states.issubset(set(field.type.enum_values)):
                        status_field_name = field.name
                        states = field.type.enum_values
                        break
            # Fallback: field named "status" (backward compat)
            if not status_field_name:
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
            audit=audit_config,
            soft_delete=soft_delete,
            bulk=bulk_config,
            state_machine=state_machine,
            examples=examples,
            publishes=publishes,
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
        return ir.PermissionRule(
            operation=operation,
            require_auth=True,
            condition=condition,
            effect=effect,
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
                    formats.append(ir.BulkFormat(fmt_token.value))
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

        if self.match(TokenType.COLON):
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
                modifiers, default, default_expr = self.parse_field_modifiers()

                fields.append(
                    ir.FieldSpec(
                        name=field_name,
                        type=field_type,
                        modifiers=modifiers,
                        default=default,
                        default_expr=default_expr,
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
